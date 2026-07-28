# -*- coding: utf-8 -*-
"""VAAL — 바이브코딩 자산 아카이버 & 런처 (Flask 웹앱)."""
import json
import os
import re
import secrets
import threading
from functools import wraps

from flask import Flask, g, jsonify, redirect, render_template, request, session, url_for

import archiver
import auth
import i18n
import pipeline
import trends
from config import ARCHIVE_DIR, CATEGORIES, PORT, PUBLIC_PREVIEW_LIMIT, READONLY, TYPES
from db import (asset_dict, connect, get_settings, init_db, now_iso,
                set_setting)

app = Flask(__name__)
app.config["TEMPLATES_AUTO_RELOAD"] = True  # debug=False에서도 템플릿 수정 반영
# 세션 서명 키 — 배포 시 반드시 SECRET_KEY 환경변수로 진짜 값을 지정해야 한다.
# (여러 워커/재시작 간 세션이 유지되려면 고정된 값이 필요하다.)
app.secret_key = os.environ.get("SECRET_KEY") or "insecure-dev-key-set-SECRET_KEY-env-var"


@app.before_request
def _set_locale():
    g.lang = i18n.resolve_locale(request.cookies.get("lang"))


@app.context_processor
def _inject_i18n():
    lang = getattr(g, "lang", i18n.DEFAULT_LOCALE)
    u = current_user()
    return {
        "lang": lang,
        "t": lambda key: i18n.T[lang].get(key, i18n.T[i18n.DEFAULT_LOCALE].get(key, key)),
        "t_json": i18n.T[lang],
        "type_labels": i18n.TYPE_LABELS[lang],
        "source_labels": i18n.SOURCE_LABELS[lang],
        "category_label": lambda c: i18n.category_label(c, lang),
        "category_labels_json": {c: i18n.category_label(c, lang) for c in CATEGORIES},
        "user": u,
        "is_admin": bool(u and auth.is_admin_email(u["email"])),
    }


@app.route("/lang/<code>")
def set_lang(code):
    resp = redirect(request.args.get("next") or "/")
    resp.set_cookie("lang", i18n.resolve_locale(code), max_age=31536000, samesite="Lax")
    return resp


def _e(key):
    lang = getattr(g, "lang", i18n.DEFAULT_LOCALE)
    return i18n.T[lang].get(key, i18n.T[i18n.DEFAULT_LOCALE][key])

# 파이프라인 백그라운드 실행 상태
_pipe_state = {"running": False, "log": [], "stats": None}
_pipe_lock = threading.Lock()


def get_db():
    if "db" not in g:
        g.db = connect()
    return g.db


@app.teardown_appcontext
def close_db(_exc):
    db = g.pop("db", None)
    if db is not None:
        db.close()


def guard_readonly():
    if READONLY:
        return jsonify({"error": _e("api.readonly")}), 403
    return None


# ---------- 계정/인증 ----------

def current_user():
    if "user" not in g:
        uid = session.get("user_id")
        g.user = get_db().execute("SELECT * FROM users WHERE id = ?",
                                  (uid,)).fetchone() if uid else None
    return g.user


def login_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if not current_user():
            if request.path.startswith("/api/"):
                return jsonify({"error": _e("api.login_required")}), 401
            return redirect(url_for("login", next=request.path))
        return view(*args, **kwargs)
    return wrapped


def admin_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        u = current_user()
        if not u or not auth.is_admin_email(u["email"]):
            if request.path.startswith("/api/"):
                return jsonify({"error": _e("api.admin_only")}), 403
            return redirect(url_for("login", next=request.path))
        return view(*args, **kwargs)
    return wrapped


# ---------- 페이지 ----------

@app.route("/app")
def index():
    return render_template("index.html", types=TYPES, categories=CATEGORIES,
                           readonly=READONLY)


@app.route("/")
def landing():
    db = get_db()
    total = db.execute("SELECT COUNT(*) AS n FROM assets").fetchone()["n"]
    archived = db.execute("SELECT COUNT(*) AS n FROM assets "
                          "WHERE archive_status = 'archived'").fetchone()["n"]
    official = db.execute("SELECT COUNT(*) AS n FROM assets "
                          "WHERE is_official = 1").fetchone()["n"]
    # 데모용 실행 예시 — 공식·허용 라이선스·실행 템플릿이 실제로 있는 자산 중 트렌드 1위
    demo = db.execute(
        "SELECT title, type, description, terminal_template, claude_code_template, "
        "       source_url, repo_full_name, license "
        "FROM assets WHERE is_official = 1 AND terminal_template != '' "
        "AND claude_code_template != '' ORDER BY trend_score DESC LIMIT 1"
    ).fetchone()
    return render_template("landing.html", total=total, archived=archived,
                           official=official, demo=demo)


@app.route("/privacy")
def privacy():
    return render_template("privacy.html")


@app.route("/signup", methods=["GET", "POST"])
def signup():
    error = None
    if request.method == "POST":
        email = (request.form.get("email") or "").strip().lower()
        pw = request.form.get("password") or ""
        pw2 = request.form.get("password_confirm") or ""
        if not re.match(r"^[^@\s]+@[^@\s]+\.[^@\s]+$", email):
            error = _e("api.email_invalid")
        elif len(pw) < 8:
            error = _e("auth.err_password_short")
        elif pw != pw2:
            error = _e("auth.err_password_mismatch")
        else:
            db = get_db()
            if db.execute("SELECT 1 FROM users WHERE email = ?", (email,)).fetchone():
                error = _e("auth.err_email_taken")
            else:
                token = auth.new_token()
                db.execute(
                    "INSERT INTO users (email, password_hash, verify_token, verify_sent_at, created_at) "
                    "VALUES (?, ?, ?, ?, ?)",
                    (email, auth.hash_password(pw), token, now_iso(), now_iso()))
                db.commit()
                verify_url = url_for("verify_email", token=token, _external=True)
                auth.send_verification_email(email, verify_url, log=print)
                return render_template("signup.html", sent_to=email)
    return render_template("signup.html", error=error)


@app.route("/login", methods=["GET", "POST"])
def login():
    error = None
    if request.method == "POST":
        email = (request.form.get("email") or "").strip().lower()
        pw = request.form.get("password") or ""
        row = get_db().execute("SELECT * FROM users WHERE email = ?", (email,)).fetchone()
        if not row or not auth.verify_password(pw, row["password_hash"]):
            error = _e("auth.err_invalid_credentials")
        elif not row["email_verified"]:
            error = _e("auth.err_not_verified")
        else:
            session.clear()
            session["user_id"] = row["id"]
            session.permanent = True
            return redirect(request.args.get("next") or request.form.get("next") or "/app")
    return render_template("login.html", error=error, next=request.args.get("next", ""))


@app.route("/logout")
def logout():
    session.clear()
    return redirect(request.referrer or "/")


@app.route("/verify/<token>")
def verify_email(token):
    db = get_db()
    row = db.execute("SELECT * FROM users WHERE verify_token = ? AND verify_token != ''",
                     (token,)).fetchone()
    if row:
        db.execute("UPDATE users SET email_verified = 1, verify_token = '' WHERE id = ?",
                  (row["id"],))
        db.commit()
    return render_template("verify.html", ok=bool(row))


@app.route("/api/waitlist", methods=["POST"])
def api_waitlist():
    data = request.get_json(force=True, silent=True) or {}
    email = (data.get("email") or "").strip().lower()
    if not re.match(r"^[^@\s]+@[^@\s]+\.[^@\s]+$", email):
        return jsonify({"error": _e("api.email_invalid")}), 400
    db = get_db()
    db.execute("INSERT OR IGNORE INTO waitlist (email, created_at) VALUES (?, ?)",
              (email[:200], now_iso()))
    db.commit()
    return jsonify({"ok": True})


# ---------- 자산 목록/상세 ----------

SORTS = {
    "trend": "trend_score DESC, popularity DESC",
    "recent": "collected_at DESC",
    "rating": "user_rating IS NULL, user_rating DESC, trend_score DESC",
    "popular": "popularity DESC",
    "usage": "usage_count DESC, trend_score DESC",
}


@app.route("/api/assets")
def api_assets():
    q = (request.args.get("q") or "").strip()
    atype = request.args.get("type") or ""
    source = request.args.get("source") or ""
    target = request.args.get("target") or ""
    category = request.args.get("category") or ""
    sort = SORTS.get(request.args.get("sort") or "trend", SORTS["trend"])
    flt = request.args.get("filter") or ""

    sql = ("SELECT * FROM assets WHERE 1=1")
    args = []
    if atype:
        sql += " AND type = ?"
        args.append(atype)
    if source:
        sql += " AND source = ?"
        args.append(source)
    if target:
        sql += " AND target_tool = ?"
        args.append(target)
    if category:
        sql += " AND category = ?"
        args.append(category)
    if q:
        sql += (" AND (title LIKE ? OR description LIKE ? OR purpose_summary LIKE ?"
                " OR usage_summary LIKE ? OR tags LIKE ? OR repo_full_name LIKE ?)")
        args += [f"%{q}%"] * 6
    u = current_user()
    if flt == "favorite":
        if not u:
            return jsonify([])
        sql += " AND id IN (SELECT asset_id FROM favorites WHERE user_id = ?)"
        args.append(u["id"])
    elif flt == "rated":
        sql += " AND user_rating IS NOT NULL"
    elif flt == "unrated":
        sql += " AND user_rating IS NULL"
    elif flt == "official":
        sql += " AND is_official = 1"
    elif flt == "recommended":
        # 추천 힌트 (기획서 6.5): 고평점·애용 자산과 태그가 겹치는 신규 자산
        sql += " AND id IN (SELECT id FROM assets WHERE " + _recommend_where() + ")"
    sql += f" ORDER BY {sort} LIMIT 500"

    db = get_db()
    rows = db.execute(sql, args).fetchall()
    my_favs = _my_favorite_ids(db, u)
    return jsonify([_asset_dict_with_fav(r, my_favs) for r in rows])


def _my_favorite_ids(db, user):
    if not user:
        return set()
    return {r["asset_id"] for r in
            db.execute("SELECT asset_id FROM favorites WHERE user_id = ?", (user["id"],))}


def _asset_dict_with_fav(row, fav_ids):
    d = asset_dict(row)
    d["my_favorite"] = row["id"] in fav_ids
    return d


def _recommend_where():
    """추천: 미평가·신규(14일)이면서, 좋아하는 자산과 태그·타입이 겹침."""
    return ("user_rating IS NULL AND collected_at >= datetime('now', '-14 days') "
            "AND type IN (SELECT type FROM assets "
            "             WHERE user_rating >= 4 OR usage_count >= 3)")


@app.route("/api/assets/<int:asset_id>")
def api_asset_detail(asset_id):
    row = get_db().execute("SELECT * FROM assets WHERE id = ?",
                           (asset_id,)).fetchone()
    if not row:
        return jsonify({"error": _e("api.not_found")}), 404
    db = get_db()
    d = _asset_dict_with_fav(row, _my_favorite_ids(db, current_user()))
    # 원문 미리보기 (아카이브에서) — 공개 배포(READONLY)에서는 18장 규칙대로
    # 라이선스가 허용 목록에 있을 때만, 그것도 짧은 스니펫만 노출한다.
    archived = row["archive_status"] == "archived"
    gated = archived and READONLY and not archiver.license_allows_preview(row["license"])
    if archived and not gated:
        limit = PUBLIC_PREVIEW_LIMIT if READONLY else 2500
        d["original_preview"] = archiver.read_original(row, limit)
    else:
        d["original_preview"] = ""
    d["preview_gated"] = gated
    return jsonify(d)


# ---------- 평가 (기획서 6.5) ----------

@app.route("/api/assets/<int:asset_id>/rate", methods=["POST"])
@admin_required
def api_rate(asset_id):
    if (err := guard_readonly()):
        return err
    data = request.get_json(force=True, silent=True) or {}
    db = get_db()
    sets, args = [], []
    if "rating" in data:
        rating = data["rating"]
        if rating is not None and not (isinstance(rating, int) and 1 <= rating <= 5):
            return jsonify({"error": _e("api.rating_invalid")}), 400
        sets.append("user_rating = ?")
        args.append(rating)
    if "review" in data:
        sets.append("review_note = ?")
        args.append(str(data["review"])[:2000])
    if not sets:
        return jsonify({"error": _e("api.no_changes")}), 400
    sets.append("updated_at = ?")
    args += [now_iso(), asset_id]
    db.execute(f"UPDATE assets SET {', '.join(sets)} WHERE id = ?", args)
    db.commit()
    row = db.execute("SELECT * FROM assets WHERE id = ?", (asset_id,)).fetchone()
    if row and row["archive_status"] == "archived":
        archiver.write_meta(db, row)  # meta.md에 평가 반영
        db.commit()
    return jsonify(asset_dict(row))


# ---------- 개인 즐겨찾기 (로그인 사용자 누구나) ----------

@app.route("/api/favorites/<int:asset_id>", methods=["POST", "DELETE"])
@login_required
def api_favorite(asset_id):
    u = current_user()
    db = get_db()
    if request.method == "POST":
        db.execute("INSERT OR IGNORE INTO favorites (user_id, asset_id, created_at) "
                  "VALUES (?, ?, ?)", (u["id"], asset_id, now_iso()))
    else:
        db.execute("DELETE FROM favorites WHERE user_id = ? AND asset_id = ?",
                  (u["id"], asset_id))
    db.commit()
    return jsonify({"ok": True})


# ---------- 복사 이력 (기획서 6.7 — 내부 사용 빈도 신호) ----------

@app.route("/api/assets/<int:asset_id>/used", methods=["POST"])
def api_used(asset_id):
    if (err := guard_readonly()):
        return err
    data = request.get_json(force=True, silent=True) or {}
    variant = data.get("variant") or "terminal"
    db = get_db()
    db.execute("INSERT INTO usage_log (asset_id, variant, used_at) VALUES (?, ?, ?)",
               (asset_id, variant[:20], now_iso()))
    db.execute("UPDATE assets SET usage_count = usage_count + 1 WHERE id = ?",
               (asset_id,))
    db.commit()
    row = db.execute("SELECT usage_count FROM assets WHERE id = ?",
                     (asset_id,)).fetchone()
    return jsonify({"usage_count": row["usage_count"] if row else 0})


# ---------- 수동 링크 큐 (X 대체) ----------

@app.route("/api/queue", methods=["GET", "POST"])
def api_queue():
    db = get_db()
    if request.method == "GET":
        rows = db.execute(
            "SELECT * FROM link_queue ORDER BY id DESC LIMIT 100").fetchall()
        return jsonify([dict(r) for r in rows])
    if (err := guard_readonly()):
        return err
    data = request.get_json(force=True, silent=True) or {}
    url = (data.get("url") or "").strip()
    if not url.startswith(("http://", "https://")):
        return jsonify({"error": _e("api.url_required")}), 400
    db.execute("INSERT INTO link_queue (url, note, created_at) VALUES (?, ?, ?)",
               (url, str(data.get("note", ""))[:500], now_iso()))
    db.commit()
    return jsonify({"ok": True})


# ---------- 파이프라인 실행 ----------

def _run_pipeline_bg(steps, use_ai, ai_limit):
    log_list = _pipe_state["log"]

    def log(msg):
        log_list.append(str(msg))
        if len(log_list) > 400:
            del log_list[:100]

    try:
        stats = pipeline.run(steps=steps, use_ai=use_ai, ai_limit=ai_limit, log=log)
        _pipe_state["stats"] = stats
    except Exception as e:  # noqa: BLE001 — UI에 실패를 보여줘야 한다
        log(f"[오류] {e!r}")
        _pipe_state["stats"] = {"error": str(e)}
    finally:
        _pipe_state["running"] = False


@app.route("/api/pipeline/run", methods=["POST"])
@admin_required
def api_pipeline_run():
    if (err := guard_readonly()):
        return err
    data = request.get_json(force=True, silent=True) or {}
    steps = data.get("steps") or pipeline.ALL_STEPS
    steps = [s for s in steps if s in pipeline.ALL_STEPS] or pipeline.ALL_STEPS
    with _pipe_lock:
        if _pipe_state["running"]:
            return jsonify({"error": _e("api.already_running")}), 409
        _pipe_state.update(running=True, log=[], stats=None)
    t = threading.Thread(target=_run_pipeline_bg,
                         args=(steps, bool(data.get("use_ai", True)),
                               int(data.get("ai_limit", 40))),
                         daemon=True)
    t.start()
    return jsonify({"ok": True, "steps": steps})


@app.route("/api/pipeline/status")
def api_pipeline_status():
    return jsonify({"running": _pipe_state["running"],
                    "log": _pipe_state["log"][-60:],
                    "stats": _pipe_state["stats"]})


# ---------- 통계/리포트 ----------

@app.route("/api/stats")
def api_stats():
    db = get_db()
    total = db.execute("SELECT COUNT(*) AS n FROM assets").fetchone()["n"]
    by_type = {r["type"]: r["n"] for r in db.execute(
        "SELECT type, COUNT(*) AS n FROM assets GROUP BY type")}
    by_source = {r["source"]: r["n"] for r in db.execute(
        "SELECT source, COUNT(*) AS n FROM assets GROUP BY source")}
    by_category = {r["category"]: r["n"] for r in db.execute(
        "SELECT category, COUNT(*) AS n FROM assets WHERE category != '' "
        "GROUP BY category ORDER BY n DESC")}
    archived = db.execute("SELECT COUNT(*) AS n FROM assets "
                          "WHERE archive_status = 'archived'").fetchone()["n"]
    rated = db.execute("SELECT COUNT(*) AS n FROM assets "
                       "WHERE user_rating IS NOT NULL").fetchone()["n"]
    week_new = db.execute("SELECT COUNT(*) AS n FROM assets "
                          "WHERE collected_at >= datetime('now', '-7 days')"
                          ).fetchone()["n"]
    week_used = db.execute("SELECT COUNT(*) AS n FROM usage_log "
                           "WHERE used_at >= datetime('now', '-7 days')"
                           ).fetchone()["n"]
    top_used = [dict(r) for r in db.execute(
        """SELECT a.id, a.title, a.type, COUNT(u.id) AS n FROM usage_log u
           JOIN assets a ON a.id = u.asset_id
           WHERE u.used_at >= datetime('now', '-7 days')
           GROUP BY u.asset_id ORDER BY n DESC LIMIT 5""")]
    rising = [dict(r) for r in db.execute(
        "SELECT id, title, type, trend_score FROM assets WHERE trend_badge = ? "
        "ORDER BY trend_score DESC LIMIT 8", (trends.BADGE_HOT,))]
    runs = [dict(r) for r in db.execute(
        "SELECT * FROM runs ORDER BY id DESC LIMIT 5")]
    return jsonify({
        "total": total, "by_type": by_type, "by_source": by_source,
        "by_category": by_category,
        "archived": archived, "rated": rated, "week_new": week_new,
        "week_used": week_used, "top_used": top_used, "rising": rising,
        "runs": runs, "archive_dir": ARCHIVE_DIR,
    })


# ---------- 설정 ----------

@app.route("/api/settings", methods=["GET", "POST"])
@admin_required
def api_settings():
    db = get_db()
    if request.method == "GET":
        return jsonify(get_settings(db))
    if (err := guard_readonly()):
        return err
    data = request.get_json(force=True, silent=True) or {}
    allowed = set(get_settings(db))
    for key, value in data.items():
        if key in allowed:
            set_setting(db, key, str(value))
    db.commit()
    return jsonify(get_settings(db))


# ---------- 아카이브 폴더 열기 ----------

@app.route("/api/open-archive", methods=["POST"])
@admin_required
def api_open_archive():
    if (err := guard_readonly()):
        return err
    data = request.get_json(force=True, silent=True) or {}
    sub = data.get("dir") or ""
    # 경로 탈출 방지: 아카이브 루트 아래만 허용
    target = os.path.realpath(os.path.join(ARCHIVE_DIR, sub))
    root = os.path.realpath(ARCHIVE_DIR)
    if not target.startswith(root):
        return jsonify({"error": _e("api.bad_path")}), 400
    if not os.path.isdir(target):
        target = root
    os.makedirs(target, exist_ok=True)
    os.startfile(target)  # Windows 탐색기
    return jsonify({"ok": True})


# ---------- 개인 모음집 + 공유 ----------

def _new_slug(db):
    slug = secrets.token_urlsafe(6)
    while db.execute("SELECT 1 FROM collections WHERE share_slug = ?", (slug,)).fetchone():
        slug = secrets.token_urlsafe(6)
    return slug


def _my_collections(db, user_id):
    return db.execute(
        """SELECT c.*, COUNT(ci.id) AS item_count FROM collections c
           LEFT JOIN collection_items ci ON ci.collection_id = c.id
           WHERE c.user_id = ? GROUP BY c.id ORDER BY c.created_at DESC""",
        (user_id,)).fetchall()


def _owned_collection(coll_id, user_id):
    return get_db().execute("SELECT * FROM collections WHERE id = ? AND user_id = ?",
                            (coll_id, user_id)).fetchone()


@app.route("/api/collections", methods=["GET", "POST"])
@login_required
def api_collections():
    db = get_db()
    u = current_user()
    if request.method == "GET":
        return jsonify([dict(r) for r in _my_collections(db, u["id"])])
    data = request.get_json(force=True, silent=True) or {}
    name = (data.get("name") or "").strip()[:100]
    if not name:
        return jsonify({"error": _e("coll.name_required")}), 400
    slug = _new_slug(db)
    db.execute("INSERT INTO collections (user_id, name, share_slug, created_at) "
              "VALUES (?, ?, ?, ?)", (u["id"], name, slug, now_iso()))
    db.commit()
    row = db.execute("SELECT c.*, 0 AS item_count FROM collections c WHERE share_slug = ?",
                     (slug,)).fetchone()
    return jsonify(dict(row))


@app.route("/api/collections/<int:coll_id>/items", methods=["POST"])
@login_required
def api_collection_add_item(coll_id):
    u = current_user()
    if not _owned_collection(coll_id, u["id"]):
        return jsonify({"error": _e("api.not_found")}), 404
    data = request.get_json(force=True, silent=True) or {}
    asset_id = data.get("asset_id")
    if not asset_id:
        return jsonify({"error": _e("api.no_changes")}), 400
    db = get_db()
    db.execute("INSERT OR IGNORE INTO collection_items (collection_id, asset_id, added_at) "
              "VALUES (?, ?, ?)", (coll_id, asset_id, now_iso()))
    db.commit()
    return jsonify({"ok": True})


@app.route("/api/collections/<int:coll_id>/items/<int:asset_id>", methods=["DELETE"])
@login_required
def api_collection_remove_item(coll_id, asset_id):
    u = current_user()
    if not _owned_collection(coll_id, u["id"]):
        return jsonify({"error": _e("api.not_found")}), 404
    db = get_db()
    db.execute("DELETE FROM collection_items WHERE collection_id = ? AND asset_id = ?",
              (coll_id, asset_id))
    db.commit()
    return jsonify({"ok": True})


@app.route("/collections")
@login_required
def collections_page():
    u = current_user()
    rows = _my_collections(get_db(), u["id"])
    return render_template("collections.html", collections=[dict(r) for r in rows])


@app.route("/c/<slug>")
def collection_public(slug):
    db = get_db()
    coll = db.execute("SELECT * FROM collections WHERE share_slug = ?", (slug,)).fetchone()
    if not coll:
        return render_template("collection_public.html", coll=None), 404
    items = db.execute(
        """SELECT a.* FROM collection_items ci JOIN assets a ON a.id = ci.asset_id
           WHERE ci.collection_id = ? ORDER BY ci.added_at DESC""",
        (coll["id"],)).fetchall()
    u = current_user()
    is_owner = bool(u and u["id"] == coll["user_id"])
    return render_template("collection_public.html", coll=dict(coll),
                           items=[asset_dict(r) for r in items], is_owner=is_owner)


init_db()

if __name__ == "__main__":
    app.run(host="127.0.0.1", port=PORT, debug=False)

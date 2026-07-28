# -*- coding: utf-8 -*-
"""VAAL — 바이브코딩 자산 아카이버 & 런처 (Flask 웹앱)."""
import json
import os
import re
import threading

from flask import Flask, g, jsonify, redirect, render_template, request

import archiver
import i18n
import pipeline
import trends
from config import ARCHIVE_DIR, CATEGORIES, PORT, PUBLIC_PREVIEW_LIMIT, READONLY, TYPES
from db import (asset_dict, connect, get_settings, init_db, now_iso,
                set_setting)

app = Flask(__name__)
app.config["TEMPLATES_AUTO_RELOAD"] = True  # debug=False에서도 템플릿 수정 반영


@app.before_request
def _set_locale():
    g.lang = i18n.resolve_locale(request.cookies.get("lang"))


@app.context_processor
def _inject_i18n():
    lang = getattr(g, "lang", i18n.DEFAULT_LOCALE)
    return {
        "lang": lang,
        "t": lambda key: i18n.T[lang].get(key, i18n.T[i18n.DEFAULT_LOCALE].get(key, key)),
        "t_json": i18n.T[lang],
        "type_labels": i18n.TYPE_LABELS[lang],
        "source_labels": i18n.SOURCE_LABELS[lang],
        "category_label": lambda c: i18n.category_label(c, lang),
        "category_labels_json": {c: i18n.category_label(c, lang) for c in CATEGORIES},
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
    if flt == "favorite":
        sql += " AND is_favorite = 1"
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

    rows = get_db().execute(sql, args).fetchall()
    return jsonify([asset_dict(r) for r in rows])


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
    d = asset_dict(row)
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
    if "favorite" in data:
        sets.append("is_favorite = ?")
        args.append(1 if data["favorite"] else 0)
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


init_db()

if __name__ == "__main__":
    app.run(host="127.0.0.1", port=PORT, debug=False)

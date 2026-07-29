# -*- coding: utf-8 -*-
"""VAAL 데이터베이스 — 스키마, 마이그레이션, 설정 저장소."""
import json
import sqlite3
from datetime import datetime, timezone

from config import DB_PATH, DEFAULT_SETTINGS

SCHEMA = """
CREATE TABLE IF NOT EXISTS assets (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    source TEXT NOT NULL,
    source_url TEXT NOT NULL UNIQUE,
    type TEXT NOT NULL DEFAULT 'etc',
    title TEXT NOT NULL,
    target_tool TEXT NOT NULL DEFAULT 'common',
    repo_full_name TEXT DEFAULT '',
    asset_path TEXT DEFAULT '',          -- 저장소 내 자산 경로 (skills/docx 등)

    archive_dir TEXT DEFAULT '',         -- vaa-archive 기준 상대 경로
    raw_file_path TEXT DEFAULT '',
    meta_file_path TEXT DEFAULT '',
    content_hash TEXT DEFAULT '',        -- 원본 변경 감지용

    description TEXT DEFAULT '',         -- 출처가 준 원문 설명
    purpose_summary TEXT DEFAULT '',     -- AI 용도 요약
    usage_summary TEXT DEFAULT '',       -- AI 사용법 요약
    args_schema TEXT DEFAULT '[]',       -- JSON: [{name, required, description}]
    args_schema_en TEXT DEFAULT '[]',    -- 위 args_schema의 영어판 설명문
    terminal_template TEXT DEFAULT '',
    claude_code_template TEXT DEFAULT '',
    cursor_apply_guide TEXT DEFAULT '',
    install_command TEXT DEFAULT '',
    terminal_template_en TEXT DEFAULT '',      -- 위 네 필드의 영어판 (rule/etc만 실제로 다름)
    claude_code_template_en TEXT DEFAULT '',
    cursor_apply_guide_en TEXT DEFAULT '',
    install_command_en TEXT DEFAULT '',

    license TEXT DEFAULT '',
    is_official INTEGER DEFAULT 0,
    collected_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    source_updated_at TEXT DEFAULT '',   -- 원본 최근 푸시 시각

    -- 평가 (기획서 6.5)
    user_rating INTEGER,
    review_note TEXT DEFAULT '',
    ai_review_draft TEXT DEFAULT '',
    is_favorite INTEGER DEFAULT 0,

    -- 유행도 (기획서 6.6)
    popularity INTEGER DEFAULT 0,
    trend_score REAL DEFAULT 0,
    star_growth_rate REAL DEFAULT 0,
    social_trend REAL DEFAULT 0,
    official_update_freq REAL DEFAULT 0,
    internal_usage REAL DEFAULT 0,
    trend_comment TEXT DEFAULT '',
    trend_badge TEXT DEFAULT '',
    usage_count INTEGER DEFAULT 0,

    ai_status TEXT DEFAULT 'pending',    -- pending | done | failed
    archive_status TEXT DEFAULT 'pending',
    category TEXT DEFAULT '',            -- 분야 (config.CATEGORIES)
    tags TEXT DEFAULT '[]'
);

CREATE INDEX IF NOT EXISTS idx_assets_type ON assets(type);
CREATE INDEX IF NOT EXISTS idx_assets_trend ON assets(trend_score DESC);
CREATE INDEX IF NOT EXISTS idx_assets_ai ON assets(ai_status);

-- star 증가율 계산용 스냅샷
CREATE TABLE IF NOT EXISTS star_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    asset_id INTEGER NOT NULL,
    stars INTEGER NOT NULL,
    recorded_at TEXT NOT NULL,
    FOREIGN KEY (asset_id) REFERENCES assets(id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS idx_star_hist ON star_history(asset_id, recorded_at);

-- 복사/실행 이력 (내부 사용 빈도)
CREATE TABLE IF NOT EXISTS usage_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    asset_id INTEGER NOT NULL,
    variant TEXT NOT NULL DEFAULT 'terminal',
    used_at TEXT NOT NULL,
    FOREIGN KEY (asset_id) REFERENCES assets(id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS idx_usage ON usage_log(asset_id, used_at);

-- X 자동 수집 대체용 수동 링크 큐 (기획서 12장 대안)
CREATE TABLE IF NOT EXISTS link_queue (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    url TEXT NOT NULL,
    note TEXT DEFAULT '',
    status TEXT NOT NULL DEFAULT 'pending',   -- pending | imported | skipped
    created_at TEXT NOT NULL,
    processed_at TEXT DEFAULT ''
);

-- 공개 랜딩 페이지 대기자 명단
CREATE TABLE IF NOT EXISTS waitlist (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    email TEXT NOT NULL UNIQUE,
    created_at TEXT NOT NULL
);

-- 회원 계정. 관리자 여부는 DB 컬럼이 아니라 VAAL_ADMIN_EMAILS 환경변수로 판별한다
-- (가입 순서로 관리자를 정하면 공개 배포 시 레이스 컨디션이 생길 수 있어서 피함).
CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    email TEXT NOT NULL UNIQUE,
    password_hash TEXT NOT NULL,
    display_name TEXT DEFAULT '',
    email_verified INTEGER DEFAULT 0,
    verify_token TEXT DEFAULT '',
    verify_sent_at TEXT DEFAULT '',
    created_at TEXT NOT NULL
);

-- 개인 즐겨찾기 (로그인 사용자 누구나 — 사이트 전체 공용 평점/후기와는 별개)
CREATE TABLE IF NOT EXISTS favorites (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    asset_id INTEGER NOT NULL,
    created_at TEXT NOT NULL,
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
    FOREIGN KEY (asset_id) REFERENCES assets(id) ON DELETE CASCADE,
    UNIQUE(user_id, asset_id)
);
CREATE INDEX IF NOT EXISTS idx_favorites_user ON favorites(user_id);

-- 사용자별 개인 모음집 + 공유 링크
CREATE TABLE IF NOT EXISTS collections (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    name TEXT NOT NULL,
    description TEXT DEFAULT '',
    share_slug TEXT NOT NULL UNIQUE,
    created_at TEXT NOT NULL,
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS idx_collections_user ON collections(user_id);

CREATE TABLE IF NOT EXISTS collection_items (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    collection_id INTEGER NOT NULL,
    asset_id INTEGER NOT NULL,
    added_at TEXT NOT NULL,
    FOREIGN KEY (collection_id) REFERENCES collections(id) ON DELETE CASCADE,
    FOREIGN KEY (asset_id) REFERENCES assets(id) ON DELETE CASCADE,
    UNIQUE(collection_id, asset_id)
);
CREATE INDEX IF NOT EXISTS idx_collection_items ON collection_items(collection_id);

CREATE TABLE IF NOT EXISTS settings (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

-- 파이프라인 실행 기록 (주간 리포트 근거)
CREATE TABLE IF NOT EXISTS runs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    started_at TEXT NOT NULL,
    finished_at TEXT DEFAULT '',
    found INTEGER DEFAULT 0,
    added INTEGER DEFAULT 0,
    archived INTEGER DEFAULT 0,
    ai_done INTEGER DEFAULT 0,
    note TEXT DEFAULT ''
);
"""


def now_iso():
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


def connect():
    con = sqlite3.connect(DB_PATH)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA foreign_keys = ON")
    return con


def _assets_columns():
    """SCHEMA의 assets 정의 블록만 잘라 '컬럼명 → 정의' 로 파싱한다."""
    body = SCHEMA.split("CREATE TABLE IF NOT EXISTS assets (", 1)[1].split("\n);", 1)[0]
    cols = {}
    for line in body.splitlines():
        line = line.split("--")[0].strip().rstrip(",").strip()
        if not line:
            continue
        name = line.split()[0]
        if name.isidentifier() and name != "id":
            cols[name] = line
    return cols


def _migrate_assets(con):
    """기존 DB에 새 컬럼이 추가된 경우 ALTER TABLE 로 따라잡는다."""
    existing = {r[1] for r in con.execute("PRAGMA table_info(assets)")}
    for name, ddl in _assets_columns().items():
        if name not in existing:
            con.execute(f"ALTER TABLE assets ADD COLUMN {ddl}")


def init_db(con=None):
    own = con is None
    con = con or connect()
    con.executescript(SCHEMA)
    _migrate_assets(con)
    for key, value in DEFAULT_SETTINGS.items():
        con.execute("INSERT OR IGNORE INTO settings (key, value) VALUES (?, ?)",
                    (key, str(value)))
    con.commit()
    if own:
        con.close()


# ---------- 설정 ----------

def get_settings(con):
    return {r["key"]: r["value"] for r in con.execute("SELECT key, value FROM settings")}


def get_setting(con, key, default=""):
    row = con.execute("SELECT value FROM settings WHERE key = ?", (key,)).fetchone()
    return row["value"] if row else default


def get_float(con, key, default=0.0):
    try:
        return float(get_setting(con, key, default))
    except (TypeError, ValueError):
        return default


def set_setting(con, key, value):
    con.execute(
        "INSERT INTO settings (key, value) VALUES (?, ?) "
        "ON CONFLICT(key) DO UPDATE SET value = excluded.value", (key, str(value)))


def setting_lines(con, key):
    """줄 단위 설정값을 리스트로 — 빈 줄과 # 주석은 제외."""
    return [ln.strip() for ln in get_setting(con, key).splitlines()
            if ln.strip() and not ln.strip().startswith("#")]


# ---------- 자산 ----------

def upsert_asset(con, item):
    """수집 항목 저장. 이미 있으면 인기도·설명만 갱신하고 평가는 보존한다.

    반환: (asset_id, is_new)
    """
    now = now_iso()
    url = item["source_url"]
    row = con.execute("SELECT id, popularity FROM assets WHERE source_url = ?",
                      (url,)).fetchone()
    stars = int(item.get("popularity") or 0)

    if row:
        con.execute(
            "UPDATE assets SET popularity = MAX(popularity, ?), updated_at = ?, "
            "       source_updated_at = COALESCE(NULLIF(?, ''), source_updated_at), "
            "       description = CASE WHEN ? != '' THEN ? ELSE description END "
            "WHERE id = ?",
            (stars, now, item.get("source_updated_at", ""),
             item.get("description", ""), item.get("description", ""), row["id"]))
        record_stars(con, row["id"], stars)
        return row["id"], False

    cur = con.execute(
        """INSERT INTO assets
           (source, source_url, type, title, target_tool, repo_full_name, asset_path,
            description, license, is_official, popularity, collected_at, updated_at,
            source_updated_at, tags)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (item.get("source", "github"), url, item.get("type", "etc"),
         item["title"][:200], item.get("target_tool", "common"),
         item.get("repo_full_name", ""), item.get("asset_path", ""),
         item.get("description", "")[:1000], item.get("license", ""),
         1 if item.get("is_official") else 0, stars, now, now,
         item.get("source_updated_at", ""),
         json.dumps(item.get("tags", []), ensure_ascii=False)))
    record_stars(con, cur.lastrowid, stars)
    return cur.lastrowid, True


def record_stars(con, asset_id, stars):
    """하루 한 번만 스냅샷을 남긴다 (증가율 계산용)."""
    today = now_iso()[:10]
    dup = con.execute(
        "SELECT 1 FROM star_history WHERE asset_id = ? AND recorded_at LIKE ?",
        (asset_id, f"{today}%")).fetchone()
    if dup:
        con.execute(
            "UPDATE star_history SET stars = MAX(stars, ?) "
            "WHERE asset_id = ? AND recorded_at LIKE ?",
            (stars, asset_id, f"{today}%"))
    else:
        con.execute(
            "INSERT INTO star_history (asset_id, stars, recorded_at) VALUES (?, ?, ?)",
            (asset_id, stars, now_iso()))


def asset_dict(row):
    """sqlite3.Row → JSON 직렬화 가능한 dict (JSON 컬럼 파싱 포함)."""
    d = dict(row)
    for col in ("args_schema", "args_schema_en", "tags"):
        try:
            d[col] = json.loads(d.get(col) or "[]")
        except (TypeError, ValueError):
            d[col] = []
    return d


if __name__ == "__main__":
    init_db()
    print(f"초기화 완료: {DB_PATH}")

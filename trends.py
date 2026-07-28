# -*- coding: utf-8 -*-
"""트렌드 스코어 계산기 (기획서 6.6).

각 신호를 0~1로 정규화한 뒤 설정 가중치로 가중합 → 0~100점.
- star 증가율: star_history 7일 스냅샷 비교
- 소셜: HN 점수 등 외부 반응 (X는 수동 큐라 최근성만 반영)
- 공식 업데이트 빈도: source_updated_at 이 최근일수록 높음
- 내부 사용 빈도: 최근 30일 복사/실행 횟수 + 즐겨찾기
- 최근성: 수집일이 최근일수록 높음
"""
import math
from datetime import datetime, timedelta, timezone

from db import get_float, now_iso

BADGE_HOT = "🔥"      # 급상승
BADGE_NEW = "🆕"      # 신규 (7일 내 수집)
BADGE_STEADY = "⭐"   # 꾸준히 인기


def _parse_dt(text):
    if not text:
        return None
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None


def _days_since(text, default=365.0):
    dt = _parse_dt(text)
    if not dt:
        return default
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return max(0.0, (datetime.now(timezone.utc) - dt).total_seconds() / 86400)


def _norm_log(value, scale):
    """log 스케일 0~1 정규화 — 인기·횟수처럼 롱테일 분포용."""
    return min(1.0, math.log1p(max(0.0, value)) / math.log1p(scale))


def _recency(days, half_life=14.0):
    """지수 감쇠 — half_life일 지나면 0.5."""
    return 0.5 ** (days / half_life)


def star_growth(con, asset_id, window_days=7):
    """최근 window_days 간 star 증가율 (증가분 / max(이전값, 10))."""
    cutoff = (datetime.now(timezone.utc) - timedelta(days=window_days)).isoformat()
    old = con.execute(
        "SELECT stars FROM star_history WHERE asset_id = ? AND recorded_at <= ? "
        "ORDER BY recorded_at DESC LIMIT 1", (asset_id, cutoff)).fetchone()
    if old is None:  # 스냅샷이 창보다 짧으면 가장 오래된 것과 비교
        old = con.execute(
            "SELECT stars FROM star_history WHERE asset_id = ? "
            "ORDER BY recorded_at ASC LIMIT 1", (asset_id,)).fetchone()
    new = con.execute(
        "SELECT stars FROM star_history WHERE asset_id = ? "
        "ORDER BY recorded_at DESC LIMIT 1", (asset_id,)).fetchone()
    if not old or not new or new["stars"] <= old["stars"]:
        return 0.0
    return (new["stars"] - old["stars"]) / max(old["stars"], 10)


def internal_usage(con, asset_id, window_days=30):
    cutoff = (datetime.now(timezone.utc) - timedelta(days=window_days)).isoformat()
    row = con.execute(
        "SELECT COUNT(*) AS n FROM usage_log WHERE asset_id = ? AND used_at >= ?",
        (asset_id, cutoff)).fetchone()
    return row["n"] if row else 0


def recompute(con, log=print):
    """전 자산의 trend_score·배지를 재계산한다."""
    weights = {
        "star": get_float(con, "w_star_growth", 0.30),
        "social": get_float(con, "w_social", 0.10),
        "official": get_float(con, "w_official_update", 0.15),
        "usage": get_float(con, "w_internal_usage", 0.30),
        "recency": get_float(con, "w_recency", 0.15),
    }
    total_w = sum(weights.values()) or 1.0

    rows = con.execute("SELECT * FROM assets").fetchall()
    now = now_iso()
    updated = 0
    for r in rows:
        growth = star_growth(con, r["id"])
        usage_n = internal_usage(con, r["id"])

        s_star = min(1.0, growth * 5)                      # 7일 20% 증가 = 1.0
        s_social = _norm_log(r["popularity"], 3000)
        s_official = _recency(_days_since(r["source_updated_at"]), half_life=21)
        s_usage = min(1.0, _norm_log(usage_n, 20) + (0.15 if r["is_favorite"] else 0))
        s_recency = _recency(_days_since(r["collected_at"]), half_life=14)

        score = 100 * (
            weights["star"] * s_star + weights["social"] * s_social
            + weights["official"] * s_official + weights["usage"] * s_usage
            + weights["recency"] * s_recency) / total_w

        days_old = _days_since(r["collected_at"])
        if s_star >= 0.5 or (usage_n >= 5 and days_old <= 30):
            badge = BADGE_HOT
        elif days_old <= 7:
            badge = BADGE_NEW
        elif s_social >= 0.55 and (r["usage_count"] or 0) > 0:
            badge = BADGE_STEADY
        elif s_social >= 0.8:
            badge = BADGE_STEADY
        else:
            badge = ""

        con.execute(
            """UPDATE assets SET trend_score = ?, star_growth_rate = ?,
                 social_trend = ?, official_update_freq = ?, internal_usage = ?,
                 trend_badge = ?, updated_at = ? WHERE id = ?""",
            (round(score, 1), round(growth, 4), round(s_social, 4),
             round(s_official, 4), round(s_usage, 4), badge, now, r["id"]))
        updated += 1
    con.commit()
    log(f"  트렌드 재계산 {updated}건 (가중치 {weights})")
    return updated

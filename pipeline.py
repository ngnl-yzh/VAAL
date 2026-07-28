# -*- coding: utf-8 -*-
"""파이프라인 — 수집 → 아카이브 → AI → 트렌드 → 인덱스/리포트 (기획서 9장).

사용법:
  python pipeline.py                 # 전체 실행
  python pipeline.py --no-ai         # AI 단계 생략 (규칙 기반 템플릿만)
  python pipeline.py --steps collect,archive
  python pipeline.py --ai-limit 60   # AI 처리 자산 수 상한
"""
import argparse
import os
import sys

import ai_layer
import archiver
import collectors
import trends
from config import ARCHIVE_DIR, CLAUDE_CMD
from db import (connect, init_db, now_iso, upsert_asset, get_setting,
                setting_lines)

sys.stdout.reconfigure(encoding="utf-8", errors="replace")


def step_collect(con, log=print):
    """모든 소스에서 수집해 DB에 저장한다. 반환: (발견, 신규)"""
    min_stars = int(get_setting(con, "min_stars", "0") or 0)
    found = []

    log("[1/5] 수집")
    log(" - GitHub 검색")
    found += collectors.collect_github_search(
        setting_lines(con, "github_queries"), min_stars=min_stars, log=log)
    log(" - Awesome 리스트")
    found += collectors.collect_awesome_lists(
        setting_lines(con, "awesome_lists"), log=log)
    log(" - 공식 저장소")
    found += collectors.collect_official(
        setting_lines(con, "official_repos"), log=log)
    found += collectors.collect_official_docs(log=log)
    log(" - 코드 검색")
    found += collectors.collect_code_search(log=log)
    log(" - HackerNews")
    found += collectors.collect_hackernews(log=log)
    log(" - 수동 링크 큐")
    queued, queue_ids = collectors.collect_link_queue(con, log=log)
    found += queued

    added = 0
    for item in found:
        item.pop("_subdir", None)
        _, is_new = upsert_asset(con, item)
        added += 1 if is_new else 0
    for qid in queue_ids:
        con.execute(
            "UPDATE link_queue SET status = 'imported', processed_at = ? WHERE id = ?",
            (now_iso(), qid))
    con.commit()
    log(f" → 발견 {len(found)}건, 신규 {added}건")
    return len(found), added


def step_archive(con, limit=None, log=print):
    """원본 미확보 자산을 내려받는다. 반환: 아카이브 수"""
    log("[2/5] 원본 아카이브")
    sql = ("SELECT * FROM assets WHERE archive_status IN ('pending', 'empty') "
           "AND repo_full_name != '' ORDER BY popularity DESC")
    rows = con.execute(sql + (f" LIMIT {int(limit)}" if limit else "")).fetchall()
    archived = 0
    for i, r in enumerate(rows, 1):
        result = archiver.archive_asset(con, r)
        archived += 1 if result == "archived" else 0
        if i % 20 == 0:
            con.commit()
            log(f"  {i}/{len(rows)} 처리")
    con.commit()
    log(f" → {archived}건 저장 (대상 {len(rows)}건)")
    return archived


def step_ai(con, limit=40, log=print):
    """AI 요약·평가초안. claude CLI 없으면 규칙 기반 폴백. 반환: 처리 수"""
    log("[3/5] AI 요약·평가초안")
    if not os.path.exists(CLAUDE_CMD):
        log(f"  [폴백] claude CLI 없음({CLAUDE_CMD}) — 규칙 기반 템플릿만 생성")
        n = ai_layer.build_templates_only(con, log=log)
        ai_layer.backfill_categories(con, log=log)
        return n
    done, failed = ai_layer.enrich_assets(con, limit=limit, log=log)
    # AI가 놓친 자산도 템플릿·분야는 반드시 채운다
    ai_layer.build_templates_only(con, log=log)
    ai_layer.backfill_categories(con, log=log)
    return done


def step_trends(con, with_comments=True, log=print):
    log("[4/5] 트렌드 스코어")
    trends.recompute(con, log=log)
    if with_comments and os.path.exists(CLAUDE_CMD):
        ai_layer.write_trend_comments(con, log=log)


def step_index(con, log=print):
    """meta.md 전체 갱신 + _index.md + 주간 리포트."""
    log("[5/5] meta.md / 인덱스 / 리포트")
    rows = con.execute(
        "SELECT * FROM assets WHERE archive_status = 'archived'").fetchall()
    for r in rows:
        archiver.write_meta(con, r)
    con.commit()
    archiver.write_index(con)
    write_weekly_report(con, log=log)
    log(f" → meta {len(rows)}건, 인덱스 갱신")


def write_weekly_report(con, log=print):
    """주간 리포트 (기획서 6.8): 신규 수집, 실행 Top 5, 급상승."""
    date = now_iso()[:10]
    new_rows = con.execute(
        "SELECT * FROM assets WHERE collected_at >= datetime('now', '-7 days') "
        "ORDER BY popularity DESC").fetchall()
    top_used = con.execute(
        """SELECT a.title, a.type, COUNT(u.id) AS n FROM usage_log u
           JOIN assets a ON a.id = u.asset_id
           WHERE u.used_at >= datetime('now', '-7 days')
           GROUP BY u.asset_id ORDER BY n DESC LIMIT 5""").fetchall()
    rising = con.execute(
        "SELECT * FROM assets WHERE trend_badge = ? "
        "ORDER BY trend_score DESC LIMIT 10", (trends.BADGE_HOT,)).fetchall()
    by_source = con.execute(
        "SELECT source, COUNT(*) AS n FROM assets GROUP BY source "
        "ORDER BY n DESC").fetchall()

    lines = [f"# VAAL 주간 리포트 — {date}", ""]
    lines += [f"## 신규 수집 {len(new_rows)}건 (최근 7일)", ""]
    for r in new_rows[:20]:
        lines.append(f"- [{r['title']}]({r['source_url']}) — {r['type']}, "
                     f"인기 {r['popularity']}")
    if len(new_rows) > 20:
        lines.append(f"- … 외 {len(new_rows) - 20}건")
    lines += ["", "## 소스별 누적", ""]
    for r in by_source:
        lines.append(f"- {r['source']}: {r['n']}건")
    lines += ["", "## 이번 주 실행 Top 5", ""]
    lines += ([f"- {r['title']} ({r['type']}) — {r['n']}회" for r in top_used]
              or ["- (실행 이력 없음)"])
    lines += ["", "## 급상승 자산", ""]
    lines += ([f"- 🔥 {r['title']} — 트렌드 {r['trend_score']:.0f}점" for r in rising]
              or ["- (해당 없음)"])

    folder = os.path.join(ARCHIVE_DIR, "_weekly-report")
    os.makedirs(folder, exist_ok=True)
    path = os.path.join(folder, f"{date}.md")
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
    log(f"  리포트: {path}")
    return path


ALL_STEPS = ["collect", "archive", "ai", "trends", "index"]


def run(steps=None, ai_limit=40, use_ai=True, log=print):
    steps = steps or ALL_STEPS
    init_db()
    con = connect()
    started = now_iso()
    stats = {"found": 0, "added": 0, "archived": 0, "ai_done": 0}
    try:
        if "collect" in steps:
            stats["found"], stats["added"] = step_collect(con, log=log)
        if "archive" in steps:
            stats["archived"] = step_archive(con, log=log)
        if "ai" in steps:
            if use_ai:
                stats["ai_done"] = step_ai(con, limit=ai_limit, log=log)
            else:
                ai_layer.build_templates_only(con, log=log)
                ai_layer.backfill_categories(con, log=log)
        if "trends" in steps:
            step_trends(con, with_comments=use_ai, log=log)
        if "index" in steps:
            step_index(con, log=log)
        con.execute(
            "INSERT INTO runs (started_at, finished_at, found, added, archived, "
            "ai_done, note) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (started, now_iso(), stats["found"], stats["added"],
             stats["archived"], stats["ai_done"], ",".join(steps)))
        con.commit()
    finally:
        con.close()
    log(f"완료: {stats}")
    return stats


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="VAAL 파이프라인")
    ap.add_argument("--steps", default=",".join(ALL_STEPS))
    ap.add_argument("--no-ai", action="store_true")
    ap.add_argument("--ai-limit", type=int, default=40)
    args = ap.parse_args()
    run(steps=[s.strip() for s in args.steps.split(",") if s.strip()],
        ai_limit=args.ai_limit, use_ai=not args.no_ai)

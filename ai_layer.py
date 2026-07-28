# -*- coding: utf-8 -*-
"""AI 요약·평가초안·인자보정 레이어 (기획서 6.4, 6.5, 6.10).

API 키 과금 대신 로컬 claude CLI(`claude -p`)를 서브프로세스로 호출한다.
ClaudeRadar weekly_update.py에서 검증된 패턴을 확장한 것.
"""
import json
import re
import subprocess

import archiver
import categorize
import templater
from config import CATEGORIES, CLAUDE_CMD
from db import now_iso

BATCH_SIZE = 4          # 한 번의 claude -p 호출로 처리할 자산 수
ORIGINAL_CHARS = 3200   # 배치에 넣을 자산당 원문 길이
TIMEOUT = 300

PROMPT = """당신은 바이브 코딩 자산(Claude Code 스킬/커맨드/플러그인, Cursor 룰)을 \
한국 개발자에게 소개하는 큐레이터입니다.
아래 자산들의 원문을 각각 분석해서 JSON으로 정리해주세요.

모든 설명(purpose/usage/review와 args의 description)은 반드시 **한국어**로 쓰세요. \
원문이 영어라도 요약은 한국어로 합니다. 스킬 이름, 명령어, 파일명, API 같은 \
기술 용어는 영어 그대로 둬도 됩니다.

각 항목마다:
- purpose: 용도 요약 (한국어 1~2문장, 무엇을 해결하는 자산인지)
- usage: 사용법 요약 (한국어 2~4문장 — 설치/적용 방법과 실제 쓰는 흐름)
- review: 평가 초안 (한국어 2~3문장 — 장점, 주의할 점, 품질 추정. 솔직하게)
- args: 실행 인자 배열 [{{"name": "...", "required": true/false, "description": "..."}}] \
— 인자가 없으면 빈 배열, description은 한국어
- category: 아래 목록 중 정확히 하나
{categories}

반드시 아래 형식의 JSON 배열만 출력하세요. 다른 텍스트는 절대 쓰지 마세요:
[{{"id": 1, "purpose": "...", "usage": "...", "review": "...", "args": [], "category": "..."}}]

자산 목록:
{items}"""


def run_claude(prompt, timeout=TIMEOUT, log=None):
    """claude -p 실행 (프롬프트는 stdin — 윈도우 명령줄 8191자 한계 회피).

    실패 시 None. 인증 만료 등 CLI 오류는 log로 알린다."""
    try:
        proc = subprocess.run(
            [CLAUDE_CMD, "-p"], input=prompt,
            capture_output=True, text=True, encoding="utf-8", errors="replace",
            timeout=timeout, shell=False)
    except (OSError, subprocess.TimeoutExpired):
        return None
    if proc.returncode != 0:
        if log:
            msg = (proc.stdout or proc.stderr or "").strip()[:150]
            log(f"    [claude CLI 오류] {msg or '알 수 없는 실패'}")
        return None
    return proc.stdout.strip()


def parse_json_array(text):
    """출력에서 JSON 배열만 추출한다 (코드펜스·잡담 방어)."""
    if not text:
        return None
    m = re.search(r"\[.*\]", text, re.S)
    if not m:
        return None
    try:
        data = json.loads(m.group(0))
    except ValueError:
        return None
    return data if isinstance(data, list) else None


def _batch_prompt(batch):
    """자산 배치 → 프롬프트 본문."""
    chunks = []
    for i, (asset, original) in enumerate(batch, 1):
        chunks.append(
            f"[{i}] id={asset['id']} | 이름: {asset['title']} "
            f"| 타입: {asset['type']} | 대상: {asset['target_tool']}\n"
            f"출처 설명: {asset['description'] or '(없음)'}\n"
            f"원문:\n{original or '(원문 확보 실패 — 이름과 설명만으로 추정)'}\n")
    return PROMPT.format(items="\n---\n".join(chunks),
                         categories=" / ".join(CATEGORIES))


def enrich_assets(con, limit=40, log=print):
    """ai_status='pending' 자산에 요약·평가초안·인자 보정을 채운다.

    반환: (성공 수, 실패 수)
    """
    rows = con.execute(
        "SELECT * FROM assets WHERE ai_status IN ('pending', 'failed') "
        "ORDER BY CASE ai_status WHEN 'pending' THEN 0 ELSE 1 END, "
        "         popularity DESC, id LIMIT ?", (limit,)).fetchall()
    if not rows:
        log("  AI 처리 대기 자산 없음")
        return 0, 0

    done = failed = 0
    for start in range(0, len(rows), BATCH_SIZE):
        batch_rows = rows[start:start + BATCH_SIZE]
        batch = [(r, archiver.read_original(r, ORIGINAL_CHARS)) for r in batch_rows]
        log(f"  배치 {start // BATCH_SIZE + 1}: {len(batch)}건 → claude -p 호출")
        out = run_claude(_batch_prompt(batch), log=log)
        results = parse_json_array(out)
        if not results:
            log("    [실패] 응답 파싱 불가")
            for r in batch_rows:
                con.execute("UPDATE assets SET ai_status = 'failed' WHERE id = ?",
                            (r["id"],))
            failed += len(batch_rows)
            con.commit()
            continue

        by_id = {}
        for item in results:
            if isinstance(item, dict) and isinstance(item.get("id"), int):
                by_id[item["id"]] = item

        for r, original in batch:
            item = by_id.get(r["id"])
            if not item:
                con.execute("UPDATE assets SET ai_status = 'failed' WHERE id = ?",
                            (r["id"],))
                failed += 1
                continue
            # 규칙 기반 템플릿에 AI 인자 보정 적용
            tmpl = templater.build(r, original)
            tmpl = templater.apply_ai_args(tmpl, {
                "args": item.get("args"),
            })
            category = (categorize.valid(str(item.get("category", "")).strip())
                        or categorize.categorize(r["title"], r["description"]))
            con.execute(
                """UPDATE assets SET
                     purpose_summary = ?, usage_summary = ?, ai_review_draft = ?,
                     args_schema = ?, terminal_template = ?, claude_code_template = ?,
                     cursor_apply_guide = ?, install_command = ?, category = ?,
                     ai_status = 'done', updated_at = ?
                   WHERE id = ?""",
                (str(item.get("purpose", ""))[:600],
                 str(item.get("usage", ""))[:900],
                 str(item.get("review", ""))[:600],
                 templater.to_json(tmpl["args_schema"]),
                 tmpl["terminal_template"], tmpl["claude_code_template"],
                 tmpl["cursor_apply_guide"], tmpl["install_command"], category,
                 now_iso(), r["id"]))
            done += 1
        con.commit()
        log(f"    완료 {done} / 실패 {failed}")
    return done, failed


def backfill_categories(con, log=print):
    """분야가 비어 있는 자산을 규칙 기반으로 분류한다 (AI가 오면 덮어씀)."""
    rows = con.execute(
        "SELECT id, title, description, tags FROM assets "
        "WHERE category = ''").fetchall()
    for r in rows:
        try:
            tags = json.loads(r["tags"] or "[]")
        except ValueError:
            tags = []
        con.execute("UPDATE assets SET category = ? WHERE id = ?",
                    (categorize.categorize(r["title"], r["description"], tags),
                     r["id"]))
    con.commit()
    if rows:
        log(f"  규칙 기반 분야 분류 {len(rows)}건")
    return len(rows)


def build_templates_only(con, log=print):
    """AI 없이 규칙 기반 템플릿만이라도 채운다 (claude CLI 부재 시 폴백)."""
    rows = con.execute(
        "SELECT * FROM assets WHERE claude_code_template = '' "
        "AND cursor_apply_guide = ''").fetchall()
    count = 0
    for r in rows:
        original = archiver.read_original(r, 3000)
        tmpl = templater.build(r, original)
        con.execute(
            """UPDATE assets SET args_schema = ?, terminal_template = ?,
                 claude_code_template = ?, cursor_apply_guide = ?,
                 install_command = ?, updated_at = ? WHERE id = ?""",
            (templater.to_json(tmpl["args_schema"]), tmpl["terminal_template"],
             tmpl["claude_code_template"], tmpl["cursor_apply_guide"],
             tmpl["install_command"], now_iso(), r["id"]))
        count += 1
    con.commit()
    log(f"  규칙 기반 템플릿 {count}건 생성")
    return count


TREND_COMMENT_PROMPT = """아래는 개인 아카이브에서 유행도 상위에 오른 바이브 코딩 자산들입니다.
각 자산이 "왜 지금 주목받는지"를 근거 수치를 언급하며 한국어 한 문장으로 써주세요.

반드시 JSON 배열만 출력: [{{"id": 1, "comment": "..."}}]

자산 목록:
{items}"""


def write_trend_comments(con, top_n=10, log=print):
    """트렌드 상위 자산에 '왜 뜨는지' 한 줄 코멘트 (기획서 6.6, 6.10)."""
    rows = con.execute(
        "SELECT id, title, type, popularity, star_growth_rate, usage_count, "
        "       trend_score FROM assets "
        "WHERE trend_score > 0 ORDER BY trend_score DESC LIMIT ?", (top_n,)).fetchall()
    if not rows:
        return 0
    items = "\n".join(
        f"[id={r['id']}] {r['title']} ({r['type']}) — 트렌드 {r['trend_score']:.0f}점, "
        f"외부 인기 {r['popularity']}, star 증가율 {r['star_growth_rate']:.2f}, "
        f"내 사용 {r['usage_count']}회" for r in rows)
    out = run_claude(TREND_COMMENT_PROMPT.format(items=items), timeout=180)
    results = parse_json_array(out) or []
    count = 0
    for item in results:
        if isinstance(item, dict) and item.get("id") and item.get("comment"):
            con.execute("UPDATE assets SET trend_comment = ? WHERE id = ?",
                        (str(item["comment"])[:300], int(item["id"])))
            count += 1
    con.commit()
    log(f"  트렌드 코멘트 {count}건")
    return count

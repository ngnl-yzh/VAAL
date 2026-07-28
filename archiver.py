# -*- coding: utf-8 -*-
"""원본 아카이버 + meta.md 생성기 (기획서 6.3, 6.4).

ClaudeRadar는 링크만 저장했지만 VAAL은 원본 파일을 실제로 내려받는다.
출처가 사라져도 자산이 남고, AI 요약·템플릿 추출이 원문을 근거로 동작한다.
"""
import hashlib
import json
import os
import re

import gh
from config import (ARCHIVE_DIR, PERMISSIVE_LICENSES, TYPE_DIRS, TYPE_LABELS,
                    SOURCE_LABELS)
from db import now_iso

# 스킬 폴더에서 함께 받아둘 보조 파일 (있을 때만)
COMPANION_FILES = ["README.md", "reference.md", "references.md", "USAGE.md"]
MAX_FILE_BYTES = 400_000

_SAFE_RE = re.compile(r'[<>:"/\\|?*\x00-\x1f]')


def safe_name(name, fallback="asset"):
    """윈도우 파일명으로 안전한 문자열."""
    name = _SAFE_RE.sub("-", (name or "").strip())
    name = re.sub(r"\s+", " ", name).strip(" .-")
    return (name or fallback)[:60]


def asset_dir_name(asset):
    date = (asset["collected_at"] or now_iso())[:10]
    return f"{date}_{safe_name(asset['title'])}"


def rel_dir(asset):
    return os.path.join(TYPE_DIRS.get(asset["type"], "etc"), asset_dir_name(asset))


def fetch_sources(asset):
    """자산의 원본 파일들을 (파일명, 내용) 목록으로 가져온다."""
    asset = dict(asset)  # sqlite3.Row 대응
    repo = asset["repo_full_name"]
    path = asset["asset_path"] or ""
    files = []

    if repo and path:
        is_file = "." in path.rsplit("/", 1)[-1]
        if is_file:
            text, _ = gh.raw_file(repo, path)
            if text:
                files.append((os.path.basename(path), text[:MAX_FILE_BYTES]))
            subdir = path.rsplit("/", 1)[0] if "/" in path else ""
        else:
            # awesome 리스트가 주는 폴더 경로(skills/docx 등) — 대표 파일을 찾는다
            subdir = path.rstrip("/")
            for name in ("SKILL.md", "README.md", ".cursorrules", "plugin.json"):
                text, _ = gh.raw_file(repo, f"{subdir}/{name}")
                if text:
                    files.append((name, text[:MAX_FILE_BYTES]))
                    break
        if subdir and asset["type"] in ("skill", "plugin"):
            have = {n.lower() for n, _ in files} | {os.path.basename(path).lower()}
            for name in COMPANION_FILES:
                if name.lower() in have:
                    continue
                text, _ = gh.raw_file(repo, f"{subdir}/{name}")
                if text:
                    files.append((name, text[:MAX_FILE_BYTES]))
    elif repo:
        text, _ = gh.repo_readme(repo, asset.get("asset_path") or "")
        if text:
            files.append(("README.md", text[:MAX_FILE_BYTES]))
    else:
        # GitHub 밖 링크(HN·X 등)는 원문 확보가 어려워 링크만 남긴다
        text = gh.get_text(asset["source_url"])
        if text and "<html" not in text[:200].lower():
            files.append(("source.txt", text[:MAX_FILE_BYTES]))

    return files


def content_hash(files):
    h = hashlib.sha256()
    for name, text in sorted(files):
        h.update(name.encode("utf-8"))
        h.update(text.encode("utf-8", "replace"))
    return h.hexdigest()[:16]


def archive_asset(con, asset, force=False):
    """원본을 내려받아 저장하고 DB를 갱신한다.

    반환: "archived" | "unchanged" | "empty"
    """
    files = fetch_sources(asset)
    if not files:
        con.execute(
            "UPDATE assets SET archive_status = 'empty', updated_at = ? WHERE id = ?",
            (now_iso(), asset["id"]))
        return "empty"

    digest = content_hash(files)
    if not force and digest == (asset["content_hash"] or "") and asset["archive_dir"]:
        return "unchanged"

    relative = rel_dir(asset)
    target = os.path.join(ARCHIVE_DIR, relative, "original")
    os.makedirs(target, exist_ok=True)
    for name, text in files:
        with open(os.path.join(target, safe_name(name, "file.txt")), "w",
                  encoding="utf-8") as f:
            f.write(text)

    main_file = os.path.join(relative, "original", safe_name(files[0][0], "file.txt"))
    con.execute(
        "UPDATE assets SET archive_dir = ?, raw_file_path = ?, content_hash = ?, "
        "       archive_status = 'archived', updated_at = ? WHERE id = ?",
        (relative, main_file, digest, now_iso(), asset["id"]))
    return "archived"


def license_allows_preview(license_str):
    """18장 — 라이선스가 허용 목록(SPDX)에 있을 때만 원문 미리보기를 노출한다."""
    return (license_str or "").strip() in PERMISSIVE_LICENSES


def read_original(asset, limit=6000):
    """AI 요약·템플릿 추출용 원문. 아카이브에 있으면 로컬에서 읽는다."""
    if asset["archive_dir"]:
        folder = os.path.join(ARCHIVE_DIR, asset["archive_dir"], "original")
        if os.path.isdir(folder):
            chunks = []
            for name in sorted(os.listdir(folder)):
                try:
                    with open(os.path.join(folder, name), encoding="utf-8") as f:
                        chunks.append(f"### {name}\n{f.read()}")
                except OSError:
                    continue
            if chunks:
                return "\n\n".join(chunks)[:limit]
    files = fetch_sources(asset)
    return "\n\n".join(f"### {n}\n{t}" for n, t in files)[:limit]


# ---------- meta.md ----------

def _fence(text, lang=""):
    return f"```{lang}\n{text}\n```" if text else "_(없음)_"


def render_meta(asset):
    """기획서 6.4 항목을 모두 담은 meta.md 본문."""
    asset = dict(asset)  # sqlite3.Row도 그대로 받을 수 있게
    args = asset.get("args_schema") or []
    if isinstance(args, str):
        try:
            args = json.loads(args)
        except ValueError:
            args = []

    rating = asset.get("user_rating")
    stars_txt = ("★" * rating + "☆" * (5 - rating)) if rating else "_(미평가)_"

    lines = [
        f"# {asset['title']}",
        "",
        "## 기본 정보",
        "",
        "| 항목 | 값 |",
        "|---|---|",
        f"| 타입 | {TYPE_LABELS.get(asset['type'], asset['type'])} |",
        f"| 분야 | {asset.get('category') or '미분류'} |",
        f"| 대상 도구 | {asset['target_tool']} |",
        f"| 출처 | {SOURCE_LABELS.get(asset['source'], asset['source'])} |",
        f"| 출처 URL | {asset['source_url']} |",
        f"| 저장소 | {asset['repo_full_name'] or '-'} |",
        f"| 저장소 내 경로 | {asset['asset_path'] or '-'} |",
        f"| 공식 여부 | {'공식' if asset['is_official'] else '비공식'} |",
        f"| 라이선스 | {asset['license'] or '미상 (원본 저장소 확인 필요)'} |",
        f"| 수집일 | {asset['collected_at'][:10]} |",
        f"| 최근 갱신 | {(asset['updated_at'] or '')[:10]} |",
        "",
        "## 용도 요약",
        "",
        asset["purpose_summary"] or "_(AI 요약 대기 중)_",
        "",
        "## 사용법 요약",
        "",
        asset["usage_summary"] or "_(AI 요약 대기 중)_",
        "",
        "## 실행 템플릿",
        "",
        "### 터미널",
        _fence(asset["terminal_template"], "bash"),
        "",
        "### Claude Code",
        _fence(asset["claude_code_template"]),
        "",
    ]

    if asset["install_command"]:
        lines += ["### 설치", _fence(asset["install_command"], "bash"), ""]
    if asset["cursor_apply_guide"]:
        lines += ["### Cursor 적용", "", asset["cursor_apply_guide"], ""]

    if args:
        lines += ["## 인자", "", "| 이름 | 필수 | 설명 |", "|---|---|---|"]
        for a in args:
            lines.append(
                f"| {a.get('name', '')} | {'필수' if a.get('required') else '선택'} "
                f"| {a.get('description', '')} |")
        lines.append("")

    lines += [
        "## 평가",
        "",
        f"- 내 평점: {stars_txt}",
        f"- 후기: {asset['review_note'] or '_(미작성)_'}",
        "",
        "### AI 평가 초안",
        "",
        asset["ai_review_draft"] or "_(대기 중)_",
        "",
        "## 유행도",
        "",
        "| 지표 | 값 |",
        "|---|---|",
        f"| 트렌드 스코어 | {asset['trend_score']:.1f} |",
        f"| 배지 | {asset['trend_badge'] or '-'} |",
        f"| 외부 인기(star/점수) | {asset['popularity']} |",
        f"| star 증가율 | {asset['star_growth_rate']:.3f} |",
        f"| 공식 업데이트 빈도 | {asset['official_update_freq']:.3f} |",
        f"| 내부 사용 빈도 | {asset['internal_usage']:.3f} |",
        f"| 복사·실행 횟수 | {asset['usage_count']} |",
        "",
        asset["trend_comment"] or "",
        "",
        "## 주의사항",
        "",
        "- 원본 라이선스를 확인하고 사용하세요. 이 아카이브는 개인 보관용 사본입니다.",
        "- 실행 템플릿은 자동 생성된 초안이므로 처음 실행 전 내용을 검토하세요.",
        "",
        "---",
        f"_VAAL 자동 생성 · {now_iso()}_",
    ]
    return "\n".join(lines)


def write_meta(con, asset):
    """meta.md 파일 기록 후 경로를 DB에 저장한다."""
    relative = asset["archive_dir"] or rel_dir(asset)
    folder = os.path.join(ARCHIVE_DIR, relative)
    os.makedirs(folder, exist_ok=True)
    path = os.path.join(folder, "meta.md")
    with open(path, "w", encoding="utf-8") as f:
        f.write(render_meta(asset))
    con.execute(
        "UPDATE assets SET meta_file_path = ?, archive_dir = ?, updated_at = ? "
        "WHERE id = ?",
        (os.path.join(relative, "meta.md"), relative, now_iso(), asset["id"]))
    return path


def write_index(con):
    """_index.md — 전체 자산 인덱스 (기획서 6.3, 6.8)."""
    rows = con.execute(
        "SELECT * FROM assets ORDER BY trend_score DESC, popularity DESC").fetchall()
    lines = [
        "# VAAL 아카이브 인덱스", "",
        f"- 총 자산: **{len(rows)}건**",
        f"- 생성: {now_iso()}", "",
        "| 트렌드 | 평점 | 타입 | 이름 | 대상 | 용도 | 출처 |",
        "|---|---|---|---|---|---|---|",
    ]
    for r in rows:
        rating = f"★{r['user_rating']}" if r["user_rating"] else "-"
        purpose = (r["purpose_summary"] or r["description"] or "").replace("|", "／")
        badge = r["trend_badge"] or ""
        meta = r["meta_file_path"]
        name = f"[{r['title']}]({meta.replace(os.sep, '/')})" if meta else r["title"]
        lines.append(
            f"| {r['trend_score']:.0f}{badge} | {rating} "
            f"| {TYPE_LABELS.get(r['type'], r['type'])} | {name} | {r['target_tool']} "
            f"| {purpose[:60]} | [링크]({r['source_url']}) |")
    os.makedirs(ARCHIVE_DIR, exist_ok=True)
    path = os.path.join(ARCHIVE_DIR, "_index.md")
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
    return path

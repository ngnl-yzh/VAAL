# -*- coding: utf-8 -*-
"""소스별 수집기 (기획서 6.1) — GitHub, awesome 리스트, 공식 채널, 수동 링크 큐.

ClaudeRadar와의 결정적 차이: 저장소를 통째로 한 항목으로 담지 않고,
저장소 안의 개별 자산(스킬 폴더, 커맨드 .md, 룰 파일)까지 펼쳐서 수집한다.
런처가 실행 명령을 만들려면 '레포'가 아니라 '자산 하나'가 필요하기 때문이다.
"""
import re

import requests

import gh
from config import GITHUB_TOKEN, USER_AGENT

# 저장소 하나에서 펼칠 자산 수 상한 (거대 모음 레포 폭주 방지)
MAX_EXPAND_PER_REPO = 40

CLAUDE_HINTS = ("claude", "anthropic")
CURSOR_HINTS = ("cursor", "cursorrules")


# ---------- 분류 ----------

def classify_path(path):
    """저장소 내 파일 경로 → (type, target_tool, 자산이름) 또는 None."""
    p = path.replace("\\", "/")
    low = p.lower()
    parts = p.split("/")

    if parts[-1].upper() == "SKILL.MD" and len(parts) >= 2:
        return "skill", "claude-code", parts[-2]
    if parts[-1] in (".cursorrules",) or low.endswith("/.cursorrules"):
        name = parts[-2] if len(parts) >= 2 else "cursorrules"
        return "rule", "cursor", name
    if ".cursor/rules/" in low and low.endswith((".mdc", ".md")):
        return "rule", "cursor", parts[-1].rsplit(".", 1)[0]
    if parts[-1] in ("plugin.json",) and len(parts) >= 2:
        return "plugin", "claude-code", parts[-2]
    if low.endswith(".md") and (
            ".claude/commands/" in low or low.startswith("commands/")
            or "/commands/" in low):
        return "command", "claude-code", parts[-1].rsplit(".", 1)[0]
    return None


def classify_text(title, description, topics=()):
    """경로 정보가 없을 때 제목·설명·토픽으로 타입과 대상 도구를 추정한다."""
    text = f"{title} {description} {' '.join(topics)}".lower()
    if "cursorrules" in text or ".cursor" in text or "cursor rules" in text:
        return "rule", "cursor"
    if "plugin" in text or "marketplace" in text:
        return "plugin", "claude-code"
    if "skill" in text:
        return "skill", "claude-code"
    if "command" in text or "slash" in text:
        return "command", "claude-code"
    target = "cursor" if "cursor" in text else (
        "claude-code" if any(h in text for h in CLAUDE_HINTS) else "common")
    return "etc", target


def is_relevant(*chunks):
    """클로드/커서와 무관한 항목이 느슨한 검색으로 섞이는 것을 막는다."""
    text = " ".join(c or "" for c in chunks).lower()
    return any(h in text for h in CLAUDE_HINTS + CURSOR_HINTS)


# ---------- 저장소 → 개별 자산 펼치기 ----------

def expand_repo(repo, info=None, source="github", is_official=False):
    """저장소 파일 트리를 훑어 개별 자산 목록을 만든다.

    자산이 하나도 안 잡히면 저장소 자체를 한 항목으로 반환한다.
    """
    info = info or gh.repo_info(repo)
    if not info:
        return []

    base = {
        "source": source,
        "repo_full_name": repo,
        "license": info["license"],
        "is_official": is_official,
        "popularity": info["stars"],
        "source_updated_at": info["pushed_at"],
        "tags": info["topics"][:8],
    }
    branch = info["default_branch"]
    tree = gh.list_tree(repo, branch)

    items, seen = [], set()
    for path in tree:
        hit = classify_path(path)
        if not hit:
            continue
        atype, target, name = hit
        key = (atype, name)
        if key in seen:
            continue
        seen.add(key)
        subdir = path.rsplit("/", 1)[0] if "/" in path else ""
        items.append({
            **base,
            "source_url": f"https://github.com/{repo}/blob/{branch}/{path}",
            "type": atype,
            "target_tool": target,
            "title": name,
            "asset_path": path,
            "description": info["description"][:300],
            "_subdir": subdir,
        })
        if len(items) >= MAX_EXPAND_PER_REPO:
            break

    if items:
        return items

    atype, target = classify_text(repo, info["description"], info["topics"])
    return [{
        **base,
        "source_url": info["html_url"],
        "type": atype,
        "target_tool": target,
        "title": repo,
        "asset_path": "",
        "description": info["description"][:300],
        "_subdir": "",
    }]


# ---------- 1. GitHub 저장소 검색 ----------

def collect_github_search(queries, min_stars=0, per_query=12, expand=True,
                          log=print):
    """키워드로 저장소를 찾고, 관련 있는 것만 개별 자산으로 펼친다."""
    found, seen_repos = [], set()
    for q in queries:
        data = gh.get("/search/repositories", params={
            "q": f"{q} stars:>={min_stars}" if min_stars else q,
            "sort": "stars", "order": "desc", "per_page": per_query})
        if not isinstance(data, dict):
            log(f"  [건너뜀] 검색 실패: {q}")
            continue
        repos = data.get("items", [])
        log(f"  '{q}' → {len(repos)}건")
        for repo in repos:
            full = repo.get("full_name", "")
            desc = repo.get("description") or ""
            topics = repo.get("topics") or []
            if not full or full in seen_repos:
                continue
            if not is_relevant(full, desc, " ".join(topics)):
                continue
            seen_repos.add(full)
            if not expand:
                atype, target = classify_text(full, desc, topics)
                found.append({
                    "source": "github", "source_url": repo["html_url"],
                    "type": atype, "target_tool": target, "title": full,
                    "repo_full_name": full, "description": desc[:300],
                    "popularity": repo.get("stargazers_count", 0),
                    "source_updated_at": repo.get("pushed_at") or "",
                    "license": ((repo.get("license") or {}).get("spdx_id") or ""),
                    "tags": topics[:8], "asset_path": "", "_subdir": "",
                })
                continue
            info = {
                "full_name": full,
                "description": desc,
                "stars": repo.get("stargazers_count", 0),
                "license": ((repo.get("license") or {}).get("spdx_id") or ""),
                "pushed_at": repo.get("pushed_at") or "",
                "topics": topics,
                "default_branch": repo.get("default_branch") or "main",
                "html_url": repo["html_url"],
            }
            found.extend(expand_repo(full, info))
    return found


# ---------- 2. awesome 리스트 파싱 ----------

LINK_RE = re.compile(
    r"\[([^\]\n]{2,80})\]\((https://github\.com/[\w.-]+/[\w.-]+[^\s)]*)\)"
    r"\s*[-–—:|]*\s*([^\n|]{0,300})")


def collect_awesome_lists(repos, log=print):
    """선별된 awesome 리스트 README에서 링크를 추출한다 (저장소 펼치기는 안 함)."""
    found = []
    for repo in repos:
        readme, _ = gh.repo_readme(repo)
        if not readme:
            log(f"  [건너뜀] README 없음: {repo}")
            continue
        rows = LINK_RE.findall(readme)
        added = 0
        for title, url, desc in rows:
            url = url.split("?")[0].split("#")[0].rstrip("/")
            parsed_repo, _, subpath = gh.parse_repo_url(url)
            if not parsed_repo:
                continue
            # 뱃지·리스트 자기 자신·프로필 링크 제외
            if (title.startswith("!") or "badge" in url.lower()
                    or "shields.io" in url or parsed_repo == repo):
                continue
            title = title.strip(" *`")
            desc = desc.strip(" -–—:|*`")
            atype, target = classify_text(title, desc)
            if subpath:  # 레포 안 특정 폴더를 가리키면 경로로 타입을 다시 판정
                hit = classify_path(f"{subpath}/SKILL.md")
                if hit:
                    atype, target, _ = hit
            found.append({
                "source": "awesome",
                "source_url": url,
                "type": atype,
                "target_tool": target,
                "title": title,
                "repo_full_name": parsed_repo,
                "asset_path": subpath,
                "description": desc[:300],
                "popularity": 0,
                "is_official": parsed_repo.startswith("anthropics/"),
                "tags": [],
                "_subdir": subpath,
            })
            added += 1
        log(f"  {repo} → {added}건")
    return found


# ---------- 3. 공식 채널 ----------

def collect_official(repos, log=print):
    """Anthropic/Cursor 공식 저장소는 자산 단위로 펼쳐 수집한다."""
    found = []
    for repo in repos:
        source = "cursor-official" if "cursor" in repo.lower() else "claude-official"
        items = expand_repo(repo, source=source, is_official=True)
        log(f"  {repo} → {len(items)}건")
        found.extend(items)
    return found


def collect_official_docs(log=print):
    """공식 문서·릴리즈 노트 (기획서 6.1 — 공식 업데이트 빈도 신호)."""
    found = []
    releases = gh.get("/repos/anthropics/claude-code/releases", params={"per_page": 5})
    for rel in releases or []:
        tag = rel.get("tag_name") or ""
        if not tag:
            continue
        found.append({
            "source": "claude-official",
            "source_url": rel.get("html_url", ""),
            "type": "etc",
            "target_tool": "claude-code",
            "title": f"Claude Code {tag} 릴리즈",
            "repo_full_name": "anthropics/claude-code",
            "description": (rel.get("body") or "")[:300],
            "is_official": True,
            "popularity": 0,
            "source_updated_at": rel.get("published_at") or "",
            "tags": ["release"], "asset_path": "", "_subdir": "",
        })
    log(f"  공식 릴리즈 → {len(found)}건")
    return [f for f in found if f["source_url"]]


# ---------- 4. 코드 검색 (토큰 필요) ----------

def collect_code_search(log=print):
    """filename:SKILL.md 코드 검색으로 미발굴 저장소를 찾는다."""
    if not GITHUB_TOKEN:
        log("  [건너뜀] 코드 검색은 GITHUB_TOKEN 필요")
        return []
    found, seen = [], set()
    for q in ("filename:SKILL.md claude", "filename:.cursorrules"):
        data = gh.get("/search/code", params={"q": q, "per_page": 30})
        if not isinstance(data, dict):
            continue
        for item in data.get("items", []):
            full = (item.get("repository") or {}).get("full_name", "")
            if not full or full in seen:
                continue
            seen.add(full)
            found.extend(expand_repo(full))
        log(f"  코드검색 '{q}' → 누적 {len(found)}건")
    return found


# ---------- 5. 수동 링크 큐 (X 대체) ----------

def collect_link_queue(con, log=print):
    """X API 대신 사용자가 직접 넣은 링크를 자산으로 변환한다 (기획서 12장)."""
    rows = con.execute(
        "SELECT * FROM link_queue WHERE status = 'pending' ORDER BY id").fetchall()
    found = []
    for row in rows:
        url = row["url"].strip()
        note = row["note"] or ""
        repo, _, subpath = gh.parse_repo_url(url)
        if repo:
            info = gh.repo_info(repo)
            if info and not subpath:
                items = expand_repo(repo, info, source="x")
                for it in items:
                    it["description"] = note[:300] or it["description"]
                found.extend(items)
                continue
            atype, target = classify_text(url, note)
            found.append({
                "source": "x", "source_url": url, "type": atype,
                "target_tool": target, "title": (note[:60] or repo),
                "repo_full_name": repo, "asset_path": subpath or "",
                "description": note[:300],
                "popularity": info["stars"] if info else 0,
                "tags": [], "_subdir": subpath or "",
            })
        else:
            atype, target = classify_text(url, note)
            found.append({
                "source": "x", "source_url": url, "type": atype,
                "target_tool": target,
                "title": note[:60] or url.split("/")[-1] or url,
                "repo_full_name": "", "asset_path": "",
                "description": note[:300], "popularity": 0,
                "tags": [], "_subdir": "",
            })
    log(f"  수동 큐 → {len(found)}건")
    return found, [r["id"] for r in rows]


# ---------- 6. HackerNews (보조 소식) ----------

def collect_hackernews(log=print):
    found = []
    for q in ("claude code", "claude skill", "cursor rules"):
        try:
            r = requests.get("https://hn.algolia.com/api/v1/search",
                             params={"query": q, "tags": "story",
                                     "numericFilters": "points>30",
                                     "hitsPerPage": 10},
                             headers={"User-Agent": USER_AGENT}, timeout=15)
            r.raise_for_status()
            hits = r.json().get("hits", [])
        except (requests.RequestException, ValueError):
            continue
        for hit in hits:
            title = hit.get("title") or ""
            if not is_relevant(title):
                continue
            url = hit.get("url") or (
                f"https://news.ycombinator.com/item?id={hit['objectID']}")
            atype, target = classify_text(title, "")
            found.append({
                "source": "hackernews", "source_url": url, "type": atype,
                "target_tool": target, "title": title[:200],
                "repo_full_name": "", "asset_path": "",
                "description": f"HN {hit.get('points', 0)}점 · "
                               f"댓글 {hit.get('num_comments', 0)}개",
                "popularity": hit.get("points", 0),
                "tags": ["hn"], "_subdir": "",
            })
    log(f"  HackerNews → {len(found)}건")
    return found

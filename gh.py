# -*- coding: utf-8 -*-
"""GitHub API 얇은 래퍼 — 헤더, 레이트리밋 대기, raw 파일 조회."""
import re
import time

import requests

from config import GITHUB_TOKEN, USER_AGENT

API = "https://api.github.com"
RAW = "https://raw.githubusercontent.com"

_session = requests.Session()
# 무인증 코어 한도(60회/시) 소진 시 재시도 대기로 파이프라인이 수십 분 멎는 것을
# 막기 위해, 소진 사실을 풀(검색/코어)별로 기억하고 리셋까지 호출을 건너뛴다.
_exhausted_until = {"search": 0.0, "core": 0.0}


def headers(raw=False):
    h = {"User-Agent": USER_AGENT}
    if not raw:
        h["Accept"] = "application/vnd.github+json"
    if GITHUB_TOKEN:
        h["Authorization"] = f"Bearer {GITHUB_TOKEN}"
    return h


def get(path, params=None, timeout=20, retries=2):
    """GitHub API GET. 검색 레이트리밋이면 짧게 재시도, 코어 한도 소진이면
    리셋 시각까지 전 호출을 즉시 건너뛴다 (무인증 60회/시 대비)."""
    url = path if path.startswith("http") else f"{API}{path}"
    is_search = "/search/" in url
    pool = "search" if is_search else "core"
    if time.time() < _exhausted_until[pool]:
        return None
    for attempt in range(retries + 1):
        try:
            r = _session.get(url, params=params, headers=headers(), timeout=timeout)
        except requests.RequestException:
            if attempt == retries:
                return None
            time.sleep(2)
            continue
        if r.status_code in (403, 429):
            if r.headers.get("X-RateLimit-Remaining") == "0":
                if is_search and attempt < retries:
                    # 검색 한도는 분 단위로 풀리므로 잠깐 기다릴 가치가 있다
                    time.sleep(min(65, int(r.headers.get("Retry-After", 20))))
                    continue
                # 코어 한도는 시간 단위 — 기다리지 말고 리셋까지 전부 스킵
                try:
                    _exhausted_until[pool] = float(
                        r.headers.get("X-RateLimit-Reset", 0)) or time.time() + 1800
                except ValueError:
                    _exhausted_until[pool] = time.time() + 1800
                return None
            return None
        if not r.ok:
            return None
        try:
            return r.json()
        except ValueError:
            return None
    return None


def get_text(url, timeout=20):
    try:
        r = _session.get(url, headers=headers(raw=True), timeout=timeout)
        return r.text if r.ok and r.text.strip() else ""
    except requests.RequestException:
        return ""


def raw_file(repo, path, branches=("HEAD", "main", "master")):
    """저장소 내 파일 원문. (내용, 사용된 raw URL) 반환, 실패 시 ('', '')."""
    for br in branches:
        url = f"{RAW}/{repo}/{br}/{path.lstrip('/')}"
        text = get_text(url)
        if text:
            return text, url
    return "", ""


def repo_readme(repo, subpath=""):
    """README(또는 SKILL.md) 원문. 하위 폴더 자산이면 그 폴더 우선."""
    names = ["SKILL.md", "README.md", "readme.md"]
    if subpath:
        for name in names:
            text, url = raw_file(repo, f"{subpath.rstrip('/')}/{name}")
            if text:
                return text, url
    for name in names:
        text, url = raw_file(repo, name)
        if text:
            return text, url
    return "", ""


REPO_URL_RE = re.compile(
    r"https?://github\.com/([\w.-]+)/([\w.-]+?)(?:\.git)?"
    r"(?:/(?:tree|blob)/([\w.-]+)/(.+?))?/*$")


def parse_repo_url(url):
    """GitHub URL → (owner/repo, branch, subpath). 매칭 실패 시 (None, None, None)."""
    m = REPO_URL_RE.match((url or "").split("?")[0].split("#")[0])
    if not m:
        return None, None, None
    owner, repo, branch, subpath = m.groups()
    return f"{owner}/{repo}", branch, (subpath or "")


def repo_info(repo):
    """레포 메타(스타/라이선스/최근푸시). 실패 시 None."""
    data = get(f"/repos/{repo}")
    if not isinstance(data, dict) or "full_name" not in data:
        return None
    lic = (data.get("license") or {}).get("spdx_id") or ""
    return {
        "full_name": data["full_name"],
        "description": data.get("description") or "",
        "stars": data.get("stargazers_count", 0),
        "license": "" if lic in ("NOASSERTION",) else lic,
        "pushed_at": data.get("pushed_at") or "",
        "topics": data.get("topics") or [],
        "default_branch": data.get("default_branch") or "main",
        "html_url": data.get("html_url") or f"https://github.com/{repo}",
    }


def list_tree(repo, branch="HEAD"):
    """저장소 전체 파일 경로 목록. 실패하거나 잘리면 빈 리스트."""
    data = get(f"/repos/{repo}/git/trees/{branch}", params={"recursive": "1"})
    if not isinstance(data, dict):
        return []
    return [t["path"] for t in data.get("tree", []) if t.get("type") == "blob"]

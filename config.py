# -*- coding: utf-8 -*-
"""VAAL 공통 설정 — 경로, 상수, 환경변수."""
import os

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, "vaal.db")

# 원본 파일 아카이브 루트 (기획서 6.3)
ARCHIVE_DIR = os.environ.get("VAAL_ARCHIVE_DIR") or os.path.join(BASE_DIR, "vaa-archive")

GITHUB_TOKEN = os.environ.get("GITHUB_TOKEN", "")
READONLY = os.environ.get("VAAL_READONLY") == "1"
# PORT: 대부분의 배포 플랫폼(Render/Railway 등)이 표준 PORT를 주입한다.
# VAAL_PORT는 로컬 개발용 커스텀 포트로 우선 적용된다.
PORT = int(os.environ.get("VAAL_PORT") or os.environ.get("PORT") or "5240")

USER_AGENT = "VAAL/1.0 (vibe-coding asset archiver)"

# claude CLI 경로 — API 키 대신 구독 CLI를 서브프로세스로 호출한다
CLAUDE_CMD = os.environ.get("VAAL_CLAUDE_CMD") or os.path.join(
    os.environ.get("APPDATA", ""), "npm", "claude.cmd")

# 자산 타입 → 아카이브 하위 폴더 (기획서 6.3)
TYPES = ["skill", "command", "plugin", "rule", "etc"]
TYPE_LABELS = {
    "skill": "스킬",
    "command": "커맨드",
    "plugin": "플러그인",
    "rule": "룰",
    "etc": "기타",
}
TYPE_DIRS = {
    "skill": "claude-skills",
    "command": "claude-commands",
    "plugin": "plugins",
    "rule": "cursor-rules",
    "etc": "etc",
}

SOURCES = ["github", "awesome", "hackernews", "claude-official",
           "cursor-official", "x", "manual"]
SOURCE_LABELS = {
    "github": "GitHub",
    "awesome": "Awesome 리스트",
    "hackernews": "HackerNews",
    "claude-official": "Claude 공식",
    "cursor-official": "Cursor 공식",
    "x": "X (수동 큐)",
    "manual": "직접 추가",
}

TARGET_TOOLS = ["claude-code", "cursor", "common"]

# 분야 카테고리 — AI 분류 + 규칙 기반 폴백 공용
CATEGORIES = [
    "문서·오피스",
    "프론트엔드",
    "백엔드·API",
    "UI·디자인",
    "마케팅·콘텐츠",
    "데이터·분석",
    "데브옵스·배포",
    "테스트·품질",
    "보안",
    "개발 워크플로",     # git, PR 리뷰, 커밋, 코드리뷰
    "AI·에이전트",
    "생산성·자동화",
    "기타",
]

# 트렌드 스코어 기본 가중치 (기획서 6.6 — 설정에서 조정 가능)
DEFAULT_WEIGHTS = {
    "w_star_growth": 0.30,
    "w_social": 0.10,
    "w_official_update": 0.15,
    "w_internal_usage": 0.30,
    "w_recency": 0.15,
}

# 18장 — 공개 배포(VAAL_READONLY=1) 시 원문 미리보기를 허용할 라이선스 (SPDX ID).
# 라이선스가 없거나(빈 문자열) 이 목록에 없으면 원문 대신 출처 링크만 보여준다.
PERMISSIVE_LICENSES = {
    "MIT", "MIT-0", "Apache-2.0", "BSD-2-Clause", "BSD-3-Clause",
    "ISC", "CC0-1.0", "Unlicense", "0BSD",
}
PUBLIC_PREVIEW_LIMIT = 600  # 공개 배포 시 원문 스니펫 상한 (18장 — "짧은 인용만")

# 수집 최소 관심도 기준 (기획서 6.2)
DEFAULT_SETTINGS = {
    "min_stars": "0",
    "github_queries": "\n".join([
        "claude skill in:name,description",
        "claude code command in:name,description",
        "claude code plugin in:name,description",
        "awesome claude code in:name,description",
        "cursorrules in:name,description",
        "cursor rules in:name,description",
    ]),
    "awesome_lists": "\n".join([
        "ComposioHQ/awesome-claude-skills",
        "karanb192/awesome-claude-skills",
        "hesreallyhim/awesome-claude-code",
        "PatrickJS/awesome-cursorrules",
    ]),
    "official_repos": "\n".join([
        "anthropics/skills",
        "anthropics/claude-code",
    ]),
    **DEFAULT_WEIGHTS,
}

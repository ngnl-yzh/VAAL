# -*- coding: utf-8 -*-
"""분야 카테고리 분류 — 규칙 기반 (AI 부재 시 폴백, AI 결과가 오면 덮어씀)."""
from config import CATEGORIES

# 키워드 → 카테고리. 위에서부터 먼저 맞는 것이 이긴다 (구체적 → 포괄적 순).
RULES = [
    ("문서·오피스", ("docx", "pptx", "xlsx", "pdf", "word", "excel", "powerpoint",
                  "spreadsheet", "slide", "presentation", "document", "office",
                  "markdown", "resume", "이력서", "보고서")),
    ("보안", ("security", "vulnerab", "pentest", "exploit", "cve", "auth",
            "oauth", "encrypt", "secret", "credential")),
    ("테스트·품질", ("test", "tdd", "jest", "pytest", "playwright", "e2e",
                 "coverage", "lint", "quality", "review-checklist")),
    ("데브옵스·배포", ("docker", "kubernetes", "k8s", "deploy", "ci/cd", "cicd",
                  "terraform", "aws", "gcp", "azure", "devops", "infra",
                  "pipeline", "github action")),
    ("데이터·분석", ("data", "sql", "database", "analytics", "pandas", "etl",
                 "visualization", "chart", "dashboard", "scraping", "crawl")),
    ("UI·디자인", ("design", "figma", "ui kit", "tailwind", "css", "animation",
                "icon", "brand", "logo", "canvas", "art", "일러스트", "디자인")),
    ("프론트엔드", ("react", "next.js", "nextjs", "vue", "svelte", "frontend",
                "front-end", "typescript", "javascript", "html", "web app",
                "component")),
    ("백엔드·API", ("backend", "back-end", "api", "fastapi", "django", "flask",
                 "node.js", "express", "graphql", "rest", "server", "rust",
                 "golang", "microservice")),
    ("마케팅·콘텐츠", ("marketing", "seo", "content", "blog", "copywriting",
                  "social media", "newsletter", "brand-guideline", "마케팅",
                  "콘텐츠", "글쓰기", "writing")),
    ("개발 워크플로", ("git", "commit", "pr ", "pull request", "code review",
                  "changelog", "release", "branch", "merge", "workflow",
                  "issue", "refactor")),
    ("AI·에이전트", ("agent", "mcp", "llm", "prompt", "rag", "subagent",
                 "orchestrat", "autonomous", "memory", "claude.md")),
    ("생산성·자동화", ("automation", "productivity", "todo", "schedul", "cron",
                  "notion", "slack", "email", "calendar", "자동화")),
]


def categorize(title, description="", tags=()):
    """제목·설명·태그 키워드로 분야를 추정한다. 못 찾으면 '기타'."""
    text = f"{title} {description} {' '.join(tags)}".lower()
    for category, keywords in RULES:
        if any(k in text for k in keywords):
            return category
    return "기타"


def valid(category):
    """AI가 준 카테고리가 목록에 있는지 검증."""
    return category if category in CATEGORIES else ""

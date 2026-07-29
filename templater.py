# -*- coding: utf-8 -*-
"""실행 템플릿 생성기 (기획서 6.7).

규칙 기반으로 먼저 뽑고(무료·즉시·결정적), 인자 구조가 복잡한 것만 AI가 보정한다.
기획서 6.10이 지적한 대로 "단순 스킬은 규칙 기반, 복잡한 인자는 AI"를 그대로 따른다.
"""
import json
import re

# SKILL.md / 커맨드 .md 상단 YAML 프론트매터
FM_RE = re.compile(r"^---\s*\n(.*?)\n---\s*\n", re.S)
# 문서 안에 등장하는 슬래시 커맨드 예시
SLASH_RE = re.compile(r"(?:^|[\s`\"'(])(/[a-z][a-z0-9]*(?:[:-][a-z0-9]+)*)", re.I | re.M)
# $1, $ARGUMENTS, <arg>, [arg] 형태의 인자 표기
ARG_TOKEN_RE = re.compile(r"\$ARGUMENTS|\$\d+|<([a-z][\w-]*)>|\[([a-z][\w-]*)\]", re.I)

PLACEHOLDER_STOPWORDS = {
    "options", "flags", "command", "subcommand", "args", "arguments", "text",
}


def parse_frontmatter(text):
    """SKILL.md 프론트매터를 얕게 파싱한다 (name/description/argument-hint 정도)."""
    m = FM_RE.match(text or "")
    if not m:
        return {}
    data = {}
    for line in m.group(1).splitlines():
        if ":" not in line or line.startswith((" ", "\t", "-", "#")):
            continue
        key, _, value = line.partition(":")
        data[key.strip().lower()] = value.strip().strip("\"'")
    return data


def guess_command_name(asset, text=""):
    """슬래시 커맨드 이름 추정: 프론트매터 name → 문서 내 예시 → 폴더/파일명."""
    fm = parse_frontmatter(text)
    name = (fm.get("name") or "").strip()
    if name and re.fullmatch(r"[\w:-]+", name):
        return name.lstrip("/")

    title_slug = re.sub(r"[^a-z0-9:-]+", "-", (asset["title"] or "").lower()).strip("-")
    for cand in SLASH_RE.findall(text or ""):
        slug = cand.lstrip("/").lower()
        # 문서에 나온 슬래시 커맨드 중 자산 이름과 관련된 것만 채택
        if slug == title_slug or slug in title_slug or title_slug in slug:
            return cand.lstrip("/")

    return title_slug or "command"


def extract_args(text, fm=None, atype="etc"):
    """문서에서 인자 후보를 뽑는다. 결과: [{name, required, description, description_en}]

    프론트매터 argument-hint가 가장 신뢰도 높고, 그다음이 $ARGUMENTS/$1 표기다.
    본문의 <x>·[x] 스캔은 오탐(마크다운 링크·강조)이 많아 커맨드에만, 그것도
    명시적 인자 표기가 없을 때만 최후수단으로 쓴다.
    description/description_en은 한국어·영어 뷰어에게 각각 보여줄 설명이다.
    """
    fm = fm if fm is not None else parse_frontmatter(text)
    args, seen = [], set()

    hint = fm.get("argument-hint") or fm.get("arguments") or ""
    for m in ARG_TOKEN_RE.finditer(hint):
        name = (m.group(1) or m.group(2) or "").strip()
        if name and name.lower() not in seen:
            seen.add(name.lower())
            args.append({"name": name, "required": bool(m.group(1)),
                         "description": f'"{hint}" 중 {name}',
                         "description_en": f'{name} (from "{hint}")'})
    if args:
        return args

    body = FM_RE.sub("", text or "")
    if "$ARGUMENTS" in body:
        return [{"name": "arguments", "required": False,
                 "description": "커맨드에 그대로 전달되는 인자 전체",
                 "description_en": "the full argument text, passed as-is to the command"}]

    # 스킬은 자연어로 호출되고 본문에 코드·수식이 많아(엑셀 A$2 등) 오탐이 더 해롭다.
    # 본문 추정은 커맨드에만 적용한다.
    if atype != "command":
        return []

    positional = sorted({m.group(0) for m in re.finditer(r"(?<![\w$])\$\d+", body)})
    if positional:
        return [{"name": p.lstrip("$"), "required": True,
                 "description": f"{p} 위치 인자",
                 "description_en": f"{p} positional argument"} for p in positional[:4]]

    for m in _body_arg_tokens(body[:4000]):
        name = (m.group(1) or m.group(2) or "").strip()
        low = name.lower()
        if not name or low in seen or low in PLACEHOLDER_STOPWORDS or len(name) > 24:
            continue
        seen.add(low)
        args.append({"name": name, "required": bool(m.group(1)),
                     "description": "", "description_en": ""})
        if len(args) >= 4:
            break
    return args


def _body_arg_tokens(body):
    """본문에서 인자 토큰만 — 마크다운 링크/이미지/체크박스는 제외."""
    for m in ARG_TOKEN_RE.finditer(body):
        if m.group(2) is not None:  # [name] 형태
            tail = body[m.end():m.end() + 1]
            head = body[max(0, m.start() - 1):m.start()]
            if tail in ("(", "[", ":") or head == "!":
                continue  # [텍스트](url), [ref][id], 각주, 이미지
        yield m


def arg_placeholder(args):
    """템플릿에 끼워 넣을 인자 자리표시자 — 필수는 <>, 선택은 []."""
    if not args:
        return ""
    return " " + " ".join(
        f"<{a['name']}>" if a.get("required") else f"[{a['name']}]" for a in args)


def _split_args_schema(args):
    """extract_args()가 만든 description/description_en 합본을 KO/EN 스키마로 분리한다."""
    ko = [{"name": a["name"], "required": a.get("required", False),
           "description": a.get("description", "")} for a in args]
    en = [{"name": a["name"], "required": a.get("required", False),
           "description": a.get("description_en", "")} for a in args]
    return ko, en


def build(asset, text=""):
    """자산 하나의 실행 템플릿 묶음을 만든다.

    반환: dict(terminal_template, claude_code_template, cursor_apply_guide,
              install_command, args_schema, 그리고 각 필드의 영어판 *_en)

    slash-command류(skill/command/plugin)는 애초에 언어 중립적이라 *_en이
    base와 동일하다. rule/etc, args_schema의 설명문만 자연어라 실제로 번역이 갈린다.
    """
    atype = asset["type"]
    repo = asset["repo_full_name"] or ""
    path = asset["asset_path"] or ""
    # 파일 경로면 부모 폴더, 폴더 경로(awesome 리스트 유래)면 그 자체가 자산 폴더
    if "." in path.rsplit("/", 1)[-1]:
        subdir = path.rsplit("/", 1)[0] if "/" in path else ""
    else:
        subdir = path.rstrip("/")
    fm = parse_frontmatter(text)
    args = extract_args(text, fm, atype)
    ph = arg_placeholder(args)
    args_schema, args_schema_en = _split_args_schema(args)

    out = {
        "terminal_template": "", "terminal_template_en": "",
        "claude_code_template": "", "claude_code_template_en": "",
        "cursor_apply_guide": "", "cursor_apply_guide_en": "",
        "install_command": "", "install_command_en": "",
        "args_schema": args_schema,
        "args_schema_en": args_schema_en,
    }

    if atype == "skill":
        name = guess_command_name(asset, text)
        out["claude_code_template"] = out["claude_code_template_en"] = f"/{name}{ph}"
        out["terminal_template"] = out["terminal_template_en"] = f'claude "/{name}{ph}"'
        if repo and subdir:
            out["install_command"] = (
                f"# 스킬을 개인 스킬 폴더로 설치\n"
                f"git clone --depth 1 https://github.com/{repo}.git /tmp/{name}-src\n"
                f"cp -r /tmp/{name}-src/{subdir} ~/.claude/skills/{name}")
            out["install_command_en"] = (
                f"# Install this skill into your personal skills folder\n"
                f"git clone --depth 1 https://github.com/{repo}.git /tmp/{name}-src\n"
                f"cp -r /tmp/{name}-src/{subdir} ~/.claude/skills/{name}")
        elif repo:
            out["install_command"] = out["install_command_en"] = (
                f"git clone --depth 1 https://github.com/{repo}.git "
                f"~/.claude/skills/{name}")

    elif atype == "command":
        name = guess_command_name(asset, text)
        out["claude_code_template"] = out["claude_code_template_en"] = f"/{name}{ph}"
        out["terminal_template"] = out["terminal_template_en"] = f'claude "/{name}{ph}"'
        if repo and path:
            out["install_command"] = (
                f"# 커맨드 파일을 프로젝트(또는 ~/.claude)의 commands 폴더에 저장\n"
                f"curl -fsSL https://raw.githubusercontent.com/{repo}/HEAD/{path} "
                f"-o .claude/commands/{name}.md")
            out["install_command_en"] = (
                f"# Save the command file into your project's (or ~/.claude's) commands folder\n"
                f"curl -fsSL https://raw.githubusercontent.com/{repo}/HEAD/{path} "
                f"-o .claude/commands/{name}.md")

    elif atype == "plugin":
        marketplace = repo or "<owner/repo>"
        plugin_name = asset["title"]
        out["claude_code_template"] = out["claude_code_template_en"] = (
            f"/plugin marketplace add {marketplace}\n"
            f"/plugin install {plugin_name}@{marketplace.split('/')[-1]}")
        out["terminal_template"] = out["terminal_template_en"] = (
            f'claude "/plugin marketplace add {marketplace}"')
        out["install_command"] = out["install_command_en"] = out["claude_code_template"]

    elif atype == "rule":
        name = asset["title"]
        filename = path.rsplit("/", 1)[-1] if path else ".cursorrules"
        dest = ".cursorrules" if filename == ".cursorrules" else \
            f".cursor/rules/{name}.mdc"
        out["cursor_apply_guide"] = (
            f"1. 원본 파일을 프로젝트 루트의 `{dest}` 로 복사합니다.\n"
            f"2. Cursor를 다시 열면 룰이 자동 적용됩니다.\n"
            f"3. 특정 대화에서만 쓰려면 채팅에서 `@{name}` 으로 참조하세요.")
        out["cursor_apply_guide_en"] = (
            f"1. Copy the original file to `{dest}` in your project root.\n"
            f"2. Reopen Cursor and the rule applies automatically.\n"
            f"3. To use it in just one chat, reference it with `@{name}`.")
        if repo and path:
            out["install_command"] = out["install_command_en"] = (
                f"curl -fsSL https://raw.githubusercontent.com/{repo}/HEAD/{path} "
                f"-o {dest}")
        # 룰도 Claude Code에서 컨텍스트로 읽힐 수 있어 참고용 명령을 함께 제공
        out["claude_code_template"] = f"@{dest} 이 룰을 참고해서 작업해줘"
        out["claude_code_template_en"] = f"@{dest} use this rule as reference for this task"

    else:  # etc — 문서·소식류
        if repo:
            out["terminal_template"] = (
                f'claude "https://github.com/{repo} 이 저장소를 살펴보고 '
                f'어떻게 쓰는지 정리해줘"')
            out["terminal_template_en"] = (
                f'claude "review this repo and summarize how to use it: '
                f'https://github.com/{repo}"')
            out["claude_code_template"] = (
                f"이 저장소를 살펴보고 사용법을 정리해줘: https://github.com/{repo}")
            out["claude_code_template_en"] = (
                f"Review this repo and summarize how to use it: https://github.com/{repo}")
        else:
            url = asset["source_url"]
            out["terminal_template"] = f'claude "{url} 이 문서 핵심만 정리해줘"'
            out["terminal_template_en"] = f'claude "summarize the key points of {url}"'
            out["claude_code_template"] = f"{url} 이 문서 핵심만 정리해줘"
            out["claude_code_template_en"] = f"Summarize the key points of {url}"

    return out


def needs_ai(result, text=""):
    """규칙 기반 결과가 부실해 AI 보정이 필요한지 판단한다."""
    if not result["claude_code_template"] and not result["cursor_apply_guide"]:
        return True
    # 명시적 인자 표기가 원문에 있는데 하나도 못 뽑았으면 AI에게 맡긴다
    body = FM_RE.sub("", text or "")
    has_arg_hint = bool(re.search(r"\$ARGUMENTS|(?<![\w$])\$\d+", body[:4000]))
    return has_arg_hint and not result["args_schema"]


def apply_ai_args(result, ai_payload):
    """AI가 준 인자 스키마·템플릿으로 규칙 기반 결과를 보정한다."""
    if not isinstance(ai_payload, dict):
        return result
    args = ai_payload.get("args")
    if isinstance(args, list) and args:
        clean = []
        for a in args[:6]:
            if isinstance(a, dict) and a.get("name"):
                clean.append({
                    "name": str(a["name"])[:32],
                    "required": bool(a.get("required")),
                    "description": str(a.get("description", ""))[:200],
                })
        if clean:
            result["args_schema"] = clean
            # AI 인자 설명은 한국어뿐이라 영어판 설명은 대응이 끊긴다 — base로 폴백하도록 비운다.
            result["args_schema_en"] = []
            ph = arg_placeholder(clean)
            base = result["claude_code_template"].split(" ")[0]
            if base.startswith("/"):
                result["claude_code_template"] = f"{base}{ph}"
                result["terminal_template"] = f'claude "{base}{ph}"'
                # skill/command류는 언어 중립적이라 영어판도 그대로 맞춰준다.
                result["claude_code_template_en"] = result["claude_code_template"]
                result["terminal_template_en"] = result["terminal_template"]
    for key in ("terminal_template", "claude_code_template", "cursor_apply_guide"):
        value = ai_payload.get(key)
        if isinstance(value, str) and value.strip() and not result[key]:
            result[key] = value.strip()[:500]
    return result


def to_json(args):
    return json.dumps(args, ensure_ascii=False)

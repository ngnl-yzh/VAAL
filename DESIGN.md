---
name: VAAL
description: 바이브코딩 자산 아카이버 & 런처 — 발견에서 실행까지 끊기지 않는 다크 개발자 도구
colors:
  bg: "#0d1117"
  panel: "#161b22"
  panel-2: "#1c2230"
  line: "#2d333b"
  text: "#e6edf3"
  dim: "#8b949e"
  accent: "#58a6ff"
  accent-2: "#3fb950"
  warn: "#d29922"
  hot: "#f85149"
  star: "#e3b341"
  chip-skill: "#79b8ff"
  chip-command: "#3fb950"
  chip-plugin: "#d2a8ff"
  chip-rule: "#f0883e"
  hover-panel: "#242b3d"
  star-off: "#3a4150"
typography:
  display:
    fontFamily: "'Segoe UI','Malgun Gothic',sans-serif"
    fontSize: "clamp(1.6rem, 3.2vw, 2.35rem)"
    fontWeight: 700
    lineHeight: 1.3
  body:
    fontFamily: "'Segoe UI','Malgun Gothic',sans-serif"
    fontSize: "14px"
    fontWeight: 400
    lineHeight: 1.5
  body-lg:
    fontFamily: "'Segoe UI','Malgun Gothic',sans-serif"
    fontSize: "15px"
    fontWeight: 400
    lineHeight: 1.55
  title:
    fontFamily: "'Segoe UI','Malgun Gothic',sans-serif"
    fontSize: "17px"
    fontWeight: 600
  title-sm:
    fontFamily: "'Segoe UI','Malgun Gothic',sans-serif"
    fontSize: "16px"
    fontWeight: 600
  caption:
    fontFamily: "'Segoe UI','Malgun Gothic',sans-serif"
    fontSize: "12px"
    fontWeight: 400
  label:
    fontFamily: "'Segoe UI','Malgun Gothic',sans-serif"
    fontSize: "11px"
    fontWeight: 400
    letterSpacing: "0.02em"
  stat:
    fontFamily: "'Segoe UI','Malgun Gothic',sans-serif"
    fontSize: "26px"
    fontWeight: 700
  mono:
    fontFamily: "Consolas, monospace"
    fontSize: "13px"
rounded:
  xs: "8px"
  sm: "6px"
  md: "10px"
  pill: "999px"
spacing:
  xs: "6px"
  sm: "10px"
  md: "14px"
  lg: "18px"
  xl: "22px"
components:
  button-primary:
    backgroundColor: "{colors.accent}"
    textColor: "#0d1117"
    rounded: "{rounded.sm}"
    padding: "6px 12px"
  button-primary-hover:
    backgroundColor: "#79b8ff"
  button-default:
    backgroundColor: "{colors.panel-2}"
    textColor: "{colors.text}"
    rounded: "{rounded.sm}"
    padding: "6px 12px"
  card:
    backgroundColor: "{colors.panel}"
    textColor: "{colors.text}"
    rounded: "{rounded.md}"
    padding: "13px 14px"
  chip:
    backgroundColor: "{colors.panel-2}"
    textColor: "{colors.dim}"
    rounded: "{rounded.pill}"
    padding: "2px 8px"
---

# Design System: VAAL

## Overview

**Creative North Star: "The Personal Command Ledger"**

VAAL은 GitHub의 다크 테마 문법(정확히 같은 배경·강조색 좌표계)을 그대로 물려받아, "내가 계속 들춰보는 개인 명령어 장부"라는 인상을 준다. 화려함이 아니라 신뢰감으로 승부하는 화면 — 개발자가 자기 터미널·에디터 옆에 계속 띄워둬도 어색하지 않아야 한다는 것이 유일한 미학적 기준이다. 이 톤은 기획 단계에서부터 명시적으로 유지 대상으로 지정되었다(PRODUCT.md 참고).

밀도는 높은 편이다(13-14px 본문, 좁은 카드 패딩) — 한 화면에 최대한 많은 자산을 스캔 가능하게 보여주는 것이 카드 크기를 키우는 것보다 우선한다. 여백보다 정보 밀도, 장식보다 명료함.

**Key Characteristics:**
- GitHub Dark와 좌표계를 공유하는 팔레트 — 개발자에게 "본 적 있는 색"으로 즉시 신뢰를 산다.
- 평상시엔 완전히 플랫(그림자 없음), 상호작용 순간(호버·오픈)에만 깊이가 나타난다.
- 정보 밀도가 장식보다 우선하는 대시보드형 레이아웃.
- 단색 강조(파랑 accent) 하나만 반복 사용 — 타입별 칩 색상을 빼면 채도 있는 색은 거의 쓰지 않는다.

## Colors

GitHub Dark 계열의 절제된 팔레트. 강조색은 accent(파랑) 하나로 고정하고, 색은 "장식"이 아니라 "분류 신호"(자산 타입 칩, 트렌드/평점)로만 쓴다.

### Primary
- **Signal Blue** (`#58a6ff`): 유일한 브랜드 강조색. 링크, 기본 버튼, 포커스 링, 검색 포커스 테두리. 화면의 10% 이내로만 등장한다.

### Secondary
- **Ledger Green** (`#3fb950`): "완료·긍정" 신호 전용 — 트렌드 스코어 수치, 커맨드 타입 칩, 복사 완료 버튼 상태.

### Tertiary
- **Star Gold** (`#e3b341`): 평점(별점)과 "공식" 배지 전용. 다른 용도로 확장하지 않는다.

### Neutral
- **Void** (`#0d1117`): 페이지 기본 배경.
- **Panel** (`#161b22`): 카드·헤더·상세 패널 배경.
- **Panel Raised** (`#1c2230`): 입력창·보조 버튼·비활성 칩 배경 — Panel보다 한 단 밝음.
- **Line** (`#2d333b`): 모든 테두리·구분선.
- **Ink** (`#e6edf3`): 기본 텍스트.
- **Dim** (`#8b949e`): 보조 텍스트·캡션·플레이스홀더 (배경 대비 6.1:1 이상 확인됨).
- **Hover Panel** (`#242b3d`): 기본 버튼·내비게이션의 호버 배경 — Panel Raised보다 한 단 더 밝은 상호작용 전용 단계.
- **Star Off** (`#3a4150`): 평점 위젯에서 비어있는 별의 색.

### Named Rules
**The One Accent Rule.** Signal Blue는 "지금 누를 수 있는 것"에만 쓴다. 장식적으로 텍스트나 배경에 흩뿌리지 않는다.

## Typography

**Body/Display Font:** 'Segoe UI', 'Malgun Gothic', sans-serif (시스템 폰트 — 이 프로젝트는 타이포로 개성을 내지 않는다)
**Label/Mono Font:** Consolas, monospace — 오직 실행 커맨드 표시(cmdbox)에만 사용

**Character:** 장식적 타이포 계층이 거의 없는 평평한 스케일. 위계는 폰트가 아니라 색(dim vs ink)과 칩으로 만든다.

### Hierarchy
- **Display** (700, clamp(1.6rem,3.2vw,2.35rem)): 공개 랜딩 페이지(Persuade 표면) 전용 헤드라인. 대시보드(Operate 표면)는 쓰지 않는다 — 이 시스템에서 유일하게 "주장을 위해 커진" 텍스트다.
- **Body-lg** (400, 15px): 랜딩 페이지의 서브카피 전용, 65ch 이내로 감싼다.
- **Title** (600, 17px): 헤더 브랜드명.
- **Title-sm** (600, 16px): 상세 패널·모달 제목.
- **Body** (400, 14px): 기본 UI 텍스트, 카드 제목.
- **Caption** (400, 12px, `--dim`): 패널 소제목, 메타 텍스트, 폼 라벨.
- **Label** (400, 11px, `--dim`): 칩, 통계 라벨처럼 가장 작은 보조 텍스트.
- **Stat** (700, 26px, `--accent`): 리포트 화면의 큰 숫자(총 자산, 실행 횟수 등) 전용.
- **Mono** (400, 13px, Consolas): 실행 커맨드 텍스트 전용 — 이 프로젝트에서 유일하게 "다른 폰트"를 쓰는 지점이라 신호값이 크다.

### Named Rules
**The Mono-Means-Runnable Rule.** Consolas는 오직 "복사해서 그대로 실행할 수 있는 문자열"에만 쓴다. 장식으로 쓰지 않는다.

## Layout

12px 그리드 갭의 auto-fill 카드 그리드(`minmax(270px,1fr)`), 좌측 210px 고정 필터 사이드바 + 유동 콘텐츠 영역. 상세 패널은 우측에서 슬라이드 인하는 660px(최대 95vw) 오버레이 드로어. 반응형 브레이크포인트는 아직 명시적으로 정의되지 않음 — 카드 그리드의 `auto-fill`이 사실상의 반응형 전략.

## Elevation & Depth

**기본은 완전히 플랫.** 카드·패널 모두 평상시엔 그림자가 없고 1px 테두리(`--line`)로만 구분된다. 2026-07-29 폴리시 작업에서 "상호작용 순간에만" 그림자가 나타나도록 규칙을 도입했다 — 평상시 플랫을 깨지 않으면서 깊이를 상태 신호로만 쓴다.

### Shadow Vocabulary
- **Card Hover** (`box-shadow: 0 4px 16px rgba(0,0,0,.35)` + `translateY(-1px)`): 카드에 마우스를 올리거나 키보드로 포커스했을 때만.
- **Focus Ring** (`box-shadow: 0 0 0 3px rgba(88,166,255,.25), 0 4px 16px rgba(0,0,0,.35)`): 카드 키보드 포커스 전용, accent 색을 틴트해서 사용.
- **Drawer Separation** (`box-shadow: -16px 0 40px rgba(0,0,0,.45)`): 상세 패널이 배경 콘텐츠 위로 뜰 때.

### Named Rules
**The Flat-At-Rest Rule.** 그림자는 상태(호버, 포커스, 오픈)에 대한 반응으로만 나타난다. 정지 상태의 UI에 그림자를 얹지 않는다.

## Shapes

카드·패널은 10px 라운드(`--radius`), 버튼·입력창·칩 컨테이너는 6px, 칩 자체는 완전한 필(999px). 코드 박스·중첩 패널처럼 패널 "안"에 놓이는 2차 컨테이너는 8px(`rounded.xs`)로 한 단 작게 — 중첩 시 라운드가 작아지는 것이 규칙이지, 무작위 값이 아니다. 테두리는 항상 1px `--line` — 그림자로 뜨우는 대신 테두리로 경계를 긋는 것이 기본 문법.

## Components

### Buttons
- **Shape:** 6px 라운드, 그림자 없음.
- **Default:** `--panel2` 배경, `--text` 색. 호버 시 `#242b3d`로 전환(120ms).
- **Primary:** `--accent` 배경(#0d1117 텍스트, 600 weight). 호버 시 `#79b8ff`.
- **Focus:** 2px accent 아웃라인 + 2px 오프셋(2026-07-29 추가 — 이전엔 포커스 표시가 없었음).

### Chips
- **Style:** `--panel2` 배경 필, 타입별로 텍스트 색만 다름(스킬=#79b8ff, 커맨드=#3fb950, 플러그인=#d2a8ff, 룰=#f0883e, 공식=star gold).
- **State:** 정적 배지 — 선택/필터 상호작용 없음, 순수 분류 표시.

### Cards / Containers
- **Corner Style:** 10px.
- **Background:** `--panel`, 테두리 `--line`.
- **Shadow Strategy:** 평상시 없음, 호버/포커스 시 Card Hover/Focus Ring 적용(Elevation 참고).
- **Internal Padding:** 13px 14px.
- **Interaction:** `role="button"` + `tabindex="0"` — 클릭과 키보드(Enter/Space) 모두로 상세 패널을 연다(2026-07-29 접근성 보강).

### Inputs / Fields
- **Style:** `--panel2` 배경, 1px `--line` 테두리, 6px 라운드.
- **Focus:** 테두리 색이 `--accent`로 전환, 별도 아웃라인 없음.

### Navigation
- **Style:** 상단 고정(`sticky`) 헤더, 텍스트 버튼형 탭(`대시보드/리포트/링크 큐/설정`). 활성 탭은 `--panel2` 배경으로 채워짐. 호버 상태 없음(탭은 즉시 전환).

### Command Box (Signature Component)
실행 커맨드를 보여주는 이 프로젝트의 시그니처 컴포넌트. `#0a0d12`(패널보다 더 어두운 배경) + `--line` 테두리 + Consolas 모노스페이스 + 우상단 "복사" 버튼 + 좌상단 라벨 칩("터미널"/"Claude Code"). 이 컴포넌트가 VAAL의 핵심 차별점(즉시 실행 변환)을 시각적으로 담당하므로, 다른 곳에 재사용하지 않고 이 용도로만 남겨둔다.

## Do's and Don'ts

### Do:
- **Do** Signal Blue를 상호작용 가능한 요소에만 쓴다 — 텍스트 강조 목적으로 쓰지 않는다.
- **Do** 그림자를 상태 반응으로만 추가한다(호버/포커스/오픈). 정지 상태 카드는 항상 플랫.
- **Do** Consolas는 실행 가능한 커맨드 문자열에만 쓴다.
- **Do** 새 인터랙티브 요소에는 `:focus-visible` 스타일을 함께 만든다(카드/버튼 선례를 따름).

### Don't:
- **Don't** 그라디언트나 글로우(halo)를 장식으로 쓰지 않는다 — 이 시스템은 GitHub Dark의 절제된 평면성을 물려받았다.
- **Don't** 칩 색상 팔레트를 자산 타입 분류 밖의 용도로 확장하지 않는다.
- **Don't** 카드에 중첩 카드를 넣지 않는다(자산 카드 안에 또 다른 카드형 컨테이너를 만들지 않음).
- **Don't** 다크 톤을 라이트 테마로 전면 교체하지 않는다 — 확장(예: 공개 랜딩 페이지)은 이 세계관 위에 짓는다, 대체하지 않는다.

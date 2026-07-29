# VAAL — 바이브코딩 자산 아카이버 & 런처

GitHub·awesome 리스트·공식 채널·수동 큐에서 Claude Code 스킬/커맨드/플러그인과
Cursor 룰을 자동 수집·아카이빙하고, 클릭 한 번으로 실행 명령어를 복사하는 개인 런처.

기획서 v0.5의 4축(수집·평가·유행도·즉시실행)을 전부 구현했다.

## 실행

```bash
cd "C:\Users\yzh37\Desktop\작업\제작 프로그램들\VAAL"
python app.py
```

→ http://127.0.0.1:5240 (launch.json 이름: `vaal`)

## 파이프라인 (CLI)

```bash
python pipeline.py                     # 수집→아카이브→AI→트렌드→인덱스 전체
python pipeline.py --no-ai             # AI 생략 (규칙 기반 템플릿만)
python pipeline.py --steps collect,archive
python pipeline.py --ai-limit 60
```

UI의 "지금 수집 실행" 버튼도 같은 파이프라인을 백그라운드로 돌린다.

## 구조

| 파일 | 역할 |
|---|---|
| `config.py` | 경로·상수·기본 설정 |
| `db.py` | SQLite 스키마(assets/star_history/usage_log/link_queue/settings/runs) |
| `gh.py` | GitHub API 래퍼 (레이트리밋 대기, raw 파일) |
| `collectors.py` | 소스별 수집기 — 저장소를 **개별 자산 단위로 펼쳐서** 수집 |
| `archiver.py` | 원본 파일 다운로드(vaa-archive/), meta.md·_index.md 생성 |
| `templater.py` | 실행 템플릿 규칙 기반 추출 (프론트매터·$ARGUMENTS·argument-hint) |
| `ai_layer.py` | `claude -p` 호출 — 용도/사용법 요약, 평가 초안, 인자 보정, 트렌드 코멘트 |
| `trends.py` | 트렌드 스코어 (star 증가율+소셜+공식 업데이트+내부 사용+최근성 가중합) |
| `pipeline.py` | 5단계 오케스트레이션 + 주간 리포트 |
| `app.py` | Flask 웹앱 (포트 5240) |

## 특징

- **AI 비용 0원**: API 키 대신 로컬 `claude -p`(구독 CLI)를 서브프로세스로 호출.
  claude CLI가 없으면 규칙 기반 템플릿만으로도 동작한다.
- **GITHUB_TOKEN 선택**: 없으면 무인증(검색 분당 10회)으로 동작, 있으면
  코드 검색(filename:SKILL.md)까지 켜진다.
- **원본 보관**: 링크만 저장하는 ClaudeRadar와 달리 SKILL.md 등 원본 파일을
  `vaa-archive/`에 내려받아 출처가 사라져도 자산이 남는다.
- **평가·유행도 내재화**: 별점/후기(사용자), AI 평가 초안, 복사 횟수 자동 집계,
  트렌드 배지(🔥 급상승 / 🆕 신규 / ⭐ 꾸준히 인기).

## 주간 자동화

`C:\Users\yzh37\.claude\automation\weekly-vaal\run.ps1` — 작업 스케줄러 등록:

```bash
schtasks /Create /TN WeeklyVAAL /SC WEEKLY /D WED /ST 09:30 /TR "powershell -NoProfile -ExecutionPolicy Bypass -File C:\Users\yzh37\.claude\automation\weekly-vaal\run.ps1"
```

## 환경 변수 (모두 선택)

| 변수 | 기본 | 설명 |
|---|---|---|
| `GITHUB_TOKEN` | 없음 | 있으면 API 한도 5,000/h + 코드 검색 활성화 |
| `VAAL_PORT` / `PORT` | 5240 | 웹 포트 (`PORT`는 Render 등 배포 플랫폼이 자동 주입) |
| `VAAL_ARCHIVE_DIR` | `./vaa-archive` | 원본 보관 폴더 — 배포 시 영구 디스크 경로로 지정 |
| `VAAL_DB_PATH` | `./vaal.db` | DB 파일 경로 — 배포 시 영구 디스크 경로로 지정 |
| `VAAL_CLAUDE_CMD` | `%APPDATA%\npm\claude.cmd` | claude CLI 경로 |
| `VAAL_READONLY` | 0 | 1이면 열람 전용. 로그인/관리자 시스템이 생긴 뒤로는 보통 불필요(관리자 본인도 막힘) |
| `SECRET_KEY` | (안전하지 않은 기본값) | 세션 서명 키 — 배포 시 반드시 진짜 랜덤값 지정 |
| `VAAL_ADMIN_EMAILS` | 없음 | 관리자로 인정할 이메일(콤마 구분). 로컬 개발 시 `admin_emails.txt`(한 줄에 하나)로도 지정 가능 |
| `SMTP_HOST`/`SMTP_PORT`/`SMTP_USER`/`SMTP_PASS`/`SMTP_FROM` | 없음 | 회원가입 인증 메일 실제 발송용. 없으면 서버 로그에 인증 링크만 출력 |
| `CRON_SECRET` | 없음 | 설정하면 `Authorization: Bearer <값>` 헤더로 로그인 없이 관리자 API(파이프라인 실행 등) 호출 가능 — Hermes 등 외부 스케줄러가 배포된 사이트를 직접 트리거할 때 사용 |

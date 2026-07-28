# -*- coding: utf-8 -*-
"""VAAL 계정/인증 — 비밀번호 해시, 이메일 인증 발송, 관리자 판별.

관리자는 DB 컬럼이 아니라 VAAL_ADMIN_EMAILS 환경변수(콤마 구분) 또는
admin_emails.txt 파일(한 줄에 하나)로 판별한다. 파일은 환경변수를 새로
띄운 프로세스에만 적용하기 번거로운 로컬 개발 환경을 위한 폴백이다.
가입 순서 기반("첫 가입자가 관리자")은 공개 배포 시 레이스 컨디션이 생길 수 있어 쓰지 않는다.
"""
import os
import secrets
import smtplib
from email.mime.text import MIMEText

from werkzeug.security import check_password_hash, generate_password_hash

_ADMIN_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "admin_emails.txt")


def _load_admin_emails():
    emails = {e.strip().lower() for e in
              os.environ.get("VAAL_ADMIN_EMAILS", "").split(",") if e.strip()}
    if os.path.isfile(_ADMIN_FILE):
        with open(_ADMIN_FILE, encoding="utf-8") as f:
            emails |= {ln.strip().lower() for ln in f if ln.strip() and not ln.startswith("#")}
    return emails


ADMIN_EMAILS = _load_admin_emails()

SMTP_HOST = os.environ.get("SMTP_HOST", "")
SMTP_PORT = int(os.environ.get("SMTP_PORT", "587"))
SMTP_USER = os.environ.get("SMTP_USER", "")
SMTP_PASS = os.environ.get("SMTP_PASS", "")
SMTP_FROM = os.environ.get("SMTP_FROM") or SMTP_USER


def hash_password(pw):
    return generate_password_hash(pw)


def verify_password(pw, pw_hash):
    return check_password_hash(pw_hash, pw)


def new_token():
    return secrets.token_urlsafe(32)


def is_admin_email(email):
    return (email or "").strip().lower() in ADMIN_EMAILS


def send_verification_email(to_email, verify_url, log=print):
    """SMTP_* 환경변수가 없으면 실제 발송 대신 로그로 링크를 남긴다(로컬 개발/테스트용)."""
    subject = "VAAL — Confirm your email / 이메일 인증"
    body = (
        "Click the link below to verify your VAAL account email:\n"
        f"{verify_url}\n\n"
        "아래 링크를 클릭해 VAAL 계정 이메일을 인증하세요:\n"
        f"{verify_url}\n"
    )
    if not (SMTP_HOST and SMTP_USER and SMTP_PASS):
        print(f"[메일 발송 미설정 — SMTP_* 환경변수 없음] {to_email} 인증 링크: {verify_url}",
              flush=True)
        return False
    msg = MIMEText(body, "plain", "utf-8")
    msg["Subject"] = subject
    msg["From"] = SMTP_FROM
    msg["To"] = to_email
    try:
        with smtplib.SMTP(SMTP_HOST, SMTP_PORT, timeout=10) as server:
            server.starttls()
            server.login(SMTP_USER, SMTP_PASS)
            server.sendmail(SMTP_FROM, [to_email], msg.as_string())
        return True
    except Exception as e:  # noqa: BLE001 — 발송 실패해도 링크는 로그로 남겨야 한다
        log(f"[메일 발송 실패] {to_email}: {e!r} — 인증 링크: {verify_url}")
        return False

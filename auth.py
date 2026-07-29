# -*- coding: utf-8 -*-
"""VAAL 계정/인증 — 비밀번호 해시, 관리자 판별.

관리자는 DB 컬럼이 아니라 VAAL_ADMIN_EMAILS 환경변수(콤마 구분) 또는
admin_emails.txt 파일(한 줄에 하나)로 판별한다. 파일은 환경변수를 새로
띄운 프로세스에만 적용하기 번거로운 로컬 개발 환경을 위한 폴백이다.
가입 순서 기반("첫 가입자가 관리자")은 공개 배포 시 레이스 컨디션이 생길 수 있어 쓰지 않는다.
"""
import os

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


def hash_password(pw):
    return generate_password_hash(pw)


def verify_password(pw, pw_hash):
    return check_password_hash(pw_hash, pw)


def is_admin_email(email):
    return (email or "").strip().lower() in ADMIN_EMAILS

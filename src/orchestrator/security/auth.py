from __future__ import annotations

"""Authentication utilities: JWT handling and dev user store.

This module provides:
- Pydantic models for Login and User context
- In-memory dev users (hashed passwords)
- JWT encode/decode helpers
- FastAPI dependencies to get the current user

Env vars (for production readiness):
- JWT_SECRET (required in prod; default for dev)
- JWT_EXPIRES_MIN (default 60)
"""

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from email.message import EmailMessage
from typing import Dict, Optional

import os
import logging
import jwt
import secrets
import smtplib
import ssl
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel, EmailStr


logger = logging.getLogger(__name__)
bearer_scheme = HTTPBearer(auto_error=False)


def _get_env(name: str, default: Optional[str] = None) -> str:
    val = os.getenv(name, default)
    if val is None:
        raise RuntimeError(f"Missing required environment variable: {name}")
    return val


@dataclass
class JwtConfig:
    secret: str
    algorithm: str = "HS256"
    expires_min: int = 60

    @staticmethod
    def from_env() -> "JwtConfig":
        secret = _get_env("JWT_SECRET", "dev-secret-change-me")
        expires = int(os.getenv("JWT_EXPIRES_MIN", "60"))
        return JwtConfig(secret=secret, expires_min=expires)


class User(BaseModel):
    email: EmailStr
    name: str
    roles: list[str]


class OTPRequest(BaseModel):
    email: EmailStr


class OTPVerifyRequest(BaseModel):
    email: EmailStr
    code: str
    name: Optional[str] = None


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int
    user: User


# In-memory dev users (email -> {name, roles})
USERS: Dict[str, Dict[str, object]] = {
    "adam.thacker@expeed.com": {
        "name": "Adam Thacker",
        "roles": ["admin"],
    },
    "contrib@example.com": {
        "name": "Contributor User",
        "roles": ["contributor"],
    },
}


@dataclass
class OTPEntry:
    code: str
    expires_at: datetime
    attempts: int = 0
    sent_at: Optional[datetime] = None


OTP_STORE: Dict[str, OTPEntry] = {}
OTP_EXP_MINUTES = int(os.getenv("OTP_EXPIRES_MIN", "10"))
OTP_MAX_ATTEMPTS = int(os.getenv("OTP_MAX_ATTEMPTS", "5"))
OTP_RESEND_DELAY_SECONDS = int(os.getenv("OTP_RESEND_DELAY_SECONDS", "180"))
INCLUDE_OTP_IN_RESPONSE = os.getenv("OPNXT_INCLUDE_OTP_IN_RESPONSE", "1").lower() in ("1", "true", "yes")


def _smtp_configured() -> bool:
    host = os.getenv("OPNXT_SMTP_HOST")
    user = os.getenv("OPNXT_SMTP_USER")
    password = os.getenv("OPNXT_SMTP_PASSWORD")
    sender = os.getenv("OPNXT_SMTP_SENDER") or user
    if not host or not user or not password or not sender:
        return False
    try:
        int(os.getenv("OPNXT_SMTP_PORT", "587"))
    except ValueError:
        return False
    return True


def _send_otp_email(recipient: str, code: str) -> None:
    if not _smtp_configured():
        logger.info("SMTP not fully configured; skipping OTP email send")
        return
    host = os.getenv("OPNXT_SMTP_HOST")
    port = int(os.getenv("OPNXT_SMTP_PORT", "587"))
    user = os.getenv("OPNXT_SMTP_USER")
    password = os.getenv("OPNXT_SMTP_PASSWORD")
    sender = os.getenv("OPNXT_SMTP_SENDER") or user
    use_tls = os.getenv("OPNXT_SMTP_USE_TLS", "1").lower() in ("1", "true", "yes")
    use_ssl = os.getenv("OPNXT_SMTP_USE_SSL", "0").lower() in ("1", "true", "yes")
    timeout = int(os.getenv("OPNXT_SMTP_TIMEOUT", "10"))

    message = EmailMessage()
    message["Subject"] = "Your OPNXT verification code"
    message["From"] = sender
    message["To"] = recipient
    message.set_content(
        f"Your one-time passcode is {code}.\n\n"
        f"It expires in {OTP_EXP_MINUTES} minutes."
    )

    try:
        context = ssl.create_default_context()
        if use_ssl:
            with smtplib.SMTP_SSL(host, port, timeout=timeout, context=context) as client:
                client.login(user, password)
                client.send_message(message)
                logger.info("Sent OTP email to %s via %s:%s (SSL)", recipient, host, port)
        else:
            with smtplib.SMTP(host, port, timeout=timeout) as client:
                client.ehlo()
                if use_tls:
                    client.starttls(context=context)
                    client.ehlo()
                client.login(user, password)
                client.send_message(message)
                logger.info("Sent OTP email to %s via %s:%s", recipient, host, port)
    except Exception:
        logger.exception("Failed to send OTP email to %s", recipient)


def create_access_token(user: User, cfg: Optional[JwtConfig] = None) -> str:
    cfg = cfg or JwtConfig.from_env()
    now = datetime.now(timezone.utc)
    exp = now + timedelta(minutes=cfg.expires_min)
    payload = {
        "sub": user.email,
        "name": user.name,
        "roles": user.roles,
        "iat": int(now.timestamp()),
        "exp": int(exp.timestamp()),
    }
    return jwt.encode(payload, cfg.secret, algorithm=cfg.algorithm)


def decode_token(token: str, cfg: Optional[JwtConfig] = None) -> User:
    cfg = cfg or JwtConfig.from_env()
    try:
        data = jwt.decode(token, cfg.secret, algorithms=[cfg.algorithm])
        return User(email=data["sub"], name=data.get("name", ""), roles=list(data.get("roles", [])))
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Token expired")
    except Exception:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")


def _get_user_record(email: str) -> Optional[Dict[str, object]]:
    return USERS.get(email.lower())


def register_user(email: str, name: str, roles: Optional[list[str]] = None) -> User:
    """Register a new in-memory user for development/demo environments.

    For open registration flows, the role is forced to ["viewer"] to avoid privilege escalation.
    In admin-controlled flows, pass roles explicitly from the router after authorization.
    """
    email_l = email.lower()
    if email_l in USERS:
        raise ValueError("User already exists")
    effective_roles = roles or ["viewer"]
    USERS[email_l] = {
        "name": name,
        "roles": effective_roles,
    }
    return User(email=email_l, name=name, roles=effective_roles)


def _generate_otp_code(length: int = 6) -> str:
    return "".join(secrets.choice("0123456789") for _ in range(length))


def issue_otp(email: str) -> str:
    email_l = email.lower()
    now = datetime.now(timezone.utc)
    existing = OTP_STORE.get(email_l)

    if existing and existing.expires_at > now:
        if existing.sent_at and (now - existing.sent_at).total_seconds() < OTP_RESEND_DELAY_SECONDS:
            logger.info(
                "OTP for %s already issued at %s; reusing existing code without resend",
                email_l,
                existing.sent_at.isoformat() if existing.sent_at else "unknown",
            )
            return existing.code
        code = existing.code
        expires = existing.expires_at
    else:
        code = _generate_otp_code()
        expires = now + timedelta(minutes=OTP_EXP_MINUTES)

    entry = OTPEntry(code=code, expires_at=expires, sent_at=now)
    OTP_STORE[email_l] = entry
    logger.info("Issued OTP for %s expiring at %s", email_l, expires.isoformat())
    _send_otp_email(email, code)
    return code


def verify_otp(email: str, code: str, name: Optional[str] = None) -> User:
    email_l = email.lower()
    entry = OTP_STORE.get(email_l)
    if not entry:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="OTP not requested")

    now = datetime.now(timezone.utc)
    if entry.expires_at < now:
        OTP_STORE.pop(email_l, None)
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="OTP expired")

    entry.attempts += 1
    if entry.attempts > OTP_MAX_ATTEMPTS:
        OTP_STORE.pop(email_l, None)
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Too many invalid attempts")

    if entry.code != code:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid code")

    OTP_STORE.pop(email_l, None)

    rec = _get_user_record(email_l)
    if rec is None:
        if not name:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Name required to create account")
        user = register_user(email_l, name, roles=["viewer"])
    else:
        if name and rec.get("name") != name:
            rec["name"] = name
        user = User(email=email_l, name=str(rec.get("name", email_l)), roles=list(rec.get("roles", [])))

    return user


def _public_mode_enabled() -> bool:
    """Return True if public mode should be enabled.

    Priority:
    1) Respect explicit OPNXT_PUBLIC_MODE if provided.
    2) Otherwise, default to True in non-production environments to simplify local dev.
       We consider production if any of the common env vars indicate it.
    """
    # Respect explicit setting first (including in tests)
    val = os.getenv("OPNXT_PUBLIC_MODE")
    if val is not None:
        return val.lower() in ("1", "true", "yes")
    # If running under pytest and not explicitly set, force public mode off so tests validate auth behavior
    if os.getenv("PYTEST_CURRENT_TEST"):
        return False
    if val is not None:
        return val.lower() in ("1", "true", "yes")
    # No explicit setting: infer from environment
    env_name = (
        os.getenv("OPNXT_ENV")
        or os.getenv("ENVIRONMENT")
        or os.getenv("ENV")
        or os.getenv("PYTHON_ENV")
        or "development"
    ).lower()
    if env_name in ("prod", "production"):
        return False
    # Avoid enabling in CI by default
    if os.getenv("CI") or os.getenv("GITHUB_ACTIONS"):
        return False
    # Default to public in dev
    return True


def get_current_user(creds: Optional[HTTPAuthorizationCredentials] = Depends(bearer_scheme)) -> User:
    """Resolve the current user.

    In normal mode, requires a valid bearer token.
    If OPNXT_PUBLIC_MODE is enabled, allow anonymous access and return a
    default guest user with contributor privileges for MVP/demo scenarios.
    """
    public_mode = _public_mode_enabled()
    if creds is None or not creds.scheme or creds.scheme.lower() != "bearer":
        if public_mode:
            return User(email="guest@example.com", name="Guest", roles=["contributor"])  # viewer+write for MVP
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing bearer token")
    token = creds.credentials
    try:
        return decode_token(token)
    except Exception:
        if public_mode:
            return User(email="guest@example.com", name="Guest", roles=["contributor"])  # tolerate bad tokens in public mode
        raise

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
from typing import Dict, Optional

import os
import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from passlib.context import CryptContext
from pydantic import BaseModel, EmailStr


pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
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


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class RegisterRequest(BaseModel):
    email: EmailStr
    name: str
    password: str
    roles: list[str] | None = None  # ignored for open registration; default to ["viewer"]


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int
    user: User


def _hash_password(plain: str) -> str:
    return pwd_context.hash(plain)


def _verify_password(plain: str, hashed: str) -> bool:
    try:
        return pwd_context.verify(plain, hashed)
    except Exception:
        return False


# In-memory dev users (email -> {name, roles, password_hash})
_DEV_ADMIN_PASSWORD = os.getenv("DEV_ADMIN_PASSWORD", "Password#1")
_DEV_CONTRIB_PASSWORD = os.getenv("DEV_CONTRIB_PASSWORD", "Password#1")
USERS: Dict[str, Dict[str, object]] = {
    "adam.thacker@expeed.com": {
        "name": "Adam Thacker",
        "roles": ["admin"],
        "password_hash": _hash_password(_DEV_ADMIN_PASSWORD),
    },
    "contrib@example.com": {
        "name": "Contributor User",
        "roles": ["contributor"],
        "password_hash": _hash_password(_DEV_CONTRIB_PASSWORD),
    },
}


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


def authenticate(email: str, password: str) -> Optional[User]:
    rec = USERS.get(email.lower())
    if not rec:
        return None
    if not _verify_password(password, rec.get("password_hash", "")):
        return None
    return User(email=email.lower(), name=str(rec.get("name", email)), roles=list(rec.get("roles", [])))


def register_user(email: str, name: str, password: str, roles: Optional[list[str]] = None) -> User:
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
        "password_hash": _hash_password(password),
    }
    return User(email=email_l, name=name, roles=effective_roles)


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

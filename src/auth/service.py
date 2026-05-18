from __future__ import annotations

import os
import secrets
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional, Tuple

import jwt
from jwt import InvalidTokenError as JWTError
from passlib.context import CryptContext


pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def _get_env_int(name: str, default: int) -> int:
    value = os.getenv(name)
    if value is None:
        return default
    try:
        return int(value)
    except ValueError:
        return default


# Fail fast if JWT_SECRET is missing or too weak — prevents accidental
# deployment with the old hardcoded default "change-me-in-production".
_raw_jwt_secret = os.getenv("JWT_SECRET")
if not _raw_jwt_secret:
    raise RuntimeError(
        "JWT_SECRET environment variable is required. "
        "Generate one with: openssl rand -hex 32"
    )
JWT_SECRET = _raw_jwt_secret
if len(JWT_SECRET.encode()) < 32:
    raise RuntimeError(
        "JWT_SECRET must be at least 32 bytes. "
        "Generate one with: openssl rand -hex 32"
    )

JWT_ALGORITHM = os.getenv("JWT_ALGORITHM", "HS256")
ACCESS_TOKEN_EXPIRE_MINUTES = _get_env_int("ACCESS_TOKEN_EXPIRE_MINUTES", 30)
REFRESH_TOKEN_EXPIRE_DAYS = _get_env_int("REFRESH_TOKEN_EXPIRE_DAYS", 7)


def hash_password(password: str) -> str:
    """Hash a plaintext password using bcrypt."""
    return pwd_context.hash(password)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verify a plaintext password against a hashed password."""
    return pwd_context.verify(plain_password, hashed_password)


def _create_token(
    subject: str,
    token_type: str,
    expires_delta: Optional[timedelta],
    jti: Optional[str] = None,
) -> str:
    now = datetime.now(timezone.utc)
    expire = now + (expires_delta or timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES))
    to_encode: Dict[str, Any] = {
        "sub": subject,
        "type": token_type,
        "iat": int(now.timestamp()),
        "exp": int(expire.timestamp()),
    }
    if jti:
        to_encode["jti"] = jti
    return jwt.encode(to_encode, JWT_SECRET, algorithm=JWT_ALGORITHM)


def create_access_token(subject: str | int, expires_minutes: Optional[int] = None) -> str:
    """Create a short-lived access token for a user."""
    delta = timedelta(minutes=expires_minutes or ACCESS_TOKEN_EXPIRE_MINUTES)
    return _create_token(str(subject), token_type="access", expires_delta=delta)


def create_refresh_token(subject: str | int, expires_days: Optional[int] = None) -> Tuple[str, str]:
    """Create a long-lived refresh token for a user.
    
    Returns (token, jti) where jti is the unique token identifier used
    for revocation and rotation.
    """
    jti = secrets.token_urlsafe(16)
    delta = timedelta(days=expires_days or REFRESH_TOKEN_EXPIRE_DAYS)
    token = _create_token(str(subject), token_type="refresh", expires_delta=delta, jti=jti)
    return token, jti


def decode_token(token: str) -> Dict[str, Any]:
    """
    Decode a JWT and return its payload.

    Raises JWTError on invalid or expired tokens.
    """
    return jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])


def create_token_pair(subject: str | int) -> Dict[str, str]:
    """Convenience helper to create both access and refresh tokens.
    
    Returns {"access_token": ..., "refresh_token": ..., "refresh_jti": ...}
    """
    access = create_access_token(subject)
    refresh, refresh_jti = create_refresh_token(subject)
    return {"access_token": access, "refresh_token": refresh, "refresh_jti": refresh_jti}

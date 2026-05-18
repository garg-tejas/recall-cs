from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, EmailStr


class SignupRequest(BaseModel):
    email: EmailStr
    username: str
    password: str


class LoginRequest(BaseModel):
    email_or_username: str
    password: str


class ClerkLoginRequest(BaseModel):
    clerk_user_id: str
    email: EmailStr
    username: str


class RefreshRequest(BaseModel):
    refresh_token: str


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"


class UserOut(BaseModel):
    id: int
    email: EmailStr
    username: str
    is_active: bool = True

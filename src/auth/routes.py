from __future__ import annotations

import secrets
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.db.models import User
from src.db.session import get_db
from .schemas import (
    ClerkLoginRequest,
    LoginRequest,
    RefreshRequest,
    SignupRequest,
    TokenResponse,
    UserOut,
)
from .service import (
    JWTError,
    create_token_pair,
    decode_token,
    hash_password,
    verify_password,
)
from .dependencies import get_current_active_user


router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/signup", response_model=TokenResponse, status_code=status.HTTP_201_CREATED)
async def signup(
    payload: SignupRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> TokenResponse:
    # Check if email or username already exists
    existing = await db.execute(
        select(User).where(
            or_(
                User.email == payload.email,
                User.username == payload.username,
            )
        )
    )
    if existing.scalar_one_or_none() is not None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Email or username already registered",
        )

    user = User(
        email=payload.email,
        username=payload.username,
        hashed_password=hash_password(payload.password),
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)

    tokens = create_token_pair(user.id)
    return TokenResponse(**tokens)


@router.post("/login", response_model=TokenResponse)
async def login(
    payload: LoginRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> TokenResponse:
    # Find by email or username
    query = select(User).where(
        or_(
            User.email == payload.email_or_username,
            User.username == payload.email_or_username,
        )
    )
    result = await db.execute(query)
    user = result.scalar_one_or_none()

    if user is None or not verify_password(payload.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )

    tokens = create_token_pair(user.id)
    return TokenResponse(**tokens)


@router.post("/clerk", response_model=TokenResponse)
async def clerk_login(
    payload: ClerkLoginRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> TokenResponse:
    """
    Exchange Clerk user credentials for our own JWT token pair.
    Creates a local user if one does not already exist for the given email.
    """
    result = await db.execute(select(User).where(User.email == payload.email))
    user = result.scalar_one_or_none()

    if user is None:
        # Auto-create user from Clerk credentials.
        # Generate a random unusable password since auth is delegated to Clerk.
        random_password = secrets.token_urlsafe(32)
        user = User(
            email=payload.email,
            username=payload.username,
            hashed_password=hash_password(random_password),
        )
        db.add(user)
        await db.commit()
        await db.refresh(user)

    tokens = create_token_pair(user.id)
    return TokenResponse(**tokens)


@router.post("/refresh", response_model=TokenResponse)
async def refresh_token(
    payload: RefreshRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> TokenResponse:
    try:
        token_data = decode_token(payload.refresh_token)
    except JWTError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid refresh token",
            headers={"WWW-Authenticate": "Bearer"},
        )

    if token_data.get("type") != "refresh":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token type",
            headers={"WWW-Authenticate": "Bearer"},
        )

    sub = token_data.get("sub")
    if sub is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token payload",
            headers={"WWW-Authenticate": "Bearer"},
        )

    try:
        user_id = int(sub)
    except (TypeError, ValueError):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token subject",
            headers={"WWW-Authenticate": "Bearer"},
        )

    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if user is None or not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found or inactive",
            headers={"WWW-Authenticate": "Bearer"},
        )

    tokens = create_token_pair(user.id)
    return TokenResponse(**tokens)


@router.get("/me", response_model=UserOut)
async def me(
    current_user: Annotated[User, Depends(get_current_active_user)],
) -> UserOut:
    return UserOut(
        id=current_user.id,
        email=current_user.email,
        username=current_user.username,
        is_active=current_user.is_active,
    )

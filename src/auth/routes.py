from __future__ import annotations

import secrets
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.db.models import User
from src.db.session import get_db
from .clerk_verify import verify_clerk_session_token
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
from src.api.main import limiter


router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/signup", response_model=TokenResponse, status_code=status.HTTP_201_CREATED)
@limiter.limit("5/minute")
async def signup(
    request: Request,
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
    user.refresh_jti = tokens["refresh_jti"]
    await db.commit()
    return TokenResponse(access_token=tokens["access_token"], refresh_token=tokens["refresh_token"])


@router.post("/login", response_model=TokenResponse)
@limiter.limit("10/minute")
async def login(
    request: Request,
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
    user.refresh_jti = tokens["refresh_jti"]
    await db.commit()
    return TokenResponse(access_token=tokens["access_token"], refresh_token=tokens["refresh_token"])


@router.post("/clerk", response_model=TokenResponse)
@limiter.limit("10/minute")
async def clerk_login(
    request: Request,
    payload: ClerkLoginRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> TokenResponse:
    """
    Exchange a verified Clerk session token for our own JWT token pair.
    The session_token is verified against Clerk's JWKS before we trust
    any claims inside it.
    """
    try:
        claims = await verify_clerk_session_token(payload.session_token)
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Invalid Clerk session token: {exc}",
        )

    clerk_user_id = claims.get("sub")
    if not clerk_user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Clerk token missing user identifier",
        )

    # Extract profile info from Clerk claims
    email = claims.get("email") or claims.get("email_address")
    username = claims.get("username") or (email.split("@")[0] if email else "user")
    display_name = claims.get("name") or claims.get("first_name") or claims.get("last_name")
    avatar_url = claims.get("image_url")

    if not email:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Clerk token missing email claim",
        )

    # Lookup by clerk_user_id first
    result = await db.execute(
        select(User).where(User.clerk_user_id == clerk_user_id)
    )
    user = result.scalar_one_or_none()

    if user is None:
        # Fallback: lookup by email
        result = await db.execute(select(User).where(User.email == email))
        user = result.scalar_one_or_none()

    if user is None:
        # Auto-create user from Clerk credentials.
        random_password = secrets.token_urlsafe(32)
        user = User(
            clerk_user_id=clerk_user_id,
            email=email,
            username=username,
            display_name=display_name,
            avatar_url=avatar_url,
            hashed_password=hash_password(random_password),
        )
        db.add(user)
        await db.commit()
        await db.refresh(user)
    else:
        # Sync clerk_user_id and profile fields if they changed
        needs_commit = False
        if user.clerk_user_id != clerk_user_id:
            user.clerk_user_id = clerk_user_id
            needs_commit = True
        if display_name and user.display_name != display_name:
            user.display_name = display_name
            needs_commit = True
        if avatar_url and user.avatar_url != avatar_url:
            user.avatar_url = avatar_url
            needs_commit = True
        if needs_commit:
            await db.commit()
            await db.refresh(user)

    tokens = create_token_pair(user.id)
    user.refresh_jti = tokens["refresh_jti"]
    await db.commit()
    return TokenResponse(access_token=tokens["access_token"], refresh_token=tokens["refresh_token"])


@router.post("/refresh", response_model=TokenResponse)
@limiter.limit("20/minute")
async def refresh_token(
    request: Request,
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
    token_jti = token_data.get("jti")
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

    # Validate stored jti — prevents use of revoked or stolen refresh tokens
    if not user.refresh_jti or user.refresh_jti != token_jti:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Refresh token revoked or invalid",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # Rotate refresh token on every use
    tokens = create_token_pair(user.id)
    user.refresh_jti = tokens["refresh_jti"]
    await db.commit()
    return TokenResponse(access_token=tokens["access_token"], refresh_token=tokens["refresh_token"])


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(
    current_user: Annotated[User, Depends(get_current_active_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> None:
    """Revoke the current user's refresh token by clearing refresh_jti."""
    current_user.refresh_jti = None
    await db.commit()


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

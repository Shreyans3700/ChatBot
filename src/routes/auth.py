import logging
import uuid

import asyncpg
from fastapi import APIRouter, Depends, HTTPException, status

from src.auth import create_access_token, hash_password, verify_password
from src.routes.dependencies import get_db
from src.schema.models import AuthResponse, LoginRequest, SignupRequest, UserResponse

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/auth", tags=["auth"])


async def _create_user(email: str, password: str, db) -> AuthResponse:
    normalized_email = email.strip().lower()
    if not normalized_email:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Email is required",
        )

    password_hash = hash_password(password)
    user_id = str(uuid.uuid4())

    async with db.acquire() as connection:
        try:
            await connection.execute(
                """
                INSERT INTO users (id, email, password_hash)
                VALUES ($1, $2, $3)
                """,
                user_id,
                normalized_email,
                password_hash,
            )
        except asyncpg.exceptions.UniqueViolationError as error:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Email is already registered",
            ) from error

    token = create_access_token(user_id=user_id, email=normalized_email)
    return AuthResponse(
        access_token=token,
        token_type="bearer",
        user=UserResponse(id=user_id, email=normalized_email),
    )


@router.post("/signup", response_model=AuthResponse, status_code=status.HTTP_201_CREATED)
async def signup(request: SignupRequest, db=Depends(get_db)) -> AuthResponse:
    try:
        return await _create_user(request.email, request.password, db)
    except HTTPException:
        raise
    except Exception as error:
        logger.exception("Signup failed")
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Unable to create user",
        ) from error


@router.post("/login", response_model=AuthResponse)
async def login(request: LoginRequest, db=Depends(get_db)) -> AuthResponse:
    normalized_email = request.email.strip().lower()
    try:
        async with db.acquire() as connection:
            row = await connection.fetchrow(
                """
                SELECT id, email, password_hash
                FROM users
                WHERE email = $1
                """,
                normalized_email,
            )

        if row is None or not verify_password(request.password, row["password_hash"]):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid email or password",
            )

        user_id = str(row["id"])
        token = create_access_token(user_id=user_id, email=row["email"])
        return AuthResponse(
            access_token=token,
            token_type="bearer",
            user=UserResponse(id=user_id, email=row["email"]),
        )
    except HTTPException:
        raise
    except Exception as error:
        logger.exception("Login failed")
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Unable to sign in",
        ) from error

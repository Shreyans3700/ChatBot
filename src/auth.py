import os
from fastapi import Header, HTTPException, status


async def verify_api_key(x_api_key: str = Header(...)) -> None:
    expected = os.getenv("AUTH_API_KEY")
    if not expected:
        raise RuntimeError("API_KEY must be configured")
    if x_api_key != expected:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or missing API key",
        )

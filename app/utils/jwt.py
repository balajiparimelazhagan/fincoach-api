from datetime import datetime, timedelta
from typing import Optional
import jwt

from app.config import settings

_REFRESH_TOKEN_TYPE = "refresh"


def create_access_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
    """
    Create a JWT access token.
    
    Args:
        data: Dictionary containing the data to encode in the token (e.g., user_id, email)
        expires_delta: Optional timedelta for token expiration. If None, uses default from settings.
    
    Returns:
        Encoded JWT token string
    """
    to_encode = data.copy()
    
    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(minutes=settings.JWT_ACCESS_TOKEN_EXPIRE_MINUTES)
    
    to_encode.update({"exp": expire, "iat": datetime.utcnow()})
    
    encoded_jwt = jwt.encode(
        to_encode,
        settings.JWT_SECRET_KEY,
        algorithm=settings.JWT_ALGORITHM
    )
    
    return encoded_jwt


def create_refresh_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
    """
    Create a long-lived JWT refresh token.

    The token carries a ``type: refresh`` claim so it cannot be used as an
    access token and vice-versa.
    """
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(days=settings.JWT_REFRESH_TOKEN_EXPIRE_DAYS)

    to_encode.update({"exp": expire, "iat": datetime.utcnow(), "type": _REFRESH_TOKEN_TYPE})

    return jwt.encode(
        to_encode,
        settings.JWT_SECRET_KEY,
        algorithm=settings.JWT_ALGORITHM,
    )


def decode_refresh_token(token: str) -> dict:
    """
    Decode and verify a JWT refresh token.

    Raises:
        jwt.ExpiredSignatureError: Token has expired.
        jwt.InvalidTokenError:     Token is invalid or is not a refresh token.
    """
    payload = jwt.decode(
        token,
        settings.JWT_SECRET_KEY,
        algorithms=[settings.JWT_ALGORITHM],
    )
    if payload.get("type") != _REFRESH_TOKEN_TYPE:
        raise jwt.InvalidTokenError("Not a refresh token")
    return payload


def decode_access_token(token: str) -> dict:
    """
    Decode and verify a JWT access token.
    
    Args:
        token: JWT token string to decode
    
    Returns:
        Decoded token payload as dictionary
    
    Raises:
        jwt.ExpiredSignatureError: If token has expired
        jwt.InvalidTokenError: If token is invalid
    """
    payload = jwt.decode(
        token,
        settings.JWT_SECRET_KEY,
        algorithms=[settings.JWT_ALGORITHM]
    )
    return payload


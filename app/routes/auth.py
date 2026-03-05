from fastapi import APIRouter, HTTPException, Query, Depends, Request
from fastapi.responses import RedirectResponse, JSONResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from google.auth.transport.requests import Request as GoogleRequest
from google.oauth2 import id_token
from urllib.parse import urlencode, quote
import uuid
import json
import secrets
import hashlib
import base64
import requests
from datetime import datetime, timedelta

from app.config import settings
from app.dependencies import get_db
from app.models.user import User
from app.logging_config import get_logger
from app.utils.jwt import create_access_token

logger = get_logger(__name__)

router = APIRouter(prefix="/auth", tags=["auth"])

# OAuth 2.0 scopes
SCOPES = [
    'openid',
    'https://www.googleapis.com/auth/userinfo.profile',
    'https://www.googleapis.com/auth/userinfo.email',
    'https://www.googleapis.com/auth/gmail.readonly'
]


def create_pkce():
    """Generate PKCE code verifier and challenge."""
    verifier = secrets.token_urlsafe(64)
    challenge = base64.urlsafe_b64encode(
        hashlib.sha256(verifier.encode()).digest()
    ).decode().rstrip("=")
    return verifier, challenge


def encode_state_with_pkce(verifier: str) -> str:
    """
    Encode PKCE verifier into state parameter using JWT.
    This makes the flow stateless - no session needed.
    """
    import jwt
    
    payload = {
        "verifier": verifier,
        "iat": datetime.utcnow(),
        "exp": datetime.utcnow() + timedelta(minutes=10)
    }
    
    token = jwt.encode(
        payload,
        settings.JWT_SECRET_KEY,
        algorithm=settings.JWT_ALGORITHM
    )
    
    return token


def decode_state_with_pkce(state: str) -> str:
    """
    Decode PKCE verifier from state parameter.
    Returns the verifier if valid, raises exception if invalid.
    """
    import jwt
    
    try:
        payload = jwt.decode(
            state,
            settings.JWT_SECRET_KEY,
            algorithms=[settings.JWT_ALGORITHM]
        )
        return payload.get("verifier")
    except jwt.ExpiredSignatureError:
        raise ValueError("State token has expired")
    except jwt.InvalidTokenError as e:
        raise ValueError(f"Invalid state token: {str(e)}")


@router.get("/google/signin")
async def google_signin():
    """
    Initiates Google OAuth sign-in flow with PKCE.
    Uses stateless approach - encodes verifier in state parameter.
    """
    if not settings.GOOGLE_CLIENT_ID or not settings.GOOGLE_CLIENT_SECRET:
        raise HTTPException(
            status_code=500,
            detail="Google OAuth credentials not configured"
        )

    # Generate PKCE verifier and challenge
    verifier, challenge = create_pkce()
    
    # Encode verifier into state (stateless - no session needed)
    state = encode_state_with_pkce(verifier)
    
    # Format scopes for URL
    scope_param = "+".join(SCOPES)

    # Build authorization URL with PKCE parameters
    auth_url = (
        "https://accounts.google.com/o/oauth2/v2/auth?"
        f"client_id={settings.GOOGLE_CLIENT_ID}&"
        f"redirect_uri={settings.GOOGLE_REDIRECT_URI}&"
        "response_type=code&"
        f"scope={scope_param}&"
        "access_type=offline&"
        "include_granted_scopes=true&"
        "prompt=consent&"
        f"code_challenge={challenge}&"
        "code_challenge_method=S256&"
        f"state={quote(state, safe='')}"
    )

    logger.info("Initiated OAuth signin flow with PKCE")
    return {"authorization_url": auth_url, "state": state}


@router.get("/google/callback")
async def google_callback(
    code: str = Query(..., description="Authorization code from Google"),
    state: str = Query(None, description="State parameter with encoded PKCE verifier"),
    db: AsyncSession = Depends(get_db)
):
    """
    Handles Google OAuth callback.
    Decodes PKCE verifier from state and exchanges code for tokens.
    Completely stateless - no session required.
    """
    if not settings.GOOGLE_CLIENT_ID or not settings.GOOGLE_CLIENT_SECRET:
        raise HTTPException(
            status_code=500,
            detail="Google OAuth credentials not configured"
        )

    try:
        # Decode verifier from state parameter (stateless)
        verifier = decode_state_with_pkce(state)
        
        if not verifier:
            logger.error("Failed to decode PKCE verifier from state")
            raise HTTPException(
                status_code=400,
                detail="Invalid state parameter"
            )
        
        logger.info("Successfully decoded PKCE verifier from state")

        # Exchange authorization code for tokens using PKCE verifier
        token_response = requests.post(
            "https://oauth2.googleapis.com/token",
            data={
                "client_id": settings.GOOGLE_CLIENT_ID,
                "client_secret": settings.GOOGLE_CLIENT_SECRET,
                "code": code,
                "grant_type": "authorization_code",
                "redirect_uri": settings.GOOGLE_REDIRECT_URI,
                "code_verifier": verifier,  # ⭐ PKCE verifier from state
            },
        )
        
        if token_response.status_code != 200:
            error_data = token_response.json()
            logger.error(f"Token exchange failed: {error_data}")
            raise HTTPException(
                status_code=400,
                detail=f"Token exchange failed: {error_data.get('error_description', 'Unknown error')}"
            )
        
        token_data = token_response.json()
        logger.info("Successfully exchanged authorization code for tokens")
        
        # Verify ID token and extract user info
        google_request = GoogleRequest()
        id_info = id_token.verify_oauth2_token(
            token_data["id_token"],
            google_request,
            settings.GOOGLE_CLIENT_ID,
            clock_skew_in_seconds=10
        )

        # Extract user information
        google_id = id_info.get('sub')
        email = id_info.get('email')
        name = id_info.get('name')
        picture = id_info.get('picture')

        if not google_id or not email:
            raise HTTPException(
                status_code=400,
                detail="Failed to retrieve user information from Google"
            )

        # Extract tokens
        access_token = token_data.get("access_token")
        refresh_token = token_data.get("refresh_token")
        token_expiry = None
        if "expires_in" in token_data:
            token_expiry = datetime.utcnow() + timedelta(seconds=token_data["expires_in"])

        # Check if user exists and create if not exists using ORM
        try:
            result = await db.execute(
                select(User).where(User.google_id == google_id)
            )
            existing_user = result.scalar_one_or_none()
        except Exception as db_error:
            logger.error(f"Database error: {db_error}")
            raise HTTPException(
                status_code=500,
                detail=f"Database error: {str(db_error)}"
            )

        if existing_user:
            # Update existing user with new tokens
            existing_user.access_token = access_token
            existing_user.refresh_token = refresh_token
            existing_user.token_expiry = token_expiry
            existing_user.name = name
            existing_user.picture = picture
            existing_user.google_credentials_json = json.dumps(token_data)
            
            await db.commit()
            await db.refresh(existing_user)
            jwt_token = create_access_token(
                data={"sub": str(existing_user.id), "email": existing_user.email}
            )
            
            logger.info(f"Existing user authenticated: {email}")
            redirect_url = f"{settings.FRONTEND_BASE_URL}{settings.FRONTEND_LOGIN_REDIRECT_PATH}?{urlencode({'token': jwt_token})}"
            return RedirectResponse(url=redirect_url)

        # Create new user
        new_user = User(
            id=str(uuid.uuid4()),
            email=email,
            name=name,
            google_id=google_id,
            picture=picture,
            access_token=access_token,
            refresh_token=refresh_token,
            token_expiry=token_expiry,
            google_credentials_json=json.dumps(token_data)
        )
        
        db.add(new_user)
        await db.commit()
        await db.refresh(new_user)

        # Create JWT token for new user
        jwt_token = create_access_token(
            data={"sub": str(new_user.id), "email": new_user.email}
        )

        logger.info(f"New user created: {email}")
        
        # Trigger initial email sync with monthly batching (3 months)
        try:
            from app.celery.celery_tasks import fetch_user_emails_initial
            fetch_user_emails_initial.delay(str(new_user.id), 3)
            logger.info(f"Triggered initial email sync for new user: {email}")
        except Exception as sync_error:
            logger.error(f"Failed to trigger initial email sync: {sync_error}")
        
        redirect_url = f"{settings.FRONTEND_BASE_URL}{settings.FRONTEND_LOGIN_REDIRECT_PATH}?{urlencode({'token': jwt_token})}"
        return RedirectResponse(url=redirect_url)

    except ValueError as e:
        logger.error(f"State decoding error: {e}")
        raise HTTPException(status_code=400, detail=f"Invalid state: {str(e)}")
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error during Google callback: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Authentication failed: {str(e)}")


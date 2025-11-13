from fastapi import APIRouter, HTTPException, Query
from sqlalchemy import select
from google.auth.transport.requests import Request
from google.oauth2 import id_token
from google_auth_oauthlib.flow import Flow
import uuid

from app.config import settings
from app.db import AsyncSessionLocal
from app.models.user import User
from app.logging_config import get_logger

logger = get_logger(__name__)

router = APIRouter(prefix="/auth", tags=["auth"])

# OAuth 2.0 scopes
SCOPES = ['openid', 'https://www.googleapis.com/auth/userinfo.profile', 'https://www.googleapis.com/auth/userinfo.email']


@router.get("/google/signin")
async def google_signin():
    """
    Initiates Google OAuth sign-in flow.
    Returns a redirect URL to Google's authorization page.
    """
    if not settings.GOOGLE_CLIENT_ID or not settings.GOOGLE_CLIENT_SECRET:
        raise HTTPException(
            status_code=500,
            detail="Google OAuth credentials not configured"
        )

    flow = Flow.from_client_config(
        {
            "web": {
                "client_id": settings.GOOGLE_CLIENT_ID,
                "client_secret": settings.GOOGLE_CLIENT_SECRET,
                "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                "token_uri": "https://oauth2.googleapis.com/token",
                "redirect_uris": [settings.GOOGLE_REDIRECT_URI]
            }
        },
        scopes=SCOPES,
        redirect_uri=settings.GOOGLE_REDIRECT_URI
    )

    authorization_url, state = flow.authorization_url(
        access_type='offline',
        include_granted_scopes='true',
        prompt='consent'
    )

    return {"authorization_url": authorization_url, "state": state}


@router.get("/google/callback")
async def google_callback(
    code: str = Query(..., description="Authorization code from Google"),
    state: str = Query(None, description="State parameter for CSRF protection")
):
    """
    Handles Google OAuth callback.
    Exchanges authorization code for tokens, fetches user info, and creates user if not exists.
    """
    if not settings.GOOGLE_CLIENT_ID or not settings.GOOGLE_CLIENT_SECRET:
        raise HTTPException(
            status_code=500,
            detail="Google OAuth credentials not configured"
        )

    try:
        flow = Flow.from_client_config(
            {
                "web": {
                    "client_id": settings.GOOGLE_CLIENT_ID,
                    "client_secret": settings.GOOGLE_CLIENT_SECRET,
                    "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                    "token_uri": "https://oauth2.googleapis.com/token",
                    "redirect_uris": [settings.GOOGLE_REDIRECT_URI]
                }
            },
            scopes=SCOPES,
            redirect_uri=settings.GOOGLE_REDIRECT_URI
        )

        # Exchange authorization code for tokens
        flow.fetch_token(code=code)

        # Get user info from ID token
        credentials = flow.credentials
        request = Request()
        id_info = id_token.verify_oauth2_token(
            credentials.id_token, 
            request, 
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

        # Extract tokens from credentials
        access_token = credentials.token
        refresh_token = credentials.refresh_token
        token_expiry = credentials.expiry

        # Check if user exists and create if not exists using ORM
        async with AsyncSessionLocal() as session:
            try:
                # Check if user exists
                result = await session.execute(
                    select(User).where(User.google_id == google_id)
                )
                existing_user = result.scalar_one_or_none()
            except Exception as db_error:
                logger.error(f"Database error - columns might not exist. Run migration: {db_error}")
                raise HTTPException(
                    status_code=500,
                    detail=f"Database schema error. Please run migrations: {str(db_error)}"
                )

            if existing_user:
                # Update existing user with new tokens
                existing_user.access_token = access_token
                existing_user.refresh_token = refresh_token
                existing_user.token_expiry = token_expiry
                existing_user.name = name
                existing_user.picture = picture
                
                await session.commit()
                await session.refresh(existing_user)
                
                logger.info(f"User already exists, tokens updated: {email}")
                return {
                    "message": "User already exists, tokens updated",
                    "user_id": existing_user.id,
                    "email": existing_user.email
                }

            # Create new user using model
            new_user = User(
                id=str(uuid.uuid4()),
                email=email,
                name=name,
                google_id=google_id,
                picture=picture,
                access_token=access_token,
                refresh_token=refresh_token,
                token_expiry=token_expiry
            )
            
            session.add(new_user)
            await session.commit()
            await session.refresh(new_user)

            logger.info(f"New user created with tokens: {email}")
            return {
                "message": "User created successfully",
                "user_id": new_user.id,
                "email": new_user.email
            }

    except ValueError as e:
        logger.error(f"Token verification failed: {e}")
        raise HTTPException(status_code=400, detail="Invalid token")
    except Exception as e:
        logger.error(f"Error during Google callback: {e}")
        raise HTTPException(status_code=500, detail=f"Authentication failed: {str(e)}")


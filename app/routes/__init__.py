from fastapi import APIRouter

api_router = APIRouter()

# Import route modules here
from app.routes import auth

api_router.include_router(auth.router)


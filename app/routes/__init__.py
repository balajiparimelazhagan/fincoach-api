from fastapi import APIRouter

api_router = APIRouter()

# Import route modules here
from app.routes import auth, transactors, categories

api_router.include_router(auth.router)
api_router.include_router(transactors.router)
api_router.include_router(categories.router)


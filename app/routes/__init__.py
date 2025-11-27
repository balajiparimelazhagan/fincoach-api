from fastapi import APIRouter

api_router = APIRouter()

# Import route modules here
from app.routes import auth, transactors, categories, users, email_sync, transactions

api_router.include_router(auth.router)
api_router.include_router(transactors.router)
api_router.include_router(categories.router)
api_router.include_router(users.router)
api_router.include_router(email_sync.router)
api_router.include_router(transactions.router)


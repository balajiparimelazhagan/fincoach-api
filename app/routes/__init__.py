from fastapi import APIRouter

api_router = APIRouter()

# Import route modules here
from app.routes import auth, transactors, categories, users, email_transaction_sync, transactions, sms_transaction_sync, user_preferences, analytics, accounts, patterns

api_router.include_router(auth.router)
api_router.include_router(transactors.router)
api_router.include_router(categories.router)
api_router.include_router(users.router)
api_router.include_router(email_transaction_sync.router)
api_router.include_router(sms_transaction_sync.router)
api_router.include_router(transactions.router)
api_router.include_router(accounts.router)
api_router.include_router(user_preferences.router)
api_router.include_router(analytics.router)
api_router.include_router(patterns.router)


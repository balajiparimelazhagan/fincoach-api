from fastapi import FastAPI, Request, status
from fastapi.responses import JSONResponse
from starlette.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
import asyncio
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.executors.asyncio import AsyncIOExecutor

from app.config import settings
from app.db import database
from app.exceptions import AppException
from app.routes import api_router
from app.logging_config import setup_logging, get_logger
from app.middleware.logging_middleware import LoggingMiddleware
from app.mail.fetch_and_parse import fetch_and_parse_all_users_emails

# Setup logging
setup_logging(settings.LOG_LEVEL)
logger = get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    try:
        logger.info("Starting up...")
        from app.db import connect_with_retry
        await connect_with_retry()

        # Initialize and start the scheduler
        scheduler = AsyncIOScheduler()
        # remove max_emails from kwargs for production
        scheduler.add_job(fetch_and_parse_all_users_emails, 'interval', minutes=10, kwargs={'max_emails': 10})
        scheduler.start()
        logger.info("Scheduler started. Fetching emails for all users every 10 minutes and saving to DB.")
        
        yield
    finally:
        logger.info("Shutting down...")
        if 'scheduler' in locals() and scheduler.running:
            scheduler.shutdown()
            logger.info("Scheduler shut down.")
        await database.disconnect()


app = FastAPI(
    title="FinCoach API",
    description="Financial coaching API",
    version="1.0.0",
    lifespan=lifespan
)

# Logging middleware
app.add_middleware(LoggingMiddleware)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["DELETE", "GET", "POST", "PUT"],
    allow_headers=["*"],
)

# Global exception handler
@app.exception_handler(AppException)
async def app_exception_handler(request: Request, exc: AppException):
    return JSONResponse(
        status_code=exc.status_code,
        content={"detail": exc.detail}
    )


# Include routers
app.include_router(api_router, prefix="/api/v1")


@app.get("/health")
async def health():
    from app.db import check_database_connection
    db_status = await check_database_connection()
    return {
        "status": "ok" if db_status else "degraded",
        "database": "connected" if db_status else "disconnected"
    }

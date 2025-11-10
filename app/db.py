import asyncio
from sqlalchemy import create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.pool import QueuePool
from databases import Database

from app.config import settings
from app.logging_config import get_logger

logger = get_logger(__name__)

# SQLAlchemy Base for models
Base = declarative_base()

# SQLAlchemy engine with connection pooling
engine = create_engine(
    settings.DATABASE_URL,
    poolclass=QueuePool,
    pool_size=10,
    max_overflow=20,
    pool_pre_ping=True,
    echo=False
)

# Async database instance for FastAPI
database = Database(
    settings.DATABASE_URL,
    min_size=5,
    max_size=20
)


async def check_database_connection() -> bool:
    """Check if database connection is healthy"""
    try:
        await database.fetch_one("SELECT 1")
        return True
    except Exception as e:
        logger.error(f"Database connection check failed: {e}")
        return False


async def connect_with_retry(max_retries: int = 3, delay: float = 1.0):
    """Connect to database with retry logic"""
    for attempt in range(max_retries):
        try:
            await database.connect()
            logger.info("Database connected successfully")
            return True
        except Exception as e:
            logger.warning(f"Database connection attempt {attempt + 1} failed: {e}")
            if attempt < max_retries - 1:
                await asyncio.sleep(delay)
            else:
                logger.error("Failed to connect to database after all retries")
                raise
    return False
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.pool import NullPool
from app.config import settings

# NullPool: no connection reuse. Each session creates a fresh asyncpg connection
# bound to the current event loop, avoiding the "Future attached to a different loop"
# error that occurs when Celery prefork workers inherit the parent's pooled connections.
celery_async_engine = create_async_engine(
    settings.DATABASE_URL.replace("postgresql://", "postgresql+asyncpg://"),
    poolclass=NullPool,
    echo=False,
)

CeleryAsyncSessionLocal = async_sessionmaker(
    celery_async_engine,
    class_=AsyncSession,
    expire_on_commit=False,
)

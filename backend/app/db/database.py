from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
from neo4j import AsyncGraphDatabase
import redis.asyncio as redis
from app.core.config import settings

# Modify the DATABASE_URL to use asyncpg for SQLAlchemy async engine
# Example: postgresql:// -> postgresql+asyncpg://
async_db_url = settings.DATABASE_URL.replace("postgresql://", "postgresql+asyncpg://")

# PostgreSQL Engine
engine = create_async_engine(
    async_db_url,
    echo=False,
    future=True,
    pool_size=10,
    max_overflow=20
)

# Async Session Factory
AsyncSessionLocal = async_sessionmaker(
    bind=engine, 
    expire_on_commit=False, 
    autoflush=False
)

# Neo4j Driver
try:
    neo4j_driver = AsyncGraphDatabase.driver(
        settings.NEO4J_URI, 
        auth=(settings.NEO4J_USER, settings.NEO4J_PASSWORD)
    )
except Exception:
    neo4j_driver = None

# Redis Client
try:
    import redis.asyncio as redis
    redis_client = redis.from_url(settings.REDIS_URL, decode_responses=True)
except Exception:
    redis_client = None

async def get_db():
    """FastAPI Dependency for PostgreSQL Sessions"""
    async with AsyncSessionLocal() as session:
        yield session

async def close_connections():
    """Graceful shutdown for DB connections"""
    await engine.dispose()
    if neo4j_driver:
        await neo4j_driver.close()
    if redis_client:
        await redis_client.aclose()

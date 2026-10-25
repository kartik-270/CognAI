from fastapi import FastAPI
from contextlib import asynccontextmanager
from sqlalchemy import text
from app.core.config import settings
from app.db.database import close_connections, engine
from app.db.models import Base
from app.api import auth
from app.api.routes import chat, memory, persona

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup: Initialize the DB schema (in a production system, use Alembic migrations instead)
    async with engine.begin() as conn:
        # Create pgvector extension if it doesn't exist
        await conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
        await conn.run_sync(Base.metadata.create_all)
        await conn.execute(text("ALTER TABLE chat_messages ADD COLUMN IF NOT EXISTS attachments JSON"))
    yield
    # Shutdown: Close database connections gracefully
    await close_connections()

app = FastAPI(
    title=settings.PROJECT_NAME,
    description="CognAI: A Research-Grounded Cognitive Companion",
    lifespan=lifespan
)

from fastapi.middleware.cors import CORSMiddleware

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router)
app.include_router(chat.router)
app.include_router(memory.router)
app.include_router(persona.router)


@app.get("/health")
async def health_check():
    return {"status": "healthy", "project": settings.PROJECT_NAME}

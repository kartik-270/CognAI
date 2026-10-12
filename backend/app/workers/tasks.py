from app.workers.celery_app import celery_app
from app.core.config import settings
from app.db.models import Episode, PermanentMemory, Goal, PersonaProfile, User, ChatMessage, DocumentAttachment
from app.services.storage import get_storage_service
from app.memory.episodic import EpisodicMemoryManager
from app.memory.consolidation import MemoryConsolidator
from app.graph.neo4j_client import neo4j_client
from sqlalchemy import select, delete, update
from sqlalchemy.pool import NullPool
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
import asyncio
import logging

logger = logging.getLogger(__name__)

from datetime import datetime
from typing import Optional

# Dedicated NullPool async engine for Celery tasks.
# Celery worker processes execute tasks within individual asyncio.run() event loops.
# NullPool ensures connections are created and closed within each specific task's event loop,
# preventing asyncpg "another operation is in progress" InterfaceErrors and cross-process connection pool sharing.
_worker_db_url = settings.DATABASE_URL.replace("postgresql://", "postgresql+asyncpg://")
_worker_engine = create_async_engine(
    _worker_db_url,
    poolclass=NullPool,
    echo=False,
    future=True,
)
WorkerAsyncSessionLocal = async_sessionmaker(
    bind=_worker_engine,
    expire_on_commit=False,
    autoflush=False
)

async def _async_consolidate(user_id: str, session_id: str, transcript: str, turn_count: int, session_timestamp: Optional[datetime] = None):
    async with WorkerAsyncSessionLocal() as db:
        # 1. Store episodic memory, compute surprise and emotional valence/intensity
        episodic_mgr = EpisodicMemoryManager(db)
        episode = await episodic_mgr.record_episode(
            user_id=user_id,
            session_id=session_id,
            transcript=transcript,
            turn_count=turn_count,
            session_timestamp=session_timestamp
        )

        # 2. Consolidate facts with contradiction detection (MemoryConflictResolver)
        consolidator = MemoryConsolidator(db)
        cons_result = await consolidator.consolidate_session(
            user_id=user_id,
            session_id=session_id,
            transcript=transcript,
            surprise_score=episode.surprise_score
        )

        # 3. Increment session count for user
        stmt = select(User).where(User.id == user_id)
        u_res = await db.execute(stmt)
        user = u_res.scalars().first()
        if user:
            user.session_count = (user.session_count or 0) + 1
            await db.commit()

        # 4. If session count >= 5, run HDBSCAN clustering
        clustering_result = None
        if user and user.session_count >= 5:
            clustering_result = await consolidator.run_hdbscan_clustering(user_id)

        return {
            "episode_id": str(episode.id),
            "surprise_score": episode.surprise_score,
            "emotional_valence": episode.emotional_valence,
            "emotional_intensity": episode.emotional_intensity,
            "consolidation": cons_result,
            "clustering": clustering_result
        }


@celery_app.task(bind=True, rate_limit='10/m', max_retries=3, default_retry_delay=60)
def consolidate_session_task(self, user_id: str, session_id: str, transcript: str, turn_count: int, session_timestamp: Optional[datetime] = None):
    """
    Background consolidation worker task.
    Enforces strict rate_limit='10/m' decorator to protect LLM API quotas.
    Consolidates episodic memory, emotional valence, surprise score, and contradiction detection.
    """
    try:
        result = asyncio.run(_async_consolidate(user_id, session_id, transcript, turn_count, session_timestamp=session_timestamp))
        logger.info(f"Consolidation task succeeded for user {user_id}, session {session_id}")
        return result
    except Exception as exc:
        logger.error(f"Consolidation task failed for user {user_id}: {exc}")
        raise self.retry(exc=exc)


async def _async_cascade_delete(user_id: str):
    async with WorkerAsyncSessionLocal() as db:
        logger.info(f"Executing Phase 2 cascading delete for user {user_id}")
        
        # 1. Delete all PostgreSQL records strictly scoped by user_id
        await db.execute(delete(Episode).where(Episode.user_id == user_id))
        await db.execute(delete(PermanentMemory).where(PermanentMemory.user_id == user_id))
        await db.execute(delete(Goal).where(Goal.user_id == user_id))
        await db.execute(delete(PersonaProfile).where(PersonaProfile.user_id == user_id))
        await db.execute(delete(ChatMessage).where(ChatMessage.user_id == user_id))
        await db.execute(delete(DocumentAttachment).where(DocumentAttachment.user_id == user_id))
        
        # 2. Delete from Neo4j graph strictly scoped by user_id
        await neo4j_client.delete_user_graph_data(user_id)

        # 3. Purge all attachment files from storage (local or S3)
        storage_service = get_storage_service()
        await storage_service.delete_user_files(user_id)
        
        # 4. Permanently remove user record from database
        await db.execute(delete(User).where(User.id == user_id))
        await db.commit()
        
        logger.info(f"Cascading delete fully completed for user {user_id}")
        return True


@celery_app.task(bind=True, max_retries=5, default_retry_delay=30)
def cascade_delete_user_task(self, user_id: str):
    """
    Phase 2 of two-phase /forget-me compliance.
    Purges all episodic, permanent, goal, persona, and graph records across PostgreSQL and Neo4j.
    Uses retries to guarantee no partial deletion states occur.
    """
    try:
        res = asyncio.run(_async_cascade_delete(user_id))
        return {"status": "purged", "user_id": user_id}
    except Exception as exc:
        logger.error(f"Cascade delete task failed for user {user_id}, retrying: {exc}")
        raise self.retry(exc=exc)

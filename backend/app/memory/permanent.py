from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update, delete
from typing import List, Optional, Dict, Any
from datetime import datetime, timezone
import uuid

from app.db.models import PermanentMemory, Goal
from app.llm.router import llm_router

class PermanentMemoryManager:
    """
    Manages long-term semantic facts and explicit user goals
    with strict row-level isolation for user_id.
    """
    def __init__(self, db: AsyncSession):
        self.db = db

    async def add_fact(
        self,
        user_id: str,
        fact: str,
        category: str = "fact",
        confidence: float = 1.0
    ) -> PermanentMemory:
        """Stores a new consolidated fact with a 1024-dim embedding."""
        embedding = await llm_router.embed(fact)
        memory = PermanentMemory(
            user_id=user_id,
            fact=fact,
            category=category,
            confidence=confidence,
            embedding=embedding,
            access_count=1,
            last_accessed_at=datetime.now(timezone.utc)
        )
        self.db.add(memory)
        await self.db.commit()
        await self.db.refresh(memory)
        return memory

    async def get_user_facts(self, user_id: str, limit: int = 50) -> List[PermanentMemory]:
        """Strict row-level retrieval of permanent facts for user_id."""
        stmt = select(PermanentMemory).where(
            PermanentMemory.user_id == user_id
        ).order_by(PermanentMemory.last_accessed_at.desc()).limit(limit)
        result = await self.db.execute(stmt)
        return list(result.scalars().all())

    async def update_fact_access(self, memory_id: uuid.UUID, user_id: str):
        """Touch last_accessed_at and increment access count with strict user_id check."""
        stmt = update(PermanentMemory).where(
            PermanentMemory.id == memory_id,
            PermanentMemory.user_id == user_id
        ).values(
            access_count=PermanentMemory.access_count + 1,
            last_accessed_at=datetime.now(timezone.utc)
        )
        await self.db.execute(stmt)
        await self.db.commit()

    async def set_goal(
        self,
        user_id: str,
        title: str,
        description: Optional[str] = None,
        status: str = "active"
    ) -> Goal:
        """Inserts or updates an active user goal with vector(1024) embedding."""
        text_to_embed = f"{title}: {description or ''}".strip()
        embedding = await llm_router.embed(text_to_embed)
        
        goal = Goal(
            user_id=user_id,
            title=title,
            description=description,
            status=status,
            embedding=embedding
        )
        self.db.add(goal)
        await self.db.commit()
        await self.db.refresh(goal)
        return goal

    async def get_active_goals(self, user_id: str) -> List[Goal]:
        """Strict row-level retrieval of active goals."""
        stmt = select(Goal).where(
            Goal.user_id == user_id,
            Goal.status == "active"
        ).order_by(Goal.updated_at.desc())
        result = await self.db.execute(stmt)
        return list(result.scalars().all())

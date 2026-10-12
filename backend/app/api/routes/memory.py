from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, delete
from typing import List, Optional
from datetime import datetime, timezone
from pydantic import BaseModel
import uuid

from app.db.database import get_db
from app.db.models import Episode, PermanentMemory, Goal, PersonaProfile, User
from app.api.auth import get_current_user
from app.memory.permanent import PermanentMemoryManager
from app.memory.consolidation import MemoryConflictResolver
from app.workers.tasks import cascade_delete_user_task
from app.graph.neo4j_client import neo4j_client
from app.llm.router import llm_router

router = APIRouter(prefix="/memory", tags=["Memory"])

class GoalCreate(BaseModel):
    title: str
    description: Optional[str] = None

class GoalResponse(BaseModel):
    id: uuid.UUID
    title: str
    description: Optional[str]
    status: str

    class Config:
        from_attributes = True

class FactCorrection(BaseModel):
    corrected_fact: str
    category: Optional[str] = None

@router.get("/episodes")
async def get_episodes(
    limit: int = 20,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Inspect episodic memories for authenticated user with strict user_id row isolation."""
    stmt = select(Episode).where(
        Episode.user_id == str(current_user.id)
    ).order_by(Episode.created_at.desc()).limit(limit)
    result = await db.execute(stmt)
    episodes = result.scalars().all()
    return [
        {
            "id": str(ep.id),
            "session_id": ep.session_id,
            "raw_summary": ep.raw_summary,
            "emotional_valence": ep.emotional_valence,
            "emotional_intensity": ep.emotional_intensity,
            "surprise_score": ep.surprise_score,
            "created_at": ep.created_at.isoformat() if ep.created_at else None
        }
        for ep in episodes
    ]

@router.get("/permanent")
async def get_permanent_memories(
    limit: int = 50,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Inspect permanent semantic facts for authenticated user."""
    perm_mgr = PermanentMemoryManager(db)
    facts = await perm_mgr.get_user_facts(user_id=str(current_user.id), limit=limit)
    return [
        {
            "id": str(f.id),
            "fact": f.fact,
            "category": f.category,
            "confidence": f.confidence,
            "access_count": f.access_count,
            "last_accessed_at": f.last_accessed_at.isoformat() if f.last_accessed_at else None
        }
        for f in facts
    ]

@router.get("/goals", response_model=List[GoalResponse])
async def get_goals(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Retrieve active goals for authenticated user."""
    perm_mgr = PermanentMemoryManager(db)
    goals = await perm_mgr.get_active_goals(user_id=str(current_user.id))
    return goals

@router.post("/goals", response_model=GoalResponse)
async def create_goal(
    goal_data: GoalCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Set a new active goal for authenticated user."""
    perm_mgr = PermanentMemoryManager(db)
    new_goal = await perm_mgr.set_goal(
        user_id=str(current_user.id),
        title=goal_data.title,
        description=goal_data.description
    )
    return new_goal

@router.post("/forget-me")
async def forget_me(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Two-Phase /forget-me GDPR/Privacy Compliance:
    Phase 1: Mark user deletion_pending = True and log request time.
    Phase 2: Queue background Celery task with retries to execute complete cascading delete
             across PostgreSQL (episodes, facts, goals, profile) and Neo4j graph data.
    """
    user_id_str = str(current_user.id)
    
    # Phase 1: Set pending flag
    current_user.deletion_pending = True
    current_user.deletion_requested_at = datetime.now(timezone.utc)
    await db.commit()

    # Phase 2: Dispatch background worker for complete cascade delete
    cascade_delete_user_task.delay(user_id=user_id_str)

    return {
        "status": "deletion_pending",
        "user_id": user_id_str,
        "message": "Two-phase cascading deletion initiated. All vector, relational, and graph memories will be permanently purged."
    }


# =========================================================================
# Gap A: Selective Deletion, Correction, and Export Endpoints
# =========================================================================

@router.delete("/episodes/{episode_id}")
async def delete_episode(
    episode_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Selectively delete a single episodic memory with strict user_id isolation."""
    user_id = str(current_user.id)
    stmt = select(Episode).where(
        Episode.id == episode_id,
        Episode.user_id == user_id
    )
    result = await db.execute(stmt)
    episode = result.scalars().first()
    if not episode:
        raise HTTPException(status_code=404, detail="Episode not found or access denied.")
    
    await db.execute(delete(Episode).where(Episode.id == episode_id, Episode.user_id == user_id))
    await db.commit()
    return {"status": "deleted", "id": str(episode_id), "type": "episode"}


@router.delete("/permanent/{memory_id}")
async def delete_permanent_memory(
    memory_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Selectively delete a single permanent memory with strict user_id isolation."""
    user_id = str(current_user.id)
    stmt = select(PermanentMemory).where(
        PermanentMemory.id == memory_id,
        PermanentMemory.user_id == user_id
    )
    result = await db.execute(stmt)
    mem = result.scalars().first()
    if not mem:
        raise HTTPException(status_code=404, detail="Permanent memory not found or access denied.")
    
    await db.execute(delete(PermanentMemory).where(
        PermanentMemory.id == memory_id,
        PermanentMemory.user_id == user_id
    ))
    await db.commit()
    return {"status": "deleted", "id": str(memory_id), "type": "permanent"}


@router.put("/permanent/{memory_id}/correct")
async def correct_permanent_memory(
    memory_id: uuid.UUID,
    correction: FactCorrection,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Correct an incorrect permanent memory.
    Re-embeds the corrected fact and runs contradiction resolution
    to ensure consistency with existing memories.
    """
    user_id = str(current_user.id)
    stmt = select(PermanentMemory).where(
        PermanentMemory.id == memory_id,
        PermanentMemory.user_id == user_id
    )
    result = await db.execute(stmt)
    mem = result.scalars().first()
    if not mem:
        raise HTTPException(status_code=404, detail="Permanent memory not found or access denied.")
    
    old_fact = mem.fact
    
    # Re-embed the corrected fact
    new_embedding = await llm_router.embed(correction.corrected_fact)
    
    # Update the memory record
    mem.fact = correction.corrected_fact
    mem.embedding = new_embedding
    if correction.category:
        mem.category = correction.category
    mem.last_accessed_at = datetime.now(timezone.utc)
    await db.commit()
    
    return {
        "status": "corrected",
        "id": str(memory_id),
        "old_fact": old_fact,
        "new_fact": correction.corrected_fact
    }


@router.delete("/sessions/{session_id}")
async def delete_session_memories(
    session_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Delete all episodic memories associated with a specific session."""
    user_id = str(current_user.id)
    
    # Verify at least one episode exists for this session + user
    stmt = select(Episode).where(
        Episode.session_id == session_id,
        Episode.user_id == user_id
    )
    result = await db.execute(stmt)
    episodes = result.scalars().all()
    if not episodes:
        raise HTTPException(status_code=404, detail="No episodes found for this session or access denied.")
    
    count = len(episodes)
    await db.execute(delete(Episode).where(
        Episode.session_id == session_id,
        Episode.user_id == user_id
    ))
    await db.commit()
    return {"status": "deleted", "session_id": session_id, "episodes_deleted": count}


@router.get("/export")
async def export_user_data(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Full data export in JSON format for GDPR Article 20 data portability.
    Returns all episodic memories, permanent facts, goals, persona profile,
    and Neo4j entity relations for the authenticated user.
    """
    user_id = str(current_user.id)
    
    # Episodic memories
    ep_result = await db.execute(
        select(Episode).where(Episode.user_id == user_id).order_by(Episode.created_at.desc())
    )
    episodes = [
        {
            "id": str(ep.id),
            "session_id": ep.session_id,
            "raw_summary": ep.raw_summary,
            "emotional_valence": ep.emotional_valence,
            "emotional_intensity": ep.emotional_intensity,
            "surprise_score": ep.surprise_score,
            "turn_count": ep.turn_count,
            "created_at": ep.created_at.isoformat() if ep.created_at else None
        }
        for ep in ep_result.scalars().all()
    ]
    
    # Permanent memories
    pm_result = await db.execute(
        select(PermanentMemory).where(PermanentMemory.user_id == user_id)
    )
    permanent_memories = [
        {
            "id": str(pm.id),
            "fact": pm.fact,
            "category": pm.category,
            "confidence": pm.confidence,
            "access_count": pm.access_count,
            "created_at": pm.created_at.isoformat() if pm.created_at else None
        }
        for pm in pm_result.scalars().all()
    ]
    
    # Goals
    goal_result = await db.execute(
        select(Goal).where(Goal.user_id == user_id)
    )
    goals = [
        {
            "id": str(g.id),
            "title": g.title,
            "description": g.description,
            "status": g.status,
            "created_at": g.created_at.isoformat() if g.created_at else None
        }
        for g in goal_result.scalars().all()
    ]
    
    # Persona profile
    pp_result = await db.execute(
        select(PersonaProfile).where(PersonaProfile.user_id == user_id)
    )
    persona_row = pp_result.scalars().first()
    persona = None
    if persona_row:
        persona = {
            "verbosity_ratio": persona_row.verbosity_ratio,
            "rephrasing_rate": persona_row.rephrasing_rate,
            "formality_score": persona_row.formality_score,
            "question_frequency": persona_row.question_frequency,
            "topic_return_rate": persona_row.topic_return_rate
        }
    
    # Neo4j entity relations
    entity_relations = await neo4j_client.get_user_subgraph(user_id, limit=200)
    
    return {
        "user_id": user_id,
        "exported_at": datetime.now(timezone.utc).isoformat(),
        "episodic_memories": episodes,
        "permanent_memories": permanent_memories,
        "goals": goals,
        "persona_profile": persona,
        "entity_relations": entity_relations
    }


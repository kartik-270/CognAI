from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from typing import Dict, Any, Optional
from datetime import datetime, timezone
from pydantic import BaseModel, Field

from app.db.database import get_db
from app.db.models import User, PersonaProfile
from app.api.auth import get_current_user
from app.persona.drift import PersonaDriftEngine

router = APIRouter(prefix="/persona", tags=["persona"])

class PersonaUpdateRequest(BaseModel):
    verbosity_ratio: Optional[float] = Field(None, ge=0.0, le=5.0)
    rephrasing_rate: Optional[float] = Field(None, ge=0.0, le=1.0)
    formality_score: Optional[float] = Field(None, ge=0.0, le=1.0)
    question_frequency: Optional[float] = Field(None, ge=0.0, le=1.0)
    topic_return_rate: Optional[float] = Field(None, ge=0.0, le=1.0)

@router.get("/state")
async def get_persona_state(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
) -> Dict[str, Any]:
    """
    Returns the user's current 5-signal persona profile and prompt directives.
    """
    engine = PersonaDriftEngine(db)
    state = await engine.get_or_create_profile(str(current_user.id))
    
    return {
        "user_id": state.user_id,
        "signals": {
            "verbosity_ratio": round(state.verbosity_ratio, 3),
            "rephrasing_rate": round(state.rephrasing_rate, 3),
            "formality_score": round(state.formality_score, 3),
            "question_frequency": round(state.question_frequency, 3),
            "topic_return_rate": round(state.topic_return_rate, 3)
        },
        "directives": state.generate_prompt_directive()
    }

@router.put("/state")
async def update_persona_state(
    request: PersonaUpdateRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
) -> Dict[str, Any]:
    """
    Manually calibrate the user's 5-signal persona profile.
    """
    engine = PersonaDriftEngine(db)
    state = await engine.get_or_create_profile(str(current_user.id))
    
    # Apply manual updates
    if request.verbosity_ratio is not None:
        state.verbosity_ratio = request.verbosity_ratio
    if request.rephrasing_rate is not None:
        state.rephrasing_rate = request.rephrasing_rate
    if request.formality_score is not None:
        state.formality_score = request.formality_score
    if request.question_frequency is not None:
        state.question_frequency = request.question_frequency
    if request.topic_return_rate is not None:
        state.topic_return_rate = request.topic_return_rate

    # Persist to database
    stmt = select(PersonaProfile).where(PersonaProfile.user_id == str(current_user.id))
    result = await db.execute(stmt)
    row = result.scalars().first()
    if row:
        row.verbosity_ratio = state.verbosity_ratio
        row.rephrasing_rate = state.rephrasing_rate
        row.formality_score = state.formality_score
        row.question_frequency = state.question_frequency
        row.topic_return_rate = state.topic_return_rate
        row.updated_at = datetime.now(timezone.utc)
        await db.commit()

    return {
        "user_id": state.user_id,
        "signals": {
            "verbosity_ratio": round(state.verbosity_ratio, 3),
            "rephrasing_rate": round(state.rephrasing_rate, 3),
            "formality_score": round(state.formality_score, 3),
            "question_frequency": round(state.question_frequency, 3),
            "topic_return_rate": round(state.topic_return_rate, 3)
        },
        "directives": state.generate_prompt_directive()
    }

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from typing import List, Dict, Any, Optional
from datetime import datetime, timezone
import re

from app.db.models import PersonaProfile
from app.persona.state import PersonaState
from app.memory.working import Message

CASUAL_MARKERS = {"hey", "hi", "lol", "yeah", "yep", "nah", "cool", "btw", "gonna", "wanna", "kinda", "super", "awesome"}
FORMAL_MARKERS = {"furthermore", "moreover", "consequently", "specifically", "regarding", "therefore", "subsequently", "utilize", "commence", "accordingly"}

class PersonaDriftEngine:
    """
    Computes the 5 behavioral signals from ongoing interaction and updates PersonaProfile.
    Signals:
    1. verbosity_ratio: user_words / assistant_words
    2. rephrasing_rate: whether current turn rephrased past turn
    3. formality_score: presence of formal vs casual linguistic markers
    4. question_frequency: ratio of questions in user turns
    5. topic_return_rate: recurrence of previous core nouns/topics
    """
    def __init__(self, db: AsyncSession):
        self.db = db

    @staticmethod
    def _extract_signals(
        user_prompt: str,
        assistant_response: Optional[str],
        is_rephrase: bool,
        recent_messages: List[Message]
    ) -> Dict[str, float]:
        user_words = len(re.findall(r'\b\w+\b', user_prompt))
        assistant_words = len(re.findall(r'\b\w+\b', assistant_response or "")) if assistant_response else max(1, user_words)
        
        # 1. Verbosity Ratio
        verbosity_ratio = float(min(5.0, user_words / max(1, assistant_words)))

        # 2. Rephrasing Indicator
        rephrasing_rate = 1.0 if is_rephrase else 0.0

        # 3. Formality Score
        words_lower = set(re.findall(r'\b[a-z]+\b', user_prompt.lower()))
        casual_count = len(words_lower.intersection(CASUAL_MARKERS))
        formal_count = len(words_lower.intersection(FORMAL_MARKERS))
        
        if formal_count > casual_count:
            formality_score = 0.8
        elif casual_count > formal_count:
            formality_score = 0.2
        else:
            formality_score = 0.5

        # 4. Question Frequency
        has_question = 1.0 if "?" in user_prompt else 0.0

        # 5. Topic Return Rate (checking keyword repetition from > 5 turns ago)
        topic_return = 0.0
        if len(recent_messages) >= 6:
            older_text = " ".join([m.content for m in recent_messages[:-4]])
            older_tokens = set(re.findall(r'\b[a-zA-Z]{4,}\b', older_text.lower()))
            current_tokens = set(re.findall(r'\b[a-zA-Z]{4,}\b', user_prompt.lower()))
            overlap = older_tokens.intersection(current_tokens)
            if overlap:
                topic_return = min(1.0, len(overlap) / max(1, len(current_tokens)))

        return {
            "verbosity_ratio": verbosity_ratio,
            "rephrasing_rate": rephrasing_rate,
            "formality_score": formality_score,
            "question_frequency": has_question,
            "topic_return_rate": topic_return
        }

    async def get_or_create_profile(self, user_id: str) -> PersonaState:
        stmt = select(PersonaProfile).where(PersonaProfile.user_id == user_id)
        result = await self.db.execute(stmt)
        row = result.scalars().first()

        if not row:
            try:
                row = PersonaProfile(user_id=user_id)
                self.db.add(row)
                await self.db.commit()
                await self.db.refresh(row)
            except Exception:
                await self.db.rollback()
                result = await self.db.execute(stmt)
                row = result.scalars().first()

        if not row:
            # Fallback if DB fetch fails
            return PersonaState(user_id=user_id)

        return PersonaState(
            user_id=user_id,
            verbosity_ratio=row.verbosity_ratio,
            rephrasing_rate=row.rephrasing_rate,
            formality_score=row.formality_score,
            question_frequency=row.question_frequency,
            topic_return_rate=row.topic_return_rate
        )

    async def update_profile(
        self,
        user_id: str,
        user_prompt: str,
        assistant_response: Optional[str],
        is_rephrase: bool,
        recent_messages: List[Message]
    ) -> PersonaState:
        """
        Extracts signals, applies EMA update, and persists to PostgreSQL.
        """
        current_state = await self.get_or_create_profile(user_id)
        new_signals = self._extract_signals(user_prompt, assistant_response, is_rephrase, recent_messages)
        
        current_state.update_ema(new_signals, alpha=0.20)

        # Update DB row
        stmt = select(PersonaProfile).where(PersonaProfile.user_id == user_id)
        result = await self.db.execute(stmt)
        row = result.scalars().first()
        if row:
            row.verbosity_ratio = current_state.verbosity_ratio
            row.rephrasing_rate = current_state.rephrasing_rate
            row.formality_score = current_state.formality_score
            row.question_frequency = current_state.question_frequency
            row.topic_return_rate = current_state.topic_return_rate
            row.updated_at = datetime.now(timezone.utc)
            await self.db.commit()

        return current_state

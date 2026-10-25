from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from typing import List, Dict, Any, Optional
from datetime import datetime, timezone, timedelta
import numpy as np
import logging

from app.db.models import Goal, Episode
from app.memory.working import Message

logger = logging.getLogger(__name__)

class ProactiveMemoryEngine:
    """
    Proactive Memory Engine (Phase 5 Core Contribution):
    Drives curiosity-driven, proactive contextual retrieval by:
    1. Detecting stalled or dormant active goals (> 3 days without progress).
    2. Finding latent connections between current user query and dormant goals.
    3. Generating non-intrusive proactive contextual nudges for the cognitive orchestrator.
    """
    def __init__(self, db: AsyncSession, stall_threshold_days: float = 3.0):
        self.db = db
        self.stall_threshold_days = stall_threshold_days

    @staticmethod
    def _cosine_similarity(vec_a: np.ndarray, vec_b: np.ndarray) -> float:
        norm_a = np.linalg.norm(vec_a)
        norm_b = np.linalg.norm(vec_b)
        if norm_a == 0 or norm_b == 0:
            return 0.0
        return float(np.dot(vec_a, vec_b) / (norm_a * norm_b))

    async def evaluate_proactive_opportunity(
        self,
        user_id: str,
        query: str,
        query_embedding: List[float],
        working_messages: List[Message],
        now: Optional[datetime] = None
    ) -> Dict[str, Any]:
        """
        Evaluates whether a proactive memory nudge should be surfaced for this turn.
        """
        curr_dt = now if now else datetime.now(timezone.utc)
        if not curr_dt.tzinfo:
            curr_dt = curr_dt.replace(tzinfo=timezone.utc)

        # 1. Fetch active user goals
        stmt = select(Goal).where(
            Goal.user_id == user_id,
            Goal.status == "active"
        )
        res = await self.db.execute(stmt)
        active_goals = res.scalars().all()

        if not active_goals:
            return {"triggered": False, "reason": "No active goals found."}

        # 2. Check for stalled goals (> stall_threshold_days inactive)
        stalled_goals = []
        for g in active_goals:
            ref_dt = g.updated_at or g.created_at
            if ref_dt:
                if not ref_dt.tzinfo:
                    ref_dt = ref_dt.replace(tzinfo=timezone.utc)
                idle_days = (curr_dt - ref_dt).total_seconds() / 86400.0
                if idle_days >= self.stall_threshold_days:
                    stalled_goals.append((g, idle_days))

        if not stalled_goals:
            return {"triggered": False, "reason": "No stalled goals detected."}

        # 3. Check for opportunistic semantic connection or open inquiry
        q_lower = query.lower()
        is_open_inquiry = any(marker in q_lower for marker in [
            "what should i", "what next", "any suggestions", "help me decide",
            "what was i doing", "what am i working on", "goals", "my plan", "where did we leave off"
        ])

        query_vec = np.array(query_embedding)
        best_goal: Optional[Goal] = None
        best_sim = 0.0
        best_idle_days = 0.0

        for g, idle_days in stalled_goals:
            if g.embedding:
                g_emb = np.array(g.embedding)
                sim = self._cosine_similarity(query_vec, g_emb)
                if sim > best_sim:
                    best_sim = sim
                    best_goal = g
                    best_idle_days = idle_days

        # Trigger conditions:
        # A) Explicit open inquiry about goals or direction
        # B) Moderate semantic connection to a dormant goal (sim >= 0.45)
        should_trigger = False
        rationale = ""

        if is_open_inquiry and stalled_goals:
            # Pick the most dormant goal
            stalled_goals.sort(key=lambda x: x[1], reverse=True)
            best_goal, best_idle_days = stalled_goals[0]
            should_trigger = True
            rationale = f"User made an open forward-looking inquiry; resurfacing dormant goal '{best_goal.title}' (idle for {best_idle_days:.1f} days)."

        elif best_goal and best_sim >= 0.45:
            should_trigger = True
            rationale = f"Current query semantically connects (sim: {best_sim:.2f}) to dormant goal '{best_goal.title}' (idle for {best_idle_days:.1f} days)."

        if not should_trigger or not best_goal:
            return {"triggered": False, "reason": "No opportune trigger condition met."}

        # Construct concise prompt directive for the LLM
        directive = (
            f"PROACTIVE GOAL NUDGE: The user previously set the active goal '{best_goal.title}' "
            f"which has been dormant for {best_idle_days:.1f} days. "
            f"Without derailing their query, naturally and tactfully acknowledge or connect this goal if relevant."
        )

        return {
            "triggered": True,
            "goal_id": str(best_goal.id),
            "goal_title": best_goal.title,
            "idle_days": round(best_idle_days, 1),
            "similarity": round(best_sim, 3),
            "rationale": rationale,
            "directive": directive
        }

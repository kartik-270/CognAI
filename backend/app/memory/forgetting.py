from typing import List, Optional
from datetime import datetime, timezone
import numpy as np

class GoalConditionedForgetting:
    """
    Implements biologically-grounded goal-conditioned memory forgetting.
    Decay rate lambda is scaled by the semantic distance to the user's active goals:
    lambda_eff = lambda_0 * (1.0 + min_goal_distance)
    Retention R = exp(-lambda_eff * delta_t)
    """
    def __init__(self, base_half_life_days: float = 30.0, pruning_threshold: float = 0.15):
        self.base_decay_rate = np.log(2) / base_half_life_days
        self.pruning_threshold = pruning_threshold

    @staticmethod
    def _cosine_distance(vec_a: np.ndarray, vec_b: np.ndarray) -> float:
        norm_a = np.linalg.norm(vec_a)
        norm_b = np.linalg.norm(vec_b)
        if norm_a == 0 or norm_b == 0:
            return 1.0
        sim = float(np.dot(vec_a, vec_b) / (norm_a * norm_b))
        return float(np.clip(1.0 - sim, 0.0, 1.0))

    def compute_retention(
        self,
        memory_embedding: List[float],
        active_goals_embeddings: List[List[float]],
        last_accessed_at: datetime,
        access_count: int = 1,
        now: Optional[datetime] = None
    ) -> float:
        """
        Computes the current retention score R in [0.0, 1.0].
        Higher access counts act as rehearsal reinforcements.
        """
        if now is None:
            now = datetime.now(timezone.utc)
        if last_accessed_at.tzinfo is None:
            last_accessed_at = last_accessed_at.replace(tzinfo=timezone.utc)

        delta_days = max(0.0, (now - last_accessed_at).total_seconds() / 86400.0)
        
        # Calculate goal distance
        mem_vec = np.array(memory_embedding)
        if active_goals_embeddings:
            goal_distances = [
                self._cosine_distance(mem_vec, np.array(g_emb))
                for g_emb in active_goals_embeddings
            ]
            min_goal_dist = min(goal_distances)
        else:
            min_goal_dist = 1.0 # Default max distance if no active goals

        # Effective decay: memories far from user goals decay up to 2x faster
        effective_lambda = self.base_decay_rate * (1.0 + min_goal_dist)
        
        # Rehearsal boost: each access reduces effective decay
        rehearsal_factor = 1.0 / (1.0 + 0.15 * min(10, access_count - 1))
        effective_lambda *= rehearsal_factor

        retention = float(np.exp(-effective_lambda * delta_days))
        return retention

    def should_prune(self, retention: float) -> bool:
        return retention < self.pruning_threshold

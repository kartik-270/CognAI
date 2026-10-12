from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update, delete
from typing import List, Dict, Any, Optional
import numpy as np
import json
import re
import logging

from app.db.models import PermanentMemory, Episode, User, Goal
from app.llm.router import llm_router
from app.graph.neo4j_client import neo4j_client

logger = logging.getLogger(__name__)

FACT_EXTRACTION_PROMPT = """
You are an expert memory consolidation system. Extract long-term permanent facts, user preferences, habits, beliefs, and stated goals from this session transcript.

Session Transcript:
\"\"\"
{transcript}
\"\"\"

Guidelines:
- Extract ONLY durable facts about the user (e.g. "User prefers Python over Java", "User is building a cognitive agent", "User lives in Delhi").
- Exclude transient conversation details (e.g. "User said hello").
- For each item, specify category: 'preference', 'identity', 'belief', or 'goal'.

Return ONLY a JSON array of objects:
[
  {{"fact": "...", "category": "preference|identity|belief|goal", "confidence": 0.95}}
]
"""

CONFLICT_RESOLUTION_PROMPT = """
You are a cognitive contradiction detector and semantic conflict resolver.
Evaluate the relationship between the EXISTING permanent memory and a NEW candidate fact.

EXISTING MEMORY:
"{existing_fact}" (Category: {existing_category})

NEW CANDIDATE FACT:
"{new_fact}" (Category: {new_category})

Determine the conflict state:
1. "CONTRADICTION_REPLACE": The new fact directly contradicts or updates the existing memory (e.g., "User is vegetarian" contradicts "User's favorite food is steak"). The new fact should supercede the existing memory.
2. "COMPATIBLE_KEEP_BOTH": Both are true, complementary, or cover distinct facets (e.g., "User likes tea" and "User likes coffee").
3. "MERGE": Both statements can be cleanly synthesized into one unified, non-redundant statement.

Return ONLY a valid JSON object:
{{
  "resolution": "CONTRADICTION_REPLACE" | "COMPATIBLE_KEEP_BOTH" | "MERGE",
  "merged_fact": "<synthesized fact if MERGE, else empty string>",
  "rationale": "<brief 1-sentence reason>"
}}
"""

ENTITY_EXTRACTION_PROMPT = """
You are a knowledge graph entity extractor. From the session transcript below, extract subject-predicate-object triples that represent durable relationships and key entities.

Session Transcript:
\"\"\"
{transcript}
\"\"\"

Guidelines:
- Extract durable relationships involving key entities (people, pets, locations, organizations, significant dates).
- Example: "Maria" - "adopted" - "Coco", "user" - "works_at" - "Google".
- EXCLUDE transient conversational details or routine actions (e.g. "ate_pizza", "went_to_store", "had_dinner"). Do not overload the graph with trivialities.
- Subject and object should be concise noun phrases or proper nouns (2-4 words max).
- Predicate should be a verb phrase in snake_case (e.g. "has_pet", "is_friends_with", "adopted", "volunteers_at").

Return ONLY a JSON array of triples:
[
  {{"subject": "...", "predicate": "...", "object": "..."}}
]
"""

class MemoryConflictResolver:
    """
    Solves Gap 2: Semantic Conflict Resolver & Contradiction Detector.
    Prevents contradictory facts from accumulating in permanent memory.
    """
    def __init__(self, db: AsyncSession, conflict_sim_threshold: float = 0.65):
        self.db = db
        self.conflict_sim_threshold = conflict_sim_threshold

    @staticmethod
    def _cosine_similarity(vec_a: np.ndarray, vec_b: np.ndarray) -> float:
        norm_a = np.linalg.norm(vec_a)
        norm_b = np.linalg.norm(vec_b)
        if norm_a == 0 or norm_b == 0:
            return 0.0
        return float(np.dot(vec_a, vec_b) / (norm_a * norm_b))

    async def resolve_and_persist(
        self,
        user_id: str,
        candidate_fact: str,
        category: str,
        confidence: float
    ) -> Dict[str, Any]:
        """
        Embeds candidate fact, checks for semantic conflicts against existing permanent memories,
        and applies contradiction resolution via secondary LLM.
        """
        cand_emb = np.array(await llm_router.embed(candidate_fact))

        # Retrieve existing user permanent memories with strict user_id row isolation
        stmt = select(PermanentMemory).where(
            PermanentMemory.user_id == user_id,
            PermanentMemory.embedding.isnot(None)
        )
        result = await self.db.execute(stmt)
        existing_memories: List[PermanentMemory] = result.scalars().all()

        conflicting_memory: Optional[PermanentMemory] = None
        max_sim = 0.0

        for mem in existing_memories:
            sim = self._cosine_similarity(cand_emb, np.array(mem.embedding))
            if sim > max_sim:
                max_sim = sim
                if sim >= self.conflict_sim_threshold:
                    conflicting_memory = mem

        # If no high semantic overlap, store candidate fact directly
        if not conflicting_memory:
            new_mem = PermanentMemory(
                user_id=user_id,
                fact=candidate_fact,
                category=category,
                confidence=confidence,
                embedding=cand_emb.tolist()
            )
            self.db.add(new_mem)
            await self.db.commit()
            return {"action": "inserted", "fact": candidate_fact}

        # High semantic overlap detected: invoke LLM contradiction check
        prompt = CONFLICT_RESOLUTION_PROMPT.format(
            existing_fact=conflicting_memory.fact,
            existing_category=conflicting_memory.category,
            new_fact=candidate_fact,
            new_category=category
        )
        raw_res = await llm_router.background_task(prompt)
        
        resolution = "COMPATIBLE_KEEP_BOTH"
        merged_fact = ""
        try:
            match = re.search(r'\{.*\}', raw_res, re.DOTALL)
            if match:
                parsed = json.loads(match.group(0))
                resolution = parsed.get("resolution", "COMPATIBLE_KEEP_BOTH")
                merged_fact = parsed.get("merged_fact", "")
        except Exception:
            pass

        if resolution == "CONTRADICTION_REPLACE":
            # Replace existing conflicting memory
            conflicting_memory.fact = candidate_fact
            conflicting_memory.category = category
            conflicting_memory.confidence = confidence
            conflicting_memory.embedding = cand_emb.tolist()
            await self.db.commit()
            return {"action": "contradiction_replaced", "old_fact": conflicting_memory.fact, "new_fact": candidate_fact}

        elif resolution == "MERGE" and merged_fact:
            merged_emb = await llm_router.embed(merged_fact)
            conflicting_memory.fact = merged_fact
            conflicting_memory.embedding = merged_emb
            await self.db.commit()
            return {"action": "merged", "merged_fact": merged_fact}

        else:
            # Compatible, add as new distinct memory
            new_mem = PermanentMemory(
                user_id=user_id,
                fact=candidate_fact,
                category=category,
                confidence=confidence,
                embedding=cand_emb.tolist()
            )
            self.db.add(new_mem)
            await self.db.commit()
            return {"action": "inserted_compatible", "fact": candidate_fact}


class MemoryConsolidator:
    """
    Orchestrates surprise-gated consolidation, fact extraction, contradiction resolution,
    and HDBSCAN clustering.
    """
    def __init__(self, db: AsyncSession, surprise_threshold: float = 0.30):
        self.db = db
        self.surprise_threshold = surprise_threshold
        self.resolver = MemoryConflictResolver(db)

    async def consolidate_session(
        self,
        user_id: str,
        session_id: str,
        transcript: str,
        surprise_score: float = 0.5
    ) -> Dict[str, Any]:
        """
        Consolidates a closed session into permanent memory if surprise exceeds threshold
        or if explicitly triggered.
        """
        # 1. Surprise Gate Check
        is_surprise_gated = surprise_score >= self.surprise_threshold
        if not is_surprise_gated:
            return {
                "status": "skipped_low_surprise",
                "surprise_score": surprise_score,
                "threshold": self.surprise_threshold
            }

        # 2. Extract durable facts via secondary LLM (Gemini 2.0 Flash)
        prompt = FACT_EXTRACTION_PROMPT.format(transcript=transcript)
        raw_facts = await llm_router.background_task(prompt)

        extracted_facts = []
        try:
            match = re.search(r'\[.*\]', raw_facts, re.DOTALL)
            if match:
                extracted_facts = json.loads(match.group(0))
        except Exception:
            pass

        actions = []
        goal_actions = []
        
        # Extract source_turn_ids and append to fact
        source_ids = re.findall(r"D\d+:\d+", transcript)
        source_suffix = "\nSources: " + ", ".join(source_ids) if source_ids else ""

        for item in extracted_facts:
            fact = item.get("fact", "").strip()
            if source_suffix and fact:
                fact += source_suffix
            cat = item.get("category", "fact")
            conf = float(item.get("confidence", 0.9))
            if not fact:
                continue
            res = await self.resolver.resolve_and_persist(user_id, fact, cat, conf)
            actions.append(res)

            # Priority 3 (Gap C): Auto-create Goal records from inferred goals
            if cat == "goal" and conf >= 0.7:
                try:
                    goal_embedding = await llm_router.embed(fact)
                    existing_goals = await self.db.execute(
                        select(Goal).where(Goal.user_id == user_id, Goal.status == "active")
                    )
                    existing_titles = [g.title.lower() for g in existing_goals.scalars().all()]
                    # Avoid duplicate goals by checking title similarity
                    if fact.lower()[:50] not in " ".join(existing_titles):
                        new_goal = Goal(
                            user_id=user_id,
                            title=fact[:200],
                            description=f"Inferred from session {session_id}",
                            status="active",
                            embedding=goal_embedding
                        )
                        self.db.add(new_goal)
                        await self.db.commit()
                        goal_actions.append({"action": "goal_inferred", "title": fact[:200]})
                        logger.info(f"Auto-inferred goal for user {user_id}: {fact[:80]}")
                except Exception as e:
                    logger.warning(f"Failed to auto-create goal: {e}")

        # Priority 2 (Gap B): Extract entity triples → Neo4j knowledge graph
        entity_actions = await self._extract_entities_to_graph(user_id, transcript)

        return {
            "status": "consolidated",
            "session_id": session_id,
            "surprise_score": surprise_score,
            "facts_extracted_count": len(extracted_facts),
            "resolutions": actions,
            "goals_inferred": goal_actions,
            "entities_extracted": entity_actions
        }

    async def _extract_entities_to_graph(
        self,
        user_id: str,
        transcript: str
    ) -> List[Dict[str, Any]]:
        """
        Extracts entity-relation triples from the session transcript and
        persists them to Neo4j with strict user_id isolation.
        """
        prompt = ENTITY_EXTRACTION_PROMPT.format(transcript=transcript)
        try:
            raw_output = await llm_router.background_task(prompt)
            match = re.search(r'\[.*\]', raw_output, re.DOTALL)
            if not match:
                return []

            triples = json.loads(match.group(0))
            results = []
            for triple in triples:
                subj = triple.get("subject", "").strip()
                pred = triple.get("predicate", "").strip()
                obj = triple.get("object", "").strip()
                if subj and pred and obj:
                    success = await neo4j_client.add_entity_relation(
                        user_id=user_id,
                        subject=subj,
                        predicate=pred,
                        object_=obj
                    )
                    if success:
                        results.append({"subject": subj, "predicate": pred, "object": obj})
            logger.info(f"Extracted {len(results)} entity triples for user {user_id}")
            return results
        except Exception as e:
            logger.warning(f"Entity extraction failed for user {user_id}: {e}")
            return []

    async def run_hdbscan_clustering(self, user_id: str, min_cluster_size: int = 2) -> Dict[str, Any]:
        """
        Runs HDBSCAN clustering on episodic memories for users with >= 5 sessions.
        For cold-start users (< 5 sessions), returns cold_start status.
        """
        stmt = select(Episode.embedding).where(
            Episode.user_id == user_id,
            Episode.embedding.isnot(None)
        )
        result = await self.db.execute(stmt)
        embeddings = [row[0] for row in result.all() if row[0] is not None]

        if len(embeddings) < 5:
            return {"status": "cold_start", "session_count": len(embeddings), "message": "Fewer than 5 sessions; HDBSCAN deferred."}

        try:
            from sklearn.cluster import HDBSCAN
            data = np.array(embeddings)
            clusterer = HDBSCAN(min_cluster_size=min_cluster_size, metric='cosine')
            labels = clusterer.fit_predict(data)
            unique_clusters = len(set(labels)) - (1 if -1 in labels else 0)
            return {
                "status": "clustered",
                "total_episodes": len(embeddings),
                "clusters_found": unique_clusters,
                "labels": labels.tolist()
            }
        except Exception as e:
            return {"status": "error", "error": str(e)}

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, text, func, desc, or_
from typing import List, Dict, Any, Optional
from datetime import datetime, timezone, timedelta
import numpy as np
import re
import logging

from app.db.models import Episode, PermanentMemory, Goal, ChatMessage
from app.llm.router import llm_router

logger = logging.getLogger(__name__)

class ScoredMemory:
    def __init__(
        self,
        id: str,
        content: str,
        memory_type: str, # 'episodic' or 'permanent'
        final_score: float,
        components: Dict[str, float],
        created_at: datetime,
        source_turn_ids: Optional[List[str]] = None
    ):
        self.id = id
        self.content = content
        self.memory_type = memory_type
        self.final_score = final_score
        self.components = components
        self.created_at = created_at
        self.source_turn_ids = source_turn_ids or re.findall(r"D\d+:\d+", content)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "content": self.content,
            "memory_type": self.memory_type,
            "score": round(self.final_score, 4),
            "components": {k: round(v, 4) for k, v in self.components.items()},
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "source_turn_ids": self.source_turn_ids
        }

class MemoryRetriever:
    """
    Cognitive retrieval system implementing the temporal-relevance formula:
    Score = (alpha * sim) + (beta * goal_sim) + (gamma * surprise) + (epsilon * temporal) - (delta * redundancy)
    """
    def __init__(
        self,
        db: AsyncSession,
        alpha: float = 0.40,
        beta: float = 0.25,
        gamma: float = 0.15,
        epsilon: float = 0.15,
        delta: float = 0.10,
        temporal_half_life_days: float = 14.0
    ):
        self.db = db
        self.alpha = alpha
        self.beta = beta
        self.gamma = gamma
        self.epsilon = epsilon
        self.delta = delta
        # Exponential decay rate: lambda = ln(2) / half_life
        self.decay_rate = np.log(2) / temporal_half_life_days

    @staticmethod
    def _cosine_similarity(vec_a: np.ndarray, vec_b: np.ndarray) -> float:
        norm_a = np.linalg.norm(vec_a)
        norm_b = np.linalg.norm(vec_b)
        if norm_a == 0 or norm_b == 0:
            return 0.0
        return float(np.dot(vec_a, vec_b) / (norm_a * norm_b))

    def _compute_temporal_relevance(
        self,
        created_at: Optional[datetime],
        now: datetime,
        intent: str = "general",
        memory_type: str = "episodic",
        date_range: Optional[List[str]] = None
    ) -> float:
        if not created_at:
            return 1.0
        if not created_at.tzinfo:
            created_at = created_at.replace(tzinfo=timezone.utc)

        if memory_type == "permanent":
            return 0.95

        # If explicit date range provided (e.g. yesterday)
        if intent == "temporal" and date_range and len(date_range) == 2:
            try:
                start_dt = datetime.strptime(date_range[0], "%Y-%m-%d").replace(tzinfo=timezone.utc)
                end_dt = datetime.strptime(date_range[1], "%Y-%m-%d").replace(tzinfo=timezone.utc, hour=23, minute=59, second=59)
                if start_dt <= created_at <= end_dt:
                    return 1.25 # Direct target window match
                # Decay with distance from target window
                if created_at < start_dt:
                    dist_days = (start_dt - created_at).total_seconds() / 86400.0
                else:
                    dist_days = (created_at - end_dt).total_seconds() / 86400.0
                return float(np.exp(-self.decay_rate * max(0.0, dist_days)))
            except Exception:
                pass

        delta_days = max(0.0, (now - created_at).total_seconds() / 86400.0)
        if intent == "temporal":
            # In a temporal query, recent interactions (past 48 hours) get top temporal weight
            if delta_days <= 2.0:
                return 1.15
            return float(np.exp(-self.decay_rate * (delta_days / 2.0)))

        return float(np.exp(-self.decay_rate * delta_days))

    async def retrieve(
        self,
        user_id: str,
        query: str,
        top_k: int = 5,
        active_goals_embeddings: Optional[List[List[float]]] = None,
        now: Optional[datetime] = None,
        intent: str = "general",
        date_range: Optional[List[str]] = None
    ) -> List[ScoredMemory]:
        """
        Retrieves top-k episodic and permanent memories scored with temporal reasoning
        and maximal marginal relevance (redundancy penalty).
        """
        now = now if now else datetime.now(timezone.utc)
        if not now.tzinfo:
            now = now.replace(tzinfo=timezone.utc)
        query_vec = np.array(await llm_router.embed(query))

        q_lower = query.lower()
        is_meta_temporal = any(kw in q_lower for kw in [
            "yesterday", "earlier", "already", "previous", "previously", "last session",
            "last time", "told you", "shared", "discussed", "what did i say", "what did we discuss",
            "remember", "recall", "we talked", "my topic", "what was my", "past chat", "past conversation"
        ])

        # Extract salient lexical search keywords (length >= 3, excluding stopwords and query conversational framing)
        STOP_WORDS = {
            "what", "when", "where", "which", "who", "whom", "whose", "why", "how",
            "this", "that", "these", "those", "there", "their", "the", "and", "but",
            "for", "with", "from", "about", "into", "through", "during", "before",
            "after", "above", "below", "to", "at", "by", "is", "am", "are", "was",
            "were", "be", "been", "being", "have", "has", "had", "having", "do",
            "does", "did", "doing", "would", "should", "could", "ought", "i'm", "you're",
            "they're", "we're", "can", "will", "just", "don't", "shouldn't", "couldn't",
            "did't", "won't", "mention", "mentioned", "describe", "described", "think",
            "say", "said", "tell", "told", "talk", "talked", "feel", "felt", "know",
            "known", "like", "kind", "type", "thing", "things", "someone", "something"
        }
        lexical_keywords = [
            w for w in re.findall(r'\b[a-zA-Z0-9_\'-]{3,}\b', q_lower)
            if w not in STOP_WORDS
        ]

        # Fetch candidate active goals if not provided
        if active_goals_embeddings is None:
            goals_stmt = select(Goal.embedding).where(
                Goal.user_id == user_id,
                Goal.status == "active",
                Goal.embedding.isnot(None)
            )
            g_result = await self.db.execute(goals_stmt)
            active_goals_embeddings = [np.array(row[0]) for row in g_result.all() if row[0] is not None]

        # Fetch candidate episodes (up to 30 most recent)
        ep_stmt = select(Episode).where(
            Episode.user_id == user_id,
            Episode.embedding.isnot(None)
        )
        
        # Apply date bounds if extracted (with inclusive end of day)
        if intent == "temporal" and date_range and len(date_range) == 2:
            try:
                start_dt = datetime.strptime(date_range[0], "%Y-%m-%d").replace(tzinfo=timezone.utc)
                end_dt = datetime.strptime(date_range[1], "%Y-%m-%d").replace(tzinfo=timezone.utc, hour=23, minute=59, second=59)
                ep_stmt_filtered = ep_stmt.where(Episode.created_at >= start_dt, Episode.created_at <= end_dt)
                ep_check = await self.db.execute(ep_stmt_filtered.limit(5))
                if ep_check.scalars().first():
                    ep_stmt = ep_stmt_filtered
            except Exception:
                pass

        # Fetch top 300 most semantically similar episodes (expanded for better recall)
        ep_stmt_sem = ep_stmt.order_by(Episode.embedding.cosine_distance(query_vec.tolist())).limit(300)
        ep_result_sem = await self.db.execute(ep_stmt_sem)
        episodes_sem = ep_result_sem.scalars().all()

        # Fetch top 50 most recent episodes (expanded)
        ep_stmt_rec = ep_stmt.order_by(Episode.created_at.desc()).limit(50)
        ep_result_rec = await self.db.execute(ep_stmt_rec)
        episodes_rec = ep_result_rec.scalars().all()

        # Hybrid Sparse: fetch episodes matching key lexical terms
        episodes_lex = []
        if lexical_keywords:
            try:
                ep_stmt_lex = ep_stmt.where(
                    or_(*[Episode.raw_summary.ilike(f"%{kw}%") for kw in lexical_keywords[:8]])
                ).limit(50)
                ep_res_lex = await self.db.execute(ep_stmt_lex)
                episodes_lex = ep_res_lex.scalars().all()
            except Exception as e:
                logger.warning(f"Lexical episode query warning: {e}")
        
        # Deduplicate episodes
        episodes_dict = {ep.id: ep for ep in episodes_sem + episodes_rec + episodes_lex}
        episodes = list(episodes_dict.values())

        # Enrich episodes with substantive user turns from the session to preserve exact context
        session_ids = [ep.session_id for ep in episodes if getattr(ep, 'session_id', None)]
        user_msgs_map: Dict[str, List[str]] = {}
        if session_ids:
            try:
                u_stmt = select(ChatMessage.session_id, ChatMessage.content).where(
                    ChatMessage.session_id.in_(session_ids),
                    ChatMessage.role == "user"
                ).order_by(ChatMessage.created_at.asc())
                u_res = await self.db.execute(u_stmt)
                for s_id, c_text in u_res.all():
                    if c_text and len(c_text.strip().split()) >= 2:
                        cleaned = c_text.strip()
                        if cleaned.lower() not in {"hello", "hi", "hey", "test", "ok", "okay"}:
                            if s_id not in user_msgs_map:
                                user_msgs_map[s_id] = []
                            user_msgs_map[s_id].append(cleaned)
            except Exception as e:
                logger.warning(f"Error fetching session user messages: {e}")

        # Fetch top 100 most semantically similar permanent memories
        perm_stmt_base = select(PermanentMemory).where(
            PermanentMemory.user_id == user_id,
            PermanentMemory.embedding.isnot(None)
        )
        perm_stmt_sem = perm_stmt_base.order_by(PermanentMemory.embedding.cosine_distance(query_vec.tolist())).limit(200)
        perm_result_sem = await self.db.execute(perm_stmt_sem)
        perms_sem = perm_result_sem.scalars().all()
        
        # Fetch top 50 most recently accessed permanent memories
        perm_stmt_rec = perm_stmt_base.order_by(PermanentMemory.last_accessed_at.desc()).limit(50)
        perm_result_rec = await self.db.execute(perm_stmt_rec)
        perms_rec = perm_result_rec.scalars().all()

        # Hybrid Sparse: fetch permanent memories matching key lexical terms
        perms_lex = []
        if lexical_keywords:
            try:
                perm_stmt_lex = perm_stmt_base.where(
                    or_(*[PermanentMemory.fact.ilike(f"%{kw}%") for kw in lexical_keywords[:8]])
                ).limit(30)
                perm_res_lex = await self.db.execute(perm_stmt_lex)
                perms_lex = perm_res_lex.scalars().all()
            except Exception as e:
                logger.warning(f"Lexical permanent memory query warning: {e}")
        
        # Deduplicate permanent memories
        perms_dict = {pm.id: pm for pm in perms_sem + perms_rec + perms_lex}
        permanent_memories = list(perms_dict.values())

        candidates = []

        # Process Episodes
        for ep in episodes:
            emb = np.array(ep.embedding)
            sim = max(0.0, self._cosine_similarity(query_vec, emb))
            
            # Goal similarity
            goal_sim = 0.0
            if active_goals_embeddings:
                goal_sim = max([max(0.0, self._cosine_similarity(emb, g_vec)) for g_vec in active_goals_embeddings])
                
            surprise = ep.surprise_score or 0.0
            temporal = self._compute_temporal_relevance(ep.created_at, now, intent, memory_type="episodic", date_range=date_range)
            
            # Temporal boosting: surface episodes close to any past-event reference.
            # Covers both meta-temporal ("we talked yesterday") and date-anchored
            # queries ("When did X happen?") without requiring an explicit date_range from the LLM.
            if (is_meta_temporal or intent == "temporal") and ep.created_at:
                c_dt = ep.created_at if ep.created_at.tzinfo else ep.created_at.replace(tzinfo=timezone.utc)
                delta_days = max(0.0, (now - c_dt).total_seconds() / 86400.0)
                if delta_days <= 2.0:
                    # Very recent (meta-temporal: "we talked earlier/yesterday")
                    sim = max(sim, 0.72)
                    temporal = max(temporal, 1.20)
                elif delta_days <= 7.0:
                    sim = max(sim, 0.55)
                    temporal = max(temporal, 1.10)
                elif delta_days <= 30.0:
                    # Within a month: helps historical date queries ("When did she paint?")
                    sim = max(sim, 0.45)


            # Build enriched episodic content
            content = ep.raw_summary or ""
            if ep.session_id and ep.session_id in user_msgs_map and user_msgs_map[ep.session_id]:
                key_inputs = " | ".join(user_msgs_map[ep.session_id][:4])
                content = f"{content} [User discussed: {key_inputs}]"

            # Hybrid Lexical keyword matching boost for micro-detail recall
            if lexical_keywords and content:
                content_lower = content.lower()
                matches = sum(1 for kw in lexical_keywords if kw in content_lower)
                if matches > 0:
                    overlap_ratio = matches / len(lexical_keywords)
                    lex_boost = min(0.25, 0.08 * matches + 0.10 * overlap_ratio)
                    sim = min(1.0, sim + lex_boost)

            candidates.append({
                "id": str(ep.id),
                "content": content,
                "type": "episodic",
                "embedding": emb,
                "created_at": ep.created_at,
                "sim": sim,
                "goal_sim": goal_sim,
                "surprise": surprise,
                "temporal": temporal
            })

        # Process unconsolidated recent sessions (if any active chats haven't consolidated yet)
        if is_meta_temporal or intent == "temporal":
            try:
                active_sids_stmt = (
                    select(ChatMessage.session_id, func.max(ChatMessage.created_at).label("last_active"))
                    .where(ChatMessage.user_id == user_id)
                    .group_by(ChatMessage.session_id)
                    .order_by(desc("last_active"))
                    .limit(3)
                )
                active_sids_res = await self.db.execute(active_sids_stmt)
                for s_id, last_act in active_sids_res.all():
                    if s_id not in session_ids: # Session not yet consolidated into an Episode
                        m_stmt = select(ChatMessage.content, ChatMessage.role).where(
                            ChatMessage.session_id == s_id
                        ).order_by(ChatMessage.created_at.asc()).limit(12)
                        m_res = await self.db.execute(m_stmt)
                        turns = m_res.all()
                        substantive = [f"{role}: {c}" for c, role in turns if c and len(c.split()) > 2 and c.lower() not in {"hello", "hi", "hey"}]
                        if substantive:
                            session_txt = f"Recent conversation session ({last_act.strftime('%Y-%m-%d %H:%M UTC') if last_act else 'recent'}): " + " | ".join(substantive[:5])
                            s_emb = np.array(await llm_router.embed(session_txt))
                            s_sim = max(0.0, self._cosine_similarity(query_vec, s_emb))
                            if is_meta_temporal:
                                s_sim = max(s_sim, 0.75)
                            if lexical_keywords:
                                matches = sum(1 for kw in lexical_keywords if kw in session_txt.lower())
                                if matches > 0:
                                    s_sim = min(1.0, s_sim + min(0.20, 0.08 * matches))
                            candidates.append({
                                "id": f"session_{s_id}",
                                "content": session_txt,
                                "type": "episodic",
                                "embedding": s_emb,
                                "created_at": last_act or now,
                                "sim": s_sim,
                                "goal_sim": 0.0,
                                "surprise": 0.2,
                                "temporal": 1.25
                            })
            except Exception as e:
                logger.warning(f"Error checking unconsolidated sessions: {e}")

        # Process Permanent Memories
        for pm in permanent_memories:
            emb = np.array(pm.embedding)
            sim = max(0.0, self._cosine_similarity(query_vec, emb))
            
            goal_sim = 0.0
            if active_goals_embeddings:
                goal_sim = max([max(0.0, self._cosine_similarity(emb, g_vec)) for g_vec in active_goals_embeddings])
                
            surprise = 0.2 # Permanent facts have lower baseline surprise
            temporal = self._compute_temporal_relevance(pm.last_accessed_at, now, intent, memory_type="permanent", date_range=date_range)
            
            pm_content = f"[{pm.category.upper()}] {pm.fact}"
            if lexical_keywords and pm.fact:
                matches = sum(1 for kw in lexical_keywords if kw in pm.fact.lower())
                if matches > 0:
                    overlap_ratio = matches / len(lexical_keywords)
                    lex_boost = min(0.25, 0.08 * matches + 0.10 * overlap_ratio)
                    sim = min(1.0, sim + lex_boost)

            candidates.append({
                "id": str(pm.id),
                "content": pm_content,
                "type": "permanent",
                "embedding": emb,
                "created_at": pm.created_at,
                "sim": sim,
                "goal_sim": goal_sim,
                "surprise": surprise,
                "temporal": temporal
            })

        # Process Knowledge Graph (Phase 5)
        from app.graph.neo4j_client import neo4j_client
        keywords = [kw for kw in re.findall(r'\b\w{3,}\b', query.lower()) if kw not in {"who", "what", "where", "when", "why", "how", "the", "and", "that", "have", "for", "with", "about"}]
        graph_triples = await neo4j_client.retrieve_subgraph(user_id, keywords, limit=10)
        
        if graph_triples:
            graph_text = "\n".join([f"({t['subject']}) -[{t['predicate']}]-> ({t['object']})" for t in graph_triples])
            emb = np.array(await llm_router.embed(graph_text))
            sim = max(0.0, self._cosine_similarity(query_vec, emb))
            
            goal_sim = 0.0
            if active_goals_embeddings:
                goal_sim = max([max(0.0, self._cosine_similarity(emb, g_vec)) for g_vec in active_goals_embeddings])
                
            candidates.append({
                "id": "neo4j_graph_results",
                "content": graph_text,
                "type": "knowledge_graph",
                "embedding": emb,
                "created_at": now,
                "sim": min(1.0, sim + 0.20),  # Boosted keyword match bonus
                "goal_sim": goal_sim,
                "surprise": 0.1,
                "temporal": 1.0
            })

        if not candidates:
            return []

        # --- Multi-hop Iterative Retrieval Pass ---
        # After first-pass candidate scoring, if intent is multi_hop, open_domain, or general,
        # extract entity terms from the top-5 candidate summaries and run a second embedding
        # search over both episodes and permanent memories to chain multi-hop evidence turns.
        if intent in ("multi_hop", "open_domain", "general") and len(candidates) > 0:
            try:
                # Score all candidates to find top-5 for pivot extraction
                _scored_preview = []
                for c in candidates:
                    _s = (self.alpha * c["sim"]) + (self.beta * c["goal_sim"]) + \
                         (self.gamma * c["surprise"]) + (self.epsilon * c["temporal"])
                    _scored_preview.append((_s, c))
                _scored_preview.sort(key=lambda x: x[0], reverse=True)
                top_contents = " ".join([c["content"] for _, c in _scored_preview[:5]])

                # Extract pivot keywords (named entities, capitalized words, and key nouns)
                pivot_terms = [w for w in re.findall(r'\b[A-Za-z]{3,}\b', top_contents) 
                               if w.lower() not in {"the", "this", "that", "user", "sources", "full", "dialogue", "segment", "part"}]
                if pivot_terms:
                    pivot_query = " ".join(list(dict.fromkeys(pivot_terms))[:12])  # Deduplicated top-12
                    pivot_vec = np.array(await llm_router.embed(pivot_query))
                    
                    # Second-pass semantic search for episodic pivots (expanded to 50)
                    pivot_ep_stmt = select(Episode).where(
                        Episode.user_id == user_id,
                        Episode.embedding.isnot(None)
                    ).order_by(Episode.embedding.cosine_distance(pivot_vec.tolist())).limit(50)
                    pivot_ep_res = await self.db.execute(pivot_ep_stmt)
                    pivot_episodes = pivot_ep_res.scalars().all()
                    
                    existing_ids = {c["id"] for c in candidates}
                    for pep in pivot_episodes:
                        if str(pep.id) in existing_ids:
                            continue
                        pemb = np.array(pep.embedding)
                        psim = max(0.0, self._cosine_similarity(query_vec, pemb))
                        # Give iterative-retrieval hits a healthy similarity floor
                        psim = max(psim, 0.42)
                        ptemporal = self._compute_temporal_relevance(
                            pep.created_at, now, intent, memory_type="episodic", date_range=date_range
                        )
                        pgoal_sim = 0.0
                        if active_goals_embeddings:
                            pgoal_sim = max([max(0.0, self._cosine_similarity(pemb, g)) 
                                            for g in active_goals_embeddings])
                        pcontent = pep.raw_summary or ""
                        if pep.session_id and pep.session_id in user_msgs_map:
                            key_inputs = " | ".join(user_msgs_map[pep.session_id][:4])
                            pcontent = f"{pcontent} [User discussed: {key_inputs}]"
                        candidates.append({
                            "id": str(pep.id),
                            "content": pcontent,
                            "type": "episodic",
                            "embedding": pemb,
                            "created_at": pep.created_at,
                            "sim": psim,
                            "goal_sim": pgoal_sim,
                            "surprise": pep.surprise_score or 0.0,
                            "temporal": ptemporal
                        })

                    # Second-pass semantic search for permanent memories pivots
                    pivot_pm_stmt = select(PermanentMemory).where(
                        PermanentMemory.user_id == user_id,
                        PermanentMemory.embedding.isnot(None)
                    ).order_by(PermanentMemory.embedding.cosine_distance(pivot_vec.tolist())).limit(30)
                    pivot_pm_res = await self.db.execute(pivot_pm_stmt)
                    pivot_perms = pivot_pm_res.scalars().all()
                    for ppm in pivot_perms:
                        if str(ppm.id) in existing_ids:
                            continue
                        ppmb = np.array(ppm.embedding)
                        ppsim = max(0.0, self._cosine_similarity(query_vec, ppmb))
                        ppsim = max(ppsim, 0.40)
                        candidates.append({
                            "id": str(ppm.id),
                            "content": f"[{ppm.category.upper()}] {ppm.fact}",
                            "type": "permanent",
                            "embedding": ppmb,
                            "created_at": ppm.created_at,
                            "sim": ppsim,
                            "goal_sim": 0.0,
                            "surprise": 0.2,
                            "temporal": 1.0
                        })
            except Exception as e:
                logger.warning(f"Multi-hop iterative retrieval pass failed: {e}")

        # Greedy selection with redundancy penalty (Maximal Marginal Relevance)
        selected: List[ScoredMemory] = []
        selected_embeddings: List[np.ndarray] = []

        for _ in range(min(top_k, len(candidates))):
            best_candidate = None
            best_score = -float("inf")
            best_components = {}

            for cand in candidates:
                if any(cand["id"] == s.id for s in selected):
                    continue

                # Redundancy penalty: max similarity to already selected memories
                redundancy = 0.0
                if selected_embeddings:
                    redundancy = max([max(0.0, self._cosine_similarity(cand["embedding"], s_emb)) for s_emb in selected_embeddings])

                final_score = (
                    (self.alpha * cand["sim"]) +
                    (self.beta * cand["goal_sim"]) +
                    (self.gamma * cand["surprise"]) +
                    (self.epsilon * cand["temporal"]) -
                    (self.delta * redundancy)
                )

                if final_score > best_score:
                    best_score = final_score
                    best_candidate = cand
                    best_components = {
                        "similarity": cand["sim"],
                        "goal_similarity": cand["goal_sim"],
                        "surprise": cand["surprise"],
                        "temporal": cand["temporal"],
                        "redundancy_penalty": redundancy
                    }

            if best_candidate and best_score > 0.0:
                selected.append(
                    ScoredMemory(
                        id=best_candidate["id"],
                        content=best_candidate["content"],
                        memory_type=best_candidate["type"],
                        final_score=best_score,
                        components=best_components,
                        created_at=best_candidate["created_at"]
                    )
                )
                selected_embeddings.append(best_candidate["embedding"])
            else:
                break

        return selected

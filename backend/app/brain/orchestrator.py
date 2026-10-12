from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from typing import Dict, Any, Optional, List
import logging
from datetime import datetime

from app.memory.working import WorkingMemory
from app.memory.retrieval import MemoryRetriever
from app.memory.permanent import PermanentMemoryManager
from app.persona.drift import PersonaDriftEngine
from app.brain.metacognition import MetacognitiveMonitor, ThinkingMode
from app.brain.context_assembler import ContextAssembler
from app.llm.router import llm_router
from app.db.models import User, DocumentAttachment
from app.services.storage import get_storage_service
import base64
import uuid

logger = logging.getLogger(__name__)

# Active in-memory working sessions keyed by user_id
# In a distributed multi-node production setup, this can be synced with Redis
_active_working_memories: Dict[str, WorkingMemory] = {}

def get_working_memory(user_id: str) -> WorkingMemory:
    if user_id not in _active_working_memories:
        _active_working_memories[user_id] = WorkingMemory(user_id=user_id, capacity=20, session_timeout_minutes=30)
    return _active_working_memories[user_id]


class CognitiveOrchestrator:
    """
    CognAI Brain Orchestrator:
    Executes the closed-loop cognitive cycle:
    1. Lazy session boundary check (> 30 min inactivity)
    2. Working memory update & rephrasing detection
    3. Multi-factor memory retrieval with temporal weighting
    4. Metacognitive confidence estimation & mode routing
    5. Context assembly with active goals & persona directives
    6. Response generation via low-latency Groq
    7. 5-Signal persona drift update
    8. Celery background dispatch on boundary expiration
    """
    def __init__(self, db: AsyncSession):
        self.db = db
        self.retriever = MemoryRetriever(db)
        self.permanent_mgr = PermanentMemoryManager(db)
        self.persona_engine = PersonaDriftEngine(db)
        self.metacognition = MetacognitiveMonitor(fast_think_threshold=0.40, clarify_threshold=0.20)

    async def ingest_turn(self, user_id: str, role: str, content: str, timestamp: Optional[datetime] = None, source_id: Optional[str] = None, sync_consolidation: bool = False) -> None:
        """
        Directly ingests a turn into Working Memory without triggering LLM generation.
        Handles lazy session boundary checks for background consolidation.
        Used strictly by external evaluation frameworks (like LoCoMo) for pure Mode A replay.
        """
        wm = get_working_memory(user_id)
        turn_result = wm.process_incoming_turn(role, content, timestamp=timestamp, source_id=source_id)
        
        # If lazy boundary was crossed, dispatch background consolidation for the expired session
        if turn_result["session_expired"]:
            expired_transcript = "\n".join([f"{m.role} [{m.source_id}]: {m.content}" if getattr(m, 'source_id', None) else f"{m.role}: {m.content}" for m in turn_result["expired_messages"]])
            if sync_consolidation:
                from app.workers.tasks import _async_consolidate
                try:
                    await _async_consolidate(
                        user_id=user_id,
                        session_id=turn_result["expired_session_id"],
                        transcript=expired_transcript,
                        turn_count=len(turn_result["expired_messages"]),
                        session_timestamp=turn_result.get("expired_session_timestamp")
                    )
                except Exception as e:
                    logger.warning(f"Could not await sync consolidation: {e}")
            else:
                from app.workers.tasks import consolidate_session_task
                try:
                    consolidate_session_task.delay(
                        user_id=user_id,
                        session_id=turn_result["expired_session_id"],
                        transcript=expired_transcript,
                        turn_count=len(turn_result["expired_messages"]),
                        session_timestamp=turn_result.get("expired_session_timestamp")
                    )
                except Exception as e:
                    logger.warning(f"Could not dispatch async consolidation task: {e}")

    async def consolidate_active_session(self, user_id: str, session_id: Optional[str] = None) -> Optional[Dict[str, Any]]:
        """
        Directly consolidates the active working memory session into episodic and permanent memory.
        Used by benchmarks, session termination, and test harnesses.
        """
        from app.workers.tasks import _async_consolidate
        wm = get_working_memory(user_id)
        if wm.messages:
            transcript = "\n".join([f"{m.role} [{m.source_id}]: {m.content}" if getattr(m, 'source_id', None) else f"{m.role}: {m.content}" for m in wm.messages])
            sid = session_id or wm.current_session_id
            turn_count = len(wm.messages)
            session_timestamp = wm.messages[0].timestamp if wm.messages else None
            res = await _async_consolidate(user_id, sid, transcript, turn_count, session_timestamp=session_timestamp)
            wm.messages = []
            return res
        return None

    async def _resolve_attachments(self, user_id: str, attachment_ids: Optional[List[str]]):
        if not attachment_ids:
            return [], []
            
        parsed_uuids = []
        for aid in attachment_ids:
            try:
                parsed_uuids.append(uuid.UUID(str(aid)))
            except Exception:
                pass
                
        if not parsed_uuids:
            return [], []
            
        stmt = select(DocumentAttachment).where(
            DocumentAttachment.id.in_(parsed_uuids),
            DocumentAttachment.user_id == user_id
        )
        res = await self.db.execute(stmt)
        records = res.scalars().all()
        
        storage_service = get_storage_service()
        doc_contexts = []
        image_urls = []
        
        for rec in records:
            if rec.is_image:
                try:
                    file_bytes = await storage_service.get_file_bytes(rec.storage_path)
                    b64 = base64.b64encode(file_bytes).decode('utf-8')
                    image_urls.append(f"data:{rec.file_type};base64,{b64}")
                except Exception as e:
                    logger.warning(f"Could not load image bytes for {rec.id}: {e}")
            else:
                doc_contexts.append({
                    "id": str(rec.id),
                    "file_name": rec.file_name,
                    "file_type": rec.file_type,
                    "extracted_text": rec.extracted_text or ""
                })
                
        return doc_contexts, image_urls

    async def step(self, user_id: str, prompt: str, update_state: bool = True, now: Optional[datetime] = None, attachment_ids: Optional[List[str]] = None) -> Dict[str, Any]:
        wm = get_working_memory(user_id)
        doc_contexts, image_urls = await self._resolve_attachments(user_id, attachment_ids)

        if update_state:
            # 1. Process turn in working memory (lazy session boundary & rephrase detection)
            turn_result = wm.process_incoming_turn("user", prompt, timestamp=now)
            
            # If lazy boundary was crossed, dispatch background consolidation for the expired session
            if turn_result["session_expired"]:
                from app.workers.tasks import consolidate_session_task
                expired_transcript = "\n".join([f"{m.role}: {m.content}" for m in turn_result["expired_messages"]])
                try:
                    consolidate_session_task.delay(
                        user_id=user_id,
                        session_id=turn_result["expired_session_id"],
                        transcript=expired_transcript,
                        turn_count=len(turn_result["expired_messages"]),
                        session_timestamp=turn_result.get("expired_session_timestamp")
                    )
                except Exception as e:
                    logger.warning(f"Could not dispatch async consolidation task: {e}")
            is_rephrasing = turn_result["is_rephrasing"]
            rephrase_score = turn_result["rephrase_score"]
            working_msgs = wm.messages[:-1]
        else:
            # Non-mutating mode: evaluation query against fixed memory state without polluting context
            is_rephrasing, rephrase_score = wm.rephrase_detector.check_rephrasing(prompt, wm.messages)
            working_msgs = list(wm.messages)

        # 2. Check user session count for cold-start onboarding
        stmt = select(User).where(User.id == user_id)
        u_res = await self.db.execute(stmt)
        user_row = u_res.scalars().first()
        session_count = user_row.session_count if user_row else 0
        is_cold_start = (session_count < 5) if update_state else False

        # 3. Retrieve active goals
        active_goals = await self.permanent_mgr.get_active_goals(user_id)
        goals_embeddings = [g.embedding for g in active_goals if g.embedding is not None]

        # 4. Extract semantic intent & proactive memory flag
        intent_res = await self.metacognition.detect_intent(prompt, now=now)
        intent = intent_res.get("intent", "general")
        
        if intent == "blocked":
            return {
                "response": "I cannot fulfill this request due to a detected prompt injection or security policy violation.",
                "session_id": wm.current_session_id,
                "cognitive_trace": {
                    "confidence": 1.0,
                    "thinking_mode": ThinkingMode.FAST_THINK.value,
                    "mode_rationale": "Blocked prompt injection attempt.",
                    "is_rephrasing": is_rephrasing,
                    "rephrase_score": rephrase_score,
                    "retrieved_memories_count": 0,
                    "retrieved_memories": [],
                    "is_cold_start": is_cold_start,
                    "persona_signals": {}
                }
            }
            
        date_range = intent_res.get("date_range")
        requires_retrieval = intent_res.get("requires_retrieval", True)

        # 5. Multi-factor memory retrieval with temporal term (Proactive Memory)
        retrieved_memories = []
        if requires_retrieval:
            retrieved_memories = await self.retriever.retrieve(
                user_id=user_id,
                query=prompt,
                top_k=10,
                active_goals_embeddings=goals_embeddings,
                now=now,
                intent=intent,
                date_range=date_range
            )

        # 5. Metacognitive Confidence Evaluation & Mode Routing
        meta_eval = self.metacognition.estimate_confidence(
            query=prompt,
            retrieved_memories=retrieved_memories,
            is_rephrasing=is_rephrasing,
            rephrase_score=rephrase_score,
            has_active_goals=bool(active_goals)
        )
        thinking_mode: ThinkingMode = meta_eval["mode"]

        # 6. Fetch / update persona state
        persona_state = await self.persona_engine.get_or_create_profile(user_id)

        # Fetch permanent facts for identity and project context continuity
        permanent_facts = await self.permanent_mgr.get_user_facts(user_id, limit=20)

        # 7. Assemble Unified Prompt
        assembled_prompt = ContextAssembler.build_prompt(
            user_query=prompt,
            working_messages=working_msgs, # prior turns
            retrieved_memories=retrieved_memories,
            active_goals=active_goals,
            persona_state=persona_state,
            thinking_mode=thinking_mode,
            is_cold_start=is_cold_start,
            now=now,
            permanent_facts=permanent_facts,
            attached_documents=doc_contexts
        )

        # 8. Generate response via metacognitive-routed LLM provider
        if image_urls:
            response_text = await llm_router.chat(assembled_prompt, images=image_urls)
        elif thinking_mode == ThinkingMode.SLOW_THINK:
            response_text = await llm_router.background_task(assembled_prompt)
        else:
            response_text = await llm_router.chat(assembled_prompt)

        # 9. Update state if enabled
        if update_state:
            wm.add_assistant_response(response_text)
            updated_persona = await self.persona_engine.update_profile(
                user_id=user_id,
                user_prompt=prompt,
                assistant_response=response_text,
                is_rephrase=is_rephrasing,
                recent_messages=wm.messages
            )
            persona_signals = {
                "verbosity_ratio": round(updated_persona.verbosity_ratio, 3),
                "rephrasing_rate": round(updated_persona.rephrasing_rate, 3),
                "formality_score": round(updated_persona.formality_score, 3),
                "question_frequency": round(updated_persona.question_frequency, 3),
                "topic_return_rate": round(updated_persona.topic_return_rate, 3)
            }
        else:
            persona_signals = {
                "verbosity_ratio": round(persona_state.verbosity_ratio, 3),
                "rephrasing_rate": round(persona_state.rephrasing_rate, 3),
                "formality_score": round(persona_state.formality_score, 3),
                "question_frequency": round(persona_state.question_frequency, 3),
                "topic_return_rate": round(persona_state.topic_return_rate, 3)
            }

        return {
            "response": response_text,
            "session_id": wm.current_session_id,
            "cognitive_trace": {
                "confidence": meta_eval["confidence"],
                "thinking_mode": meta_eval["mode"].value,
                "mode_rationale": meta_eval["rationale"],
                "is_rephrasing": is_rephrasing,
                "rephrase_score": rephrase_score,
                "retrieved_memories_count": len(retrieved_memories),
                "retrieved_memories": [m.to_dict() for m in retrieved_memories],
                "is_cold_start": is_cold_start,
                "persona_signals": persona_signals
            }
        }

    async def step_stream(self, user_id: str, prompt: str, update_state: bool = True, now: Optional[datetime] = None, attachment_ids: Optional[List[str]] = None):
        """
        Executes the closed-loop cognitive cycle and streams response chunks in real-time.
        Yields start event, chunk events, and final complete event.
        """
        wm = get_working_memory(user_id)
        doc_contexts, image_urls = await self._resolve_attachments(user_id, attachment_ids)

        if update_state:
            turn_result = wm.process_incoming_turn("user", prompt, timestamp=now)
            if turn_result["session_expired"]:
                from app.workers.tasks import consolidate_session_task
                expired_transcript = "\n".join([f"{m.role}: {m.content}" for m in turn_result["expired_messages"]])
                try:
                    consolidate_session_task.delay(
                        user_id=user_id,
                        session_id=turn_result["expired_session_id"],
                        transcript=expired_transcript,
                        turn_count=len(turn_result["expired_messages"]),
                        session_timestamp=turn_result.get("expired_session_timestamp")
                    )
                except Exception as e:
                    logger.warning(f"Could not dispatch async consolidation task: {e}")
            is_rephrasing = turn_result["is_rephrasing"]
            rephrase_score = turn_result["rephrase_score"]
            working_msgs = wm.messages[:-1]
        else:
            is_rephrasing, rephrase_score = wm.rephrase_detector.check_rephrasing(prompt, wm.messages)
            working_msgs = list(wm.messages)

        # 2. Check user session count
        stmt = select(User).where(User.id == user_id)
        u_res = await self.db.execute(stmt)
        user_row = u_res.scalars().first()
        session_count = user_row.session_count if user_row else 0
        is_cold_start = (session_count < 5) if update_state else False

        # 3. Retrieve active goals
        active_goals = await self.permanent_mgr.get_active_goals(user_id)
        goals_embeddings = [g.embedding for g in active_goals if g.embedding is not None]

        # 4. Extract semantic intent & proactive memory flag
        intent_res = await self.metacognition.detect_intent(prompt, now=now)
        intent = intent_res.get("intent", "general")

        if intent == "blocked":
            yield {
                "type": "done",
                "response": "I cannot fulfill this request due to a detected prompt injection or security policy violation.",
                "session_id": wm.current_session_id,
                "cognitive_trace": {
                    "confidence": 1.0,
                    "thinking_mode": ThinkingMode.FAST_THINK.value,
                    "mode_rationale": "Blocked prompt injection attempt.",
                    "is_rephrasing": is_rephrasing,
                    "rephrase_score": rephrase_score,
                    "retrieved_memories_count": 0,
                    "retrieved_memories": [],
                    "is_cold_start": is_cold_start,
                    "persona_signals": {}
                }
            }
            return

        date_range = intent_res.get("date_range")
        requires_retrieval = intent_res.get("requires_retrieval", True)

        # 5. Multi-factor memory retrieval
        retrieved_memories = []
        if requires_retrieval:
            retrieved_memories = await self.retriever.retrieve(
                user_id=user_id,
                query=prompt,
                top_k=10,
                active_goals_embeddings=goals_embeddings,
                now=now,
                intent=intent,
                date_range=date_range
            )

        meta_eval = self.metacognition.estimate_confidence(
            query=prompt,
            retrieved_memories=retrieved_memories,
            is_rephrasing=is_rephrasing,
            rephrase_score=rephrase_score,
            has_active_goals=bool(active_goals)
        )
        thinking_mode: ThinkingMode = meta_eval["mode"]

        # 6. Fetch persona state
        persona_state = await self.persona_engine.get_or_create_profile(user_id)

        # Fetch permanent facts for identity and project context continuity
        permanent_facts = await self.permanent_mgr.get_user_facts(user_id, limit=20)

        # 7. Assemble Unified Prompt
        assembled_prompt = ContextAssembler.build_prompt(
            user_query=prompt,
            working_messages=working_msgs,
            retrieved_memories=retrieved_memories,
            active_goals=active_goals,
            persona_state=persona_state,
            thinking_mode=thinking_mode,
            is_cold_start=is_cold_start,
            now=now,
            permanent_facts=permanent_facts,
            attached_documents=doc_contexts
        )

        initial_trace = {
            "confidence": meta_eval["confidence"],
            "thinking_mode": meta_eval["mode"].value,
            "mode_rationale": meta_eval["rationale"],
            "is_rephrasing": is_rephrasing,
            "rephrase_score": rephrase_score,
            "retrieved_memories_count": len(retrieved_memories),
            "retrieved_memories": [m.to_dict() for m in retrieved_memories],
            "is_cold_start": is_cold_start,
            "persona_signals": {}
        }

        # Yield start event so client knows generation has begun
        yield {
            "type": "start",
            "session_id": wm.current_session_id,
            "cognitive_trace": initial_trace
        }

        # 8. Stream tokens from LLM
        chunks = []
        if image_urls:
            stream_gen = llm_router.chat_stream(assembled_prompt, images=image_urls)
        elif thinking_mode == ThinkingMode.SLOW_THINK:
            stream_gen = llm_router.background_stream(assembled_prompt)
        else:
            stream_gen = llm_router.chat_stream(assembled_prompt)
        async for chunk in stream_gen:
            if chunk:
                chunks.append(chunk)
                yield {
                    "type": "chunk",
                    "delta": chunk,
                    "session_id": wm.current_session_id
                }

        response_text = "".join(chunks)

        # 9. Update state if enabled
        if update_state:
            wm.add_assistant_response(response_text)
            updated_persona = await self.persona_engine.update_profile(
                user_id=user_id,
                user_prompt=prompt,
                assistant_response=response_text,
                is_rephrase=is_rephrasing,
                recent_messages=wm.messages
            )
            persona_signals = {
                "verbosity_ratio": round(updated_persona.verbosity_ratio, 3),
                "rephrasing_rate": round(updated_persona.rephrasing_rate, 3),
                "formality_score": round(updated_persona.formality_score, 3),
                "question_frequency": round(updated_persona.question_frequency, 3),
                "topic_return_rate": round(updated_persona.topic_return_rate, 3)
            }
        else:
            persona_signals = {
                "verbosity_ratio": round(persona_state.verbosity_ratio, 3),
                "rephrasing_rate": round(persona_state.rephrasing_rate, 3),
                "formality_score": round(persona_state.formality_score, 3),
                "question_frequency": round(persona_state.question_frequency, 3),
                "topic_return_rate": round(persona_state.topic_return_rate, 3)
            }

        initial_trace["persona_signals"] = persona_signals

        yield {
            "type": "done",
            "response": response_text,
            "session_id": wm.current_session_id,
            "cognitive_trace": initial_trace
        }

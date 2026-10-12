from typing import List, Optional, Dict, Any
from datetime import datetime, timezone
from app.memory.retrieval import ScoredMemory
from app.memory.working import Message
from app.db.models import Goal, PermanentMemory
from app.persona.state import PersonaState
from app.brain.metacognition import ThinkingMode

class ContextAssembler:
    """
    Assembles episodic and permanent memories, working context (capped 20 turns),
    active goals, persona directives, and metacognitive mode directives into a unified prompt.
    """
    @staticmethod
    def build_prompt(
        user_query: str,
        working_messages: List[Message],
        retrieved_memories: List[ScoredMemory],
        active_goals: List[Goal],
        persona_state: PersonaState,
        thinking_mode: ThinkingMode,
        is_cold_start: bool = False,
        now: Optional[datetime] = None,
        permanent_facts: Optional[List[PermanentMemory]] = None,
        attached_documents: Optional[List[Dict[str, Any]]] = None
    ) -> str:
        sections = []

        curr_dt = now if now else datetime.now(timezone.utc)
        time_grounding = curr_dt.strftime("%A, %B %d, %Y (%Y-%m-%d %H:%M UTC)")

        # 1. System Role, Temporal Ground Truth & Baseline
        sections.append(
            f"You are CognAI, an adaptive cognitive companion with long-term memory.\n"
            f"CURRENT SYSTEM DATE & TIME: {time_grounding}\n"
            f"TEMPORAL GROUND TRUTH DIRECTIVE: Today is {time_grounding}. Always evaluate temporal references ('today', 'yesterday', 'this week', 'this year', 'upcoming', 'recent', 'next year') relative to this current date. Do NOT assume an outdated model cutoff year when answering questions or recommending upcoming conferences, events, or deadlines.\n"
            "CRITICAL INSTRUCTION: You must distinguish between personal memory queries and general knowledge queries.\n"
            "1. For personal questions about the user's life, events, projects, preferences, or past conversations: "
            "you MUST base your answers STRICTLY on the RELEVANT MEMORIES section below. "
            "If RELEVANT MEMORIES contains ANY information that answers (even partially) the question, "
            "you MUST state that information clearly and directly — do NOT say 'I don't know', 'I don't have that information', "
            "or 'that wasn't mentioned'. Quote or paraphrase the memory content. "
            "Do NOT ask the user to repeat information already in RELEVANT MEMORIES.\n"
            "2. For general knowledge, advice, brainstorming, or casual chat, you may freely use your general world knowledge to assist the user.\n"
            "3. If genuinely no relevant memory exists for a personal question, briefly acknowledge this and "
            "offer to help in a different way — but only after thoroughly checking ALL sections of RELEVANT MEMORIES."
        )

        # 2. Metacognitive Mode Instruction
        if thinking_mode == ThinkingMode.SLOW_THINK:
            sections.append(
                "[MODE: DELIBERATIVE SLOW-THINK]\n"
                "Confidence is moderate. Reason methodically step-by-step. Explicitly cross-check facts "
                "against the retrieved memories below, test your assumptions, and formulate a well-structured response."
            )
        elif thinking_mode == ThinkingMode.CLARIFY:
            sections.append(
                "[MODE: CLARIFYING INQUIRY]\n"
                "Confidence is low or the user's intent is ambiguous. Do not speculate or hallucinate. "
                "Formulate a concise, courteous clarifying question to determine the user's exact goal."
            )

        # 3. Cold Start Onboarding Directive (if user < 5 sessions)
        if is_cold_start:
            sections.append(
                "[COLD-START ONBOARDING ACTIVE]\n"
                "The user is relatively new. While learning their style, do NOT ask repetitive questions or ask for details they already specified in RELEVANT MEMORIES, PERMANENT KNOWLEDGE, or prior turns. Directly answer their query with full context."
            )

        # 4. Persona Directives (5-Signal Engine)
        persona_directive = persona_state.generate_prompt_directive()
        if persona_directive:
            sections.append(f"[{persona_directive}]")

        # 5. Permanent User Facts (Identity, Domain & Background)
        if permanent_facts:
            fact_lines = [f"- [{f.category.upper()}] {f.fact}" for f in permanent_facts]
            sections.append("PERMANENT USER KNOWLEDGE (Core Profile, Identity & Established Background):\n" + "\n".join(fact_lines))

        # 6. Active User Goals
        if active_goals:
            goal_lines = [f"- {g.title}: {g.description or ''}" for g in active_goals]
            sections.append("USER'S ACTIVE GOALS:\n" + "\n".join(goal_lines))

        # 6. Retrieved Long-Term & Episodic Memories (with temporal relevance)
        if retrieved_memories:
            mem_lines = []
            for mem in retrieved_memories:
                time_anchor = ""
                if mem.created_at:
                    c_dt = mem.created_at if mem.created_at.tzinfo else mem.created_at.replace(tzinfo=timezone.utc)
                    time_anchor = f" [Anchor Date: {c_dt.strftime('%Y-%m-%d (%A, %B %d, %Y)')}]"
                mem_lines.append(f"- [{mem.memory_type.upper()}{time_anchor}] {mem.content}")
            sections.append(
                "RELEVANT MEMORIES (Retrieved from Long-Term Memory):\n"
                "TEMPORAL REASONING & CALENDAR ARITHMETIC RULES:\n"
                "1. Each memory indicates its [Anchor Date]. When a memory mentions relative time expressions ('yesterday', 'last week', 'last month', 'next month', 'last year', 'N years ago'), you MUST explicitly calculate and state the exact calendar date, month, or year relative to that memory's [Anchor Date], NOT relative to today's date!\n"
                "2. Specific Calendar Arithmetic Rules:\n"
                "   - 'last year' relative to Anchor Date year Y -> explicitly calculate and state the exact year (Y - 1). (e.g., Anchor Date in May 2023 + 'last year' = exactly 2022. State 'in 2022').\n"
                "   - 'yesterday' relative to Anchor Date -> calculate (Anchor Date - 1 day). (e.g., Anchor Date 8 May 2023 + 'yesterday' = '7 May 2023').\n"
                "   - 'N years ago' relative to Anchor Date year Y -> explicitly output the year (Y - N).\n"
                "   - 'next month' relative to Anchor Date month M -> state the name of month (M + 1).\n"
                "3. In answers to temporal questions ('When did...?', 'What year...?'), always explicitly include the calculated exact calendar year or date in the answer.\n" +
                "\n".join(mem_lines)
            )

        # 7. Working Memory Context (Recent 20 Turns)
        if working_messages:
            history_lines = [f"{m.role.capitalize()}: {m.content}" for m in working_messages]
            sections.append("CONVERSATION CONTEXT (Working Memory):\n" + "\n".join(history_lines))

        # 8. Attached Documents Context (PDF, DOCX, TXT, etc.)
        if attached_documents:
            doc_lines = []
            for doc in attached_documents:
                doc_lines.append(f"--- Document: {doc['file_name']} ({doc.get('file_type', 'document')}) ---\n{doc.get('extracted_text', '')}\n--- End of {doc['file_name']} ---")
            sections.append("ATTACHED DOCUMENTS CONTEXT:\n" + "\n\n".join(doc_lines))

        # 9. Final User Query
        sections.append(f"User: {user_query}\nAssistant:")

        return "\n\n".join(sections)

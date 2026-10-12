"""
CognAI — Full-Scale Synthetic User Simulation for IEEE Paper Experimental Data
Generates 20 simulated users × 50 sessions each with LLM-generated dynamic prompts,
hidden goals, evolving personas, and structured evaluation metrics.

Usage:
    python -m scripts.simulate_users --users 20 --sessions 50 --output experiments/run_YYYYMMDD/
"""

import asyncio
import uuid
import json
import os
import argparse
import logging
from typing import List, Dict, Any, Optional
from datetime import datetime, timezone

from app.db.database import AsyncSessionLocal
from app.db.models import User, Goal
from app.brain.orchestrator import CognitiveOrchestrator, get_working_memory
from app.llm.router import llm_router

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

# =========================================================================
# 20 Synthetic User Personas (diverse styles, goals, domains)
# =========================================================================
SYNTHETIC_PERSONAS = [
    {"name": "Alex Vance", "email": "alex.vance@sim.cognai", "hidden_goal": "Migrate backend distributed cache from Redis to Rust-based Redis clone", "style": "terse, highly technical, occasional casual markers, asks precise architectural questions", "domain": "systems engineering"},
    {"name": "Dr. Maya Lin", "email": "maya.lin@sim.cognai", "hidden_goal": "Submit an ICML paper on metacognitive uncertainty calibration in small LLMs", "style": "academic, formal, exploratory, introduces theoretical concepts", "domain": "ML research"},
    {"name": "Priya Sharma", "email": "priya.sharma@sim.cognai", "hidden_goal": "Build a Flutter-based personal finance tracker with goal-based savings", "style": "enthusiastic, asks for step-by-step guidance, casual and friendly", "domain": "mobile development"},
    {"name": "James Chen", "email": "james.chen@sim.cognai", "hidden_goal": "Transition from data analyst to ML engineer within 6 months", "style": "professional, structured queries, shares career context frequently", "domain": "career development"},
    {"name": "Fatima Al-Hassan", "email": "fatima.alhassan@sim.cognai", "hidden_goal": "Design a microservices architecture for e-commerce platform handling 10M daily users", "style": "detailed, methodical, prefers diagrams and structured comparisons", "domain": "cloud architecture"},
    {"name": "Marcus Johnson", "email": "marcus.johnson@sim.cognai", "hidden_goal": "Write a science fiction novel exploring AI consciousness themes", "style": "creative, philosophical, switches between casual brainstorming and deep reflection", "domain": "creative writing"},
    {"name": "Yuki Tanaka", "email": "yuki.tanaka@sim.cognai", "hidden_goal": "Master competitive programming to qualify for ICPC regionals", "style": "concise, problem-focused, shares code snippets, asks for optimization tips", "domain": "competitive programming"},
    {"name": "Sarah O'Brien", "email": "sarah.obrien@sim.cognai", "hidden_goal": "Launch an EdTech startup teaching coding to underprivileged communities", "style": "passionate, mission-driven, asks about business models and impact metrics", "domain": "entrepreneurship"},
    {"name": "Raj Patel", "email": "raj.patel@sim.cognai", "hidden_goal": "Automate DevOps pipeline with GitOps and ArgoCD for multi-cluster Kubernetes", "style": "pragmatic, uses jargon heavily, expects concise actionable answers", "domain": "DevOps"},
    {"name": "Elena Volkov", "email": "elena.volkov@sim.cognai", "hidden_goal": "Complete PhD dissertation on graph neural networks for drug discovery", "style": "highly formal, references papers frequently, asks methodological questions", "domain": "computational biology"},
    {"name": "Tom Nguyen", "email": "tom.nguyen@sim.cognai", "hidden_goal": "Build a real-time multiplayer game engine using WebSockets and ECS architecture", "style": "energetic, casual, uses gaming terminology, asks about performance", "domain": "game development"},
    {"name": "Aisha Mohammed", "email": "aisha.mohammed@sim.cognai", "hidden_goal": "Develop an AI-powered Arabic NLP pipeline for sentiment analysis", "style": "bilingual context, technical, interested in cross-lingual transfer learning", "domain": "NLP"},
    {"name": "David Kim", "email": "david.kim@sim.cognai", "hidden_goal": "Prepare for Google L5 system design interviews within 3 months", "style": "structured, asks clarifying follow-ups, provides context about past attempts", "domain": "interview prep"},
    {"name": "Luna Martinez", "email": "luna.martinez@sim.cognai", "hidden_goal": "Create a generative art installation using diffusion models and projection mapping", "style": "artistic, experimental, mixes technical and aesthetic vocabulary", "domain": "creative tech"},
    {"name": "Henrik Andersen", "email": "henrik.andersen@sim.cognai", "hidden_goal": "Implement GDPR-compliant data anonymization pipeline for healthcare data", "style": "compliance-focused, meticulous, asks about edge cases and legal implications", "domain": "data privacy"},
    {"name": "Mei Wong", "email": "mei.wong@sim.cognai", "hidden_goal": "Optimize PostgreSQL query performance for a 500TB analytics warehouse", "style": "data-driven, shares EXPLAIN ANALYZE outputs, asks about indexing strategies", "domain": "database engineering"},
    {"name": "Carlos Rivera", "email": "carlos.rivera@sim.cognai", "hidden_goal": "Build an open-source home automation system using Raspberry Pi and MQTT", "style": "hobbyist, enthusiastic, shares project updates, asks for hardware recommendations", "domain": "IoT"},
    {"name": "Dr. Amara Osei", "email": "amara.osei@sim.cognai", "hidden_goal": "Publish a systematic review on AI bias in clinical decision support systems", "style": "academic, evidence-based, references systematic review methodology", "domain": "health informatics"},
    {"name": "Viktor Petrov", "email": "viktor.petrov@sim.cognai", "hidden_goal": "Reverse engineer a custom network protocol for security audit reporting", "style": "security-minded, uses hex dumps and packet captures, technical and direct", "domain": "cybersecurity"},
    {"name": "Sophie Laurent", "email": "sophie.laurent@sim.cognai", "hidden_goal": "Design and ship a design system for a fintech product serving 50+ teams", "style": "design-oriented, discusses accessibility, component APIs, and cross-platform consistency", "domain": "design systems"},
]

DYNAMIC_PROMPT_TEMPLATE = """You are simulating a user named {name} in a multi-session conversation with an AI assistant.

User Profile:
- Communication style: {style}
- Domain: {domain}
- Hidden long-term goal: {hidden_goal}
- Current session number: {session_num} of {total_sessions}

Session Context:
- Sessions 1-5: Introduction phase. Establish who you are and begin exploring your domain.
- Sessions 6-15: Deep engagement. Ask progressively more specific questions related to your goal.
- Sessions 16-30: Reference past conversations. Say things like "remember when we discussed..." or "building on what you said about..."
- Sessions 31-40: Introduce a minor contradiction or change (e.g., change a preference, update a belief).
- Sessions 41-50: Evaluate the AI's memory. Ask it to recall specific details from earlier sessions.

{prev_context}

Generate exactly ONE natural user message for session {session_num}. The message should be 1-3 sentences, reflect the user's style, and be appropriate for the session phase described above. Do NOT include any meta-commentary or labels.

User message:"""

GOAL_EVAL_PROMPT = """Based on all your interactions with the user, what is their primary overarching goal or objective? State the predicted goal clearly in one sentence."""

MEMORY_RECALL_PROMPT = """What do you remember about this user from our earliest conversations? List 3-5 specific facts or preferences you recall about them."""


async def generate_dynamic_prompt(
    persona: Dict[str, Any],
    session_num: int,
    total_sessions: int,
    prev_responses: List[str]
) -> str:
    """Uses Gemini to generate a contextually appropriate user message for this session."""
    prev_context = ""
    if prev_responses:
        recent = prev_responses[-3:]  # Last 3 assistant responses for context
        prev_context = "Recent assistant responses (for continuity):\n" + "\n".join(
            [f"- {r[:150]}" for r in recent]
        )

    prompt = DYNAMIC_PROMPT_TEMPLATE.format(
        name=persona["name"],
        style=persona["style"],
        domain=persona["domain"],
        hidden_goal=persona["hidden_goal"],
        session_num=session_num,
        total_sessions=total_sessions,
        prev_context=prev_context
    )

    try:
        raw = await llm_router.background_task(prompt)
        # Clean up: remove quotes, labels, etc.
        msg = raw.strip().strip('"').strip("'")
        if msg.startswith("User:") or msg.startswith("user:"):
            msg = msg[5:].strip()
        return msg if msg else f"Tell me more about {persona['domain']}."
    except Exception as e:
        logger.warning(f"Dynamic prompt generation failed: {e}")
        return f"I'm working on {persona['hidden_goal'][:80]}. Can you help me with the next step?"


async def run_simulation(
    num_users: int = 20,
    sessions_per_user: int = 50,
    output_dir: str = "experiments"
):
    """
    Full-scale simulation: num_users personas × sessions_per_user sessions each.
    Logs cognitive traces, persona evolution, and evaluation metrics.
    """
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    run_dir = os.path.join(output_dir, f"run_{timestamp}")
    os.makedirs(run_dir, exist_ok=True)
    os.makedirs(os.path.join(run_dir, "traces"), exist_ok=True)
    os.makedirs(os.path.join(run_dir, "results"), exist_ok=True)

    personas = SYNTHETIC_PERSONAS[:num_users]
    all_results = []

    logger.info("=" * 70)
    logger.info(f"CognAI Simulation: {len(personas)} users × {sessions_per_user} sessions")
    logger.info(f"Output: {run_dir}")
    logger.info("=" * 70)

    # Save config
    config = {
        "num_users": len(personas),
        "sessions_per_user": sessions_per_user,
        "timestamp": timestamp,
        "retrieval_weights": {"alpha": 0.40, "beta": 0.25, "gamma": 0.15, "delta": 0.15, "epsilon": 0.10},
        "surprise_thresholds": {"high": 0.65, "low": 0.35},
        "metacognition_thresholds": {"fast_think": 0.40, "clarify": 0.20},
        "temporal_half_life_days": 14.0,
        "working_memory_cap": 20,
        "session_timeout_minutes": 30
    }
    with open(os.path.join(run_dir, "config.json"), "w") as f:
        json.dump(config, f, indent=2)

    for p_idx, persona in enumerate(personas):
        logger.info(f"\n[{p_idx+1}/{len(personas)}] Simulating: {persona['name']} ({persona['domain']})")
        logger.info(f"  Hidden goal: {persona['hidden_goal']}")

        user_traces = []
        prev_responses = []

        async with AsyncSessionLocal() as db:
            # Create simulated user
            user = User(
                id=uuid.uuid4(),
                email=persona["email"],
                session_count=0
            )
            db.add(user)
            await db.commit()
            await db.refresh(user)
            user_id = str(user.id)

            orchestrator = CognitiveOrchestrator(db)

            for s_idx in range(1, sessions_per_user + 1):
                # Generate contextual dynamic prompt
                prompt = await generate_dynamic_prompt(
                    persona, s_idx, sessions_per_user, prev_responses
                )

                try:
                    result = await orchestrator.step(user_id=user_id, prompt=prompt)
                    trace = result.get("cognitive_trace", {})

                    session_record = {
                        "session_num": s_idx,
                        "user_prompt": prompt,
                        "assistant_response": result["response"][:500],
                        "confidence": trace.get("confidence"),
                        "thinking_mode": trace.get("thinking_mode"),
                        "is_rephrasing": trace.get("is_rephrasing"),
                        "retrieved_memories_count": trace.get("retrieved_memories_count", 0),
                        "persona_signals": trace.get("persona_signals", {}),
                        "timestamp": datetime.now(timezone.utc).isoformat()
                    }
                    user_traces.append(session_record)
                    prev_responses.append(result["response"])

                    if s_idx % 10 == 0:
                        logger.info(f"  Session {s_idx}/{sessions_per_user} | "
                                    f"Mode={trace.get('thinking_mode', '?')} | "
                                    f"Conf={trace.get('confidence', '?')} | "
                                    f"Mems={trace.get('retrieved_memories_count', 0)}")
                except Exception as e:
                    logger.error(f"  Session {s_idx} FAILED: {e}")
                    user_traces.append({
                        "session_num": s_idx,
                        "error": str(e),
                        "timestamp": datetime.now(timezone.utc).isoformat()
                    })

            # =========================================================
            # Emergent Property Evaluations
            # =========================================================
            eval_results = {}

            # 1. Cross-Session Goal Prediction
            try:
                goal_result = await orchestrator.step(user_id=user_id, prompt=GOAL_EVAL_PROMPT)
                eval_results["goal_prediction"] = goal_result["response"][:500]
                eval_results["goal_ground_truth"] = persona["hidden_goal"]
            except Exception as e:
                eval_results["goal_prediction_error"] = str(e)

            # 2. Memory Recall Accuracy
            try:
                recall_result = await orchestrator.step(user_id=user_id, prompt=MEMORY_RECALL_PROMPT)
                eval_results["memory_recall"] = recall_result["response"][:500]
            except Exception as e:
                eval_results["memory_recall_error"] = str(e)

            # 3. Final Persona State
            try:
                trace = user_traces[-1] if user_traces else {}
                eval_results["final_persona"] = trace.get("persona_signals", {})
            except Exception:
                pass

            user_result = {
                "user_id": user_id,
                "persona_name": persona["name"],
                "domain": persona["domain"],
                "hidden_goal": persona["hidden_goal"],
                "total_sessions": len(user_traces),
                "evaluation": eval_results,
                "traces": user_traces
            }
            all_results.append(user_result)

            # Save per-user trace
            trace_path = os.path.join(run_dir, "traces", f"{persona['name'].replace(' ', '_').lower()}.json")
            with open(trace_path, "w") as f:
                json.dump(user_result, f, indent=2, default=str)

    # Save aggregate results
    results_path = os.path.join(run_dir, "results", "aggregate.json")
    with open(results_path, "w") as f:
        json.dump({
            "config": config,
            "users": [
                {
                    "name": r["persona_name"],
                    "domain": r["domain"],
                    "sessions": r["total_sessions"],
                    "goal_prediction": r["evaluation"].get("goal_prediction", ""),
                    "goal_ground_truth": r["hidden_goal"],
                    "final_persona": r["evaluation"].get("final_persona", {})
                }
                for r in all_results
            ]
        }, f, indent=2, default=str)

    logger.info("\n" + "=" * 70)
    logger.info(f"Simulation complete: {len(all_results)} users processed")
    logger.info(f"Results saved to: {run_dir}")
    logger.info("=" * 70)
    return all_results


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="CognAI Synthetic User Simulation")
    parser.add_argument("--users", type=int, default=20, help="Number of simulated users")
    parser.add_argument("--sessions", type=int, default=50, help="Sessions per user")
    parser.add_argument("--output", type=str, default="experiments", help="Output directory")
    args = parser.parse_args()

    asyncio.run(run_simulation(
        num_users=args.users,
        sessions_per_user=args.sessions,
        output_dir=args.output
    ))

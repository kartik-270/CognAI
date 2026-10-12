# CognAI — Product Requirements Document (PRD)

## 1. Introduction
CognAI is an intelligent, personalized cognitive companion built on the premise of continuous learning and growth through user interaction. Unlike standard conversational agents that suffer from "goldfish memory" or context-window overflow, CognAI is designed to maintain long-term, coherent, and deeply personalized relationships with users. It achieves this by mimicking human neurobiology: separating working memory, episodic memory, and permanent semantic schemas into a dynamic, active reconstruction process that evolves alongside the user.

## 2. Problem Statement
Current LLM agents and basic RAG architectures fail at long-term continuity due to several critical limitations:
- **Blind Merge & Contradictions**: RAG systems blindly append new facts. Over time, the context gets polluted with contradictory information (e.g., "User is a Python developer" vs "User switched to Rust"), leading to degraded reasoning.
- **Passive Memory**: Current systems only retrieve information when explicitly queried. They lack the curiosity or proactive mechanisms to detect stalled goals or unresolved conversational threads.
- **Persona Drift**: Pre-prompted personas quickly degrade over long multi-turn conversations. Models regress to a baseline tone and verbosity.
- **The Cold Start Problem**: Clustering algorithms (like HDBSCAN) used for memory consolidation fail on sparse data for new users, rendering the agent generic for the first several sessions.
- **API Rate Limits**: Heavy background memory consolidation and entity extraction tasks often cause silent failures when strict rate limits (e.g., Groq's 30 RPM) are exceeded during peak concurrency.

## 3. Solution Overview
CognAI implements a **closed-loop cognitive system** to resolve these bottlenecks:
- **Metacognitive Self-Monitoring**: A "Thinking Governor" that evaluates confidence (e.g., < 0.4 triggers slow-think, < 0.2 triggers clarifying question).
- **Surprise-Gated Consolidation**: Prioritizes unexpected interactions for permanent encoding using Cosine Distance against historical prior centroids.
- **Onboarding Bootstrap (Cold Start Fix)**: Actively solicits goals and preferences during the first 5 sessions, seeding permanent memory immediately without waiting for density clustering.
- **Rate-Limited Background Workers**: Decoupling real-time chat from heavy extraction tasks. Chat uses Groq; asynchronous consolidation uses Gemini 2.0 Flash / Qwen, throttled via Celery to ensure system stability.
- **Emotional Valence Tagging**: Modulating memory retrieval based on the emotional intensity of the session, derived from a manually validated (-1.0 to +1.0) scoring rubric.
- **Strict Privacy**: Row-level tenant isolation with a two-phase `/forget-me` transaction that sets a `deletion_pending` flag and queues a retry worker to guarantee cascading deletes across vectors and graph nodes.

## 4. System Architecture
- **Language Models**: Unified multi-provider engine (OpenAI, Anthropic, Gemini, Groq, Qwen).
- **Embeddings**: `BAAI/bge-m3` (1024-dim dense vectors).
- **Vector Storage**: PostgreSQL with `pgvector` extension.
- **Graph Storage**: Neo4j Community Edition (for entity-relation triples).
- **Workflow Orchestration**: LangGraph.
- **Backend**: FastAPI with standard HTTP and WebSocket streaming.
- **Task Queue**: Celery with Redis broker.

## 5. Phased Implementation Scope (12-Week Honest Priority Stack)

**Phase 1: Core Infrastructure (Weeks 1–3)**
- Setup unified LLM core router (Groq for chat, Gemini/Qwen for background).
- Establish vector schema (`vector(1024)` + emotional tags).
- Implement JWT Authentication (Email & Google OAuth2).
- Enforce 20-turn working memory cap.

**Phase 2: Memory & Cognitive Triggers (Weeks 4–6)**
- Episodic storage with emotional valence tagging (using constrained LLM prompt rubrics).
- 30-minute session boundaries (triggered lazily on the next message, not via blind timers).
- Temporal retrieval weighting.
- 5-signal implicit Persona drift engine.

**Phase 3: Metacognition & Consolidation (Weeks 7–9)**
- Metacognitive layer for confidence scoring and fast/slow overrides.
- Semantic contradiction detection during consolidation.
- Rate-limited Celery worker deployment.

**Phase 4: Research Experiments & Evaluation (Weeks 10–12)**
- Synthetic data generation (100 sessions via User Simulator script).
- LongMemEval benchmarking.
- Closed-loop experiment ablation runs.
- **Emergent Evaluation Metric**: Measuring cross-session goal prediction accuracy to prove the integrated system outperforms single-module baselines.

## 6. Out of Scope (Post-Publication / Phase 5+)
- Multi-granularity Memory Consolidation (extracting schemas from themes).
- Personalized PageRank (PPR) Graph Retrieval.
- Proactive Curiosity-Driven Memory triggers during chat.

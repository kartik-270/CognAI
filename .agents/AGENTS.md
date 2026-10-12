# Agent Boundaries & Development Guidelines (CognAI)

These rules apply to all AI agents assisting in the development, modification, or architecture of the CognAI project.

## 1. Strict Terminology Constraint
- **NEVER** use words like "free", "zero-cost", "free tier", "complimentary", or "no cost" anywhere in the codebase, documentation, schemas, or comments.
- Use appropriate terms like "Open-Source", "Community Edition", "Self-Hosted", "Local Runtime", "Managed Endpoint", or "Public Tier".

<!-- ## 2. Priority Stack Discipline
- Stick strictly to the "Honest Priority Stack" defined for the 12-week sprint detailed in `cognai-implementation-plan.md`.
- **Do NOT** attempt to implement Personalized PageRank (PPR) Graph Retrieval, Multi-granularity schemas, or Proactive Memory during the core development phases. These are deferred to Phase 5 (Post-Publication).
- Focus first on: Contradiction Detection, Session Boundary Logic, Working Memory Cap, Temporal Retrieval Term, 5-Signal Persona Drift, and Metacognitive Confidence Score. -->

## 3. Authentication & Privacy
- All authentication must be routed through manual **Email** and **Google Provider (OAuth2)**, resulting in the issuance of a JWT.
- Ensure strict row-level isolation for `user_id` in PostgreSQL and Neo4j queries.
- Always include the `/forget-me` cascading delete logic when modifying data deletion pathways.

## 4. API & Resource Management
- **Groq API**: Reserved strictly for low-latency, user-facing chat responses.
- **Gemini 2.0 Flash / Qwen 2.5**: Used for all background consolidation, entity extraction, and goal inference tasks.
- **Celery Limits**: All Celery tasks that invoke LLMs MUST have strict `rate_limit` decorators (e.g., `10/m`) to prevent silent LLM API rate limit failures.

## 5. Architecture Standards
- **Embeddings**: Only use `BAAI/bge-m3` returning 1024-dimensional vectors.
- **PostgreSQL Schema**: Ensure all vector columns are `vector(1024)`. Do NOT revert to 384-dimensional models.
- **Emotional Tagging**: Ensure episodic memories properly include `emotional_valence` and `emotional_intensity`.

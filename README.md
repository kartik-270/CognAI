# CognAI

**A Research-Grounded, Mobile-First Cognitive Companion**

CognAI is an advanced cognitive AI architecture designed to move beyond simple Retrieval-Augmented Generation (RAG). It implements a **closed-loop feedback system** utilizing biologically-inspired memory hierarchies, metacognitive self-monitoring, and dynamic persona adaptation. 

Unlike standard conversational agents that suffer from "goldfish memory" or context-window overflow, CognAI maintains long-term, coherent relationships with users by separating working memory, episodic memory, and permanent semantic schemas into a dynamic, active reconstruction process.

---

## Key Innovations

1. **Surprise-Gated Consolidation**: Uses Cosine Distance to measure episodic surprise against a user's historical prior, triggering prioritized memory consolidation for unexpected interactions.
2. **Goal-Conditioned Forgetting**: Simulates hippocampal tagging by slowing the decay rate of memories relevant to active inferred goals.
3. **Metacognitive Monitor**: A "Thinking Governor" that evaluates response confidence, detects contradictions, and dynamically shifts between fast and slow reasoning modes.
4. **Emotional Valence Tagging**: Modulates memory retrieval and decay based on the affective intensity and valence of the interaction.
5. **Closed-Loop Persona Drift**: Online adaptation of the AI's interaction style based on 5 implicit, high-signal user behaviors (verbosity, rephrasing, casual markers, question frequency, topic return rate).

---

## Architecture Stack

### LLM & Intelligence
- **Core LLM Library**: Unified multi-provider engine (OpenAI, Anthropic, Gemini, Groq, Qwen).
- **Real-Time Reasoning**: Groq API (Llama 3.3 70B & 3.1 8B Instant) – Reserved strictly for low-latency chat.
- **Background Processing**: Google Gemini 2.0 Flash / Local Qwen 2.5 – Handles memory consolidation, entity extraction, and goal inference to protect chat API rate limits.
- **Orchestration**: LangGraph state machine.

### Memory & Persistence
- **Embeddings**: `BAAI/bge-m3` (1024-dimensional dense vectors).
- **Vector DB**: PostgreSQL + pgvector (`vector(1024)`) for episodic and permanent memory.
- **Graph DB**: Neo4j Community Edition for storing entity-relation triples.
- **Cache & Message Broker**: Redis.

### Infrastructure & Mobile
- **Backend API**: FastAPI (Python).
- **Background Workers**: Celery + Redis (Strictly rate-limited to `10/m`).
- **Authentication**: JWT secured via manual Email and Google Provider (OAuth2).
- **Mobile Client**: Flutter.

---

## Security & Privacy
- **Authentication**: Standardized Email & Google OAuth2 flow issuing secure JWTs for WebSocket streaming.
- **Tenant Isolation**: Strict row-level isolation by `user_id` across PostgreSQL and Neo4j.
- **Compliance**: A fully implemented `/forget-me` endpoint triggering cascading deletes of all episodic data, permanent memories, and graph triples for the requesting user.

---

## Setup & Local Development

### Prerequisites
- Docker & Docker Compose
- Python 3.10+
- Node/Flutter SDK (for mobile client)

### Environment Variables (`.env`)
```env
# LLM API Keys
GROQ_API_KEY=your_groq_key
GEMINI_API_KEY=your_gemini_key
# QWEN_API_KEY=your_qwen_key 

# Databases
DATABASE_URL=postgresql://postgres:postgres@localhost:5432/cognai
REDIS_URL=redis://localhost:6379/0
NEO4J_URI=bolt://localhost:7687
NEO4J_USER=neo4j
NEO4J_PASSWORD=password
```

### Running the Services
```bash
# 1. Start Infrastructure (PostgreSQL, pgvector, Redis, Neo4j)
docker-compose up -d

# 2. Run Database Migrations
alembic upgrade head

# 3. Start FastAPI Backend
uvicorn cognai.api.main:app --reload --port 8000

# 4. Start Celery Worker (Rate-limited background consolidation)
celery -A cognai.workers.celery_app worker --loglevel=info
```

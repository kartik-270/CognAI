# CognAI — A Research-Grounded Cognitive Companion

CognAI is an intelligent, personalized cognitive companion built on the premise of **continuous learning and growth through user interaction**. Unlike standard conversational agents that suffer from context-window overflow or static personas, CognAI is designed to maintain long-term, coherent, and deeply personalized relationships. It achieves this by mimicking human neurobiology: separating working memory, episodic memory, and permanent semantic schemas into a dynamic, active reconstruction process.

## Core Cognitive Architecture

1. **Surprise-Gated Consolidation**: The AI only remembers what matters. By mathematically measuring "surprise" against historical knowledge, it selectively permanently encodes novel or contradictory information.
2. **5-Signal Persona Drift**: The AI implicitly analyzes your verbosity, formality, and inquiry rates. Over time, its own personality naturally drifts to mirror your communication style.
3. **Goal-Conditioned Forgetting**: Memories degrade dynamically based on their relevance to your current life goals, preventing the AI from fixating on outdated context.
4. **Emotional Valence Tagging**: The system maps the emotional intensity of conversations, allowing it to proactively adjust its empathy and tone over time.
5. **Metacognitive Monitor**: The AI possesses a "Thinking Governor." When uncertainty is high, it deliberately shifts into "slow-think" mode or actively asks you clarifying questions.

## Technology Stack

### Backend (FastAPI)
- **Framework**: FastAPI (Python 3.10)
- **Database**: PostgreSQL with `pgvector` (`bge-m3` 1024-dim dense vectors)
- **Graph DB**: Neo4j Community Edition (for semantic schemas)
- **Caching & Brokers**: Redis
- **Background Processing**: Celery (Rate-limited for API safety)
- **LLM Routing**: 
  - **Chat**: Groq (Low-latency real-time reasoning)
  - **Background**: Gemini 2.0 Flash / Qwen 2.5 (Memory consolidation & schemas)
- **Auth**: Native JWT via Email & Google OAuth2

### Frontend (Flutter)
- **Framework**: Flutter (iOS & Android compatible)
- **State Management**: Riverpod (for reactive WebSocket streams)
- **Design System**: "Luminous Minimal" (Quiet Premium aesthetic)
- **Network**: WebSockets (Real-time chat + metacognitive indicators) with automatic reconnection.

## Infrastructure & DevOps

The project includes a robust DevOps pipeline. To initialize the backend stack locally:

```bash
# 1. Start the databases and Redis
make up

# 2. View container logs
make logs
```

### Environment Setup (`.env`)
You must provide the following variables for the backend to function:
```env
# Databases
POSTGRES_USER=postgres
POSTGRES_PASSWORD=postgrespassword
POSTGRES_DB=cognai

NEO4J_USER=neo4j
NEO4J_PASSWORD=neo4jpassword

# LLMs
GROQ_API_KEY=your_groq_key
GEMINI_API_KEY=your_gemini_key

# Auth
GOOGLE_CLIENT_ID=your_google_oauth_client_id
GOOGLE_CLIENT_SECRET=your_google_oauth_secret
```

### Starting the Backend
```bash
cd backend
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
pip install -r requirements.txt
uvicorn app.api.main:app --reload
```

### Starting the Frontend
```bash
cd frontend/cognai_app
flutter pub get
flutter run
```
### Database commands
```bash

make db-migrate m="Add chat_messages table"
make db-upgrade


  ```
db-migrate:
	docker-compose exec backend alembic revision --autogenerate -m "$(m)"
db-upgrade:
	docker-compose exec backend alembic upgrade head


## Repository Structure
- `backend/`: FastAPI core, Celery workers, LangGraph orchestrator, and Database models.
- `frontend/cognai_app/`: Feature-first Flutter application utilizing Riverpod and local assets.
- `terraform/`: Infrastructure-as-code for AWS deployment.
- `docker-compose.yml`: Local orchestrator for PostgreSQL (pg16 + pgvector), Neo4j, and Redis.

## Privacy Note
CognAI is built with strict row-level isolation per user. It features a transactional `/forget-me` compliance endpoint that guarantees a two-phase cascading delete of all vectors, graph nodes, and episodic data across the system.

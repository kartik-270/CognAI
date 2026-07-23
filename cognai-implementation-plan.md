# CognAI — Detailed Implementation Plan
> Unified Stack · Research-Grounded · Mobile-First Cognitive Companion

---

## Open-Source & Unified Resource Stack

| Layer | Tool | Access & Runtime |
|---|---|---|
| Core LLM Library | Unified Provider Engine | Multi-provider abstraction (OpenAI, Anthropic, Gemini, Groq, Qwen) |
| LLM Reasoning (Chat) | Groq API (Llama 3.3 70B & Llama 3.1 8B Instant) | Managed Endpoint, reserved for real-time chat latency |
| LLM Background | Google Gemini 2.0 Flash / Qwen 2.5 | Managed/Local, used for background memory consolidation |
| Embeddings | sentence-transformers (`BAAI/bge-m3`) | Local runtime, 1024-dimensional dense & sparse vectors |
| Vector Store | PostgreSQL + pgvector | Self-hosted Docker container (`vector(1024)`) |
| Graph DB | Neo4j Community Edition | Self-hosted Docker container |
| Cache & Broker | Redis | Self-hosted Docker container |
| Orchestration | LangGraph | Open source (Apache 2.0) |
| Backend | FastAPI | Open source (ASGI framework) |
| Mobile App | Flutter | Open source framework |
| Async Workers | Celery + Redis | Distributed worker queue (Rate-limited) |
| Clustering | scikit-learn (HDBSCAN) | Dynamic min cluster size |

---

## Architecture & Privacy Strategy

### Authentication & Privacy
- **Authentication**: Handled manually via **Email** and **Google Provider (OAuth2)**.
- **Session Security**: Upon successful login, the backend issues a JWT token. WebSocket connections are authenticated via this JWT.
- **Privacy Design**: Strict row-level isolation by `user_id` across PostgreSQL and Neo4j.
- **Compliance**: The `/forget-me` compliance feature uses a two-phase transaction. It sets a `deletion_pending` flag and queues a retry worker to ensure a complete cascading delete across PostgreSQL and Neo4j, avoiding partial deletion states.

### API Rate Limit Mitigation
To avoid hitting the Groq API rate limit (30 RPM) during heavy background tasks:
- **Task Segregation**: Fast, real-time chat routing uses Groq. All asynchronous consolidation, entity extraction, and goal inference tasks use Gemini 2.0 Flash or local Qwen.
- **Celery Limits**: Background workers are configured with explicit rate limits (e.g., `rate_limit='10/m'`).

### The Cold Start Problem (Bootstrapping)
For users with $< 5$ sessions, HDBSCAN clustering cannot form meaningful episodic clusters. 
- **Solution**: The system injects an "Onboarding/Bootstrap" prompt layer during early sessions, asking lightweight clarifying questions to explicitly gather goals and preferences. These are directly seeded into permanent memory to bypass the initial clustering requirement.

---

## Project Structure

```
cognai/
├── brain/                    
│   ├── orchestrator.py       # LangGraph state machine
│   ├── context_assembler.py  
│   ├── router.py             
│   └── metacognition.py      # Thinking Governor: confidence & contradiction detection
│
├── llm/                      
│   ├── base.py               
│   ├── providers.py          
│   └── router.py             
│
├── memory/
│   ├── working.py            # Sliding context window (capped 20 turns) + rephrasing
│   ├── episodic.py           # Session storage + cosine distance surprise + emotional valence
│   ├── consolidation.py      # HDBSCAN clustering + permanent memory extraction
│   ├── permanent.py          
│   └── forgetting.py         
│
├── graph/                    
│   └── neo4j_client.py       
│
├── persona/
│   ├── state.py              
│   ├── drift.py              # 5-signal implicit extraction (verbosity, tone, questions, etc.)
│   └── reflection.py         
│
├── api/
│   ├── main.py               
│   ├── auth.py               # Email & Google Provider JWT generation
│   ├── routes/chat.py        # Authenticated WebSocket streaming
│   └── routes/memory.py      # Memory inspect & /forget-me endpoints
│
├── workers/
│   ├── celery_app.py         # Celery broker & strict rate limiting config
│   └── consolidation_worker.py 
│
├── db/
│   └── schema.sql            # vector(1024) schemas & emotional_valence fields
│
└── mobile/                   # Flutter application
```

---

## Phase 1 — Core Infrastructure & "Must-Have" Loop (Weeks 1–3)

**Goal:** Auth layer, Multi-provider LLM, Vector schema, Working memory.

### Database Schema (vector(1024) + Emotion)
```sql
CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE episodes (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id TEXT NOT NULL,
    session_id TEXT NOT NULL,
    embedding vector(1024),
    raw_summary TEXT,
    emotional_valence FLOAT DEFAULT 0.0,    -- -1.0 to 1.0
    emotional_intensity FLOAT DEFAULT 0.0,  -- 0.0 to 1.0
    surprise_score FLOAT DEFAULT 0.0,
    created_at TIMESTAMPTZ DEFAULT NOW()
);
```

### Authentication Layer
```python
# api/auth.py
from fastapi import Depends, HTTPException
from fastapi.security import OAuth2PasswordBearer
# Implement Google Provider OAuth2 & Email login to issue JWTs
```

---

## Phase 2 — Memory & Cognitive Triggers (Weeks 4–6)

### Temporal Retrieval & Emotional Tagging
- **Emotional Tagging Rubric**: The summarization prompt must use a constrained scoring rubric (-1.0 to +1.0) with explicit behavioral anchors, validated manually on 10-20 sessions to ensure cross-model consistency.
```python
# memory/retrieval.py
def compute_score(self, sim, goal_sim, surprise, temporal_relevance, redundancy):
    return (α * sim) + (β * goal_sim) + (γ * surprise) + (ε * temporal_relevance) - (δ * redundancy)
```

### Session Boundary & Capping
```python
# memory/working.py
# 30-minute inactivity boundary logic:
# Episodic writes are triggered lazily when the NEXT message arrives and 
# delta > 30 mins, OR upon graceful app shutdown. Never on a blind timer.
# 20-turn sliding window cap
```

---

## Phase 3 — Metacognition & Consolidation (Weeks 7–9)

### Metacognitive Monitor & Contradiction Detection
```python
# brain/metacognition.py
class MetacognitiveMonitor:
    def estimate_confidence(self, retrieval_coverage, persona_certainty):
        """
        Thresholds:
        - Confidence >= 0.4: Standard fast-think response.
        - Confidence < 0.4: Overrides to slow-think mode.
        - Confidence < 0.2: Triggers a clarifying question back to the user.
        """
        pass
        
# memory/consolidation.py
class MemoryConflictResolver:
    def check_conflicts(self, new_facts, existing_permanent_memory):
        """Resolves contradictions via LLM before merging into permanent store."""
        pass
```

### Rate-Limited Background Workers
```python
# workers/celery_app.py
celery_app = Celery("cognai", broker=REDIS_URL, backend=REDIS_URL)
# Apply rate_limit='10/m' to consolidation tasks to protect API quotas.
# Route these tasks to Gemini/Qwen.
```

---

## Phase 4 — Research Experiments & Evaluation (Weeks 10–12)

### Synthetic Data Generation (Missing Eval Data Fix)
```python
# scripts/simulate_users.py
"""
Uses a local LLM or Gemini to act as synthetic users with hidden personas.
Generates 100 interaction sessions per user to populate the database and 
evaluate the LongMemEval benchmark natively.
"""
```

### Experiment Protocol: Closed-Loop Emergent System
**Core Publishable Research Claim:** Evaluate the complete emergent closed-loop system interacting simultaneously against individual single-module ablations.
**Emergent Metric:** Cross-session goal prediction accuracy — after N sessions, can the full system correctly predict what the user will ask about next better than any single-module baseline?

---

## Post-Publication Roadmap (Nice-to-Haves)
- **Multi-granularity Memory Consolidation**: Upgrading flat facts to thematic schemas.
- **Personalized PageRank (PPR) Graph Retrieval**: Full multi-hop Neo4j reasoning.
- **Proactive Curiosity-Driven Memory**: Detecting stalled goals and unresolved threads to proactively surface during chat.

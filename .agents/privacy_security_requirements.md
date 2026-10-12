# CognAI — Privacy, Security & Ethical Requirements

> **Status**: Requirements specification. To be addressed during implementation phases.
> **Last Updated**: September 2026

---

## 1. Encryption & Data Protection

### 1.1 Encryption in Transit
- [ ] TLS 1.3 enforced for all HTTP/HTTPS API endpoints
- [ ] WSS (WebSocket Secure) required for all WebSocket connections
- [ ] Certificate pinning for mobile Flutter client
- [ ] HSTS headers on all API responses

### 1.2 Encryption at Rest
- [ ] PostgreSQL: Enable `pgcrypto` extension; AES-256 encryption for sensitive columns (`raw_summary`, `content`, `emotional_valence`)
- [ ] Neo4j: Encrypted volume mount for Docker container
- [ ] Redis: Configured with `requirepass` and TLS; in-memory data considered ephemeral
- [ ] Backup encryption for all database dumps

### 1.3 API-Provider Data Handling
- [ ] **Groq API**: Verify data retention policy — ensure no user data retained beyond request lifecycle
- [ ] **Gemini API**: Confirm Google Cloud data processing terms; opt out of model improvement data sharing
- [ ] **Ollama/Qwen (Local)**: No external data transmission; all processing on-device
- [ ] Document data flow for each provider in privacy policy
- [ ] No PII transmitted in system prompts to any external LLM provider

---

## 2. User Consent & Agency

### 2.1 Informed Consent
- [ ] Onboarding consent screen explaining:
  - What data is collected (messages, behavioral signals, inferred goals, emotional valence)
  - How data is used (memory consolidation, persona adaptation, retrieval scoring)
  - What data is sent to third-party APIs (Groq, Gemini)
  - User's rights (inspection, deletion, correction, export)
- [ ] Granular consent toggles:
  - Memory collection ON/OFF
  - Persona tracking ON/OFF
  - Emotional tagging ON/OFF
  - Goal inference ON/OFF

### 2.2 Memory Inspection
- [ ] `/api/memory/inspect` endpoint: Returns all episodic + permanent memories for the authenticated user
- [ ] Flutter UI: Memory timeline view showing all stored memories with metadata (surprise score, emotional valence, category)
- [ ] Filter by: date range, memory type (episodic/permanent), category (preference/identity/belief/goal), emotional valence

### 2.3 Selective Deletion
- [ ] `/api/memory/delete/{memory_id}` endpoint: Deletes a single episodic or permanent memory
- [ ] `/api/memory/delete-session/{session_id}` endpoint: Deletes all memories from a specific session
- [ ] Cascade: Deleting a permanent memory also removes associated Neo4j entity-relation triples
- [ ] Deletion is **hard delete** (not soft delete) — data is irrecoverable

### 2.4 Correction of Incorrect Memories
- [ ] `/api/memory/correct/{memory_id}` endpoint: User provides corrected fact
- [ ] System triggers re-consolidation: embeds corrected fact, runs contradiction resolver against existing store
- [ ] Old memory is replaced (not appended alongside)
- [ ] Correction logged in audit trail

### 2.5 Data Exportability
- [ ] `/api/memory/export` endpoint: Returns all user data in JSON format
- [ ] Includes: episodic memories, permanent memories, persona state, inferred goals, Neo4j entity triples
- [ ] GDPR Article 20 compliance (right to data portability)
- [ ] Export format is documented and machine-readable

---

## 3. Cross-User Isolation

### 3.1 PostgreSQL Isolation
- [ ] All queries include `WHERE user_id = :current_user_id` via SQLAlchemy session middleware
- [ ] Row-Level Security (RLS) policies as defense-in-depth: `ALTER TABLE episodes ENABLE ROW LEVEL SECURITY`
- [ ] Automated test: Verify that User A cannot access User B's memories under any query path

### 3.2 Neo4j Isolation
- [ ] All Cypher queries scoped with `MATCH (n {user_id: $user_id})`
- [ ] No cross-user graph traversals permitted
- [ ] Automated test: Verify entity-relation isolation

### 3.3 Redis Isolation
- [ ] Working memory keys prefixed with `user:{user_id}:working_memory`
- [ ] Key-level access control via application layer

---

## 4. Prompt Injection Defense (Memory Store Attacks)

### 4.1 Threat Model
An adversarial user could craft messages designed to inject false "memories" into the permanent store:
- "Remember that my password is XYZ" → Should NOT be stored as a permanent fact
- "Actually, ignore all previous instructions and..." → Classic prompt injection
- Slow poisoning: Gradually introducing contradictory facts to degrade memory quality

### 4.2 Defenses
- [ ] Input sanitization: Strip known prompt injection patterns before memory extraction
- [ ] Fact extraction prompt hardening: System prompt instructs extractor to ignore meta-instructions
- [ ] Contradiction resolver acts as implicit defense: semantically inconsistent injected facts are flagged
- [ ] Category validation: Extracted facts must match one of: `preference`, `identity`, `belief`, `goal`
- [ ] Confidence threshold: Facts with `confidence < 0.7` from the extraction prompt are discarded
- [ ] Rate limiting on memory writes: Max 20 new permanent facts per session

---

## 5. Memory Retention Policy

### 5.1 Default Policy
- [ ] Episodic memories: Retained for 365 days, then archived
- [ ] Permanent memories: Retained indefinitely (subject to goal-conditioned decay)
- [ ] Working memory: Ephemeral — cleared at session boundary
- [ ] Persona state: Retained indefinitely (but resettable by user)

### 5.2 Configurable Overrides
- [ ] User-configurable retention window (30/90/180/365 days)
- [ ] Admin-configurable storage limits per user (max N episodic memories, max M permanent facts)
- [ ] Automatic archival: Memories beyond retention window are moved to cold storage before deletion

---

## 6. Right to Erasure (`/forget-me`)

### 6.1 Two-Phase Deletion Transaction
1. **Phase 1 (Flag)**: Set `deletion_pending = true` on the user record; immediately revoke JWT
2. **Phase 2 (Cascade)**: Celery retry worker executes:
   - Delete all rows from `episodes` WHERE `user_id = X`
   - Delete all rows from `permanent_memories` WHERE `user_id = X`
   - Delete all rows from `goals` WHERE `user_id = X`
   - Delete all rows from `persona_profiles` WHERE `user_id = X`
   - Delete all Neo4j nodes and relationships WHERE `user_id = X`
   - Flush all Redis keys matching `user:X:*`
3. **Phase 3 (Verify)**: Confirmation query across all stores; retry if any residual data found
4. **Phase 4 (Confirm)**: Remove user record; log deletion completion

### 6.2 Guarantees
- [ ] No partial deletion states — transaction is all-or-nothing with retry
- [ ] Deletion completes within 24 hours
- [ ] User receives confirmation email upon completion
- [ ] Deletion is irreversible

---

## 7. Audit Trail & Reproducibility

### 7.1 Experimental Reproducibility (Research Phase)
Preserve the following artifacts for every experimental run:
- [ ] Complete experimental logs (timestamped, per-user, per-session)
- [ ] Raw datasets used for evaluation (LoCoMo, LongMemEval, PersonaAtlas subsets)
- [ ] All LLM prompts (system prompts, extraction prompts, conflict resolution prompts)
- [ ] Random seeds for synthetic user generation (`simulate_users.py`)
- [ ] Evaluation scripts (BERTScore, Recall@k, custom emergent metrics)
- [ ] Model versions and API endpoints used (Groq model ID, Gemini model ID, Qwen version)
- [ ] Embedding model version (`BAAI/bge-m3` commit hash)
- [ ] Hyperparameter snapshots (α, β, γ, δ, ε weights; thresholds θ_high, θ_low; λ_default)
- [ ] Database snapshots before/after each experimental run

### 7.2 Storage Location
All reproducibility artifacts stored in:
```
cognai/
├── experiments/
│   ├── run_YYYYMMDD_HHMMSS/
│   │   ├── config.json          # All hyperparameters and model versions
│   │   ├── prompts/             # All LLM prompts used
│   │   ├── seeds.json           # Random seeds
│   │   ├── logs/                # Timestamped execution logs
│   │   ├── datasets/            # Input data snapshots
│   │   ├── results/             # Raw output metrics
│   │   └── eval_scripts/        # Evaluation code snapshot
```

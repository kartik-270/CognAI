# CognAI — Experimental Reproducibility Checklist

> **Purpose**: Ensure all experimental artifacts are preserved for peer review, replication, and future phases.
> **Last Updated**: September 2026
> **Status**: Track during Phase 4 (Weeks 10–12)

---

## Per-Experiment Run: Mandatory Artifacts

### 1. Configuration Snapshot
- [ ] `config.json` containing:
  - Retrieval weights: α, β, γ, δ, ε
  - Surprise thresholds: θ_high, θ_low
  - Decay rate: λ_default
  - Metacognition thresholds: fast_think (0.4), clarify (0.2)
  - Temporal half-life: T_1/2
  - Working memory cap (20 turns)
  - Session boundary timeout (30 min)
  - Contradiction similarity threshold (0.65)
  - HDBSCAN min_cluster_size

### 2. Model Versions
- [ ] Groq model ID (e.g., `llama-3.3-70b-versatile`)
- [ ] Gemini model ID (e.g., `gemini-2.0-flash`)
- [ ] Qwen version (e.g., `qwen2.5-7b-instruct`)
- [ ] Embedding model: `BAAI/bge-m3` — exact HuggingFace commit hash
- [ ] sentence-transformers library version
- [ ] Python version, torch version, scikit-learn version

### 3. Prompts
- [ ] System prompt for chat (Groq)
- [ ] System prompt for slow-think override (Gemini)
- [ ] Fact extraction prompt (`FACT_EXTRACTION_PROMPT`)
- [ ] Conflict resolution prompt (`CONFLICT_RESOLUTION_PROMPT`)
- [ ] Emotional valence scoring rubric prompt
- [ ] Goal inference prompt
- [ ] Entity extraction prompt
- [ ] Synthetic user persona prompts (for `simulate_users.py`)

### 4. Random Seeds
- [ ] `seeds.json` containing:
  - NumPy random seed
  - Python random seed
  - Per-simulated-user persona seed
  - HDBSCAN random state

### 5. Datasets
- [ ] LoCoMo evaluation subset (version, split, preprocessing)
- [ ] LongMemEval evaluation subset (version, split)
- [ ] PersonaAtlas subset (HuggingFace revision hash)
- [ ] Custom 20-user × 50-session corpus:
  - Raw generated transcripts
  - Ground-truth annotations (goal labels, contradiction injection points, temporal targets)
  - User persona definitions (hidden goals, personality traits)

### 6. Evaluation Scripts
- [ ] BERTScore computation script (model version, layer used)
- [ ] Recall@k computation script
- [ ] Temporal recall accuracy scorer
- [ ] LongMemEval judge prompt and scoring script
- [ ] Contradiction rate calculator
- [ ] Persona differentiation score calculator
- [ ] Cross-session goal prediction evaluator
- [ ] Statistical significance test script (paired t-test, Bonferroni correction)

### 7. Raw Results
- [ ] Per-query retrieval scores (all 5 components + final score)
- [ ] Per-session consolidation logs (surprise scores, contradiction resolutions)
- [ ] Per-user persona state evolution over 50 sessions
- [ ] Ablation results: full matrix (5 modules × 7 metrics)
- [ ] Weight sensitivity sweep results
- [ ] Latency measurements (p50, p95, p99)

### 8. Database Snapshots
- [ ] PostgreSQL dump before each experimental run
- [ ] PostgreSQL dump after each experimental run
- [ ] Neo4j export (Cypher dump) before/after
- [ ] Redis working memory snapshot (if relevant)

---

## Directory Structure

```
cognai/
├── experiments/
│   ├── run_20261115_143000/           # Example run
│   │   ├── config.json
│   │   ├── model_versions.json
│   │   ├── prompts/
│   │   │   ├── chat_system.txt
│   │   │   ├── slowthink_system.txt
│   │   │   ├── fact_extraction.txt
│   │   │   ├── conflict_resolution.txt
│   │   │   ├── emotional_valence.txt
│   │   │   ├── goal_inference.txt
│   │   │   └── user_personas/
│   │   │       ├── user_01.json
│   │   │       └── ...
│   │   ├── seeds.json
│   │   ├── datasets/
│   │   │   ├── locomo_subset/
│   │   │   ├── longmemeval_subset/
│   │   │   ├── personaatlas_subset/
│   │   │   └── custom_corpus/
│   │   │       ├── transcripts/
│   │   │       └── annotations/
│   │   ├── eval_scripts/
│   │   │   ├── compute_bertscore.py
│   │   │   ├── compute_recall.py
│   │   │   ├── compute_temporal.py
│   │   │   ├── compute_contradiction.py
│   │   │   ├── compute_persona_diff.py
│   │   │   ├── compute_goal_pred.py
│   │   │   └── statistical_tests.py
│   │   ├── results/
│   │   │   ├── retrieval_quality.csv
│   │   │   ├── longmemeval_scores.csv
│   │   │   ├── emergent_properties.csv
│   │   │   ├── ablation_matrix.csv
│   │   │   ├── weight_sensitivity.csv
│   │   │   └── latency_measurements.csv
│   │   ├── logs/
│   │   │   ├── consolidation.log
│   │   │   ├── retrieval.log
│   │   │   └── metacognition.log
│   │   └── db_snapshots/
│   │       ├── pg_before.sql.gz
│   │       ├── pg_after.sql.gz
│   │       ├── neo4j_before.cypher.gz
│   │       └── neo4j_after.cypher.gz
│   └── run_20261201_100000/           # Next run...
│       └── ...
```

---

## Version Control Rules

1. **Never commit raw database dumps to git** — store in `.gitignore`d `experiments/` directory
2. **Always commit**: `config.json`, `seeds.json`, `model_versions.json`, evaluation scripts
3. **Tag each experimental run** in git: `git tag -a exp-v1.0 -m "Baseline ablation run"`
4. **Lock dependencies**: `pip freeze > requirements-experiment.txt` before each run

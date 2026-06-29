# Upgrade Roadmap

This roadmap turns InterviewAgent from a functional demo into a portfolio-ready, deployable agent system.

## Phase A: Presentation and Reproducibility

Goal: make the repository credible within the first minute.

- Rewrite README with product positioning, architecture, startup steps, API flow, and resume bullets.
- Remove mojibake from public-facing docs and configuration examples.
- Add Dockerfile and `.dockerignore` so `docker compose up --build` has a real API image target.
- Remove secret-looking values from `.env.example`.
- Document the current architecture and production gaps.
- Keep the first pass scoped to repository entry points and deployment scaffolding.

Acceptance criteria:

- A reviewer can understand the system from README without reading code.
- `.env.example` contains only placeholders.
- Docker Compose references an actual Dockerfile.
- The upgrade path is explicit and ordered.
- `python scripts/verify_fast.py` provides a standard-library-only verification path.

## Phase B: Production Safety

Goal: make the system safe for real users and multi-user sessions.

- Add session ownership checks to every session endpoint.
- Move session metadata, turns, messages, and reports into database tables.
- Keep Redis as a hot cache, not the only active-state source.
- Keep user-selected phase switching as a first-class practice feature, protected by session ownership and valid-phase checks.
- Validate production config at startup:
  - `SECRET_KEY` must not use the placeholder value.
  - CORS must not be `"*"` in production.
  - `APP_ENV=production` must not use in-memory sessions.
- Add upload size and JD length limits.
- Add clear API errors for expired, missing, or unauthorized sessions.

Acceptance criteria:

- User A cannot read, mutate, or stream User B's session.
- Production startup fails fast on unsafe defaults.
- Reports and transcripts survive process restarts.
- API tests cover ownership, auth, and session lifecycle.

## Phase C: Agent and RAG Quality Loop

Goal: prove the agent is better than a prompt-only chatbot.

- Build a small offline evaluation dataset:
  - JD snippets
  - expected technical entities
  - expected graph nodes
  - expected follow-up topics
- Status: bilingual offline RAG eval and ablation framework are implemented in `evals/rag_cases.json`, `app/evals/rag_eval.py`, and `scripts/run_rag_eval.py`.
- Current dependency-free local baseline:
  - `sparse_bm25`: `Recall@5=0.8190`, `MRR@5=1.0000`
  - `dense_hashing`: `Recall@5=0.5679`, `MRR@5=0.8893`
  - `hybrid_rrf`: `Recall@5=0.7238`, `MRR@5=1.0000`
  - `hybrid_rrf_graph`: `Recall@5=0.8964`, `MRR@5=0.8571`
- Measure retrieval:
  - Recall@K
  - MRR
  - duplicate rate
  - graph expansion usefulness
- Measure agent workflow:
  - phase transition accuracy
  - repeated-question rate
  - empty-response rate
  - JSON report parse success rate
- Compare retrieval modes:
  - BM25 only
  - vector only
  - graph only
  - RRF hybrid
- Add regression tests for evaluator output shape and fallback behavior.

Acceptance criteria:

- The project can show numeric RAG improvements.
- The agent workflow has automated quality checks.
- Report generation is stable enough for demos and CI.

## Phase D: Observability and Operations

Goal: make system behavior diagnosable.

- Add request IDs and session IDs to structured logs.
- Track LLM latency, token usage, ASR latency, TTS latency, and retrieval latency.
- Track session completion rate and failure reasons.
- Add timeout and retry wrappers for external services.
- Add a lightweight admin/debug view or CLI for inspecting sessions and traces.

Acceptance criteria:

- A failed interview can be traced from upload to final error.
- Latency and cost hotspots are visible.
- External-service failures degrade gracefully.

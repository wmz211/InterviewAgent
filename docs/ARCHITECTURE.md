# InterviewAgent Architecture

## Product Goal

InterviewAgent is a multimodal interview agent platform. It simulates structured technical and HR interviews, adapts questions to a candidate's resume and target JD, and produces an evidence-based evaluation report.

The core design idea is to treat the interviewer as an orchestrated workflow instead of a single prompt. Each interview phase owns a focused responsibility, and the LangGraph state is the shared contract between phases.

## Runtime Flow

1. The user registers or logs in and receives a JWT token.
2. The user uploads a resume and JD.
3. The upload endpoint parses the resume, creates an initial `InterviewState`, and stores it by `session_id`.
4. The interview starts with a LangGraph invocation.
5. Each turn appends a human message, routes to the current phase node, and returns the next interviewer response.
6. When the interview reaches `wrap_up`, the evaluator scores phase QA records and writes a structured report.
7. Completed sessions are persisted for history and report endpoints.

## Key Components

| Component | Responsibility |
| --- | --- |
| `app/api/` | HTTP, SSE, and WebSocket entry points |
| `app/auth/` | JWT authentication and current-user resolution |
| `app/core/interview_graph.py` | LangGraph workflow construction and phase routing |
| `app/core/state.py` | Shared state schema used by every phase |
| `app/core/session_store.py` | Active session storage with memory and Redis backends |
| `app/db/interview_sessions.py` | Durable interview session metadata writes |
| `app/db/interview_messages.py` | Durable interview transcript writes |
| `app/evals/rag_eval.py` | Dependency-free RAG retrieval evaluation metrics and graph-aware baseline |
| `app/agents/nodes/` | Interview phase implementations |
| `app/rag/` | Resume parsing, vector retrieval, and graph retrieval |
| `app/evaluation/` | Scoring rubric and final report generation |
| `app/audio/` | Streaming ASR/TTS and WebSocket audio protocol |

## Interview State

`InterviewState` is the single source of truth for each interview. It contains:

- identity: `session_id`, `candidate_name`, `user_id`
- document context: `resume_summary`, `jd_text`
- conversation: `messages`
- workflow control: `current_node`, `phase_turn_count`, `should_transition`
- assessment data: `node_scores`, `asked_question_ids`
- completion metadata: `interview_complete`, `interview_mode`
- practice metadata: `practice_mode`, `selected_phase`

The current implementation stores live sessions in memory or Redis, writes completed sessions to JSON, and persists interview session metadata plus transcript messages to SQL tables. The next persistence steps are to move turn-level QA records, reports, and history reads into database tables while keeping Redis as a hot cache.

## Agent Workflow

Tech mode:

```text
greeting -> resume_dive -> jd_tech -> coding_test -> wrap_up
```

HR mode:

```text
greeting -> hr_self_intro -> hr_behavioral -> hr_career -> wrap_up
```

Each node returns a partial state update. LangGraph merges the update into the current state, then the API stores the result.

Users can choose a valid phase during both full interviews and phase-practice sessions. Full interviews still start at `greeting` by default, while phase practice can start directly at the selected phase. Phase switching is protected by session ownership and interview-mode phase validation.

## Retrieval Design

The JD technical phase combines several signals:

- alias/entity matching over the knowledge graph
- BM25 lexical retrieval
- vector retrieval over node labels, aliases, and descriptions
- Reciprocal Rank Fusion to merge rankings
- `LEADS_TO` graph expansion for follow-up chains

This gives the project a strong interview story: the system does not only retrieve similar text; it uses graph structure to ask progressive technical questions.

## RAG Evaluation

The repository includes an offline RAG evaluation path. `scripts/run_rag_eval.py` loads `data/tech_knowledge_graph.json` and `evals/rag_cases.json`, compares sparse BM25, dense embedding retrieval, RRF hybrid fusion, and graph-expanded hybrid retrieval, then writes `output/rag_eval_report.json`.

Current dependency-free local baseline:

- `sparse_bm25`: `Recall@5=0.8190`, `MRR@5=1.0000`
- `dense_hashing`: `Recall@5=0.5679`, `MRR@5=0.8893`
- `hybrid_rrf`: `Recall@5=0.7238`, `MRR@5=1.0000`
- `hybrid_rrf_graph`: `Recall@5=0.8964`, `MRR@5=0.8571`

This is intentionally a CI-friendly baseline. The same runner can use a real multilingual SentenceTransformer backend, and the next step is to add a Chroma-backed dense retriever that reuses the same evaluation cases.

## Production Gaps

The next production hardening phase should address:

- user ownership checks on every session endpoint
- database-backed sessions and reports
- production config validation
- upload size limits and content validation
- testable retry and timeout policies around LLM, ASR, TTS, Neo4j, and ChromaDB
- structured tracing, latency metrics, token cost tracking, and failure-rate dashboards

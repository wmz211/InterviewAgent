# InterviewAgent Phase A Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the repository presentation and local startup path credible for interview review.

**Architecture:** Keep core application behavior unchanged. Improve only repository entry points, deployment scaffolding, and explanatory documentation.

**Tech Stack:** Markdown, Docker, Docker Compose, FastAPI runtime.

---

### Task 1: Rewrite Repository Entry Documentation

**Files:**
- Modify: `README.md`
- Create: `docs/ARCHITECTURE.md`
- Create: `docs/UPGRADE_ROADMAP.md`

- [x] **Step 1: Replace mojibake README with product-oriented content**

Include project goal, core capabilities, tech stack, architecture diagram, interview flow, quick start, Docker usage, API order, tests, project structure, upgrade roadmap, and resume bullet.

- [x] **Step 2: Add architecture document**

Document runtime flow, key components, interview state, agent workflow, retrieval design, and production gaps.

- [x] **Step 3: Add upgrade roadmap**

Split remaining work into Phase B production safety, Phase C quality loop, and Phase D observability.

### Task 2: Add Container Build Target

**Files:**
- Create: `Dockerfile`
- Create: `.dockerignore`
- Modify: `docker-compose.yml`

- [x] **Step 1: Add Dockerfile**

Use `python:3.11-slim`, install system dependencies needed by Python packages and audio handling, install `requirements.txt`, copy app assets, expose port 8000, and run `python -m app.main`.

- [x] **Step 2: Add `.dockerignore`**

Exclude `.git`, local IDE files, virtual environments, caches, generated audio, local databases, session archives, and `.env`.

- [x] **Step 3: Rewrite Compose file**

Keep `neo4j`, `redis`, and `api` services. Replace hardcoded Neo4j password with `.env` interpolation and keep API service on `build: .`.

### Task 3: Sanitize Environment Example

**Files:**
- Modify: `.env.example`

- [x] **Step 1: Remove secret-looking values**

Replace API keys, auth secrets, and database passwords with placeholders.

- [x] **Step 2: Clarify local development defaults**

Set `GRAPH_BACKEND=networkx` for low-friction local development and leave `REDIS_URL=` empty for in-memory sessions.

### Task 4: Verify Static Quality

**Files:**
- Inspect changed files

- [ ] **Step 1: Search for leaked placeholder patterns**

Run:

```powershell
Select-String -Path README.md,.env.example,docker-compose.yml,docs\*.md -Pattern "sk-|interviewagent123|change-me-in-production"
```

Expected: no output.

- [ ] **Step 2: Check changed file list**

Run:

```powershell
git diff -- README.md .env.example Dockerfile .dockerignore docker-compose.yml docs
```

Expected: only Phase A documentation and scaffolding changes.


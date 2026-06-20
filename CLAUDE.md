# CLAUDE.md — StartupIQ

One-line: **StartupIQ** is a full-stack, AI-powered startup-idea evaluator (competitor research, target customers, market opportunity, risks, MVP/feasibility, revenue models) — also a learning project built phase-by-phase, with a companion book in `book/`.

## Tech stack

- **Backend:** Python ≥3.11, FastAPI, SQLModel + async SQLAlchemy + asyncpg, Alembic (migrations), Pydantic v2 / pydantic-settings.
- **DB + Auth:** Supabase (Postgres + Supabase Auth). App data in `public` schema; `profiles` mirrors `auth.users` 1:1 via a DB trigger.
- **Async/infra:** Redis with **Arq** (job queue + worker), **slowapi** (rate limiting), Redis cache. `httpx` for outbound (webhook delivery).
- **LLM:** provider-agnostic abstraction. `OpenAIProvider` (dev) / `ClaudeProvider` (prod), selected by `LLM_PROVIDER`. Defaults: `OPENAI_MODEL=gpt-4o-mini`, `CLAUDE_MODEL=claude-sonnet-4-6`.
- **Frontend:** Next.js 15 (App Router) + React 19 + TypeScript + Tailwind v3 + `@supabase/supabase-js`.
- **Ops:** Docker + Compose (+ nginx reverse proxy), Kubernetes manifests (`infra/k8s/`), GitHub Actions CI/CD (`.github/workflows/ci.yml`), Locust load tests.

## Layout

```
backend/     FastAPI app
  app/core/      config.py (Settings), security.py (JWT), arq.py, cache.py, rate_limit.py
  app/db/        session.py (async engine), models/ (profile, idea, job, webhook)
  app/schemas/   Pydantic request/response + llm_results.py (LLM output schemas)
  app/api/v1/    router.py + ideas, evaluations, jobs, dashboard, webhooks
  app/llm/       base.py (LLMProvider ABC), openai_provider, claude_provider, factory, features.py (registry)
  app/worker/    settings.py (WorkerSettings), tasks.py (run_evaluation_feature), webhooks.py (dispatch/deliver)
  alembic/       migrations 0001..0004
  tests/         pytest (conftest has shared fixtures + overrides)
frontend/    Next.js app (app/, components/, lib/: supabaseClient.ts, api.ts, features.ts)
docker/      docker-compose.yml, nginx/nginx.conf, .env (frontend build vars)
infra/       k8s/ (manifests + README), seed/seed_data.py, loadtest/ (index_demo.py, locustfile.py)
book/        companion learning book (Ch 1–14 + epilogue + glossary); README.md = TOC
docs/        architecture.md, deployment.md
```

## Architecture (request flow)

Frontend → (nginx/Ingress) → FastAPI API (stateless, N replicas) → Postgres (Supabase) + Redis. Slow LLM work is **never** done in the request: the API enqueues an Arq job and returns `202` + `job_id`; the **worker** runs the LLM call and writes the result to the `jobs` row; the client polls `GET /api/v1/jobs/{id}`. On job completion the worker fires webhooks (HMAC-signed, retried).

## Conventions

- **Layered design:** API (routers) → security/deps → schemas → db. Endpoints stay thin; business logic in services/worker.
- **Program to interfaces, not vendors:** LLM behind `LLMProvider`, cache behind `Cache` ABC, queue behind the Arq pool. This is what makes everything testable with fakes.
- **Config only via env** (12-factor). All settings live in `app/core/config.py` `Settings`; read `settings.X`, never hardcode. Add new env vars there + to `.env.example`.
- **API:** REST under `/api/v1`, resource-oriented. Separate Pydantic `*Create`/`*Read`/`*Update` schemas (input schemas must NOT include server-controlled fields like `user_id`). Pagination via `limit`/`offset` — never return unbounded lists.
- **Auth + ownership:** every protected route takes `user_id = Depends(get_current_user)` and filters/checks `... == user_id`. Return `404` (not `403`) for resources owned by others (don't leak existence).
- **Migrations:** schema changes go through a new Alembic migration (`0005_...`), never hand-edited DB. Register new models in `app/db/models/__init__.py`.
- **Naming:** snake_case Python, kebab/lowercase routes, `feature_type` enum values match `app/llm/features.py` `FeatureType`.
- **The book:** when adding a phase/feature, extend `book/` + glossary (the project doubles as a teaching artifact).

## Run / build / test

- **Backend deps:** `cd backend && python -m venv .venv && source .venv/bin/activate && pip install -e ".[dev]"`. **Activate the venv** for any project Python tool (uvicorn/arq/alembic/pytest, and `infra/` scripts). `kubectl`/`docker`/`curl` need no venv.
- **Tests:** `cd backend && pytest` — fully hermetic (in-memory SQLite via StaticPool, fakes for Redis/LLM/auth, limiter disabled). **Must pass with zero secrets/services** (CI runs them). ~20 tests.
- **Local dev (4 processes):** `redis-server`; `uvicorn app.main:app --reload`; `arq app.worker.settings.WorkerSettings`; `cd frontend && npm run dev`.
- **Whole stack:** `cd docker && docker compose up --build` → http://localhost (nginx routes `/`→frontend, `/api`→backend).
- **Migrations:** `cd backend && alembic upgrade head` (or `docker compose run --rm api alembic upgrade head`).
- **Kubernetes / load tests:** see `infra/k8s/README.md` and `infra/README.md`.
- Env files: copy `*.env.example` → real env files (`backend/.env`, `frontend/.env.local`, `docker/.env`). **They are git-ignored.**

## Hard constraints / invariants (never violate)

- **Never commit secrets.** Real keys live in `backend/.env`, `frontend/.env.local`, `docker/.env` — all git-ignored. Before any commit, verify no `.env` is staged. `.env.example` files (placeholders) are the only env files in git.
- **Keep the app stateless.** No per-process in-memory state for anything that must be consistent across replicas — rate-limit counters, cache, and the job queue MUST live in Redis (this is what makes horizontal scaling correct).
- **Tests must stay hermetic.** No real network/DB/Redis/LLM in tests; depend on interfaces and inject fakes (CI has no secrets).
- **Don't construct network clients with config at import time.** Build them lazily (e.g. `_get_jwk_client()` in `security.py`). A module-level `PyJWKClient(...)` once broke CI when `SUPABASE_URL` was empty.
- **Auth is JWKS-based (ES256), not a shared secret.** Supabase tokens are verified against the public JWKS endpoint via `pyjwt[crypto]` — keep the `[crypto]` extra (needed for ES256).
- **Supabase connection strings (known foot-guns):**
  - App uses the **transaction pooler** (`...pooler.supabase.com:6543`) → asyncpg prepared-statement caching is disabled in `db/session.py` (`statement_cache_size=0`, `prepared_statement_cache_size=0`, unique `prepared_statement_name_func`). Any new engine needs the same.
  - Migrations use `DATABASE_URL_DIRECT` = the **session pooler** (`...pooler.supabase.com:5432`), NOT the direct `db.<ref>.supabase.co` host (that is IPv6-only and unreachable from Docker).
- **`profiles.id` FKs to `auth.users.id`** — you cannot insert a profile for a non-existent auth user (seed/test data attaches to existing users).
- **Frontend `NEXT_PUBLIC_*` config is baked in at BUILD time** (Docker build args / CI secrets), not read at runtime — unlike the backend (runtime env). A frontend image built without real Supabase values fails the build.
- **Webhook payloads are signed over the exact bytes sent** (HMAC-SHA256, header `X-StartupIQ-Signature: sha256=...`) — serialize once, sign those bytes, send those bytes.
- **Evaluation feature types** are the closed set in `app/llm/features.py` `FeatureType` (`competitor_research`, `target_customer`, `market_opportunity`, `risk_identification`, `mvp_feasibility`, `revenue_model`); webhook events are `evaluation.completed` / `evaluation.failed`.

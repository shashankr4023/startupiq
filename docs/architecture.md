# StartupIQ — Startup Idea Evaluator (Learning Project Plan)

## Context

The user is a beginner who wants to learn System Design, Backend Engineering, API design, Caching/Redis, FastAPI, Database design, Supabase, Webhooks, Docker, Kubernetes, Load Balancers, Rate Limiting, Scalability, and Reliability by building a real product end-to-end: **StartupIQ**, a tool that evaluates startup ideas (competitor research, target customers, market opportunity, risks, MVP/feasibility, revenue models).

Confirmed decisions:
- **LLM engine**: provider-agnostic abstraction. **OpenAI API** during dev/testing, **Claude API (Anthropic)** for production.
- **Full-stack**: FastAPI backend + Next.js (React) frontend.
- **DB/Auth**: Supabase (Postgres + Supabase Auth/JWT).
- **Caching/Queue/Rate limiting**: Redis.
- **Containerization**: Docker Compose for local dev now; Kubernetes (minikube/kind) as a later milestone; architecture designed to be portable to AWS/GCP/Azure later.
- **Scale target**: data model/queries designed for ~10,000 users / ~10,000 ideas (synthetic seed data for load testing), even though real usage is solo.
- **Webhooks**: meaningful integration point — fire on events like `evaluation.completed`.

This plan is the full roadmap plus a concrete Phase 1 starting point. Implementation will proceed phase-by-phase; this turn focuses on setting up the repo structure and Phase 1 (backend skeleton + DB + auth + CRUD).

---

## 1. Feature List

### Core (user-specified)
1. Startup idea submission (create/edit ideas)
2. Competitor research
3. Target customer analysis
4. Market opportunity (TAM/SAM/SOM-style)
5. Risk identification
6. MVP generation & feasibility assessment
7. Revenue model suggestions

### Recommended additions (kept lean — each maps to a learning goal)
8. Overall idea score / SWOT summary (meta-evaluation run after the above — teaches job orchestration/dependencies)
9. Evaluation versioning / re-run (append-only history per idea)
10. Tags & collections (many-to-many relationships)
11. Exportable report (Markdown/PDF, background task + file storage)
12. Shareable read-only report link (token-based auth, separate from Supabase JWT)
13. Async job status tracking (`/jobs/{id}` polling)
14. Usage dashboard (ideas/evaluations/job counts — exercises caching)
15. Webhook subscriptions (`evaluation.completed`, `idea.created` events, HMAC-signed)

No multi-tenant orgs, billing, or real-time chat — kept intentionally scoped for a solo learner.

---

## 2. High-Level Architecture

```
Next.js Frontend (React, App Router, Supabase Auth client)
        │ HTTPS, Authorization: Bearer <supabase JWT>
        ▼
Reverse Proxy (Nginx/Traefik) — TLS termination, routes /api -> backend, / -> frontend
        │
        ▼
FastAPI Backend (stateless, multiple replicas later)
  - validates Supabase JWT (PyJWT, HS256, no roundtrip)
  - rate limiting (slowapi + Redis, per-user/per-IP)
  - response caching (Redis, short TTL, invalidate on write)
  - sync CRUD endpoints; enqueues Arq jobs for LLM evaluations
        │                         │
        ▼                         ▼
Supabase Postgres            Redis
  (SQLModel + async             - Arq job queue/broker
   SQLAlchemy, Supavisor         - rate-limit counters
   pooler connection)            - cache store
        ▲                         │
        │                         ▼
        │                  Arq Worker (separate container)
        │                    - LLMProvider abstraction:
        │                      OpenAIProvider / ClaudeProvider
        │                      selected via LLM_PROVIDER env var
        └──────────────────── - writes evaluation_results to Postgres
                                 - enqueues dispatch_webhook_event task
                                       │
                                       ▼
                              Webhook Dispatcher (Arq task)
                                - HMAC-SHA256 signs payload
                                - POSTs to subscriber URLs, retries w/ backoff
```

Key points:
- **Sync vs async**: idea CRUD, tags, collections, dashboard = sync request/response. LLM evaluations = `POST .../evaluations` returns `202` + job IDs; client polls `/jobs/{id}` (and later gets a webhook).
- **LLM abstraction**: `LLMProvider` ABC with `async generate(prompt, schema) -> BaseModel`. `OpenAIProvider` and `ClaudeProvider` implementations, chosen via `LLM_PROVIDER=openai|claude`. Only the **worker** calls LLM providers — API layer just enqueues jobs.
- **Redis, three roles**: job queue (Arq), rate-limit counters (slowapi RedisStorage — shared across replicas), response cache (TTL + invalidate-on-write).
- **Cloud-readiness**: all state in Postgres/Redis (externalizable); API/worker containers stateless, config via env vars; generated reports go to Supabase Storage, not local disk.
- **RLS**: enable Row Level Security on Supabase tables as defense-in-depth, but primary authorization happens in FastAPI route/service layer (filter by `user_id == current_user_id`), since the backend connects via a direct/service connection, not per-user Supabase client.

---

## 3. Data Model (Postgres / Supabase)

`profiles` mirrors `auth.users` (1:1, populated via a Postgres trigger on `auth.users` insert).

- **profiles**: `id` (PK, = auth.users.id), `email`, `display_name`, `created_at`
- **startup_ideas**: `id` PK, `user_id` FK→profiles (indexed), `title`, `description`, `industry`, `target_market`, `status` (`draft`/`active`/`archived`), `created_at`, `updated_at`. Index `(user_id, created_at desc)`.
- **evaluations**: `id` PK, `idea_id` FK (indexed), `triggered_by` FK→profiles, `version` int, `status` (`pending`/`running`/`completed`/`failed`/`partial`), `created_at`, `completed_at`. Index `(idea_id, version desc)`.
- **evaluation_results**: `id` PK, `evaluation_id` FK (indexed), `feature_type` enum (`competitor_research`, `target_customer`, `market_opportunity`, `risk_identification`, `mvp_feasibility`, `revenue_model`, `overall_score`), `status`, `result_json` jsonb, `llm_provider`, `model_name`, `error_message`, `created_at`, `completed_at`. Unique `(evaluation_id, feature_type)`.
- **jobs**: `id` PK (= Arq job_id), `evaluation_id` FK nullable, `job_type` (`run_evaluation`/`dispatch_webhook`/`generate_report`), `status`, `attempts`, `result_summary`, `created_at`, `updated_at`.
- **tags**: `id` PK, `user_id` FK, `name`, unique `(user_id, name)`.
- **idea_tags**: `idea_id` FK, `tag_id` FK, PK both.
- **collections**: `id` PK, `user_id` FK, `name`, `created_at`.
- **collection_ideas**: `collection_id` FK, `idea_id` FK, PK both.
- **webhooks**: `id` PK, `user_id` FK, `target_url`, `secret`, `event_types text[]`, `is_active`, `created_at`.
- **webhook_deliveries**: `id` PK, `webhook_id` FK, `event_type`, `payload_json` jsonb, `response_status`, `attempt_count`, `delivered_at`, `created_at`.
- **shared_reports**: `id` PK, `idea_id` FK, `evaluation_id` FK, `share_token` unique indexed, `expires_at`, `created_at`.

At 10k ideas × ~3 evaluation versions × 7 feature types ≈ 210k `evaluation_results` rows — comfortably indexable.

---

## 4. API Design

Base path `/api/v1`, path-based versioning. All endpoints require `Authorization: Bearer <supabase_jwt>` except `/shared/{token}`.

- **Ideas**: `POST/GET /ideas`, `GET/PATCH/DELETE /ideas/{id}` (DELETE = soft delete via status=archived)
- **Evaluations**: `POST /ideas/{id}/evaluations` (→ 202 + job_ids), `GET /ideas/{id}/evaluations`, `GET /evaluations/{id}` (cached), `POST /evaluations/{id}/rerun`
- **Jobs**: `GET /jobs/{id}` (poll status)
- **Reports**: `POST /ideas/{id}/reports` (async), `GET /reports/{id}`, `POST /ideas/{id}/share`, `GET /shared/{token}` (public)
- **Tags/Collections**: standard CRUD
- **Webhooks**: `GET/POST /webhooks`, `PATCH/DELETE /webhooks/{id}`, `GET /webhooks/{id}/deliveries`
- **Compare/Dashboard**: `GET /ideas/compare?ids=...` (cached), `GET /dashboard/stats` (cached ~60s)

**LLM abstraction seam**:
```python
class LLMProvider(ABC):
    @abstractmethod
    async def generate(self, prompt: str, schema: type[BaseModel]) -> BaseModel: ...

class OpenAIProvider(LLMProvider): ...
class ClaudeProvider(LLMProvider): ...

def get_llm_provider() -> LLMProvider:
    return ClaudeProvider(...) if settings.LLM_PROVIDER == "claude" else OpenAIProvider(...)
```
Worker task `run_evaluation_feature(evaluation_id, feature_type)` calls `get_llm_provider().generate(prompt, schema_for(feature_type))`.

**Rate limits** (slowapi + RedisStorage, shared across replicas):
- `POST /ideas/{id}/evaluations`: ~10/hour per user
- General CRUD: ~100/minute per user
- `/shared/{token}`: ~30/minute per IP

---

## 5. Repo Structure (Monorepo)

```
startupiq/
├── backend/
│   ├── app/
│   │   ├── main.py
│   │   ├── core/ (config.py, security.py, redis.py)
│   │   ├── db/ (session.py, models/: profile.py, idea.py, evaluation.py, job.py, webhook.py, tag.py)
│   │   ├── schemas/ (idea.py, evaluation.py, llm_results.py)
│   │   ├── api/v1/ (router.py, ideas.py, evaluations.py, jobs.py, tags.py, collections.py, webhooks.py, reports.py, dashboard.py)
│   │   ├── llm/ (base.py, openai_provider.py, claude_provider.py, factory.py, prompts/)
│   │   ├── services/
│   │   └── middleware/ (rate_limit.py, cache.py)
│   ├── alembic/
│   ├── pyproject.toml, .env.example
│   └── tests/
├── worker/
│   └── worker/ (main.py, tasks/: run_evaluation.py, generate_report.py, dispatch_webhook.py)
├── frontend/  (Next.js App Router: app/, lib/supabaseClient.ts, lib/api.ts, components/)
├── docker/ (docker-compose.yml, docker-compose.prod.yml, nginx/nginx.conf)
├── infra/ (k8s/, seed/seed_data.py)
├── .env.example
└── docs/architecture.md
```

`worker` imports models/schemas/LLM code directly from `backend.app` (shared via PYTHONPATH in Docker) — avoids duplication at this scale.

---

## 6. Phased Roadmap

1. **Backend skeleton + DB + Auth + CRUD** — FastAPI structure, Supabase setup, SQLModel models, Alembic migrations, JWT validation, idea CRUD. *(FastAPI, API design, DB design, Supabase, auth basics)*
2. **LLM abstraction + single sync evaluation** — `LLMProvider` ABC + OpenAI/Claude impls, prompt templates, one sync evaluation endpoint. *(Abstraction design, LLM integration, structured outputs)*
3. **Async jobs + Arq worker + Redis queue** — Redis container, Arq worker, refactor to job-based evaluations across all 6+1 feature types, `jobs` table + polling. *(Background jobs, queues, async system design)*
4. **Caching + rate limiting** — Redis caching for reads/dashboard, invalidation, slowapi + RedisStorage limits. *(Caching strategies, rate limiting, Redis)*
5. **Next.js frontend + Supabase Auth + dashboard** — login/signup, idea list/detail, evaluation results w/ polling, usage dashboard. *(Full-stack integration, frontend auth)*
6. **Docker Compose full stack** — Dockerfiles for backend/worker/frontend, compose wiring + Nginx reverse proxy. *(Docker, containerization, orchestration)*
7. **Webhooks** — webhook CRUD, dispatcher Arq task on `evaluation.completed`, HMAC signing, retries. *(Webhooks, event-driven design, reliability)*
8. **Load testing with seed data (10k scale)** — `infra/seed/seed_data.py`, locust/k6 scripts, `EXPLAIN ANALYZE`-driven index tuning. *(Scalability, DB performance)*
9. **Kubernetes migration** — `infra/k8s/` manifests, minikube/kind, HPA experiments. *(Kubernetes, orchestration, scaling)*
10. **Cloud deployment prep** — externalize Redis, GitHub Actions CI/CD, deploy to managed K8s or cloud VM. *(Cloud deployment, CI/CD, 12-factor apps)*

---

## 7. Phase 1 — Concrete Plan (this implementation pass)

### 7.1 Files/directories to create
```
backend/
├── app/
│   ├── __init__.py
│   ├── main.py
│   ├── core/__init__.py, config.py, security.py
│   ├── db/__init__.py, session.py, models/__init__.py, profile.py, idea.py
│   ├── schemas/__init__.py, idea.py
│   └── api/__init__.py, v1/__init__.py, router.py, ideas.py
├── alembic/ (env.py, script.py.mako, versions/)
├── alembic.ini, pyproject.toml, .env.example
└── tests/test_ideas.py
docs/architecture.md  (copy of this plan for reference)
```

### 7.2 Backend skeleton
- `pyproject.toml` deps: `fastapi`, `uvicorn[standard]`, `sqlmodel`, `sqlalchemy[asyncio]`, `asyncpg`, `alembic`, `pydantic-settings`, `pyjwt`, `python-dotenv`.
- `core/config.py`: `Settings(BaseSettings)` — `DATABASE_URL`, `SUPABASE_JWT_SECRET`, `SUPABASE_URL`, `SUPABASE_ANON_KEY`, `ENVIRONMENT`.
- `db/session.py`: async engine via `create_async_engine(settings.DATABASE_URL)` using Supabase **Supavisor pooler** connection string; `get_session()` dependency.
- `main.py`: FastAPI app, CORS for Next.js dev origin, includes `api/v1/router.py`, `GET /health`.

### 7.3 DB schema / migrations
- User creates Supabase project, gathers Project URL, anon key, JWT secret, pooler + direct Postgres connection strings.
- SQLModel models: `Profile` (`profiles` table, `id` matches `auth.users.id`), `StartupIdea` (`startup_ideas`, fields per section 3).
- `alembic init alembic`; configure `env.py` with SQLModel metadata + **direct** connection string (not pooler) for migrations.
- `alembic revision --autogenerate -m "create profiles and startup_ideas"` → review → `alembic upgrade head`.
- Raw-SQL migration adding Postgres trigger to auto-insert `profiles` row on `auth.users` insert (standard Supabase pattern).

### 7.4 JWT validation
`core/security.py`: `get_current_user()` dependency using `HTTPBearer` + `PyJWT.decode(token, settings.SUPABASE_JWT_SECRET, algorithms=["HS256"], audience="authenticated")`, returns `UUID` from `payload["sub"]`. Injected into protected routes; ownership checks filter by `user_id == current_user_id`.

### 7.5 First endpoints (`api/v1/ideas.py`)
- `POST /api/v1/ideas` — create idea (201)
- `GET /api/v1/ideas` — list current user's ideas, paginated (`limit`/`offset`), ordered by `created_at desc`
- `GET /api/v1/ideas/{idea_id}` — get one (404 if not found or not owned)

Schemas in `schemas/idea.py`: `IdeaCreate`, `IdeaRead`, `IdeaUpdate` (for future PATCH).

### 7.6 Verification
1. `uvicorn app.main:app --reload` starts cleanly, `GET /health` returns 200.
2. Create a test user via Supabase Auth (UI or REST), obtain JWT.
3. `curl -X POST localhost:8000/api/v1/ideas -H "Authorization: Bearer <jwt>" -d '{...}'` → 201, row visible in Supabase table editor.
4. `GET /api/v1/ideas` returns only that user's ideas; `GET /api/v1/ideas/{id}` works and 404s for other users' ideas.
5. Confirm `profiles` row auto-created via trigger on signup.

Phase 1 establishes a working, verified foundation before introducing the LLM abstraction (Phase 2) and async jobs (Phase 3).

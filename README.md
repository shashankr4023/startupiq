# StartupIQ

StartupIQ is an AI-assisted startup idea evaluator: it researches competitors,
profiles target customers, sizes market opportunity, flags risks, sketches an
MVP/feasibility assessment, and suggests revenue models for a given startup idea.

It is also a **learning project**, built phase by phase to cover real backend and
system-design skills end to end: FastAPI, Supabase (Postgres + Auth), a
provider-agnostic LLM layer (OpenAI/Claude), Redis (queue + cache + rate limiting),
a background worker, webhooks, Docker, Kubernetes, load testing, and CI/CD.

📖 **A companion book in [`book/`](book/README.md)** explains every phase from a
beginner's perspective — the *what* and the *why* behind each decision.

## Architecture

```
Next.js frontend ──▶ nginx / Ingress ──▶ FastAPI API (stateless, N replicas)
                                            │            │
                                   Supabase Postgres   Redis ──▶ Arq worker
                                   (+ Supabase Auth)   (queue,    (LLM calls,
                                                        cache,     webhook delivery)
                                                        limits)
```

Full design + phased roadmap: [docs/architecture.md](docs/architecture.md).
Deployment guide: [docs/deployment.md](docs/deployment.md).

## Repo layout

```
backend/   FastAPI app + Arq worker (app/worker) + Alembic migrations
frontend/  Next.js (App Router) app
docker/    Docker Compose + nginx reverse proxy
infra/     Kubernetes manifests (k8s/) + seed & load-test scripts (loadtest/)
book/      The companion learning book (14 chapters + epilogue)
docs/      Architecture and deployment docs
.github/   CI/CD pipeline (GitHub Actions)
```

## Run it

| Goal | How |
|---|---|
| Backend tests | `cd backend && pip install -e ".[dev]" && pytest` |
| Local dev (4 terminals) | Redis, `uvicorn app.main:app`, `arq app.worker.settings.WorkerSettings`, `npm run dev` |
| Whole stack, one command | `cd docker && docker compose up --build` → http://localhost |
| On Kubernetes | see [infra/k8s/README.md](infra/k8s/README.md) |
| Load test / DB perf | see [infra/README.md](infra/README.md) |

Configuration is via env files (`backend/.env`, `frontend/.env.local`,
`docker/.env`) — copy the `.example` files and fill in your Supabase + LLM keys.
**These files are git-ignored; never commit secrets.**

## Status

All 10 phases complete: API + AI evaluation + async jobs + caching/rate-limiting +
frontend + Docker + webhooks + load testing + Kubernetes + CI/CD.

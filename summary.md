# StartupIQ — Session Handoff Summary

> One-time snapshot to hand off to a fresh session. For durable, always-true
> project context (stack, conventions, invariants) see **`CLAUDE.md`** — this file
> is the *current state + recent in-flight work* that CLAUDE.md doesn't capture.

## 1. The goal

**StartupIQ** is a full-stack, AI-powered startup-idea evaluator, built as a
**beginner learning project** for the owner (Shashank). The point was never just
the app — it was learning, hands-on, the skills behind it: System Design, backend
systems, API design, caching, Redis, FastAPI, database design, Supabase, webhooks,
Docker, Kubernetes, load balancers, rate limiters, scalability, reliability, and
CI/CD. The project doubles as a **teaching artifact**: there is a companion book in
`book/` (Markdown chapters) and a polished **31-page illustrated PDF** built from
it.

The whole thing was built **phase by phase (10 phases)**, each phase teaching one
cluster of concepts, each verified live by the user before moving on, and each
accompanied by a new book chapter.

## 2. Current status: COMPLETE

**All 10 phases are done.** Phases 1–9 were run/verified live by the user. Phase
10 (CI/CD + cloud) is implemented; the repo is on GitHub and CI runs. The most
recent task (just finished) was producing the **PDF book**.

| Phase | What | Verified live? |
|---|---|---|
| 1 | Backend skeleton, DB, JWT auth, idea CRUD | ✅ |
| 2 | LLM provider abstraction (OpenAI/Claude) + sync evaluation | ✅ (real OpenAI) |
| 3 | Async jobs: Redis + Arq worker + `/jobs/{id}` polling | ✅ |
| 4 | Caching + rate limiting (slowapi) | ✅ |
| 5 | Next.js frontend (login, idea tiles, visualised results) | builds clean |
| 6 | Docker + Compose + nginx | ✅ |
| 7 | Webhooks (HMAC-signed, retried) | ✅ (in Docker) |
| 8 | Load testing (seed, EXPLAIN, Locust) | ✅ (saw 6ms cached vs 410ms uncached) |
| 9 | Kubernetes (Docker Desktop k8s) | ✅ (proved "5 not 15" rate limit) |
| 10 | CI/CD (GitHub Actions) + cloud deploy guide | partially — see §6 |

## 3. Tech stack (quick orientation)

- **Backend** `backend/`: Python 3.11, FastAPI, SQLModel + async SQLAlchemy + asyncpg, Alembic, Pydantic v2. Arq worker (`app/worker/`). slowapi rate limiting. httpx for webhook delivery.
- **DB/Auth**: Supabase (Postgres + Supabase Auth, **asymmetric ES256 JWTs verified via JWKS**).
- **LLM**: provider-agnostic (`app/llm/`). `OPENAI_MODEL=gpt-4o-mini` (dev), `CLAUDE_MODEL=claude-sonnet-4-6` (prod), chosen by `LLM_PROVIDER`.
- **Frontend** `frontend/`: Next.js 15 (App Router) + React 19 + TS + Tailwind v3 + supabase-js.
- **Ops**: `docker/` (Compose + nginx), `infra/k8s/` (manifests), `infra/loadtest/` + `infra/seed/`, `.github/workflows/ci.yml`.
- **Book**: `book/` (Markdown Ch 1–14 + epilogue + glossary), plus `book/StartupIQ-Book.html` and `book/StartupIQ-Book.pdf`.

## 4. Key decisions & rejected alternatives

- **Provider-agnostic LLM layer** (`LLMProvider` ABC + OpenAI/Claude impls + factory). *Why:* swap dev↔prod with one env var, and fake it in tests. *Rejected:* calling OpenAI directly everywhere (untestable, vendor lock-in).
- **Supabase Auth (JWKS/ES256), not custom auth.** *Why:* don't hand-roll security-critical login. *Gotcha:* this project's Supabase uses **asymmetric** signing keys, so we verify against the public JWKS endpoint with `pyjwt[crypto]`, NOT a shared HS256 secret (a first attempt assumed HS256 and failed).
- **Arq (not Celery) for the queue.** *Why:* async-native, tiny, Redis-only — gentler for a learner. Celery is heavyweight and sync-first.
- **Jobs store their result directly on the `jobs` row** (Phase 3). *Why:* simplest thing that works. *Deliberately deferred:* the normalized `evaluations`/`evaluation_results` tables + a "run all 6 features as one evaluation" flow (see §7).
- **Two caching styles:** read-through + invalidate-on-write for idea detail; TTL-only for dashboard. *Decision:* deliberately did NOT cache the idea *list* (pagination makes invalidation messy).
- **Rate-limit key = user (from JWT sub), fallback IP**, counters in **Redis** (not process memory) so the limit holds across replicas.
- **nginx/Ingress single-origin** (`/`→frontend, `/api`→backend) to eliminate CORS in Docker/k8s.
- **Docker Desktop built-in Kubernetes**, not minikube/kind. *Why:* user already had Docker Desktop + kubectl; local images "just work".
- **CI/CD stops at "publish images"** (build + push to GHCR), not auto-deploy. *Why:* actual cloud deploy costs money / is the user's choice. Documented two paths in `docs/deployment.md` (managed k8s, or a single VM + Compose).
- **Visual polish of the frontend was deliberately deferred** by the user (see memory `frontend-polish-deferred`). Don't proactively beautify it.
- **PDF rendering: WeasyPrint, not Chrome headless.** *Why:* on this Mac, headless Chrome rasterized pages to images and truncated to 8 blank pages. WeasyPrint produced proper 31-page vector text. *Required:* `brew install pango poppler` + `pip install --user weasyprint pypdf`, and render with `DYLD_FALLBACK_LIBRARY_PATH=/opt/homebrew/lib`.

## 5. Gotchas we hit (these recur — all are also in CLAUDE.md invariants)

1. **JWT ES256 needs `cryptography`** → dependency is `pyjwt[crypto]`.
2. **asyncpg + Supabase transaction pooler (port 6543)** → "prepared statement already exists". Fixed in `backend/app/db/session.py` with `connect_args`: `statement_cache_size=0`, `prepared_statement_cache_size=0`, unique `prepared_statement_name_func`.
3. **Supabase direct host `db.<ref>.supabase.co` is IPv6-only** → unreachable from Docker. `DATABASE_URL_DIRECT` (used by Alembic) now points at the **session pooler** (`...pooler.supabase.com:5432`, IPv4, supports DDL).
4. **Don't build network clients at import time.** `PyJWKClient(...)` validates its URL in the constructor; a module-level instance crashed CI when `SUPABASE_URL` was empty (no `.env`). Fixed: lazy `_get_jwk_client()` in `security.py`.
5. **Frontend `NEXT_PUBLIC_*` is baked at BUILD time** (Docker build args / CI secrets), not runtime. An image built without real Supabase values **fails the build** (`supabaseUrl is required` during prerender).
6. **Secrets**: real keys live only in git-ignored `.env` files. Root `.gitignore` excludes them; verified `backend/.env` is NOT tracked.
7. **`profiles.id` FKs `auth.users.id`** → can't seed ideas for a fake user; seed data attaches to a real account.

## 6. Exact current state of in-flight work

**Git:** on branch `main`, remote `https://github.com/shashankr4023/startupiq.git`.
Two commits pushed:
- `2f328fb` — initial full project
- `a89be4f` — the lazy-JWKS-client CI fix (committed AND pushed)

**Uncommitted (untracked) files** — created this session, not yet committed:
- `CLAUDE.md` (durable project context — should be committed)
- `book/StartupIQ-Book.html` (PDF book source)
- `book/StartupIQ-Book.pdf` (the 31-page rendered book)
- *(also `summary.md`, this file)*

**CI status (needs confirmation in a fresh session):**
- `backend-tests` job: was failing on the JWKS import bug → **fixed and pushed** (`a89be4f`). Should now be green.
- `frontend-build` job: passes (uses dummy NEXT_PUBLIC values baked into the workflow).
- `publish-images` job: the **backend image built+pushed OK** (so GHCR write permission works), but the **frontend image build FAILED** because the three `NEXT_PUBLIC_*` repository secrets are **not set**, so the build args were empty → `supabaseUrl is required`. **This is the one outstanding item.**

## 7. Precise next steps to pick up from

**A. Make CI fully green (the only loose end):**
1. In the GitHub repo → Settings → Secrets and variables → Actions → add three secrets:
   - `NEXT_PUBLIC_SUPABASE_URL` = `https://kwxsnxrjieowjipzutzs.supabase.co`
   - `NEXT_PUBLIC_SUPABASE_ANON_KEY` = (copy exact value from `frontend/.env.local`)
   - `NEXT_PUBLIC_API_BASE_URL` = `http://localhost` (change to the real domain when deploying)
2. (If `publish-images` ever fails on a *push* rather than build: Settings → Actions → General → Workflow permissions → "Read and write".)
3. Re-run the failed workflow (Actions → run → "Re-run failed jobs"). No code change needed.

**B. Commit the session's new files** (optional but recommended):
`git add CLAUDE.md book/StartupIQ-Book.html book/StartupIQ-Book.pdf summary.md && git commit -m "Add CLAUDE.md, PDF book, handoff summary" && git push`. (Verify `git status` shows no `.env` staged first.)

**C. Optional follow-on work (none of it required — project is complete):**
- **Frontend visual polish** — deferred by the user; tile structure is ready, it's a Tailwind/CSS pass against `reference.jpeg`. Don't start unprompted.
- **"Evaluate all 6 at once" flow** — add the `evaluations` + `evaluation_results` tables (next Alembic migration `0005_...`), so one click runs six jobs and fires a single `evaluation.completed` webhook.
- **Other deferred features** — tags/collections, exportable reports, shareable read-only links, idea comparison, evaluation versioning.
- **Actually deploy it** — follow `docs/deployment.md` Path B (a small VM + Compose + managed Redis + Caddy for HTTPS) for the easiest real, live deployment.
- **Rotate API keys** — the real OpenAI/Anthropic keys in `backend/.env` were typed into chat during the build; rotating them in the providers' dashboards is good hygiene now that the repo is public-facing.

## 8. How to run / verify (fast reference; full detail in CLAUDE.md)

- **Tests** (hermetic, no secrets): `cd backend && source .venv/bin/activate && pytest` → 20 pass.
- **Whole stack locally**: `cd docker && docker compose up --build` → http://localhost.
- **Kubernetes**: `infra/k8s/README.md`. **Load tests**: `infra/README.md`.
- **Re-render the PDF book**: `brew install pango poppler` once, then
  `DYLD_FALLBACK_LIBRARY_PATH=/opt/homebrew/lib python3 -c "from weasyprint import HTML; HTML('book/StartupIQ-Book.html').write_pdf('book/StartupIQ-Book.pdf')"`.

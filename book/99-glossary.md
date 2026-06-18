# Glossary

Plain-English definitions of every term used so far. Skim it now; return when a
word stops you.

### A–C

**API (Application Programming Interface)** — A contract for how programs talk:
"send a request shaped like this to this URL, get back a response shaped like
that." Our API is how the frontend (and curl) reach the backend.

**Alembic** — The tool we use to write and run database **migrations** for
SQLAlchemy/SQLModel.

**Abstract Base Class (ABC)** — A Python class that defines a *contract* (a set
of methods subclasses must implement) but can't be instantiated itself. Our
`LLMProvider` is an ABC; `OpenAIProvider` and `ClaudeProvider` implement it.

**Abstraction layer** — A boundary that hides *how* something works behind a
stable *what*. Code above the boundary depends only on the contract, so the
implementation below can be swapped freely. Our LLM layer is the example.

**Adaptive thinking** — A Claude feature where the model decides how much to
reason before answering. We enable it for the (hard) idea-evaluation task.

**Arq** — A small, async-native Python library implementing a job queue + worker
on top of Redis. We use it to run slow LLM evaluations in the background.

**202 Accepted** — The HTTP status meaning "I've accepted your request and will
process it, but I'm not finished." Returned when we enqueue an evaluation job.

**Async (asynchronous)** — A style where a program, while waiting on something
slow (like the database or an AI call), goes and does other work instead of
freezing. Key to serving many users with one server.

**Authentication** — Verifying *who* a caller is. In our app, done by checking
their JWT. (Contrast: authorization.)

**Authorization** — Verifying whether a caller is *allowed* to do a specific
thing (e.g. view *this* idea). Separate from, and done after, authentication.

**Backend** — The server-side program (FastAPI) that holds the logic, talks to
the database, and exposes the API. The user never sees it directly.

**CORS (Cross-Origin Resource Sharing)** — A browser security rule that blocks a
web page from calling an API on a different origin unless that API explicitly
allows it. We configure it so our own frontend can call our own backend.

**Cache** — A small, fast store (Redis) holding the result of expensive work, so
repeat requests are served instantly instead of recomputed.

**CI/CD** — *Continuous Integration* (auto-run tests/builds on every push, catching
breakage early) + *Continuous Delivery* (auto-build and publish deployable
artifacts). Ours runs on GitHub Actions.

**Container registry** — A store for built Docker images (we use GitHub's
`ghcr.io`). CI pushes images here; the cloud pulls them. The bridge between build
and deploy.

**Cache hit / miss** — A *hit* is when the requested value is in the cache (fast
path); a *miss* is when it isn't and must be recomputed and stored.

**Cache invalidation** — Deleting a cached value when the underlying data changes,
so the next read recomputes fresh. We do this on every write to an idea.

**Container** — A sealed, runnable unit packaging an app *with* its whole
environment (OS libs, runtime, deps, code), so it runs identically anywhere.

**Bulk insert (batched)** — Inserting many rows in groups (e.g. 1,000 at a time)
instead of one-by-one, to cut round trips to the database. Used by the seed
script.

**CRUD** — Create, Read, Update, Delete: the four basic operations on data. Our
ideas endpoints are textbook CRUD.

**EXPLAIN ANALYZE** — A Postgres command that runs a query and reports exactly
how it executed (scan type, rows touched, real time). The tool for diagnosing
slow queries.

**Docker** — The tool that builds and runs containers.

**Docker Compose** — Describes a multi-container app in one YAML file and runs
all the services together (`docker compose up`). Ours wires up 5 services.

**Dockerfile** — The recipe (a script of steps) that builds a container image.

**Image vs container** — An *image* is the read-only template you build once; a
*container* is a running instance of it (one image → many containers).

**Multi-stage build** — A Dockerfile with multiple `FROM` stages where the final
image copies only the build *output*, leaving the heavy build tools behind. Used
for the slim frontend image.

### D–F

**Dependency Injection (DI)** — A pattern where a function *declares* what it
needs (`Depends(get_current_user)`) and the framework *supplies* it. Removes
repetition and makes testing easy. FastAPI's signature feature.

**Endpoint** — A single API door: one HTTP method + path (e.g.
`POST /api/v1/ideas`) handled by one function.

**Event-driven design** — A style where one part *announces* that something
happened ("evaluation.completed") without knowing who reacts, and other parts
react independently. Decouples the emitter from the reactors.

**Exponential backoff** — Retrying a failed operation with growing waits between
attempts (2s, 4s, 8s…), giving a struggling dependency room to recover.

**Fan-out** — A step that takes one event and schedules many independent jobs
(one per target). Our webhook dispatcher fans out to per-webhook delivery jobs.

**Engine (SQLAlchemy)** — The long-lived object that manages connections to the
database. Created once per app.

**Environment variable** — A configuration value supplied by the surrounding
system rather than hardcoded. How we keep secrets out of code (see 12-Factor).

**FastAPI** — The Python web framework we use to build the API. Fast, modern,
and validates data automatically from type hints.

**Foreign key** — A column that must point to a real row's primary key in
another table (e.g. `startup_ideas.user_id` → `profiles.id`). Enforces that
relationships are valid.

**Frontend** — The user-facing program (Next.js). Runs in the browser, calls the
backend's API. Knows nothing about the database directly. Built in Phase 5.

**Client component (`"use client"`)** — A React component that runs in the
browser (vs. on the server). Needed for interactivity, state, timers, and auth.
Marked with `"use client";` at the top of the file.

**Dynamic route (`[id]`)** — A Next.js folder named with brackets whose value
comes from the URL (e.g. `/ideas/abc` fills `[id]` with `abc`).

**Next.js** — The React framework we use for the frontend: folder-based routing,
build tooling, and server/client rendering.

**Tailwind CSS** — A styling approach using utility classes (`flex`,
`rounded-tile`, `bg-brand-blue`) composed directly in the markup.

**TypeScript** — JavaScript plus a type system that catches shape errors before
the app runs. The frontend's equivalent of Pydantic's validation.

### G–L

**HTTP method** — The verb of a request: `GET` (read), `POST` (create), `PATCH`
(update), `DELETE` (remove).

**Index (database)** — A pre-sorted lookup structure that makes queries on a
column fast, like the index at the back of a book. We index columns we filter or
sort by (`user_id`, `status`, `created_at`).

**Job** — A unit of work to be done later (e.g. "run competitor research for
idea X"), recorded as a row in the `jobs` table and processed by the worker.

**GitHub Actions** — GitHub's built-in automation that runs your CI/CD workflow
(defined in `.github/workflows/`) on its servers when you push code.

**HMAC (Hash-based Message Authentication Code)** — A keyed signature: hash the
message together with a secret key. Proves the message is *authentic* (from
someone with the key) and *untampered* (any change breaks the signature). We sign
webhook payloads with HMAC-SHA256.

**HorizontalPodAutoscaler (HPA)** — A Kubernetes object that automatically adds or
removes pod replicas based on a metric (e.g. CPU), so the app right-sizes itself.

**Horizontal scaling** — Adding more *copies* of a service behind a load balancer
("scale out"). Contrast vertical scaling (a bigger machine, "scale up").

**Idempotency** — Being safe to do more than once with the same effect as once.
Webhook receivers should be idempotent because retries can deliver an event twice
("at-least-once delivery").

**Ingress** — The Kubernetes front door: routes external HTTP by URL path to the
right Service. Our cluster's equivalent of the nginx reverse proxy.

**JWKS (JSON Web Key Set)** — A public URL where an auth provider (Supabase)
publishes the **public keys** used to verify its JWTs. Our server fetches and
caches these.

**Kubernetes (k8s)** — A container orchestrator: you declare a desired state
(N copies of X, reachable at Y) and it continuously makes reality match — starting,
restarting, scaling, and load-balancing pods.

**kubectl** — The command-line tool for talking to a Kubernetes cluster
(`kubectl apply`, `kubectl get pods`, `kubectl scale`, …).

**Deployment (k8s)** — A spec that keeps N identical **pods** running, replacing
crashed ones and rolling out new versions. Each of our programs is a Deployment.

**Pod** — Kubernetes' smallest unit: one running container (plus helpers). Roughly
one instance of one of our programs.

**Service (k8s)** — A stable in-cluster address for a set of pods that also
**load-balances** requests across them. Pods find Redis via the `redis` Service.

**ConfigMap / Secret (k8s)** — Config injected into pods as environment variables;
non-secret in a ConfigMap, sensitive (keys, DB URLs) in a Secret.

**Orchestrator** — Software that runs and manages many containers across machines
(scaling, healing, networking, rollouts). Kubernetes is the standard one.

**Index Scan / Seq Scan** — Two ways Postgres finds rows. A *Seq Scan* reads the
whole table (slow on big tables); an *Index Scan* jumps straight to matching rows
via an index (fast). The goal of indexing is to turn the former into the latter.

**Latency percentile (p50/p95/p99)** — The latency below which that % of requests
fall. p95 = the slowest 1-in-20. Real performance targets use percentiles, not
averages, because the slow tail is what users feel.

**Lifespan** — FastAPI's startup/shutdown hook. Code that runs once when the
server boots and once when it stops. We use it to open/close the Redis pool.

**Load testing** — Simulating many concurrent users to measure throughput and
latency under pressure, finding bottlenecks. We use Locust.

**Locust** — A Python load-testing tool: you script what a user does, it runs
many of them at once and reports throughput + percentiles.

**JWT (JSON Web Token)** — A small, digitally signed token proving a caller's
identity. Readable by anyone but tamper-proof. Its `sub` field holds the user id.

**Layered architecture** — Organizing code into layers (API → security → schema
→ data) where each only talks to the one below. Keeps a growing system
maintainable. A form of *separation of concerns*.

**Factory** — A function whose job is to *construct and return* the right object
based on configuration. `get_llm_provider()` is a factory: it reads
`LLM_PROVIDER` and returns an OpenAI or Claude provider.

**Interface / contract** — The set of methods a class promises to provide
(defined by an ABC). Calling code programs against the interface, not a specific
implementation. See *Abstraction layer*.

**LLM (Large Language Model)** — The AI (OpenAI/Claude) that generates
evaluations. Introduced in Part 2 (Chapter 6).

**LLMProvider** — Our ABC defining the contract every AI vendor implementation
must satisfy: a `generate()` method plus `name`/`model`. The seam that lets us
swap OpenAI for Claude with one env var.

**Registry pattern** — Describing many similar things as *data* in one lookup
table (a dict/enum) instead of as repeated code branches. Our `FEATURES` registry
maps each evaluation type to its schema + prompt; adding a new type is one entry.

**Structured outputs** — An LLM feature that constrains the model to return data
matching a schema you provide (rather than free-form text), yielding valid,
parseable JSON. Both OpenAI (`response_format`) and Claude (`output_format`)
support it; we pass our Pydantic result schemas.

### M–P

**Middleware** — Code that wraps *every* request/response passing through the
app (e.g. CORS). A layer everyone goes through.

**Migration** — A versioned, ordered script describing one change to the
database schema. Run with `alembic upgrade head`. Version control for your
database structure.

**Model (DB)** — A Python class (with `table=True`) describing the shape of a
database table. Lives in `app/db/models/`.

**Monorepo** — One Git repository holding all parts of the project (backend,
frontend, worker, infra).

**ORM (Object-Relational Mapper)** — A tool (SQLModel) that maps database rows to
Python objects, so you write Python instead of raw SQL.

**Pagination** — Returning a *page* of results (e.g. 20) via `limit`/`offset`
instead of an entire unbounded list. Essential at scale.

**Pooler / connection pooling** — A layer that reuses a small set of database
connections across many requests, so the database isn't overwhelmed. Supabase
gives a pooler connection (port 6543) for the app and a direct one (5432) for
migrations.

**Postgres (PostgreSQL)** — The relational database we use (via Supabase).

**Producer / Consumer** — The two ends of a queue. The *producer* (our API) adds
jobs; the *consumer* (our worker) takes and processes them. They run as separate
processes and never call each other directly — they communicate through the queue.

**Polling** — A client repeatedly asking the server "is it done yet?" (calling
`GET /jobs/{id}` on a loop) until an async job completes. The simplest way to wait
on background work.

**Queue** — A line that jobs wait in: producers add to the back, the worker takes
from the front. Ours lives in Redis, managed by Arq.

**Rate limiting** — Capping how many requests a client may make in a time window,
rejecting the excess with `429`. Protects our (billed) evaluation endpoint.
Counters live in Redis so the limit holds across all API replicas. We use slowapi.

**Read-through cache** — A caching strategy: check the cache; on a miss, load from
the source, store it in the cache, then return it. Our idea-detail endpoint.

**slowapi** — The FastAPI rate-limiting library we use, backed by Redis.

**Primary key** — The column uniquely identifying each row in a table. Ours are
UUIDs.

**Pydantic** — The library that validates and shapes data from type hints.
Powers our **schemas** and FastAPI's automatic request validation.

**`pyproject.toml`** — The file declaring the project's identity and its
dependency list. The source of truth for what gets installed.

### R–S

**Redis** — An in-memory (RAM-based, very fast) data store. In this project it
plays three roles across phases: a job **queue** (Phase 3), a **cache**, and a
**rate-limit** counter (both Phase 4).

**Referential integrity** — The database guarantee that foreign keys always
point to real rows. You physically can't create an idea for a non-existent user.

**Reverse proxy** — A single entry point (nginx) that forwards incoming requests
to the right internal service based on the URL path. Makes the app one origin
(killing CORS) and is where HTTPS terminates in production.

**REST** — A style of API design centered on **resources** (nouns, like
`/ideas`) acted on by HTTP methods (verbs). Makes APIs predictable.

**Schema (API)** — A Pydantic class describing the shape of JSON crossing the
API boundary (`IdeaCreate`, `IdeaRead`). Distinct from a DB **model**; also a
security boundary (controls what a client may send).

**Separation of concerns** — The principle that each part of a system should
have one well-defined job. The reason we use layers and separate files.

**Session (DB)** — A short-lived workspace for one unit of work (usually one
request): you query/add/commit through it, then discard it.

**Soft delete** — "Deleting" by marking a row (e.g. `status="archived"`) instead
of removing it, preserving history. Our `DELETE /ideas/{id}` does this.

**SQLModel** — The library combining Pydantic + SQLAlchemy to define DB tables
as Python classes. Our **models** use it.

**Throughput (RPS)** — Requests per second the system handles; its capacity.
Higher is better.

**Status code** — The numeric result of an HTTP request: `200` OK, `201`
Created, `202` Accepted, `204` No Content, `401` Unauthorized, `404` Not Found,
`422` Unprocessable (validation failed), `429` Too Many Requests (rate limited).

**TTL (time-to-live)** — How long a cached value stays valid before it expires.
After the TTL, the next read recomputes. Bounds how stale a cache can ever be.

**Supabase** — A hosted Postgres database plus built-in Auth and a dashboard.
*Is* Postgres under the hood.

**Supabase Auth** — Supabase's ready-made login/signup system; it issues the
JWTs our backend verifies.

### T–Z

**Trigger (database)** — A function the database runs automatically on an event.
Ours creates a `profiles` row whenever Supabase creates a user.

**12-Factor App** — A set of principles for building portable, scalable apps. The
one we apply in Part 1: *store config in the environment, not in code.*

**UUID** — A random 128-bit identifier (e.g. `da272dcd-1b4d-…`). Used as our
primary keys: unguessable and generatable anywhere.

**Uvicorn** — The server program that actually runs our FastAPI app
(`uvicorn app.main:app --reload`).

**Virtual environment (`.venv`)** — A private, per-project copy of Python and its
libraries, isolating this project's dependencies from the rest of your machine.
Must be `activate`d in each new terminal.

**Stateless** — Keeping no important data in a process's own memory (it lives in
Postgres/Redis instead), so any copy can serve any request. What makes horizontal
scaling possible.

**Readiness / liveness probe** — Health checks Kubernetes runs against a pod
(here, hitting `/health`). Readiness gates whether traffic is sent; liveness
restarts a wedged pod. Self-healing.

**Volume (Docker)** — Storage that lives outside a container's lifecycle, so data
(e.g. Redis's) survives the container being recreated.

**Webhook** — A URL a user registers so our server can POST an event to it when
something happens (the reverse of a normal API call). Server-initiated
notification.

**Worker** — A separate, long-running program that loops: take a job off the
queue, do it, repeat. Slow work (our LLM calls) lives here, keeping the API fast.
Run with `arq app.worker.settings.WorkerSettings`.

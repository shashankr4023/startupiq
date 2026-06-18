# Chapter 7 — Background Jobs: Queues, Workers, and Why the API Got Faster

In Chapter 6 we made StartupIQ intelligent — but slow. Asking an AI to analyze an
idea takes 10–20 seconds, and our endpoint *blocked* for that entire time. One
user, fine. But that approach falls apart the moment you have real traffic, and
it makes for a terrible user experience (a spinning browser tab for 20 seconds).

This chapter fixes that with one of the most important patterns in all of backend
engineering: **moving slow work out of the request and into a background worker
via a queue.** It's how every serious system handles anything slow — sending
email, processing video, generating reports, calling AIs. Learn it once here, use
it forever.

## 7.1 The problem, precisely

Here's what "synchronous" meant in Phase 2:

```
Client ──POST /evaluations/competitor_research──▶ API
                                                   │
                                                   │ calls OpenAI...
                                                   │ ...waits...
                                                   │ ...still waiting (15s)...
                                                   │ ...gets result
Client ◀──────────── 200 + result ────────────────┘
        (browser frozen this whole time)
```

Two things are wrong with this:

1. **The user waits.** The HTTP connection is held open for 15 seconds. If their
   network hiccups, the result is lost. If they want five evaluations, they wait
   five times in a row.
2. **The server is tied up.** A web server has a limited number of "workers"
   handling requests. If each request hogs one for 15 seconds doing nothing but
   waiting on an API, you run out of capacity almost immediately. Ten users could
   bring the whole thing to its knees. *This is a scalability disaster.*

The fix is to stop doing the slow thing inside the request.

## 7.2 The pattern: enqueue now, work later, poll for the result

Instead of "do it and wait," we split the work into three independent moments:

```
1. ACCEPT      Client ──POST /evaluations/...──▶ API
                                                  │ create a "job" record (status: queued)
                                                  │ drop the job on a QUEUE
               Client ◀── 202 Accepted ──────────┘ (instant! returns a job_id)
                          {job_id, status_url}

2. WORK        Worker ──picks job off queue──▶ calls OpenAI... (15s, but nobody's waiting)
                                              └─▶ writes result to the job record (status: completed)

3. POLL        Client ──GET /jobs/{job_id}──▶ API ──▶ "still queued"
               Client ──GET /jobs/{job_id}──▶ API ──▶ "running"
               Client ──GET /jobs/{job_id}──▶ API ──▶ "completed" + the result 🎉
```

The API now does almost no work per request — it just records a job and hands it
off, responding in milliseconds. The slow part happens elsewhere, in a separate
program, where no user is waiting on a connection. The client checks back
("polls") every second or two until the job is done.

The new vocabulary:

- **Job** — a unit of work to be done later (here: "run competitor research for
  idea X"). We store each as a row in a `jobs` table.
- **Queue** — a line that jobs wait in. Producers add to the back; the worker
  takes from the front. Our queue lives in **Redis**.
- **Worker** — a *separate program* that sits in a loop: take a job from the
  queue, do it, repeat. Slow work lives here.
- **202 Accepted** — the HTTP status that means exactly "I've accepted your
  request and will process it, but I'm not done yet." (Compare `200 OK` = "done,
  here's the result.") The perfect status for "your job is queued."

## 7.3 Meet Redis (its first of three jobs)

**Redis** is an in-memory data store — extremely fast because it keeps data in
RAM rather than on disk. It's a Swiss Army knife; in this project it'll do three
different jobs across three phases. **This phase uses it as a queue** (a message
broker between the API and the worker). In Phase 4 it'll also become a cache and a
rate-limit counter. Same Redis, three roles — a big part of why it's worth
learning.

For now, just picture Redis as a shared whiteboard both the API and the worker can
see: the API writes "job 123 needs doing" on it; the worker reads it off.

We don't talk to Redis directly, though. We use **Arq** — a small, async-native
library that implements the whole queue-and-worker machinery on top of Redis. Arq
handles the fiddly parts (serializing jobs, the worker's take-a-job loop, retries)
so we write just two things: *what to enqueue* and *what the worker does*.

> **Why Arq and not Celery?** Celery is the famous Python job queue, but it's
> heavyweight and was built for synchronous code. Our whole stack is `async`
> (Chapter 3), and Arq is async-native, tiny, and Redis-only — a much gentler fit
> for a learner. Same concepts, far less ceremony.

## 7.4 The jobs table: a durable record

First, the `jobs` table — `backend/app/db/models/job.py`:

```python
class Job(SQLModel, table=True):
    __tablename__ = "jobs"
    id: UUID = Field(default_factory=uuid4, primary_key=True)  # also the Arq job id
    user_id: UUID = Field(foreign_key="profiles.id", index=True)
    idea_id: UUID = Field(foreign_key="startup_ideas.id", index=True)
    feature_type: str
    status: str = Field(default="queued", index=True)   # queued→running→completed|failed
    attempts: int = Field(default=0)
    result_json: dict | None = Field(default=None, sa_column=Column(JSON, nullable=True))
    llm_provider: str | None = Field(default=None)
    model_name: str | None = Field(default=None)
    error_message: str | None = Field(default=None)
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
```

A few design notes worth absorbing:

- **Why store jobs in Postgres at all, when Arq already tracks them in Redis?**
  Because Redis is in-memory and Arq expires job records after a while — it's a
  *transient* queue, not a permanent archive. Postgres is our durable source of
  truth. By mirroring each job into a `jobs` table, the user can still look up "what
  evaluations did I run last week and what did they say?" long after Redis has
  forgotten. **Right tool for each job:** Redis for the fast, ephemeral queue;
  Postgres for the permanent record.
- **`result_json` lives right on the job row.** When the worker finishes, it
  writes the structured AI result here (as JSON). So the job record doubles as the
  result record. (This is a deliberate Phase-3 simplification — later phases may
  split results into their own table once features like versioning and side-by-side
  comparison need it. *Make it work first; normalize when there's a reason to.*)
- **`status` walks a tiny state machine:** `queued` → `running` → `completed` or
  `failed`. The `status` column is indexed because we'll query by it ("show me
  running jobs") — the indexing lesson from Chapter 3, applied again.
- **`attempts` and `error_message`** set us up to reason about reliability:
  retries and failures. (We'll lean on these more in Phase 7.)

This table needs a migration, of course — `0003_create_jobs.py` (Chapter 3's
Alembic pattern), run with `alembic upgrade head`.

## 7.5 The producer: the API just enqueues

Here's the rewritten endpoint, `backend/app/api/v1/evaluations.py`. Compare it to
Phase 2's version — it no longer imports or calls any LLM provider at all:

```python
@router.post("/{idea_id}/evaluations/{feature_type}", status_code=202)
async def request_evaluation(
    idea_id: UUID,
    feature_type: FeatureType,
    user_id: UUID = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
    pool: ArqRedis = Depends(get_arq_pool),          # ← the queue connection
):
    idea = await session.get(StartupIdea, idea_id)
    if idea is None or idea.user_id != user_id:       # ← same authorization as always
        raise HTTPException(status_code=404, detail="Idea not found")

    job = Job(id=uuid4(), user_id=user_id, idea_id=idea_id,
              feature_type=feature_type.value, status="queued")    # 1. record it
    session.add(job)
    await session.commit()

    await pool.enqueue_job("run_evaluation_feature",               # 2. queue it
                           str(job.id), _job_id=str(job.id))

    return {                                                       # 3. respond instantly
        "job_id": str(job.id),
        "status": job.status,
        "feature_type": feature_type.value,
        "status_url": f"/api/v1/jobs/{job.id}",
    }
```

Three moves: **record** the job in Postgres, **enqueue** it on Redis, **respond**
with `202` and a `job_id`. No waiting. Notice the endpoint passes only the job's
*id* to the queue, not the idea text or the prompt — everything the worker needs
is already on the job row, so the worker can fetch it. And one neat trick:
`_job_id=str(job.id)` tells Arq to use *our* UUID as its job id too, keeping the
Postgres row and the Redis job perfectly in lock-step.

Where does `pool` come from? It's the Redis connection, created once when the app
boots. That's the job of the **lifespan** in `backend/app/main.py`:

```python
@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.arq_pool = await create_arq_pool()   # open the pool on startup
    yield
    await app.state.arq_pool.aclose()              # close it on shutdown

app = FastAPI(..., lifespan=lifespan)
```

A **lifespan** is FastAPI's "startup and shutdown" hook — code that runs once when
the server boots (before any request) and once when it stops. Opening a connection
pool once and reusing it is far better than opening one per request. The endpoint
reaches it through a dependency, `get_arq_pool` (Chapter 4's dependency injection,
again).

## 7.6 The consumer: the worker

Now the other side. The **worker** is a *separate process* — you literally run it
in its own terminal with `arq app.worker.settings.WorkerSettings`. Even though its
code lives in the same `app/` package, it runs independently of the API. (That
separation is the whole point — and in Phase 6 we'll put it in its own Docker
container.)

`backend/app/worker/settings.py` tells Arq how to run:

```python
class WorkerSettings:
    functions = [run_evaluation_feature]   # the tasks this worker can run
    redis_settings = get_redis_settings()  # which Redis to pull jobs from
    on_startup = startup                   # set up a DB session factory
    on_shutdown = shutdown
    max_jobs = 10                          # how many jobs to run at once
```

And the actual work, `backend/app/worker/tasks.py` — this is the slow LLM call
that *used* to live in the API:

```python
async def run_evaluation_feature(ctx: dict, job_id: str) -> str:
    session_maker = ctx["session_maker"]
    async with session_maker() as session:
        job = await session.get(Job, UUID(job_id))
        if job is None:
            return "job-not-found"

        job.status = "running"                  # ← a poller can now see progress
        job.attempts += 1
        await session.commit()

        idea = await session.get(StartupIdea, job.idea_id)
        spec = FEATURES[FeatureType(job.feature_type)]
        provider = get_llm_provider()           # ← the Phase 2 abstraction, reused!

        try:
            result = await provider.generate(
                system_prompt=SYSTEM_PROMPT,
                user_prompt=build_user_prompt(idea, spec),
                schema=spec.result_schema,
            )
            job.result_json = result.model_dump()
            job.llm_provider, job.model_name = provider.name, provider.model
            job.status = "completed"
        except Exception as exc:
            job.status = "failed"               # ← record the failure, don't crash
            job.error_message = str(exc)

        await session.commit()
        return job.status
```

Read what the worker does: load the job, flip it to `running`, do the slow AI call
(using *exactly the same `LLMProvider` abstraction from Chapter 6* — it didn't
change at all, we just call it from a different place), then write the result (or
the error) back onto the job row and mark it `completed`/`failed`. A poller
watching `GET /jobs/{id}` sees the status climb through those states in real time.

Two things to notice:

- **The worker has its own database session.** It's a separate process, so it
  can't borrow the API's session. `on_startup` stashes a session factory in `ctx`
  (Arq's per-worker context dict) and the task uses it. The worker reuses the same
  engine config from Chapter 3 — pointed at the same Postgres — so both processes
  read and write the same data.
- **Failures are caught, not crashed.** If the AI call throws, we record
  `status="failed"` and the message, rather than letting the worker die. The user
  polls and learns it failed, cleanly. Reliability is a feature.

## 7.7 The poll endpoint

The last piece, `backend/app/api/v1/jobs.py` — how the client checks back:

```python
@router.get("/{job_id}")
async def get_job(job_id: UUID, user_id=Depends(get_current_user),
                 session=Depends(get_session)):
    job = await session.get(Job, job_id)
    if job is None or job.user_id != user_id:        # ← ownership check, as always
        raise HTTPException(status_code=404, detail="Job not found")
    return {
        "job_id": str(job.id), "status": job.status,
        "result": job.result_json, "error_message": job.error_message,
        # ...feature_type, attempts, provider, timestamps...
    }
```

Dead simple: look up the job, check the caller owns it (the authorization habit
from Chapter 4), and return its current state. The client calls this on a loop —
"are we there yet?" — until `status` is `completed` (and `result` is populated) or
`failed`.

> Polling is the simplest way for a client to wait on async work, and the right
> place to start. (Fancier alternatives — webhooks, WebSockets, server-sent
> events — exist, and we'll actually build **webhooks** in Phase 7 as a push-based
> notification when a job finishes. Polling first; pushing later.)

## 7.8 The whole flow, end to end

Putting it together, here's a real run:

```
POST /api/v1/ideas/{id}/evaluations/competitor_research
  → 202 {"job_id": "abc...", "status": "queued", "status_url": "/api/v1/jobs/abc..."}

GET /api/v1/jobs/abc...   → {"status": "queued",    "result": null}
GET /api/v1/jobs/abc...   → {"status": "running",   "result": null}     (worker picked it up)
GET /api/v1/jobs/abc...   → {"status": "completed", "result": {...competitor research...}}
```

The API answered the first call in milliseconds. The 15-second AI call happened in
the worker, where no connection was held open. The user's browser was never
frozen. *That* is why this architecture scales — and it's the same shape behind
"we'll email you when your export is ready" everywhere on the web.

## 7.9 Testing async code without Redis or an AI

Async systems sound hard to test — two processes, a queue, an external AI. But our
layering makes each piece testable in isolation
(`backend/tests/test_evaluations.py` and `test_worker.py`):

- **The producer (API):** we swap the real Redis pool for a `FakePool` that just
  records what got enqueued. The test asserts the endpoint returns `202`, creates a
  `queued` job row, and handed the right job id to the queue — *without any Redis
  running*.

  ```python
  class FakePool:
      def __init__(self): self.enqueued = []
      async def enqueue_job(self, function, *args, **kwargs):
          self.enqueued.append((function, args, kwargs))
  ```

- **The consumer (worker):** we call `run_evaluation_feature(...)` directly with a
  test database and a **fake LLM provider** (the same trick from Chapter 6), and
  assert the job ends up `completed` with the result — *and* a separate test where
  the provider raises, asserting the job ends up `failed` with an error message.
  *No Redis, no Arq runtime, no real AI.*

This is the payoff of clean seams compounding: because the API depends on a *pool
interface* and the worker depends on the *`LLMProvider` interface*, we can fake
both and test the entire async flow offline, deterministically, in milliseconds.
All nine tests run in ~0.14 seconds.

## 7.10 Running it yourself

You now need **three** things running at once (three terminals):

**Terminal 1 — Redis** (the queue). If you don't have it:
```bash
# macOS
brew install redis
redis-server
# ...or with Docker:  docker run -p 6379:6379 redis
```

**Terminal 2 — the API:**
```bash
cd backend && source .venv/bin/activate
alembic upgrade head        # creates the new jobs table (first time only)
uvicorn app.main:app --reload
```

**Terminal 3 — the worker:**
```bash
cd backend && source .venv/bin/activate
arq app.worker.settings.WorkerSettings
```
You'll see the worker log `Starting worker...` and then sit waiting for jobs.

Now request an evaluation (Chapter 6's curl, but watch what's different):
```bash
curl -X POST "http://localhost:8000/api/v1/ideas/$IDEA_ID/evaluations/competitor_research" \
  -H "Authorization: Bearer $TOKEN"
# → returns INSTANTLY with {"job_id": "...", "status": "queued", ...}
```
Watch Terminal 3 — the worker logs the job running. Then poll:
```bash
curl "http://localhost:8000/api/v1/jobs/$JOB_ID" -H "Authorization: Bearer $TOKEN" | python -m json.tool
```
Run it a couple of times and watch `status` go `queued` → `running` →
`completed`, with `result` filling in. You just used a real job queue.

> Heads-up: if the API or worker fails to start with a Redis connection error,
> Redis (Terminal 1) isn't running. Both the API (to enqueue) and the worker (to
> pull) need it.

---

**Recap.** We moved the slow LLM call out of the request and into a background
worker. The API now **records** a job, **enqueues** it on Redis via Arq, and
returns `202` + a `job_id` instantly; a separate **worker** process pulls the job,
does the AI call using the unchanged Chapter-6 abstraction, and writes the result
onto the durable `jobs` row; the client **polls** `GET /jobs/{id}` until it's
done. This is the async pattern at the core of every scalable backend — and we
tested all of it without Redis or a real AI.

**This completes Part 3.** Three of Redis's jobs remain to explore. **Part 4
(Phase 4)** puts Redis to work as a **cache** (so repeated reads are instant) and
a **rate limiter** (so nobody — including you — can rack up a giant AI bill by
hammering the evaluation endpoint).

# Chapter 8 — Caching and Rate Limiting: Redis's Other Two Jobs

In Phase 3 we used Redis as a **queue**. This phase puts the same Redis to work
in two more roles — a **cache** (so repeated reads are instant) and a **rate
limiter** (so nobody, including you, can hammer the expensive AI endpoint). One
piece of infrastructure, three jobs. That versatility is a big part of why Redis
is everywhere.

These two features answer two different questions every real backend must face:

- *"How do I make this fast?"* → **caching**.
- *"How do I stop this from being abused (or from bankrupting me)?"* → **rate
  limiting**.

## 8.1 Caching: the core idea

A **cache** is a small, fast store where you keep the result of expensive work so
you don't have to redo it. The canonical example: reading a user's idea hits the
database every time. The database is fast, but not free — and if a hundred
clients fetch the same idea repeatedly, that's a hundred identical queries. A
cache says: *compute it once, remember the answer, serve the remembered copy.*

The pattern we use is **read-through caching**:

```
GET /ideas/{id}
   │
   ├─ 1. Is it in the cache?  ── YES ─▶ return it instantly (a "cache hit")
   │
   └─ NO ("cache miss")
          ├─ 2. Load it from the database
          ├─ 3. Store it in the cache (with an expiry)
          └─ 4. return it
```

The *first* request for an idea is a miss (it does the DB work and fills the
cache). Every request after that, until the cache entry expires, is a hit —
served from Redis without touching Postgres at all.

But caching introduces *the* classic hard problem in computer science:

> "There are only two hard things in Computer Science: cache invalidation and
> naming things." — Phil Karlton

The danger is **staleness**: if the idea changes but the cache still holds the
old copy, users see wrong data. We defend against staleness two ways, and you'll
see both in this chapter:

1. **TTL (time-to-live):** every cached entry self-destructs after N seconds. So
   even if we forget to update it, it can only ever be N seconds stale.
2. **Invalidation:** when we *write* (update/delete), we explicitly delete the
   cached copy, forcing the next read to recompute.

## 8.2 The cache abstraction

Just like the LLM provider in Chapter 6, we don't scatter raw Redis calls through
our endpoints. We define an interface — `backend/app/core/cache.py`:

```python
class Cache(ABC):
    @abstractmethod
    async def get_json(self, key: str) -> Any | None: ...
    @abstractmethod
    async def set_json(self, key: str, value: Any, ttl_seconds: int) -> None: ...
    @abstractmethod
    async def delete(self, key: str) -> None: ...
```

with two implementations: `RedisCache` (production — stores JSON strings in Redis
with an expiry) and `InMemoryCache` (a dict, for tests). The exact same trick as
the LLM abstraction: endpoints depend on the `Cache` interface, so in tests we
swap in the dict version and verify caching behavior *without Redis running*.

A cache key is just a string that uniquely names the thing being cached. Ours:

```python
def _idea_cache_key(user_id, idea_id) -> str:
    return f"idea:{user_id}:{idea_id}"
```

Notice the `user_id` in the key. That's deliberate — it guarantees one user's
cached idea can never be served to another, a small defence-in-depth touch on top
of the ownership checks.

## 8.3 Read-through caching in the endpoint

Here's the cached `GET /ideas/{id}`, from `backend/app/api/v1/ideas.py`:

```python
@router.get("/{idea_id}", response_model=IdeaRead)
async def get_idea(idea_id, user_id=Depends(get_current_user),
                  session=Depends(get_session), cache: Cache = Depends(get_cache)):
    key = _idea_cache_key(user_id, idea_id)

    cached = await cache.get_json(key)          # 1. try the cache
    if cached is not None:
        return cached                           #    HIT - instant, no DB

    idea = await session.get(StartupIdea, idea_id)   # 2. MISS - hit the DB
    if idea is None or idea.user_id != user_id:
        raise HTTPException(status_code=404, detail="Idea not found")

    data = IdeaRead.model_validate(idea).model_dump(mode="json")
    await cache.set_json(key, data, settings.CACHE_TTL_IDEA)   # 3. fill the cache
    return data
```

The `cache` arrives via dependency injection (Chapter 4 again — the same `Depends`
mechanism, now delivering a cache). On a hit we return immediately. On a miss we
do the DB read, then store a JSON-serializable copy with a TTL (`CACHE_TTL_IDEA`,
60 seconds), then return it.

### Invalidation on write

The other half — when the idea *changes*, the cached copy must die. In both
`PATCH` and `DELETE`:

```python
session.add(idea)
await session.commit()
await cache.delete(_idea_cache_key(user_id, idea_id))   # ← invalidate
```

After any write, we delete the cache entry. The next `GET` will miss and
repopulate with fresh data. This is the discipline caching demands: *every write
path must invalidate what it changes.* Forgetting one is how stale-data bugs are
born — which is exactly why our test mutates the DB behind the cache's back to
prove the cache is really being used, then patches through the API to prove
invalidation works.

### Why we cache the *detail* but not the *list*

You'll notice `GET /ideas` (the list) is deliberately **not** cached, with a
comment saying so. This is a judgment call worth understanding: the list's cache
key would depend on `limit` and `offset` (every page is different), and a single
new idea would have to invalidate *every page* of *every pagination window* — a
mess. The detail endpoint, keyed by a single id, is trivial to invalidate. **Cache
what's easy to invalidate; skip what isn't.** Knowing when *not* to cache is as
important as knowing how.

## 8.4 TTL-only caching: the dashboard

The new dashboard endpoint (`backend/app/api/v1/dashboard.py`,
`GET /api/v1/dashboard/stats`) shows the *other* caching flavor. It computes
aggregate counts — total ideas, ideas by status, jobs by status — which means
several `COUNT` and `GROUP BY` queries:

```python
ideas_total = await session.scalar(
    select(func.count()).select_from(StartupIdea).where(StartupIdea.user_id == user_id)
)
job_status_rows = await session.execute(
    select(Job.status, func.count()).where(Job.user_id == user_id).group_by(Job.status)
)
jobs_by_status = {status: count for status, count in job_status_rows.all()}
```

Aggregations like these get *expensive* as data grows (they scan many rows — this
is where Chapter 3's indexes earn their keep, and where Phase 8's 10k-row load
test will really show their value). But dashboard numbers don't need to be
perfectly live — a 60-second-old count is fine. So we cache the whole result with
just a TTL and **no invalidation at all**:

```python
cached = await cache.get_json(key)
if cached is not None:
    return cached
# ...expensive aggregation...
await cache.set_json(key, data, settings.CACHE_TTL_DASHBOARD)
```

For 60 seconds, every dashboard load is a cheap cache hit; then it expires and the
next load recomputes. This is the right pattern whenever data is *expensive to
compute* but *cheap to be slightly stale* — analytics, counts, trending lists,
leaderboards. (Our test proves it: add an idea after the first load, and the count
*doesn't* change until the TTL would expire — it's serving the cached copy.)

> **Two caching styles, one chapter:** the idea detail uses *invalidate-on-write*
> (must always be correct); the dashboard uses *TTL-only* (allowed to lag).
> Choosing between them per-endpoint is a real design skill.

## 8.5 Rate limiting: protecting the expensive door

Now the second question: how do we stop the evaluation endpoint from being
hammered? Each call costs a real (if small) LLM charge. A bug in a client, an
over-eager retry loop, or just you mashing the button could fire hundreds of
billed calls in seconds. A **rate limiter** caps how many requests a given client
may make in a time window, rejecting the excess with **429 Too Many Requests**.

We use **slowapi**, the standard FastAPI rate limiter, backed by Redis. The setup
is in `backend/app/core/rate_limit.py`:

```python
limiter = Limiter(
    key_func=user_or_ip_key,
    storage_uri=settings.REDIS_URL,        # counters live in Redis
    in_memory_fallback_enabled=True,       # degrade gracefully if Redis blips
)
```

Two ideas here are worth dwelling on.

**Why Redis for the counters?** Because the count must be *shared*. Picture Phase
9, where we run three copies of the API behind a load balancer. If each copy kept
its own in-memory counter, a user could get 10 requests *per copy* = 30 total,
blowing past the limit. Storing the counter in Redis — which all copies share —
means "10 per hour" is enforced *across the whole fleet*. This is the same
"stateless app, shared state in Redis/Postgres" principle behind everything we've
built for scale.

**What's the "key"?** The limiter counts requests *per key*. Our key function
decides whose budget a request counts against — `backend/app/core/rate_limit.py`:

```python
def user_or_ip_key(request: Request) -> str:
    auth = request.headers.get("authorization", "")
    if auth.lower().startswith("bearer "):
        token = auth[7:]
        try:
            payload = jwt.decode(token, options={"verify_signature": False})
            if payload.get("sub"):
                return f"user:{payload['sub']}"   # per-user budget
        except jwt.PyJWTError:
            pass
    return f"ip:{get_remote_address(request)}"     # fall back to per-IP
```

So each logged-in user gets their *own* 10-per-hour budget (keyed by their JWT's
`sub`), and unauthenticated traffic is bucketed by IP. Note we decode the token
*without verifying* it — that's fine here, because this only chooses a counter
bucket; real verification still happens in the endpoint's auth dependency. A
forged token just lands in a junk bucket.

### Applying a limit

A limit is a one-line decorator on the endpoint
(`backend/app/api/v1/evaluations.py`):

```python
@router.post("/{idea_id}/evaluations/{feature_type}", status_code=202)
@limiter.limit(settings.RATE_LIMIT_EVALUATION)     # "10/hour"
async def request_evaluation(request: Request, idea_id, feature_type, ...):
```

The limits are config values (`RATE_LIMIT_EVALUATION = "10/hour"`,
`RATE_LIMIT_WRITE = "60/minute"`), so they're tunable without code changes. We put
a **strict** limit on evaluations (they cost money) and a **looser** one on idea
creation. One slowapi quirk to know: a rate-limited endpoint *must* take a
`request: Request` parameter — that's how slowapi reaches the headers to compute
the key.

Finally, `app/main.py` registers the limiter and installs the handler that turns
an exceeded limit into a clean `429`:

```python
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
```

## 8.6 Wiring Redis in once, at startup

Both new features need a Redis connection. As with the Arq pool in Chapter 7, we
open it **once** in the lifespan and reuse it (`app/main.py`):

```python
@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.arq_pool = await create_arq_pool()           # queue (Phase 3)
    app.state.cache_redis = Redis.from_url(settings.REDIS_URL)
    app.state.cache = RedisCache(app.state.cache_redis)    # cache (Phase 4)
    yield
    await app.state.arq_pool.aclose()
    await app.state.cache_redis.aclose()
```

(The rate limiter manages its own Redis connection internally via slowapi, so we
only explicitly open the queue and cache connections.)

## 8.7 Testing — without Redis, again

The pattern that's served us all along holds here too. Because the endpoints
depend on the `Cache` *interface*, the test suite injects an `InMemoryCache`
(`tests/conftest.py`) and verifies real caching semantics offline:

- **Cache hit + invalidation** (`tests/test_caching.py`): fetch an idea (fills the
  cache), then change the DB row *directly* (no API write, so no invalidation) and
  fetch again — the test asserts you still get the **old** value, *proving* the
  response came from cache. Then it `PATCH`es through the API and asserts the next
  read reflects the change, *proving* invalidation fired.
- **Dashboard TTL caching**: load stats, add another idea, load again — the count
  doesn't change, proving it's cached.
- **The rate-limit key function** (`tests/test_rate_limit.py`): a unit test that a
  request with a token buckets to `user:<sub>` and one without falls back to
  `ip:<address>`.

For the limiter's full `429` behavior we **disable it in tests** (one line in
`conftest.py`: `app.state.limiter.enabled = False`) so request counts don't
interfere with the other tests, and verify the threshold by hand instead (next
section). All 13 tests run in ~0.17 s.

## 8.8 Running and seeing it work

Caching and rate limiting both need Redis — which you already have running from
Phase 3 (Terminal 1). Restart the API so it picks up the new code, then:

**See caching:** fetch an idea twice and watch the second one come back instantly.
(With the API logging at debug level, or by timing with `curl -w`, the first call
touches Postgres and the second doesn't.)
```bash
curl -s "http://localhost:8000/api/v1/ideas/$IDEA_ID" -H "Authorization: Bearer $TOKEN" -w "\n%{time_total}s\n"
curl -s "http://localhost:8000/api/v1/ideas/$IDEA_ID" -H "Authorization: Bearer $TOKEN" -w "\n%{time_total}s\n"  # faster
```
Then `PATCH` the idea and fetch again — the change shows up immediately (the patch
invalidated the cache).

**See the dashboard:**
```bash
curl -s "http://localhost:8000/api/v1/dashboard/stats" -H "Authorization: Bearer $TOKEN" | python -m json.tool
```

**See rate limiting:** the evaluation limit is `10/hour`. Fire it 11 times in a
loop and watch the 11th get rejected with `429`:
```bash
for i in $(seq 1 11); do
  curl -s -o /dev/null -w "request $i -> %{http_code}\n" \
    -X POST "http://localhost:8000/api/v1/ideas/$IDEA_ID/evaluations/competitor_research" \
    -H "Authorization: Bearer $TOKEN"
done
# requests 1-10 -> 202,  request 11 -> 429
```
(Want to test without spending an hour waiting for the window to reset? Temporarily
set `RATE_LIMIT_EVALUATION="3/minute"` in `.env`, restart the API, and you'll trip
it on the 4th call.)

---

**Recap.** We put Redis to work in two new roles. **Caching** makes repeated reads
instant: read-through with invalidate-on-write for idea details (always correct),
and TTL-only for the dashboard (allowed to lag) — and we learned that *not*
caching the list was the right call. **Rate limiting** protects the expensive
evaluation endpoint with a per-user budget enforced via shared Redis counters,
returning `429` when exceeded. Both plug in through the same interface-and-
dependency-injection patterns we've used since Chapter 4, so both are fully
testable without Redis.

**This completes Part 4** — and with it, the backend's core capabilities: CRUD,
AI evaluation, async jobs, caching, and rate limiting. The system is fast,
intelligent, and protected. **Part 5 (Phase 5)** finally gives it a face: a
Next.js frontend with Supabase login, an idea dashboard, and a UI that kicks off
evaluations and polls for results — turning our API into a product a person can
actually use.

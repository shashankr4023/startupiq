# Chapter 12 — Load Testing: Proving It Scales

Way back in Chapter 1 we made a decision that probably felt theoretical: *design
for 10,000 users and 10,000 ideas, even though you'll mostly use it alone.* We
added indexes to columns "because we'll query by them," paginated every list
"because loading all rows won't scale," and cached the dashboard "because the
aggregation gets expensive." All of that was a *bet* that these choices would
matter at scale.

This phase collects the bet. We **generate** thousands of records and **measure** —
and you'll watch, concretely, an index turn a slow scan into an instant lookup,
and see the API hold up (or not) under concurrent load. The lesson of Phase 8
isn't a new feature; it's a new *skill*: how to find out whether your system is
actually fast, instead of hoping.

> No application code changes this phase. Everything lives in `infra/` — seed
> scripts and load tests. We're putting the existing system under a microscope.

## 12.1 First, you need data

A system feels fast with 5 rows. The interesting behavior only appears with tens
of thousands. So step one is **generating realistic volume** — `infra/seed/
seed_data.py`.

The script inserts thousands of ideas under your account. The technique worth
learning is **batched bulk insertion**:

```python
BATCH = 1000
batch = []
for i in range(count):
    batch.append((uuid4(), uid, f"SEED idea {i}", ...))
    if len(batch) == BATCH:
        await conn.executemany("INSERT INTO startup_ideas (...) VALUES ($1,...)", batch)
        batch = []
```

Why batch? Each round trip to the database has overhead (network, transaction).
Inserting 10,000 rows **one at a time** means 10,000 round trips — slow. Inserting
them in **batches of 1,000** means 10 round trips. Same rows, a fraction of the
time. This is the single most important pattern for moving bulk data, and you'll
use it constantly (imports, migrations, backfills).

> A subtle FK lesson surfaces here: `startup_ideas.user_id → profiles.id →
> auth.users.id`. We can't invent a fake user — the foreign key would reject it
> (referential integrity, Chapter 3). So the seed data attaches to a *real*
> account and tags each title `SEED ` for safe cleanup. The database's integrity
> rules constrain even our test data — which is the point of them.

Run it:
```bash
python infra/seed/seed_data.py --email you@example.com --count 10000
# ...and to undo:
python infra/seed/seed_data.py --email you@example.com --cleanup
```

## 12.2 The headline act: watching an index work

Now the payoff for all those `index=True` flags in Chapter 3. The question:
*does an index actually make a query faster, and by how much?* The tool that
answers it is **`EXPLAIN ANALYZE`** — you put it in front of any SQL query and
Postgres tells you *exactly* how it executed: what method it used, how many rows
it touched, and how long it really took.

`infra/loadtest/index_demo.py` makes this vivid and safe. It builds a throwaway
200,000-row table, then runs the *same query shape* as "list my newest ideas"
(`WHERE owner = ? ORDER BY created_at DESC LIMIT 20`) twice — once without an
index, once with — and prints both plans. Run it:

```bash
python infra/loadtest/index_demo.py
```

**Without an index**, the plan looks like this (abridged):
```
Limit  (actual time=48.2..48.3 rows=20)
  ->  Sort  (actual time=48.2..48.2 rows=200 ...)
        ->  Seq Scan on loadtest_demo  (actual time=0.1..41.0 rows=200 loops=1)
              Filter: (owner = '...')
              Rows Removed by Filter: 199800
```

Read the key line: **`Seq Scan`** — a "sequential scan." To find the ~200 rows for
one owner, Postgres read **all 200,000 rows** and threw away 199,800 (`Rows
Removed by Filter`). It's scanning the entire table because it has no faster way
to find the matches. On a big table, this is exactly the kind of query that's
snappy in dev and grinds to a halt in production.

**With an index** on `(owner, created_at DESC)`, the same query:
```
Limit  (actual time=0.05..0.08 rows=20)
  ->  Index Scan using idx_demo_owner_created on loadtest_demo
        (actual time=0.04..0.06 rows=20 loops=1)
        Index Cond: (owner = '...')
```

Now it's an **`Index Scan`**: Postgres jumps *straight* to this owner's rows via
the index (Chapter 3's "the index at the back of a book") — and because the index
is already sorted by `created_at DESC`, it doesn't even need a separate sort step;
it reads the first 20 and stops. Look at the `actual time`: it dropped from ~48ms
to ~0.08ms — **hundreds of times faster**, and that gap *widens* as the table
grows (a seq scan gets linearly slower; an index lookup stays roughly flat).

That single comparison is the whole lesson of database performance in miniature.
When a query is slow, the first question is always: *"Is it doing a Seq Scan on a
big table? If so, what index would let it do an Index Scan instead?"*

> The seed data uses Python-side batched inserts (§12.1); the index demo fills its
> table with one server-side `INSERT … SELECT FROM generate_series(...)` statement
> — zero per-row round trips, the fastest way to manufacture rows *inside* the
> database. Two bulk-loading techniques, side by side.

## 12.3 Load testing the API

Indexes make a *single* query fast. But production means *many* requests at once.
**Load testing** answers: how does the whole API behave when 50 (or 500) users hit
it simultaneously? We use **Locust** (`infra/loadtest/locustfile.py`), which
simulates concurrent users and measures the results.

A Locust "user" is just a script of what a real user does — here, browsing:

```python
class StartupIQUser(HttpUser):
    wait_time = between(1, 3)         # pause 1-3s between actions, like a human
    @task(3)                          # weight 3: do this most often
    def list_ideas(self):
        self.client.get("/api/v1/ideas?limit=20")
    @task(2)
    def dashboard(self):
        self.client.get("/api/v1/dashboard/stats")
    @task(1)
    def idea_detail(self):
        self.client.get(f"/api/v1/ideas/{self.idea_id}")
```

Run it and Locust spins up N of these users, all hitting your API at once:
```bash
export STARTUPIQ_TOKEN=<a fresh token>
locust -f infra/loadtest/locustfile.py --host http://localhost:8000
# open http://localhost:8089, set 50 users, Start
```

### Reading the numbers: throughput and percentiles

Locust reports two things that matter:

- **Throughput (RPS)** — requests per second the system handled. Higher is better;
  it's your capacity.
- **Latency percentiles** — and this is the concept worth internalizing.
  *Average* latency lies. What matters is the distribution:
  - **p50** (median): half of requests were faster than this. The "typical" feel.
  - **p95**: 95% were faster — i.e. the *slowest 1-in-20*. This is what frustrated
    users actually experience.
  - **p99**: the slowest 1-in-100. Your worst-case tail.

  A system with a great average but a terrible p99 still has users hitting
  multi-second waits. Real teams set targets on **p95/p99**, not averages, because
  the tail is where the pain is. (You'll see this everywhere: SLAs are written in
  percentiles.)

### What to watch for — your earlier choices, validated

This is where Phases 3–4 prove themselves under fire:

- **Pagination holds the line.** `/ideas?limit=20` stays fast even with 10,000
  seeded ideas, because it fetches *one page* via the `user_id` index — never all
  rows. Imagine the alternative (returning all 10k every time); it'd collapse.
- **The cache earns its keep.** `/ideas/{id}` and `/dashboard/stats` are
  cached (Chapter 8). Under load, repeated hits are served from Redis, so their
  latency stays low and the database is spared the expensive aggregation on every
  request. Watch their p95 stay flat while uncached paths climb.
- **The rate limiter is doing its job.** If you crank the concurrency on the
  *evaluation* endpoint, you'll see `429`s — that's not a failure, it's the
  protection from Chapter 8 working as designed. (Which is why our read-focused
  load test avoids it.)

If a particular endpoint's p95 balloons under load, *that's* your bottleneck —
and the fix is usually one of: add/adjust an index (§12.2), add a cache, or reduce
what the endpoint does per request. Load testing turns "I think it's fast" into "I
measured it, and here's the slowest part."

## 12.4 A note on where you run this

Pointing a heavy load test at your real Supabase project is fine for a learning
run, but two cautions: the free tier has connection and rate limits (you may see
errors that are *Supabase* throttling, not your code), and the seed data lives in
your real database until you `--cleanup`. For serious, repeatable load
experiments — drop an index, measure; re-add it, measure — a throwaway **local
Postgres** (a one-line `docker run postgres`) you can abuse freely is the
professional setup. The scripts read their connection from `backend/.env`, so
pointing them at a local database is just a different `DATABASE_URL_DIRECT`. The
`index_demo.py` lab, because it builds and drops its own table, is safe to run
anywhere.

---

**Recap.** We stopped adding features and started *measuring*. We learned to
**bulk-insert** data in batches, to read an **`EXPLAIN ANALYZE`** plan and tell a
table-scanning **Seq Scan** from an instant **Index Scan** (watching ~48ms become
~0.08ms), and to **load test** with Locust — reading **throughput** and **p50/p95/
p99** percentiles rather than misleading averages. Crucially, the load test
*validated* our earlier design bets: pagination, caching, and rate limiting all do
exactly what we built them to do, under real concurrent pressure.

**This completes Part 8.** We've proven the single-machine stack scales well. The
final two phases take it *multi-machine*: **Part 9 (Phase 9)** runs the
containers on **Kubernetes**, where we can run several copies of the API behind a
load balancer and watch the Redis-backed rate limiter hold across all of them —
and **Part 10** ships the whole thing to the cloud with CI/CD.

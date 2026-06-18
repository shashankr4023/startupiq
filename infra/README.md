# infra/ — scale & operations tooling

Tooling for Phase 8 (load testing) and later phases. Run the Python scripts from
the **backend virtualenv** (they reuse `asyncpg` + `python-dotenv` and read the
DB connection from `backend/.env`).

```bash
cd backend && source .venv/bin/activate && cd ..
```

## 1. Seed synthetic data — `seed/seed_data.py`

Insert thousands of ideas (+ jobs) under an existing account so the API has
realistic volume to serve.

```bash
# Attach 10,000 seed ideas to your account (found by email):
python infra/seed/seed_data.py --email you@example.com --count 10000

# Remove them again when done:
python infra/seed/seed_data.py --email you@example.com --cleanup
```
Every seeded idea's title starts with `SEED ` so cleanup is exact and safe.

## 2. See what an index does — `loadtest/index_demo.py`

Builds a throwaway 200k-row table and prints `EXPLAIN ANALYZE` for the same query
shape as "list my ideas", first **without** an index (Seq Scan) then **with** one
(Index Scan). Drops the table afterwards — your real schema is untouched.

```bash
python infra/loadtest/index_demo.py
```

## 3. Load test the API — `loadtest/locustfile.py`

Hammer the read endpoints with many concurrent simulated users and measure
throughput + latency percentiles.

```bash
pip install -r infra/loadtest/requirements.txt

export STARTUPIQ_TOKEN=<a fresh Supabase access_token>
# local backend:
locust -f infra/loadtest/locustfile.py --host http://localhost:8000
# or the Docker stack (nginx on port 80):
locust -f infra/loadtest/locustfile.py --host http://localhost
```
Open http://localhost:8089, set users (e.g. 50) + spawn rate, and Start. Or run
headless: add `--headless -u 50 -r 10 -t 30s`.

See **book/12-load-testing.md** for what to look for and how to read the results.

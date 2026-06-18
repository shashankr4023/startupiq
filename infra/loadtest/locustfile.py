"""Load test for StartupIQ's read endpoints, using Locust.

Locust simulates many concurrent users hammering the API and reports throughput
(requests/sec) and latency percentiles (p50/p95/p99). We focus on the read paths
that matter for scale - listing ideas, the dashboard aggregation, and idea detail
(which is cached) - so we can watch how the system behaves under load.

We deliberately do NOT load-test the evaluation endpoint here: it costs real LLM
calls and is rate-limited (429) by design.

Run (from the backend venv with `locust` installed):
    export STARTUPIQ_TOKEN=<a fresh Supabase access_token>
    locust -f infra/loadtest/locustfile.py --host http://localhost:8000

Then open http://localhost:8089 and start a run (e.g. 50 users). Or headless:
    locust -f infra/loadtest/locustfile.py --host http://localhost:8000 \
           --headless -u 50 -r 10 -t 30s
"""

import os

from locust import HttpUser, between, task


class StartupIQUser(HttpUser):
    # Each simulated user waits 1-3s between requests, like a real person.
    wait_time = between(1, 3)

    def on_start(self) -> None:
        token = os.environ.get("STARTUPIQ_TOKEN")
        if not token:
            raise SystemExit("Set STARTUPIQ_TOKEN to a valid Supabase access token.")
        self.client.headers.update({"Authorization": f"Bearer {token}"})

        # Grab one idea id up front for the detail task.
        self.idea_id = None
        resp = self.client.get("/api/v1/ideas?limit=1", name="/ideas (setup)")
        if resp.ok and resp.json():
            self.idea_id = resp.json()[0]["id"]

    @task(3)
    def list_ideas(self) -> None:
        # The paginated list - note we only ever fetch a page, never all rows.
        self.client.get("/api/v1/ideas?limit=20", name="/ideas")

    @task(2)
    def dashboard(self) -> None:
        # The cached aggregation - should stay fast even with lots of data.
        self.client.get("/api/v1/dashboard/stats", name="/dashboard/stats")

    @task(1)
    def idea_detail(self) -> None:
        # Cached read-through - repeated hits should be served from Redis.
        if self.idea_id:
            self.client.get(f"/api/v1/ideas/{self.idea_id}", name="/ideas/{id}")

# Chapter 11 — Webhooks: Telling the Outside World

So far, StartupIQ only speaks when spoken to. A client asks ("run this
evaluation"), the server answers. But real systems often need to do the
opposite: **proactively notify** someone when something happens, without being
asked. "Your evaluation is ready." "A payment cleared." "A build finished." The
standard mechanism for one server to push an event to another is a **webhook**,
and that's what this phase builds.

Webhooks turn StartupIQ from an island into an *integration point*: a user can
wire "when my idea finishes evaluating, ping my Slack / my Zapier / my own app."
Along the way we'll learn three things that show up everywhere in backend
engineering: **event-driven design**, **HMAC signatures**, and **retry/reliability
patterns**.

## 11.1 What a webhook actually is

A webhook is delightfully simple: it's just **a URL you give me, that I POST to
when an event happens.** That's it. The "hook" is the user's URL; the "web" is
that we reach it over plain HTTP.

It's the mirror image of a normal API call:

```
Normal API:   Client ──"do X"──▶ Server ──result──▶ Client     (client initiates)
Webhook:      Server ──"X happened"──▶ Client's URL            (server initiates)
```

The receiver runs a little endpoint that waits for our POST. When our event
fires, we send the event data as JSON to their URL. They do whatever they want
with it. We don't know or care — we just deliver.

Two hard questions immediately appear, and most of this chapter is about them:

1. **Trust:** the receiver gets an HTTP request claiming to be from StartupIQ.
   How do they *know* it's really us and not a prankster POSTing fake "your
   evaluation is done" events? → **signing** (§11.4).
2. **Reliability:** the receiver's server might be down, slow, or flaky when we
   try to deliver. How do we not lose the event? → **retries + an audit log**
   (§11.5).

## 11.2 The data model

Two tables (`backend/app/db/models/webhook.py`):

**`webhooks`** — a user's subscription:
```python
class Webhook(SQLModel, table=True):
    id: UUID
    user_id: UUID                       # whose subscription
    target_url: str                     # where to POST
    secret: str                         # used to sign payloads (see §11.4)
    event_types: list[str]              # e.g. ["evaluation.completed"]
    is_active: bool = True
    created_at: datetime
```

**`webhook_deliveries`** — the audit log, one row per attempt to deliver an event
to a webhook:
```python
class WebhookDelivery(SQLModel, table=True):
    id: UUID
    webhook_id: UUID
    event_type: str
    payload_json: dict                  # exactly what we sent
    response_status: int | None         # what their server replied (or None on error)
    attempt_count: int                  # how many tries so far
    delivered_at: datetime | None       # set when it finally succeeded
    created_at: datetime
```

That second table is the **reliability ledger**. Without it, a failed delivery
would just vanish; with it, the user can open `GET /webhooks/{id}/deliveries` and
see exactly what was sent, when, how many times, and whether it landed. *Making
the invisible visible is half of reliability engineering.*

## 11.3 Managing subscriptions (the easy part)

The CRUD endpoints (`backend/app/api/v1/webhooks.py`) are familiar territory —
the same patterns as ideas: ownership checks, validation, soft/hard delete:

- `POST /webhooks` — register `{target_url, event_types}`. We **generate the
  secret server-side** (`secrets.token_hex(32)`) and return it once.
- `GET /webhooks`, `PATCH /webhooks/{id}`, `DELETE /webhooks/{id}`
- `GET /webhooks/{id}/deliveries` — the audit log.

The only new wrinkle: we validate `event_types` against a known set
(`SUPPORTED_EVENTS = {"evaluation.completed", "evaluation.failed"}`) and `422` on
anything else — you can't subscribe to an event that doesn't exist.

The interesting part isn't the CRUD. It's what happens when an evaluation
finishes.

## 11.4 Event-driven design: firing the event

Recall the worker's `run_evaluation_feature` (Chapter 7). When a job finishes, it
now does one more thing — it **emits an event**:

```python
# app/worker/tasks.py, after the job is marked completed/failed
redis = ctx.get("redis")
if redis is not None:
    event = "evaluation.completed" if job.status == "completed" else "evaluation.failed"
    await redis.enqueue_job("dispatch_webhook_event", str(job.user_id), event, {
        "event": event, "job_id": str(job.id), "idea_id": str(job.idea_id),
        "feature_type": job.feature_type, "status": job.status, "result": job.result_json,
    })
```

This is **event-driven design** in miniature. The evaluation task doesn't know or
care *who* is listening — it just announces "evaluation.completed happened" and
moves on. Something else entirely (the dispatcher) decides what to do about it.
That decoupling is powerful: tomorrow we could add email notifications or
analytics that also react to the same event, *without touching the evaluation
code at all*. The emitter and the reactors are independent.

Notice *how* it emits: it enqueues another Arq job (using the Redis pool that Arq
helpfully puts in `ctx`). It does **not** POST to the webhook inline. Why?
Because delivering to N webhooks — each possibly slow or failing — has nothing to
do with running an evaluation, and we don't want webhook problems to slow down or
break the evaluation task. So the event is just dropped on the queue (Chapter 7's
pattern, reused) for a *separate* set of jobs to handle. Slow, unreliable work
gets pushed to the background — the same instinct as the whole of Phase 3.

### Fan-out, then deliver

Delivery is split into **two** task types (`app/worker/webhooks.py`), and the
split matters:

```
dispatch_webhook_event(user, event, payload)      ← "fan-out"
   │  find this user's active webhooks subscribed to this event
   │  for each: create a delivery audit row
   └─ enqueue ──▶ deliver_webhook(delivery_id)     ← "one POST", retried alone
```

- **`dispatch_webhook_event`** is the fan-out: it looks up which of the user's
  webhooks care about this event, creates a `webhook_deliveries` row for each,
  and enqueues an individual `deliver_webhook` job per webhook.
- **`deliver_webhook`** does exactly one POST to exactly one URL.

Why separate them? **So each webhook's delivery is retried independently.** If a
user has three webhooks and one is down, we don't want retrying that one to
re-send to the two that already succeeded (double-delivery is a real bug). One
delivery job per target = clean, isolated retries. This is a classic distributed-
systems shape: a fan-out step that schedules independent unit-of-work jobs.

## 11.5 Signing: proving it's really us

Here's the trust problem again: the receiver's endpoint is a public URL. Anyone
on the internet could POST `{"event": "evaluation.completed", ...}` to it and
fake an event. How does the receiver know a given request genuinely came from
StartupIQ?

The answer is an **HMAC signature**. When the user registered the webhook, we
gave them a `secret` — a random string only they and we know. For every delivery,
we compute a fingerprint of the *exact bytes* of the payload, keyed by that
secret, and send it in a header (`app/worker/webhooks.py`):

```python
def sign(secret: str, body: bytes) -> str:
    return hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()

# ...when delivering:
body = json.dumps(delivery.payload_json, separators=(",", ":")).encode()
headers = {
    "Content-Type": "application/json",
    "X-StartupIQ-Event": delivery.event_type,
    "X-StartupIQ-Signature": f"sha256={sign(webhook.secret, body)}",
}
```

**HMAC** (Hash-based Message Authentication Code) combines the message with a
secret key and runs it through a hash (SHA-256). The result has two properties
that solve our problem at once:

1. **Authenticity** — only someone who knows the secret could produce a matching
   signature. The receiver recomputes `HMAC(their copy of the secret, the bytes
   they received)` and checks it equals our header. If it matches, it's provably
   from us.
2. **Integrity** — the signature covers the exact payload bytes. If even one
   character was changed in transit (or by an attacker), the recomputed signature
   won't match, and the receiver rejects it.

This is the *same idea as JWT verification* from Chapter 5 — a keyed signature
proving a message is authentic and untampered — now applied in the outbound
direction. (It's exactly how Stripe, GitHub, and most real webhook providers sign
their webhooks; the header name differs, the mechanism is identical.)

> **Subtle but critical:** we sign the *exact bytes we send* and send the *exact
> bytes we signed* — serialize the JSON once into `body`, sign `body`, POST
> `body`. If we signed a dict and let the HTTP library re-serialize it
> differently, the receiver's recomputed signature wouldn't match. "Sign the
> bytes on the wire" is the rule.

## 11.6 Reliability: retries with backoff

The receiver might be down or slow exactly when we deliver. Dropping the event
would be bad. So `deliver_webhook` retries:

```python
async def deliver_webhook(ctx, delivery_id):
    attempt = ctx.get("job_try", 1)              # Arq tells us which try this is
    # ...load delivery + webhook, build signed request...
    delivery.attempt_count = attempt
    try:
        status_code = await _post(webhook.target_url, body, headers)
    except Exception:
        status_code = None                       # network error = failed attempt
    delivery.response_status = status_code
    success = status_code is not None and 200 <= status_code < 300
    if success:
        delivery.delivered_at = datetime.utcnow()
    await session.commit()                        # record EVERY attempt in the ledger

    if success:
        return "delivered"
    if attempt < MAX_TRIES:
        raise Retry(defer=2 ** attempt)           # back off: 2s, 4s, 8s, 16s...
    return "failed"                               # gave up after MAX_TRIES
```

Two reliability ideas here:

- **Retry with exponential backoff.** On failure we raise Arq's `Retry`, which
  reschedules the job — but with `defer=2**attempt`, so the gap grows: ~2s, 4s,
  8s, 16s. Backing off (rather than hammering every second) gives a struggling
  receiver room to recover and avoids making their outage worse. Arq increments
  `job_try` each time; after `MAX_TRIES` we stop and mark it failed. This is the
  *standard* shape for delivering to an unreliable dependency (the SDK retry
  logic from the LLM providers does the same thing internally).
- **Record every attempt.** We `commit()` the delivery row on *every* try — so
  the audit log shows `attempt_count` climbing and the last `response_status`,
  win or lose. When a user asks "why didn't my webhook fire?", the answer is
  right there in `GET /webhooks/{id}/deliveries`.

A note on a related concept the receiver must handle: **idempotency**. Because we
retry, a receiver could occasionally get the *same* event twice (e.g. we deliver
successfully but their `200` reply gets lost, so we retry). Well-behaved
receivers deduplicate on an event id. Our payload carries `job_id`, which serves
that purpose. "At-least-once delivery" — the receiver must tolerate duplicates —
is the realistic guarantee almost all webhook systems provide.

## 11.7 Testing it without a real receiver

The whole subsystem is tested offline (`tests/test_webhooks.py`,
`test_webhook_dispatch.py`):

- **CRUD** — register/list/delete, ownership `404`s, and that an unknown event
  type is rejected with `422`.
- **`sign()`** — a unit test that our signature equals a hand-computed HMAC.
- **Fan-out** — seed three webhooks (one matching+active, one for the wrong
  event, one inactive); assert `dispatch_webhook_event` creates a delivery and
  enqueues a job for *only* the matching active one.
- **Delivery** — monkeypatch the `_post` function (so no real HTTP): a `200` marks
  the delivery `delivered`; a `500` records the failure and **raises `Retry`** on
  an early attempt, then returns `"failed"` on the final attempt.

Isolating the network call behind a `_post` function (so tests can swap it) is the
same seam-for-testability move we've used since Chapter 6. All 20 tests run in
~0.2s, no network.

## 11.8 Trying it live

Webhooks are best seen with a real receiver. The easiest is a throwaway endpoint:

1. **Get a test receiver URL.** Open **https://webhook.site** — it gives you a
   unique URL and shows every request it receives, live (headers and body).
2. **Register it** (with the API running, Chapter 7's three terminals):
   ```bash
   curl -X POST http://localhost:8000/api/v1/webhooks \
     -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" \
     -d '{"target_url":"https://webhook.site/your-unique-id","event_types":["evaluation.completed"]}'
   ```
   Save the `secret` from the response.
3. **Trigger an evaluation** (any feature on any idea). When the worker finishes
   the job, watch webhook.site — a POST arrives within seconds, carrying the
   event JSON, an `X-StartupIQ-Signature: sha256=…` header, and `X-StartupIQ-
   Event: evaluation.completed`.
4. **See the audit log:**
   ```bash
   curl "http://localhost:8000/api/v1/webhooks/$WEBHOOK_ID/deliveries" \
     -H "Authorization: Bearer $TOKEN" | python -m json.tool
   # → response_status: 200, attempt_count: 1, delivered_at: ...
   ```
5. **See a retry:** point a webhook at a URL that returns an error (or a closed
   port), trigger an evaluation, and watch `attempt_count` climb in the deliveries
   log as the worker backs off and retries.

> Verifying the signature on the receiving side (if you build your own receiver)
> is: read the raw body bytes, compute `HMAC-SHA256(secret, body)`, and compare to
> the hex after `sha256=` in the header. Match = trust it.

---

**Recap.** StartupIQ can now push events outward. Users register **webhooks**
(URL + events + a generated secret); when an evaluation finishes, the worker
**emits an event** (event-driven design) that a **fan-out** dispatcher turns into
independent, per-webhook delivery jobs. Each delivery **signs** the exact payload
with HMAC-SHA256 (authenticity + integrity, just like JWTs in reverse),
**retries with exponential backoff** on failure, and records **every attempt** in
a delivery audit log. We tested the whole thing — signing, fan-out, success, and
retry — without sending a single real HTTP request.

**This completes Part 7.** The product is now a genuine integration point. The
remaining phases stop adding features and instead harden what we have for **scale
and operations**: **Part 8 (Phase 8)** generates 10,000 records and load-tests the
system to find bottlenecks and prove our indexes and caches earn their keep.

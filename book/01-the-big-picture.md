# Chapter 1 — The Big Picture

Before we touch a single line of code, you need a mental model of the whole
system. If you can't draw it on a napkin, you can't reason about it. So let's
build that picture.

## 1.1 What StartupIQ does, in one sentence

> A user types in a startup idea; the system uses an AI to research competitors,
> size the market, identify risks, propose an MVP, and suggest revenue models;
> then it shows the user a structured report.

That's it. Everything we build serves that sentence.

## 1.2 The components, and why each exists

A real web product is never one program. It's several specialized programs
talking to each other. Here's our cast of characters and the *one job* each has:

```
        ┌────────────────────┐
        │  Browser (the user)│
        └─────────┬──────────┘
                  │  HTTPS
        ┌─────────▼──────────┐   "The face."  React/Next.js. What the user
        │   Frontend          │   sees and clicks. Knows nothing about the
        │   (Next.js)         │   database — it only calls the backend's API.
        └─────────┬──────────┘
                  │  API calls (JSON over HTTP) + a login token
        ┌─────────▼──────────┐   "The brain / traffic controller."  FastAPI.
        │   Backend API       │   Validates who you are, enforces rules, reads
        │   (FastAPI)         │   & writes the database, hands slow work to the
        └──┬───────────────┬──┘   queue. Does NOT call the AI itself.
           │               │
   ┌───────▼──────┐  ┌─────▼──────┐
   │  Database    │  │   Redis     │   "Memory" vs "scratchpad + mailbox."
   │  (Postgres / │  │             │   Postgres = permanent truth. Redis =
   │   Supabase)  │  │             │   fast temporary store, a job queue,
   └──────────────┘  └─────┬──────┘   and a rate-limit counter.
                           │  picks up jobs
                     ┌─────▼──────┐   "The worker."  A separate program that
                     │   Worker    │   does the slow AI calls in the background
                     │   (Arq)     │   so the API stays fast and responsive.
                     └─────┬──────┘
                           │  calls
                     ┌─────▼──────┐   "The interchangeable AI engine."
                     │ LLM Provider│   OpenAI while we develop, Claude in
                     │ (OpenAI /   │   production — swappable behind one
                     │  Claude)    │   interface.
                     └────────────┘
```

You do not need all of this to exist today. In Phase 1, only the **Backend
API** and the **Database** are real. Everything else is a box we'll fill in
later. But knowing the final shape tells you *where each new piece fits* when
we add it — so nothing feels random.

## 1.3 The single most important idea: layers

Look again at the backend. Inside it, we don't write one giant file. We split
responsibilities into **layers**, where each layer talks only to the one
directly below it:

```
   An HTTP request arrives
            │
            ▼
   ┌─────────────────────┐
   │ API layer            │   "Which URLs exist? What JSON comes in/out?"
   │ app/api/v1/ideas.py  │   Files: the route handlers.
   └─────────┬───────────┘
             ▼
   ┌─────────────────────┐
   │ Security layer       │   "Who is making this request?"
   │ app/core/security.py │
   └─────────┬───────────┘
             ▼
   ┌─────────────────────┐
   │ Schema layer         │   "Is this JSON valid? Shape it."
   │ app/schemas/idea.py  │
   └─────────┬───────────┘
             ▼
   ┌─────────────────────┐
   │ Data layer           │   "Talk to Postgres."
   │ app/db/...           │
   └─────────────────────┘
```

**Why bother splitting it up?** Because change is the only constant. When we
later add caching, we touch *one* layer. When we swap OpenAI for Claude, we
touch *one* file. If everything were tangled into one file, every change would
risk breaking everything else. Layers are how you keep a growing system from
collapsing under its own weight. This pattern has a name — **separation of
concerns** — and it is the backbone of all good software design.

## 1.4 The 10-phase map

We build StartupIQ in ten phases. Each phase adds *one* major capability and
teaches *one* cluster of skills. You are here: **end of Phase 1.**

| Phase | What we build | What you learn |
|---|---|---|
| **1 ✅** | Backend skeleton, database, login, store/fetch ideas | FastAPI, REST, DB design, auth basics |
| 2 | The AI engine (one synchronous evaluation) | Abstraction/interfaces, calling LLMs |
| 3 | Background jobs + worker + queue | Async systems, queues, Redis as a broker |
| 4 | Caching + rate limiting | Performance, Redis as cache, throttling |
| 5 | The Next.js frontend + login UI | Full-stack integration |
| 6 | Docker Compose (run it all with one command) | Containers, orchestration |
| 7 | Webhooks (notify other systems) | Event-driven design, reliability |
| 8 | Load testing with 10,000 fake records | Scalability, database indexing |
| 9 | Kubernetes | Container orchestration at scale |
| 10 | Cloud deployment + CI/CD | Shipping to the real world |

Notice the order is chosen so each phase only introduces *new* concepts while
*reusing* everything before it. By Phase 4 you'll be adding a cache to
endpoints you already understand cold — so all your attention goes to the cache.

## 1.5 What "designed for 10,000 users" actually means here

You'll mostly use this app alone. So why design for 10,000 users and 10,000
ideas? Because the *interesting lessons* only appear at scale:

- A query that's instant on 5 rows can be painfully slow on 50,000 — unless you
  added the right **index** (Chapter 3).
- Loading "all ideas" into memory is fine for you, fatal for 10,000 users —
  which is why every list endpoint has **pagination** from day one (Chapter 4).

We design for scale not because we'll hit it, but because *designing as if we
will* is how you learn the habits that matter. In Phase 8 we'll generate 10,000
fake ideas and actually measure these effects.

---

**Next:** [Chapter 2 — Project Setup](02-project-setup.md), where we turn an
empty folder into a real Python project.

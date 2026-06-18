# Building StartupIQ — A Learner's Companion

> A book that grows alongside the code. Every chapter explains not just *what*
> we built, but *why* we built it that way — assuming you're starting from
> close to zero.

This is the companion text for the **StartupIQ** project: a Startup Idea
Evaluator we're building from scratch to learn backend engineering, system
design, and the infrastructure skills that turn a script into a real,
deployable product.

## How to read this book

- **Read it next to the code.** Every chapter points at real files in this
  repo (e.g. `backend/app/api/v1/ideas.py`). Open them side by side.
- **Each Part maps to a build Phase.** We build the product in 10 phases (see
  Chapter 1). The book gains a Part as each phase is completed, so the book is
  never ahead of what actually exists in the repo.
- **Concepts are introduced when we need them,** not all up front. You'll learn
  what a JWT is in the chapter where we first verify one — because that's when
  it sticks.
- **"War stories" are included on purpose.** When we hit a real bug (like a JWT
  that wouldn't validate), we keep the debugging story. Debugging *is* the
  skill; watching someone reason through a failure teaches more than clean
  code ever does.

## Table of Contents

### Part 0 — Orientation
- [Preface — who this is for and how to use it](00-preface.md)

### Part 1 — Foundations (Phase 1: Backend skeleton, DB, Auth, CRUD)
- [Chapter 1 — The Big Picture: what we're building and the 10-phase map](01-the-big-picture.md)
- [Chapter 2 — Project Setup: repo layout, virtualenvs, and 12-factor config](02-project-setup.md)
- [Chapter 3 — Database Design: Postgres, Supabase, SQLModel, and migrations](03-database-design.md)
- [Chapter 4 — API Design: FastAPI, REST, schemas, and dependency injection](04-api-design.md)
- [Chapter 5 — Authentication: JWTs, Supabase Auth, and a real debugging story](05-authentication.md)

### Part 2 — Making It Intelligent (Phase 2: the LLM evaluation engine)
- [Chapter 6 — The Evaluation Engine: a provider-agnostic LLM abstraction](06-llm-abstraction.md)

### Part 3 — Making It Scale (Phase 3: async jobs, queues, and a worker)
- [Chapter 7 — Background Jobs: queues, workers, and why the API got faster](07-async-jobs.md)

### Part 4 — Making It Fast & Safe (Phase 4: caching and rate limiting)
- [Chapter 8 — Caching and Rate Limiting: Redis's other two jobs](08-caching-rate-limiting.md)

### Part 5 — Giving It a Face (Phase 5: the Next.js frontend)
- [Chapter 9 — The Frontend: a face for the API](09-frontend.md)

### Part 6 — Packaging It (Phase 6: Docker & one-command startup)
- [Chapter 10 — Docker: the whole stack in one command](10-docker.md)

### Part 7 — Talking Outward (Phase 7: webhooks)
- [Chapter 11 — Webhooks: telling the outside world](11-webhooks.md)

### Part 8 — Proving It Scales (Phase 8: load testing & DB performance)
- [Chapter 12 — Load Testing: proving it scales](12-load-testing.md)

### Part 9 — Running Many Copies (Phase 9: Kubernetes)
- [Chapter 13 — Kubernetes: running many copies](13-kubernetes.md)

### Part 10 — Shipping It (Phase 10: CI/CD & the cloud)
- [Chapter 14 — Shipping It: CI/CD and the cloud](14-cloud-cicd.md)
- [Epilogue — what you built, and what you learned](15-epilogue.md)

### Appendices
- [Glossary — every term, in plain English](99-glossary.md)

---

*All 10 phases are complete. The build — and the book — are done. See the
[Epilogue](15-epilogue.md).*

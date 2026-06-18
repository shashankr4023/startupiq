# Preface

## Who this book is for

You, specifically: someone who can write some code, wants to *understand*
backend systems, and learns best by building one real thing all the way
through rather than reading ten disconnected tutorials.

You don't need prior experience with FastAPI, Postgres, Redis, Docker, or
Kubernetes. You *do* need a little comfort with Python and the command line,
and a willingness to be confused for a few minutes before things click. That
confusion is normal and is not a sign you're doing it wrong.

## Why build a "Startup Idea Evaluator" to learn this?

Because the product is just an excuse. We needed something that naturally
demands every concept on the syllabus:

| We want to learn… | …so the product needs… |
|---|---|
| Database design | to store users, ideas, and evaluations |
| API design | endpoints clients call to create and read those things |
| Authentication | so each user only sees their own ideas |
| Background jobs & queues | because asking an AI to analyze an idea is slow |
| Caching | because re-reading the same analysis should be instant |
| Rate limiting | because AI calls cost money and must be throttled |
| Webhooks | to notify other systems when an analysis finishes |
| Docker / Kubernetes | to run all these pieces together, reproducibly |
| Scalability & reliability | to survive 10,000 users and the occasional crash |

If the product were simpler, we couldn't justify learning these things. The
evaluator is the scaffolding; the skills are the point.

## The core philosophy: build it in layers, learn it in layers

We will **not** build the whole system at once. We build the simplest thing
that works, prove it works, then add one capability at a time. Phase 1 doesn't
even call an AI — it just stores and retrieves ideas. That's deliberate: you
can't debug a queue, a cache, *and* an AI integration simultaneously when
you're learning. One new idea at a time.

This mirrors a real engineering principle: **make it work, make it right, make
it fast — in that order.**

## A note on the "war stories"

Real engineering is mostly debugging. In Phase 1 alone we hit three separate
auth failures stacked on top of each other (Chapter 5). Most tutorials hide
that. We keep it, because the most valuable thing you can learn is not the
final correct code — it's *how to reason from a confusing error message to a
fix*. When you see a ❌ in this book, slow down: that's where the real learning
is.

Let's begin.

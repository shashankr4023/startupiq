# Chapter 4 — API Design

We have a database full of ideas. But the outside world — your future frontend,
a curl command, a mobile app — can't touch Postgres directly (that would be a
security nightmare). It goes through an **API**: a controlled set of doors, each
with rules about who may enter and what they may do. This chapter builds those
doors with **FastAPI**.

## 4.1 What "API" really means here

An **API** (Application Programming Interface) is a contract: "send a request
shaped *like this* to *this URL*, and you'll get a response shaped *like that*."
Our API speaks **REST over HTTP with JSON** — the lingua franca of the web.

The vocabulary you need:

- **HTTP method** = the *verb*, what you want to do:
  - `GET` — read something (never changes data)
  - `POST` — create something new
  - `PATCH` — partially update something
  - `DELETE` — remove something
- **URL / path** = the *noun*, which thing: `/api/v1/ideas/123`
- **Status code** = the result in a number: `200` OK, `201` Created, `404` Not
  Found, `401` Unauthorized. (You'll memorize these without trying.)
- **Request/response body** = the data, as JSON.

## 4.2 REST: designing URLs around *resources*

REST's core idea: design your URLs around **resources** (nouns), and use HTTP
methods (verbs) to act on them. So for "ideas," we don't invent URLs like
`/createIdea` or `/getMyIdeas`. We have *one* noun, `/ideas`, and vary the verb:

| Verb + path | Meaning |
|---|---|
| `POST /api/v1/ideas` | Create a new idea |
| `GET /api/v1/ideas` | List my ideas |
| `GET /api/v1/ideas/{id}` | Get one specific idea |
| `PATCH /api/v1/ideas/{id}` | Update one idea |
| `DELETE /api/v1/ideas/{id}` | Archive one idea |

This consistency means once you learn the pattern, you can *guess* the API for
any new resource (tags, webhooks, evaluations) — they'll all follow the same
shape. Predictability is a feature.

### Why `/api/v1/`?

The `v1` is **versioning**. Someday you'll want to change how the API works in a
way that would break existing clients. Instead of breaking them, you introduce
`/api/v2/` and let old clients keep using `/api/v1/`. Building the version in
from day one costs nothing and saves enormous pain later. The path-based style
(`/v1/` in the URL) is the simplest kind, which is exactly why we chose it.

## 4.3 Two kinds of "shape": models vs schemas

Here's a distinction that confuses every beginner, so let's nail it.

- A **model** (`app/db/models/idea.py`, Chapter 3) describes the shape of a row
  *in the database*.
- A **schema** (`app/schemas/idea.py`) describes the shape of JSON *crossing the
  API boundary* — what a client may send, and what we send back.

Why aren't they the same? Because the database shape and the public shape
*should* differ — and that difference is a security boundary. Look at
`app/schemas/idea.py`:

```python
from pydantic import BaseModel, ConfigDict, Field

class IdeaCreate(BaseModel):              # what a client SENDS to create an idea
    title: str = Field(min_length=1, max_length=200)
    description: str = Field(min_length=1)
    industry: str | None = None
    target_market: str | None = None

class IdeaRead(BaseModel):                # what we SEND BACK
    id: UUID
    user_id: UUID
    title: str
    description: str
    industry: str | None
    target_market: str | None
    status: str
    created_at: datetime
    updated_at: datetime
    model_config = ConfigDict(from_attributes=True)

class IdeaUpdate(BaseModel):              # what a client sends to PATCH (all optional)
    title: str | None = Field(default=None, min_length=1, max_length=200)
    # ... every field optional, because PATCH updates only what's provided
```

Notice the crucial detail: **`IdeaCreate` has no `id`, no `user_id`, no
`status`, no timestamps.** Those are server-controlled. If a client could send
`user_id`, a malicious user could create ideas *as someone else*. By simply not
including it in the input schema, that attack is impossible. The schema isn't
just validation — it's a wall defining exactly what a client is allowed to
influence.

These schemas are built with **Pydantic**, which validates automatically:
`Field(min_length=1, max_length=200)` means an empty title or a 5,000-character
one is rejected *before your code ever runs*, with a clear error. You declare
the rules; Pydantic enforces them.

`from_attributes=True` on `IdeaRead` is a small convenience: it lets FastAPI
build the JSON response straight from a database `StartupIdea` object (reading
its attributes), so we don't manually copy field by field.

## 4.4 The endpoints, dissected

Here's the create endpoint from `app/api/v1/ideas.py`. Every line is doing a
job worth understanding:

```python
router = APIRouter(prefix="/ideas", tags=["ideas"])

@router.post("", response_model=IdeaRead, status_code=status.HTTP_201_CREATED)
async def create_idea(
    payload: IdeaCreate,                              # ① the validated request body
    user_id: UUID = Depends(get_current_user),       # ② who's calling (Chapter 5)
    session: AsyncSession = Depends(get_session),    # ③ a database session
) -> StartupIdea:
    idea = StartupIdea(**payload.model_dump(), user_id=user_id)   # ④ build the row
    session.add(idea)                                # ⑤ stage it
    await session.commit()                           # ⑥ save it for real
    await session.refresh(idea)                      # ⑦ reload DB-filled fields
    return idea                                      # ⑧ FastAPI → JSON via IdeaRead
```

1. **`payload: IdeaCreate`** — FastAPI sees this type and *automatically* reads
   the request's JSON body, validates it against `IdeaCreate`, and rejects bad
   input with a `422` error. You never write parsing code.
2. **`user_id = Depends(get_current_user)`** — dependency injection (next
   section). FastAPI runs the auth check and hands us the verified user's id.
3. **`session = Depends(get_session)`** — likewise hands us a fresh DB session.
4. **`StartupIdea(**payload.model_dump(), user_id=user_id)`** — we take the
   client's fields and *we* attach the `user_id` from the token. The client
   could not set it even if they tried (§4.3).
5–7. **add → commit → refresh** — stage the new row, write it to Postgres, then
   reload it to pick up DB-generated values (`id`, `created_at`).
8. **`return idea`** — we return a database object, but `response_model=IdeaRead`
   tells FastAPI to convert it into JSON shaped like `IdeaRead`. If `StartupIdea`
   had a secret field, it wouldn't leak — only `IdeaRead`'s fields go out.

### Reading: the authorization pattern

The `get_idea` endpoint shows a pattern repeated in *every* read/update/delete:

```python
@router.get("/{idea_id}", response_model=IdeaRead)
async def get_idea(idea_id: UUID, user_id=Depends(get_current_user), session=Depends(get_session)):
    idea = await session.get(StartupIdea, idea_id)
    if idea is None or idea.user_id != user_id:        # ← the critical check
        raise HTTPException(status_code=404, detail="Idea not found")
    return idea
```

That `idea.user_id != user_id` check is **authorization**, and it's worth
pausing on. The token proved *who you are* (**authentication**). This line
enforces *what you're allowed to see* (**authorization**). They are different
things, and you need both. Without this line, anyone could fetch anyone else's
idea by guessing its id.

Subtle touch: we return **`404` Not Found**, not `403` Forbidden, when the idea
belongs to someone else. Why? Returning `403` would *confirm* "yes, an idea with
this id exists, you just can't see it" — leaking information. `404` reveals
nothing. Small decision, real security thinking.

### The list endpoint and pagination

```python
@router.get("", response_model=list[IdeaRead])
async def list_ideas(user_id=Depends(get_current_user), session=Depends(get_session),
                     limit: int = 20, offset: int = 0):
    result = await session.execute(
        select(StartupIdea)
        .where(StartupIdea.user_id == user_id)         # only MY ideas
        .order_by(StartupIdea.created_at.desc())       # newest first
        .limit(limit).offset(offset)                   # one page at a time
    )
    return list(result.scalars().all())
```

`limit` and `offset` implement **pagination**. Instead of returning *all* of a
user's ideas (fine for 5, catastrophic for 10,000), we return a *page* — 20 at a
time. `offset=0` is the first page, `offset=20` the second, and so on. This is
why we designed for scale from day one (Chapter 1): the habit of never loading
an unbounded list is baked in before we ever have a big list. Note also `.where(
user_id == ...)` — the database does the filtering *and* uses the `user_id`
index we created in Chapter 3. Layers cooperating.

## 4.5 Dependency Injection: FastAPI's superpower

You've now seen `Depends(...)` several times. This is **dependency injection
(DI)**, and it's the idea that makes FastAPI so clean.

Instead of each endpoint manually doing "parse the auth header, verify the
token, open a database session," it just *declares what it needs*:

```python
user_id: UUID = Depends(get_current_user)
session: AsyncSession = Depends(get_session)
```

…and FastAPI *provides* those things before the function runs. The endpoint
reads like a statement of requirements: "to do this, I need the current user and
a database session." The wiring is handled for you.

Why this is powerful:

- **No repetition.** Auth logic lives in *one* function, used by every endpoint.
- **Testability.** In a test, you can swap a dependency for a fake one (a fake
  user, a test database) without touching the endpoint code.
- **Readability.** The function signature documents exactly what it depends on.

You'll lean on DI constantly. When we add caching and rate limiting in Phase 4,
they'll plug in as dependencies too.

## 4.6 Wiring it together: routers and `main.py`

We don't pile every endpoint into one file. Each resource gets its own
**router** (`ideas.py` has the ideas router), and they're combined:

```python
# app/api/v1/router.py
api_router = APIRouter(prefix="/api/v1")
api_router.include_router(ideas.router)        # later: + evaluations, tags, webhooks...
```

The `prefix="/api/v1"` here is *why* every ideas URL automatically starts with
`/api/v1` — set once, applies to all. Then the top-level app pulls it all in,
`app/main.py`:

```python
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.api.v1.router import api_router
from app.core.config import settings

app = FastAPI(title="StartupIQ API", version="0.1.0")

app.add_middleware(                              # ← CORS, explained below
    CORSMiddleware,
    allow_origins=[settings.FRONTEND_ORIGIN],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(api_router)

@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}
```

Two things deserve a note:

- **CORS middleware.** By default, a browser will *block* JavaScript running on
  `localhost:3000` (your future frontend) from calling an API on a different
  origin like `localhost:8000`. This is a browser security feature. The CORS
  (Cross-Origin Resource Sharing) middleware explicitly says "I permit requests
  from this origin," unblocking your own frontend. It's not boilerplate — it's a
  real security mechanism you're consciously configuring. **Middleware**, by the
  way, is code that wraps *every* request/response — a layer that everything
  passes through.

- **The `/health` endpoint.** It just returns `{"status": "ok"}`. Trivial, but
  vital: in later phases, load balancers and Kubernetes will repeatedly call
  `/health` to ask "is this server alive and ready for traffic?" before routing
  users to it. Nearly every production service has one.

## 4.7 Try it yourself

With the server running (`uvicorn app.main:app --reload`), FastAPI gives you a
free interactive API explorer at **http://localhost:8000/docs**. It reads your
schemas and routes and generates a clickable UI — you can try every endpoint in
the browser. This "Swagger UI" is generated entirely from the type hints and
schemas you already wrote. (You'll still need a login token to call protected
endpoints — which is exactly where Chapter 5 picks up.)

---

**Recap.** We built a RESTful, versioned API where input/output shapes are
enforced by Pydantic schemas (a security boundary), every endpoint checks
ownership (authorization), lists are paginated (scale), and cross-cutting needs
like "the current user" and "a DB session" are supplied by dependency injection.

**Next:** [Chapter 5 — Authentication](05-authentication.md) — how the server
knows *who* is calling, and a three-layered real bug we debugged to make it
work.

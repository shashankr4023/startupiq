# Chapter 2 — Project Setup

In which an empty folder becomes a real project. Boring? No. The decisions here
quietly shape everything that follows.

## 2.1 The repository layout (a "monorepo")

We keep the *entire* product — backend, future frontend, future worker,
infrastructure — in one Git repository. This is called a **monorepo** ("mono" =
one). The alternative is a separate repo per piece.

For a solo learner, a monorepo wins: one place to clone, one place to search,
and you can see how the pieces relate. Here's our top-level shape (some folders
are empty placeholders for future phases):

```
Startup-Idea-Evaluator/
├── backend/      ← the FastAPI API. This is all of Phase 1.
├── worker/       ← (Phase 3) the background job runner
├── frontend/     ← (Phase 5) the Next.js UI
├── docker/       ← (Phase 6) how to run it all together
├── infra/        ← (Phase 8-9) Kubernetes + load-test seed data
├── book/         ← you are reading this
└── docs/         ← architecture notes
```

**Why separate top-level folders instead of one big `app/`?** Because
`backend`, `worker`, and `frontend` are genuinely *different programs* that will
eventually run in *different containers* on *different machines*. The folder
boundary mirrors the runtime boundary. When something is a separate process in
production, it's healthy for it to feel separate in the codebase too.

## 2.2 Inside `backend/` — the Python package

```
backend/
├── app/                    ← the actual application code (a Python "package")
│   ├── main.py             ← the entry point: creates the FastAPI app
│   ├── core/               ← cross-cutting concerns (config, security)
│   ├── db/                 ← database connection + table definitions
│   ├── schemas/            ← the shapes of JSON going in and out
│   └── api/                ← the URL route handlers
├── alembic/                ← database migration scripts (Chapter 3)
├── tests/                  ← automated tests
├── scripts/                ← one-off helper scripts (e.g. our JWT debugger)
├── pyproject.toml          ← the project's identity + dependency list
└── .env                    ← secrets & config (NEVER committed to Git)
```

Those `__init__.py` files you see in each folder are how Python knows a folder
is part of an importable **package**. They're often empty; their mere presence
is the signal. That's why we can write `from app.core.config import settings`
anywhere — `app` is a package, `core` is a sub-package, and so on.

## 2.3 The virtual environment: why `.venv`

When you `pip install fastapi`, where does it go? If installed globally, every
Python project on your machine shares the same library versions — and Project A
needing `fastapi 0.100` while Project B needs `fastapi 0.115` becomes a war.

A **virtual environment** (`.venv`) is a private, throwaway copy of Python and
its libraries that belongs to *this project only*:

```bash
python -m venv .venv          # create it (once)
source .venv/bin/activate     # "enter" it (each new terminal)
```

After `activate`, your prompt usually shows `(.venv)`. Now `pip install` puts
libraries *inside* `.venv`, isolated from the rest of your system. Delete the
folder and it's like it never happened. **You must `activate` it in every new
terminal window** — that trips up every beginner at least once. (When you saw
`source .venv/bin/activate` before each command in this project, that's why.)

## 2.4 `pyproject.toml` — the project's ID card

This file declares two things: *what this project is* and *what it depends on*.
Our dependency list (trimmed) looks like:

```toml
dependencies = [
    "fastapi",              # the web framework
    "uvicorn[standard]",    # the server that runs FastAPI
    "sqlmodel",             # defines DB tables as Python classes
    "sqlalchemy[asyncio]",  # the engine SQLModel uses to talk to Postgres
    "asyncpg",              # the actual Postgres driver (async)
    "alembic",              # database migrations
    "pydantic-settings",    # loads config from the environment
    "pyjwt[crypto]",        # verifies login tokens (the [crypto] matters! Ch.5)
    "python-dotenv",        # reads the .env file
]
```

Why pin these in a file instead of just `pip install`-ing as you go? **Repro­
ducibility.** Six months from now, or on a teammate's machine, or inside a
Docker image, someone runs one command and gets the *exact same* environment.
A project that only works because of libraries you installed by hand and forgot
about is a project that breaks the moment it leaves your laptop. (We learned a
version of this lesson the hard way in Chapter 5 with `pyjwt[crypto]`.)

## 2.5 Configuration and the "12-Factor" rule

Here's a rule professional systems live by, from a famous document called *The
Twelve-Factor App*:

> **Store config in the environment, never in code.**

"Config" means anything that changes between your laptop and production: the
database address, API keys, the frontend's URL. These must *never* be hardcoded,
for two reasons:

1. **Security.** A database password committed to Git is a password leaked to
   anyone who ever sees the repo. This is one of the most common ways real
   companies get breached.
2. **Portability.** The same code image should run on your laptop (talking to a
   dev database) and in the cloud (talking to the real one) — differing *only*
   by the environment it's handed. No code changes between environments.

We implement this with two files:

- **`.env`** — your real values. **Git-ignored.** Never committed.
  ```
  SUPABASE_URL=https://yourproject.supabase.co
  DATABASE_URL=postgresql+asyncpg://...
  ```
- **`.env.example`** — the same *keys* with fake values, *committed* to Git as
  documentation. It tells the next person (or future you) "here are the
  variables you need to fill in," without leaking any secret.

And the code that reads them, in `app/core/config.py`:

```python
from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    ENVIRONMENT: str = "development"
    SUPABASE_URL: str = ""
    DATABASE_URL: str = "postgresql+asyncpg://postgres:postgres@localhost:5432/postgres"
    # ... etc

settings = Settings()   # reads .env once, on startup
```

`BaseSettings` is a small piece of magic from `pydantic-settings`: it
automatically matches each class attribute to an environment variable of the
same name, reading from `.env` (or the real OS environment in production). The
defaults (like `"development"`) are fallbacks for when a variable isn't set.

Everywhere else in the app, we just `from app.core.config import settings` and
read `settings.DATABASE_URL`. One source of truth, loaded once. If you ever
wonder "where does this value come from?", the answer is always: an environment
variable, surfaced through this one `Settings` object.

---

**Next:** [Chapter 3 — Database Design](03-database-design.md). We now have an
empty, well-organized project. Time to give it a memory.

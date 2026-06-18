# Chapter 3 — Database Design

A web app without a database is a goldfish: it forgets everything the instant it
restarts. This chapter gives StartupIQ a memory — and teaches you how to design
one that stays fast and correct as it grows.

## 3.1 Why a *relational* database (Postgres)

Our data has *relationships*: a user *has many* ideas; an idea *has many*
evaluations; an evaluation *has many* results. When data is full of "has many"
and "belongs to" relationships, a **relational database** is the right tool. It
stores data in **tables** (like spreadsheets) and lets you connect them.

We use **PostgreSQL** ("Postgres") — the most respected open-source relational
database. It's rock-solid, free, and used by companies at massive scale.

## 3.2 Why Supabase

**Supabase** is a hosted Postgres database with batteries included. We could run
raw Postgres ourselves, but Supabase hands us, for free:

- A real Postgres database in the cloud (no install).
- **Supabase Auth** — a complete login/signup system (huge — see Chapter 5).
- A web dashboard to browse our tables (the "Table Editor").

The key thing to understand: **Supabase *is* Postgres.** Anything you learn here
about Postgres applies directly. Supabase just wraps it in conveniences.

## 3.3 Tables as Python classes: SQLModel

We *could* write raw SQL like `CREATE TABLE startup_ideas (...)`. Instead we
describe each table as a Python class using **SQLModel**, and let it generate
the SQL. A tool that maps between database rows and program objects like this is
called an **ORM** (Object-Relational Mapper).

Here's our entire `startup_ideas` table, from
`backend/app/db/models/idea.py`:

```python
from datetime import datetime
from uuid import UUID, uuid4
from sqlmodel import Field, SQLModel

class StartupIdea(SQLModel, table=True):
    __tablename__ = "startup_ideas"

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    user_id: UUID = Field(foreign_key="profiles.id", index=True)
    title: str
    description: str
    industry: str | None = Field(default=None)
    target_market: str | None = Field(default=None)
    status: str = Field(default="active", index=True)
    created_at: datetime = Field(default_factory=datetime.utcnow, index=True)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
```

Read it line by line, because nearly every word teaches a database concept:

- **`table=True`** — "this class is a real database table," not just a plain
  Python object. (Later we'll see SQLModel/Pydantic classes *without* this, used
  only for shaping JSON.)
- **`id: UUID ... primary_key=True`** — every table needs a **primary key**: a
  column whose value uniquely identifies a row. We use a **UUID** (a random
  128-bit id like `da272dcd-1b4d-...`) instead of a simple counter (1, 2, 3…).
  Why? UUIDs don't leak information (a competitor can't tell how many ideas
  exist by watching the numbers climb) and they can be generated anywhere
  without coordinating with the database. `default_factory=uuid4` means "if no
  id is given, generate a random one."
- **`user_id: UUID = Field(foreign_key="profiles.id")`** — this is the heart of
  "relational." A **foreign key** says "this column must point to a real `id` in
  the `profiles` table." It's how we link an idea to its owner. The database
  itself *enforces* this: you physically cannot create an idea pointing to a
  non-existent user. That guarantee is called **referential integrity**.
- **`index=True`** (on `user_id`, `status`, `created_at`) — this is the single
  most important performance concept in this chapter. See §3.5.
- **`str | None`** — the `| None` means the column is optional (can be empty /
  `NULL`). `industry` and `target_market` are nice-to-haves; `title` and
  `description` are required.
- **`status: str = Field(default="active")`** — new ideas default to "active."
  Recall (Chapter 1) that we never truly delete ideas; we set `status` to
  `"archived"`. This is a **soft delete**.
- **`created_at` / `updated_at`** — timestamps. Nearly every table in a real
  system has these; you'll be grateful for them when debugging "when did this
  happen?"

## 3.4 The `profiles` table and a subtle Supabase pattern

Supabase Auth manages its *own* hidden table of users, called `auth.users`. We
are told **not** to attach our foreign keys directly to it (it's Supabase's
internal table and can change). The standard pattern is to keep our *own*
`profiles` table that mirrors it 1-to-1:

```python
class Profile(SQLModel, table=True):
    """Mirrors auth.users (1:1), populated via a Postgres trigger on signup."""
    __tablename__ = "profiles"

    id: UUID = Field(primary_key=True)        # SAME id as auth.users
    email: str = Field(index=True)
    display_name: str | None = Field(default=None)
    created_at: datetime = Field(default_factory=datetime.utcnow)
```

So the chain is: `auth.users` (Supabase's) → `profiles` (ours, same `id`) →
`startup_ideas.user_id` points at `profiles.id`. Our app only ever deals with
`profiles`; Supabase Auth deals with `auth.users`; they share the same id.

But who *creates* the `profiles` row when someone signs up? We don't want to
remember to do it by hand. Enter triggers.

## 3.5 The performance lesson: indexes

Imagine `startup_ideas` has 50,000 rows and you run "give me all ideas where
`user_id = X`." Without help, Postgres reads *all 50,000 rows* and checks each
one — a "full table scan." Slow, and it gets slower as data grows.

An **index** is a pre-sorted lookup structure (think of the index at the back of
a book: instead of reading every page to find "Redis," you jump straight to it).
With `index=True` on `user_id`, Postgres keeps a sorted map of user_id → rows,
and answers that query almost instantly no matter how big the table gets.

We indexed exactly the columns we'll *filter or sort by*:

- `user_id` — because every query is "ideas belonging to **this user**."
- `status` — because we'll filter out archived ideas.
- `created_at` — because we show ideas **newest first** (sorting uses indexes too).

**The trade-off:** indexes make reads fast but writes slightly slower (every
insert must also update the index) and use disk space. So you don't index
*everything* — you index what you query. Knowing *which* columns to index is a
core database-design skill, and we'll feel its impact for real in Phase 8 when
we load 10,000 rows and measure.

## 3.6 Triggers: making the database do work automatically

A **trigger** is a small function the database runs *automatically* when
something happens. We use one to solve the "who creates the profile?" question:
whenever Supabase inserts a row into `auth.users`, a trigger fires and inserts
the matching `profiles` row for us. The user signs up once, and a profile
appears as if by magic — because the database guarantees it, not our app code.

The SQL (added via a migration, see §3.8) is:

```sql
create function public.handle_new_user() returns trigger as $$
begin
  insert into public.profiles (id, email) values (new.id, new.email);
  return new;
end;
$$ language plpgsql security definer;

create trigger on_auth_user_created
  after insert on auth.users
  for each row execute procedure public.handle_new_user();
```

This is your first taste of pushing logic *into* the database. The advantage:
it's **guaranteed**. No matter how a user gets created — our app, the Supabase
dashboard, an admin script — a profile always follows. Correctness enforced at
the lowest level beats correctness you have to remember.

## 3.7 Connecting to the database: the engine and sessions

`backend/app/db/session.py` sets up how our app *talks* to Postgres:

```python
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from app.core.config import settings

engine = create_async_engine(settings.DATABASE_URL, echo=False, future=True)

async_session_maker = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

async def get_session():
    async with async_session_maker() as session:
        yield session
```

Three ideas here:

- **The engine** is the long-lived object that manages the actual connection(s)
  to Postgres. You create it *once* for the whole app.
- **A session** is a short-lived workspace for *one unit of work* (typically one
  HTTP request). You add/query/commit through it, then it's thrown away.
  `get_session()` hands out a fresh session and cleanly closes it after — and
  it's wired into endpoints via FastAPI's dependency injection (Chapter 4).
- **`async`** — everything is asynchronous. When the app is waiting on Postgres
  to respond, `async` lets it go serve *other* requests in the meantime instead
  of freezing. This is a big part of how a single server handles many users at
  once. (Async is subtle; for now just absorb: "async = don't sit idle while
  waiting.")

### A real-world wrinkle: two connection strings

You may have noticed we configured `DATABASE_URL` **and** `DATABASE_URL_DIRECT`.
This is a genuine production concern. Supabase offers two ways to connect:

- A **pooler** connection (port 6543) — efficient for an app making many short
  requests. The running app uses this (`DATABASE_URL`).
- A **direct** connection (port 5432) — needed for schema changes. Migrations
  use this (`DATABASE_URL_DIRECT`).

(A "pooler" reuses a small set of database connections across many requests so
you don't exhaust the database — important at 10,000-user scale. You don't need
the details yet; just know *why* there are two.)

## 3.8 Migrations: version control for your database schema

Your set of tables and columns — the **schema** — will change constantly as the
product grows (new tables in Phase 2, 3, 7…). How do you evolve a live database
safely, and keep every environment (your laptop, a teammate's, production) in
sync? You **don't** edit tables by hand. You write **migrations**.

A migration is a small, ordered script describing one change ("create these
tables," "add this column," "add this trigger"). They're numbered and run in
order — like Git commits, but for database structure. We use **Alembic** (the
standard migration tool for SQLAlchemy/SQLModel). Our two migrations so far:

```
backend/alembic/versions/
├── 0001_create_profiles_and_startup_ideas.py   ← makes the two tables
└── 0002_add_profile_creation_trigger.py        ← adds the signup trigger
```

You apply them all with one command:

```bash
alembic upgrade head     # "bring the database up to the latest migration"
```

`head` means "the newest." Alembic records which migrations a database has
already run, so this command only applies new ones — run it on a fresh database
and it creates everything; run it on an up-to-date one and it does nothing.

**Why this matters so much:** in six months you'll add a `tags` table. You'll
write migration `0008`, run `alembic upgrade head`, and your database evolves
*reproducibly* — and so does production, with the same command, the same result.
No "works on my machine," no hand-typed `ALTER TABLE` you forgot to also run in
production. The schema becomes code you can review, version, and trust.

One Alembic detail worth seeing — `backend/alembic/env.py` deliberately uses the
*direct* connection for migrations (§3.7) and imports our models so Alembic can
compare them against the live database:

```python
import app.db.models                      # register all tables on the metadata
target_metadata = SQLModel.metadata
config.set_main_option("sqlalchemy.url", settings.DATABASE_URL_DIRECT)  # direct, not pooler
```

---

**Recap.** We have two tables (`profiles`, `startup_ideas`), linked by a foreign
key, indexed on the columns we query, kept in sync with Supabase Auth by a
trigger, connected through an async engine, and evolved safely through Alembic
migrations. The app now has a memory.

**Next:** [Chapter 4 — API Design](04-api-design.md). We have data; now we build
the doors through which the outside world reads and writes it.

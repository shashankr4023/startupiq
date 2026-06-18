# Chapter 10 — Docker: The Whole Stack in One Command

Right now, running StartupIQ means juggling **four terminals**: Redis, the API,
the worker, and the frontend — each needing the right directory, the right
virtualenv, the right command, started in the right order. That's fine on your
laptop today. But it's fragile ("which terminal died?"), unteachable ("just run
these four things, in this order, with these env files…"), and it won't survive
the move to a server or the cloud.

This phase fixes all of that. After it, the entire stack — all five pieces —
starts with a **single command**:

```bash
docker compose up --build
```

…and the whole app is at `http://localhost`. This is the **containerization**
lesson, and it's the gateway to everything in Phases 9–10 (Kubernetes, cloud).

## 10.1 The problem containers solve

You've felt this already in this very project: "works on my machine." We hit a
missing `cryptography` library (Chapter 5), needed a specific Redis running
(Chapter 7), a specific Node version, the right Python, env files in the right
places. Every one of those is an *environment* assumption. Move to a fresh
machine and any of them can break.

A **container** packages an application *together with its entire environment* —
the OS libraries, the language runtime, the dependencies, the code — into one
sealed, runnable unit. If it runs in the container on your laptop, it runs
*identically* in the container on a server, because the container *is* the
environment. No more "works on my machine"; the machine comes with it.

**Docker** is the tool that builds and runs containers. Two core concepts:

- An **image** is the sealed, read-only template — "Python 3.11 + our deps + our
  code." You build it once.
- A **container** is a running instance of an image. You can start many
  containers from one image (which is exactly how we'll scale in Phase 9).

> Mental model: an image is a *class*, a container is an *object* (an instance).
> Or: an image is a cooking recipe; a container is the meal you cook from it.

## 10.2 A Dockerfile: the recipe for an image

A **Dockerfile** is a script of steps that builds an image. Here's our backend's,
`backend/Dockerfile`, annotated:

```dockerfile
FROM python:3.11-slim          # 1. start from a minimal Python 3.11 OS image
ENV PYTHONUNBUFFERED=1         # 2. make container logs live, not buffered
WORKDIR /app                   # 3. work inside /app from here on

COPY pyproject.toml ./         # 4. copy the dependency manifest...
COPY app ./app                 #    ...and our code...
RUN pip install --no-cache-dir .   # 5. install our package + all its deps

COPY alembic ./alembic         # 6. copy migration files
COPY alembic.ini ./

EXPOSE 8000                    # 7. document that the app listens on 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--proxy-headers"]  # 8. default command
```

Read it as a sequence of instructions to a fresh machine: start from Python, copy
our stuff in, install it, and here's how to run it. Each line is a **layer** —
Docker caches layers, so if only your code changes (not `pyproject.toml`), it
reuses the cached base and dependency layers and rebuilds fast.

Two details worth calling out:

- **`--host 0.0.0.0`** — inside a container, `localhost` means "only this
  container." Binding to `0.0.0.0` ("all interfaces") is what lets *other*
  containers (nginx) reach the API. This trips up everyone once.
- **`--proxy-headers`** — tells uvicorn to trust the `X-Forwarded-*` headers that
  nginx sets, so the app sees the real client info through the proxy.

### One image, two roles

Notice the API and the **worker** are the same program with the same
dependencies — they differ only in the command (`uvicorn …` vs `arq …`). So they
share **one image**. The worker doesn't get its own Dockerfile; in the compose
file it just *overrides the command*. Build once, run two ways. (We'll see that in
§10.4.)

## 10.3 Multi-stage builds: a small frontend image

The frontend Dockerfile (`frontend/Dockerfile`) shows a more advanced, very
common pattern: a **multi-stage build**. The problem it solves: *building* a
Next.js app needs the whole toolchain (all of `node_modules`, the compiler), but
*running* it needs almost none of that. We don't want to ship the heavy build
tools in the final image.

So there are two stages:

```dockerfile
# Stage 1: "builder" - has everything, runs the build
FROM node:20-alpine AS builder
WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci                     # install ALL dependencies
COPY . .
RUN npm run build              # produces a slim "standalone" bundle

# Stage 2: "runner" - starts fresh, copies ONLY the built output
FROM node:20-alpine AS runner
WORKDIR /app
ENV NODE_ENV=production HOSTNAME=0.0.0.0 PORT=3000
COPY --from=builder /app/.next/standalone ./   # ← just the result
COPY --from=builder /app/.next/static ./.next/static
COPY --from=builder /app/public ./public
CMD ["node", "server.js"]
```

The final image contains only stage 2's contents — the compiled app and a minimal
server — not the build tools. (We enabled Next's `output: "standalone"` in
`next.config.mjs` precisely so it traces and bundles only the dependencies the
running server actually needs.) Smaller images build faster, deploy faster, and
have a smaller attack surface. The `HOSTNAME=0.0.0.0` is the same "bind to all
interfaces" lesson as the backend, in Node form.

### The build-time vs runtime env trap (important)

Here's a subtle thing that bites people. Recall (Chapter 9) that `NEXT_PUBLIC_*`
variables are **baked into the browser bundle at build time** — they're compiled
*into* the JavaScript. That means the frontend image's Supabase URL and API base
must be known *when `npm run build` runs*, not when the container starts. So the
Dockerfile takes them as **build arguments** (`ARG`), and compose passes them in
at build time:

```dockerfile
ARG NEXT_PUBLIC_SUPABASE_URL
ENV NEXT_PUBLIC_SUPABASE_URL=$NEXT_PUBLIC_SUPABASE_URL
RUN npm run build
```

Contrast with the *backend*, whose config is read at **runtime** (every time the
container starts, from environment variables). This split — frontend config baked
at build, backend config injected at run — is a genuinely important distinction,
and getting it wrong is a classic "why is my deployed frontend calling localhost?"
bug.

## 10.4 docker compose: orchestrating five containers

One image is one container. But StartupIQ is *five* programs that must run
together and talk to each other. **Docker Compose** describes a multi-container
app in one YAML file and runs them as a unit. Here's the shape of
`docker/docker-compose.yml`:

```yaml
services:
  redis:                         # the queue + cache + rate-limit store
    image: redis:7-alpine
    volumes: [redis-data:/data]

  api:                           # FastAPI
    build: { context: ../backend, dockerfile: Dockerfile }
    image: startupiq-backend:latest
    env_file: ../backend/.env    # reuse all our existing config
    environment:
      REDIS_URL: redis://redis:6379    # ← note the hostname: "redis"
      FRONTEND_ORIGIN: http://localhost
    depends_on: [redis]

  worker:                        # SAME image, different command
    build: { context: ../backend, dockerfile: Dockerfile }
    image: startupiq-backend:latest
    command: ["arq", "app.worker.settings.WorkerSettings"]
    env_file: ../backend/.env
    environment: { REDIS_URL: redis://redis:6379 }
    depends_on: [redis]

  frontend:                      # Next.js
    build:
      context: ../frontend
      args: { NEXT_PUBLIC_SUPABASE_URL: ${...}, ... }   # build-time env
    depends_on: [api]

  nginx:                         # the single front door
    image: nginx:alpine
    ports: ["80:80"]             # the ONLY port exposed to your host
    volumes: ["./nginx/nginx.conf:/etc/nginx/nginx.conf:ro"]
    depends_on: [api, frontend]

volumes:
  redis-data:
```

Several big ideas are packed in here:

**Service names are hostnames.** This is the magic that makes containers talk.
Compose puts all services on a private network where each is reachable by its
*service name*. That's why the API's `REDIS_URL` is `redis://redis:6379` — `redis`
is literally the hostname of the Redis container. Likewise nginx reaches the API
at `api:8000`. No IP addresses, no fragile wiring — just names. (This is also why
we *override* `REDIS_URL` here: the value in our `.env` says
`redis://localhost:6379`, which would be wrong inside a container — `localhost`
there means the container itself. Compose's `environment:` wins over `env_file:`.)

**`depends_on` orders startup.** Redis comes up before the API; the API before
nginx. (It only waits for *start*, not full readiness — production setups add
health checks, a fine later refinement.)

**Volumes persist data.** Containers are ephemeral — delete one and its internal
files vanish. A named **volume** (`redis-data`) is storage that lives *outside*
the container's lifecycle, so Redis's data survives a restart. (Our real data
lives in Supabase anyway, but it's the right habit.)

**Reusing `.env`.** The backend services load our existing `backend/.env` via
`env_file` — so all the Supabase/OpenAI/Claude config we already set up just
works, no duplication. (Secrets are injected at runtime, never baked into the
image — note the `.dockerignore` excludes `.env`.)

## 10.5 The reverse proxy: one front door, no CORS

Look at the ports. Only **nginx** publishes a port to your host (`80:80`).
Everything else — the API, the frontend, Redis — is reachable only *inside* the
compose network. The outside world goes through nginx, which routes by URL
(`docker/nginx/nginx.conf`):

```nginx
location /api/ { proxy_pass http://api:8000; }      # API calls
location /     { proxy_pass http://frontend:3000; } # everything else
```

This is a **reverse proxy**: a single entry point that forwards requests to the
right internal service based on the path. The payoff is bigger than tidiness —
it makes the whole app a **single origin** (`http://localhost`). The browser loads
the page from `http://localhost` and calls the API at `http://localhost/api/...`
— *same origin*. Remember the CORS middleware we carefully configured back in
Chapter 4 to let `localhost:3000` call `localhost:8000`? With a reverse proxy,
there's no cross-origin call at all, so CORS simply doesn't enter the picture.
(This is also the pattern you'll use in production, where nginx would additionally
terminate HTTPS.)

```
Browser ──http://localhost──▶ nginx ──/api/*──▶ api:8000  (FastAPI)
                                  └───/*──────▶ frontend:3000  (Next.js)
                                              api/worker ──▶ redis:6379
```

## 10.6 Running it

**1. Install Docker Desktop** (one-time): download from docker.com, install, and
launch it. Confirm it's running:
```bash
docker --version
docker compose version
```

**2. Make sure config is in place** (already done in this repo):
- `backend/.env` — your real backend config (Supabase, OpenAI/Claude keys).
- `docker/.env` — the `NEXT_PUBLIC_*` values for the frontend build (copied from
  `docker/.env.example`).

**3. Bring up the whole stack** from the `docker/` folder:
```bash
cd docker
docker compose up --build
```
The first run takes a few minutes (downloading base images, installing deps,
building the frontend). You'll see logs from all five services interleaved,
prefixed with the service name. When it settles, open **http://localhost** —
the full app, login and all, running entirely in containers.

**4. Stop it:** `Ctrl+C`, then `docker compose down` (add `-v` to also wipe the
Redis volume).

A few useful commands as you explore:
```bash
docker compose ps                 # what's running
docker compose logs -f worker     # follow one service's logs
docker compose up --build -d      # run detached (in the background)
docker compose down               # stop and remove the containers
```

> **Migrations:** your Supabase database was already migrated in earlier phases,
> so there's nothing to run. On a *fresh* database you'd apply them from inside a
> container once: `docker compose run --rm api alembic upgrade head`.
>
> **The 4-terminal workflow still works.** Nothing here changed how you run things
> locally with `uvicorn`/`arq`/`npm`. Docker is an *additional*, all-in-one way to
> run the same code — useful for a clean full-stack run and essential for Phases
> 9–10.

---

**Recap.** We packaged every piece of StartupIQ into containers. A **Dockerfile**
builds each image (the backend's doubles as the worker; the frontend uses a
**multi-stage build** for a slim result). **docker compose** runs all five
services as a unit, wired together by *service-name hostnames*, with Redis data on
a **volume** and config reused from our `.env`. An **nginx reverse proxy** is the
single front door, collapsing the app to one origin and erasing CORS. The whole
stack now starts with `docker compose up` — reproducibly, on any machine with
Docker.

**This completes Part 6.** StartupIQ is now portable. **Part 7 (Phase 7)** adds
**webhooks**: when an evaluation finishes, the system will POST a signed event to
a URL the user registers — teaching event-driven design, HMAC signatures, and
retry/reliability patterns. After that, Phases 8–10 push this containerized stack
toward real scale (load testing, Kubernetes, the cloud).

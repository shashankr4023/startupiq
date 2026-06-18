# Deploying StartupIQ to the Cloud

This guide covers shipping StartupIQ to the real internet. The CI/CD pipeline
(`.github/workflows/ci.yml`) already **tests, builds, and publishes** images on
every push to `main`. This doc is about the last mile: running those images on a
cloud host with production config.

## The mental model: dev → CI → CD

```
You push code ──▶  CI: lint/test/build  ──▶  CD: publish images  ──▶  Deploy to cloud
  (git push)        (GitHub Actions)          (ghcr.io registry)       (you run / automate)
```

- **CI (Continuous Integration):** every push runs the tests and builds the
  frontend, so broken code is caught immediately — not discovered in production.
- **CD (Continuous Delivery):** every push to `main` builds the Docker images and
  pushes them to **GitHub Container Registry** (`ghcr.io/<you>/startupiq-backend`,
  `…-frontend`). These are the exact, versioned artifacts you deploy.

The *deploy* step (pulling those images onto a server) can be manual at first, and
automated later. Both paths below pull the **published images** — they don't build
on the server.

## What's already production-ready

Because we followed the **12-factor app** principles throughout, very little
changes for production:

| 12-factor principle | How StartupIQ already does it |
|---|---|
| **Config in the environment** | Every setting is an env var (`backend/app/core/config.py`); nothing secret is in code. |
| **Backing services as attached resources** | Postgres (Supabase), Redis, and the LLM API are all reached via URLs/keys from env — swappable without code changes. |
| **Stateless processes** | The API and worker keep no local state; all of it is in Postgres/Redis. So you can run many copies (Phase 9). |
| **Build, release, run separated** | CI builds an immutable image; you release it by deploying with production config. |
| **Disposability** | Containers start fast and stop cleanly; k8s/Compose restart them freely. |
| **Logs to stdout** | Containers log to stdout (`PYTHONUNBUFFERED=1`), so the platform collects them. |

The main *additions* for production are: a **managed Redis**, **real secrets** in
the platform, a **domain + HTTPS**, and pulling images from the **registry**.

## Backing services for production

- **Database + Auth → Supabase.** Already cloud-hosted. Nothing to do — the same
  `DATABASE_URL`/`SUPABASE_*` you use locally work in production. (For real scale,
  move off the free tier.)
- **Redis → a managed Redis.** Locally we ran Redis ourselves. In production, use a
  managed service (e.g. **Upstash**, AWS **ElastiCache**, or your cloud's Redis) so
  it's durable and externalized. You just set `REDIS_URL` to the managed endpoint —
  no code change. (This is why Redis was always reached via `REDIS_URL`.)
- **LLM → Claude in production.** Flip `LLM_PROVIDER=claude` and set
  `ANTHROPIC_API_KEY` (the whole point of the provider abstraction from Chapter 6).

## Secrets: never in git, always in the platform

`backend/.env`, `docker/.env`, and `frontend/.env.local` are **git-ignored** and
must never be committed. In production, secrets live in the platform's secret store:

- **GitHub Actions** (for the image build): repo → Settings → Secrets and variables
  → Actions → add `NEXT_PUBLIC_SUPABASE_URL`, `NEXT_PUBLIC_SUPABASE_ANON_KEY`,
  `NEXT_PUBLIC_API_BASE_URL` (used by the frontend image build).
- **Kubernetes** (Path A): a `Secret` (as in Phase 9), populated from the managed
  values — not from a committed file.
- **A VM** (Path B): an `.env` file present only on the server (never in git), or
  the host's secret manager.

---

## Path A — Managed Kubernetes (the scalable way)

Use a managed cluster: **GKE** (Google), **EKS** (AWS), **AKS** (Azure), or the
simpler **DigitalOcean Kubernetes**. Reuse the Phase 9 manifests in `infra/k8s/`
with three changes:

1. **Images from the registry.** Change each `image:` from
   `startupiq-backend:latest` to `ghcr.io/<you>/startupiq-backend:latest` (and the
   frontend likewise), and drop `imagePullPolicy: IfNotPresent`. Add an image-pull
   secret if your GHCR packages are private.
2. **Externalize Redis.** Delete `02-redis.yaml` and point `REDIS_URL` (in the
   Secret) at your managed Redis endpoint. (Running Redis in-cluster is fine for a
   demo, but managed is the production choice.)
3. **Domain + HTTPS.** Put a real hostname on the Ingress and add TLS — typically
   with **cert-manager** issuing Let's Encrypt certificates automatically. Your
   cloud's ingress/load-balancer gets a public IP; point your domain's DNS at it.

Then it's the same flow as Phase 9: `kubectl apply -f infra/k8s/…`, scale with
`kubectl scale`, autoscale with the HPA. You can even add a final CD job that runs
`kubectl set image deployment/api …` to roll out the new image automatically after
publish.

## Path B — A single cloud VM (the simple, cheap way)

For a solo project, one small VM (a ~$5–10/month droplet/instance) running Docker
Compose is plenty:

1. Provision an Ubuntu VM; install Docker + the Compose plugin.
2. Copy the repo (or just `docker/`) to the server. Create `backend/.env` and
   `docker/.env` **on the server** with production values (managed `REDIS_URL`,
   `LLM_PROVIDER=claude`, real keys) — never committed.
3. Either build on the VM (`docker compose -f docker/docker-compose.yml up -d
   --build`) or pull the CI-published images. The nginx service already fronts
   everything on port 80.
4. **Domain + HTTPS:** point your domain at the VM's IP, and add TLS — easiest is
   to put **Caddy** in front (automatic HTTPS) or add a certbot/Let's Encrypt step
   to the nginx config.
5. Set restart policies (`restart: unless-stopped`, already in the compose file) so
   it survives reboots.

This gives you the full app at `https://yourdomain.com` on one box. When you
outgrow it, Path A is waiting — same images, same Supabase, same Redis-via-URL.

---

## A realistic first deploy

If you want to *actually* put this online with the least friction:

1. Push to GitHub (CI goes green, images publish to GHCR).
2. Take the **Path B** VM route with a managed Upstash Redis (free tier) and
   `LLM_PROVIDER=claude`.
3. Front it with Caddy for automatic HTTPS on your domain.

That's a real, production-shaped deployment of everything you built — for a few
dollars a month — without the operational weight of a managed Kubernetes cluster.

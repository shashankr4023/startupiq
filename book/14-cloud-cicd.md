# Chapter 14 — Shipping It: CI/CD and the Cloud

We've built a complete, scalable, orchestrated system — but it only runs on *your*
machine. The final phase closes the loop: an automated pipeline that **tests,
builds, and publishes** the app on every code change, and a clear path to running
it on the public internet. This is how software actually reaches users.

## 14.1 The problem: from "works on my laptop" to "running for the world"

Every time you changed code in this project, *you* manually ran the tests, *you*
rebuilt the Docker images, *you* restarted things. That's fine for one developer
on one machine. But it doesn't scale to a real project, because it's:

- **Error-prone** — forget to run the tests and you ship a bug.
- **Inconsistent** — "it built on my machine" isn't proof it builds anywhere.
- **Manual** — every deploy is a chore someone has to remember to do correctly.

The answer is **CI/CD**: a robot that does all of this for you, the same way, every
time, automatically.

- **CI — Continuous Integration:** every time you push code, automatically run the
  tests and build everything. Catch breakage *immediately*, before it spreads.
- **CD — Continuous Delivery:** every time `main` changes, automatically build the
  deployable artifacts (our Docker images) and publish them, ready to deploy.

## 14.2 The pipeline: `.github/workflows/ci.yml`

We use **GitHub Actions** — GitHub's built-in automation. You describe a
*workflow* in YAML; GitHub runs it on its own servers whenever the trigger fires.
No CI server to maintain. Ours has three **jobs**:

```yaml
on:
  push: { branches: [main] }
  pull_request:

jobs:
  backend-tests:   # run pytest
  frontend-build:  # run npm run build
  publish-images:  # build + push Docker images to the registry (main only)
```

The trigger (`on:`) says: run on every pull request *and* every push to `main`.
That means **no broken code can merge unnoticed** — the tests run on the PR first.

### Job 1 — backend tests

```yaml
backend-tests:
  steps:
    - uses: actions/checkout@v4              # grab the code
    - uses: actions/setup-python@v5          # install Python 3.11
    - run: pip install -e ".[dev]"           # install the app + test deps
      working-directory: backend
    - run: pytest -q                          # run all 20 tests
      working-directory: backend
```

This is the payoff for a habit we kept all book long: **our tests are fully
hermetic.** They use in-memory SQLite, and fakes for Redis, the LLM, and auth
(Chapters 6–11). So they run on a bare GitHub server with **no secrets, no
database, no Redis** — and pass in a fraction of a second. A test suite that needs
real infrastructure can't run in CI; ours can, because we designed every external
dependency to be swappable. That design choice, made for testability, is exactly
what makes automated CI possible.

### Job 2 — frontend build

```yaml
frontend-build:
  steps:
    - uses: actions/setup-node@v4
    - run: npm ci          # install exactly the locked deps
    - run: npm run build   # compile the Next.js app
      env:
        NEXT_PUBLIC_SUPABASE_URL: https://example.supabase.co  # dummy - just compiling
        ...
```

This proves the frontend *compiles* (TypeScript types check, the build succeeds).
We feed it dummy `NEXT_PUBLIC_*` values because we're only checking that it builds,
not connecting to anything. (Recall from Chapter 10 that these are baked in at
build time — so even a compile check needs them present.)

### Job 3 — publish images (the CD part)

```yaml
publish-images:
  needs: [backend-tests, frontend-build]     # only if both passed
  if: github.ref == 'refs/heads/main'        # only on main, not PRs
  permissions: { packages: write }
  steps:
    - uses: docker/login-action@v3           # log in to the registry
      with: { registry: ghcr.io, username: ${{ github.actor }}, password: ${{ secrets.GITHUB_TOKEN }} }
    - uses: docker/build-push-action@v6      # build + push backend image
      with: { context: ./backend, push: true, tags: ghcr.io/${{ github.repository_owner }}/startupiq-backend:latest }
    - uses: docker/build-push-action@v6      # build + push frontend image
      with: { context: ./frontend, push: true, build-args: ... }
```

Two important guards: `needs:` means this only runs **after the tests and build
pass** (you never publish broken code), and `if:` means it only runs on **`main`**
(pull requests get tested but don't publish). When it runs, it builds the same
Docker images from Chapter 10 and pushes them to **GitHub Container Registry**
(`ghcr.io`) — a place to store and version your built images. Those published
images are the **deployable artifacts**: the exact, tested thing you ship to the
cloud.

> **Registry = the bridge between build and deploy.** CI builds an image and pushes
> it to the registry; the cloud pulls it from the registry and runs it. The image
> is built *once* and runs identically everywhere — the core promise of containers
> (Chapter 10), now realized across machines.

## 14.3 Secrets in CI

The pipeline needs some secrets (the real `NEXT_PUBLIC_*` values for the published
frontend image). These never go in the YAML or the repo — they live in **GitHub's
encrypted secret store** (repo → Settings → Secrets and variables → Actions) and
are referenced as `${{ secrets.NAME }}`. This is Chapter 2's "config in the
environment" principle, extended to the build pipeline. (And `GITHUB_TOKEN` for
the registry login is provided automatically by GitHub — you don't set it.)

## 14.4 The last mile: running it in the cloud

CI/CD gets you *tested, published images*. The final step is running them on a
public server. The full guide is in `docs/deployment.md`; the shape of it:

**Almost nothing changes**, because we built for this all along. The 12-factor
principles (Chapter 2 and beyond) mean production differs from local only in
*configuration*, not code:

- **Database + Auth:** Supabase is already cloud — no change.
- **Redis:** swap your local Redis for a **managed Redis** (e.g. Upstash) by
  changing one env var, `REDIS_URL`. (This is why Redis was *always* reached via a
  URL, never hardcoded.)
- **LLM:** set `LLM_PROVIDER=claude` + `ANTHROPIC_API_KEY` — the provider
  abstraction from Chapter 6 makes this a config flip, not a code change.
- **Secrets:** in the platform's secret store, never in git.
- **Domain + HTTPS:** point a domain at the server and add TLS.

Two deployment routes:

- **Path A — Managed Kubernetes** (GKE/EKS/AKS/DigitalOcean): reuse the Phase 9
  manifests, but with `image: ghcr.io/...` (from the registry), external managed
  Redis, and a real domain + TLS. Everything you practiced in Chapter 13 applies —
  scaling, the HPA, the rate limiter holding across replicas — now on real
  hardware.
- **Path B — A single small VM** running Docker Compose (Chapter 10's setup with
  production env + HTTPS). Cheaper and simpler; perfect for a solo project. When you
  outgrow it, Path A is waiting with the same images.

That's the whole journey of a code change: **you push → CI tests it → CD publishes
an image → the cloud runs it → a user opens the app.** Fully automated from your
`git push` to a tested artifact, with one deliberate human (or automated) step to
release it.

## 14.5 Putting StartupIQ on GitHub

To turn the pipeline on, the project needs to be on GitHub:

```bash
cd /Users/shashank/Workspace/Startup-Idea-Evaluator
git init
git add -A
git status            # ← verify NO .env files are staged (the .gitignore guards this)
git commit -m "StartupIQ: full-stack AI idea evaluator"
# create an empty repo on github.com, then:
git remote add origin https://github.com/<you>/startupiq.git
git branch -M main
git push -u origin main
```

The moment you push, the **Actions** tab on GitHub shows the pipeline running —
tests, build, and (on `main`) image publish — all green, automatically. You've
just set up the same CI/CD that professional teams rely on.

> ⚠️ **Before you push:** confirm `git status` shows no `.env` files (they hold
> real keys). The root `.gitignore` excludes them, but check. If a key was ever
> exposed, rotate it in the provider's dashboard.

---

**Recap.** We automated the path from code to artifact with a **GitHub Actions
CI/CD pipeline**: every push runs the **hermetic test suite** and builds the
frontend; every push to `main` builds and **publishes the Docker images** to a
registry. We saw why our long-held habits — env-based config, swappable backing
services, fakeable dependencies, stateless processes — make the app **deploy-ready
with almost no changes**: production differs from local in configuration alone.
And we mapped the two real-world deployment paths, managed Kubernetes and a single
VM.

**This completes Part 10 — and the build.** StartupIQ is feature-complete,
containerized, scalable, orchestrated, and shippable. Turn the page for a short
**epilogue** that looks back at everything the journey taught.

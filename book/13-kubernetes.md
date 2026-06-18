# Chapter 13 — Kubernetes: Running Many Copies

In Chapter 12 we found StartupIQ's ceiling: at some point, one copy of the API
can't keep up. The fix (Chapter 12 §4) was **horizontal scaling** — run several
copies behind a load balancer. This phase actually does it, on **Kubernetes**.

Docker Compose (Chapter 10) was great for running the stack on *one* machine. But
the moment you want *many* copies of a service, automatic restarts when something
crashes, rolling updates with no downtime, and autoscaling under load — you've
outgrown Compose. That's the job of an **orchestrator**, and Kubernetes ("k8s")
is the industry standard.

This is a big, jargon-heavy topic, so we'll learn only the handful of concepts
StartupIQ actually needs, grounded in the manifests in `infra/k8s/`.

## 13.1 What Kubernetes is, in one breath

Kubernetes is a system you give a *desired state* to — "I want 3 copies of the
API, 1 worker, 1 Redis, reachable at this URL" — and it works continuously to
**make reality match that description**. A pod crashes? It starts a new one. A
machine dies? It reschedules the pods elsewhere. You ask for 5 copies instead of
3? It creates 2 more. You stop describing *how* to run things and start
describing *what* you want; k8s figures out the how, forever.

You express that desired state as **YAML manifests** (declarative, like Alembic
migrations or Compose files), and apply them with `kubectl apply`.

## 13.2 The five nouns you need

Kubernetes has a hundred concepts. You need five.

**Pod** — the smallest unit: one running container (plus its immediate helpers).
Roughly "one instance of one of our programs." You rarely create pods directly.

**Deployment** — "keep N identical pods of this thing running." This is the
workhorse. Our `infra/k8s/03-api.yaml` says *replicas: 3* — "always keep 3 API
pods alive." If one dies, the Deployment replaces it. If you change the image, it
rolls pods over to the new version gradually. Each of our programs is a
Deployment: `api` (×3), `worker`, `frontend`, `redis`.

```yaml
kind: Deployment
metadata: { name: api, namespace: startupiq }
spec:
  replicas: 3                       # ← keep three copies alive
  template:
    spec:
      containers:
        - name: api
          image: startupiq-backend:latest
          envFrom: [ secretRef: {...}, configMapRef: {...} ]
```

**Service** — a *stable address* for a set of pods, **and a load balancer**. Pods
come and go with changing IPs; a Service gives them one unchanging name and
spreads incoming requests across whichever pods are currently alive. Our `api`
Service load-balances across the 3 api pods; the `redis` Service is how every pod
finds Redis (at the name `redis:6379` — that's why our `REDIS_URL` is
`redis://redis:6379`). **Service = the in-cluster load balancer.**

**ConfigMap & Secret** — config injected into pods as environment variables.
Non-secret values go in a **ConfigMap** (`01-configmap.yaml`); sensitive ones
(API keys, DB URLs) go in a **Secret**. This is Chapter 2's "config in the
environment" principle, the Kubernetes way — and it's why our app never needed
changing: it already reads everything from env vars. We even build the Secret
*directly from `backend/.env`*:

```bash
kubectl create secret generic startupiq-secrets --from-env-file=backend/.env -n startupiq
```

**Ingress** — the cluster's front door. It routes external HTTP by URL path to the
right Service — the exact same job nginx did in Compose (Chapter 10). Our
`06-ingress.yaml` sends `/api/*` to the api Service and everything else to the
frontend Service, giving the whole app one origin (`http://localhost`, no CORS).

```
Internet ──▶ Ingress ──/api/*──▶ api Service ──▶ [api pod, api pod, api pod]
                  └────/*───────▶ frontend Service ──▶ [frontend pod]
                                  api/worker pods ──▶ redis Service ──▶ [redis pod]
```

That's the whole architecture. Five nouns.

## 13.3 Why this works: stateless replicas + one shared brain

Here's the part that ties the entire book together. We can run 3 (or 30) API pods
*only because* of a decision made all the way back in the design: **the API is
stateless.** It keeps nothing important in its own memory — every piece of durable
state lives in **Postgres** (the data) or **Redis** (the queue, cache, and
rate-limit counters). So any pod can serve any request; they're interchangeable.
The load balancer can throw a request at any of the three and get the same answer.

Contrast the alternative: if an API pod kept the rate-limit counter *in its own
memory*, then with 3 pods a user would get *3 separate* budgets — the limit would
silently triple, and which limit you hit would depend on which pod you happened to
land on. Chaos. We avoided this in Chapter 8 by putting the counter in Redis, and
**this chapter is where that choice pays off.** Three stateless pods, one shared
Redis "brain":

```
   api pod 1 ─┐
   api pod 2 ─┼──▶ Redis  (the ONE rate-limit counter, the ONE cache)
   api pod 3 ─┘
```

The same is true of the cache: all 3 pods read and write the *same* Redis cache,
so a value cached by a request that hit pod 1 is instantly available to a request
that hits pod 3. Shared state in Redis is what makes the stateless replicas
coherent.

## 13.4 Self-healing, for free

Two small blocks in `03-api.yaml` buy a lot of reliability:

```yaml
readinessProbe: { httpGet: { path: /health, port: 8000 } }
livenessProbe:  { httpGet: { path: /health, port: 8000 } }
```

Remember the trivial `/health` endpoint we added way back in Chapter 4 ("load
balancers and Kubernetes will hit this")? Here's the payoff:

- **Readiness probe** — k8s won't route traffic to a pod until `/health` returns
  200. So during a deploy, new pods only get requests once they're actually ready;
  no user hits a half-started pod.
- **Liveness probe** — if a running pod stops answering `/health`, k8s assumes
  it's wedged and **restarts it automatically.** Your app heals itself at 3am
  without anyone awake.

This is the "Reliability" goal from your original list, made concrete.

## 13.5 The experiment: prove the limit is global

Theory is cheap; let's prove the shared-state claim. With the app deployed and the
API at 3 replicas, we make the write rate-limit small (`5/minute`) and fire 7
idea-creates through the load-balanced Ingress:

```bash
for i in $(seq 1 7); do
  curl -s -o /dev/null -w "request $i -> %{http_code}\n" \
    -X POST http://localhost/api/v1/ideas -H "Authorization: Bearer $TOKEN" \
    -H "Content-Type: application/json" -d '{"title":"k8s rate test","description":"x"}'
done
# 5 x 201, then 429, 429
```

The Ingress spread those 7 requests across 3 different pods — yet you get **exactly
5 successes**, not 15. If each pod counted in its own memory, three pods would
allow 5 each = 15. Getting 5 *total* proves the counter is shared (in Redis) and
the limit is enforced **globally across the whole fleet**. That single result is
the entire lesson of horizontal scaling done right. (We use the *free* idea-create
endpoint for this, not evaluations, so the demo costs nothing.)

And scaling itself is one command:
```bash
kubectl scale deployment/api -n startupiq --replicas=5    # now 5 copies
```
k8s creates two more pods; the Service immediately starts load-balancing across
all five. No code, no config, no downtime.

## 13.6 Autoscaling (the HPA)

You can even make k8s scale *itself*. The **HorizontalPodAutoscaler**
(`07-hpa.yaml`) watches CPU and adds/removes api pods automatically:

```yaml
kind: HorizontalPodAutoscaler
spec:
  scaleTargetRef: { kind: Deployment, name: api }
  minReplicas: 2
  maxReplicas: 6
  metrics:
    - type: Resource
      resource: { name: cpu, target: { type: Utilization, averageUtilization: 60 } }
```

"Keep average CPU around 60%: under load, grow toward 6 pods; when idle, shrink
back to 2." Point the Chapter 12 Locust test at it and watch `kubectl get hpa` add
pods as the pressure climbs, then remove them when you stop. The system right-sizes
itself — the essence of elastic, cloud-native scaling.

## 13.7 How to run it

You already have `kubectl` and Docker Desktop, which ships a one-click Kubernetes.
The full sequence is in **`infra/k8s/README.md`**; the shape of it:

1. **Enable** Docker Desktop's Kubernetes; install the ingress-nginx controller.
2. **Build** the images (`docker compose -f docker/docker-compose.yml build`) —
   the cluster uses your local images (`imagePullPolicy: IfNotPresent`).
3. **Create** the namespace, the Secret (from `backend/.env`), and the ConfigMap.
4. **Apply** the Deployments + Services + Ingress (`kubectl apply -f infra/k8s/...`).
5. **Watch** `kubectl get pods -n startupiq -w` until 3 api pods + the rest are
   Running, then open `http://localhost`.
6. **Experiment**: `kubectl scale …`, run the rate-limit proof, optionally the HPA.
7. **Tear down** with one command: `kubectl delete namespace startupiq`.

A few commands you'll lean on (the k8s daily driver):
```bash
kubectl get pods -n startupiq            # what's running
kubectl logs deploy/api -n startupiq     # an api pod's logs
kubectl describe pod <name> -n startupiq # why a pod won't start
kubectl scale deployment/api -n startupiq --replicas=N
```

> The local-cluster reality: getting images visible to the cluster and the
> ingress controller installed is the fiddly part of *any* local k8s — the README
> has a troubleshooting table. The manifests themselves are exactly what you'd use
> against a real cloud cluster; only the "where's the cluster" part changes (which
> is Phase 10).

---

**Recap.** We moved StartupIQ from one machine to an orchestrated cluster with
**Kubernetes**. We met its five core nouns — **Pod**, **Deployment** (keep N
copies alive), **Service** (stable address + load balancer), **ConfigMap/Secret**
(env config), and **Ingress** (the front door) — and ran the API as **3 stateless
replicas**. We proved that the **Redis-backed rate limiter and cache stay correct
across all replicas** (5 successes, not 15), which is the whole reason we built the
app stateless. We got **self-healing** from the `/health` probes we added in
Chapter 4, and **autoscaling** from the HPA.

**This completes Part 9.** The app now scales horizontally on a real
orchestrator — locally. **Part 10 (Phase 10)**, the finale, takes the *same*
manifests and images and ships them to the cloud with a CI/CD pipeline, so a
`git push` builds, tests, and deploys StartupIQ to the internet.

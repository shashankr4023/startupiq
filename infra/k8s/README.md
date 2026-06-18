# Running StartupIQ on Kubernetes

These manifests run the whole stack (api ×3, worker, frontend, redis) on a local
Kubernetes cluster, fronted by an Ingress at `http://localhost`. The point of
Phase 9: run **multiple copies** of the API behind a load balancer and watch the
**Redis-backed rate limiter and cache stay correct across all of them**.

Read **book/13-kubernetes.md** alongside this for the concepts.

---

## 0. Prerequisites

You already have `kubectl` and Docker Desktop. Enable its built-in Kubernetes:

1. Docker Desktop → **Settings → Kubernetes → Enable Kubernetes → Apply & Restart.**
2. Wait until the Kubernetes status (bottom-left of Docker Desktop) is green.
3. Point kubectl at it:
   ```bash
   kubectl config use-context docker-desktop
   kubectl get nodes        # should show one node, STATUS Ready
   ```

Install the **ingress-nginx** controller (the front door; one command):
```bash
kubectl apply -f https://raw.githubusercontent.com/kubernetes/ingress-nginx/controller-v1.11.3/deploy/static/provider/cloud/deploy.yaml
kubectl -n ingress-nginx rollout status deployment/ingress-nginx-controller --timeout=120s
```

## 1. Build the images (so the cluster can use them)

Kubernetes here runs your **locally built** images (the manifests use
`imagePullPolicy: IfNotPresent`). Build the latest (includes all phases) from the
repo root:
```bash
docker compose -f docker/docker-compose.yml build
docker images | grep startupiq    # should list startupiq-backend and -frontend
```

## 2. Create the namespace + secret + config

```bash
# from the repo root
kubectl apply -f infra/k8s/00-namespace.yaml

# Build the Secret straight from your backend .env (Supabase, API keys, etc.):
kubectl create secret generic startupiq-secrets \
  --from-env-file=backend/.env -n startupiq

kubectl apply -f infra/k8s/01-configmap.yaml
```

## 3. Deploy everything

```bash
kubectl apply -f infra/k8s/02-redis.yaml
kubectl apply -f infra/k8s/03-api.yaml
kubectl apply -f infra/k8s/04-worker.yaml
kubectl apply -f infra/k8s/05-frontend.yaml
kubectl apply -f infra/k8s/06-ingress.yaml

# Watch them come up (Ctrl+C when all show Running / READY):
kubectl get pods -n startupiq -w
```
You should see **3 `api-…` pods**, plus one each of worker, frontend, redis.

## 4. Use it

Open **http://localhost** — the app, served through the Ingress, exactly like the
Docker Compose version but now load-balanced across 3 API pods. Or hit the API
directly:
```bash
curl -i http://localhost/api/v1/ideas -H "Authorization: Bearer $TOKEN"
```

## 5. The experiment: scale, and prove shared state holds

**Scale the API up and down at will:**
```bash
kubectl scale deployment/api -n startupiq --replicas=5
kubectl get pods -n startupiq        # now 5 api pods
kubectl scale deployment/api -n startupiq --replicas=3
```

**Prove the rate limiter is global, not per-pod.** This is the key lesson. The
idea-create endpoint is rate-limited (free, no LLM). Make the limit small so it
trips fast, by overriding it in the ConfigMap:
```bash
kubectl set data configmap/startupiq-config -n startupiq RATE_LIMIT_WRITE=5/minute 2>/dev/null \
  || kubectl patch configmap/startupiq-config -n startupiq --type merge -p '{"data":{"RATE_LIMIT_WRITE":"5/minute"}}'
kubectl rollout restart deployment/api -n startupiq   # pods reload config
kubectl rollout status deployment/api -n startupiq
```
Now fire 7 idea-creates (more than the limit of 5) at the load-balanced endpoint:
```bash
for i in $(seq 1 7); do
  curl -s -o /dev/null -w "request $i -> %{http_code}\n" \
    -X POST http://localhost/api/v1/ideas \
    -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" \
    -d '{"title":"k8s rate test","description":"x"}'
done
# Expect: 5 x 201, then 429, 429.
```
Even though those 7 requests were spread across 3 different api pods by the
load balancer, you still get **exactly 5 successes** — not 15 (5 per pod). That's
because the rate-limit counter lives in **shared Redis**, not in any pod's memory.
*That* is why we built the app stateless. (Put the limit back:
`kubectl patch configmap/... RATE_LIMIT_WRITE` to `60/minute`, then
`kubectl rollout restart deployment/api -n startupiq`.)

## 6. (Optional) Autoscaling with the HPA

Needs the metrics-server:
```bash
kubectl apply -f https://github.com/kubernetes-sigs/metrics-server/releases/latest/download/components.yaml
# Docker Desktop: metrics-server needs --kubelet-insecure-tls; patch it:
kubectl patch deployment metrics-server -n kube-system --type=json \
  -p='[{"op":"add","path":"/spec/template/spec/containers/0/args/-","value":"--kubelet-insecure-tls"}]'
kubectl apply -f infra/k8s/07-hpa.yaml
kubectl get hpa -n startupiq      # watch CPU% and replica count
```
Throw load at it (the Locust test from infra/loadtest, --host http://localhost)
and watch `kubectl get hpa -n startupiq` add api pods automatically.

## 7. Tear down

```bash
kubectl delete namespace startupiq        # removes everything in one go
# (optionally) Docker Desktop → Settings → Kubernetes → disable, to reclaim resources
```

---

## Troubleshooting

| Symptom | Fix |
|---|---|
| pods stuck `ErrImageNeverPull` / `ImagePullBackOff` | Image not in the cluster's store — re-run `docker compose -f docker/docker-compose.yml build`; confirm `docker images` lists `startupiq-backend:latest` |
| `http://localhost` not responding | ingress-nginx not ready — `kubectl get pods -n ingress-nginx`; also stop any `docker compose` stack using port 80 |
| pods `CrashLoopBackOff` | `kubectl logs deploy/api -n startupiq` — usually a bad value in the Secret; recreate it from `backend/.env` |
| `kubectl create secret ... --from-env-file` errors on comments | Older kubectl chokes on `#` lines; strip comments/blanks: `grep -v '^#' backend/.env | grep . > /tmp/env && kubectl create secret generic startupiq-secrets --from-env-file=/tmp/env -n startupiq` |

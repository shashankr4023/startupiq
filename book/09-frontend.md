# Chapter 9 — The Frontend: A Face for the API

For eight chapters StartupIQ has been an engine with no body — powerful, but only
reachable through curl and Swagger. This phase gives it a face: a **Next.js**
web app where you log in, manage ideas, and click a tile to watch an AI
evaluation run and render itself as a little visualization. It's the moment the
project stops being "a backend" and becomes "a product."

This chapter is different from the others — it's frontend, not backend. But the
*architecture lessons* rhyme: clear layers, a single place for auth, programming
against the API contract, and the async poll-for-results pattern from Chapter 7
seen from the other side.

## 9.1 The stack, and why

- **Next.js (React) with the App Router** — the most popular React framework. We
  use it for routing (each folder under `app/` is a URL) and its build tooling.
- **TypeScript** — JavaScript with types. It catches "you passed the wrong shape"
  bugs *before* the app runs, the same safety Pydantic gives us on the backend.
- **Tailwind CSS** — utility classes (`flex`, `rounded-tile`, `bg-brand-blue`)
  you compose right in the markup, so we can match the reference design fast
  without writing separate stylesheets.
- **`@supabase/supabase-js`** — the official client for Supabase Auth. It handles
  login, stores the session, and refreshes the token — so we never build a login
  system by hand.

Everything lives in the top-level `frontend/` folder, a sibling of `backend/`.
They're separate programs that talk only over HTTP — exactly the boundary we drew
in Chapter 1.

## 9.2 The shape of a Next.js app

A quick orientation, because the folder *is* the routing:

```
frontend/
├── app/                      ← every folder here is a route (URL)
│   ├── layout.tsx            ← wraps every page (fonts, <html>/<body>)
│   ├── page.tsx              ← "/"  - decides login vs app
│   ├── login/page.tsx        ← "/login"
│   └── ideas/
│       ├── page.tsx          ← "/ideas"        (list + create)
│       └── [id]/page.tsx     ← "/ideas/<id>"   (the tile grid)
├── components/               ← reusable UI pieces
│   ├── AuthGuard.tsx, TopNav.tsx, IdeaForm.tsx, FeatureTile.tsx
│   └── results/              ← the result visualizations
└── lib/                      ← non-UI logic
    ├── supabaseClient.ts     ← the Supabase connection
    ├── api.ts                ← the one wrapper for all backend calls
    └── features.ts           ← metadata for the 6 feature tiles
```

`lib/` is our "logic layer", `components/` is reusable UI, `app/` is pages. The
same separation-of-concerns instinct from the backend, in frontend clothes.

### "use client"

You'll see `"use client";` at the top of most files. Next.js can render
components on the *server* by default, but ours need to run in the *browser* —
they use React state, click handlers, timers, and the user's auth session. That
top line marks a component as browser-side ("client component"). For a learner,
the rule of thumb: anything interactive or auth-aware gets `"use client"`.

## 9.3 Authentication: login without building login

The single biggest thing we get for free is auth. `lib/supabaseClient.ts` is the
whole setup:

```ts
export const supabase = createClient(
  process.env.NEXT_PUBLIC_SUPABASE_URL!,
  process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY!,
);
```

Two notes: the `NEXT_PUBLIC_` prefix is how Next.js marks env vars that are safe
to ship to the browser (Chapter 2's config principle, frontend edition). And the
**anon key** is *meant* to be public — it only permits what Supabase's auth rules
allow, so exposing it is fine.

The login page (`app/login/page.tsx`) is then just a form calling two Supabase
methods:

```ts
await supabase.auth.signInWithPassword({ email, password });  // log in
await supabase.auth.signUp({ email, password });              // register
```

Supabase verifies the credentials, and on success stores a **session** (including
the JWT access token) in the browser. We never see a password hash, never issue a
token, never manage a session table. That's the payoff of using a managed auth
provider — recall this was a *deliberate decision* back in planning.

### Guarding pages

`components/AuthGuard.tsx` wraps every protected page. On mount it asks Supabase
"is there a session?" — if not, it redirects to `/login`:

```ts
supabase.auth.getSession().then(({ data }) => {
  if (!data.session) router.replace("/login");
});
```

It also subscribes to `onAuthStateChange`, so signing out anywhere instantly
bounces you out. Every real page is wrapped like `<AuthGuard><RealPage/></AuthGuard>`.

## 9.4 One wrapper for every backend call

Here's the frontend mirror of a pattern we've used all along: don't scatter
`fetch(...)` calls everywhere — funnel them through one place. `lib/api.ts`:

```ts
async function authHeader() {
  const { data } = await supabase.auth.getSession();
  const token = data.session?.access_token;
  return token ? { Authorization: `Bearer ${token}` } : {};
}

async function request<T>(path, options) {
  const headers = { "Content-Type": "application/json", ...(await authHeader()), ... };
  const res = await fetch(`${API_BASE}/api/v1${path}`, { ...options, headers });
  if (!res.ok) throw new ApiError(res.status, (await res.json()).detail);
  return res.json();
}
```

Every call automatically gets the current user's token attached as
`Authorization: Bearer <jwt>` — the exact header our backend verifies via JWKS
(Chapter 5). This closes the loop: Supabase issues the token on the client, our
FastAPI verifies it on the server, and this wrapper is the bridge. Below it, a
small typed surface names every endpoint:

```ts
export const api = {
  listIdeas: () => request<Idea[]>("/ideas"),
  createIdea: (body) => request<Idea>("/ideas", { method: "POST", body: JSON.stringify(body) }),
  requestEvaluation: (ideaId, feature) =>
    request<JobResponse>(`/ideas/${ideaId}/evaluations/${feature}`, { method: "POST" }),
  getJob: (jobId) => request<Job>(`/jobs/${jobId}`),
};
```

Components call `api.listIdeas()`, never raw URLs. If the API changes, we fix it
here once. (The `Idea`, `Job` TypeScript interfaces are the frontend's copy of
the backend's Pydantic schemas — the same data contract, restated for the client.)

## 9.5 The tile: the async pattern from the client's side

This is the heart of the chapter. Each of the six features is a **tile**
(`components/FeatureTile.tsx`), and clicking "Evaluate" runs the *exact* async
flow we built in Chapter 7 — but now you can watch it:

```ts
async function run() {
  setStatus("queued");
  const job = await api.requestEvaluation(ideaId, meta.key);  // POST → 202 + job_id
  setJobId(job.job_id);
}

useEffect(() => {                       // when we have a job, poll it
  if (!jobId) return;
  timer.current = setInterval(async () => {
    const job = await api.getJob(jobId);             // GET /jobs/{id}
    if (job.status === "completed") { setResult(job.result); setStatus("completed"); stopPolling(); }
    else if (job.status === "failed") { setError(job.error_message); stopPolling(); }
    else setStatus(job.status);                       // queued | running
  }, 2000);
  return stopPolling;
}, [jobId]);
```

Recognize this? It's the curl loop from Chapter 7's §7.10 — *POST to get a job id,
then poll `GET /jobs/{id}` every 2 seconds until done* — turned into UI. The tile
shows a spinner that reads "Queued…" then "Analyzing…" then flips to the result.
Crucially, the browser is **never frozen**: because the backend returns `202`
instantly and the worker does the slow AI call, the page stays fully responsive,
and you can fire all six tiles at once and watch them complete independently.
*That* is why we did the async work in Phase 3 — this is the experience it buys.

A subtle React detail worth knowing: we keep the interval handle in a `useRef`
and clear it (`stopPolling`) the moment the job finishes or the component
unmounts. Forgetting to stop a timer is a classic memory-leak bug; the `return
stopPolling` in the effect is the cleanup that prevents it.

## 9.6 Visualising the result

A wall of text isn't a great result. So `components/results/` turns each
feature's structured JSON into a little visualization — matching the reference
design's stat-and-badge aesthetic. The primitives (`primitives.tsx`) are pure
CSS/SVG, no charting library:

- **`ScoreRing`** — an SVG circle that fills proportionally to a 1–10 score
  (used for MVP feasibility), green/amber/red by value.
- **`Bar`** — a labelled progress bar (revenue-model fit scores).
- **`Stat`** — a big number + caption (the TAM/SAM/SOM callouts).
- **`Badge` / `Chips`** — colored pills; `levelColor()` maps low/medium/high to
  green/amber/red so risk severity and market saturation read at a glance.

`FeatureResult.tsx` then switches on the feature and composes these — e.g. MVP
feasibility shows a score ring + complexity badge + timeline, market opportunity
shows three stat callouts + a growth badge, revenue models shows a bar per model.
Each tile also has an expandable "details" section with the full text. The data
all comes straight from the backend result schemas (Chapter 6) — the frontend is
just *drawing* what the AI already returned in a structured shape. (Which is
exactly why we made the LLM return structured data instead of prose: structured
output is what makes visualization possible at all.)

## 9.7 The pages, briefly

- **`/login`** — the split-panel login/signup (brand panel + form).
- **`/ideas`** — lists your ideas as cards and has a create form. On create it
  reloads the list. (Cards link to the detail page.)
- **`/ideas/[id]`** — the star: a blue header with the idea, then the 3×2 grid of
  feature tiles. The `[id]` folder name is a *dynamic route* — Next.js fills it
  from the URL and hands it to the page (in Next 15, via `use(params)`).

All three reach the backend only through `lib/api.ts`, and the two real pages are
wrapped in `AuthGuard`.

## 9.8 Running the whole stack

You now run **four** processes. The three backend ones from before, plus the
frontend:

**Terminals 1–3** (unchanged): `redis-server`, the API (`uvicorn ...`), the
worker (`arq ...`).

**Terminal 4 — the frontend:**
```bash
cd frontend
npm install            # first time only
npm run dev            # starts Next.js on http://localhost:3000
```

Open **http://localhost:3000**:

1. You're redirected to **/login**. Sign in with the test user you made in
   Supabase (or sign up — see the note below).
2. You land on **/ideas**. Create an idea (or see existing ones).
3. Click an idea → the **tile grid**. Hit **Evaluate** on any tile and watch it
   go *Queued… → Analyzing… → result*. Fire all six if you like — they run in
   parallel. Click "Show details" on a tile for the full breakdown.

> **CORS:** the backend already allows `http://localhost:3000` (its
> `FRONTEND_ORIGIN` from Chapter 4). If you run the frontend on a different port,
> update that env var or the browser will block the calls.
>
> **Signup & email confirmation:** by default Supabase emails a confirmation link
> on signup, so a brand-new account can't log in until confirmed. Easiest for
> development: in the Supabase dashboard → Authentication → Providers → Email,
> turn *off* "Confirm email" — or just keep using the test user you already
> created.

---

**Recap.** StartupIQ has a face. A Next.js app handles login through Supabase
(no auth code of our own), routes the user through an ideas list to a per-idea
**tile grid**, and each tile runs the Phase-3 async flow — enqueue, poll, render
— turning the AI's structured output into score rings, bars, and badges. The
frontend reuses every backend idea we've built: the JWT it sends is verified by
Chapter 5's JWKS check, the `202`+poll it does is Chapter 7's queue, and the
shapes it draws are Chapter 6's schemas.

**This completes Part 5.** We now have a real, working full-stack product running
across four local processes. **Part 6 (Phase 6)** packages all of them —
frontend, backend, worker, Redis — into **Docker** containers so the entire stack
starts with a single command instead of four terminals, and becomes portable to
any machine or cloud.

# Chapter 6 — The Evaluation Engine: A Provider-Agnostic LLM Abstraction

This is where StartupIQ stops being a glorified notebook and starts being
*intelligent*. Until now we could store and fetch ideas; now we can feed an idea
to an AI and get back structured competitor research, market sizing, risks, an
MVP plan, and revenue models.

But the *engineering* lesson of this chapter isn't "how to call an AI." It's how
to wrap something external, expensive, and swappable behind a clean boundary so
the rest of your app never depends on it directly. That pattern — the
**abstraction layer** — is one of the most important ideas in all of software
design, and an AI integration is the perfect place to learn it.

## 6.1 The problem: two AIs, one app

Your requirement (from the very start) was: **use OpenAI while developing and
testing, but Claude in production.** Why? OpenAI is convenient for fast local
iteration; Claude is what you want answering real users. Both are *large language
models* (LLMs) — give them a prompt, they give back text.

The naive approach would be to sprinkle `openai.chat.completions.create(...)`
calls throughout your endpoints. Then, to switch to Claude, you'd hunt down every
one of those calls and rewrite it. And every endpoint would be tangled up with
vendor-specific details. That's exactly the kind of mess layered design exists to
prevent (Chapter 1).

## 6.2 The solution: program to an interface, not an implementation

Here's the central idea. We define a **contract** — "anything that can take
prompts and return structured data is an LLM provider" — and then write the rest
of the app against *that contract*, never against OpenAI or Claude specifically.

In Python, a contract like this is an **Abstract Base Class** (ABC). Look at
`backend/app/llm/base.py`:

```python
from abc import ABC, abstractmethod
from typing import TypeVar
from pydantic import BaseModel

SchemaT = TypeVar("SchemaT", bound=BaseModel)

class LLMProvider(ABC):
    @abstractmethod
    async def generate(self, *, system_prompt: str, user_prompt: str,
                       schema: type[SchemaT]) -> SchemaT:
        ...

    @property
    @abstractmethod
    def name(self) -> str: ...   # "openai" or "claude"

    @property
    @abstractmethod
    def model(self) -> str: ...  # "gpt-4o" or "claude-opus-4-8"
```

Unpacking this:

- **`ABC` + `@abstractmethod`** — this class can't be used directly. It's a
  *template* that says "any real provider MUST implement a `generate` method, a
  `name`, and a `model`." If a subclass forgets one, Python refuses to let you
  create it. The ABC is the contract, enforced by the language.
- **`generate(...)` is the one method that matters.** It takes a system prompt
  (who the AI should be), a user prompt (the actual request), and a **`schema`**
  (the exact shape of data we want back), and returns a validated instance of
  that schema. Notice it says *nothing* about OpenAI or Claude — that's the whole
  point.
- **`SchemaT = TypeVar(..., bound=BaseModel)`** — this is a neat bit of typing.
  It means "whatever Pydantic model you pass as `schema`, you get an instance of
  *that same model* back." Call `generate(..., CompetitorResearchResult)` and the
  type checker knows you'll get a `CompetitorResearchResult`. The interface stays
  generic but callers keep full type safety.
- **`name` and `model`** — small but important: we record *which* AI produced
  each result. When you're comparing OpenAI's dev output against Claude's
  production output later, you'll be glad you tracked this.

> **The mental model:** `LLMProvider` is like a wall socket. Your app is an
> appliance that plugs into the socket. OpenAI and Claude are two different power
> plants. The appliance doesn't know or care which plant is behind the socket —
> it just expects 240 volts (the contract). Swap the plant; the appliance keeps
> working.

## 6.3 The two implementations

Now we write the concrete providers — the actual plugs that fit the socket.

**OpenAI** (`backend/app/llm/openai_provider.py`), used in development:

```python
class OpenAIProvider(LLMProvider):
    def __init__(self, api_key=None, model=None):
        self._model = model or settings.OPENAI_MODEL
        self._client = AsyncOpenAI(api_key=api_key or settings.OPENAI_API_KEY)

    async def generate(self, *, system_prompt, user_prompt, schema):
        completion = await self._client.chat.completions.parse(
            model=self._model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            response_format=schema,        # ← structured outputs
        )
        parsed = completion.choices[0].message.parsed
        if parsed is None:
            raise ValueError("OpenAI returned no parsed structured output")
        return parsed
```

**Claude** (`backend/app/llm/claude_provider.py`), used in production:

```python
class ClaudeProvider(LLMProvider):
    def __init__(self, api_key=None, model=None):
        self._model = model or settings.CLAUDE_MODEL
        self._client = AsyncAnthropic(api_key=api_key or settings.ANTHROPIC_API_KEY)

    async def generate(self, *, system_prompt, user_prompt, schema):
        response = await self._client.messages.parse(
            model=self._model,
            max_tokens=8000,
            system=system_prompt,
            thinking={"type": "adaptive"},   # let Claude reason as needed
            messages=[{"role": "user", "content": user_prompt}],
            output_format=schema,            # ← structured outputs
        )
        parsed = response.parsed_output
        if parsed is None:
            raise ValueError("Claude returned no parsed structured output")
        return parsed
```

Look at how **different** the insides are — different SDKs, different method
names (`chat.completions.parse` vs `messages.parse`), different ways of passing
the system prompt, Claude's extra `thinking` and `max_tokens`. *None of that
leaks out.* Both expose the identical `generate(...)` signature from the
contract. All the vendor-specific mess is sealed inside these two files.

### The key feature both rely on: structured outputs

A plain LLM returns free-form text. That's useless to a program — we'd have to
parse prose and hope. **Structured outputs** solve this: we hand the model a
schema (one of our Pydantic models from §6.4) and the model is *constrained* to
fill in exactly that shape, returning valid JSON we get back as a validated
object. `response_format=schema` (OpenAI) and `output_format=schema` (Claude) are
how each vendor does it. This is what makes an LLM usable as a reliable component
in a system rather than a chatbot.

### Adaptive thinking (Claude)

The one Claude-specific touch worth understanding: `thinking={"type":
"adaptive"}`. Evaluating a startup idea is genuinely hard reasoning, so we let
Claude think before it answers — it decides how much reasoning each request
needs. The *final* answer is still constrained to our schema; the thinking just
makes that answer better. (OpenAI's `parse` doesn't need an equivalent knob
here.)

## 6.4 Telling the AI exactly what shape to return

For structured outputs to work, we must *define* the shapes. That's
`backend/app/schemas/llm_results.py` — a Pydantic model per evaluation type. For
example, competitor research:

```python
class Competitor(BaseModel):
    name: str = Field(description="Company or product name")
    description: str = Field(description="What they do, in one or two sentences")
    strengths: list[str] = Field(description="Key strengths / advantages")
    weaknesses: list[str] = Field(description="Key weaknesses / gaps")
    differentiation: str = Field(description="How the idea could differentiate")

class CompetitorResearchResult(BaseModel):
    summary: str = Field(description="Overall competitive landscape summary")
    competitors: list[Competitor] = Field(description="3-6 notable competitors")
    market_saturation: str = Field(description="low/medium/high, with a reason")
```

Two things to absorb:

- **These are the same Pydantic models from Chapter 4** — but used for a brand
  new purpose. In Chapter 4 they validated *incoming API JSON*. Here they define
  *what we demand back from an AI*. Same tool, different job. That reuse is a sign
  the abstraction is healthy.
- **`Field(description=...)` is doing real work.** Those descriptions are sent to
  the model as part of the schema — they *guide* what the AI writes into each
  field. Good descriptions produce good output. The schema is simultaneously a
  data contract *and* a mini-prompt.

A subtle design choice: every field is **required** (no `Optional`). Strict
structured-output modes on both vendors prefer fully-specified schemas, and it
guarantees we never get back a half-empty result. We describe numeric ranges
(like a 1–10 score) in the field *description* rather than enforcing them with
bounds, because strict mode doesn't support numeric constraints — a small,
real-world accommodation.

## 6.5 The registry: one place that knows all the features

We have six evaluation types. We do *not* want six near-identical endpoints or a
giant `if feature == "competitor_research": ... elif ...` block. Instead, one
**registry** describes every feature once — `backend/app/llm/features.py`:

```python
class FeatureType(str, Enum):
    competitor_research = "competitor_research"
    target_customer = "target_customer"
    market_opportunity = "market_opportunity"
    risk_identification = "risk_identification"
    mvp_feasibility = "mvp_feasibility"
    revenue_model = "revenue_model"

@dataclass(frozen=True)
class FeatureSpec:
    label: str
    result_schema: type[BaseModel]
    instruction: str

FEATURES: dict[FeatureType, FeatureSpec] = {
    FeatureType.competitor_research: FeatureSpec(
        label="Competitor Research",
        result_schema=CompetitorResearchResult,
        instruction="Identify the most relevant existing competitors...",
    ),
    # ... five more entries
}
```

This is the **registry pattern**, and it's worth recognizing because you'll use
it everywhere. Each feature is just *data*: a label, which schema to fill, and
the instruction to add to the prompt. The code that runs an evaluation looks up
the spec and runs it generically — it has no per-feature branches.

The payoff: **adding a seventh evaluation type later is one new schema + one new
dictionary entry.** No new endpoint, no new `if`. That's the registry earning its
keep. (Recall our "Overall Score / SWOT" feature from the roadmap — that's
exactly how we'll add it.)

There are two more pieces here:

- **`FeatureType(str, Enum)`** — an enumeration of the valid feature names.
  Because it inherits from `str`, the value *is* the string `"competitor_research"`,
  so it works directly as a URL path segment and JSON value. And FastAPI will
  automatically reject any feature name not in the enum with a `422` error — free
  validation (we test exactly this in §6.7).
- **`SYSTEM_PROMPT` and `build_user_prompt(idea, spec)`** — the system prompt
  sets the AI's persona ("You are StartupIQ, an experienced startup analyst...");
  `build_user_prompt` assembles the idea's title/description/industry plus the
  feature instruction into the actual request. Separating the *stable* system
  prompt from the *per-request* user prompt is good practice (and will matter for
  caching much later).

## 6.6 The factory: choosing a provider at runtime

One question remains: *who decides* whether we're using OpenAI or Claude? The
**factory** — `backend/app/llm/factory.py`:

```python
@lru_cache(maxsize=1)
def get_llm_provider() -> LLMProvider:
    provider = settings.LLM_PROVIDER.lower()
    if provider == "claude":
        from app.llm.claude_provider import ClaudeProvider
        return ClaudeProvider()
    if provider == "openai":
        from app.llm.openai_provider import OpenAIProvider
        return OpenAIProvider()
    raise ValueError(f"Unknown LLM_PROVIDER={settings.LLM_PROVIDER!r}")
```

This is the *only* place in the entire codebase that names the concrete
providers. It reads the `LLM_PROVIDER` environment variable (Chapter 2's
12-factor config!) and returns the matching one. So switching the whole
application from OpenAI to Claude is exactly one line in your `.env`:

```
LLM_PROVIDER=claude
```

No code change. That is the abstraction paying off in the most literal way
possible. Two details:

- **`@lru_cache(maxsize=1)`** — builds the provider once and reuses it, instead
  of constructing a new client on every request. (A tiny, sensible optimization.)
- **Lazy imports inside the branches** — we only import the OpenAI SDK if we're
  actually using OpenAI. So a missing `ANTHROPIC_API_KEY` never breaks you while
  you're running on OpenAI, and vice-versa.

## 6.7 Wiring it into an endpoint — and why it stays simple

Now the reveal. Here's the entire evaluation endpoint,
`backend/app/api/v1/evaluations.py`:

```python
@router.post("/{idea_id}/evaluations/{feature_type}")
async def run_evaluation(
    idea_id: UUID,
    feature_type: FeatureType,
    user_id: UUID = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
    provider: LLMProvider = Depends(get_llm_provider),   # ← the abstraction
):
    idea = await session.get(StartupIdea, idea_id)
    if idea is None or idea.user_id != user_id:           # ← Ch.4 authorization
        raise HTTPException(status_code=404, detail="Idea not found")

    spec = FEATURES[feature_type]                         # ← registry lookup
    user_prompt = build_user_prompt(idea, spec)

    try:
        result = await provider.generate(
            system_prompt=SYSTEM_PROMPT,
            user_prompt=user_prompt,
            schema=spec.result_schema,
        )
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"LLM provider error: {exc}")

    return {
        "idea_id": str(idea_id),
        "feature_type": feature_type.value,
        "feature_label": spec.label,
        "llm_provider": provider.name,
        "model": provider.model,
        "result": result.model_dump(),
    }
```

Read how *little* this endpoint knows. It does not import OpenAI or Claude. It
gets `provider` through **dependency injection** (Chapter 4) — `Depends(
get_llm_provider)` — so it receives "the configured provider" without caring
which. It looks the feature up in the registry. It calls `provider.generate(...)`
against the *contract*. Every layer we built earlier shows up here cooperating:
auth, ownership check, DI, the registry, the abstraction. That's the system
design working.

The `502 Bad Gateway` on failure is a deliberate REST touch: if *our* server is
fine but the *upstream* AI failed, `502` ("bad gateway") is the honest status —
it says "the thing I depend on broke," not "you sent a bad request."

### Why this is still *synchronous* — on purpose

This endpoint **blocks** while the AI thinks (which can take many seconds). For a
learning Phase 2, that's intentional: we wanted to isolate the LLM integration
without *also* introducing background jobs at the same time. One new concept at a
time (the philosophy from the Preface). In **Chapter 7 (Phase 3)** we'll move
this slow work onto a queue and a worker, so the API responds instantly with a
job id and the AI runs in the background. The abstraction we built here won't
change at all — only *where* `generate` gets called.

## 6.8 The real test of an abstraction: faking it

Here's the proof that the boundary is clean. In our tests
(`backend/tests/test_evaluations.py`) we never call a real AI — that would be
slow, cost money, and give different output every run. Instead we write a
**fake** provider and inject it:

```python
class FakeLLMProvider(LLMProvider):
    async def generate(self, *, system_prompt, user_prompt, schema):
        return CANNED_RESULT          # a fixed, schema-valid object
    @property
    def name(self): return "fake"
    @property
    def model(self): return "fake-model-1"

@pytest.fixture
def fake_llm():
    app.dependency_overrides[get_llm_provider] = lambda: FakeLLMProvider()
    yield
    app.dependency_overrides.pop(get_llm_provider, None)
```

Because the endpoint only depends on the `LLMProvider` *contract*, we can slot in
a third implementation that the endpoint can't distinguish from the real thing.
The test runs in **10 milliseconds**, offline, deterministically. This is not a
trick — *the ability to substitute a fake is the definition of a well-isolated
dependency.* If faking it were hard, that would be a signal the abstraction was
leaky. It was easy, so the design is sound.

Our three tests verify the three behaviors that matter: a valid request returns
the structured result tagged with the provider; an idea you don't own returns
`404`; and an invalid feature name returns `422` (the enum validation from §6.5,
for free). All green.

## 6.9 How to actually run it

To try it against a real AI:

1. Put an `OPENAI_API_KEY` (and keep `LLM_PROVIDER=openai`) in your `.env`.
2. Start the server: `uvicorn app.main:app --reload`.
3. Create an idea (Chapter 4's curl), grab its `id`, then:

```bash
curl -X POST \
  "http://localhost:8000/api/v1/ideas/<idea_id>/evaluations/competitor_research" \
  -H "Authorization: Bearer $TOKEN"
```

You'll get back structured competitor research as JSON. Swap to
`market_opportunity`, `risk_identification`, etc. in the URL for the other
analyses. To run it through Claude instead, set `LLM_PROVIDER=claude` and add
`ANTHROPIC_API_KEY` — and notice you changed *zero lines of code*.

---

**Recap.** We built a provider-agnostic LLM layer: an `LLMProvider` contract
(ABC), two interchangeable implementations (OpenAI, Claude) that hide all
vendor-specific detail, Pydantic result schemas that double as the AI's output
contract, a registry that describes all six evaluation features as data, and a
factory that picks the provider from one env var. The endpoint that uses it all
stays tiny and vendor-blind — provable by how trivially we faked the provider in
tests.

**This completes Part 2.** StartupIQ can now turn an idea into real, structured
AI analysis. But it does so by *blocking* — and that won't scale. **Part 3
(Phase 3)** fixes that: Redis, a job queue, and a background worker, so
evaluations run asynchronously and the API stays fast.

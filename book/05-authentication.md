# Chapter 5 — Authentication

Every protected endpoint in Chapter 4 had this line:

```python
user_id: UUID = Depends(get_current_user)
```

This chapter is about that one function — how the server figures out *who* is
making a request — and about the very real, three-layered bug we had to debug to
make it work. That debugging story is the most valuable part of this chapter, so
don't skim it.

## 5.1 The problem authentication solves

HTTP is **stateless**: every request arrives with no memory of the ones before
it. The server has no idea who's calling unless the request *itself* carries
proof of identity. So how does the very first request after login prove "I'm
user da272dcd-…" — without sending a password every single time, and without the
server storing a session for every user (which doesn't scale)?

The modern answer: a **token** — specifically, a **JWT**.

## 5.2 What a JWT is

A **JWT** (JSON Web Token, pronounced "jot") is a small, **digitally signed**
piece of text that says, in effect: "the bearer of this token is user X, this
was issued at time Y, and it expires at time Z." It has three parts separated by
dots: `header.payload.signature`.

Decode the *payload* of the token we actually used in this project and you see:

```json
{
  "iss": "https://kwxsnxrjieowjipzutzs.supabase.co/auth/v1",
  "aud": "authenticated",
  "sub": "da272dcd-1b4d-4aa7-a1db-88d51587b303",   ← the user's id!
  "exp": 1781237468,                                ← expiry timestamp
  "iat": 1781233868,                                ← issued-at timestamp
  "role": "authenticated"
}
```

The `sub` ("subject") field *is* the user id our endpoints need. So why can't a
hacker just type out a JSON like this claiming to be anyone? Because of the
**signature** (the third part). Supabase signs the token with a secret key when
you log in. The server can verify that signature mathematically. Change even one
character of the payload and the signature no longer matches — the token is
rejected. The payload is *readable* by anyone (it's not encrypted), but it's
*tamper-proof*.

> **Key insight:** A JWT isn't secret, it's *trustworthy*. Anyone can read what
> it claims; only the holder of the signing key could have produced a valid one.

## 5.3 The flow

```
1. User logs in (email + password) ──► Supabase Auth
2. Supabase verifies, signs a JWT  ──► returns it to the user
3. User's client stores the JWT
4. Every API request includes it:  ──► Authorization: Bearer <jwt>
5. Our FastAPI server verifies the signature, reads `sub`, trusts it.
```

The beautiful part of step 5: our server verifies the token **without calling
Supabase**. Verification is pure math against a key the server already has. No
network round-trip per request, which is what makes JWTs fast and scalable.
This is why we chose Supabase Auth — steps 1–2, building a secure login system,
is a huge amount of work we got for free.

## 5.4 The verification function

Here's `app/core/security.py` in its final, working form:

```python
from uuid import UUID
import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jwt import PyJWKClient
from app.core.config import settings

bearer_scheme = HTTPBearer()

# Fetches and caches Supabase's PUBLIC signing keys (JWKS).
_jwk_client = PyJWKClient(settings.SUPABASE_JWKS_URL)

async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(bearer_scheme),
) -> UUID:
    token = credentials.credentials
    try:
        signing_key = _jwk_client.get_signing_key_from_jwt(token)   # find the right public key
        payload = jwt.decode(
            token,
            signing_key.key,
            algorithms=["ES256", "RS256"],
            audience="authenticated",
        )
    except jwt.PyJWTError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
            headers={"WWW-Authenticate": "Bearer"},
        )
    sub = payload.get("sub")
    if sub is None:
        raise HTTPException(status_code=401, detail="Token missing subject claim")
    return UUID(sub)
```

`HTTPBearer()` pulls the token out of the `Authorization: Bearer <token>`
header. `jwt.decode(...)` verifies the signature, the audience, and the expiry
all at once — if *anything* is wrong it raises, and we answer `401 Unauthorized`.
If all is well, we return the `sub` as the user's id, and every endpoint that
declared `Depends(get_current_user)` receives it.

But the version above is the *fixed* version. Getting here took three debugging
rounds — and that's the real lesson.

## 5.5 War story: the token that wouldn't validate

When we first tried to create an idea, the server answered:
`{"detail": "Invalid or expired token"}`. The token was fresh. So why?

Our *first* version of `get_current_user` looked different — it verified using a
**shared secret** with the `HS256` algorithm:

```python
# our FIRST attempt (wrong for this project)
payload = jwt.decode(token, settings.SUPABASE_JWT_SECRET, algorithms=["HS256"], ...)
```

This is the *classic* JWT setup, and it's what most tutorials show. It just
didn't match *our* Supabase project. Here's how we found out.

### The technique: stop guessing, start inspecting

The endpoint's error message was deliberately vague (`"Invalid or expired
token"` — Chapter 4's lesson about not leaking auth details). Vague is right for
production, useless for debugging. So we wrote a throwaway script,
`backend/scripts/debug_jwt.py`, that does the *same* verification but prints the
**real** underlying error instead of swallowing it.

> **This is a transferable skill.** When a system gives you a generic failure,
> write a tiny script that reproduces just that step and surfaces the raw error.
> Don't theorize from the outside — get the system to tell you what's wrong.

### Round 1 — wrong algorithm

The script decoded the token's *header* (the first part, also public) and
printed:

```
{'alg': 'ES256', 'kid': '8363acb1-...', 'typ': 'JWT'}
```

There it was. The token was signed with **ES256**, but our code was trying to
verify it with **HS256**. Two fundamentally different schemes:

- **HS256** is *symmetric*: the same secret key both signs and verifies. Good
  when one party does both.
- **ES256 / RS256** are *asymmetric*: a **private** key (which only Supabase
  has) signs, and a corresponding **public** key (which anyone may have)
  verifies. The `kid` ("key id") in the header points at *which* public key.

Newer Supabase projects (like ours) default to **asymmetric** keys. So there's
no shared secret to give our server — instead, the server must fetch Supabase's
**public** key and verify with that.

**The fix:** use `PyJWKClient`, which downloads Supabase's public keys from a
standard URL — its **JWKS** endpoint (JSON Web Key Set):

```
https://<your-project>.supabase.co/auth/v1/.well-known/jwks.json
```

It reads the token's `kid`, fetches the matching public key, and caches it (so
it's a one-time fetch, not per request). We rewrote `get_current_user` to the
`PyJWKClient` version above and removed the now-useless `SUPABASE_JWT_SECRET`
from our config. We thought we were done.

### Round 2 — same error, deeper cause

We ran it again. **Same `"Invalid or expired token"`.** Frustrating — but
instead of guessing, we extended the debug script to run the *exact* new
code path and, again, print the raw error. This time:

```
--- Fetching JWKS from: https://...supabase.co/auth/v1/.well-known/jwks.json ---
HTTP status: 200
Body: {"keys":[{"alg":"ES256","crv":"P-256",..., "kid":"8363acb1-...", ...}]}

❌ Verification FAILED: MissingCryptographyError:
   ES256 requires 'cryptography' to be installed.
```

A *completely* different problem, revealed only because we refused to guess. The
JWKS fetch worked, the right key was found — but PyJWT **physically could not
perform** ES256 verification, because ES256 relies on elliptic-curve math that
lives in a separate library called `cryptography`, which wasn't installed.

PyJWT can do simple HS256 on its own, but for asymmetric algorithms it delegates
the heavy crypto to that optional library. We had `pyjwt` but not its crypto
extra.

**The fix:** install PyJWT *with* its crypto extra, and — crucially — record it
permanently in `pyproject.toml` so it's never missing again:

```toml
"pyjwt[crypto]>=2.9",   # [crypto] pulls in `cryptography`, required for ES256
```

```bash
pip install 'pyjwt[crypto]'
```

We ran the script one more time: `✅ Verification SUCCEEDED`. The curl finally
created the idea. Phase 1 was genuinely done.

### What this war story teaches

1. **A generic error can hide several distinct causes.** "Invalid token" meant
   *wrong algorithm*, then later *missing library* — same message, unrelated
   problems. Never assume the second occurrence of an error has the same cause
   as the first.
2. **Debug by inspection, not theory.** Each round, the fix came from making the
   system *print the real error*, not from speculating. The `debug_jwt.py` script
   was worth more than any amount of staring at the code.
3. **Eliminate one layer at a time.** The script confirmed, in order: token not
   expired ✅ → JWKS reachable ✅ → correct key present ✅ → *then* the true
   failure surfaced. Each green check ruled out a whole category.
4. **Dependency "extras" are real and easy to miss.** `pyjwt` vs `pyjwt[crypto]`
   is the difference between working and not. Pinning it in `pyproject.toml`
   means your Docker build (Phase 6) and any future machine get it automatically
   — the bug can't silently return.

## 5.6 Authentication vs Authorization (don't confuse them)

A final framing you'll use forever:

- **Authentication** = "Who are you?" → done by `get_current_user` verifying the
  JWT. Output: a trusted user id.
- **Authorization** = "Are you allowed to do *this*?" → done in each endpoint,
  e.g. `if idea.user_id != user_id: 404` (Chapter 4). Output: allow or deny.

A valid token proves *who* you are; it does **not** automatically grant access
to a specific idea. You need both checks, in that order. Mixing them up — or
skipping the second — is one of the most common security holes in real apps.

---

**Recap.** The server identifies callers via signed JWTs from Supabase Auth,
verified locally against Supabase's public keys (no per-request round-trip). We
debugged a stacked failure — wrong algorithm, then a missing crypto library — by
building a script that surfaced the real errors instead of guessing. And we
firmly separated *authentication* (who) from *authorization* (allowed to).

**This completes Part 1.** You now have a secure, well-structured backend that
stores and serves a user's startup ideas. In **Part 2** we make it intelligent:
the LLM provider abstraction that turns a stored idea into an actual evaluation.

"""Rate limiting with slowapi (backed by Redis).

A *rate limiter* caps how many requests a client may make in a window of time.
We use it to protect the expensive evaluation endpoint - without it, a bug, a
script, or an impatient click-frenzy could fire hundreds of (billed) LLM calls.

The limiter counts requests per *key*. Our key is the authenticated user
(extracted from their JWT) so each user gets their own budget; if there's no
token we fall back to the client IP. The counters live in Redis, which means the
limit is shared across *all* API replicas - essential once we scale horizontally.
"""

import jwt
from fastapi import Request
from slowapi import Limiter
from slowapi.util import get_remote_address

from app.core.config import settings


def user_or_ip_key(request: Request) -> str:
    """Rate-limit key: the user's id when authenticated, else their IP.

    We decode the JWT *without verifying* it here - this is only to bucket the
    counter, not to grant access (real verification still happens in the
    endpoint's auth dependency). A forged token just buckets into a junk key.
    """
    auth = request.headers.get("authorization", "")
    if auth.lower().startswith("bearer "):
        token = auth[7:]
        try:
            payload = jwt.decode(token, options={"verify_signature": False})
            sub = payload.get("sub")
            if sub:
                return f"user:{sub}"
        except jwt.PyJWTError:
            pass
    return f"ip:{get_remote_address(request)}"


limiter = Limiter(
    key_func=user_or_ip_key,
    storage_uri=settings.REDIS_URL,
    # If Redis is briefly unreachable, fall back to per-process memory counting
    # rather than erroring out the request.
    in_memory_fallback_enabled=True,
)

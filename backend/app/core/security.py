from uuid import UUID

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jwt import PyJWKClient

from app.core.config import settings

bearer_scheme = HTTPBearer()

# PyJWKClient fetches and caches Supabase's public signing keys (JWKS).
# Newer Supabase projects sign access tokens with an asymmetric key
# (ES256/RS256) identified by a "kid" in the token header, so verification
# uses the matching public key rather than a shared secret.
_jwk_client = PyJWKClient(settings.SUPABASE_JWKS_URL)


async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(bearer_scheme),
) -> UUID:
    """Validate the Supabase-issued JWT and return the authenticated user's id.

    Validation is done locally against Supabase's public JWKS, so no
    per-request round trip to Supabase is required (the public keys are
    fetched once and cached).
    """
    token = credentials.credentials
    try:
        signing_key = _jwk_client.get_signing_key_from_jwt(token)
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
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token missing subject claim",
        )

    return UUID(sub)

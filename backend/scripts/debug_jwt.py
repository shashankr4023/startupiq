"""One-off debugging helper: decode a Supabase access token locally and check
why it might be failing validation via Supabase's JWKS endpoint.

Usage:
    python scripts/debug_jwt.py
    (then paste the access_token when prompted)

This script does NOT send the token anywhere except to your own Supabase
project's public JWKS endpoint (to fetch its public signing keys).
"""

import time

import httpx
import jwt
from dotenv import load_dotenv
from jwt import PyJWKClient

from app.core.config import settings

load_dotenv()

token = input("Paste the access_token: ").strip()

header = jwt.get_unverified_header(token)
payload = jwt.decode(token, options={"verify_signature": False})

print("\n--- Token header ---")
print(header)

print("\n--- Token payload (unverified) ---")
for key in ("iss", "aud", "sub", "exp", "iat", "role"):
    print(f"{key}: {payload.get(key)}")

now = int(time.time())
exp = payload.get("exp", 0)
print(f"\nnow:     {now}")
print(f"exp:     {exp}")
print(f"expired: {exp < now}")

jwks_url = settings.SUPABASE_JWKS_URL
print(f"\n--- Fetching JWKS from: {jwks_url} ---")
try:
    resp = httpx.get(jwks_url, timeout=10)
    print(f"HTTP status: {resp.status_code}")
    print(f"Body: {resp.text}")
except Exception as e:
    print(f"Request failed: {e!r}")

print("\n--- Attempting PyJWKClient verification (same path as security.py) ---")
try:
    jwk_client = PyJWKClient(jwks_url)
    signing_key = jwk_client.get_signing_key_from_jwt(token)
    print(f"Found signing key with kid: {signing_key.key_id}")
    decoded = jwt.decode(
        token,
        signing_key.key,
        algorithms=["ES256", "RS256"],
        audience="authenticated",
    )
    print("\n✅ Verification SUCCEEDED")
    print(decoded)
except Exception as e:
    print(f"\n❌ Verification FAILED: {type(e).__name__}: {e}")

"""Unit test for the rate-limiter key function.

We don't exercise slowapi's full 429 machinery here (that needs Redis and is
verified manually - see book Chapter 8). We test our own logic: that an
authenticated request buckets by user id, and an anonymous one falls back to IP.
"""

import jwt

from app.core.rate_limit import user_or_ip_key


class FakeRequest:
    def __init__(self, headers: dict, host: str = "203.0.113.7"):
        self.headers = headers
        self.client = type("Client", (), {"host": host})()


def test_key_is_user_when_token_present():
    token = jwt.encode({"sub": "user-123"}, "x" * 32, algorithm="HS256")
    req = FakeRequest({"authorization": f"Bearer {token}"})
    assert user_or_ip_key(req) == "user:user-123"


def test_key_falls_back_to_ip_when_no_token():
    req = FakeRequest({})
    assert user_or_ip_key(req) == "ip:203.0.113.7"

"""Selects the concrete LLM provider based on configuration.

This is the only place that knows which providers exist. Call sites just ask
`get_llm_provider()` and receive an `LLMProvider` - they don't care which one.
Switching the whole app from OpenAI to Claude is a single env var:
`LLM_PROVIDER=claude`.
"""

from functools import lru_cache

from app.core.config import settings
from app.llm.base import LLMProvider


@lru_cache(maxsize=1)
def get_llm_provider() -> LLMProvider:
    """Return the configured provider (constructed once and cached).

    Imports are done lazily inside the branches so we don't construct an
    OpenAI client when running with Claude (or vice-versa), and so missing
    optional config for the *unused* provider never breaks startup.
    """
    provider = settings.LLM_PROVIDER.lower()

    if provider == "claude":
        from app.llm.claude_provider import ClaudeProvider

        return ClaudeProvider()
    if provider == "openai":
        from app.llm.openai_provider import OpenAIProvider

        return OpenAIProvider()

    raise ValueError(
        f"Unknown LLM_PROVIDER={settings.LLM_PROVIDER!r}; expected 'openai' or 'claude'"
    )

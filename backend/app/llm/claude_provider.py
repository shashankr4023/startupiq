"""Claude (Anthropic) implementation of LLMProvider - used in production.

Uses Anthropic's structured outputs via `messages.parse(output_format=...)`,
which constrains Claude to return exactly our schema and exposes the validated
instance as `response.parsed_output`.

Adaptive thinking is enabled: Claude decides how much to reason per request,
which improves the quality of these open-ended analytical evaluations. The
structured-output format still constrains the *final* answer to our schema.
"""

from anthropic import AsyncAnthropic

from app.core.config import settings
from app.llm.base import LLMProvider, SchemaT


class ClaudeProvider(LLMProvider):
    def __init__(self, api_key: str | None = None, model: str | None = None) -> None:
        self._model = model or settings.CLAUDE_MODEL
        self._client = AsyncAnthropic(api_key=api_key or settings.ANTHROPIC_API_KEY)

    async def generate(
        self,
        *,
        system_prompt: str,
        user_prompt: str,
        schema: type[SchemaT],
    ) -> SchemaT:
        response = await self._client.messages.parse(
            model=self._model,
            max_tokens=8000,
            system=system_prompt,
            thinking={"type": "adaptive"},
            messages=[{"role": "user", "content": user_prompt}],
            output_format=schema,
        )
        parsed = response.parsed_output
        if parsed is None:
            # Happens on a refusal or truncation before valid JSON was produced.
            raise ValueError("Claude returned no parsed structured output")
        return parsed

    @property
    def name(self) -> str:
        return "claude"

    @property
    def model(self) -> str:
        return self._model

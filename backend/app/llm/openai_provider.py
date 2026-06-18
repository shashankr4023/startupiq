"""OpenAI implementation of LLMProvider - used during development/testing.

Uses OpenAI's structured outputs (`chat.completions.parse` with a Pydantic
`response_format`), which constrains the model to return exactly our schema and
hands back a parsed, validated instance.
"""

from openai import AsyncOpenAI

from app.core.config import settings
from app.llm.base import LLMProvider, SchemaT


class OpenAIProvider(LLMProvider):
    def __init__(self, api_key: str | None = None, model: str | None = None) -> None:
        self._model = model or settings.OPENAI_MODEL
        self._client = AsyncOpenAI(api_key=api_key or settings.OPENAI_API_KEY)

    async def generate(
        self,
        *,
        system_prompt: str,
        user_prompt: str,
        schema: type[SchemaT],
    ) -> SchemaT:
        completion = await self._client.chat.completions.parse(
            model=self._model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            response_format=schema,
        )
        parsed = completion.choices[0].message.parsed
        if parsed is None:
            # Happens on a refusal or if the model returned no parseable content.
            raise ValueError("OpenAI returned no parsed structured output")
        return parsed

    @property
    def name(self) -> str:
        return "openai"

    @property
    def model(self) -> str:
        return self._model

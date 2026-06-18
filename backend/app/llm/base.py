"""The provider-agnostic LLM interface.

This is the single seam between StartupIQ and whichever LLM vendor we use.
Everything above this line (endpoints, services, the future worker) talks only
to `LLMProvider`; everything below (OpenAI, Claude) is an interchangeable
implementation detail selected at runtime by the factory.

Keeping this boundary tight is the whole point of Phase 2: swapping OpenAI for
Claude is a one-line config change, not a code change.
"""

from abc import ABC, abstractmethod
from typing import TypeVar

from pydantic import BaseModel

# A type variable bound to BaseModel lets `generate` return the *same* concrete
# schema type it was given - so callers get full type information back, e.g.
# `generate(..., CompetitorResearchResult)` is typed as returning that model.
SchemaT = TypeVar("SchemaT", bound=BaseModel)


class LLMProvider(ABC):
    """Abstract base class every concrete provider must implement."""

    @abstractmethod
    async def generate(
        self,
        *,
        system_prompt: str,
        user_prompt: str,
        schema: type[SchemaT],
    ) -> SchemaT:
        """Send the prompts to the LLM and return a validated instance of `schema`.

        Implementations MUST use the vendor's structured-output feature so the
        response is guaranteed to match `schema`, and MUST return an instance of
        that Pydantic model (not raw text/JSON).
        """
        raise NotImplementedError

    @property
    @abstractmethod
    def name(self) -> str:
        """Short provider id recorded alongside results, e.g. 'openai' or 'claude'."""
        raise NotImplementedError

    @property
    @abstractmethod
    def model(self) -> str:
        """The concrete model id used, e.g. 'gpt-4o' or 'claude-opus-4-8'."""
        raise NotImplementedError

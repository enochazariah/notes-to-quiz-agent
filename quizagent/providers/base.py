from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, TypeVar

from pydantic import BaseModel

from ..pdf_input import SourceMaterial

T = TypeVar("T", bound=BaseModel)


class ProviderError(RuntimeError):
    """Raised with a message that is safe to show to the user (never contains secrets)."""


class LLMProvider(ABC):
    name: str = "base"

    @abstractmethod
    def generate(
        self,
        *,
        task: str,
        schema: type[T],
        prompt: str,
        source: SourceMaterial | None = None,
        params: dict[str, Any] | None = None,
    ) -> T:
        """Return an instance of `schema`. `params` carries the same request in structured
        form (used by the offline mock; real providers rely on `prompt`)."""

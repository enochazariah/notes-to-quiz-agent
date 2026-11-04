"""One place that decides which provider the app uses."""
from __future__ import annotations

from ..config import Settings
from .base import LLMProvider
from .mock import MockProvider


def build_provider(settings: Settings) -> LLMProvider:
    if settings.use_mock:
        return MockProvider()
    from .bedrock import BedrockProvider

    return BedrockProvider(settings.bedrock_model_id, settings.aws_region,
                           token=settings.bedrock_token, max_tokens=settings.bedrock_max_tokens)

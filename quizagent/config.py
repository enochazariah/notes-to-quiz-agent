"""Settings from Streamlit secrets, environment variables, or local .env."""
from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Mapping

PLACEHOLDER_PREFIX = "PASTE_"
DEFAULT_REGION = "us-east-1"
# Example model ID taken from AWS's own Bedrock API-key docs. It is a cross-region
# inference profile ("us." prefix). Use the prefix that matches your region (us., eu., apac.,
# global.), or run scripts/check_bedrock.py to list what your account can use.
DEFAULT_MODEL_ID = "us.anthropic.claude-sonnet-4-6"
_BEDROCK_SETTINGS = ("AWS_BEARER_TOKEN_BEDROCK", "AWS_REGION", "BEDROCK_MODEL_ID")


def _int(env: Mapping[str, str], name: str, default: int) -> int:
    try:
        return int(str(env.get(name, default)).strip())
    except (TypeError, ValueError):
        return default


def _str(env: Mapping[str, str], name: str, default: str = "") -> str:
    return (env.get(name) or "").strip() or default


def _streamlit_bedrock_settings() -> Mapping[str, str]:
    import streamlit as st
    from streamlit.errors import StreamlitSecretNotFoundError

    try:
        return {name: st.secrets[name] for name in _BEDROCK_SETTINGS if name in st.secrets}
    except StreamlitSecretNotFoundError:
        return {}


@dataclass(frozen=True)
class Settings:
    bedrock_token: str = ""
    aws_region: str = DEFAULT_REGION
    bedrock_model_id: str = DEFAULT_MODEL_ID
    bedrock_max_tokens: int = 4096
    access_code: str = ""
    demo_mode: bool = False
    max_pdf_mb: int = 25
    max_pdf_pages: int = 60
    max_builds_per_session: int = 5
    max_daily_builds: int = 100

    @property
    def has_real_key(self) -> bool:
        token = self.bedrock_token.strip()
        return bool(token) and not token.upper().startswith(PLACEHOLDER_PREFIX)

    @property
    def use_mock(self) -> bool:
        return self.demo_mode or not self.has_real_key


def load_settings(env: Mapping[str, str] | None = None) -> Settings:
    """Load settings; Streamlit secrets override environment and .env values.

    An explicit mapping is used as-is, which keeps tests and other callers isolated.
    """
    if env is None:
        from dotenv import load_dotenv

        load_dotenv()  # real environment variables (Render) win over .env
        merged_env = dict(os.environ)
        merged_env.update(_streamlit_bedrock_settings())
        env = merged_env
    return Settings(
        bedrock_token=_str(env, "AWS_BEARER_TOKEN_BEDROCK"),
        aws_region=_str(env, "AWS_REGION") or _str(env, "AWS_DEFAULT_REGION") or DEFAULT_REGION,
        bedrock_model_id=_str(env, "BEDROCK_MODEL_ID", DEFAULT_MODEL_ID),
        bedrock_max_tokens=_int(env, "BEDROCK_MAX_TOKENS", 4096),
        access_code=_str(env, "ACCESS_CODE"),
        demo_mode=_str(env, "DEMO_MODE").lower() in {"1", "true", "yes"},
        max_pdf_mb=_int(env, "MAX_PDF_MB", 25),
        max_pdf_pages=_int(env, "MAX_PDF_PAGES", 60),
        max_builds_per_session=_int(env, "MAX_BUILDS_PER_SESSION", 5),
        max_daily_builds=_int(env, "MAX_DAILY_BUILDS", 100),
    )

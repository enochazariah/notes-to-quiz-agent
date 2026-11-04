"""Check your Bedrock setup without starting the app.

Run from the project folder:   python scripts/check_bedrock.py
It reads .env, lists models your account can see (best effort), and makes one small live call
to prove structured output works. It never prints the token."""
from __future__ import annotations

import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from pydantic import BaseModel  # noqa: E402

from quizagent.config import load_settings  # noqa: E402
from quizagent.providers.base import ProviderError  # noqa: E402
from quizagent.providers.factory import build_provider  # noqa: E402


class Ping(BaseModel):
    answer: str


def main() -> int:
    s = load_settings()
    print(f"Region:   {s.aws_region}")
    print(f"Model ID: {s.bedrock_model_id}")
    if not s.has_real_key:
        print("Token:    NOT SET (still the placeholder). Edit .env first.")
        return 1
    print(f"Token:    set ({len(s.bedrock_token)} characters, value hidden)")

    try:
        import boto3

        os.environ["AWS_BEARER_TOKEN_BEDROCK"] = s.bedrock_token
        control = boto3.client("bedrock", region_name=s.aws_region)
        ids = sorted(m["modelId"] for m in control.list_foundation_models(byOutputModality="TEXT")["modelSummaries"]
                     if m["modelId"].startswith(("anthropic.", "amazon.nova")))
        print("\nClaude/Nova models visible in this region:")
        print("\n".join(f"  {i}" for i in ids[:25]) or "  (none listed)")
        profiles = sorted(p["inferenceProfileId"] for p in control.list_inference_profiles()["inferenceProfileSummaries"]
                          if any(k in p["inferenceProfileId"] for k in ("anthropic", "nova")))
        print("\nInference profiles (use these IDs for newer models):")
        print("\n".join(f"  {i}" for i in profiles[:25]) or "  (none listed)")
    except Exception as exc:  # noqa: BLE001
        print(f"\nCould not list models ({type(exc).__name__}). Skipping the list; testing the model directly.")

    print("\nCalling the model once with structured output...")
    try:
        out = build_provider(s).generate(task="ping", schema=Ping, prompt="Call the tool with answer set to the word ready.")
    except ProviderError as exc:
        print(f"FAILED: {exc}")
        return 1
    print(f"OK: the model answered {out.answer!r}. Your setup works.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

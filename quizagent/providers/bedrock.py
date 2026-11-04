"""Amazon Bedrock provider (Converse API).

Auth: boto3 reads the Bedrock API key from the AWS_BEARER_TOKEN_BEDROCK environment variable.
Nothing in this file ever logs, prints or returns the token.

Structured output: the Pydantic schema is sent as a single tool and the model is forced to call
it (works with Anthropic Claude and Amazon Nova models). If a model rejects forced tool choice,
the provider falls back to asking for plain JSON and parses it.
"""
from __future__ import annotations

import json
import os
import re
from typing import Any

from botocore.exceptions import BotoCoreError, ClientError, ConnectTimeoutError, EndpointConnectionError, NoCredentialsError, NoRegionError, ReadTimeoutError

from ..pdf_input import SourceMaterial
from ..prompts import SYSTEM_PROMPT
from .base import LLMProvider, ProviderError, T

TOOL_NAME = "submit_result"
_SYSTEM = SYSTEM_PROMPT + f"\nDeliver your answer by calling the {TOOL_NAME} tool."

_CRED_CODES = {"AccessDeniedException", "UnrecognizedClientException", "ExpiredTokenException",
               "InvalidSignatureException", "InvalidClientTokenId", "UnauthorizedException"}
_BUSY_CODES = {"ThrottlingException", "TooManyRequestsException", "ServiceQuotaExceededException"}
_TEMP_CODES = {"ModelTimeoutException", "ServiceUnavailableException", "InternalServerException",
               "ModelNotReadyException", "RequestTimeout"}


def tool_schema(model_cls: type[T]) -> dict[str, Any]:
    """Pydantic JSON schema with $ref/$defs inlined and schema 'title' keywords removed."""
    full = model_cls.model_json_schema()
    defs = full.get("$defs", {})

    def walk(node: Any) -> Any:
        if isinstance(node, dict):
            if "$ref" in node:
                return walk(defs[node["$ref"].split("/")[-1]])
            return {k: walk(v) for k, v in node.items()
                    if k != "$defs" and not (k == "title" and isinstance(v, str))}  # keep fields NAMED title
        if isinstance(node, list):
            return [walk(x) for x in node]
        return node

    return walk({k: v for k, v in full.items() if k != "$defs"})


def _coerce(node: Any) -> Any:
    """Some models return nested lists/objects as JSON-encoded strings; decode them."""
    if isinstance(node, dict):
        return {k: _coerce(v) for k, v in node.items()}
    if isinstance(node, list):
        return [_coerce(x) for x in node]
    if isinstance(node, str) and node.strip()[:1] in ("[", "{"):
        try:
            return _coerce(json.loads(node))
        except ValueError:
            return node
    return node


def _extract_json(text: str) -> Any:
    text = re.sub(r"^```(?:json)?|```$", "", text.strip(), flags=re.M).strip()
    start, end = text.find("{"), text.rfind("}")
    if start == -1 or end <= start:
        raise ValueError("no JSON object in the model's answer")
    return json.loads(text[start:end + 1])


class BedrockProvider(LLMProvider):
    name = "bedrock"

    def __init__(self, model_id: str, region: str, *, token: str | None = None, max_tokens: int = 4096,
                 temperature: float = 0.3, client: Any = None):
        self.model_id = model_id
        self.region = region
        self.max_tokens = max_tokens
        self.temperature = temperature
        self._mode = "tool"
        if client is None:
            import boto3
            from botocore.config import Config

            if token:  # boto3 reads the key from this variable; strip stray whitespace from pasted values
                os.environ["AWS_BEARER_TOKEN_BEDROCK"] = token.strip()
            client = boto3.client(
                "bedrock-runtime", region_name=region,
                config=Config(retries={"max_attempts": 4, "mode": "adaptive"}, connect_timeout=10, read_timeout=120),
            )
        self._client = client

    # ---------- public API ----------
    def generate(self, *, task: str, schema: type[T], prompt: str,
                 source: SourceMaterial | None = None, params: dict[str, Any] | None = None) -> T:
        blocks: list[dict[str, str]] = []
        if source is not None and source.text:
            blocks.append({"text": "NOTES:\n" + source.text})
        last_problem = ""
        for attempt in range(2):
            text = prompt if attempt == 0 else (
                f"{prompt}\n\nYour previous answer was rejected ({last_problem}). Return a complete, valid answer.")
            try:
                raw = self._converse(blocks + [{"text": text}], schema)
                try:
                    return schema.model_validate(raw)
                except ValueError:
                    return schema.model_validate(_coerce(raw))
            except ValueError as exc:  # pydantic ValidationError and JSON errors
                last_problem = str(exc).splitlines()[0][:160]
        raise ProviderError("The AI answered in an unexpected format. Please try again.")

    # ---------- internals ----------
    def _converse(self, blocks: list[dict[str, str]], schema: type[T]) -> Any:
        js = tool_schema(schema)
        content = [dict(b) for b in blocks]
        kwargs: dict[str, Any] = {
            "modelId": self.model_id,
            "system": [{"text": _SYSTEM}],
            "inferenceConfig": {"maxTokens": self.max_tokens, "temperature": self.temperature},
        }
        if self._mode == "tool":
            kwargs["toolConfig"] = {
                "tools": [{"toolSpec": {"name": TOOL_NAME, "description": "Return the final structured result.",
                                        "inputSchema": {"json": js}}}],
                "toolChoice": {"tool": {"name": TOOL_NAME}},
            }
        else:
            content[-1]["text"] += ("\n\nReturn ONLY a JSON object, with no other text, that matches this JSON schema:\n"
                                    + json.dumps(js))
        kwargs["messages"] = [{"role": "user", "content": content}]

        try:
            resp = self._client.converse(**kwargs)
        except ClientError as exc:
            if self._mode == "tool" and self._tool_choice_unsupported(exc):
                self._mode = "json"
                return self._converse(blocks, schema)
            raise self._friendly(exc) from None
        except (NoCredentialsError, NoRegionError, EndpointConnectionError, ConnectTimeoutError,
                ReadTimeoutError, BotoCoreError) as exc:
            raise self._friendly_core(exc) from None

        if resp.get("stopReason") == "max_tokens":
            raise ProviderError("The AI's answer was cut off. Try fewer questions, or set a larger BEDROCK_MAX_TOKENS.")
        parts = resp.get("output", {}).get("message", {}).get("content", [])
        for part in parts:
            if "toolUse" in part:
                return part["toolUse"]["input"]
        return _extract_json("".join(p.get("text", "") for p in parts))

    @staticmethod
    def _tool_choice_unsupported(exc: ClientError) -> bool:
        err = exc.response.get("Error", {})
        low = err.get("Message", "").lower()
        return err.get("Code") == "ValidationException" and ("toolchoice" in low or "tool choice" in low or "tool_choice" in low)

    def _friendly(self, exc: ClientError) -> ProviderError:
        err = exc.response.get("Error", {})
        code, low = err.get("Code", ""), err.get("Message", "").lower()
        if code in _CRED_CODES:
            return ProviderError(
                "Bedrock refused the request. Check that AWS_BEARER_TOKEN_BEDROCK is correct and not expired, "
                f"and that this key's account can use the model in {self.region}.")
        if code == "ResourceNotFoundException" or (code == "ValidationException" and any(
                k in low for k in ("model identifier", "model id", "inference profile", "on-demand throughput"))):
            return ProviderError(
                f"The model '{self.model_id}' isn't available in {self.region} for this account. Set BEDROCK_MODEL_ID "
                "to a model or inference-profile ID your region offers (run scripts/check_bedrock.py to list them).")
        if code in _BUSY_CODES:
            return ProviderError("Bedrock is rate-limiting requests right now. Wait a minute and try again.")
        if code in _TEMP_CODES:
            return ProviderError("Bedrock had a temporary problem. Please try again in a moment.")
        return ProviderError(f"Bedrock returned an error ({code or 'unknown'}). Please try again.")

    def _friendly_core(self, exc: BotoCoreError) -> ProviderError:
        if isinstance(exc, NoCredentialsError):
            return ProviderError("No Bedrock token found. Set AWS_BEARER_TOKEN_BEDROCK.")
        if isinstance(exc, NoRegionError):
            return ProviderError("No AWS region set. Set AWS_REGION, for example us-east-1.")
        if isinstance(exc, (EndpointConnectionError, ConnectTimeoutError, ReadTimeoutError)):
            return ProviderError(f"Couldn't reach Bedrock in {self.region}. Check your connection and AWS_REGION.")
        return ProviderError(f"Couldn't call Bedrock ({type(exc).__name__}). Please try again.")

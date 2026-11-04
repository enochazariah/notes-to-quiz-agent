import json
import os
import unittest
from unittest import mock

from botocore.exceptions import ClientError, EndpointConnectionError, NoCredentialsError, NoRegionError

from quizagent.providers.base import ProviderError
from quizagent.providers.bedrock import BedrockProvider, TOOL_NAME, _coerce, tool_schema
from quizagent.schemas import ConceptMap, MCQBatch, TheoryBatch
from tests.helpers import sample_source

SECRET = "SECRET-TOKEN-999"


def tool_reply(payload, stop="tool_use"):
    return {"output": {"message": {"role": "assistant", "content": [
        {"toolUse": {"toolUseId": "t", "name": TOOL_NAME, "input": payload}}]}}, "stopReason": stop}


def text_reply(text, stop="end_turn"):
    return {"output": {"message": {"role": "assistant", "content": [{"text": text}]}}, "stopReason": stop}


def client_error(code, message="boom"):
    return ClientError({"Error": {"Code": code, "Message": message}}, "Converse")


class FakeClient:
    def __init__(self, outcomes):
        self.outcomes, self.calls = list(outcomes), []

    def converse(self, **kwargs):
        self.calls.append(kwargs)
        out = self.outcomes.pop(0)
        if isinstance(out, Exception):
            raise out
        return out


EMPTY_BATCH = {"questions": []}
MAP = {"main_topic": "T", "subtopics": [{"title": "A", "summary": "s", "key_points": ["k"]}]}


def provider(outcomes):
    client = FakeClient(outcomes)
    return BedrockProvider("test-model", "us-east-1", client=client), client


class SchemaTests(unittest.TestCase):
    def test_refs_and_defs_are_inlined(self):
        for cls in (ConceptMap, MCQBatch, TheoryBatch):
            text = json.dumps(tool_schema(cls))
            self.assertNotIn("$ref", text)
            self.assertNotIn("$defs", text)

    def test_field_named_title_survives(self):
        props = tool_schema(ConceptMap)["properties"]["subtopics"]["items"]["properties"]
        self.assertIn("title", props)

    def test_coerce_decodes_stringified_json(self):
        fixed = _coerce({"questions": json.dumps([{"a": 1}]), "name": "plain", "note": "[not json"})
        self.assertEqual(fixed["questions"], [{"a": 1}])
        self.assertEqual((fixed["name"], fixed["note"]), ("plain", "[not json"))


class GenerateTests(unittest.TestCase):
    def test_forced_tool_request_shape(self):
        p, c = provider([tool_reply(MAP)])
        out = p.generate(task="t", schema=ConceptMap, prompt="PROMPT", source=sample_source())
        self.assertEqual(out.main_topic, "T")
        call = c.calls[0]
        self.assertEqual(call["modelId"], "test-model")
        self.assertEqual(call["toolConfig"]["toolChoice"], {"tool": {"name": TOOL_NAME}})
        self.assertIn("system", call)
        blocks = call["messages"][0]["content"]
        self.assertTrue(blocks[0]["text"].startswith("NOTES:\n"))
        self.assertEqual(blocks[-1]["text"], "PROMPT")
        self.assertEqual(call["inferenceConfig"]["maxTokens"], 4096)

    def test_stringified_nested_output_is_repaired(self):
        p, _ = provider([tool_reply({"questions": json.dumps([])})])
        self.assertEqual(p.generate(task="t", schema=MCQBatch, prompt="x").questions, [])

    def test_invalid_output_retries_once_then_succeeds(self):
        p, c = provider([tool_reply({"wrong": 1}), tool_reply(EMPTY_BATCH)])
        self.assertEqual(p.generate(task="t", schema=MCQBatch, prompt="x").questions, [])
        self.assertIn("rejected", c.calls[1]["messages"][0]["content"][-1]["text"])

    def test_invalid_twice_gives_friendly_error(self):
        p, _ = provider([tool_reply({"wrong": 1}), tool_reply({"wrong": 2})])
        with self.assertRaises(ProviderError) as ctx:
            p.generate(task="t", schema=MCQBatch, prompt="x")
        self.assertIn("unexpected format", str(ctx.exception))

    def test_falls_back_to_json_when_tool_choice_unsupported(self):
        p, c = provider([client_error("ValidationException", "This model doesn't support the toolChoice.tool field"),
                         text_reply("```json\n" + json.dumps(EMPTY_BATCH) + "\n```")])
        self.assertEqual(p.generate(task="t", schema=MCQBatch, prompt="x").questions, [])
        self.assertNotIn("toolConfig", c.calls[1])
        self.assertIn("JSON schema", c.calls[1]["messages"][0]["content"][-1]["text"])
        self.assertEqual(p._mode, "json")

    def test_text_json_accepted_when_model_skips_the_tool(self):
        p, _ = provider([text_reply(json.dumps(EMPTY_BATCH))])
        self.assertEqual(p.generate(task="t", schema=MCQBatch, prompt="x").questions, [])

    def test_cut_off_answer_is_reported(self):
        p, _ = provider([tool_reply(EMPTY_BATCH, stop="max_tokens")])
        with self.assertRaises(ProviderError) as ctx:
            p.generate(task="t", schema=MCQBatch, prompt="x")
        self.assertIn("cut off", str(ctx.exception))


class ErrorMappingTests(unittest.TestCase):
    def message_for(self, exc):
        p, _ = provider([exc])
        with self.assertRaises(ProviderError) as ctx:
            p.generate(task="t", schema=MCQBatch, prompt="x")
        return str(ctx.exception)

    def test_credentials_problem_is_actionable(self):
        for code in ("AccessDeniedException", "UnrecognizedClientException", "ExpiredTokenException"):
            msg = self.message_for(client_error(code, f"bad token {SECRET}"))
            self.assertIn("AWS_BEARER_TOKEN_BEDROCK", msg)

    def test_wrong_model_id_names_the_model_and_the_fix(self):
        for exc in (client_error("ValidationException", "The provided model identifier is invalid."),
                    client_error("ValidationException", "Invocation of model ID x with on-demand throughput isn't supported"),
                    client_error("ResourceNotFoundException", "not found")):
            msg = self.message_for(exc)
            self.assertIn("test-model", msg)
            self.assertIn("BEDROCK_MODEL_ID", msg)

    def test_busy_and_temporary(self):
        self.assertIn("rate-limiting", self.message_for(client_error("ThrottlingException")))
        self.assertIn("temporary", self.message_for(client_error("ModelTimeoutException")))

    def test_config_and_network_errors(self):
        self.assertIn("AWS_BEARER_TOKEN_BEDROCK", self.message_for(NoCredentialsError()))
        self.assertIn("AWS_REGION", self.message_for(NoRegionError()))
        self.assertIn("us-east-1", self.message_for(EndpointConnectionError(endpoint_url="https://x")))

    def test_no_message_ever_contains_the_secret(self):
        for exc in (client_error("AccessDeniedException", SECRET), client_error("ValidationException", SECRET),
                    client_error("WeirdException", SECRET), client_error("ThrottlingException", SECRET)):
            self.assertNotIn(SECRET, self.message_for(exc))

    def test_unknown_error_shows_only_the_code(self):
        self.assertIn("WeirdException", self.message_for(client_error("WeirdException", "internal detail")))


class TokenEnvTests(unittest.TestCase):
    def test_token_is_exported_trimmed_for_boto3(self):
        with mock.patch.dict(os.environ, {}, clear=False):
            BedrockProvider("m", "us-east-1", token=" ABSK-test \n")
            self.assertEqual(os.environ["AWS_BEARER_TOKEN_BEDROCK"], "ABSK-test")


if __name__ == "__main__":
    unittest.main()

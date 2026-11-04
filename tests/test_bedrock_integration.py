"""Runs the REAL boto3 client (real bearer-token auth path) against a loopback fake of Bedrock.
Proves request building, auth header, parsing and the full quiz pipeline. Does NOT prove that real
AWS accepts a given model, region or schema; that needs a live key (scripts/check_bedrock.py)."""
import os
import unittest
from unittest import mock

from quizagent.agent import QuizAgent, make_report
from quizagent.config import load_settings
from quizagent.providers.base import ProviderError
from quizagent.providers.factory import build_provider
from quizagent.schemas import ConceptMap
from tests import fake_bedrock as fb
from tests.helpers import sample_source


class BedrockLoopbackTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server, cls.port = fb.start()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()

    def setUp(self):
        fb.State.mode, fb.State.log = "ok", []
        self.env = mock.patch.dict(os.environ, {
            "AWS_ENDPOINT_URL_BEDROCK_RUNTIME": f"http://127.0.0.1:{self.port}",
            "AWS_EC2_METADATA_DISABLED": "true", "AWS_REGION": "us-east-1",
            "AWS_BEARER_TOKEN_BEDROCK": "PASTE_placeholder"})
        self.env.start()
        self.settings = load_settings({"AWS_BEARER_TOKEN_BEDROCK": " FAKE-TOKEN-123 \n", "AWS_REGION": "us-east-1",
                                       "BEDROCK_MODEL_ID": "us.test.model:0"})
        self.provider = build_provider(self.settings)

    def tearDown(self):
        self.env.stop()

    def test_factory_picks_bedrock_for_a_real_token(self):
        self.assertEqual(self.provider.name, "bedrock")
        self.assertEqual(build_provider(load_settings({})).name, "mock")

    def test_bearer_token_is_sent_trimmed_and_without_sigv4(self):
        self.provider.generate(task="concept_map", schema=ConceptMap, prompt="break them into a concept map", source=sample_source())
        req = fb.State.log[0]
        self.assertEqual(req["auth"], "Bearer FAKE-TOKEN-123")
        self.assertNotIn("AWS4-HMAC", req["auth"])
        self.assertEqual(req["path"], "/model/us.test.model:0/converse")
        self.assertEqual(req["body"]["toolConfig"]["toolChoice"]["tool"]["name"], "submit_result")

    def test_full_quiz_pipeline_through_real_boto3(self):
        agent = QuizAgent(self.provider, seed=1)
        src = sample_source()
        cmap = agent.analyze(src)
        quiz = agent.build_quiz(src, cmap, 10, 20)
        self.assertEqual(len(quiz.mcqs), 10)
        self.assertEqual(sum(t.total_marks for t in quiz.theory), 20)
        grades = [agent.grade_theory(t, "an answer") for t in quiz.theory]
        report = make_report(quiz.mcqs, [q.correct_index for q in quiz.mcqs], grades)
        self.assertEqual(report.percent, 100)
        self.assertEqual(agent.feedback(report, "playful").headline, "Fake headline")
        self.assertTrue(all(r["auth"] == "Bearer FAKE-TOKEN-123" for r in fb.State.log))

    def test_stringified_nested_json_is_repaired(self):
        fb.State.mode = "stringified"
        agent = QuizAgent(self.provider)
        self.assertGreaterEqual(len(agent.analyze(sample_source()).subtopics), 1)

    def test_model_without_forced_tools_falls_back_to_json(self):
        fb.State.mode = "tool_unsupported"
        agent = QuizAgent(self.provider)
        self.assertGreaterEqual(len(agent.analyze(sample_source()).subtopics), 1)
        self.assertTrue(any("toolConfig" not in r["body"] for r in fb.State.log))

    def test_credential_error_is_friendly_and_leaks_nothing(self):
        fb.State.mode = "403"
        with self.assertRaises(ProviderError) as ctx:
            QuizAgent(self.provider).analyze(sample_source())
        self.assertIn("AWS_BEARER_TOKEN_BEDROCK", str(ctx.exception))
        self.assertNotIn("SECRET-TOKEN-999", str(ctx.exception))
        self.assertNotIn("FAKE-TOKEN-123", str(ctx.exception))

    def test_wrong_model_id_is_friendly(self):
        fb.State.mode = "400_model"
        with self.assertRaises(ProviderError) as ctx:
            QuizAgent(self.provider).analyze(sample_source())
        self.assertIn("us.test.model:0", str(ctx.exception))
        self.assertIn("BEDROCK_MODEL_ID", str(ctx.exception))

    def test_truncated_answer_is_reported(self):
        fb.State.mode = "max_tokens"
        with self.assertRaises(ProviderError) as ctx:
            QuizAgent(self.provider).analyze(sample_source())
        self.assertIn("cut off", str(ctx.exception))


if __name__ == "__main__":
    unittest.main()

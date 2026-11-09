import io
import os
import unittest
from datetime import date, timedelta
from unittest.mock import patch

from pypdf import PdfReader, PdfWriter

from quizagent.config import DEFAULT_MODEL_ID, DEFAULT_REGION, load_settings
from quizagent.pdf_input import PdfError, load_pdf
from quizagent.usage import DailyCounter
from tests.helpers import SAMPLE_TEXT, make_pdf

LINES = [s.strip() + "." for s in SAMPLE_TEXT.split(".") if s.strip()]


class ConfigTests(unittest.TestCase):
    def test_placeholder_token_means_demo_mode(self):
        s = load_settings({"AWS_BEARER_TOKEN_BEDROCK": "PASTE_YOUR_BEDROCK_API_KEY_HERE"})
        self.assertFalse(s.has_real_key)
        self.assertTrue(s.use_mock)

    def test_missing_token_means_demo_mode(self):
        self.assertTrue(load_settings({}).use_mock)

    def test_real_token_uses_bedrock(self):
        s = load_settings({"AWS_BEARER_TOKEN_BEDROCK": "ABSKexample"})
        self.assertTrue(s.has_real_key)
        self.assertFalse(s.use_mock)

    def test_demo_flag_forces_mock(self):
        self.assertTrue(load_settings({"AWS_BEARER_TOKEN_BEDROCK": "ABSKexample", "DEMO_MODE": "1"}).use_mock)

    def test_whitespace_is_trimmed_everywhere(self):
        s = load_settings({"AWS_BEARER_TOKEN_BEDROCK": " ABSKexample \n", "AWS_REGION": " eu-west-1 ",
                           "BEDROCK_MODEL_ID": " eu.amazon.nova-lite-v1:0 ", "ACCESS_CODE": " code "})
        self.assertEqual((s.bedrock_token, s.aws_region, s.bedrock_model_id, s.access_code),
                         ("ABSKexample", "eu-west-1", "eu.amazon.nova-lite-v1:0", "code"))

    def test_defaults_and_region_fallbacks(self):
        s = load_settings({})
        self.assertEqual((s.aws_region, s.bedrock_model_id, s.max_pdf_mb), (DEFAULT_REGION, DEFAULT_MODEL_ID, 25))
        self.assertEqual(load_settings({"AWS_DEFAULT_REGION": "af-south-1"}).aws_region, "af-south-1")
        self.assertEqual(load_settings({"AWS_REGION": "", "AWS_DEFAULT_REGION": ""}).aws_region, DEFAULT_REGION)

    def test_streamlit_bedrock_secrets_override_process_environment(self):
        secrets = {
            "AWS_BEARER_TOKEN_BEDROCK": "cloud-test-token",
            "AWS_REGION": "eu-north-1",
            "BEDROCK_MODEL_ID": "eu.test-model",
        }
        environment = {
            "AWS_BEARER_TOKEN_BEDROCK": "environment-test-token",
            "AWS_REGION": "us-east-1",
            "BEDROCK_MODEL_ID": "us.test-model",
        }
        with patch("dotenv.load_dotenv"), patch.dict(os.environ, environment, clear=True), \
                patch("quizagent.config._streamlit_bedrock_settings", return_value=secrets):
            settings = load_settings()
        self.assertTrue(settings.bedrock_token == secrets["AWS_BEARER_TOKEN_BEDROCK"])
        self.assertEqual((settings.aws_region, settings.bedrock_model_id),
                         (secrets["AWS_REGION"], secrets["BEDROCK_MODEL_ID"]))

    def test_process_environment_fills_streamlit_secret_gaps(self):
        environment = {
            "AWS_BEARER_TOKEN_BEDROCK": "environment-test-token",
            "AWS_REGION": "us-east-1",
            "BEDROCK_MODEL_ID": "us.test-model",
        }
        with patch("dotenv.load_dotenv"), patch.dict(os.environ, environment, clear=True), \
                patch("quizagent.config._streamlit_bedrock_settings",
                      return_value={"AWS_REGION": "eu-north-1"}):
            settings = load_settings()
        self.assertTrue(settings.bedrock_token == environment["AWS_BEARER_TOKEN_BEDROCK"])
        self.assertEqual((settings.aws_region, settings.bedrock_model_id),
                         ("eu-north-1", environment["BEDROCK_MODEL_ID"]))

    def test_bad_int_falls_back(self):
        self.assertEqual(load_settings({"MAX_PDF_MB": "abc"}).max_pdf_mb, 25)


class CounterTests(unittest.TestCase):
    def test_limit_and_rollover(self):
        day = [date(2026, 10, 31)]
        c = DailyCounter(2, today=lambda: day[0])
        self.assertTrue(c.try_consume())
        self.assertTrue(c.try_consume())
        self.assertFalse(c.try_consume())
        day[0] += timedelta(days=1)
        self.assertTrue(c.try_consume())


def encrypt(pdf: bytes, user: str, algorithm: str) -> bytes:
    writer = PdfWriter(clone_from=io.BytesIO(pdf))
    writer.encrypt(user_password=user, owner_password="owner", algorithm=algorithm)
    out = io.BytesIO()
    writer.write(out)
    return out.getvalue()


class PdfTests(unittest.TestCase):
    def test_text_pdf_is_read(self):
        src = load_pdf(make_pdf([LINES]), "n.pdf")
        self.assertIn("chloroplast", src.text.lower())
        self.assertEqual(src.page_count, 1)

    def test_scan_or_tiny_text_is_rejected_with_clear_message(self):
        with self.assertRaises(PdfError) as ctx:
            load_pdf(make_pdf([["Hi"]]), "scan.pdf")
        self.assertIn("text-based PDF", str(ctx.exception))

    def test_rejects_non_pdf(self):
        with self.assertRaises(PdfError):
            load_pdf(b"hello", "x.pdf")

    def test_rejects_over_size_limit(self):
        with self.assertRaises(PdfError) as ctx:
            load_pdf(b"%PDF" + b"0" * (2 * 1024 * 1024), "x.pdf", max_mb=1)
        self.assertIn("1 MB", str(ctx.exception))

    def test_25mb_default_limit(self):
        with self.assertRaises(PdfError) as ctx:
            load_pdf(b"%PDF" + b"0" * (26 * 1024 * 1024), "x.pdf")
        self.assertIn("25 MB", str(ctx.exception))

    def test_rejects_too_many_pages(self):
        with self.assertRaises(PdfError):
            load_pdf(make_pdf([["a"]] * 3), "x.pdf", max_pages=2)

    def test_corrupt_pdf(self):
        with self.assertRaises(PdfError):
            load_pdf(b"%PDF-1.4 garbage garbage", "x.pdf")

    def test_owner_password_only_pdf_still_opens(self):
        for algo in ("RC4-128", "AES-128", "AES-256"):
            with self.subTest(algo=algo):
                src = load_pdf(encrypt(make_pdf([LINES]), "", algo), "n.pdf")
                self.assertIn("chloroplast", src.text.lower())

    def test_user_password_pdf_is_rejected(self):
        with self.assertRaises(PdfError) as ctx:
            load_pdf(encrypt(make_pdf([LINES]), "secret", "AES-256"), "n.pdf")
        self.assertIn("password", str(ctx.exception))


if __name__ == "__main__":
    unittest.main()

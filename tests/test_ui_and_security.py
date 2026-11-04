import re
import unittest
from pathlib import Path

from quizagent import ui_theme as ui

ROOT = Path(__file__).resolve().parent.parent
SKIP_DIRS = {".git", "__pycache__", ".venv", "node_modules"}


def project_files():
    for p in ROOT.rglob("*"):
        if p.is_file() and not (set(p.parts) & SKIP_DIRS):
            yield p


class UiHelperTests(unittest.TestCase):
    EVIL = '<script>alert(1)</script>"><img src=x onerror=alert(2)>'

    def test_ai_text_is_escaped_everywhere_it_enters_html(self):
        for html in (ui.topic(self.EVIL), ui.chips([self.EVIL]), ui.question_meta(self.EVIL, self.EVIL, 5),
                     ui.score_card(55, self.EVIL, self.EVIL), ui.list_card(self.EVIL, [self.EVIL]),
                     ui.hero(self.EVIL, True)):
            self.assertNotIn("<script", html)
            self.assertNotIn("<img", html)

    def test_markup_has_no_blank_lines_or_code_block_indents(self):
        for html in (ui.hero("x", False), ui.stepper(2), ui.score_card(90, "a", "b"), ui.list_card("t", ["a"])):
            self.assertNotIn("\n\n", html)
            self.assertFalse(any(line.startswith("    ") for line in html.splitlines()))

    def test_stepper_marks_progress(self):
        html = ui.stepper(2)
        self.assertEqual((html.count("nq-step done"), html.count("nq-step on")), (1, 1))

    def test_score_tone_thresholds(self):
        self.assertEqual([ui.tone_for(p) for p in (95, 80, 79, 50, 49, 0)],
                         ["var(--ok)", "var(--ok)", "var(--pen)", "var(--pen)", "var(--bad)", "var(--bad)"])


class SecurityTests(unittest.TestCase):
    PATTERNS = [r"ABSK[A-Za-z0-9+/=]{20,}", r"bedrock-api-key-[A-Za-z0-9+/=]{20,}", r"AKIA[0-9A-Z]{16}",
                r"-----BEGIN [A-Z ]*PRIVATE KEY-----", r"aws_secret_access_key\s*=\s*\S{20,}"]

    def test_no_secret_shaped_strings_in_shipped_files(self):
        for p in project_files():
            if p.name == ".env" or p.suffix in {".pyc", ".pdf"}:
                continue  # .env is the user's own local file
            text = p.read_text(errors="ignore")
            for pat in self.PATTERNS:
                self.assertIsNone(re.search(pat, text), f"secret-like string in {p.relative_to(ROOT)}")

    def test_env_files_are_git_ignored_but_example_is_not(self):
        lines = (ROOT / ".gitignore").read_text().splitlines()
        self.assertIn(".env", lines)
        self.assertIn(".env.*", lines)
        self.assertIn("!.env.example", lines)

    def test_example_env_has_only_placeholders(self):
        env = dict(l.split("=", 1) for l in (ROOT / ".env.example").read_text().splitlines()
                   if "=" in l and not l.startswith("#"))
        self.assertTrue(env["AWS_BEARER_TOKEN_BEDROCK"].startswith("PASTE_"))
        for name in ("AWS_REGION", "BEDROCK_MODEL_ID"):
            self.assertIn(name, env)

    def test_render_yaml_keeps_the_token_out_of_the_file(self):
        text = (ROOT / "render.yaml").read_text()
        block = text[text.index("AWS_BEARER_TOKEN_BEDROCK"):].split("- key:")[0]
        self.assertIn("sync: false", block)
        self.assertNotIn("value:", block)

    def test_code_never_prints_or_logs_the_token(self):
        for p in [ROOT / "app.py", *(ROOT / "quizagent").rglob("*.py")]:
            for n, line in enumerate(p.read_text().splitlines(), 1):
                if "token" in line.lower() and re.search(r"print\(|logging|logger|st\.(write|code|text|info|error|warning|markdown)", line):
                    if "AWS_BEARER_TOKEN_BEDROCK" in line and "st." in line:
                        continue  # error text that only NAMES the variable
                    self.fail(f"{p.name}:{n} may expose the token: {line.strip()}")

    def test_upload_limit_is_25mb_in_both_places(self):
        cfg = (ROOT / ".streamlit" / "config.toml").read_text()
        self.assertIn("maxUploadSize = 25", cfg)
        from quizagent.config import load_settings
        self.assertEqual(load_settings({}).max_pdf_mb, 25)


if __name__ == "__main__":
    unittest.main()

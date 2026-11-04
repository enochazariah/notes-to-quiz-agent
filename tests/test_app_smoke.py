import os
import unittest
from pathlib import Path

APP = str(Path(__file__).resolve().parent.parent / "app.py")


class AppSmokeTest(unittest.TestCase):
    def test_app_loads_in_demo_mode(self):
        os.environ["DEMO_MODE"] = "1"
        os.environ.pop("ACCESS_CODE", None)
        from streamlit.testing.v1 import AppTest

        at = AppTest.from_file(APP, default_timeout=30).run()
        self.assertFalse(at.exception, at.exception)
        self.assertTrue(any("Demo mode" in w.value for w in at.warning))
        self.assertTrue(any("Notes to Quiz" in m.value for m in at.markdown))
        self.assertEqual(len(at.slider), 2)

    def test_access_code_blocks_until_entered(self):
        os.environ["DEMO_MODE"] = "1"
        os.environ["ACCESS_CODE"] = "letmein"
        from streamlit.testing.v1 import AppTest

        try:
            at = AppTest.from_file(APP, default_timeout=30).run()
            self.assertFalse(at.exception, at.exception)
            self.assertEqual(len(at.file_uploader), 0)
            at.text_input[0].set_value("wrong").run()
            self.assertTrue(at.error)
            at.text_input[0].set_value("letmein").run()
            self.assertGreaterEqual(len(at.slider), 1)
        finally:
            os.environ.pop("ACCESS_CODE", None)


if __name__ == "__main__":
    unittest.main()

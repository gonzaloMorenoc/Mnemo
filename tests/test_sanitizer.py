import unittest

from src.sanitizer import build_provenance_metadata, sanitize_text


class SanitizerTests(unittest.TestCase):
    def test_sanitize_text_redacts_common_secrets(self):
        raw = """
        Contact: qa.user@example.com
        URL: https://internal.mycorp.internal/service
        Token: api_key=abc123456789TOKEN
        IP: 10.20.30.40
        Path: /Users/alice/private/project/secrets.env
        """
        sanitized = sanitize_text(raw)
        self.assertIn("[REDACTED_EMAIL]", sanitized)
        self.assertIn("[REDACTED_URL]", sanitized)
        self.assertIn("[REDACTED_SECRET]", sanitized)
        self.assertIn("[REDACTED_IP]", sanitized)
        self.assertIn("[REDACTED_PATH]", sanitized)
        self.assertNotIn("qa.user@example.com", sanitized)

    def test_provenance_metadata_extracts_tags_and_error_type(self):
        text = "Playwright timeout while running node test in kubernetes"
        metadata = build_provenance_metadata(text)
        self.assertIn("playwright", metadata["tech_tags"])
        self.assertIn("node", metadata["tech_tags"])
        self.assertIn("kubernetes", metadata["tech_tags"])
        self.assertEqual(metadata["error_type"], "timeout")


if __name__ == "__main__":
    unittest.main()

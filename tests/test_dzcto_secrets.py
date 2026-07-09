import json
import sys
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "scripts"))

import dzcto  # noqa: E402
from dzcto_common import (  # noqa: E402
    HIGH_CONFIDENCE,
    LOW_CONFIDENCE,
    redact,
    redacted_json_text,
    scan_secrets,
)


GITHUB_TOKEN = "ghp_" + "AbCdEf1234567890AbCdEf1234567890AbCd"
SHORT_GITHUB_TOKEN = "ghp_ABC123def456"
AWS_TOKEN = "AKIAABCDEFGHIJKLMNOP"
LOW_GENERIC_SECRET = "api_key = \"dGhpcy1pcy1hLXZlcnktc2VjcmV0LXRva2Vu\""


class TestSecretScanner(unittest.TestCase):
    def test_provider_prefixes_are_high_confidence(self):
        findings = scan_secrets(f"token={GITHUB_TOKEN} aws={AWS_TOKEN}")
        self.assertEqual([finding.rule for finding in findings], ["github_pat", "aws_access_key"])
        self.assertTrue(all(finding.confidence == HIGH_CONFIDENCE for finding in findings))

    def test_bearer_regression_detects_token_substring(self):
        findings = scan_secrets(f"authorization: Bearer {SHORT_GITHUB_TOKEN}")
        self.assertEqual(len(findings), 1)
        self.assertEqual(findings[0].rule, "github_pat")
        self.assertEqual(findings[0].confidence, HIGH_CONFIDENCE)

    def test_prose_false_positive_corpus_has_no_findings(self):
        examples = [
            "The secret to our success was focus.",
            "Password reset flow is now live.",
            "The authorization model was simplified.",
            "Revenue grew 12% after the secret sauce shipped.",
        ]
        for example in examples:
            with self.subTest(example=example):
                self.assertEqual(scan_secrets(example), [])

    def test_benign_high_entropy_shapes_have_no_findings(self):
        examples = [
            "0123456789abcdef0123456789abcdef01234567",
            "abcdef1",
            "123e4567-e89b-12d3-a456-426614174000",
            "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAAB",
            "[REDACTED:github_pat]",
        ]
        for example in examples:
            with self.subTest(example=example):
                self.assertEqual(scan_secrets(example), [])

    def test_assignment_entropy_gate(self):
        self.assertEqual(scan_secrets('api_key = "aaaaaaaaaaaaaaaaaaaaaa"'), [])
        findings = scan_secrets(LOW_GENERIC_SECRET)
        self.assertEqual(len(findings), 1)
        self.assertEqual(findings[0].rule, "generic_assignment")
        self.assertEqual(findings[0].confidence, LOW_CONFIDENCE)

    def test_empty_single_char_and_boundaries(self):
        self.assertEqual(scan_secrets(""), [])
        self.assertEqual(scan_secrets("x"), [])
        self.assertEqual(scan_secrets(f"x{GITHUB_TOKEN}"), [])

    def test_benign_exclusion_never_suppresses_provider_prefix(self):
        findings = scan_secrets("ghp_" + "a" * 36)
        self.assertEqual(len(findings), 1)
        self.assertEqual(findings[0].rule, "github_pat")
        self.assertEqual(findings[0].confidence, HIGH_CONFIDENCE)


class TestRedaction(unittest.TestCase):
    def test_bearer_token_is_redacted_without_mangling_scheme(self):
        redacted = redact(f"authorization: Bearer {SHORT_GITHUB_TOKEN}")
        self.assertNotIn(SHORT_GITHUB_TOKEN, redacted)
        self.assertIn("authorization: Bearer [REDACTED:github_pat]", redacted)

    def test_prose_survives_byte_intact(self):
        examples = [
            "The secret to our success was focus.",
            "Password reset flow is now live.",
            "The authorization model was simplified.",
            "Revenue grew 12% after the secret sauce shipped.",
        ]
        for example in examples:
            with self.subTest(example=example):
                self.assertEqual(redact(example), example)

    def test_anchored_key_matching(self):
        payload = {
            "tokens_processed": 1234,
            "github_token": "x",
            "openai_api_key": "y",
            "credential_rotation_note": "we rotated keys",
        }
        redacted = redact(payload)
        self.assertEqual(redacted["tokens_processed"], 1234)
        self.assertEqual(redacted["github_token"], "[REDACTED:secret_key]")
        self.assertEqual(redacted["openai_api_key"], "[REDACTED:secret_key]")
        self.assertEqual(redacted["credential_rotation_note"], "[REDACTED:secret_key]")

    def test_idempotence_and_determinism(self):
        examples = [
            f"authorization: Bearer {SHORT_GITHUB_TOKEN}",
            LOW_GENERIC_SECRET,
            {"nested": [f"deploy token {GITHUB_TOKEN}"]},
        ]
        for example in examples:
            with self.subTest(example=example):
                first = redact(example)
                self.assertEqual(redact(first), first)
                self.assertEqual(redact(example), first)

    def test_nested_structures_and_passthrough_values(self):
        payload = {
            "items": [{"note": f"authorization: Bearer {SHORT_GITHUB_TOKEN}"}],
            "projectFolder": "/Users/example/Acme",
            "none": None,
            "count": 3,
            "ok": True,
        }
        redacted = redact(payload)
        self.assertNotIn(SHORT_GITHUB_TOKEN, json.dumps(redacted))
        self.assertEqual(redacted["projectFolder"], "[REDACTED:local_path]")
        self.assertIsNone(redacted["none"])
        self.assertEqual(redacted["count"], 3)
        self.assertIs(redacted["ok"], True)

    def test_redact_never_blocks_on_high_confidence_hit(self):
        try:
            redacted = redact(f"authorization: Bearer {SHORT_GITHUB_TOKEN}")
        except SystemExit:
            self.fail("redact() must not raise SystemExit")
        self.assertNotIn(SHORT_GITHUB_TOKEN, redacted)

    def test_redacted_json_text_contract_and_inherited_consumer(self):
        payload = {"log": f"authorization: Bearer {SHORT_GITHUB_TOKEN}", "b": 1}
        text = redacted_json_text(payload)
        self.assertEqual(text, dzcto.redacted_json_text(payload))
        self.assertTrue(text.endswith("\n"))
        self.assertIn('  "b": 1', text)
        self.assertNotIn(SHORT_GITHUB_TOKEN, text)


if __name__ == "__main__":
    unittest.main()

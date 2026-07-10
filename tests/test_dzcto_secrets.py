import sys
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "scripts"))

from dzcto_common import (  # noqa: E402
    HIGH_CONFIDENCE,
    LOW_CONFIDENCE,
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

if __name__ == "__main__":
    unittest.main()

import unittest

from ci_triage.web import parse_triage_input


class ParseTriageInputTests(unittest.TestCase):
    def test_accepts_manual_log_and_retry_outcomes(self):
        log, attempts = parse_triage_input({
            "log": "AssertionError: expected 4, got 3",
            "attempts": ["failed", "passed", "failed"],
        })

        self.assertEqual(log, "AssertionError: expected 4, got 3")
        self.assertEqual([attempt["status"] for attempt in attempts], ["failed", "passed", "failed"])

    def test_allows_missing_retry_observations(self):
        log, attempts = parse_triage_input({"log": "ModuleNotFoundError: No module named 'yaml'"})

        self.assertTrue(log.startswith("ModuleNotFoundError"))
        self.assertEqual(attempts, [])

    def test_rejects_empty_log(self):
        with self.assertRaisesRegex(ValueError, "Paste a CI log"):
            parse_triage_input({"log": "  ", "attempts": []})

    def test_rejects_unknown_attempt_status(self):
        with self.assertRaisesRegex(ValueError, "Attempt 1"):
            parse_triage_input({"log": "failure", "attempts": ["skipped"]})

    def test_rejects_more_than_twenty_attempts(self):
        with self.assertRaisesRegex(ValueError, "no more than 20"):
            parse_triage_input({"log": "failure", "attempts": ["failed"] * 21})

    def test_rejects_non_object_request(self):
        with self.assertRaisesRegex(ValueError, "JSON object"):
            parse_triage_input(["not", "an", "object"])


if __name__ == "__main__":
    unittest.main()

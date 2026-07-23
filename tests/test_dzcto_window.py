"""Tests for since_last_report window resolution (DAYZEROCTO-12)."""

import datetime as dt
import io
import json
import sys
import tempfile
import unittest
from contextlib import redirect_stderr
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "scripts"))

import dzcto  # noqa: E402


def weekly_report(start: str, end: str, **overrides) -> dict:
    data = {
        "report_type": "weekly",
        "company": "Acme",
        "window": {"start": start, "end": end},
        "headline": "A week happened.",
    }
    data.update(overrides)
    return data


class WindowResolutionTestCase(unittest.TestCase):
    """Fixture artifact folder shaped like a real one: <root>/reports/ceo-updates/*.json."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = Path(self._tmp.name) / "artifacts"
        self.reports = self.root / "reports" / "ceo-updates"
        self.reports.mkdir(parents=True)

    def write_report(self, name: str, data) -> Path:
        path = self.reports / name
        path.write_text(json.dumps(data), encoding="utf-8")
        return path

    def write_weekly(self, end: str, start: str = "2000-01-01") -> Path:
        return self.write_report(f"{end}-ceo-report-{start}-to-{end}.json", weekly_report(start, end))

    def resolve(self, as_of: str):
        """Resolve, capturing stderr so warn-never-fail notes never pollute test output."""
        buffer = io.StringIO()
        with redirect_stderr(buffer):
            result = dzcto.resolve_since_last_report_window(self.root, dt.date.fromisoformat(as_of))
        return result, buffer.getvalue()


class TestCursorSelection(WindowResolutionTestCase):
    def test_newest_weekly_report_is_the_cursor(self):
        self.write_weekly("2026-07-07", "2026-07-01")
        newest = self.write_weekly("2026-07-14", "2026-07-08")

        result, _ = self.resolve("2026-07-23")

        self.assertEqual(result["start"], "2026-07-15")
        self.assertEqual(result["end"], "2026-07-23")
        self.assertEqual(result["days"], 9)
        self.assertFalse(result["empty"])
        self.assertEqual(result["cursor"]["window_end"], "2026-07-14")
        self.assertEqual(result["cursor"]["report"], f"reports/ceo-updates/{newest.name}")

    def test_skipped_cadence_period_self_heals_into_one_long_window(self):
        self.write_weekly("2026-07-02", "2026-06-26")

        result, stderr = self.resolve("2026-07-23")

        # Start 07-03 through 07-23 inclusive is 21 days. The span is deliberately uncapped:
        # a long window after a skipped week is the self-healing behavior, not an anomaly.
        self.assertEqual(result["start"], "2026-07-03")
        self.assertEqual(result["days"], 21)
        self.assertFalse(result["empty"])
        self.assertEqual(stderr, "", "a long self-healed window must not warn")

    def test_ad_hoc_report_with_a_later_window_end_does_not_move_the_cursor(self):
        self.write_weekly("2026-07-14", "2026-07-08")
        self.write_report(
            "2026-07-20-ceo-report-2026-07-15-to-2026-07-20.json",
            weekly_report("2026-07-15", "2026-07-20", report_type="ad_hoc"),
        )

        result, _ = self.resolve("2026-07-23")

        # Coverage is weekly-scoped: an ad_hoc report must not swallow days out of the
        # weekly ritual, even though it is newer.
        self.assertEqual(result["cursor"]["window_end"], "2026-07-14")
        self.assertEqual(result["start"], "2026-07-15")

    def test_legacy_report_without_report_type_is_not_treated_as_weekly(self):
        untyped = weekly_report("2026-07-15", "2026-07-20")
        del untyped["report_type"]
        self.write_report("2026-07-20-ceo-report-2026-07-15-to-2026-07-20.json", untyped)

        result, _ = self.resolve("2026-07-23")

        self.assertIsNone(result["cursor"])
        self.assertIsNone(result["start"])

    def test_data_json_is_excluded_from_cursor_selection(self):
        self.write_report("data.json", weekly_report("2026-07-15", "2026-07-20"))

        result, _ = self.resolve("2026-07-23")

        self.assertIsNone(result["cursor"])


class TestEmptyAndFutureWindows(WindowResolutionTestCase):
    def test_cursor_on_the_run_date_yields_an_empty_window(self):
        self.write_weekly("2026-07-23", "2026-07-17")

        result, stderr = self.resolve("2026-07-23")

        self.assertTrue(result["empty"])
        self.assertEqual(result["days"], 0)
        self.assertGreater(result["start"], result["end"], "start must exceed end so the state is self-evident")
        self.assertIn("already covers", stderr)

    def test_cursor_after_the_run_date_is_non_fatal(self):
        self.write_weekly("2026-08-01", "2026-07-26")

        result, stderr = self.resolve("2026-07-23")

        self.assertTrue(result["empty"])
        self.assertEqual(result["days"], 0)
        self.assertIn("is after", stderr)

    def test_single_day_window_counts_as_one_day(self):
        self.write_weekly("2026-07-22", "2026-07-16")

        result, _ = self.resolve("2026-07-23")

        self.assertEqual(result["start"], "2026-07-23")
        self.assertEqual(result["end"], "2026-07-23")
        self.assertEqual(result["days"], 1)
        self.assertFalse(result["empty"])


class TestWarnNeverFailReads(WindowResolutionTestCase):
    def test_missing_reports_directory_yields_no_cursor(self):
        empty_root = Path(self._tmp.name) / "no-reports"
        empty_root.mkdir()

        buffer = io.StringIO()
        with redirect_stderr(buffer):
            result = dzcto.resolve_since_last_report_window(empty_root, dt.date(2026, 7, 23))

        self.assertIsNone(result["cursor"])
        self.assertIsNone(result["start"])
        self.assertEqual(result["end"], "2026-07-23")
        self.assertFalse(result["empty"])

    def test_unreadable_json_is_skipped_and_an_older_weekly_still_wins(self):
        self.write_weekly("2026-07-07", "2026-07-01")
        (self.reports / "2026-07-14-ceo-report-broken.json").write_text("{not json", encoding="utf-8")

        result, stderr = self.resolve("2026-07-23")

        self.assertEqual(result["cursor"]["window_end"], "2026-07-07")
        self.assertIn("unreadable JSON", stderr)

    def test_weekly_without_window_or_iso_filename_is_skipped(self):
        undated = weekly_report("2026-07-20", "2026-07-26")
        del undated["window"]
        self.write_report("latest-ceo-report.json", undated)
        self.write_weekly("2026-07-07", "2026-07-01")

        result, stderr = self.resolve("2026-07-23")

        self.assertEqual(result["cursor"]["window_end"], "2026-07-07")
        self.assertIn("no resolvable date", stderr)

    def test_no_reports_at_all_yields_no_cursor(self):
        result, _ = self.resolve("2026-07-23")

        self.assertIsNone(result["cursor"])
        self.assertIsNone(result["start"])
        self.assertEqual(result["days"], 0)


class TestWindowDerivation(unittest.TestCase):
    """The pure derivation, isolated from any filesystem read."""

    def test_days_are_inclusive_of_both_bounds(self):
        start, end, days, empty = dzcto.derive_since_last_report_window(
            dt.date(2026, 7, 14), dt.date(2026, 7, 23)
        )

        self.assertEqual((start, end), (dt.date(2026, 7, 15), dt.date(2026, 7, 23)))
        self.assertEqual(days, 9)
        self.assertFalse(empty)

    def test_days_never_go_negative(self):
        _, _, days, empty = dzcto.derive_since_last_report_window(
            dt.date(2026, 8, 1), dt.date(2026, 7, 23)
        )

        self.assertEqual(days, 0)
        self.assertTrue(empty)


if __name__ == "__main__":
    unittest.main()

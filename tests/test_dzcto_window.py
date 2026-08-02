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


class TestStreakExclusionsDoNotMoveTheCursor(WindowResolutionTestCase):
    """DAYZEROCTO-15 KTD5. The streak exclusion belongs to the streak pool ONLY.

    The cursor is a coverage ledger: it decides which days the next report covers. If an
    excluded report failed to advance it, the days that report already covered would be
    re-reported in the next window and land in two reports -- a correctness bug strictly worse
    than the inflated streak this feature exists to fix.

    This is structurally safe today because latest_weekly_report_cursor() in scripts/dzcto.py is
    a separate implementation from the artifact renderer's streak pool; they share an idiom, not
    a function. These tests exist so a future 'let's share the predicate' refactor fails loudly
    here instead of silently double-reporting days.
    """

    def test_quiet_excluded_report_still_advances_the_cursor(self):
        quiet = self.write_report(
            "2026-07-14-ceo-report-2026-07-08-to-2026-07-14.json",
            weekly_report("2026-07-08", "2026-07-14",
                          work_evidence={"quiet": True, "commits": 0, "merges": 0}),
        )

        result, _ = self.resolve("2026-07-23")

        self.assertEqual(result["cursor"]["window_end"], "2026-07-14")
        self.assertEqual(result["cursor"]["report"], f"reports/ceo-updates/{quiet.name}")
        self.assertEqual(result["start"], "2026-07-15")
        self.assertFalse(result["empty"])

    def test_test_run_report_still_advances_the_cursor(self):
        self.write_report(
            "2026-07-14-ceo-report-2026-07-08-to-2026-07-14.json",
            weekly_report("2026-07-08", "2026-07-14", test_run=True),
        )

        result, _ = self.resolve("2026-07-23")

        self.assertEqual(result["cursor"]["window_end"], "2026-07-14")
        self.assertEqual(result["start"], "2026-07-15")

    def test_no_day_is_covered_twice_when_the_newest_report_is_excluded(self):
        """The failure this guards against, stated as coverage rather than as a cursor value."""
        self.write_weekly("2026-07-07", "2026-07-01")
        self.write_report(
            "2026-07-14-ceo-report-2026-07-08-to-2026-07-14.json",
            weekly_report("2026-07-08", "2026-07-14",
                          work_evidence={"quiet": True, "commits": 0, "merges": 0}),
        )

        result, _ = self.resolve("2026-07-23")

        # Must start the day after the excluded report's window, not the day after the older
        # counted one -- otherwise 07-08..07-14 gets reported a second time.
        self.assertEqual(result["start"], "2026-07-15")
        self.assertNotEqual(result["start"], "2026-07-08")


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


class TestWindowCommand(unittest.TestCase):
    """End-to-end `dzcto window` CLI behavior, mirroring tests/test_dzcto_evidence.py."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = Path(self._tmp.name)
        self.home = self.root / "home"
        self.home.mkdir()
        self.artifacts = self.root / "artifacts"
        self.sidecar = self.artifacts / ".dzcto"
        self.sidecar.mkdir(parents=True)
        self.reports = self.artifacts / "reports" / "ceo-updates"
        self.reports.mkdir(parents=True)

    def write_local_config(self, **weekly_defaults) -> None:
        config = {"weeklyReportDefaults": weekly_defaults} if weekly_defaults else {}
        (self.sidecar / "config.json").write_text(json.dumps(config), encoding="utf-8")

    def write_global_profile(self, name: str, **profile) -> None:
        config_dir = self.home / ".dzcto"
        config_dir.mkdir(exist_ok=True)
        (config_dir / "config.json").write_text(
            json.dumps({"defaultProfile": name, "profiles": {name: profile}}), encoding="utf-8"
        )

    def write_weekly(self, end: str, start: str) -> Path:
        path = self.reports / f"{end}-ceo-report-{start}-to-{end}.json"
        path.write_text(json.dumps(weekly_report(start, end)), encoding="utf-8")
        return path

    def run_cli(self, *args: str, check: bool = True):
        import os
        import subprocess

        env = os.environ.copy()
        env["HOME"] = str(self.home)
        return subprocess.run(
            [sys.executable, str(REPO / "scripts" / "dzcto.py"), "window", *args],
            capture_output=True,
            text=True,
            check=check,
            env=env,
        )

    def test_since_last_report_range_resolves_the_cursor_window(self):
        self.write_local_config(range="since_last_report")
        self.write_weekly("2026-07-07", "2026-07-01")
        self.write_weekly("2026-07-14", "2026-07-08")

        result = self.run_cli("--artifacts-dir", str(self.artifacts), "--as-of", "2026-07-23")
        data = json.loads(result.stdout)

        self.assertEqual(data["mode"], "since_last_report")
        self.assertEqual(data["range"], "since_last_report")
        self.assertEqual(data["start"], "2026-07-15")
        self.assertEqual(data["end"], "2026-07-23")
        self.assertEqual(data["days"], 9)
        self.assertFalse(data["empty"])
        self.assertIsNone(data["fallback_reason"])
        self.assertEqual(data["cursor"]["window_end"], "2026-07-14")

    def test_day_based_range_defers_instead_of_resolving(self):
        self.write_local_config(range="previous_completed_week", startDay="Friday", endDay="Thursday")
        self.write_weekly("2026-07-14", "2026-07-08")

        result = self.run_cli("--artifacts-dir", str(self.artifacts), "--as-of", "2026-07-23")
        data = json.loads(result.stdout)

        # The resolver owns since_last_report only; every other range is an explicit deferral
        # so the skill's day-based path is a declared branch rather than an accident.
        self.assertEqual(data["mode"], "day_based")
        self.assertEqual(data["range"], "previous_completed_week")
        self.assertIsNone(data["start"])
        self.assertEqual(data["end"], "2026-07-23")
        self.assertIsNone(data["cursor"])
        self.assertEqual(result.returncode, 0)

    def test_absent_weekly_defaults_do_not_crash(self):
        self.write_local_config()

        data = json.loads(self.run_cli("--artifacts-dir", str(self.artifacts), "--as-of", "2026-07-23").stdout)

        self.assertEqual(data["mode"], "day_based")
        self.assertIsNone(data["range"])

    def test_cursor_mode_without_any_prior_weekly_report_falls_back(self):
        self.write_local_config(range="since_last_report")

        data = json.loads(self.run_cli("--artifacts-dir", str(self.artifacts), "--as-of", "2026-07-23").stdout)

        self.assertEqual(data["mode"], "fallback")
        self.assertEqual(data["fallback_reason"], "no_prior_weekly_report")
        self.assertEqual(data["end"], "2026-07-23")
        self.assertIsNone(data["start"])

    def test_profile_alone_resolves_the_same_window(self):
        # The config-model trap: binding to the wrong .dzcto/config.json returns a
        # valid-but-empty result with no error, so assert a real window, not just exit 0.
        self.write_global_profile(
            "acme",
            artifactsDir=str(self.artifacts),
            weeklyReportDefaults={"range": "since_last_report"},
        )
        self.write_weekly("2026-07-14", "2026-07-08")

        data = json.loads(self.run_cli("--profile", "acme", "--as-of", "2026-07-23").stdout)

        self.assertEqual(data["mode"], "since_last_report")
        self.assertEqual(data["start"], "2026-07-15")
        self.assertEqual(data["days"], 9)

    def test_unresolvable_artifact_folder_exits_2_with_guidance(self):
        result = self.run_cli("--as-of", "2026-07-23", check=False)

        self.assertEqual(result.returncode, 2)
        self.assertIn("No artifact/report folder could be resolved", result.stderr)
        self.assertEqual(result.stdout, "")

    def test_non_iso_as_of_fails_clearly_without_a_traceback(self):
        self.write_local_config(range="since_last_report")

        result = self.run_cli("--artifacts-dir", str(self.artifacts), "--as-of", "23-07-2026", check=False)

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("--as-of must use YYYY-MM-DD format", result.stderr)
        self.assertNotIn("Traceback", result.stderr)

    def test_stdout_stays_parseable_json_while_stderr_carries_notes(self):
        self.write_local_config(range="since_last_report")
        self.write_weekly("2026-07-07", "2026-07-01")
        (self.reports / "2026-07-14-ceo-report-broken.json").write_text("{not json", encoding="utf-8")

        result = self.run_cli("--artifacts-dir", str(self.artifacts), "--as-of", "2026-07-23")

        self.assertIn("unreadable JSON", result.stderr)
        self.assertEqual(json.loads(result.stdout)["cursor"]["window_end"], "2026-07-07")

    def test_window_command_is_hidden_from_top_level_help(self):
        import subprocess

        result = subprocess.run(
            [sys.executable, str(REPO / "scripts" / "dzcto.py"), "--help"],
            capture_output=True,
            text=True,
            check=True,
        )

        self.assertNotIn("window", result.stdout)

    def test_window_command_still_has_its_own_help(self):
        import subprocess

        result = subprocess.run(
            [sys.executable, str(REPO / "scripts" / "dzcto.py"), "window", "--help"],
            capture_output=True,
            text=True,
            check=True,
        )

        self.assertIn("--as-of", result.stdout)


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

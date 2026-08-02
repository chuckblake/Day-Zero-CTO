"""Tests for the CEO report schema v1 + week-over-week machinery (DAYZEROCTO-1)."""

import contextlib
import datetime as dt
import io
import json
import os
import re
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "scripts"))

import dzcto_artifact as artifact  # noqa: E402

GITHUB_TOKEN = "ghp_" + "AbCdEf1234567890AbCdEf1234567890AbCd"
AWS_TOKEN = "AKIA" + "ABCDEFGHIJKLMNOP"
LOW_GENERIC_SECRET = "api_key = \"dGhpcy1pcy1hLXZlcnktc2VjcmV0LXRva2Vu\""
LOW_GENERIC_VALUE = "dGhpcy1pcy1hLXZlcnktc2VjcmV0LXRva2Vu"
GIT_SHA = "0123456789abcdef0123456789abcdef01234567"


def v1_report(**overrides):
    data = {
        "schema_version": "ceo-report/1",
        "report_type": "weekly",
        "company": "Acme",
        "window": {"start": "2026-06-19", "end": "2026-06-25"},
        "headline": "Cadence held.",
        "progress": [{"area": "Auth", "status": "on-track", "summary": "Login shipped", "items": ["OAuth"]}],
        "risks_blockers": [{"risk": "Rate limits", "detail": "Near quota", "severity": "medium"}],
        "asks_decisions": [{"ask": "Approve upgrade", "context": "Quota", "owner": "CEO"}],
        "next": ["Billing"],
        "metrics": {"prs_merged": 5},
        "sources": ["git log"],
    }
    data.update(overrides)
    return data


def write_report(folder: Path, name: str, data) -> Path:
    path = folder / name
    path.write_text(json.dumps(data), encoding="utf-8")
    return path


class TestValidateCeoReport(unittest.TestCase):
    def test_valid_v1_report_has_no_warnings(self):
        self.assertEqual(artifact.validate_ceo_report(v1_report()), [])

    def test_legacy_report_warns_but_lists_each_violation(self):
        legacy = {
            "headline": "x",
            "progress": ["did a thing"],
            "risks_blockers": [{"item": "risk", "level": "high"}],
            "asks_decisions": ["ask"],
            "next": [],
            "sources": [],
        }
        warnings = artifact.validate_ceo_report(legacy)
        joined = "\n".join(warnings)
        self.assertIn("missing required field: report_type", joined)
        self.assertIn("missing required field: company", joined)
        self.assertIn("missing required field: window", joined)
        self.assertIn("progress items should be objects", joined)
        self.assertIn("risks_blockers items should carry 'risk'", joined)
        self.assertIn("asks_decisions items should be objects", joined)

    def test_window_end_before_start_warns(self):
        data = v1_report(window={"start": "2026-06-25", "end": "2026-06-19"})
        self.assertTrue(any("earlier than window.start" in w for w in artifact.validate_ceo_report(data)))

    def test_bad_report_type_and_nonscalar_metric_warn(self):
        data = v1_report(report_type="monthly", metrics={"prs": [1, 2]})
        warnings = artifact.validate_ceo_report(data)
        self.assertTrue(any("report_type" in w for w in warnings))
        self.assertTrue(any("metrics['prs']" in w for w in warnings))

    def test_empty_structured_report_warns_to_narrate_headline(self):
        data = v1_report(progress=[], risks_blockers=[], asks_decisions=[], next=[], sources=[])
        warnings = artifact.validate_ceo_report(data)
        self.assertEqual([warning for warning in warnings if "no structured content" in warning], [
            "report has no structured content; if the window was quiet, say so in headline"
        ])

    def test_carried_forward_risk_suppresses_empty_report_warning(self):
        data = v1_report(progress=[], asks_decisions=[], next=[], sources=[])
        warnings = artifact.validate_ceo_report(data)
        self.assertFalse(any("no structured content" in warning for warning in warnings))

    def test_empty_metrics_and_sources_do_not_trigger_empty_report_warning(self):
        data = v1_report(metrics={}, sources=[])
        warnings = artifact.validate_ceo_report(data)
        self.assertFalse(any("no structured content" in warning for warning in warnings))

    def test_missing_required_sections_still_warn_without_crashing(self):
        warnings = artifact.validate_ceo_report({"headline": "Quiet window."})
        joined = "\n".join(warnings)
        self.assertIn("missing required field: progress", joined)
        self.assertIn("missing required field: risks_blockers", joined)
        self.assertIn("missing required field: asks_decisions", joined)
        self.assertIn("missing required field: next", joined)
        self.assertIn("no structured content", joined)


class TestReportEffectiveDate(unittest.TestCase):
    def test_window_end_wins_over_filename(self):
        date = artifact.report_effective_date(Path("2026-01-01-x.json"), {"window": {"end": "2026-06-25"}})
        self.assertEqual(date, "2026-06-25")

    def test_filename_prefix_fallback(self):
        self.assertEqual(artifact.report_effective_date(Path("2026-06-25-x.json"), {}), "2026-06-25")

    def test_unresolvable_returns_none(self):
        self.assertIsNone(artifact.report_effective_date(Path("ceo-report-old.json"), {}))


class TestWeeklyStreak(unittest.TestCase):
    def d(self, value: str) -> dt.date:
        return dt.date.fromisoformat(value)

    def test_three_consecutive_weeklies_count_from_today(self):
        dates = [self.d("2026-06-25"), self.d("2026-06-18"), self.d("2026-06-11")]
        self.assertEqual(artifact.weekly_streak(dates, self.d("2026-06-26"), 7), 3)

    def test_single_live_weekly_counts_as_one(self):
        self.assertEqual(artifact.weekly_streak([self.d("2026-06-25")], self.d("2026-06-26"), 7), 1)

    def test_empty_dates_return_zero(self):
        self.assertEqual(artifact.weekly_streak([], self.d("2026-06-26"), 7), 0)

    def test_ten_days_since_latest_is_late_but_live(self):
        dates = [self.d("2026-06-25"), self.d("2026-06-18")]
        self.assertEqual(artifact.weekly_streak(dates, self.d("2026-07-05"), 7), 2)

    def test_eleven_days_since_latest_is_lapsed(self):
        dates = [self.d("2026-06-25"), self.d("2026-06-18")]
        self.assertEqual(artifact.weekly_streak(dates, self.d("2026-07-06"), 7), 0)

    def test_rerun_inside_same_period_does_not_inflate_streak(self):
        dates = [self.d("2026-06-25"), self.d("2026-06-22"), self.d("2026-06-18")]
        self.assertEqual(artifact.weekly_streak(dates, self.d("2026-06-26"), 7), 2)

    def test_gap_period_stops_the_streak(self):
        dates = [
            self.d("2026-07-02"),
            self.d("2026-06-25"),
            self.d("2026-06-18"),
            self.d("2026-06-04"),
            self.d("2026-05-28"),
        ]
        self.assertEqual(artifact.weekly_streak(dates, self.d("2026-07-03"), 7), 3)

    def test_duplicate_dates_count_once(self):
        dates = [self.d("2026-06-25"), self.d("2026-06-25"), self.d("2026-06-18")]
        self.assertEqual(artifact.weekly_streak(dates, self.d("2026-06-26"), 7), 2)

    def test_fourteen_day_cadence_counts_fourteen_day_periods(self):
        dates = [
            self.d("2026-06-25"),
            self.d("2026-06-18"),
            self.d("2026-06-11"),
            self.d("2026-05-28"),
        ]
        self.assertEqual(artifact.weekly_streak(dates, self.d("2026-06-26"), 14), 3)

    def test_zero_cadence_falls_back_to_weekly(self):
        dates = [self.d("2026-06-25"), self.d("2026-06-18")]
        self.assertEqual(artifact.weekly_streak(dates, self.d("2026-06-26"), 0), 2)


class TestWeeklyReportDates(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.folder = Path(self._tmp.name)
        self.addCleanup(self._tmp.cleanup)

    def test_collects_weekly_report_dates_newest_first(self):
        write_report(self.folder, "2026-06-18-ceo-report.json", v1_report(window={"start": "2026-06-12", "end": "2026-06-18"}))
        write_report(self.folder, "2026-06-25-ceo-report.json", v1_report())
        self.assertEqual(
            artifact.weekly_report_dates(self.folder),
            [dt.date(2026, 6, 25), dt.date(2026, 6, 18)],
        )

    def test_excludes_data_json_even_when_weekly(self):
        write_report(self.folder, "data.json", v1_report())
        self.assertEqual(artifact.weekly_report_dates(self.folder), [])

    def test_excludes_ad_hoc_and_legacy_reports(self):
        write_report(self.folder, "2026-06-25-ceo-report-adhoc.json", v1_report(report_type="ad_hoc"))
        legacy = v1_report()
        del legacy["report_type"]
        write_report(self.folder, "2026-06-18-ceo-report-legacy.json", legacy)
        self.assertEqual(artifact.weekly_report_dates(self.folder), [])

    def test_skips_bad_dates_and_invalid_json(self):
        write_report(self.folder, "ceo-report-bad-date.json", v1_report(window={"start": "2026-06-19", "end": "not-a-date"}))
        (self.folder / "2026-06-25-ceo-report-bad-json.json").write_text("{not json", encoding="utf-8")
        self.assertEqual(artifact.weekly_report_dates(self.folder), [])

    def test_uses_iso_filename_prefix_when_window_missing(self):
        write_report(self.folder, "2026-06-25-ceo-report.json", v1_report(window={}))
        self.assertEqual(artifact.weekly_report_dates(self.folder), [dt.date(2026, 6, 25)])

    def test_empty_and_missing_directories_return_empty_lists(self):
        self.assertEqual(artifact.weekly_report_dates(self.folder), [])
        self.assertEqual(artifact.weekly_report_dates(self.folder / "missing"), [])

    def test_reports_without_eligibility_facts_still_count(self):
        """Upgrade safety (DAYZEROCTO-15 KTD3): every report already on disk predates the
        eligibility fields. Excluding on absence would retroactively zero every user's streak."""
        write_report(self.folder, "2026-06-25-ceo-report.json", v1_report())
        self.assertEqual(artifact.weekly_report_dates(self.folder), [dt.date(2026, 6, 25)])

    def test_excludes_test_run_reports_and_names_the_reason(self):
        write_report(self.folder, "2026-06-25-ceo-report.json", v1_report(test_run=True))
        stderr = io.StringIO()
        with contextlib.redirect_stderr(stderr):
            self.assertEqual(artifact.weekly_report_dates(self.folder), [])
        note = stderr.getvalue()
        self.assertIn("excluding weekly-streak candidate", note)
        self.assertIn("2026-06-25-ceo-report.json", note)
        self.assertIn("test run", note)

    def test_test_run_false_is_counted(self):
        write_report(self.folder, "2026-06-25-ceo-report.json", v1_report(test_run=False))
        self.assertEqual(artifact.weekly_report_dates(self.folder), [dt.date(2026, 6, 25)])

    def test_non_boolean_test_run_is_counted_and_does_not_raise(self):
        """Only a real boolean True excludes. A truthy string is malformed input, and the
        fail-safe direction for malformed eligibility facts is to count (KTD3)."""
        write_report(self.folder, "2026-06-25-ceo-report.json", v1_report(test_run="yes"))
        write_report(self.folder, "2026-06-18-ceo-report.json", v1_report(
            test_run=None, window={"start": "2026-06-12", "end": "2026-06-18"}))
        self.assertEqual(
            artifact.weekly_report_dates(self.folder),
            [dt.date(2026, 6, 25), dt.date(2026, 6, 18)],
        )

    def test_unreadable_report_keeps_its_existing_skip_note(self):
        """The new filter runs after the existing tolerant-collector skips, so a malformed
        payload is still reported as 'skipping', never as an eligibility 'excluding'."""
        (self.folder / "2026-06-25-ceo-report.json").write_text("{not json", encoding="utf-8")
        stderr = io.StringIO()
        with contextlib.redirect_stderr(stderr):
            self.assertEqual(artifact.weekly_report_dates(self.folder), [])
        note = stderr.getvalue()
        self.assertIn("skipping weekly-streak candidate", note)
        self.assertNotIn("excluding weekly-streak candidate", note)

    def test_excluded_report_breaks_the_streak_run(self):
        """An excluded middle week is a real gap, not a silent collapse of the remaining weeks."""
        write_report(self.folder, "2026-06-25-ceo-report.json", v1_report())
        write_report(self.folder, "2026-06-18-ceo-report.json", v1_report(
            test_run=True, window={"start": "2026-06-12", "end": "2026-06-18"}))
        write_report(self.folder, "2026-06-11-ceo-report.json", v1_report(
            window={"start": "2026-06-05", "end": "2026-06-11"}))
        with contextlib.redirect_stderr(io.StringIO()):
            dates = artifact.weekly_report_dates(self.folder)
        self.assertEqual(dates, [dt.date(2026, 6, 25), dt.date(2026, 6, 11)])
        self.assertEqual(artifact.weekly_streak(dates, dt.date(2026, 6, 26), 7), 1)


class TestCountsTowardWeeklyStreak(unittest.TestCase):
    def test_absent_facts_count_with_no_reason(self):
        self.assertEqual(artifact.counts_toward_weekly_streak(v1_report()), (True, None))

    def test_test_run_excludes_and_returns_a_human_readable_reason(self):
        counts, reason = artifact.counts_toward_weekly_streak(v1_report(test_run=True))
        self.assertFalse(counts)
        self.assertIsInstance(reason, str)
        self.assertIn("test run", reason)

    def test_quiet_work_evidence_excludes_and_names_the_commit_count(self):
        counts, reason = artifact.counts_toward_weekly_streak(
            v1_report(work_evidence={"quiet": True, "commits": 0, "merges": 0})
        )
        self.assertFalse(counts)
        self.assertIn("quiet window", reason)
        self.assertIn("0 commits", reason)

    def test_non_quiet_work_evidence_counts(self):
        self.assertEqual(
            artifact.counts_toward_weekly_streak(
                v1_report(work_evidence={"quiet": False, "commits": 12, "merges": 3})
            ),
            (True, None),
        )

    def test_malformed_work_evidence_counts_and_does_not_raise(self):
        """Malformed eligibility facts fail safe toward counting (KTD3), never toward exclusion."""
        for bad in ("quiet", None, [], {"quiet": "yes"}, {"commits": 0}):
            with self.subTest(work_evidence=bad):
                self.assertEqual(
                    artifact.counts_toward_weekly_streak(v1_report(work_evidence=bad)),
                    (True, None),
                )


class TestResolveWeeklyCadenceDays(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.core_dir = Path(self._tmp.name) / "core"
        self.core_dir.mkdir()
        self.addCleanup(self._tmp.cleanup)

    def write_cadence(self, body: str) -> None:
        (self.core_dir / "OPERATING_CADENCE.md").write_text(body, encoding="utf-8")

    def test_configured_cadence_rule_wins(self):
        self.write_cadence(
            """# Operating Cadence

## Index Cadence Rules

| Report | Folder | Cadence | Day | Command |
| --- | --- | --- | --- | --- |
| CEO updates | ceo-updates | every 2 weeks | Thursday | /dzcto-ceo-report-weekly |
"""
        )
        self.assertEqual(artifact.resolve_weekly_cadence_days(self.core_dir, "ceo-updates"), 14)

    def test_missing_cadence_file_falls_back_to_weekly(self):
        self.assertEqual(artifact.resolve_weekly_cadence_days(self.core_dir, "ceo-updates"), 7)

    def test_file_without_rules_falls_back_to_weekly(self):
        self.write_cadence("# Operating Cadence\n\nNo table yet.\n")
        self.assertEqual(artifact.resolve_weekly_cadence_days(self.core_dir, "ceo-updates"), 7)

    def test_table_without_matching_folder_falls_back_to_weekly(self):
        self.write_cadence(
            """# Operating Cadence

## Index Cadence Rules

| Report | Folder | Cadence | Day | Command |
| --- | --- | --- | --- | --- |
| Other | investor-updates | every 2 weeks | Friday | /other |
"""
        )
        self.assertEqual(artifact.resolve_weekly_cadence_days(self.core_dir, "ceo-updates"), 7)


class TestRenderIndexWeeklyStreak(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.workspace = Path(self._tmp.name) / "ws"
        self.reports_dir = self.workspace / "reports" / "ceo-updates"
        self.reports_dir.mkdir(parents=True)
        self.addCleanup(self._tmp.cleanup)
        # render_index reads the global config for defaultProfile (DAYZEROCTO-14); pin it so
        # these tests never depend on the developer's real ~/.dzcto/config.json.
        patcher = mock.patch.object(artifact, "read_global_config", dict)
        patcher.start()
        self.addCleanup(patcher.stop)

    def render(self, today: str) -> str:
        artifact.render_index(self.workspace, self.workspace, today=dt.date.fromisoformat(today))
        return (self.workspace / "index.html").read_text(encoding="utf-8")

    def streak_tile(self, html: str) -> str:
        start = html.index('<div class="k-label">Weekly streak</div>')
        end = html.index('<div class="k-label">Weekly default</div>', start)
        return html[start:end]

    def streak_tone(self, html: str) -> str:
        """data-tone lives on the tile's opening tag, which sits before the label streak_tile()
        slices from -- so read it from the enclosing element, not the sliced body."""
        label = html.index('<div class="k-label">Weekly streak</div>')
        opening = html.rindex('<div class="kpi"', 0, label)
        return re.search(r'data-tone="([^"]*)"', html[opening:label]).group(1)

    def test_two_consecutive_weeklies_render_streak_tile(self):
        write_report(self.reports_dir, "2026-06-25-ceo-report.json", v1_report())
        write_report(self.reports_dir, "2026-06-18-ceo-report.json", v1_report(window={"start": "2026-06-12", "end": "2026-06-18"}))
        tile = self.streak_tile(self.render("2026-06-26"))
        self.assertIn("Weekly streak", tile)
        self.assertIn('<div class="k-val">2</div>', tile)
        self.assertIn("of 3 - North Star", tile)

    def test_three_consecutive_weeklies_render_north_star_met(self):
        write_report(self.reports_dir, "2026-06-25-ceo-report.json", v1_report())
        write_report(self.reports_dir, "2026-06-18-ceo-report.json", v1_report(window={"start": "2026-06-12", "end": "2026-06-18"}))
        write_report(self.reports_dir, "2026-06-11-ceo-report.json", v1_report(window={"start": "2026-06-05", "end": "2026-06-11"}))
        tile = self.streak_tile(self.render("2026-06-26"))
        self.assertIn('<div class="k-val">3</div>', tile)
        self.assertIn("North Star met", tile)
        self.assertNotIn("of 3 - North Star", tile)

    def test_zero_reports_render_call_to_action(self):
        tile = self.streak_tile(self.render("2026-06-26"))
        self.assertIn("Weekly streak", tile)
        self.assertIn('<div class="k-val">0</div>', tile)
        self.assertIn("Start a weekly report", tile)

    def test_lapsed_weekly_streak_renders_zero(self):
        write_report(self.reports_dir, "2026-06-25-ceo-report.json", v1_report())
        tile = self.streak_tile(self.render("2026-07-06"))
        self.assertIn("Weekly streak", tile)
        self.assertIn('<div class="k-val">0</div>', tile)

    def test_malformed_json_does_not_block_index_write(self):
        write_report(self.reports_dir, "2026-06-25-ceo-report.json", v1_report())
        write_report(self.reports_dir, "2026-06-18-ceo-report.json", v1_report(window={"start": "2026-06-12", "end": "2026-06-18"}))
        (self.reports_dir / "2026-06-11-ceo-report-bad.json").write_text("{not json", encoding="utf-8")
        html = self.render("2026-06-26")
        self.assertTrue((self.workspace / "index.html").exists())
        self.assertIn('<div class="k-val">2</div>', self.streak_tile(html))

    def test_only_excluded_reports_render_the_paused_state_not_the_zero_state(self):
        """An honestly-filed quiet week must not read as 'you never started'. The product asks
        for that report; the tile has to distinguish paused from never-started."""
        write_report(self.reports_dir, "2026-06-25-ceo-report.json", v1_report(
            work_evidence={"quiet": True, "commits": 0, "merges": 0}))
        with contextlib.redirect_stderr(io.StringIO()):
            tile = self.streak_tile(self.render("2026-06-26"))
        self.assertIn('<div class="k-val">0</div>', tile)
        self.assertIn("Paused", tile)
        self.assertIn("not counted", tile)

    def test_paused_state_does_not_use_the_warning_tone(self):
        """A quiet week the product asked the user to file is not an error state."""
        write_report(self.reports_dir, "2026-06-25-ceo-report.json", v1_report(test_run=True))
        with contextlib.redirect_stderr(io.StringIO()):
            html = self.render("2026-06-26")
        self.assertIn("Paused", self.streak_tile(html))
        self.assertEqual(self.streak_tone(html), "info")

    def test_empty_workspace_keeps_the_warn_tone_call_to_action(self):
        """The new branch must not steal the genuine zero-state."""
        html = self.render("2026-06-26")
        self.assertIn("Start a weekly report", self.streak_tile(html))
        self.assertEqual(self.streak_tone(html), "warn")

    def test_excluded_report_alongside_counting_ones_keeps_the_normal_tile(self):
        write_report(self.reports_dir, "2026-06-25-ceo-report.json", v1_report())
        write_report(self.reports_dir, "2026-06-18-ceo-report.json", v1_report(
            test_run=True, window={"start": "2026-06-12", "end": "2026-06-18"}))
        with contextlib.redirect_stderr(io.StringIO()):
            tile = self.streak_tile(self.render("2026-06-26"))
        self.assertIn('<div class="k-val">1</div>', tile)
        self.assertIn("of 3 - North Star", tile)


class TestClassifyWeeklyReports(unittest.TestCase):
    """weekly_report_dates() is now a thin wrapper; the classifier is the one loop and the one
    predicate call site that both the streak count and the index tile read."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.folder = Path(self._tmp.name)
        self.addCleanup(self._tmp.cleanup)

    def test_returns_counted_dates_and_named_exclusions(self):
        write_report(self.folder, "2026-06-25-ceo-report.json", v1_report())
        write_report(self.folder, "2026-06-18-ceo-report.json", v1_report(
            test_run=True, window={"start": "2026-06-12", "end": "2026-06-18"}))
        with contextlib.redirect_stderr(io.StringIO()):
            dates, exclusions = artifact.classify_weekly_reports(self.folder)
        self.assertEqual(dates, [dt.date(2026, 6, 25)])
        self.assertEqual(len(exclusions), 1)
        name, reason = exclusions[0]
        self.assertEqual(name, "2026-06-18-ceo-report.json")
        self.assertIn("test run", reason)

    def test_wrapper_returns_only_the_counted_dates(self):
        write_report(self.folder, "2026-06-25-ceo-report.json", v1_report())
        self.assertEqual(
            artifact.weekly_report_dates(self.folder),
            artifact.classify_weekly_reports(self.folder)[0],
        )

    def test_missing_directory_returns_two_empty_lists(self):
        self.assertEqual(artifact.classify_weekly_reports(self.folder / "missing"), ([], []))

    def test_skipped_candidates_are_not_reported_as_exclusions(self):
        """A malformed report is skipped, not excluded -- the two are different facts and the
        index tile must not call an unreadable file a paused streak."""
        (self.folder / "2026-06-25-ceo-report.json").write_text("{not json", encoding="utf-8")
        with contextlib.redirect_stderr(io.StringIO()):
            dates, exclusions = artifact.classify_weekly_reports(self.folder)
        self.assertEqual(dates, [])
        self.assertEqual(exclusions, [])


class TestRenderIndexWeeklyDefaultTile(unittest.TestCase):
    """The weekly-default KPI card must not describe cursor mode in weekday terms."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.workspace = Path(self._tmp.name) / "ws"
        self.sidecar = self.workspace / ".dzcto"
        self.sidecar.mkdir(parents=True)
        (self.workspace / "reports" / "ceo-updates").mkdir(parents=True)
        self.addCleanup(self._tmp.cleanup)
        # render_index reads the global config for defaultProfile (DAYZEROCTO-14); pin it so
        # these tests never depend on the developer's real ~/.dzcto/config.json.
        patcher = mock.patch.object(artifact, "read_global_config", dict)
        patcher.start()
        self.addCleanup(patcher.stop)

    def render(self, **weekly_defaults) -> str:
        config = {"weeklyReportDefaults": weekly_defaults} if weekly_defaults else {}
        (self.sidecar / "config.json").write_text(json.dumps(config), encoding="utf-8")
        artifact.render_index(self.workspace, self.workspace, today=dt.date(2026, 7, 23))
        return (self.workspace / "index.html").read_text(encoding="utf-8")

    def weekly_tile(self, html: str) -> str:
        start = html.index('<div class="k-label">Weekly default</div>')
        return html[start : start + 400]

    def test_cursor_mode_does_not_render_a_weekday_range(self):
        tile = self.weekly_tile(self.render(range="since_last_report"))

        self.assertIn("Since last", tile)
        self.assertNotIn(" to ", tile)

    def test_cursor_mode_suppresses_stale_start_and_end_days(self):
        # A profile switched to cursor mode often still carries its old weekday keys;
        # rendering them would state a confident, wrong window shape.
        html = self.render(range="since_last_report", startDay="Friday", endDay="Thursday", lookbackDays=7)
        tile = self.weekly_tile(html)

        self.assertNotIn("Friday", tile)
        self.assertNotIn("Thursday", tile)
        self.assertNotIn("Fri to Thu", tile)
        self.assertNotIn("7 days", tile)

    def test_day_based_range_still_renders_its_weekday_abbreviations(self):
        tile = self.weekly_tile(
            self.render(range="previous_completed_week", startDay="Friday", endDay="Thursday")
        )

        self.assertIn("Fri to Thu", tile)

    def test_unconfigured_range_still_renders_the_needed_call_to_action(self):
        tile = self.weekly_tile(self.render())

        self.assertIn("Needed", tile)

    def test_copyable_weekly_prompt_inherits_the_corrected_label(self):
        html = self.render(range="since_last_report", startDay="Friday", endDay="Thursday")

        # The prompt card and the KPI tile share one label source; proving the prompt is
        # clean proves they did not drift into two independent formatters.
        self.assertIn("since_last_report", html)
        self.assertNotIn("since_last_report; Friday to Thursday", html)


class TestLocatePriorReport(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.folder = Path(self._tmp.name)
        self.addCleanup(self._tmp.cleanup)

    def current(self, start="2026-06-26", end="2026-07-02", report_type="weekly"):
        return v1_report(report_type=report_type, window={"start": start, "end": end})

    def target(self, end="2026-07-02"):
        return self.folder / f"{end}-ceo-report-current.json"

    def test_first_report_has_no_prior(self):
        path, data, date, notes = artifact.locate_prior_report(self.target(), self.current())
        self.assertIsNone(path)
        self.assertIsNone(data)
        self.assertEqual(notes, [])

    def test_weekly_picks_most_recent_weekly(self):
        write_report(self.folder, "2026-06-18-ceo-report-a.json", v1_report(window={"start": "2026-06-12", "end": "2026-06-18"}))
        expected = write_report(self.folder, "2026-06-25-ceo-report-b.json", v1_report())
        path, _data, date, notes = artifact.locate_prior_report(self.target(), self.current())
        self.assertEqual(path, expected)
        self.assertEqual(date, "2026-06-25")
        self.assertEqual(notes, [])

    def test_weekly_skips_interleaved_ad_hoc(self):
        expected = write_report(self.folder, "2026-06-25-ceo-report-w.json", v1_report())
        write_report(
            self.folder,
            "2026-06-30-ceo-report-adhoc.json",
            v1_report(report_type="ad_hoc", window={"start": "2026-06-28", "end": "2026-06-30"}),
        )
        path, _data, _date, notes = artifact.locate_prior_report(self.target(), self.current())
        self.assertEqual(path, expected)
        self.assertEqual(notes, [])

    def test_ad_hoc_picks_most_recent_any_type(self):
        write_report(self.folder, "2026-06-18-ceo-report-w1.json", v1_report(window={"start": "2026-06-12", "end": "2026-06-18"}))
        expected = write_report(self.folder, "2026-06-25-ceo-report-w2.json", v1_report())
        path, _data, _date, notes = artifact.locate_prior_report(
            self.target(), self.current(report_type="ad_hoc")
        )
        self.assertEqual(path, expected)
        self.assertEqual(notes, [])

    def test_weekly_falls_back_to_untyped_legacy_with_note(self):
        legacy = v1_report()
        del legacy["report_type"]
        expected = write_report(self.folder, "2026-06-25-ceo-report-legacy.json", legacy)
        path, _data, _date, notes = artifact.locate_prior_report(self.target(), self.current())
        self.assertEqual(path, expected)
        self.assertEqual(notes, ["cadence_fallback"])

    def test_gap_week_prior_still_selected(self):
        expected = write_report(self.folder, "2026-06-11-ceo-report-old.json", v1_report(window={"start": "2026-06-05", "end": "2026-06-11"}))
        path, _data, date, _notes = artifact.locate_prior_report(self.target(), self.current())
        self.assertEqual(path, expected)
        self.assertEqual(date, "2026-06-11")

    def test_rolling_lookback_overlap_gets_no_caveat(self):
        expected = write_report(self.folder, "2026-06-29-ceo-report-roll.json", v1_report(window={"start": "2026-06-20", "end": "2026-06-29"}))
        path, _data, _date, notes = artifact.locate_prior_report(
            self.target(), self.current(start="2026-06-23", end="2026-07-02")
        )
        self.assertEqual(path, expected)
        self.assertEqual(notes, [])

    def test_cross_cadence_overlap_gets_caveat(self):
        expected = write_report(
            self.folder,
            "2026-06-30-ceo-report-adhoc.json",
            v1_report(report_type="ad_hoc", window={"start": "2026-06-20", "end": "2026-06-30"}),
        )
        path, _data, _date, notes = artifact.locate_prior_report(
            self.target(), self.current(start="2026-06-26", end="2026-07-02", report_type="ad_hoc")
        )
        self.assertEqual(path, expected)
        self.assertEqual(notes, ["overlap"])

    def test_legacy_unresolvable_name_never_wins_by_sort(self):
        # "ceo-report-*.json" sorts lexicographically after date prefixes; it must be
        # skipped (no window, no ISO prefix), not treated as the newest prior.
        write_report(self.folder, "ceo-report-legacy.json", {"headline": "old"})
        expected = write_report(self.folder, "2026-06-25-ceo-report-b.json", v1_report())
        path, _data, _date, _notes = artifact.locate_prior_report(self.target(), self.current())
        self.assertEqual(path, expected)

    def test_same_window_rerun_not_its_own_prior(self):
        write_report(self.folder, "2026-07-02-ceo-report-other-title.json", self.current())
        path, _data, _date, _notes = artifact.locate_prior_report(self.target(), self.current())
        self.assertIsNone(path)

    def test_corrupt_prior_skipped(self):
        (self.folder / "2026-06-25-ceo-report-bad.json").write_text("{not json", encoding="utf-8")
        expected = write_report(self.folder, "2026-06-18-ceo-report-ok.json", v1_report(window={"start": "2026-06-12", "end": "2026-06-18"}))
        path, _data, _date, _notes = artifact.locate_prior_report(self.target(), self.current())
        self.assertEqual(path, expected)

    def test_data_json_excluded(self):
        write_report(self.folder, "data.json", v1_report())
        path, _data, _date, _notes = artifact.locate_prior_report(self.target(), self.current())
        self.assertIsNone(path)

    def test_weekly_fallback_to_typed_ad_hoc_gets_no_weekly_prior_note(self):
        expected = write_report(
            self.folder,
            "2026-06-25-ceo-report-adhoc.json",
            v1_report(report_type="ad_hoc"),
        )
        path, _data, _date, notes = artifact.locate_prior_report(self.target(), self.current())
        self.assertEqual(path, expected)
        self.assertEqual(notes, ["no_weekly_prior"])

    def test_same_day_prior_with_different_window_is_found(self):
        # A morning ad-hoc ending the same day must not leave the afternoon report
        # falsely claiming "first report".
        expected = write_report(
            self.folder,
            "2026-07-02-ceo-report-morning.json",
            v1_report(report_type="ad_hoc", window={"start": "2026-07-01", "end": "2026-07-02"}),
        )
        path, _data, _date, notes = artifact.locate_prior_report(
            self.target(), self.current(start="2026-06-26", end="2026-07-02", report_type="ad_hoc")
        )
        self.assertEqual(path, expected)
        self.assertEqual(notes, ["overlap"])

    def test_equal_effective_dates_tiebreak_on_generated_at(self):
        # Distinct windows sharing the same end date (a same-window pair would be excluded).
        older = v1_report(window={"start": "2026-06-18", "end": "2026-06-25"})
        older["generated_at"] = "2026-06-25T08:00:00Z"
        newer = v1_report(window={"start": "2026-06-19", "end": "2026-06-25"})
        newer["generated_at"] = "2026-06-25T18:00:00Z"
        write_report(self.folder, "2026-06-25-ceo-report-a.json", older)
        expected = write_report(self.folder, "2026-06-25-ceo-report-b.json", newer)
        path, _data, _date, _notes = artifact.locate_prior_report(self.target(), self.current())
        self.assertEqual(path, expected)


class TestReportChangesHtml(unittest.TestCase):
    def test_no_prior_renders_placeholder_for_ceo_updates(self):
        html = artifact.report_changes_html("ceo-updates", v1_report(), None, "")
        self.assertIn("Week over week", html)
        self.assertIn("First report", html)
        self.assertIn("no prior baseline", html)

    def test_all_groups_and_metric_delta_render_without_truncation(self):
        previous = v1_report(
            progress=[{"area": "Auth", "summary": "Login shipped"}],
            risks_blockers=[{"risk": "Rate limits"}],
            asks_decisions=[{"ask": "Approve upgrade"}],
            next=["Billing"],
            metrics={"prs_merged": 5},
        )
        current = v1_report(
            progress=[{"area": "Billing", "summary": "Stripe wired"}],
            risks_blockers=[{"risk": "Churn spike"}],
            asks_decisions=[{"ask": "Hire SRE"}],
            next=["Launch"],
            metrics={"prs_merged": 8},
        )
        html = artifact.report_changes_html("ceo-updates", current, previous, "2026-06-25")
        self.assertIn("2026-06-25", html)
        self.assertIn("prs_merged", html)
        self.assertIn("5 → 8", html)
        self.assertIn("(+3)", html)
        for label in ("Progress", "Risks / Blockers", "Asks / Decisions", "Next"):
            self.assertIn(f"{label}:</strong> Added", html)
            self.assertIn(f"{label}:</strong> No longer listed", html)

    def test_identical_reports_render_no_material_changes(self):
        html = artifact.report_changes_html("ceo-updates", v1_report(), v1_report(), "2026-06-25")
        self.assertIn("No material structured changes", html)

    def test_group_missing_from_prior_is_not_comparable(self):
        previous = v1_report()
        del previous["risks_blockers"]
        html = artifact.report_changes_html("ceo-updates", v1_report(), previous, "2026-06-25")
        self.assertIn("Not comparable", html)
        self.assertIn("prior report lacked this section", html)

    def test_empty_current_group_names_prior_without_claiming_removal(self):
        current = v1_report(progress=[], next=[])
        html = artifact.report_changes_html("ceo-updates", current, v1_report(), "2026-06-25")
        self.assertIn("Progress:</strong> No items this window", html)
        self.assertIn("prior listed: Login shipped", html)
        self.assertIn("Next:</strong> No items this window", html)
        self.assertIn("prior listed: Billing", html)
        self.assertNotIn("No longer listed", html)

    def test_partial_group_removal_still_renders_no_longer_listed(self):
        previous = v1_report(next=["Billing", "Launch"])
        current = v1_report(next=["Billing"])
        html = artifact.report_changes_html("ceo-updates", current, previous, "2026-06-25")
        self.assertIn("Next:</strong> No longer listed: Launch", html)
        self.assertNotIn("Next:</strong> No items this window", html)

    def test_empty_current_and_prior_group_emits_no_group_line(self):
        previous = v1_report(progress=[])
        current = v1_report(progress=[])
        html = artifact.report_changes_html("ceo-updates", current, previous, "2026-06-25")
        self.assertNotIn("Progress:</strong>", html)
        self.assertIn("No material structured changes", html)

    def test_every_group_empty_against_populated_prior_suppresses_no_material_fallback(self):
        current = v1_report(progress=[], risks_blockers=[], asks_decisions=[], next=[])
        html = artifact.report_changes_html("ceo-updates", current, v1_report(), "2026-06-25")
        for label in ("Progress", "Risks / Blockers", "Asks / Decisions", "Next"):
            self.assertIn(f"{label}:</strong> No items this window", html)
        self.assertNotIn("No material structured changes", html)
        self.assertNotIn("No longer listed", html)

    def test_not_comparable_wins_over_empty_current_group(self):
        previous = v1_report()
        del previous["progress"]
        current = v1_report(progress=[])
        html = artifact.report_changes_html("ceo-updates", current, previous, "2026-06-25")
        self.assertIn("Progress:</strong> Not comparable", html)
        self.assertNotIn("Progress:</strong> No items this window", html)

    def test_rendered_quiet_report_uses_empty_group_diff_phrasing(self):
        current = v1_report(progress=[], asks_decisions=[], next=[])
        html = artifact.render_structured_report("ceo-updates", current, previous_data=v1_report(), previous_date="2026-06-25")
        self.assertIn("Progress:</strong> No items this window", html)
        self.assertIn("<h2>Progress</h2>", html)
        self.assertIn("No progress to report for this window.", html)
        self.assertNotIn("No longer listed", html)

    def test_disjoint_metrics_render_no_delta(self):
        previous = v1_report(metrics={"deploys": 2})
        html = artifact.report_changes_html("ceo-updates", v1_report(metrics={"prs_merged": 8}), previous, "d")
        self.assertNotIn("→", html)

    def test_notes_render(self):
        html = artifact.report_changes_html(
            "ceo-updates", v1_report(), v1_report(), "2026-06-25", ["cadence_fallback", "overlap"]
        )
        self.assertIn("predates cadence tagging", html)
        self.assertIn("deltas may double-count", html)

    def test_not_comparable_suppresses_no_material_changes_line(self):
        previous = v1_report()
        del previous["risks_blockers"]
        html = artifact.report_changes_html("ceo-updates", v1_report(), previous, "2026-06-25")
        self.assertIn("Not comparable", html)
        self.assertNotIn("No material structured changes", html)

    def test_headline_only_change_renders_updated_emphasis(self):
        current = v1_report(headline="A very different emphasis this week.")
        html = artifact.report_changes_html("ceo-updates", current, v1_report(), "2026-06-25")
        self.assertIn("Updated emphasis", html)
        self.assertIn("A very different emphasis this week.", html)

    def test_large_int_metrics_render_with_separators_not_scientific(self):
        previous = v1_report(metrics={"arr": 1_200_000})
        current = v1_report(metrics={"arr": 1_534_500})
        html = artifact.report_changes_html("ceo-updates", current, previous, "2026-06-25")
        self.assertIn("1,200,000 → 1,534,500", html)
        self.assertIn("(+334,500)", html)
        self.assertNotIn("e+", html)

    def test_huge_int_metric_never_aborts_rendering(self):
        previous = v1_report(metrics={"absurd": 10**400, "prs_merged": 5})
        current = v1_report(metrics={"absurd": 10**400 + 1, "prs_merged": 8})
        html = artifact.report_changes_html("ceo-updates", current, previous, "2026-06-25")
        self.assertIn("5 → 8", html)  # the sane metric still renders

    def test_nonfinite_and_bool_metrics_are_skipped(self):
        previous = v1_report(metrics={"nan": float("nan"), "launched": False, "prs_merged": 5})
        current = v1_report(metrics={"nan": float("nan"), "launched": True, "prs_merged": 5})
        self.assertEqual(artifact.metric_delta_items(current, previous), [])


class TestWeekOverWeekWindowLength(unittest.TestCase):
    """Varying-length windows must be visible wherever their metrics are compared."""

    NINE_DAYS = {"start": "2026-07-15", "end": "2026-07-23"}
    SEVEN_DAYS = {"start": "2026-06-19", "end": "2026-06-25"}

    def render(self, current, previous, previous_date="2026-06-25"):
        return artifact.report_changes_html("ceo-updates", current, previous, previous_date)

    def test_window_line_names_both_lengths_and_precedes_the_metric_deltas(self):
        current = v1_report(window=self.NINE_DAYS, metrics={"prs_merged": 8})
        html = self.render(current, v1_report(metrics={"prs_merged": 5}))

        self.assertIn("Window:", html)
        self.assertIn("9 days", html)
        self.assertIn("(2026-07-15 to 2026-07-23)", html)
        self.assertIn("prior 7 days", html)
        self.assertLess(
            html.index("Window:"), html.index("prs_merged"),
            "the reader needs the denominator before the numbers",
        )

    def test_window_line_never_uses_an_arrow(self):
        # test_disjoint_metrics_render_no_delta asserts no "→" anywhere in the output,
        # so the window line must read "start to end" rather than "start → end".
        html = self.render(v1_report(window=self.NINE_DAYS), v1_report())

        self.assertIn("Window:", html)
        self.assertNotIn("2026-07-15 → 2026-07-23", html)

    def test_equal_length_windows_still_disclose(self):
        html = self.render(v1_report(), v1_report())

        # Disclosure, not anomaly flagging — it renders even when nothing varies.
        self.assertIn("Window:", html)
        self.assertIn("7 days", html)
        self.assertIn("prior 7 days", html)

    def test_window_line_renders_without_any_numeric_metric_delta(self):
        current = v1_report(window=self.NINE_DAYS, metrics={"note": "qualitative"})
        html = self.render(current, v1_report(metrics={"note": "qualitative"}))

        self.assertIn("Window:", html)
        self.assertIn("9 days", html)

    def test_window_line_does_not_suppress_the_no_material_changes_fallback(self):
        html = self.render(v1_report(), v1_report())

        self.assertIn("Window:", html)
        self.assertIn("No material structured changes", html)

    def test_single_day_window_renders_as_one_day(self):
        current = v1_report(window={"start": "2026-07-23", "end": "2026-07-23"})
        html = self.render(current, v1_report())

        self.assertIn("1 day", html)
        self.assertNotIn("1 days", html)

    def test_prior_window_missing_start_omits_the_line(self):
        previous = v1_report(window={"end": "2026-06-25"})
        html = self.render(v1_report(window=self.NINE_DAYS), previous)

        self.assertNotIn("Window:", html)

    def test_reversed_window_omits_the_line_rather_than_rendering_a_negative_length(self):
        current = v1_report(window={"start": "2026-07-23", "end": "2026-07-15"})
        html = self.render(current, v1_report())

        self.assertNotIn("Window:", html)

    def test_non_iso_window_values_omit_the_line_without_aborting(self):
        current = v1_report(window={"start": "last Monday", "end": "today"})
        html = self.render(current, v1_report())

        self.assertNotIn("Window:", html)
        self.assertIn("Week over week", artifact.report_changes_html("ceo-updates", current, None, ""))

    def test_first_report_placeholder_is_unchanged(self):
        html = artifact.report_changes_html("ceo-updates", v1_report(), None, "")

        self.assertIn("First report", html)
        self.assertNotIn("Window:", html)

    def test_window_values_are_html_escaped_like_their_neighbours(self):
        current = v1_report(window=self.NINE_DAYS)
        html = self.render(current, v1_report())

        self.assertIn("<li><strong>Window:</strong>", html)
        self.assertNotIn("<script", html)


class TestCitedEvidenceSources(unittest.TestCase):
    def test_empty_missing_and_blank_only_sources_are_not_cited(self):
        for data in ({}, {"sources": []}, {"sources": [{}, {"detail": "No title"}, "   "]}):
            with self.subTest(data=data):
                self.assertEqual(artifact.cited_evidence_sources(data), [])

    def test_populated_sources_are_returned(self):
        sources = ["git log", {"title": "PR 123", "path": "pull/123"}]
        self.assertEqual(artifact.cited_evidence_sources({"sources": sources}), sources)

    def test_source_aliases_are_supported(self):
        for key in ("source_list", "evidence_sources"):
            with self.subTest(key=key):
                self.assertEqual(artifact.cited_evidence_sources({key: ["git diff"]}), ["git diff"])

    def test_render_sources_counts_only_cited_entries(self):
        html = artifact.render_sources({"sources": [{"detail": "No title"}, "git log"]})
        self.assertIn("1 source", html)
        self.assertEqual(html.count("<li>"), 1)


class TestThinEvidenceRendering(unittest.TestCase):
    def test_empty_sources_prepend_banner_once(self):
        html = artifact.render_structured_report("ceo-updates", v1_report(sources=[]), previous_data=None)
        self.assertEqual(html.count('<aside class="report-thin-evidence"'), 1)
        self.assertLess(html.index("report-thin-evidence"), html.index("report-changes"))
        self.assertIn("<h2>Progress</h2>", html)

    def test_populated_sources_do_not_render_banner(self):
        html = artifact.render_structured_report("ceo-updates", v1_report(), previous_data=None)
        self.assertNotIn('<aside class="report-thin-evidence"', html)


class TestCeoQuietWindowRendering(unittest.TestCase):
    def sparse_quiet_report(self):
        return v1_report(
            headline="Quiet week: no code shipped; rate-limit risk carries forward.",
            progress=[],
            risks_blockers=[{"risk": "Rate limits", "detail": "Near quota", "severity": "medium"}],
            asks_decisions=[],
            next=[],
            metrics={},
            sources=[],
        )

    def test_sparse_quiet_report_renders_required_empty_sections(self):
        html = artifact.render_structured_report("ceo-updates", self.sparse_quiet_report(), previous_data=None)
        self.assertIn("<h2>Progress</h2>", html)
        self.assertIn("No progress to report for this window.", html)
        self.assertIn("<h2>Risks / Blockers</h2>", html)
        self.assertIn("Rate limits", html)
        self.assertNotIn("No risks or blockers this window.", html)
        self.assertIn("<h2>Asks / Decisions</h2>", html)
        self.assertIn("No asks or decisions this window.", html)
        self.assertIn("<h2>Next</h2>", html)
        self.assertIn("Nothing queued for the next window.", html)
        self.assertIn("<span>Sources</span>", html)
        self.assertIn("0 sources", html)
        self.assertIn("No evidence sources recorded for this window.", html)

    def test_sparse_quiet_report_keeps_optional_sections_absent(self):
        # One carried risk keeps the report sparse enough that Follow-up signals
        # would only duplicate the body. Metrics is optional when omitted or empty.
        html = artifact.render_structured_report("ceo-updates", self.sparse_quiet_report(), previous_data=None)
        self.assertNotIn('<span class="label">PRs Merged</span>', html)
        self.assertNotIn('aria-label="Follow-up signals"', html)

    def test_quiet_required_sections_render_in_spine_order(self):
        html = artifact.render_structured_report("ceo-updates", self.sparse_quiet_report(), previous_data=None)
        anchors = [
            "<h2>Week over week</h2>",
            "<h2>Progress</h2>",
            "<h2>Risks / Blockers</h2>",
            "<h2>Asks / Decisions</h2>",
            "<h2>Next</h2>",
            "<span>Sources</span>",
        ]
        positions = [html.index(anchor) for anchor in anchors]
        self.assertEqual(positions, sorted(positions))

    def test_empty_progress_variants_render_placeholder(self):
        for progress in (None, [], [""], [{}], ["   "]):
            with self.subTest(progress=progress):
                html = artifact.render_structured_report(
                    "ceo-updates",
                    v1_report(progress=progress, asks_decisions=[], next=[], sources=[]),
                    previous_data=None,
                )
                self.assertIn("<h2>Progress</h2>", html)
                self.assertIn("No progress to report for this window.", html)

    def test_populated_ceo_report_has_no_empty_placeholders(self):
        html = artifact.render_structured_report("ceo-updates", v1_report(), previous_data=None)
        self.assertNotIn("empty-item", html)


class TestReportSectionSpine(unittest.TestCase):
    TEMPLATE = REPO / "docs" / "ceo-report-template.md"
    TEMPLATE_HEADER = "## Section spine (fixed, in order)"
    SPINE = [
        ("Masthead", '<span class="eyebrow">CEO Reports - Day Zero CTO</span>'),
        ("Lede", "Cadence held."),
        ("Week over week", "<h2>Week over week</h2>"),
        ("Follow-up signals", 'aria-label="Follow-up signals"'),
        ("Metrics", '<span class="label">PRs Merged</span>'),
        ("Progress", "<h2>Progress</h2>"),
        ("Risks / Blockers", "<h2>Risks / Blockers</h2>"),
        ("Asks / Decisions", "<h2>Asks / Decisions</h2>"),
        ("Next", "<h2>Next</h2>"),
        ("Sources", "<span>Sources</span>"),
        ("Footer", '<footer class="app-footer">'),
    ]

    def documented_sections(self) -> list[str]:
        text = self.TEMPLATE.read_text(encoding="utf-8")
        self.assertIn(self.TEMPLATE_HEADER, text, "docs/ceo-report-template.md lost its section spine")
        block = text.split(self.TEMPLATE_HEADER, 1)[1].split("\n## ", 1)[0]
        sections = []
        for line in block.splitlines():
            if not line.startswith("| "):
                continue
            cells = [cell.strip() for cell in line.strip().strip("|").split("|")]
            if len(cells) < 2 or not cells[0].isdigit():
                continue
            section = cells[1].replace("**", "").replace("`", "")
            sections.append(section.split(" \u2014 ", 1)[0])
        return sections

    def rendered_report(self) -> str:
        data = v1_report(next=["Billing", "Launch"])
        title = "CEO Report 2026-06-19 to 2026-06-25"
        body = artifact.render_structured_report("ceo-updates", data, previous_data=None)
        return artifact.render_report_page(
            title,
            data["window"]["end"],
            "ceo-updates",
            body,
            {},
            "Acme",
            lede=artifact.report_lead_summary(data),
        )

    def test_spine_constant_matches_template_sections(self):
        self.assertEqual(
            self.documented_sections(),
            [section for section, _anchor in self.SPINE],
            "TestReportSectionSpine.SPINE must mirror docs/ceo-report-template.md",
        )

    def test_template_spine_sections_render_in_order(self):
        html = self.rendered_report()
        positions = []
        for section, anchor in self.SPINE:
            try:
                positions.append((section, html.index(anchor)))
            except ValueError:
                self.fail(f"{section} anchor missing from rendered CEO report; see docs/ceo-report-template.md")

        for previous, current in zip(positions, positions[1:]):
            previous_section, previous_index = previous
            current_section, current_index = current
            self.assertLess(
                previous_index,
                current_index,
                f"{current_section} rendered before {previous_section}; see docs/ceo-report-template.md",
            )


class TestSkillSchemaLockstep(unittest.TestCase):
    HEADER = "## Report JSON schema (v1)"

    def schema_block(self, skill: str) -> str:
        text = (REPO / "skills" / skill / "SKILL.md").read_text(encoding="utf-8")
        self.assertIn(self.HEADER, text, f"{skill} lost its schema block")
        block = text.split(self.HEADER, 1)[1]
        return block.split("\n## ", 1)[0]

    def test_schema_blocks_are_byte_identical(self):
        self.assertEqual(
            self.schema_block("dzcto-ceo-report"),
            self.schema_block("dzcto-ceo-report-weekly"),
            "Report JSON schema (v1) blocks in the two SKILL.md files must stay byte-identical",
        )

    def test_both_blocks_forbid_authoring_the_eligibility_fields(self):
        """test_run and work_evidence decide streak eligibility, so an author must be told not to
        write them -- the renderer strips authored values, and a skill that still invites them
        would produce reports whose fields silently vanish."""
        for skill in ("dzcto-ceo-report", "dzcto-ceo-report-weekly"):
            with self.subTest(skill=skill):
                block = self.schema_block(skill)
                self.assertIn("Do not author", block)
                self.assertIn("`test_run`", block)
                self.assertIn("`work_evidence`", block)


class TestEligibilityFieldsAreDocumented(unittest.TestCase):
    """The renderer stamps these field names; the docs that describe the contract must use the
    same ones, so a rename in code that skips the docs fails here instead of shipping."""

    ELIGIBILITY_FIELDS = ("test_run", "work_evidence")

    def test_template_canon_documents_both_fields(self):
        text = (REPO / "docs" / "ceo-report-template.md").read_text(encoding="utf-8")
        for field in self.ELIGIBILITY_FIELDS:
            with self.subTest(field=field):
                self.assertIn(f"`{field}`", text)

    def test_readme_field_table_documents_both_fields(self):
        text = (REPO / "README.md").read_text(encoding="utf-8")
        for field in self.ELIGIBILITY_FIELDS:
            with self.subTest(field=field):
                self.assertIn(f"`{field}`", text)

    def test_quiet_windows_section_describes_the_mechanism(self):
        """The section already asserted the behavior before any code implemented it. It must now
        name what actually causes the exclusion, or it stays an unbacked claim."""
        text = (REPO / "docs" / "ceo-report-template.md").read_text(encoding="utf-8")
        section = text.split("## Quiet windows", 1)[1].split("\n## ", 1)[0]
        self.assertIn("--evidence-file", section)
        self.assertIn("work_evidence", section)

    def test_concepts_weekly_streak_entry_matches_what_ships(self):
        """CONCEPTS.md previously disclaimed these exclusions outright. It must describe the two
        that ship without overclaiming the two that do not."""
        text = (REPO / "CONCEPTS.md").read_text(encoding="utf-8")
        entry = text.split("### Weekly streak", 1)[1].split("\n### ", 1)[0]
        self.assertIn("test_run", entry)
        self.assertIn("work_evidence", entry)
        self.assertNotIn(
            "not the canonical North Star metric with exclusions such as test runs",
            entry,
            "the stale disclaimer contradicts the shipped exclusions",
        )

    def test_only_the_weekly_skill_passes_the_evidence_file(self):
        """Ad-hoc reports never enter the weekly pool, so wiring --evidence-file into that skill
        would imply an eligibility contract it does not participate in."""
        weekly = (REPO / "skills" / "dzcto-ceo-report-weekly" / "SKILL.md").read_text(encoding="utf-8")
        ad_hoc = (REPO / "skills" / "dzcto-ceo-report" / "SKILL.md").read_text(encoding="utf-8")
        self.assertIn("--evidence-file", weekly)
        self.assertIn("--output-json", weekly)
        self.assertNotIn("--evidence-file", ad_hoc)

    def test_weekly_skill_saves_the_snapshot_before_it_renders_with_it(self):
        """--evidence-file can only point at a path the collector was told to write."""
        text = (REPO / "skills" / "dzcto-ceo-report-weekly" / "SKILL.md").read_text(encoding="utf-8")
        self.assertLess(text.index("--output-json"), text.index("--evidence-file"))


class TestWeeklySkillConsumesTheWindowResolver(unittest.TestCase):
    """The weekly skill must consume resolved dates, not interpret weeklyReportDefaults itself."""

    def weekly_text(self) -> str:
        return (REPO / "skills" / "dzcto-ceo-report-weekly" / "SKILL.md").read_text(encoding="utf-8")

    def test_resolver_runs_before_the_evidence_collector(self):
        text = self.weekly_text()

        self.assertIn("dzcto window", text)
        self.assertLess(
            text.index("dzcto window"), text.index("dzcto evidence"),
            "the window must be resolved before evidence is gathered for it",
        )

    def test_both_invocation_forms_are_documented(self):
        text = self.weekly_text()

        self.assertIn("dzcto window \\", text)
        self.assertIn("python3 scripts/dzcto.py window \\", text)

    def test_empty_window_branch_forbids_calling_the_evidence_collector(self):
        # Omitting this is the one instruction whose absence produces a hard failure in a
        # real run: an empty window has start > end, which dzcto evidence rejects.
        text = self.weekly_text()

        self.assertIn("empty", text)
        self.assertIn("do not call `dzcto evidence`", text)

    def test_day_based_fallback_path_is_preserved(self):
        text = self.weekly_text()

        self.assertIn("day_based", text)
        self.assertIn("fallback", text)
        self.assertIn("weeklyReportDefaults", text)

    def test_ad_hoc_skill_does_not_mention_the_weekly_resolver(self):
        # The ad-hoc skill is deliberately not cadence-scoped, so it must not grow a cursor.
        text = (REPO / "skills" / "dzcto-ceo-report" / "SKILL.md").read_text(encoding="utf-8")

        self.assertNotIn("dzcto window", text)


class TestInitSkillOffersCursorMode(unittest.TestCase):
    def test_init_skill_offers_since_last_report(self):
        text = (REPO / "skills" / "dzcto-init" / "SKILL.md").read_text(encoding="utf-8")

        self.assertIn("since_last_report", text)
        self.assertIn('--weekly-range "since_last_report"', text)


class TestSkillBadNewsInstructions(unittest.TestCase):
    SKILLS = ("dzcto-ceo-report", "dzcto-ceo-report-weekly")

    def skill_text(self, skill: str) -> str:
        return (REPO / "skills" / skill / "SKILL.md").read_text(encoding="utf-8").lower()

    def test_report_skills_prompt_bad_news_evidence(self):
        for skill in self.SKILLS:
            with self.subTest(skill=skill):
                text = self.skill_text(skill)
                self.assertIn("reverts or reverted commits", text)
                self.assertIn("failing or red ci", text)
                self.assertIn("slipped or descoped work", text)


class TestSkillOpenAndShareInstructions(unittest.TestCase):
    SKILLS = ("dzcto-ceo-report", "dzcto-ceo-report-weekly")

    def test_report_skills_finish_with_open_and_share(self):
        for skill in self.SKILLS:
            with self.subTest(skill=skill):
                text = (REPO / "skills" / skill / "SKILL.md").read_text(encoding="utf-8")
                self.assertIn("--open", text)
                self.assertIn("Save as PDF", text)
                self.assertIn("printed share recipe", text)
                self.assertNotIn("End with the generated report path and a brief summary.", text)


class TestSkillEvidencePrimary(unittest.TestCase):
    SKILLS = ("dzcto-ceo-report", "dzcto-ceo-report-weekly")

    def test_evidence_collector_precedes_conversation_notes_in_step_four(self):
        for skill in self.SKILLS:
            with self.subTest(skill=skill):
                text = (REPO / "skills" / skill / "SKILL.md").read_text(encoding="utf-8")
                step_four = text.split("4. Gather evidence", 1)[1].split("\n5. ", 1)[0]
                self.assertIn("dzcto evidence", step_four)
                self.assertIn("primary grounding source", step_four)
                self.assertLess(step_four.index("dzcto evidence"), step_four.index("User notes"))


class TestSkillQuietWindowInstructions(unittest.TestCase):
    SKILLS = ("dzcto-ceo-report", "dzcto-ceo-report-weekly")

    def skill_text(self, skill: str) -> str:
        return (REPO / "skills" / skill / "SKILL.md").read_text(encoding="utf-8").lower()

    def test_report_skills_prompt_quiet_window_authoring(self):
        for skill in self.SKILLS:
            with self.subTest(skill=skill):
                text = self.skill_text(skill)
                self.assertIn("quiet", text)
                self.assertIn("never pad", text)
                self.assertIn("carry still-true risks, asks, and next items forward verbatim", text)
                self.assertIn("metrics", text)
                self.assertIn("prs_merged: 0", text)

    def test_weekly_skill_names_quiet_week_without_streak_claims(self):
        text = self.skill_text("dzcto-ceo-report-weekly")
        self.assertIn("quiet week", text)
        self.assertNotIn("streak", text)

    def test_ad_hoc_skill_uses_window_neutral_quiet_language(self):
        text = self.skill_text("dzcto-ceo-report")
        self.assertNotIn("quiet week", text)
        self.assertIn("quiet-window report", text)


class TestArtifactWritePath(unittest.TestCase):
    """End-to-end runs of the artifact CLI against a temp workspace."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.workspace = Path(self._tmp.name) / "ws"
        self.addCleanup(self._tmp.cleanup)
        self.run_cli("--init", "--artifacts-dir", str(self.workspace), "--company-name", "Acme", "--no-save-preferences")

    def run_cli(self, *cli_args, check=True):
        return subprocess.run(
            [sys.executable, str(REPO / "scripts" / "dzcto_artifact.py"), *cli_args],
            capture_output=True,
            text=True,
            check=check,
        )

    def generate(self, data, title, *extra, check=True):
        data_file = self.workspace.parent / f"{artifact.slugify(title)}.json"
        data_file.write_text(json.dumps(data), encoding="utf-8")
        return self.run_cli(
            "--artifacts-dir", str(self.workspace), "--kind", "ceo-updates",
            "--title", title, "--data-file", str(data_file), *extra,
            check=check,
        )

    def reports_dir(self) -> Path:
        return self.workspace / "reports" / "ceo-updates"

    def test_open_flag_preserves_stdout_path_and_prints_share_recipe(self):
        with mock.patch.dict(os.environ, {"DZCTO_NO_OPEN": "1"}):
            result = self.generate(v1_report(), "CEO Report open and share", "--open")

        stdout_lines = result.stdout.splitlines()
        self.assertEqual(len(stdout_lines), 1)
        self.assertTrue(Path(stdout_lines[0]).exists())
        self.assertIn("Save as PDF", result.stderr)
        self.assertIn("report ready to share", result.stderr)

    def test_without_open_flag_prints_no_share_recipe(self):
        result = self.generate(v1_report(), "CEO Report path only")

        self.assertEqual(len(result.stdout.splitlines()), 1)
        self.assertNotIn("Save as PDF", result.stderr)
        self.assertNotIn("report ready to share", result.stderr)

    def test_wrapper_forwards_open_flag(self):
        data_file = self.workspace.parent / "wrapper-open.json"
        data_file.write_text(json.dumps(v1_report()), encoding="utf-8")
        with mock.patch.dict(os.environ, {"DZCTO_NO_OPEN": "1"}):
            result = subprocess.run(
                [
                    sys.executable,
                    str(REPO / "scripts" / "dzcto.py"),
                    "artifact",
                    "--artifacts-dir", str(self.workspace),
                    "--kind", "ceo-updates",
                    "--title", "CEO Report wrapper open",
                    "--data-file", str(data_file),
                    "--open",
                ],
                capture_output=True,
                text=True,
                check=True,
            )

        self.assertEqual(len(result.stdout.splitlines()), 1)
        self.assertIn("Save as PDF", result.stderr)

    def test_test_run_flag_stamps_metadata_and_keeps_stdout_to_the_path(self):
        result = self.generate(v1_report(), "CEO Report marked test run", "--test-run")

        stdout_lines = result.stdout.splitlines()
        self.assertEqual(len(stdout_lines), 1)
        report_path = Path(stdout_lines[0])
        self.assertTrue(report_path.exists())
        written = json.loads(report_path.with_suffix(".json").read_text(encoding="utf-8"))
        self.assertIs(written["test_run"], True)
        self.assertIn("test_run", result.stderr)

    def test_without_test_run_flag_no_marker_is_stamped(self):
        result = self.generate(v1_report(), "CEO Report unmarked")

        report_path = Path(result.stdout.splitlines()[0])
        written = json.loads(report_path.with_suffix(".json").read_text(encoding="utf-8"))
        self.assertNotIn("test_run", written)

    def test_authored_test_run_is_overwritten_by_the_renderer(self):
        """Streak eligibility is renderer-owned metadata: a report author cannot mark their own
        report a test run, and cannot suppress the flag the operator passed."""
        result = self.generate(v1_report(test_run=True), "CEO Report authored marker")
        report_path = Path(result.stdout.splitlines()[0])
        written = json.loads(report_path.with_suffix(".json").read_text(encoding="utf-8"))
        self.assertNotIn("test_run", written)

    def evidence_snapshot(self, name, *, start="2026-06-19", end="2026-06-25", repos=1, commits=0, merges=0):
        """Shaped like scripts/dzcto.py's build_evidence_data() output."""
        snapshot = {
            "window": {"start": start, "end": end},
            "repos": [{"repo": f"/tmp/repo{i}"} for i in range(repos)],
            "totals": {"repos": repos, "commits": commits, "merges": merges, "authors": 0},
            "quiet": commits == 0,
            "generated_at": "2026-06-25T00:00:00Z",
        }
        path = self.workspace.parent / name
        path.write_text(json.dumps(snapshot), encoding="utf-8")
        return path

    def written_json(self, result):
        return json.loads(Path(result.stdout.splitlines()[0]).with_suffix(".json").read_text(encoding="utf-8"))

    def test_quiet_evidence_stamps_work_facts_and_drops_the_report_from_the_streak(self):
        snapshot = self.evidence_snapshot("quiet-evidence.json", commits=0)
        result = self.generate(v1_report(), "CEO Report quiet week", "--evidence-file", str(snapshot))

        self.assertEqual(
            self.written_json(result)["work_evidence"],
            {"quiet": True, "commits": 0, "merges": 0},
        )
        self.assertIn("does not count toward the weekly streak", result.stderr)
        with contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(artifact.weekly_report_dates(self.reports_dir()), [])

    def test_busy_evidence_stamps_not_quiet_and_the_report_still_counts(self):
        snapshot = self.evidence_snapshot("busy-evidence.json", commits=12, merges=3)
        result = self.generate(v1_report(), "CEO Report busy week", "--evidence-file", str(snapshot))

        self.assertEqual(
            self.written_json(result)["work_evidence"],
            {"quiet": False, "commits": 12, "merges": 3},
        )
        self.assertEqual(artifact.weekly_report_dates(self.reports_dir()), [dt.date(2026, 6, 25)])

    def test_no_evidence_file_stamps_nothing_and_stays_silent(self):
        """The legacy path must be unchanged: no flag, no field, no warning."""
        result = self.generate(v1_report(), "CEO Report no evidence")

        self.assertNotIn("work_evidence", self.written_json(result))
        self.assertNotIn("work_evidence", result.stderr)

    def test_mismatched_evidence_window_stamps_nothing_and_names_both_windows(self):
        """KTD2: a stale snapshot marking a busy week quiet is the failure this guard prevents.
        Absent-and-warned is strictly better than present-and-wrong."""
        snapshot = self.evidence_snapshot("stale-evidence.json", start="2026-06-12", end="2026-06-18")
        result = self.generate(v1_report(), "CEO Report stale evidence", "--evidence-file", str(snapshot))

        self.assertNotIn("work_evidence", self.written_json(result))
        self.assertIn("2026-06-12 to 2026-06-18", result.stderr)
        self.assertIn("2026-06-19 to 2026-06-25", result.stderr)
        self.assertEqual(artifact.weekly_report_dates(self.reports_dir()), [dt.date(2026, 6, 25)])

    def test_zero_repo_snapshot_is_undetermined_not_quiet(self):
        """build_evidence_data() reports quiet=True when no repos are configured, because zero
        commits is trivially true. No repos is absence of evidence, not evidence of no work --
        treating it as quiet would exclude every report of every user without a configured repo."""
        snapshot = self.evidence_snapshot("no-repos-evidence.json", repos=0, commits=0)
        result = self.generate(v1_report(), "CEO Report no repos", "--evidence-file", str(snapshot))

        self.assertNotIn("work_evidence", self.written_json(result))
        self.assertIn("zero readable repositories", result.stderr)
        self.assertEqual(artifact.weekly_report_dates(self.reports_dir()), [dt.date(2026, 6, 25)])

    def test_missing_or_malformed_evidence_file_warns_but_still_renders(self):
        missing = self.workspace.parent / "nope-evidence.json"
        result = self.generate(v1_report(), "CEO Report missing evidence", "--evidence-file", str(missing))
        self.assertTrue(Path(result.stdout.splitlines()[0]).exists())
        self.assertNotIn("work_evidence", self.written_json(result))
        self.assertIn("work_evidence was not stamped", result.stderr)

        broken = self.workspace.parent / "broken-evidence.json"
        broken.write_text("{not json", encoding="utf-8")
        result = self.generate(v1_report(), "CEO Report broken evidence", "--evidence-file", str(broken))
        self.assertTrue(Path(result.stdout.splitlines()[0]).exists())
        self.assertNotIn("work_evidence", self.written_json(result))
        self.assertIn("work_evidence was not stamped", result.stderr)

    def test_authored_work_evidence_is_overwritten_by_the_renderer(self):
        snapshot = self.evidence_snapshot("authored-evidence.json", commits=0)
        result = self.generate(
            v1_report(work_evidence={"quiet": False, "commits": 999, "merges": 999}),
            "CEO Report authored evidence",
            "--evidence-file", str(snapshot),
        )
        self.assertEqual(
            self.written_json(result)["work_evidence"],
            {"quiet": True, "commits": 0, "merges": 0},
        )

    def test_authored_work_evidence_is_dropped_even_without_a_snapshot(self):
        """An author must not be able to declare their own week busy by supplying the field."""
        result = self.generate(
            v1_report(work_evidence={"quiet": False, "commits": 999, "merges": 999}),
            "CEO Report authored evidence only",
        )
        self.assertNotIn("work_evidence", self.written_json(result))

    def test_wrapper_forwards_evidence_file_flag(self):
        snapshot = self.evidence_snapshot("wrapper-evidence.json", commits=0)
        data_file = self.workspace.parent / "wrapper-evidence-data.json"
        data_file.write_text(json.dumps(v1_report()), encoding="utf-8")
        result = subprocess.run(
            [
                sys.executable,
                str(REPO / "scripts" / "dzcto.py"),
                "artifact",
                "--artifacts-dir", str(self.workspace),
                "--kind", "ceo-updates",
                "--title", "CEO Report wrapper evidence",
                "--data-file", str(data_file),
                "--evidence-file", str(snapshot),
            ],
            capture_output=True,
            text=True,
            check=True,
        )

        stdout_lines = result.stdout.splitlines()
        self.assertEqual(len(stdout_lines), 1)
        written = json.loads(Path(stdout_lines[0]).with_suffix(".json").read_text(encoding="utf-8"))
        self.assertIs(written["work_evidence"]["quiet"], True)

    def test_wrapper_forwards_test_run_flag(self):
        """Three-site wiring regression: the dzcto.py wrapper whitelists flags rather than
        forwarding argv, so an engine-only flag silently vanishes on the real user path."""
        data_file = self.workspace.parent / "wrapper-test-run.json"
        data_file.write_text(json.dumps(v1_report()), encoding="utf-8")
        result = subprocess.run(
            [
                sys.executable,
                str(REPO / "scripts" / "dzcto.py"),
                "artifact",
                "--artifacts-dir", str(self.workspace),
                "--kind", "ceo-updates",
                "--title", "CEO Report wrapper test run",
                "--data-file", str(data_file),
                "--test-run",
            ],
            capture_output=True,
            text=True,
            check=True,
        )

        stdout_lines = result.stdout.splitlines()
        self.assertEqual(len(stdout_lines), 1)
        written = json.loads(Path(stdout_lines[0]).with_suffix(".json").read_text(encoding="utf-8"))
        self.assertIs(written["test_run"], True)

    def test_open_failure_is_advisory_and_uri_handles_spaces(self):
        report_path = self.workspace / "report with spaces.html"
        report_path.write_text("<p>Report</p>", encoding="utf-8")
        stderr = io.StringIO()
        with (
            mock.patch.dict(os.environ, {"DZCTO_NO_OPEN": ""}),
            mock.patch.object(artifact.webbrowser, "open", side_effect=RuntimeError("no browser")) as browser_open,
            mock.patch.object(artifact.sys, "stderr", stderr),
        ):
            artifact.emit_open_and_share(report_path)

        browser_open.assert_called_once_with(report_path.as_uri())
        self.assertIn("could not open", stderr.getvalue())
        self.assertIn("Save as PDF", stderr.getvalue())

    def test_removed_report_kind_is_rejected(self):
        result = self.run_cli(
            "--artifacts-dir", str(self.workspace), "--kind", "snapshot", "--title", "Snapshot",
            check=False,
        )
        self.assertEqual(result.returncode, 2)
        self.assertIn("invalid choice", result.stderr)

    def test_first_report_derives_date_and_renders_placeholder(self):
        self.generate(v1_report(), "CEO Report 2026-06-19 to 2026-06-25")
        html = self.reports_dir() / "2026-06-25-ceo-report-2026-06-19-to-2026-06-25.html"
        self.assertTrue(html.exists(), "filename must derive from window.end without --date")
        text = html.read_text(encoding="utf-8")
        self.assertIn("report-changes", text)
        self.assertIn("no prior baseline", text)
        emitted = json.loads(html.with_suffix(".json").read_text(encoding="utf-8"))
        self.assertIsNone(emitted["prior_report"])
        self.assertEqual(emitted["schema_version"], "ceo-report/1")
        self.assertTrue(emitted["generated_at"])

    def test_init_refreshes_existing_structured_reports_without_rewriting_json(self):
        self.generate(v1_report(), "CEO Report 2026-06-19 to 2026-06-25")
        html = self.reports_dir() / "2026-06-25-ceo-report-2026-06-19-to-2026-06-25.html"
        json_path = html.with_suffix(".json")
        before_json = json_path.read_text(encoding="utf-8")
        html.write_text("<!doctype html><title>Old</title><p>old report format</p>", encoding="utf-8")

        result = self.run_cli("--init", "--artifacts-dir", str(self.workspace), "--company-name", "Acme", "--no-save-preferences")

        refreshed = html.read_text(encoding="utf-8")
        self.assertIn("refreshed 1 existing report", result.stderr)
        self.assertIn("report-body", refreshed)
        self.assertIn("Week over week", refreshed)
        self.assertNotIn("old report format", refreshed)
        self.assertEqual(before_json, json_path.read_text(encoding="utf-8"))

    def test_second_report_diffs_against_first(self):
        self.generate(v1_report(), "CEO Report 2026-06-19 to 2026-06-25")
        second = v1_report(
            window={"start": "2026-06-26", "end": "2026-07-02"},
            metrics={"prs_merged": 8},
            next=["Launch"],
        )
        self.generate(second, "CEO Report 2026-06-26 to 2026-07-02")
        html = (self.reports_dir() / "2026-07-02-ceo-report-2026-06-26-to-2026-07-02.html").read_text(encoding="utf-8")
        self.assertIn("since the last report was run on 2026-06-25", html)
        self.assertIn("5 → 8", html)
        emitted = json.loads((self.reports_dir() / "2026-07-02-ceo-report-2026-06-26-to-2026-07-02.json").read_text(encoding="utf-8"))
        self.assertEqual(emitted["prior_report"], "reports/ceo-updates/2026-06-25-ceo-report-2026-06-19-to-2026-06-25.json")

    def test_data_json_autoload_path_gets_wow_section_too(self):
        self.generate(v1_report(), "CEO Report 2026-06-19 to 2026-06-25")
        # Seed data.json as the auto-load source for the next run (no --data-file).
        next_week = v1_report(window={"start": "2026-06-26", "end": "2026-07-02"}, metrics={"prs_merged": 9})
        (self.reports_dir() / "data.json").write_text(json.dumps(next_week), encoding="utf-8")
        self.run_cli(
            "--artifacts-dir", str(self.workspace), "--kind", "ceo-updates",
            "--title", "CEO Report 2026-06-26 to 2026-07-02",
        )
        html = (self.reports_dir() / "2026-07-02-ceo-report-2026-06-26-to-2026-07-02.html").read_text(encoding="utf-8")
        self.assertIn("since the last report was run on 2026-06-25", html)
        emitted = json.loads((self.reports_dir() / "2026-07-02-ceo-report-2026-06-26-to-2026-07-02.json").read_text(encoding="utf-8"))
        self.assertTrue(emitted["prior_report"])

    def test_explicit_date_disagreeing_with_window_end_warns_and_loses(self):
        result = self.generate(v1_report(), "CEO Report 2026-06-19 to 2026-06-25", "--date", "2026-06-30")
        self.assertIn("disagrees with window.end", result.stderr)
        self.assertTrue((self.reports_dir() / "2026-06-25-ceo-report-2026-06-19-to-2026-06-25.html").exists())

    def test_legacy_report_warns_but_still_renders(self):
        legacy = {"headline": "old style", "progress": ["thing"], "next": [], "sources": []}
        result = self.generate(legacy, "CEO Report legacy")
        self.assertIn("ceo-report schema warning", result.stderr)
        self.assertEqual(result.returncode, 0)

    def test_quiet_empty_report_warns_but_still_renders_placeholders(self):
        data = v1_report(
            headline="Quiet week: no material engineering movement.",
            progress=[],
            risks_blockers=[],
            asks_decisions=[],
            next=[],
            metrics={},
            sources=[],
        )
        result = self.generate(data, "CEO Report quiet")
        self.assertEqual(result.returncode, 0)
        self.assertIn("ceo-report schema warning", result.stderr)
        self.assertIn("no structured content", result.stderr)
        html = (self.reports_dir() / "2026-06-25-ceo-report-quiet.html").read_text(encoding="utf-8")
        self.assertIn("No progress to report for this window.", html)
        self.assertIn("No risks or blockers this window.", html)
        self.assertIn("No asks or decisions this window.", html)
        self.assertIn("Nothing queued for the next window.", html)
        self.assertIn("No evidence sources recorded for this window.", html)

    def test_empty_sources_warn_and_annotate_without_blocking(self):
        result = self.generate(v1_report(sources=[]), "CEO Report thin evidence")
        self.assertEqual(result.returncode, 0)
        self.assertIn("dzcto: no cited evidence sources", result.stderr)
        html = (self.reports_dir() / "2026-06-25-ceo-report-thin-evidence.html").read_text(encoding="utf-8")
        self.assertIn('<aside class="report-thin-evidence"', html)

    def test_populated_sources_stay_quiet_and_unannotated(self):
        result = self.generate(v1_report(), "CEO Report cited evidence")
        self.assertNotIn("no cited evidence sources", result.stderr)
        html = (self.reports_dir() / "2026-06-25-ceo-report-cited-evidence.html").read_text(encoding="utf-8")
        self.assertNotIn('<aside class="report-thin-evidence"', html)

    def test_body_only_report_is_excluded_from_evidence_warning(self):
        body_file = self.workspace.parent / "body-only.html"
        body_file.write_text("<p>Legacy body-only report.</p>", encoding="utf-8")
        result = self.run_cli(
            "--artifacts-dir", str(self.workspace), "--kind", "ceo-updates",
            "--title", "CEO Report body only", "--date", "2026-06-25",
            "--body-file", str(body_file),
        )
        self.assertNotIn("no cited evidence sources", result.stderr)
        html = (self.reports_dir() / "2026-06-25-ceo-report-body-only.html").read_text(encoding="utf-8")
        self.assertNotIn('<aside class="report-thin-evidence"', html)

    def test_high_confidence_secret_blocks_and_writes_no_report_artifact(self):
        result = self.generate(
            v1_report(headline=f"Leaked token {GITHUB_TOKEN}"),
            "CEO Report blocked",
            check=False,
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("secret detected in headline", result.stderr)
        self.assertIn("github_pat", result.stderr)
        self.assertEqual(list(self.reports_dir().glob("*.html")), [])
        self.assertEqual(list(self.reports_dir().glob("*.json")), [])
        self.assertFalse((self.reports_dir() / "data.json").exists())

    def test_high_confidence_secret_in_title_blocks_before_slug_write(self):
        data_file = self.workspace.parent / "clean-title-source.json"
        data_file.write_text(json.dumps(v1_report()), encoding="utf-8")
        result = self.run_cli(
            "--artifacts-dir", str(self.workspace), "--kind", "ceo-updates",
            "--title", f"CEO Report {GITHUB_TOKEN}", "--data-file", str(data_file),
            check=False,
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("secret detected in title", result.stderr)
        self.assertEqual(list(self.reports_dir().glob("*ghp*")), [])

        self.generate(v1_report(), "CEO Report clean")
        html = (self.reports_dir() / "2026-06-25-ceo-report-clean.html").read_text(encoding="utf-8")
        self.assertNotIn(GITHUB_TOKEN, html)
        self.assertIn("dzcto-provenance", html)

    def test_high_confidence_secret_in_metric_value_blocks(self):
        result = self.generate(
            v1_report(metrics={"deploy_key": GITHUB_TOKEN}),
            "CEO Report metric secret",
            check=False,
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("metrics.deploy_key", result.stderr)
        self.assertIn("github_pat", result.stderr)
        self.assertEqual(list(self.reports_dir().glob("*.html")), [])

    def test_high_confidence_secret_in_raw_body_blocks(self):
        body_file = self.workspace.parent / "body.html"
        body_file.write_text(f"<p>{AWS_TOKEN}</p>", encoding="utf-8")
        result = self.run_cli(
            "--artifacts-dir", str(self.workspace), "--kind", "ceo-updates",
            "--title", "CEO Report body secret", "--body-file", str(body_file),
            check=False,
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("body@", result.stderr)
        self.assertIn("aws_access_key", result.stderr)
        self.assertEqual(list(self.reports_dir().glob("*.html")), [])

    def test_low_confidence_secret_is_redacted_and_warned(self):
        result = self.generate(
            v1_report(risks_blockers=[{"risk": "Leak", "detail": LOW_GENERIC_SECRET, "severity": "medium"}]),
            "CEO Report low secret",
        )
        self.assertEqual(result.returncode, 0)
        self.assertIn("redacted", result.stderr)
        self.assertIn("generic_assignment", result.stderr)
        html = (self.reports_dir() / "2026-06-25-ceo-report-low-secret.html").read_text(encoding="utf-8")
        emitted = (self.reports_dir() / "2026-06-25-ceo-report-low-secret.json").read_text(encoding="utf-8")
        self.assertNotIn(LOW_GENERIC_VALUE, html)
        self.assertNotIn(LOW_GENERIC_VALUE, emitted)
        self.assertIn("[REDACTED:generic_assignment]", emitted)

    def test_prose_and_git_sha_survive_end_to_end(self):
        data = v1_report(
            headline="The secret to our success was focus.",
            progress=[{"area": "Core", "status": "on-track", "summary": f"Reviewed {GIT_SHA}", "items": []}],
        )
        self.generate(data, "CEO Report prose")
        html = (self.reports_dir() / "2026-06-25-ceo-report-prose.html").read_text(encoding="utf-8")
        self.assertIn("The secret to our success was focus.", html)
        self.assertIn(GIT_SHA, html)

    def test_redaction_is_stable_across_week_over_week_reports(self):
        first = v1_report(risks_blockers=[{"risk": "Leak", "detail": LOW_GENERIC_SECRET, "severity": "medium"}])
        second = v1_report(
            window={"start": "2026-06-26", "end": "2026-07-02"},
            risks_blockers=[{"risk": "Leak", "detail": LOW_GENERIC_SECRET, "severity": "medium"}],
        )
        self.generate(first, "CEO Report 2026-06-19 to 2026-06-25")
        self.generate(second, "CEO Report 2026-06-26 to 2026-07-02")
        first_json = json.loads((self.reports_dir() / "2026-06-25-ceo-report-2026-06-19-to-2026-06-25.json").read_text(encoding="utf-8"))
        second_json = json.loads((self.reports_dir() / "2026-07-02-ceo-report-2026-06-26-to-2026-07-02.json").read_text(encoding="utf-8"))
        self.assertEqual(first_json["risks_blockers"][0]["detail"], second_json["risks_blockers"][0]["detail"])
        self.assertEqual(first_json["risks_blockers"][0]["detail"], 'api_key = "[REDACTED:generic_assignment]"')
        self.assertTrue(second_json["prior_report"])
        html = (self.reports_dir() / "2026-07-02-ceo-report-2026-06-26-to-2026-07-02.html").read_text(encoding="utf-8")
        self.assertIn("report-changes", html)
        self.assertNotIn(LOW_GENERIC_VALUE, html)

    def test_secret_bearing_prior_report_is_redacted_without_blocking(self):
        prior = v1_report(
            progress=[{"area": "Legacy", "status": "at-risk", "summary": f"Remove {GITHUB_TOKEN}", "items": []}],
            window={"start": "2026-06-19", "end": "2026-06-25"},
        )
        write_report(self.reports_dir(), "2026-06-25-ceo-report-prior.json", prior)
        current = v1_report(
            window={"start": "2026-06-26", "end": "2026-07-02"},
            progress=[{"area": "Current", "status": "on-track", "summary": "Clean work", "items": ["Ship"]}],
        )
        result = self.generate(current, "CEO Report current")
        self.assertEqual(result.returncode, 0)
        self.assertIn("prior-report", result.stderr)
        self.assertIn("github_pat", result.stderr)
        html = (self.reports_dir() / "2026-07-02-ceo-report-current.html").read_text(encoding="utf-8")
        self.assertIn("report-changes", html)
        self.assertNotIn(GITHUB_TOKEN, html)
        self.assertIn("[REDACTED:github_pat]", html)


class TestRenderIndexConfigPanel(unittest.TestCase):
    """DAYZEROCTO-14 U2: the Defaults panel and its settings link."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.workspace = Path(self._tmp.name) / "ws"
        self.sidecar = self.workspace / ".dzcto"
        self.sidecar.mkdir(parents=True)
        (self.workspace / "reports" / "ceo-updates").mkdir(parents=True)
        self.addCleanup(self._tmp.cleanup)
        # render_index now reads the GLOBAL config for defaultProfile. Without this patch
        # every index test would depend on the developer's real ~/.dzcto/config.json.
        self.global_config = {"defaultProfile": "test-default"}
        patcher = mock.patch.object(artifact, "read_global_config", lambda: dict(self.global_config))
        patcher.start()
        self.addCleanup(patcher.stop)

    def render(self, config=None) -> str:
        (self.sidecar / "config.json").write_text(json.dumps(config or {}), encoding="utf-8")
        artifact.render_index(self.workspace, self.workspace, today=dt.date(2026, 7, 23))
        return (self.workspace / "index.html").read_text(encoding="utf-8")

    def settings_section(self, html: str) -> str:
        start = html.index('id="sec-settings"')
        return html[start : html.index("</details>", start)]

    def test_panel_renders_every_configured_value(self):
        section = self.settings_section(
            self.render(
                {
                    "profile": "arwen",
                    "weeklyReportDefaults": {"range": "previous_completed_week", "startDay": "Friday", "endDay": "Thursday"},
                    "ceoReportTone": "direct and calm",
                    "codeRepos": ["/Users/someone/Code/arwen-api", "/Users/someone/Code/arwen-web"],
                }
            )
        )

        self.assertIn("arwen", section)
        self.assertIn("test-default", section)
        self.assertIn("previous_completed_week", section)
        self.assertIn("direct and calm", section)
        self.assertIn("arwen-api", section)
        self.assertIn(artifact.TOOL_VERSION, section)

    def test_panel_links_to_the_settings_page(self):
        self.assertIn('href="settings.html"', self.settings_section(self.render()))

    def test_settings_section_is_collapsed_for_a_ceo_facing_share(self):
        html = self.render()
        start = html.index('id="sec-settings"')
        # The <details> opening tag must not carry `open` — operator settings stay folded away.
        self.assertNotIn("open", html[html.rindex("<details", 0, start) : html.index(">", start)])

    def test_empty_config_still_renders_a_usable_panel_and_link(self):
        section = self.settings_section(self.render())

        self.assertIn('href="settings.html"', section)
        self.assertIn(artifact.TOOL_VERSION, section)
        self.assertNotIn(">None<", section)

    def test_repo_paths_never_reach_the_shareable_index(self):
        html = self.render({"codeRepos": ["/Users/chuckblake/Documents/Code/day-zero-cto"]})
        section = self.settings_section(html)

        self.assertIn("day-zero-cto", section)
        self.assertNotIn("/Users/chuckblake/Documents/Code/day-zero-cto", section)

    def test_displayed_tone_matches_the_tone_the_prompt_card_uses(self):
        # One tone source. If the panel showed "Not set" while the copyable prompt carried
        # the built-in default, the page would state a voice the reports do not use.
        html = self.render()
        default_tone = "direct, concise, business-facing, calm about risk, explicit about asks"

        self.assertIn(default_tone, self.settings_section(html))
        self.assertIn(default_tone, html)

    def test_config_panel_does_not_migrate_into_the_kpi_window(self):
        # Pins the absence-proxy trap in TestRenderIndexWeeklyDefaultTile: that helper slices
        # 400 characters after the "Weekly default" KPI label and asserts no weekday detail.
        html = self.render({"weeklyReportDefaults": {"range": "since_last_report", "startDay": "Friday", "endDay": "Thursday", "lookbackDays": 7}})
        start = html.index('<div class="k-label">Weekly default</div>')
        window = html[start : start + 400]

        for forbidden in (" to ", "Friday", "Thursday", "7 days"):
            self.assertNotIn(forbidden, window)

    def test_regenerating_the_index_refreshes_the_displayed_config(self):
        first = self.settings_section(self.render({"weeklyReportDefaults": {"range": "since_last_report"}}))
        self.assertIn("since_last_report", first)

        second = self.settings_section(
            self.render({"weeklyReportDefaults": {"range": "previous_completed_week", "startDay": "Monday", "endDay": "Sunday"}})
        )
        self.assertIn("previous_completed_week", second)
        self.assertNotIn("since_last_report", second)


class TestSettingsFlagParity(unittest.TestCase):
    """DAYZEROCTO-14 U4: the settings page cannot document a flag the CLI does not have.

    scripts/dzcto.py builds its parser inline in main(), so there is no importable parser
    object to introspect without refactoring main() -- explicitly out of scope in the plan.
    Matching against the init subparser's source text catches the same regression (a renamed,
    removed, or invented flag) at a fraction of the blast radius.
    """

    # Operator/plumbing flags a CTO-facing settings page deliberately does not document.
    # Enumerated so the subset relationship is a decision, not an accident.
    INTENTIONALLY_UNDOCUMENTED = {"--no-save-preferences", "--no-switch-default"}

    def setUp(self):
        self.cli_source = (REPO / "scripts" / "dzcto.py").read_text(encoding="utf-8")
        start = self.cli_source.index('sub.add_parser(\n        "init"')
        end = self.cli_source.index('sub.add_parser("install-command"', start)
        self.init_block = self.cli_source[start:end]

    def declared_init_flags(self) -> set:
        return set(re.findall(r'init\.add_argument\("(--[a-z0-9-]+)"', self.init_block))

    def test_every_documented_flag_exists_in_the_init_cli(self):
        declared = self.declared_init_flags()
        self.assertTrue(declared, "failed to parse any flags out of the init subparser")

        for flag, _key, _description in artifact.INIT_REPORT_SETTING_FLAGS:
            self.assertIn(flag, declared, f"{flag} is documented on the settings page but not declared by `dzcto init`")

    def test_the_parity_check_actually_rejects_an_unknown_flag(self):
        # Guards the guard: a matcher that accepted anything would pass the test above
        # while catching no drift at all.
        self.assertNotIn("--not-a-real-flag", self.declared_init_flags())

    def test_undocumented_flags_are_an_enumerated_decision(self):
        documented = {flag for flag, _key, _description in artifact.INIT_REPORT_SETTING_FLAGS}
        missing = self.declared_init_flags() - documented

        self.assertEqual(
            missing,
            self.INTENTIONALLY_UNDOCUMENTED,
            "a `dzcto init` flag is neither documented on the settings page nor listed as "
            "intentionally undocumented -- decide which it is",
        )

    def test_skill_doc_points_at_the_generated_page_instead_of_copying_it(self):
        skill = (REPO / "skills" / "dzcto-init" / "SKILL.md").read_text(encoding="utf-8")
        self.assertIn("settings.html", skill)
        # SKILL.md's example invocation legitimately names most flags, so flag mentions are
        # not the drift signal. Reproducing the table's per-flag DESCRIPTIONS would be -- that
        # is the mapping the generated page owns as the single source of truth.
        copied = [
            description
            for _flag, _key, description in artifact.INIT_REPORT_SETTING_FLAGS
            if description in skill
        ]
        self.assertEqual(copied, [], f"SKILL.md re-copied settings-table descriptions: {copied}")


class TestRenderSettingsPage(unittest.TestCase):
    """DAYZEROCTO-14 U3: the generated, browser-viewable settings page."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.workspace = Path(self._tmp.name) / "ws"
        self.sidecar = self.workspace / ".dzcto"
        self.sidecar.mkdir(parents=True)
        (self.workspace / "reports" / "ceo-updates").mkdir(parents=True)
        self.addCleanup(self._tmp.cleanup)
        patcher = mock.patch.object(artifact, "read_global_config", lambda: {"defaultProfile": "test-default"})
        patcher.start()
        self.addCleanup(patcher.stop)

    def render(self, config=None) -> str:
        (self.sidecar / "config.json").write_text(json.dumps(config or {}), encoding="utf-8")
        artifact.render_index(self.workspace, self.workspace, today=dt.date(2026, 7, 23))
        return (self.workspace / "settings.html").read_text(encoding="utf-8")

    def test_rendering_the_index_also_writes_the_settings_page(self):
        self.render()
        self.assertTrue((self.workspace / "settings.html").exists())

    def test_page_documents_the_merge_over_semantics(self):
        page = self.render()
        self.assertIn("merges over", page)
        self.assertIn("preserved", page)

    def test_page_documents_the_default_profile_switch_and_its_opt_out(self):
        page = self.render()
        self.assertIn("defaultProfile", page)
        self.assertIn("--no-switch-default", page)

    def test_every_documented_flag_appears_on_the_page(self):
        page = self.render()
        for flag, _key, _description in artifact.INIT_REPORT_SETTING_FLAGS:
            self.assertIn(flag, page, f"{flag} missing from the settings page")

    def test_page_shows_the_readers_current_values(self):
        page = self.render(
            {
                "profile": "arwen",
                "weeklyReportDefaults": {"range": "previous_completed_week", "startDay": "Friday", "endDay": "Thursday"},
                "ceoReportTone": "direct and calm",
            }
        )
        self.assertIn("arwen", page)
        self.assertIn("previous_completed_week", page)
        self.assertIn("direct and calm", page)
        self.assertIn("test-default", page)

    def test_manifest_records_the_settings_page(self):
        self.render()
        manifest = json.loads((self.sidecar / "manifest.json").read_text(encoding="utf-8"))
        paths = [item.get("relativePath") for item in manifest["artifacts"]]
        self.assertIn("settings.html", paths)

    def test_report_pruning_never_drops_the_settings_entry(self):
        # prune_manifest_report_artifacts only removes entries under reports/; a root-level
        # page must survive a second render.
        self.render()
        artifact.prune_manifest_report_artifacts(self.workspace)
        self.render()
        manifest = json.loads((self.sidecar / "manifest.json").read_text(encoding="utf-8"))
        paths = [item.get("relativePath") for item in manifest["artifacts"]]
        self.assertIn("settings.html", paths)
        self.assertEqual(paths.count("settings.html"), 1)

    def test_regenerating_refreshes_the_settings_page_values(self):
        first = self.render({"weeklyReportDefaults": {"range": "since_last_report"}})
        self.assertIn("since_last_report", first)

        second = self.render({"weeklyReportDefaults": {"range": "previous_completed_week", "startDay": "Monday", "endDay": "Sunday"}})
        self.assertIn("previous_completed_week", second)
        self.assertNotIn("since_last_report", second)

    def test_missing_sidecar_config_still_produces_a_usable_page(self):
        page = self.render()
        self.assertIn("dzcto init", page)
        self.assertIn("--weekly-range", page)

    def test_credential_shaped_config_is_never_echoed_verbatim(self):
        page = self.render({"ceoReportTone": f"be terse; token {GITHUB_TOKEN}"})
        self.assertNotIn(GITHUB_TOKEN, page)

    def test_local_paths_never_reach_the_settings_page(self):
        page = self.render({"codeRepos": ["/Users/chuckblake/Documents/Code/day-zero-cto"]})
        self.assertIn("day-zero-cto", page)
        self.assertNotIn("/Users/chuckblake/Documents/Code/day-zero-cto", page)

    def test_settings_page_links_back_to_the_index(self):
        page = self.render()
        self.assertIn('href="index.html"', page)


class TestProfileConfigView(unittest.TestCase):
    """DAYZEROCTO-14 U1: the config view the index panel and settings page both read."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.workspace = Path(self._tmp.name) / "ws"
        self.workspace.mkdir(parents=True)
        self.addCleanup(self._tmp.cleanup)

    def view(self, config=None, global_config=None):
        return artifact.profile_config_view(config or {}, self.workspace, global_config or {})

    def test_populated_config_returns_every_displayed_value(self):
        view = self.view(
            {
                "profile": "arwen",
                "weeklyReportDefaults": {"range": "previous_completed_week", "startDay": "Friday", "endDay": "Thursday"},
                "ceoReportTone": "direct and calm",
                "codeRepos": ["/Users/someone/Code/arwen-api"],
            },
            {"defaultProfile": "arwen"},
        )

        self.assertEqual(view["profileName"], "arwen")
        self.assertEqual(view["defaultProfile"], "arwen")
        self.assertIn("previous_completed_week", view["weeklyRangeLabel"])
        self.assertEqual(view["tone"], "direct and calm")
        self.assertEqual(view["evidenceRepos"], ["arwen-api"])
        self.assertEqual(view["evidenceRepoCount"], 1)
        self.assertEqual(view["toolVersion"], artifact.TOOL_VERSION)

    def test_empty_config_still_returns_a_complete_view(self):
        view = self.view()

        for key in ("profileName", "defaultProfile", "weeklyRangeLabel", "tone", "artifactDirectory", "toolVersion"):
            self.assertIn(key, view)
            self.assertTrue(str(view[key]).strip(), f"{key} rendered empty")
            self.assertNotEqual(str(view[key]), "None", f"{key} rendered the literal string None")
        self.assertEqual(view["evidenceRepos"], [])
        self.assertEqual(view["evidenceRepoCount"], 0)

    def test_empty_repo_list_renders_a_zero_count(self):
        view = self.view({"codeRepos": []})

        self.assertEqual(view["evidenceRepos"], [])
        self.assertEqual(view["evidenceRepoCount"], 0)

    def test_non_string_and_blank_repo_entries_are_skipped(self):
        view = self.view({"codeRepos": ["/tmp/real-repo", "   ", None, 7, {"path": "/tmp/nope"}]})

        self.assertEqual(view["evidenceRepos"], ["real-repo"])
        self.assertEqual(view["evidenceRepoCount"], 1)

    def test_absolute_repo_paths_never_leak_beyond_their_basename(self):
        # The index is a shareable artifact and therefore an egress point: a repo path
        # would leak the operator's username and directory layout to every reader.
        view = self.view({"codeRepos": ["/Users/chuckblake/Documents/Code/day-zero-cto"]})

        self.assertEqual(view["evidenceRepos"], ["day-zero-cto"])
        for repo in view["evidenceRepos"]:
            self.assertNotIn("/", repo)
            self.assertNotIn("Users", repo)

    def test_tool_version_is_sourced_not_hardcoded(self):
        self.assertEqual(self.view()["toolVersion"], artifact.TOOL_VERSION)

    def test_default_profile_reads_the_global_config_through_the_injection_seam(self):
        # Without this seam every render_index test would read the developer's real
        # ~/.dzcto/config.json and stop being hermetic.
        global_path = Path(self._tmp.name) / "global.json"
        global_path.write_text(json.dumps({"defaultProfile": "injected-profile"}), encoding="utf-8")

        with mock.patch.object(artifact, "read_global_config", lambda: json.loads(global_path.read_text())):
            view = artifact.profile_config_view({}, self.workspace)

        self.assertEqual(view["defaultProfile"], "injected-profile")

    def test_missing_global_config_does_not_crash_the_view(self):
        with mock.patch.object(artifact, "read_global_config", dict):
            view = artifact.profile_config_view({}, self.workspace)

        self.assertTrue(str(view["defaultProfile"]).strip())


class TestWeeklyRangeLabel(unittest.TestCase):
    """DAYZEROCTO-14 U1: one formatter, so the panel and prompt card cannot drift apart."""

    def test_cursor_mode_suppresses_weekday_and_lookback_detail(self):
        label = artifact.weekly_range_label(
            {"weeklyReportDefaults": {"range": "since_last_report", "startDay": "Friday", "endDay": "Thursday", "lookbackDays": 7}}
        )

        self.assertEqual(label, "since_last_report")
        self.assertNotIn("Friday", label)
        self.assertNotIn(" to ", label)
        self.assertNotIn("7 days", label)

    def test_day_based_range_keeps_its_weekday_detail(self):
        label = artifact.weekly_range_label(
            {"weeklyReportDefaults": {"range": "previous_completed_week", "startDay": "Friday", "endDay": "Thursday"}}
        )

        self.assertEqual(label, "previous_completed_week; Friday to Thursday")

    def test_unconfigured_range_reports_not_configured(self):
        self.assertIn("not_configured", artifact.weekly_range_label({}))


if __name__ == "__main__":
    unittest.main()

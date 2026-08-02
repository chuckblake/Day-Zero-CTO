"""Tests for the CEO report schema v1 + week-over-week machinery (DAYZEROCTO-1)."""

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

import dzcto  # noqa: E402
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

    def authored_reports(self, pattern: str = "*.html") -> list[Path]:
        """Report artifacts this test authored, excluding init's first-run sample.

        setUp runs `--init`, which now seeds a sample CEO report (DAYZEROCTO-19). The
        blocked-write assertions below used to glob the whole folder as a proxy for "the
        blocked run wrote nothing"; that proxy breaks the moment an unrelated, legitimate
        artifact lives there. Naming what the assertion actually means preserves the
        coverage instead of relaxing it -- see
        docs/solutions/conventions/absence-proxy-assertions-break-on-additive-rendering-2026-07-23.md
        """
        return [path for path in self.reports_dir().glob(pattern) if path.stem != artifact.SAMPLE_REPORT_STEM]

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
        # Two, not one: setUp's init seeded a sample report (DAYZEROCTO-19) and the format
        # refresh deliberately includes it, so the sample never drifts off the current format.
        self.assertIn("refreshed 2 existing reports", result.stderr)
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
        self.assertEqual(self.authored_reports(), [])
        self.assertEqual(self.authored_reports("*.json"), [])
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
        self.assertEqual(self.authored_reports(), [])

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
        self.assertEqual(self.authored_reports(), [])

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
    # --no-sample-report is a one-shot init behavior with no stored config key, so it has no
    # row on a page that maps flags to persisted profile values (DAYZEROCTO-19).
    INTENTIONALLY_UNDOCUMENTED = {"--no-save-preferences", "--no-switch-default", "--no-sample-report"}

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


class TestIsSampleReport(unittest.TestCase):
    """DAYZEROCTO-19 U1: the one predicate every sample-aware surface routes through."""

    def test_explicit_true_marker_is_the_only_match(self):
        self.assertTrue(artifact.is_sample_report({"sample": True}))

    def test_missing_false_and_truthy_non_true_markers_are_real_reports(self):
        # Strictly opt-in: only a literal True marks a sample, so a stray truthy value in a
        # real report can never silently exclude it from the streak or prior-report pool.
        for data in ({}, {"sample": False}, {"sample": "yes"}, {"sample": 1}, v1_report()):
            with self.subTest(data=data):
                self.assertFalse(artifact.is_sample_report(data))

    def test_non_dict_input_is_not_a_sample(self):
        for data in (None, [], "sample", 0):
            with self.subTest(data=data):
                self.assertFalse(artifact.is_sample_report(data))


class TestBuildSampleReportData(unittest.TestCase):
    """DAYZEROCTO-19 U1: the sample payload and its `today` injection seam."""

    FIXED_TODAY = dt.date(2026, 8, 1)

    def build(self, company="Acme"):
        return artifact.build_sample_report_data(company, today=self.FIXED_TODAY)

    def test_marker_type_and_window_derive_from_the_injected_date(self):
        data = self.build()
        self.assertIs(data["sample"], True)
        self.assertEqual(data["report_type"], "weekly")
        self.assertEqual(data["company"], "Acme")
        # A completed 7-day inclusive window ending the day before the run date.
        self.assertEqual(data["window"], {"start": "2026-07-25", "end": "2026-07-31"})

    def test_today_seam_is_load_bearing(self):
        # Proves the default argument is a real seam, not decoration: a different injected
        # date must move the window. Without this the suite would silently read the clock.
        other = artifact.build_sample_report_data("Acme", today=dt.date(2026, 1, 15))
        self.assertNotEqual(other["window"], self.build()["window"])
        self.assertEqual(other["window"], {"start": "2026-01-08", "end": "2026-01-14"})

    def test_same_injected_date_is_deterministic(self):
        self.assertEqual(self.build()["window"], self.build()["window"])

    def test_sources_are_empty_never_fabricated(self):
        # The traceability guardrail: a sample must not invent citations. An empty list keeps
        # the payload schema-conformant while leaving cited_evidence_sources() empty, so the
        # existing thin-evidence banner still tells the truth.
        data = self.build()
        self.assertEqual(data["sources"], [])
        self.assertEqual(artifact.cited_evidence_sources(data), [])

    def test_payload_is_schema_v1_conformant(self):
        self.assertEqual(artifact.validate_ceo_report(self.build()), [])


class TestSampleReportRendering(unittest.TestCase):
    """DAYZEROCTO-19 U1: the banner and its single dispatch point."""

    def render(self, **overrides):
        data = artifact.build_sample_report_data("Acme", today=dt.date(2026, 8, 1))
        data.update(overrides)
        return artifact.render_structured_report("ceo-updates", data, previous_data=None)

    def test_sample_banner_renders_for_a_sample_report(self):
        self.assertIn('<aside class="report-sample"', self.render())

    def test_sample_banner_sits_above_the_thin_evidence_banner(self):
        # Both banners are true and both render; "this is an example" must be read first.
        html = self.render()
        self.assertIn('<aside class="report-thin-evidence"', html)
        self.assertLess(html.index("report-sample"), html.index("report-thin-evidence"))

    def test_real_report_renders_no_sample_banner(self):
        html = artifact.render_structured_report("ceo-updates", v1_report(), previous_data=None)
        self.assertNotIn("report-sample", html)

    def test_banner_avoids_the_metric_delta_arrow_sentinel(self):
        # test_disjoint_metrics_render_no_delta uses the arrow as an absence proxy over report
        # output, so no additive banner may spend it. See
        # docs/solutions/conventions/absence-proxy-assertions-break-on-additive-rendering-2026-07-23.md
        self.assertNotIn("→", artifact.render_sample_report_banner())

    def test_banner_css_uses_only_defined_custom_properties(self):
        css = artifact.base_css()
        self.assertIn(".report-sample {", css)
        declared = set(re.findall(r"(--[a-z0-9-]+):", css))
        used = set(re.findall(r"var\((--[a-z0-9-]+)\)", css.split(".report-sample {", 1)[1].split("}", 1)[0]))
        self.assertEqual(used - declared, set(), "sample banner CSS references an undefined token")


class TestSampleReportOnInit(unittest.TestCase):
    """DAYZEROCTO-19 U1: `dzcto init` seeds an openable, labelled sample report."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.workspace = Path(self._tmp.name) / "ws"
        self.addCleanup(self._tmp.cleanup)

    def init(self, *extra, check=True):
        return subprocess.run(
            [
                sys.executable, str(REPO / "scripts" / "dzcto_artifact.py"),
                "--init", "--artifacts-dir", str(self.workspace),
                "--company-name", "Acme", "--no-save-preferences", *extra,
            ],
            capture_output=True, text=True, check=check,
        )

    def reports_dir(self) -> Path:
        return self.workspace / "reports" / "ceo-updates"

    def sample_html(self) -> Path:
        return self.reports_dir() / f"{artifact.SAMPLE_REPORT_STEM}.html"

    def write_real_report(self, name="2026-06-25-ceo-report-real.json"):
        return write_report(self.reports_dir(), name, v1_report())

    def test_init_writes_a_labelled_sample_report(self):
        result = self.init()
        self.assertTrue(self.sample_html().exists())
        self.assertTrue(self.sample_html().with_suffix(".json").exists())
        self.assertIn("sample CEO report generated", result.stderr)
        html = self.sample_html().read_text(encoding="utf-8")
        self.assertIn('<aside class="report-sample"', html)
        self.assertIn("Sample report", html)

    def test_sample_json_carries_the_marker_and_no_fabricated_sources(self):
        self.init()
        data = json.loads(self.sample_html().with_suffix(".json").read_text(encoding="utf-8"))
        self.assertIs(data["sample"], True)
        self.assertEqual(data["sources"], [])
        self.assertTrue(data["generated_at"])

    def test_init_never_writes_the_rolling_latest_pointer(self):
        # data.json is auto-loaded by `dzcto artifact` when no --data-file is given; writing it
        # here would make a later REAL run silently render the sample's fabricated content.
        self.init()
        self.assertFalse((self.reports_dir() / "data.json").exists())

    def test_rerunning_init_does_not_duplicate_the_sample(self):
        self.init()
        first = self.sample_html().read_text(encoding="utf-8")
        self.init()
        self.assertEqual(len(list(self.reports_dir().glob(f"{artifact.SAMPLE_REPORT_STEM}*.html"))), 1)
        self.assertIn("report-sample", first)

    def test_no_sample_report_flag_suppresses_it(self):
        self.init("--no-sample-report")
        self.assertFalse(self.sample_html().exists())

    def test_wrapper_forwards_the_opt_out_flag(self):
        subprocess.run(
            [
                sys.executable, str(REPO / "scripts" / "dzcto.py"), "init",
                "--artifacts-dir", str(self.workspace), "--company-name", "Acme",
                "--no-save-preferences", "--no-sample-report",
            ],
            capture_output=True, text=True, check=True,
        )
        self.assertFalse(self.sample_html().exists())

    def test_workspace_with_a_real_report_gets_no_sample(self):
        self.init("--no-sample-report")
        self.write_real_report()
        self.init()
        self.assertFalse(self.sample_html().exists())

    def test_sample_is_never_the_prior_report_for_the_first_real_report(self):
        # The sharpest failure this feature must avoid: locate_prior_report() coerces unknown
        # report_type values to ad_hoc, so nothing about report_type alone would exclude a
        # sample -- the first real CEO report would diff against fabricated data.
        self.init()
        data_file = self.workspace.parent / "first-real.json"
        data_file.write_text(json.dumps(v1_report()), encoding="utf-8")
        subprocess.run(
            [
                sys.executable, str(REPO / "scripts" / "dzcto_artifact.py"),
                "--artifacts-dir", str(self.workspace), "--kind", "ceo-updates",
                "--title", "CEO Report 2026-06-19 to 2026-06-25", "--data-file", str(data_file),
            ],
            capture_output=True, text=True, check=True,
        )
        real = self.reports_dir() / "2026-06-25-ceo-report-2026-06-19-to-2026-06-25.html"
        emitted = json.loads(real.with_suffix(".json").read_text(encoding="utf-8"))
        self.assertIsNone(emitted["prior_report"])
        self.assertIn("no prior baseline", real.read_text(encoding="utf-8"))

    def test_secret_shaped_company_name_is_redacted_in_the_sample_data(self):
        # The sample embeds a user-supplied company name and a report artifact is an egress
        # point, so its report DATA runs through the same sanitizer as any other report.
        #
        # Scope note: the page chrome's sticky title is built from dashboard_title(company),
        # which bypasses sanitize_current_report_data on EVERY report -- verified against a
        # real report on main, so it predates this feature and is not something the sample
        # introduces or worsens. Deliberately not asserted here and not fixed in this branch;
        # filed on the issue instead of silently widening scope.
        result = subprocess.run(
            [
                sys.executable, str(REPO / "scripts" / "dzcto_artifact.py"),
                "--init", "--artifacts-dir", str(self.workspace),
                "--company-name", f"Acme {LOW_GENERIC_SECRET}", "--no-save-preferences",
            ],
            capture_output=True, text=True, check=True,
        )
        emitted = self.sample_html().with_suffix(".json").read_text(encoding="utf-8")
        self.assertNotIn(LOW_GENERIC_VALUE, emitted)
        self.assertIn("[REDACTED:generic_assignment]", emitted)
        self.assertEqual(result.returncode, 0)

    def test_sample_is_refreshed_by_a_later_init(self):
        # The one surface that deliberately INCLUDES the sample, so it never drifts off the
        # current report format.
        self.init()
        self.sample_html().write_text("<!doctype html><title>Old</title><p>stale</p>", encoding="utf-8")
        result = self.init()
        refreshed = self.sample_html().read_text(encoding="utf-8")
        self.assertIn("refreshed 1 existing report", result.stderr)
        self.assertIn("report-sample", refreshed)
        self.assertNotIn("stale", refreshed)


class TestSampleReportIsNeverEvidence(unittest.TestCase):
    """DAYZEROCTO-19 U2: every evidence-bearing selection surface skips the sample.

    One test per consumer. A seventh reader of the reports glob added later without the
    predicate should show up here as an obvious omission rather than as a wrong number on
    someone's index six months from now.
    """

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.workspace = Path(self._tmp.name) / "ws"
        self.reports = self.workspace / "reports" / "ceo-updates"
        self.reports.mkdir(parents=True)
        # project_status_checks() resolves the workspace root by probing for .dzcto/ and
        # otherwise falls back to <project>/knowledge/wiki. Without this sidecar the status
        # assertions below would look at an empty directory and pass for the wrong reason.
        (self.workspace / ".dzcto").mkdir(parents=True, exist_ok=True)
        (self.workspace / ".dzcto" / "config.json").write_text(json.dumps({"companyName": "Acme"}), encoding="utf-8")
        # render_index reads the global config for defaultProfile (DAYZEROCTO-14); pin it so
        # these tests never depend on the developer's real ~/.dzcto/config.json.
        patcher = mock.patch.object(artifact, "read_global_config", dict)
        patcher.start()
        self.addCleanup(patcher.stop)

    def write_sample(self, end="2026-07-31"):
        data = artifact.build_sample_report_data("Acme", today=dt.date.fromisoformat(end) + dt.timedelta(days=1))
        path = write_report(self.reports, f"{artifact.SAMPLE_REPORT_STEM}.json", data)
        path.with_suffix(".html").write_text("<html>sample</html>", encoding="utf-8")
        return path

    def write_real_weekly(self, end="2026-07-31", start="2026-07-25"):
        data = v1_report(window={"start": start, "end": end})
        path = write_report(self.reports, f"{end}-ceo-report-real.json", data)
        path.with_suffix(".html").write_text("<html>real</html>", encoding="utf-8")
        return path

    # 1. weekly streak
    def test_sample_contributes_no_weekly_streak_date(self):
        self.write_sample()
        self.assertEqual(artifact.weekly_report_dates(self.reports), [])

    def test_weekly_streak_is_zero_with_only_a_sample(self):
        self.write_sample()
        dates = artifact.weekly_report_dates(self.reports)
        self.assertEqual(artifact.weekly_streak(dates, dt.date(2026, 8, 1), 7), 0)

    def test_real_weekly_still_counts_alongside_a_sample(self):
        self.write_sample()
        self.write_real_weekly()
        self.assertEqual(artifact.weekly_report_dates(self.reports), [dt.date(2026, 7, 31)])

    # 2. prior report (landed in U1; pinned here beside its siblings)
    def test_sample_is_never_selected_as_a_prior_report(self):
        self.write_sample()
        current = v1_report(window={"start": "2026-08-01", "end": "2026-08-07"})
        path, data, eff, notes = artifact.locate_prior_report(self.reports / "2026-08-07-ceo-report-x.json", current)
        self.assertIsNone(path)
        self.assertIsNone(data)

    def test_real_prior_still_wins_over_a_sample(self):
        self.write_sample()
        real = self.write_real_weekly()
        current = v1_report(window={"start": "2026-08-01", "end": "2026-08-07"})
        path, _data, _eff, _notes = artifact.locate_prior_report(self.reports / "2026-08-07-ceo-report-x.json", current)
        self.assertEqual(path, real)

    # 3. since-last-report cursor (scripts/dzcto.py)
    def test_sample_is_not_a_since_last_report_cursor(self):
        self.write_sample()
        self.assertIsNone(dzcto.latest_weekly_report_cursor(self.workspace))

    def test_since_last_report_falls_back_when_only_a_sample_exists(self):
        self.write_sample()
        resolved = dzcto.resolve_since_last_report_window(self.workspace, dt.date(2026, 8, 1))
        self.assertIsNone(resolved["cursor"])
        self.assertIsNone(resolved["start"])

    def test_real_weekly_still_becomes_the_cursor_alongside_a_sample(self):
        self.write_sample()
        real = self.write_real_weekly()
        cursor = dzcto.latest_weekly_report_cursor(self.workspace)
        self.assertIsNotNone(cursor)
        self.assertEqual(cursor[0], real)
        self.assertEqual(cursor[1], dt.date(2026, 7, 31))

    # 4. dzcto status
    def test_status_reports_no_generated_reports_for_a_sample_only_workspace(self):
        self.write_sample()
        checks = {check["label"]: check for check in dzcto.project_status_checks(self.workspace)}
        reports_check = checks["CEO reports"]
        self.assertEqual(reports_check["status"], "warn")
        self.assertIn("No CEO reports generated yet", reports_check["detail"])
        self.assertIn("/dzcto-ceo-report-weekly", reports_check["command"])

    def test_status_counts_real_reports_alongside_a_sample(self):
        self.write_sample()
        self.write_real_weekly()
        checks = {check["label"]: check for check in dzcto.project_status_checks(self.workspace)}
        self.assertEqual(checks["CEO reports"]["status"], "pass")
        self.assertIn("1 generated report(s)", checks["CEO reports"]["detail"])

    # 5. the one surface that deliberately INCLUDES the sample
    def test_format_refresh_still_re_renders_the_sample(self):
        sample = self.write_sample()
        refreshed = artifact.refresh_existing_report_pages(self.workspace, "Acme")
        self.assertEqual(refreshed, 1)
        self.assertIn("report-sample", sample.with_suffix(".html").read_text(encoding="utf-8"))

    # marker discipline
    def test_a_report_without_the_marker_is_still_real_everywhere(self):
        self.write_real_weekly()
        self.assertEqual(artifact.weekly_report_dates(self.reports), [dt.date(2026, 7, 31)])
        self.assertIsNotNone(dzcto.latest_weekly_report_cursor(self.workspace))


class TestRenderIndexSampleReport(unittest.TestCase):
    """DAYZEROCTO-19 U3: the index counts real work only, and badges the sample."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.workspace = Path(self._tmp.name) / "ws"
        self.reports = self.workspace / "reports" / "ceo-updates"
        self.reports.mkdir(parents=True)
        (self.workspace / ".dzcto").mkdir(parents=True, exist_ok=True)
        (self.workspace / ".dzcto" / "config.json").write_text(json.dumps({"companyName": "Acme"}), encoding="utf-8")
        patcher = mock.patch.object(artifact, "read_global_config", dict)
        patcher.start()
        self.addCleanup(patcher.stop)

    def write_sample(self):
        data = artifact.build_sample_report_data("Acme", today=dt.date(2026, 8, 1))
        path = write_report(self.reports, f"{artifact.SAMPLE_REPORT_STEM}.json", data)
        path.with_suffix(".html").write_text(
            "<!doctype html><title>CEO Report 2026-07-25 to 2026-07-31</title>", encoding="utf-8"
        )
        return path.with_suffix(".html")

    def write_real(self, end="2026-07-31", start="2026-07-25"):
        data = v1_report(window={"start": start, "end": end})
        path = write_report(self.reports, f"{end}-ceo-report-real-{end}.json", data)
        path.with_suffix(".html").write_text(f"<!doctype html><title>CEO Report {start} to {end}</title>", encoding="utf-8")
        return path.with_suffix(".html")

    def index_html(self) -> str:
        artifact.render_index(self.workspace, self.workspace, today=dt.date(2026, 8, 1))
        return (self.workspace / "index.html").read_text(encoding="utf-8")

    def reports_section(self, html: str) -> str:
        """The rendered CEO Reports section only.

        Card-class assertions must never run against the whole page: base_css() ships a
        `.report-sample-card` rule on every index, so `assertNotIn`/index-ordering checks over
        the full document measure stylesheet order rather than card order and are silently
        meaningless. Same trap as
        docs/solutions/conventions/absence-proxy-assertions-break-on-additive-rendering-2026-07-23.md
        """
        self.assertIn('id="sec-reports"', html)
        return html.split('id="sec-reports"', 1)[1].split("</details>", 1)[0]

    def kpi(self, html: str) -> tuple[str, str]:
        match = re.search(
            r'CEO reports</div>\s*<div class="k-val">([^<]*)</div>\s*<div class="k-sub">([^<]*)</div>', html
        )
        self.assertIsNotNone(match, "CEO reports KPI tile not found")
        return match.group(1), match.group(2)

    def test_sample_only_workspace_reports_zero_and_keeps_the_empty_state(self):
        # The defect this unit fixes: before U3 a fresh install rendered "1 / Unknown date".
        self.write_sample()
        html = self.index_html()
        value, sub = self.kpi(html)
        self.assertEqual(value, "0")
        self.assertEqual(sub, "No reports yet")
        self.assertIn("Start here", html)

    def test_sample_only_workspace_still_offers_the_sample_to_open(self):
        self.write_sample()
        section = self.reports_section(self.index_html())
        self.assertIn("report-sample-card", section)
        self.assertIn(f"reports/ceo-updates/{artifact.SAMPLE_REPORT_STEM}.html", section)
        self.assertIn("Sample report", section)

    def test_real_reports_are_counted_and_the_sample_is_not(self):
        self.write_sample()
        self.write_real("2026-07-31", "2026-07-25")
        self.write_real("2026-07-24", "2026-07-18")
        value, sub = self.kpi(self.index_html())
        self.assertEqual(value, "2")
        self.assertEqual(sub, "2026-07-31")

    def test_latest_pointer_never_targets_the_sample(self):
        # sample-ceo-report.html sorts AFTER any 2026-*.html, so a reverse sort would hand the
        # sample the primary slot and the latest-report link if it were not partitioned out.
        self.write_sample()
        real = self.write_real()
        html = self.index_html()
        match = re.search(r'<a class="kpi" href="([^"]*)">', html)
        self.assertIsNotNone(match)
        self.assertEqual(match.group(1), f"reports/ceo-updates/{real.name}")

    def test_sample_never_takes_the_primary_card_slot(self):
        self.write_sample()
        real = self.write_real()
        html = self.index_html()
        primary = re.search(r'<a class="report report-primary" href="([^"]*)"', html)
        self.assertIsNotNone(primary, "a real report must hold the primary slot")
        self.assertEqual(primary.group(1), f"reports/ceo-updates/{real.name}")
        section = self.reports_section(html)
        self.assertLess(section.index("report-primary"), section.index("report-sample-card"))

    def test_sample_is_searchable_as_a_sample(self):
        self.write_sample()
        card = self.reports_section(self.index_html()).split("report-sample-card", 1)[1]
        search_attr = re.search(r'data-search-text="([^"]*)"', card)
        self.assertIsNotNone(search_attr)
        self.assertIn("sample", search_attr.group(1).lower())

    def test_workspace_without_a_sample_renders_no_sample_card(self):
        self.write_real()
        html = self.index_html()
        value, _sub = self.kpi(html)
        self.assertEqual(value, "1")
        self.assertNotIn("report-sample-card", self.reports_section(html))

    def test_sample_html_without_sibling_json_counts_as_a_real_report(self):
        # Fail-safe direction: an unreadable marker must never silently hide a real report
        # from the count. Mirrors test_malformed_json_does_not_block_index_write.
        (self.reports / f"{artifact.SAMPLE_REPORT_STEM}.html").write_text("<html>orphan</html>", encoding="utf-8")
        value, _sub = self.kpi(self.index_html())
        self.assertEqual(value, "1")

    def test_sample_card_css_uses_only_defined_custom_properties(self):
        css = artifact.base_css()
        self.assertIn(".report-sample-card", css)
        declared = set(re.findall(r"(--[a-z0-9-]+):", css))
        block = css.split(".report-sample-card", 1)[1].split("}", 1)[0]
        self.assertEqual(set(re.findall(r"var\((--[a-z0-9-]+)\)", block)) - declared, set())

    def test_index_and_status_agree_on_the_report_count(self):
        self.write_sample()
        self.write_real()
        value, _sub = self.kpi(self.index_html())
        checks = {check["label"]: check for check in dzcto.project_status_checks(self.workspace)}
        self.assertIn(f"{value} generated report(s)", checks["CEO reports"]["detail"])


if __name__ == "__main__":
    unittest.main()

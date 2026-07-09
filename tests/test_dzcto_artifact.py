"""Tests for the CEO report schema v1 + week-over-week machinery (DAYZEROCTO-1)."""

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "scripts"))

import dzcto_artifact as artifact  # noqa: E402


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


class TestReportEffectiveDate(unittest.TestCase):
    def test_window_end_wins_over_filename(self):
        date = artifact.report_effective_date(Path("2026-01-01-x.json"), {"window": {"end": "2026-06-25"}})
        self.assertEqual(date, "2026-06-25")

    def test_filename_prefix_fallback(self):
        self.assertEqual(artifact.report_effective_date(Path("2026-06-25-x.json"), {}), "2026-06-25")

    def test_unresolvable_returns_none(self):
        self.assertIsNone(artifact.report_effective_date(Path("ceo-report-old.json"), {}))


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

    def test_no_prior_renders_nothing_for_other_kinds(self):
        self.assertEqual(artifact.report_changes_html("snapshot", {}, None, ""), "")

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


class TestArtifactWritePath(unittest.TestCase):
    """End-to-end runs of the artifact CLI against a temp workspace."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.workspace = Path(self._tmp.name) / "ws"
        self.addCleanup(self._tmp.cleanup)
        self.run_cli("--init", "--artifacts-dir", str(self.workspace), "--company-name", "Acme", "--no-save-preferences")

    def run_cli(self, *cli_args):
        return subprocess.run(
            [sys.executable, str(REPO / "scripts" / "dzcto_artifact.py"), *cli_args],
            capture_output=True,
            text=True,
            check=True,
        )

    def generate(self, data, title, *extra):
        data_file = self.workspace.parent / f"{artifact.slugify(title)}.json"
        data_file.write_text(json.dumps(data), encoding="utf-8")
        return self.run_cli(
            "--artifacts-dir", str(self.workspace), "--kind", "ceo-updates",
            "--title", title, "--data-file", str(data_file), *extra,
        )

    def reports_dir(self) -> Path:
        return self.workspace / "reports" / "ceo-updates"

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


if __name__ == "__main__":
    unittest.main()

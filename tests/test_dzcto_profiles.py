"""Repository-aware profile resolution when --profile is omitted (DAYZEROCTO-20)."""

import json
import os
import subprocess
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest import mock

REPO = Path(__file__).resolve().parent.parent
DZCTO_BIN = REPO / "bin" / "dzcto"
sys.path.insert(0, str(REPO / "scripts"))

import dzcto_artifact as artifact  # noqa: E402
from dzcto_common import TOOL_VERSION  # noqa: E402

TITLE = "Profile Test"


def v1_report() -> dict:
    return {
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


def snapshot(root: Path) -> dict[str, bytes | None]:
    """Every path under root with file bytes, so any write or new path shows up."""
    return {
        str(path.relative_to(root)): (path.read_bytes() if path.is_file() else None)
        for path in sorted(root.rglob("*"))
    }


class ProfileFixture(unittest.TestCase):
    """Temporary HOME, a real local Git repository and separate artifact workspaces."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = Path(self._tmp.name).resolve()
        self.home = self.root / "home"
        self.home.mkdir()
        self.repo = self.root / "code" / "app"
        self.repo.mkdir(parents=True)
        self.git("init", "-q")
        self.nested = self.repo / "src" / "deep"
        self.nested.mkdir(parents=True)
        self.outside = self.root / "outside"
        self.outside.mkdir()
        self.workspaces = {}
        for name in ("alpha", "beta", "gamma", "default"):
            workspace = self.root / f"ws-{name}"
            workspace.mkdir()
            self.workspaces[name] = workspace
        self.data_file = self.root / "report.json"
        self.data_file.write_text(json.dumps(v1_report()), encoding="utf-8")

    def env(self) -> dict[str, str]:
        env = {key: value for key, value in os.environ.items() if not key.startswith("GIT_")}
        env["HOME"] = str(self.home)
        env["DZCTO_NO_OPEN"] = "1"
        # Discovery must describe the fixture cwd only, never an enclosing checkout.
        env["GIT_CEILING_DIRECTORIES"] = str(self.root)
        return env

    def git(self, *args: str, env_extra: dict[str, str] | None = None) -> None:
        env = self.env()
        env.update(env_extra or {})
        subprocess.run(["git", "-C", str(self.repo), *args], capture_output=True, text=True, check=True, env=env)

    def write_global(self, profiles: dict, default: str = "default") -> None:
        config_dir = self.home / ".dzcto"
        config_dir.mkdir(exist_ok=True)
        config = {"defaultProfile": default, "profiles": profiles}
        (config_dir / "config.json").write_text(json.dumps(config), encoding="utf-8")

    def profile(self, name: str, *repos) -> dict:
        return {"artifactsDir": str(self.workspaces[name]), "codeRepos": [str(repo) for repo in repos]}

    def write_matching(self, *names: str, default: str = "default") -> None:
        """Profiles in the given insertion order, each listing the fixture repository."""
        profiles = {name: self.profile(name, self.repo) for name in names}
        profiles.setdefault("default", self.profile("default", self.root / "code" / "elsewhere"))
        self.write_global(profiles, default=default)

    def run_cli(self, cwd: Path, *args: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            ["sh", str(DZCTO_BIN), *args],
            cwd=cwd,
            capture_output=True,
            text=True,
            env=self.env(),
        )

    def run_artifact(self, cwd: Path, *extra: str) -> subprocess.CompletedProcess[str]:
        return self.run_cli(
            cwd, "artifact", "--kind", "ceo-updates", "--title", TITLE, "--data-file", str(self.data_file), *extra
        )

    def reports_in(self, workspace: Path) -> list[Path]:
        return sorted(workspace.glob("reports/ceo-updates/*profile-test*.html"))

    def assert_report_only_in(self, result: subprocess.CompletedProcess[str], expected: str) -> None:
        self.assertEqual(result.returncode, 0, result.stderr)
        for name, workspace in self.workspaces.items():
            with self.subTest(workspace=name):
                if name == expected:
                    self.assertEqual(len(self.reports_in(workspace)), 1)
                else:
                    self.assertEqual(self.reports_in(workspace), [])
                    self.assertFalse((workspace / "reports").exists())


class TestRepositoryMatch(ProfileFixture):
    def test_single_match_wins_over_default_from_repo_root(self):
        self.write_matching("alpha")

        self.assert_report_only_in(self.run_artifact(self.repo), "alpha")

    def test_single_match_wins_from_a_nested_directory(self):
        self.write_matching("alpha")

        self.assert_report_only_in(self.run_artifact(self.nested), "alpha")

    def test_tilde_entry_matches_after_expansion(self):
        home_repo = self.home / "code" / "proj"
        home_repo.mkdir(parents=True)
        subprocess.run(["git", "-C", str(home_repo), "init", "-q"], capture_output=True, check=True, env=self.env())
        self.write_global(
            {
                "default": self.profile("default"),
                "alpha": {"artifactsDir": str(self.workspaces["alpha"]), "codeRepos": ["~/code/proj/"]},
            }
        )

        self.assert_report_only_in(self.run_artifact(home_repo), "alpha")

    def test_non_canonical_and_symlinked_entries_match(self):
        link = self.root / "link-to-app"
        link.symlink_to(self.repo, target_is_directory=True)
        for entry in (str(link), f"{self.repo}/../app/"):
            with self.subTest(entry=entry):
                for workspace in self.workspaces.values():
                    for report in self.reports_in(workspace):
                        report.unlink()
                self.write_global(
                    {
                        "default": self.profile("default"),
                        "alpha": {"artifactsDir": str(self.workspaces["alpha"]), "codeRepos": [entry]},
                    }
                )
                result = self.run_artifact(self.repo)
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertEqual(len(self.reports_in(self.workspaces["alpha"])), 1)
                self.assertEqual(self.reports_in(self.workspaces["default"]), [])

    def test_duplicate_entries_in_one_profile_are_not_ambiguous(self):
        self.write_global(
            {
                "default": self.profile("default"),
                "alpha": {
                    "artifactsDir": str(self.workspaces["alpha"]),
                    "codeRepos": [str(self.repo), f"{self.repo}/", f"{self.repo}/src/.."],
                },
            }
        )

        self.assert_report_only_in(self.run_artifact(self.repo), "alpha")


class TestDefaultFallback(ProfileFixture):
    def test_no_matching_profile_uses_default(self):
        self.write_global(
            {
                "alpha": self.profile("alpha", self.root / "code" / "other"),
                "default": self.profile("default"),
            }
        )

        self.assert_report_only_in(self.run_artifact(self.repo), "default")

    def test_outside_any_git_repository_uses_default(self):
        self.write_matching("alpha")

        self.assert_report_only_in(self.run_artifact(self.outside), "default")

    def test_subdirectory_entry_does_not_match_the_repository(self):
        self.write_global(
            {
                "alpha": self.profile("alpha", self.repo / "src"),
                "default": self.profile("default"),
            }
        )

        for cwd in (self.repo, self.repo / "src"):
            with self.subTest(cwd=cwd):
                result = self.run_artifact(cwd)
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertEqual(self.reports_in(self.workspaces["alpha"]), [])
                self.assertEqual(len(self.reports_in(self.workspaces["default"])), 1)

    def test_legacy_global_config_still_falls_back(self):
        config_dir = self.home / ".dzcto"
        config_dir.mkdir()
        (config_dir / "config.json").write_text(
            json.dumps({"defaultArtifactsDir": str(self.workspaces["default"]), "companyName": "Legacy"}),
            encoding="utf-8",
        )

        self.assert_report_only_in(self.run_artifact(self.repo), "default")

    def test_empty_global_config_keeps_the_missing_folder_error(self):
        config_dir = self.home / ".dzcto"
        config_dir.mkdir()
        (config_dir / "config.json").write_text("{}", encoding="utf-8")

        result = self.run_artifact(self.repo)

        self.assertEqual(result.returncode, 2)
        self.assertIn("--project, --artifacts-dir, or --home is required", result.stderr)

    def test_unavailable_git_falls_back_to_default(self):
        config = {
            "defaultProfile": "default",
            "profiles": {
                "alpha": self.profile("alpha", self.repo),
                "default": self.profile("default"),
            },
        }
        with (
            mock.patch.object(artifact, "read_global_config", return_value=config),
            mock.patch.object(artifact.subprocess, "run", side_effect=FileNotFoundError("git")),
        ):
            selected = artifact.profile_from_global()

        self.assertEqual(selected["artifactsDir"], str(self.workspaces["default"]))


class TestAmbiguousMatch(ProfileFixture):
    def expected_error(self, *names: str) -> str:
        return f"dzcto: {self.repo} is listed in more than one profile ({', '.join(names)}); pass --profile"

    def assert_refused_without_writes(self, cwd: Path, names: tuple[str, ...], *args: str) -> None:
        before = snapshot(self.root)

        result = self.run_cli(cwd, *args)

        self.assertEqual(result.returncode, 2, result.stderr)
        self.assertEqual(result.stderr.strip(), self.expected_error(*names))
        self.assertEqual(snapshot(self.root), before)

    def artifact_args(self, *extra: str) -> tuple[str, ...]:
        return ("artifact", "--kind", "ceo-updates", "--title", TITLE, "--data-file", str(self.data_file), *extra)

    def test_two_matching_profiles_exit_2_with_sorted_names(self):
        self.write_matching("beta", "alpha")

        self.assert_refused_without_writes(self.repo, ("alpha", "beta"), *self.artifact_args())

    def test_three_matching_profiles_exit_2_from_a_nested_directory(self):
        self.write_matching("gamma", "alpha", "beta")

        self.assert_refused_without_writes(self.nested, ("alpha", "beta", "gamma"), *self.artifact_args())

    def test_explicit_destination_does_not_hide_ambiguity_on_a_report(self):
        self.write_matching("beta", "alpha")

        self.assert_refused_without_writes(
            self.repo,
            ("alpha", "beta"),
            *self.artifact_args("--artifacts-dir", str(self.workspaces["gamma"])),
        )

    def test_window_and_evidence_refuse_the_same_ambiguity(self):
        self.write_matching("beta", "alpha")

        with self.subTest(command="window"):
            self.assert_refused_without_writes(self.repo, ("alpha", "beta"), "window", "--as-of", "2026-07-23")
        with self.subTest(command="evidence"):
            self.assert_refused_without_writes(
                self.repo, ("alpha", "beta"), "evidence", "--start", "2026-06-10", "--end", "2026-06-12", "--json"
            )


class TestExplicitProfile(ProfileFixture):
    def test_explicit_profile_beats_a_matching_profile(self):
        self.write_matching("alpha")
        profiles = json.loads((self.home / ".dzcto" / "config.json").read_text(encoding="utf-8"))["profiles"]
        profiles["beta"] = self.profile("beta")
        self.write_global(profiles)

        self.assert_report_only_in(self.run_artifact(self.repo, "--profile", "beta"), "beta")

    def test_explicit_profile_beats_an_ambiguous_listing(self):
        self.write_matching("beta", "alpha")

        self.assert_report_only_in(self.run_artifact(self.repo, "--profile", "alpha"), "alpha")

    def test_explicit_profile_does_not_probe_git(self):
        config = {
            "defaultProfile": "default",
            "profiles": {"alpha": self.profile("alpha", self.repo), "beta": self.profile("beta", self.repo)},
        }
        with (
            mock.patch.object(artifact, "read_global_config", return_value=config),
            mock.patch.object(artifact, "current_repo_toplevel", side_effect=AssertionError("probed git")),
        ):
            selected = artifact.profile_from_global("beta")

        self.assertEqual(selected["artifactsDir"], str(self.workspaces["beta"]))

    def test_explicit_artifacts_dir_still_sets_the_destination(self):
        self.write_matching("alpha")

        result = self.run_artifact(self.repo, "--artifacts-dir", str(self.workspaces["gamma"]))

        self.assert_report_only_in(result, "gamma")


class TestCommandsShareTheSelection(ProfileFixture):
    def test_window_reads_the_repo_matched_workspace(self):
        self.write_matching("alpha")
        alpha = self.workspaces["alpha"]
        (alpha / ".dzcto").mkdir()
        (alpha / ".dzcto" / "config.json").write_text(
            json.dumps({"weeklyReportDefaults": {"range": "since_last_report"}}), encoding="utf-8"
        )
        reports = alpha / "reports" / "ceo-updates"
        reports.mkdir(parents=True)
        cursor = {"report_type": "weekly", "company": "Acme", "window": {"start": "2026-07-08", "end": "2026-07-14"}, "headline": "x"}
        (reports / "2026-07-14-ceo-report-2026-07-08-to-2026-07-14.json").write_text(json.dumps(cursor), encoding="utf-8")
        default = self.workspaces["default"]
        (default / ".dzcto").mkdir()
        (default / ".dzcto" / "config.json").write_text(
            json.dumps({"weeklyReportDefaults": {"range": "last_7_days"}}), encoding="utf-8"
        )

        in_repo = self.run_cli(self.repo, "window", "--as-of", "2026-07-23")
        outside = self.run_cli(self.outside, "window", "--as-of", "2026-07-23")

        self.assertEqual(in_repo.returncode, 0, in_repo.stderr)
        matched = json.loads(in_repo.stdout)
        self.assertEqual(matched["mode"], "since_last_report")
        self.assertEqual(matched["start"], "2026-07-15")
        self.assertEqual(outside.returncode, 0, outside.stderr)
        fallback = json.loads(outside.stdout)
        self.assertEqual(fallback["mode"], "day_based")
        self.assertEqual(fallback["range"], "last_7_days")

    def test_evidence_uses_the_matched_profile_folder_and_repos(self):
        stamp = "2026-06-11T12:00:00+0000"
        self.git(
            "-c", "user.name=Profile Bot", "-c", "user.email=bot@example.com", "-c", "commit.gpgsign=false",
            "commit", "--allow-empty", "-q", "-m", "Alpha work",
            env_extra={"GIT_AUTHOR_DATE": stamp, "GIT_COMMITTER_DATE": stamp},
        )
        self.write_matching("alpha")
        args = ("evidence", "--start", "2026-06-10", "--end", "2026-06-12", "--json")
        generated = Path(".dzcto") / "generated" / "evidence-2026-06-10-2026-06-12.json"

        result = self.run_cli(self.repo, *args)

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout)["totals"]["commits"], 1)
        self.assertTrue((self.workspaces["alpha"] / generated).is_file())
        self.assertFalse((self.workspaces["default"] / generated).exists())

        fallback = self.run_cli(self.outside, *args)

        self.assertEqual(fallback.returncode, 0, fallback.stderr)
        self.assertEqual(json.loads(fallback.stdout)["totals"]["commits"], 0)
        self.assertTrue((self.workspaces["default"] / generated).is_file())


class TestInitAndSmoke(ProfileFixture):
    def test_explicitly_directed_init_ignores_an_ambiguous_listing(self):
        self.write_matching("beta", "alpha")
        workspace = self.root / "ws-new"

        result = self.run_cli(self.repo, "init", "--artifacts-dir", str(workspace), "--no-sample-report")

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue((workspace / "index.html").is_file())
        self.assertTrue((workspace / ".dzcto" / "config.json").is_file())

    def test_init_then_artifact_smoke(self):
        workspace = self.root / "ws-smoke"

        init = self.run_cli(
            self.outside, "init", "--artifacts-dir", str(workspace), "--profile", "smoke", "--company-name", "Smoke Co"
        )
        self.assertEqual(init.returncode, 0, init.stderr)
        report = self.run_artifact(self.outside, "--artifacts-dir", str(workspace))

        self.assertEqual(report.returncode, 0, report.stderr)
        self.assertEqual(len(self.reports_in(workspace)), 1)
        self.assertTrue((workspace / "index.html").is_file())
        saved = json.loads((self.home / ".dzcto" / "config.json").read_text(encoding="utf-8"))
        self.assertEqual(saved["defaultProfile"], "smoke")


class TestSkillsAndRelease(unittest.TestCase):
    SKILLS = ("dzcto-ceo-report", "dzcto-ceo-report-weekly")

    def step_one(self, skill: str) -> str:
        text = (REPO / "skills" / skill / "SKILL.md").read_text(encoding="utf-8")
        lines = [line for line in text.splitlines() if line.startswith("1. Resolve the profile")]
        self.assertEqual(len(lines), 1)
        return lines[0]

    def test_step_one_matches_the_repository_before_default(self):
        for skill in self.SKILLS:
            with self.subTest(skill=skill):
                step = self.step_one(skill)
                self.assertIn("if the user named a profile", step)
                self.assertIn("git rev-parse --show-toplevel", step)
                self.assertIn("profiles.*.codeRepos", step)
                self.assertIn("more than one profile matches, ask the user", step)
                self.assertLess(step.index("profiles.*.codeRepos"), step.index("`defaultProfile`"))

    def test_both_skills_share_the_same_step_one(self):
        self.assertEqual(self.step_one(self.SKILLS[0]), self.step_one(self.SKILLS[1]))

    def test_manifest_versions_match_tool_version(self):
        codex = json.loads((REPO / ".codex-plugin" / "plugin.json").read_text(encoding="utf-8"))
        claude = json.loads((REPO / ".claude-plugin" / "plugin.json").read_text(encoding="utf-8"))
        marketplace = json.loads((REPO / ".claude-plugin" / "marketplace.json").read_text(encoding="utf-8"))

        self.assertEqual(codex["version"], TOOL_VERSION)
        self.assertEqual(claude["version"], TOOL_VERSION)
        self.assertEqual(marketplace["version"], TOOL_VERSION)
        self.assertEqual([plugin["version"] for plugin in marketplace["plugins"]], [TOOL_VERSION])

    def test_claude_desktop_package_carries_updated_skills_and_helpers(self):
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp) / "bundle.zip"
            env = dict(os.environ, HOME=tmp)
            result = subprocess.run(
                ["sh", str(DZCTO_BIN), "package-claude-desktop", "--output", str(output)],
                capture_output=True,
                text=True,
                env=env,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            with zipfile.ZipFile(output) as bundle:
                names = set(bundle.namelist())
                for skill in self.SKILLS:
                    reference = bundle.read(f"day-zero-cto/references/{skill}.md").decode("utf-8")
                    self.assertIn("profiles.*.codeRepos", reference)
                self.assertIn("day-zero-cto/scripts/dzcto.py", names)


class TestPackagedHelper(ProfileFixture):
    """The Claude Desktop bundle's own helper copy, run from the extracted archive."""

    def setUp(self):
        super().setUp()
        archive = self.root / "bundle.zip"
        built = self.run_cli(self.outside, "package-claude-desktop", "--output", str(archive))
        self.assertEqual(built.returncode, 0, built.stderr)
        with zipfile.ZipFile(archive) as bundle:
            bundle.extractall(self.root / "bundle")
        self.helper = self.root / "bundle" / "day-zero-cto" / "scripts" / "dzcto.py"

    def run_packaged(self, cwd: Path) -> subprocess.CompletedProcess[str]:
        env = self.env()
        # Keep the extracted bundle byte-identical so the no-write snapshot stays exact.
        env["PYTHONDONTWRITEBYTECODE"] = "1"
        return subprocess.run(
            [sys.executable, str(self.helper), "artifact", "--kind", "ceo-updates", "--title", TITLE,
             "--data-file", str(self.data_file)],
            cwd=cwd,
            capture_output=True,
            text=True,
            env=env,
        )

    def test_packaged_helper_targets_the_repo_matched_profile(self):
        self.write_matching("alpha")

        self.assert_report_only_in(self.run_packaged(self.repo), "alpha")

    def test_packaged_helper_refuses_an_ambiguous_listing(self):
        self.write_matching("beta", "alpha")
        before = snapshot(self.root)

        result = self.run_packaged(self.repo)

        self.assertEqual(result.returncode, 2, result.stderr)
        self.assertEqual(
            result.stderr.strip(),
            f"dzcto: {self.repo} is listed in more than one profile (alpha, beta); pass --profile",
        )
        self.assertEqual(snapshot(self.root), before)

    def test_packaged_helper_warns_on_a_mood_headline_and_still_renders(self):
        headline = "A heavy hardening week: four gates shipped."
        self.data_file.write_text(json.dumps(dict(v1_report(), headline=headline)), encoding="utf-8")
        self.write_matching("alpha")

        result = self.run_packaged(self.repo)

        self.assert_report_only_in(result, "alpha")
        self.assertIn(
            'dzcto: ceo-report schema warning: headline characterizes the window ("heavy hardening week")',
            result.stderr,
        )
        [report] = self.reports_in(self.workspaces["alpha"])
        self.assertIn(headline, report.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()

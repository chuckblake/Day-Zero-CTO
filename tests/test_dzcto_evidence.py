"""End-to-end tests for window-scoped Git evidence collection."""

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


REPO = Path(__file__).resolve().parent.parent
DZCTO = REPO / "scripts" / "dzcto.py"


class TestDzctoEvidence(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = Path(self._tmp.name)
        self.home = self.root / "home"
        self.home.mkdir()
        self.artifacts = self.root / "artifacts"
        (self.artifacts / ".dzcto").mkdir(parents=True)
        self.repo = self.root / "code"
        self.repo.mkdir()
        self.git("init")
        self.git("config", "user.name", "Evidence Bot")
        self.git("config", "user.email", "evidence@example.com")
        self.commit("before.txt", "before", "Before the window", "2026-06-09")
        self.commit("start.txt", "start", "Start work DAYZEROCTO-7", "2026-06-10")
        self.git("checkout", "-b", "feature/x")
        self.commit("feature.txt", "feature", "Ship feature (#15)", "2026-06-11")
        self.git("checkout", "-")
        self.git(
            "merge",
            "--no-ff",
            "feature/x",
            "-m",
            "Merge pull request #16 from feature/x",
            date="2026-06-12",
        )
        self.commit("after.txt", "after", "After the window", "2026-06-13")
        self.write_artifact_config([self.repo])

    def git(self, *args: str, date: str | None = None) -> subprocess.CompletedProcess[str]:
        env = os.environ.copy()
        if date:
            timestamp = f"{date}T12:00:00+0000"
            env.update({"GIT_AUTHOR_DATE": timestamp, "GIT_COMMITTER_DATE": timestamp})
        return subprocess.run(
            ["git", "-C", str(self.repo), *args],
            capture_output=True,
            text=True,
            check=True,
            env=env,
        )

    def commit(self, filename: str, body: str, subject: str, date: str) -> None:
        (self.repo / filename).write_text(body, encoding="utf-8")
        self.git("add", filename)
        self.git("commit", "-m", subject, date=date)

    def write_artifact_config(self, repos: list[Path]) -> None:
        config = {"codeRepos": [str(repo) for repo in repos]}
        (self.artifacts / ".dzcto" / "config.json").write_text(json.dumps(config), encoding="utf-8")

    def run_cli(self, *args: str, check: bool = True) -> subprocess.CompletedProcess[str]:
        env = os.environ.copy()
        env["HOME"] = str(self.home)
        return subprocess.run(
            [sys.executable, str(DZCTO), "evidence", *args],
            capture_output=True,
            text=True,
            check=check,
            env=env,
        )

    def collect_window(self) -> dict:
        result = self.run_cli(
            "--artifacts-dir",
            str(self.artifacts),
            "--start",
            "2026-06-10",
            "--end",
            "2026-06-12",
            "--json",
        )
        return json.loads(result.stdout)

    def test_configured_repo_collects_only_in_window_commits_and_merge_refs(self):
        data = self.collect_window()

        self.assertEqual(data["window"], {"start": "2026-06-10", "end": "2026-06-12"})
        self.assertEqual(data["totals"], {"repos": 1, "commits": 3, "merges": 1, "authors": 1})
        subjects = [commit["subject"] for commit in data["repos"][0]["commits"]]
        self.assertEqual(
            set(subjects),
            {"Start work DAYZEROCTO-7", "Ship feature (#15)", "Merge pull request #16 from feature/x"},
        )
        self.assertNotIn("Before the window", subjects)
        self.assertNotIn("After the window", subjects)
        self.assertEqual(data["repos"][0]["merges"][0]["pr"], "#16")
        self.assertEqual(data["repos"][0]["merges"][0]["source_branch"], "feature/x")
        self.assertEqual(data["issue_refs"], ["#15", "#16", "DAYZEROCTO-7"])
        self.assertFalse(data["quiet"])
        self.assertIn(str(self.repo), data["sources"][0])
        self.assertIn("--since=2026-06-10", data["sources"][0])
        self.assertIn("--until=2026-06-12", data["sources"][0])

        generated = self.artifacts / ".dzcto" / "generated" / "evidence-2026-06-10-2026-06-12.json"
        self.assertEqual(json.loads(generated.read_text(encoding="utf-8")), data)

    def test_profile_resolves_artifact_folder_and_code_repos_without_repo_flag(self):
        config_dir = self.home / ".dzcto"
        config_dir.mkdir()
        (config_dir / "config.json").write_text(
            json.dumps(
                {
                    "defaultProfile": "acme",
                    "profiles": {
                        "acme": {"artifactsDir": str(self.artifacts), "codeRepos": [str(self.repo)]}
                    },
                }
            ),
            encoding="utf-8",
        )
        self.write_artifact_config([])

        result = self.run_cli(
            "--profile",
            "acme",
            "--start",
            "2026-06-10",
            "--end",
            "2026-06-12",
            "--json",
        )

        self.assertEqual(json.loads(result.stdout)["totals"]["commits"], 3)

    def test_empty_window_is_quiet_and_honors_output_json(self):
        output = self.root / "custom" / "evidence.json"
        result = self.run_cli(
            "--artifacts-dir",
            str(self.artifacts),
            "--start",
            "2026-06-01",
            "--end",
            "2026-06-02",
            "--output-json",
            str(output),
            "--json",
        )
        data = json.loads(result.stdout)

        self.assertTrue(data["quiet"])
        self.assertEqual(data["totals"]["commits"], 0)
        self.assertEqual(json.loads(output.read_text(encoding="utf-8")), data)

    def test_no_configured_repos_writes_valid_quiet_evidence(self):
        self.write_artifact_config([])

        data = self.collect_window()

        self.assertTrue(data["quiet"])
        self.assertEqual(data["repos"], [])
        self.assertIn("No code repositories are configured", data["note"])

    def test_unreadable_repo_is_skipped_without_failure(self):
        missing = self.root / "not-a-repo"
        missing.mkdir()
        self.write_artifact_config([missing])

        data = self.collect_window()

        self.assertTrue(data["quiet"])
        self.assertEqual(data["repos"], [])
        self.assertEqual(data["skipped_repos"][0]["repo"], str(missing.resolve()))

    def test_start_after_end_fails(self):
        result = self.run_cli(
            "--artifacts-dir",
            str(self.artifacts),
            "--start",
            "2026-06-12",
            "--end",
            "2026-06-10",
            check=False,
        )

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("--start must be on or before --end", result.stderr)

    def test_missing_folder_and_profile_fails_clearly(self):
        result = self.run_cli("--start", "2026-06-10", "--end", "2026-06-12", check=False)

        self.assertEqual(result.returncode, 2)
        self.assertIn("No artifact/report folder could be resolved", result.stderr)

    def test_evidence_command_is_hidden_from_top_level_help(self):
        result = subprocess.run(
            [sys.executable, str(DZCTO), "--help"],
            capture_output=True,
            text=True,
            check=True,
        )

        self.assertNotIn("evidence", result.stdout)

    def test_retired_commands_are_rejected(self):
        for command in (
            "lfg",
            "refresh",
            "serve",
            "check-stale",
            "collect-issue-bundle",
            "snapshot",
            "codebase-accountability",
            "learning",
        ):
            with self.subTest(command=command):
                result = subprocess.run(
                    [sys.executable, str(DZCTO), command],
                    capture_output=True,
                    text=True,
                )
                self.assertEqual(result.returncode, 2)
                self.assertIn("invalid choice", result.stderr)

    def test_status_remains_available_as_a_self_serve_command(self):
        project = self.root / "status-project"
        project.mkdir()
        result = subprocess.run(
            [sys.executable, str(DZCTO), "status", str(project), "--json"],
            capture_output=True,
            text=True,
        )

        self.assertEqual(result.returncode, 1)
        self.assertFalse(json.loads(result.stdout)["ok"])

        configured = subprocess.run(
            [sys.executable, str(DZCTO), "status", str(self.artifacts), "--json"],
            capture_output=True,
            text=True,
        )
        self.assertEqual(configured.returncode, 0)
        self.assertTrue(json.loads(configured.stdout)["ok"])


if __name__ == "__main__":
    unittest.main()

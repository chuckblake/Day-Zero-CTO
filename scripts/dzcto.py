#!/usr/bin/env python3
"""User-facing Day Zero CTO command wrapper."""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import re
import subprocess
import sys
import textwrap
import zipfile
from pathlib import Path
from typing import Any

from dzcto_artifact import (
    date_value,
    default_artifacts_dir_for_profile,
    default_artifacts_dir_from_global,
    is_sample_report,
    is_sample_report_path,
    normalize_report_folder,
    profile_from_global,
    read_json_file,
    report_effective_date,
)
from dzcto_common import (
    TOOL_VERSION,
    read_json,
    sidecar_dir,
    utc_now,
    wiki_root_for_project,
)
from dzcto_progress import Progress


REPO_ROOT = Path(__file__).resolve().parents[1]
SKILLS_DIR = REPO_ROOT / "skills"
DEFAULT_COMMAND_DEST = Path.home() / ".local" / "bin" / "dzcto"
COMMAND_SHIM_MARKER = "Day Zero CTO stable command shim"
UNKNOWN_VALUES = {"", "unknown", "tbd", "to be determined", "n/a", "none"}
ARTIFACT_FOLDER_GUIDANCE = (
    "No artifact/report folder could be resolved. Pass --artifacts-dir or configure "
    "a profile with artifactsDir in ~/.dzcto/config.json.\n"
)


def script_path(name: str) -> Path:
    return Path(__file__).resolve().with_name(name)


def run_script(name: str, args: list[str]) -> int:
    return subprocess.call([sys.executable, str(script_path(name)), *args])


def run_git(args: list[str], capture: bool = False) -> subprocess.CompletedProcess[str]:
    try:
        return subprocess.run(
            ["git", "-C", str(REPO_ROOT), *args],
            check=False,
            capture_output=capture,
            text=True,
        )
    except FileNotFoundError:
        raise SystemExit("Missing git command. Install Git or update this source folder manually, then rerun setup.")


def resolve_project(path: str) -> Path:
    return Path(path).expanduser().resolve()


def sh_quote(value: str) -> str:
    return "'" + value.replace("'", "'\"'\"'") + "'"


ISSUE_REF_PATTERN = re.compile(r"(?:[A-Z][A-Z0-9]+-\d+|#\d+|GH-\d+)", re.I)
MERGE_PR_PATTERN = re.compile(r"\bMerge pull request (?P<pr>#\d+) from (?P<branch>\S+)", re.I)


def repo_git(repo: Path, args: list[str]) -> subprocess.CompletedProcess[str]:
    try:
        return subprocess.run(["git", "-C", str(repo), *args], check=False, capture_output=True, text=True)
    except FileNotFoundError:
        raise SystemExit("Missing git command. Install Git before running codebase accountability.")


def repo_git_text(repo: Path, args: list[str]) -> str:
    result = repo_git(repo, args)
    return result.stdout.strip() if result.returncode == 0 else ""


def parse_commit_rows(output: str) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for line in output.splitlines():
        parts = line.split("\t", 4)
        if len(parts) != 5:
            continue
        full, short, date, author, subject = parts
        rows.append({"full": full, "short": short, "date": date, "author": author, "subject": subject})
    return rows


def artifact_folder_and_profile(args: argparse.Namespace) -> tuple[Path | None, dict[str, Any]]:
    profile = profile_from_global(args.profile)
    if args.artifacts_dir:
        wiki_root = Path(args.artifacts_dir).expanduser().resolve()
    elif args.profile:
        wiki_root = default_artifacts_dir_for_profile(args.profile)
    else:
        wiki_root = default_artifacts_dir_from_global()

    return wiki_root, profile


def evidence_folder_and_repos(args: argparse.Namespace) -> tuple[Path | None, list[Path]]:
    wiki_root, profile = artifact_folder_and_profile(args)
    if wiki_root is None:
        return None, []

    values = project_repos(wiki_root)
    values.extend(str(item) for item in (profile.get("codeRepos", []) or []) if str(item).strip())
    values.extend(args.repo or [])

    repos: list[Path] = []
    seen: set[str] = set()
    for value in values:
        path = Path(value).expanduser().resolve()
        key = str(path)
        if key not in seen:
            seen.add(key)
            repos.append(path)
    return wiki_root, repos


def latest_weekly_report_cursor(wiki_root: Path) -> tuple[Path, dt.date] | None:
    reports_dir = wiki_root / "reports" / normalize_report_folder("ceo-updates")
    if not reports_dir.is_dir():
        print(f"dzcto: weekly-report cursor directory not found: {reports_dir}", file=sys.stderr)
        return None

    try:
        report_paths = sorted(reports_dir.glob("*.json"))
    except OSError:
        print(f"dzcto: weekly-report cursor directory is unreadable: {reports_dir}", file=sys.stderr)
        return None

    candidates: list[tuple[dt.date, str, Path]] = []
    for path in report_paths:
        if path.name == "data.json":
            continue
        try:
            data = read_json_file(path, None)
        except (OSError, UnicodeError):
            data = None
        if not isinstance(data, dict):
            print(f"dzcto: skipping weekly-report cursor candidate {path.name} (unreadable JSON)", file=sys.stderr)
            continue

        # Sample reports are weekly-shaped examples, not coverage cursors.
        if is_sample_report(data):
            continue
        # Coverage cursors are weekly-only. Prior-report diff selection may fall back to
        # another report type because comparison and coverage are deliberately different jobs.
        if data.get("report_type") != "weekly":
            continue
        effective_date = date_value(report_effective_date(path, data))
        if effective_date is None:
            print(f"dzcto: skipping weekly-report cursor candidate {path.name} (no resolvable date)", file=sys.stderr)
            continue
        candidates.append((effective_date, path.name, path))

    if not candidates:
        return None
    effective_date, _, path = max(candidates)
    return path, effective_date


def derive_since_last_report_window(cursor_end: dt.date, as_of: dt.date) -> tuple[dt.date, dt.date, int, bool]:
    start = cursor_end + dt.timedelta(days=1)
    empty = start > as_of
    return start, as_of, max((as_of - start).days + 1, 0), empty


def resolve_since_last_report_window(wiki_root: Path, as_of: dt.date | None = None) -> dict[str, Any]:
    end = as_of or dt.date.today()
    cursor = latest_weekly_report_cursor(wiki_root)
    if cursor is None:
        return {
            "start": None,
            "end": end.isoformat(),
            "days": 0,
            "empty": False,
            "cursor": None,
        }

    report_path, cursor_end = cursor
    start, end, days, empty = derive_since_last_report_window(cursor_end, end)
    if empty:
        relation = "is after" if cursor_end > end else "already covers"
        print(
            f"dzcto: weekly-report cursor {cursor_end.isoformat()} {relation} "
            f"run date {end.isoformat()}; window is empty",
            file=sys.stderr,
        )
    return {
        "start": start.isoformat(),
        "end": end.isoformat(),
        "days": days,
        "empty": empty,
        "cursor": {
            "report": report_path.relative_to(wiki_root).as_posix(),
            "window_end": cursor_end.isoformat(),
        },
    }


def evidence_log_args(start: dt.date, end: dt.date, *, merges_only: bool = False) -> list[str]:
    args = ["log"]
    if merges_only:
        # All merge commits matter here, not just first-parent merges: evidence repos may use
        # topic-branch merges that never land directly on the current branch's first-parent chain.
        args.append("--merges")
    args.extend(
        [
            f"--since={start.isoformat()} 00:00:00",
            f"--until={end.isoformat()} 23:59:59",
            "--date=short",
            "--pretty=format:%H%x09%h%x09%ad%x09%an%x09%s",
        ]
    )
    return args


def evidence_commit(row: dict[str, str]) -> dict[str, Any]:
    return {
        "full": row["full"],
        "short": row["short"],
        "date": row["date"],
        "author": row["author"],
        "subject": row["subject"],
        "refs": unique_sorted(ISSUE_REF_PATTERN.findall(row["subject"])),
    }


def evidence_merge(row: dict[str, str]) -> dict[str, Any]:
    match = MERGE_PR_PATTERN.search(row["subject"])
    return {
        "full": row["full"],
        "short": row["short"],
        "date": row["date"],
        "author": row["author"],
        "subject": row["subject"],
        "pr": match.group("pr") if match else None,
        "source_branch": match.group("branch") if match else None,
    }


def build_evidence_data(repos: list[Path], *, start: dt.date, end: dt.date) -> dict[str, Any]:
    repo_rows: list[dict[str, Any]] = []
    skipped_repos: list[dict[str, str]] = []
    issue_refs: list[str] = []
    sources: list[str] = []
    all_authors: set[str] = set()
    total_commits = 0
    total_merges = 0

    for repo in repos:
        if repo_git(repo, ["rev-parse", "--git-dir"]).returncode != 0:
            skipped_repos.append({"repo": str(repo), "reason": "Not a readable Git repository"})
            continue

        # Git filters --since/--until on commit date; %ad deliberately surfaces author date.
        commit_output = repo_git_text(repo, evidence_log_args(start, end))
        commits = [evidence_commit(row) for row in parse_commit_rows(commit_output)]
        merges = [
            evidence_merge(row)
            for row in parse_commit_rows(repo_git_text(repo, evidence_log_args(start, end, merges_only=True)))
        ]
        branch = repo_git_text(repo, ["branch", "--show-current"]) or "detached"
        head = repo_git_text(repo, ["rev-parse", "--short", "HEAD"]) or "unknown"
        authors = unique_sorted([commit["author"] for commit in commits])
        repo_refs = unique_sorted([ref for commit in commits for ref in commit["refs"]])

        total_commits += len(commits)
        total_merges += len(merges)
        all_authors.update(authors)
        issue_refs.extend(repo_refs)
        sources.append(
            f"git log {repo} --since={start.isoformat()} --until={end.isoformat()} "
            f"— {len(commits)} commits, {len(merges)} merges"
        )
        repo_rows.append(
            {
                "repo": str(repo),
                "branch": branch,
                "head": head,
                "commits": commits,
                "merges": merges,
                "counts": {"commits": len(commits), "merges": len(merges), "authors": len(authors)},
            }
        )

    data: dict[str, Any] = {
        "window": {"start": start.isoformat(), "end": end.isoformat()},
        "repos": repo_rows,
        "totals": {
            "repos": len(repo_rows),
            "commits": total_commits,
            "merges": total_merges,
            "authors": len(all_authors),
        },
        "issue_refs": unique_sorted(issue_refs),
        "sources": sources,
        "quiet": total_commits == 0,
        "generated_at": utc_now(),
    }
    if skipped_repos:
        data["skipped_repos"] = skipped_repos
    if not repos:
        data["note"] = "No code repositories are configured; use conversation notes and prior reports as fallback evidence."
    elif not repo_rows:
        data["note"] = "No configured code repositories were readable; use conversation notes and prior reports as fallback evidence."
    return data


def unique_sorted(values: list[str]) -> list[str]:
    return sorted({value for value in values if value})


def parse_snapshot_date(value: str, label: str) -> dt.date:
    try:
        return dt.date.fromisoformat(value)
    except ValueError:
        raise SystemExit(f"{label} must use YYYY-MM-DD format, got: {value}")


def snapshot_window(args: argparse.Namespace) -> tuple[dt.date, dt.date]:
    end = parse_snapshot_date(args.end, "--end") if args.end else dt.date.today()
    if args.start:
        start = parse_snapshot_date(args.start, "--start")
    else:
        start = end - dt.timedelta(days=max(args.days, 1) - 1)
    if start > end:
        raise SystemExit(f"--start must be on or before --end, got {start} > {end}")
    return start, end


def run_evidence(args: argparse.Namespace) -> int:
    wiki_root, repos = evidence_folder_and_repos(args)
    if wiki_root is None:
        sys.stderr.write(ARTIFACT_FOLDER_GUIDANCE)
        return 2

    start, end = snapshot_window(args)
    data = build_evidence_data(repos, start=start, end=end)
    generated_dir = sidecar_dir(wiki_root) / "generated"
    generated_dir.mkdir(parents=True, exist_ok=True)
    data_path = (
        Path(args.output_json).expanduser().resolve()
        if args.output_json
        else generated_dir / f"evidence-{start.isoformat()}-{end.isoformat()}.json"
    )
    data_path.parent.mkdir(parents=True, exist_ok=True)
    data_path.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    if args.json:
        print(json.dumps(data, indent=2, sort_keys=True))
    else:
        print(data_path)
    return 0


def run_window(args: argparse.Namespace) -> int:
    wiki_root, profile = artifact_folder_and_profile(args)
    if wiki_root is None:
        sys.stderr.write(ARTIFACT_FOLDER_GUIDANCE)
        return 2

    end = parse_snapshot_date(args.as_of, "--as-of") if args.as_of else dt.date.today()
    config_path = sidecar_dir(wiki_root) / "config.json"
    try:
        config = read_json(config_path, {})
    except (OSError, UnicodeError) as error:
        print(f"dzcto: weekly-report config is unreadable: {config_path} ({error})", file=sys.stderr)
        config = {}
    local_defaults = config.get("weeklyReportDefaults") if isinstance(config, dict) else None
    profile_defaults = profile.get("weeklyReportDefaults") if isinstance(profile, dict) else None
    local_defaults = local_defaults if isinstance(local_defaults, dict) else {}
    profile_defaults = profile_defaults if isinstance(profile_defaults, dict) else {}
    range_value = (
        local_defaults["range"]
        if "range" in local_defaults
        else profile_defaults.get("range")
    )

    if range_value == "since_last_report":
        data = resolve_since_last_report_window(wiki_root, end)
        has_cursor = data["cursor"] is not None
        data.update(
            {
                "mode": "since_last_report" if has_cursor else "fallback",
                "range": range_value,
                "fallback_reason": None if has_cursor else "no_prior_weekly_report",
            }
        )
    else:
        data = {
            "mode": "day_based",
            "range": range_value,
            "start": None,
            "end": end.isoformat(),
            "days": 0,
            "empty": False,
            "cursor": None,
            "fallback_reason": None,
        }

    print(json.dumps(data, indent=2, sort_keys=True))
    return 0


def print_quickstart(project: Path | None = None) -> None:
    artifacts_path = str(project) if project else "$HOME/Documents/Acme CEO Reports"
    artifacts_arg = f'"{artifacts_path}"'
    print(
        textwrap.dedent(
            f"""
            Day Zero CTO quickstart

            1. Check the install
               dzcto doctor

            2. Initialize CEO report artifacts
               /dzcto-init

               Manual equivalent:
               dzcto init --artifacts-dir {artifacts_arg} \\
                 --profile "acme" \\
                 --company-name "Acme" \\
                 --company-description "Acme helps operators coordinate field service teams." \\
                 --weekly-range "previous_completed_week" \\
                 --weekly-start-day "Friday" \\
                 --weekly-end-day "Thursday" \\
                 --ceo-report-tone "Direct, concise, business-facing, calm about risk, explicit about asks."

               Weekly range values: previous_completed_week, last_7_days, since_last_report.

            3. Generate reports
               /dzcto-ceo-report-weekly
               /dzcto-ceo-report

            4. Open the report index
               {artifacts_arg}/index.html
            """
        ).strip()
    )


def command_reference_text(project: Path | None = None) -> str:
    artifacts_path = str(project) if project else "$HOME/Documents/Acme CEO Reports"
    artifacts_arg = f'"{artifacts_path}"'
    return textwrap.dedent(
        f"""
        Day Zero CTO command reference

        Slash commands
          /dzcto-init
              Ask for artifact/report location, company context, weekly report defaults, CEO report tone, then create index.html.
          /dzcto-ceo-report-weekly
              Generate a CEO report using the weekly defaults captured by init.
          /dzcto-ceo-report
              Ask for a concrete date range and generate a CEO report for that range.

        Local helper
          dzcto init --artifacts-dir {artifacts_arg} [--profile <name>] [--company-name <name>] [--company-description <summary>] [--company-url <url>]
                     [--weekly-range <range>] [--weekly-start-day <day>] [--weekly-end-day <day>]
                     [--weekly-lookback-days N] [--ceo-report-tone <text>] [--repo <path> ...]
              Create or refresh the artifact folder, .dzcto/config.json, reports/ceo-updates/, index.html,
              and a named profile in ~/.dzcto/config.json for cross-repo defaults.
              Weekly range values: previous_completed_week, last_7_days, since_last_report.
          dzcto artifact --profile <name> --kind ceo-updates --title <title>
                         [--date YYYY-MM-DD] [--data-file <json>] [--body-file <html>]
              Render a CEO report and refresh the index. If --profile is omitted, use defaultProfile.
          dzcto setup
              Install the local Codex plugin marketplace entry.
          dzcto install-command
              Create a stable shell command, usually ~/.local/bin/dzcto.
          dzcto update
              Pull or relink the local install, then run doctor.
          dzcto doctor
              Check install health, manifests, helper syntax, and wrappers.
          dzcto status {artifacts_arg}
              Check one CEO-report workspace and print actionable setup gaps.
          dzcto version
              Print the installed Day Zero CTO helper version.
        """
    ).strip()


def print_help_topic(topic: str | None, project: Path | None = None) -> None:
    artifacts_path = str(project) if project else "$HOME/Documents/Acme CEO Reports"
    artifacts_arg = f'"{artifacts_path}"'
    topics = {
        "commands": command_reference_text(project),
        "reports": f"""
            CEO reports

            Init captures company context, weekly defaults, and tone:
              dzcto init --artifacts-dir {artifacts_arg} --profile acme --company-name "Acme" --company-description "<one-sentence summary>" --weekly-range previous_completed_week --weekly-start-day Friday --weekly-end-day Thursday --ceo-report-tone "<tone>"

            Weekly report:
              /dzcto-ceo-report-weekly

            Custom range:
              /dzcto-ceo-report

            Reports render under:
              {artifacts_path}/reports/ceo-updates/
        """,
        "install": """
            Install/update

            Local Codex plugin install:
              bin/dzcto setup

            Stable shell command:
              bin/dzcto install-command

            Update:
              bin/dzcto update
        """,
    }
    if topic in topics:
        print(textwrap.dedent(topics[topic]).strip())
        return
    print(command_reference_text(project))


def has_real_value(value: Any) -> bool:
    if value is None:
        return False
    text = str(value).strip().lower()
    return text not in UNKNOWN_VALUES


def project_status_checks(project: Path) -> list[dict[str, str]]:
    wiki_root = project if (project / ".dzcto").exists() else wiki_root_for_project(project)
    config = read_json(sidecar_dir(wiki_root) / "config.json", {})
    repos = [str(item).strip() for item in (config.get("codeRepos", []) if isinstance(config, dict) else []) if str(item).strip()]
    checks: list[dict[str, str]] = []

    def add(status: str, label: str, detail: str, command: str = "") -> None:
        checks.append({"status": status, "label": label, "detail": detail, "command": command})

    add(
        "pass" if wiki_root.exists() else "fail",
        "Knowledge wiki",
        str(wiki_root) if wiki_root.exists() else f"Missing {wiki_root}",
        f"dzcto init {sh_quote(str(project))}",
    )

    company_name = config.get("companyName") if isinstance(config, dict) else ""
    company_description = config.get("companyDescription") if isinstance(config, dict) else ""
    add(
        "pass" if has_real_value(company_name) else "warn",
        "Company name",
        str(company_name).strip() if has_real_value(company_name) else "Missing from .dzcto/config.json; run init with --company-name",
        f"dzcto init {sh_quote(str(project))} --company-name \"<name>\"",
    )
    add(
        "pass" if has_real_value(company_description) else "warn",
        "Company description",
        "Captured" if has_real_value(company_description) else "Run init with --company-description \"<one-sentence summary>\"",
        f"dzcto init {sh_quote(str(project))} --company-description \"<summary>\"",
    )
    add(
        "pass" if repos else "warn",
        "Read-only repos",
        f"{len(repos)} configured" if repos else "No repo paths configured",
        f"dzcto init {sh_quote(str(project))} --repo \"<repo path>\"",
    )

    reports_dir = wiki_root / "reports" / "ceo-updates"
    report_count = sum(1 for path in reports_dir.glob("*.html") if not is_sample_report_path(path))
    add(
        "pass" if report_count else "warn",
        "CEO reports",
        f"{report_count} generated report(s)" if report_count else "No CEO reports generated yet",
        "Run /dzcto-ceo-report-weekly or /dzcto-ceo-report",
    )

    index_path = wiki_root / "index.html"
    add(
        "pass" if index_path.exists() else "warn",
        "CEO report index",
        str(index_path) if index_path.exists() else "Missing index.html; rerun init",
        f"dzcto init {sh_quote(str(project))}",
    )
    return checks


def print_project_status(project: Path, *, as_json: bool = False) -> int:
    checks = project_status_checks(project)
    failing = [check for check in checks if check["status"] == "fail"]
    warnings = [check for check in checks if check["status"] == "warn"]
    if as_json:
        print(json.dumps({"ok": not failing, "checks": checks}, indent=2, sort_keys=True))
        return 1 if failing else 0
    labels = {"pass": "PASS", "warn": "WARN", "fail": "FAIL"}
    for index, check in enumerate(checks, start=1):
        print(f"[{index}/{len(checks)}] {labels.get(check['status'], check['status'].upper())} {check['label']} - {check['detail']}")
        if check.get("command") and check["status"] != "pass":
            print(f"      Next: {check['command']}")
    print()
    if failing:
        print("Day Zero CTO project needs setup attention.")
    elif warnings:
        print("Day Zero CTO project is usable, with setup items remaining.")
    else:
        print("Day Zero CTO project is ready.")
    return 1 if failing else 0


def project_repos(wiki_root: Path) -> list[str]:
    config = read_json(sidecar_dir(wiki_root) / "config.json", {})
    if not isinstance(config, dict):
        return []
    return [str(item).strip() for item in (config.get("codeRepos", []) or []) if str(item).strip()]


def command_shim_text(current_bin: Path) -> str:
    return f"""#!/usr/bin/env bash
# {COMMAND_SHIM_MARKER}
# Generated by `dzcto install-command`. Edit by rerunning that command.
set -euo pipefail

canonical() {{
  local target="$1"
  (cd "$(dirname "$target")" 2>/dev/null && printf '%s/%s\\n' "$(pwd -P)" "$(basename "$target")")
}}

SELF="$(canonical "$0" 2>/dev/null || printf '%s\\n' "$0")"

try_exec() {{
  local candidate="${{1:-}}"
  shift || true
  [ -n "$candidate" ] || return 0
  [ -x "$candidate" ] || return 0
  local resolved
  resolved="$(canonical "$candidate" 2>/dev/null || printf '%s\\n' "$candidate")"
  [ "$resolved" = "$SELF" ] && return 0
  exec "$candidate" "$@"
}}

try_exec "${{DZCTO_BIN:-}}" "$@"
if [ -n "${{DZCTO_HOME:-}}" ]; then
  try_exec "$DZCTO_HOME/bin/dzcto" "$@"
fi

SOURCE_BIN={sh_quote(str(current_bin))}
case "$SOURCE_BIN" in
  *"/.claude/plugins/cache/"*|*"/.codex/plugins/cache/"*) ;;
  *) try_exec "$SOURCE_BIN" "$@" ;;
esac

try_exec "$HOME/plugins/day-zero-cto/bin/dzcto" "$@"

if command -v python3 >/dev/null 2>&1; then
  latest="$(
    python3 - <<'PY'
from pathlib import Path
import os
import re

roots = [
    "~/.claude/plugins/cache/day-zero-cto/day-zero-cto",
    "~/.codex/plugins/cache/personal/day-zero-cto",
]

def version_key(path: Path):
    version = path.parent.parent.name
    pieces = tuple(int(part) if part.isdigit() else part for part in re.split(r"([0-9]+)", version))
    try:
        modified = path.stat().st_mtime
    except OSError:
        modified = 0
    return pieces, modified

candidates = []
for root in roots:
    root_path = Path(root).expanduser()
    if not root_path.exists():
        continue
    for candidate in root_path.glob("*/bin/dzcto"):
        if candidate.is_file() and os.access(candidate, os.X_OK):
            candidates.append(candidate)

if candidates:
    print(max(candidates, key=version_key))
PY
  )"
  try_exec "$latest" "$@"
fi

try_exec "$SOURCE_BIN" "$@"

cat >&2 <<'EOF'
Could not find a Day Zero CTO dzcto helper.

Set DZCTO_HOME to a Day Zero CTO checkout/plugin folder, set DZCTO_BIN to a
specific helper path, or reinstall the plugin.
EOF
exit 127
"""


def install_command_shim(destination: Path, force: bool, progress: Progress | None = None) -> None:
    current_bin = REPO_ROOT / "bin" / "dzcto"
    destination = destination.expanduser()
    destination = destination if destination.is_absolute() else (Path.cwd() / destination).resolve()
    if destination.resolve() == current_bin.resolve():
        raise SystemExit("Refusing to overwrite the repo's own bin/dzcto wrapper.")

    if progress:
        progress.step("Install stable dzcto command", str(destination))

    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.is_symlink():
        if not force:
            raise SystemExit(f"{destination} is already a symlink. Rerun with --force to replace it.")
        destination.unlink()
    elif destination.exists():
        existing = destination.read_text(encoding="utf-8", errors="replace") if destination.is_file() else ""
        if COMMAND_SHIM_MARKER not in existing and not force:
            raise SystemExit(f"{destination} already exists and was not created by Day Zero CTO. Rerun with --force to replace it.")

    destination.write_text(command_shim_text(current_bin), encoding="utf-8")
    destination.chmod(0o755)

    if progress:
        progress.note(f"Installed stable command: {destination}")
        path_entries = os.environ.get("PATH", "").split(os.pathsep)
        if str(destination.parent) not in path_entries:
            progress.note(f"Add this to your shell profile if needed: export PATH=\"{destination.parent}:$PATH\"")
        progress.note('After that, run commands like: dzcto status "$HOME/Documents/Arwen CTO"')


def claude_desktop_skill_markdown() -> str:
    return """---
name: day-zero-cto
description: "Run the simplified Day Zero CTO CEO-report workflow: initialize artifact storage, generate weekly CEO reports, and generate custom date-range CEO reports."
---

# Day Zero CTO

Use Day Zero CTO to help an early-stage technical leader turn engineering reality into CEO-facing reports.

## Surface Notes

- In Claude Desktop chat, create or update downloadable artifacts inside Claude's available workspace unless the user has provided a mounted writable folder.
- For local filesystem report indexes, ask the user to run the local helper from a terminal or from an agent with filesystem access: `dzcto init --artifacts-dir <dir> --profile <name>` and `dzcto artifact --profile <name> --kind ceo-updates ...`.
- Global preferences live in `~/.dzcto/config.json` as named profiles under `profiles.<name>` plus `defaultProfile`, so one install can support multiple repos or CTO contexts.
- If the helper lives under a versioned plugin cache path, ask the user to run `dzcto install-command` once to create a stable `~/.local/bin/dzcto` command.
- Do not write Day Zero CTO artifacts into a code repo unless the user explicitly asks.
- Treat code repos as read-only evidence.

## Workflows

Read the matching reference file when needed:

- `references/dzcto-init.md`: initialize artifact storage, company context, weekly defaults, and CEO tone.
- `references/dzcto-ceo-report-weekly.md`: create a CEO report using configured weekly defaults.
- `references/dzcto-ceo-report.md`: create a CEO report for a custom date range.

Use concise, evidence-grounded judgment. When durable local HTML is needed, prefer the bundled Python helper if the environment can run it; otherwise provide the user with the exact `dzcto` command to run locally.
"""


def package_claude_desktop(output: Path | None) -> Path:
    destination = output or REPO_ROOT / "dist" / "day-zero-cto-claude-desktop.zip"
    destination.parent.mkdir(parents=True, exist_ok=True)
    root = "day-zero-cto"
    with zipfile.ZipFile(destination, "w", compression=zipfile.ZIP_DEFLATED) as bundle:
        bundle.writestr(f"{root}/SKILL.md", claude_desktop_skill_markdown())
        for skill_file in sorted(SKILLS_DIR.glob("*/SKILL.md")):
            bundle.write(skill_file, f"{root}/references/{skill_file.parent.name}.md")
        for script in sorted((REPO_ROOT / "scripts").glob("*.py")):
            bundle.write(script, f"{root}/scripts/{script.name}")
        bundle.write(REPO_ROOT / "README.md", f"{root}/references/README.md")
        bundle.write(REPO_ROOT / "LICENSE", f"{root}/LICENSE")
    return destination


def update_local_install(args: argparse.Namespace) -> int:
    total = 6 + (1 if args.editable_skills else 0)
    progress = Progress(total)

    progress.step("Verify update source", str(REPO_ROOT))
    git_dir = REPO_ROOT / ".git"
    if not git_dir.exists() and not args.no_pull:
        progress.note("This source folder is not a Git clone, so dzcto cannot pull updates automatically.")
        progress.note("Install from GitHub, or run dzcto update --no-pull to refresh local links only.")
        return 1
    if not git_dir.exists():
        progress.note("No .git directory found; skipping Git checks and refreshing local links only.")

    progress.step("Check local edits")
    if git_dir.exists():
        status = run_git(["status", "--porcelain"], capture=True)
        if status.returncode:
            if status.stderr:
                progress.note(status.stderr.strip())
            return status.returncode
        dirty_lines = [line for line in status.stdout.splitlines() if line.strip()]
        if dirty_lines and not args.allow_dirty and not args.no_pull:
            progress.note("Local edits found; refusing to run git pull over a dirty worktree.")
            for line in dirty_lines[:12]:
                progress.note(line)
            if len(dirty_lines) > 12:
                progress.note(f"...and {len(dirty_lines) - 12} more")
            progress.note("Commit or stash local edits, then rerun dzcto update.")
            progress.note("To refresh install links without pulling, run dzcto update --no-pull.")
            return 1
        if dirty_lines and args.no_pull:
            progress.note("Local edits found; continuing because --no-pull was provided.")
        elif dirty_lines:
            progress.note("Local edits found; continuing because --allow-dirty was provided.")
        else:
            progress.note("Working tree is clean.")

    progress.step("Pull latest repo changes" if not args.no_pull else "Skip repo pull")
    if args.no_pull:
        progress.note("--no-pull provided")
    else:
        pull = run_git(["pull", "--ff-only"], capture=True)
        for line in (pull.stdout + pull.stderr).strip().splitlines():
            progress.note(line)
        if pull.returncode:
            progress.note("Pull failed. Resolve the Git issue, then rerun dzcto update.")
            return pull.returncode

    progress.step("Refresh Codex plugin marketplace entry")
    setup_args = []
    if args.plugin_link:
        setup_args.extend(["--plugin-link", args.plugin_link])
    if args.marketplace_file:
        setup_args.extend(["--marketplace-file", args.marketplace_file])
    code = run_script("install_local_marketplace.py", setup_args)
    if code:
        return code

    if args.editable_skills:
        progress.step("Refresh editable Codex skill links")
        skill_args = []
        if args.editable_skills_dir:
            skill_args.extend(["--dest-dir", args.editable_skills_dir])
        code = run_script("install_local_skills.py", skill_args)
        if code:
            return code

    progress.step("Run install doctor")
    doctor_args = ["--project", str(resolve_project(args.project))] if args.project else []
    code = run_script("dzcto_doctor.py", doctor_args)
    if code:
        return code

    progress.step("Next step", "restart Codex Desktop, reload Claude Code plugins, or start a fresh agent session")
    return 0


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(prog="dzcto", description="Day Zero CTO local skill helper")
    sub = parser.add_subparsers(dest="command", required=True, metavar="command")

    help_cmd = sub.add_parser("help", help="Print Day Zero CTO workflow help")
    help_cmd.add_argument(
        "topic",
        nargs="?",
        choices=["reports", "commands", "install"],
        help="Optional help topic",
    )
    help_cmd.add_argument("--project", help="Optional project folder for command examples")

    quickstart = sub.add_parser("quickstart", help="Print the self-serve startup guide")
    quickstart.add_argument("--project", help="Optional project folder for command examples")

    sub.add_parser("version", help="Print the Day Zero CTO helper version")

    setup = sub.add_parser("setup", help="Install Day Zero CTO for Codex Desktop")
    setup.add_argument("--editable-skills", action="store_true", help="Also link skills into ~/.codex/skills for active Codex development")
    setup.add_argument("--plugin-link", help="Where to create the local plugin symlink")
    setup.add_argument("--marketplace-file", help="Codex plugin marketplace/settings JSON file")
    setup.add_argument("--editable-skills-dir", help="Destination directory for editable skill symlinks")
    setup.add_argument("--wiki-project", help="Optional project folder to initialize during setup")
    setup.add_argument("--company-name")
    setup.add_argument("--company-description")
    setup.add_argument("--company-url")
    setup.add_argument("--report-prompt-context", help="Extra context appended to report and operating prompt cards")
    setup.add_argument("--repo", action="append", default=[], help="Read-only code repository path for the wiki; may be repeated")

    update = sub.add_parser("update", help="Pull latest Day Zero CTO and refresh a local install")
    update.add_argument("--no-pull", action="store_true", help="Refresh local install links without running git pull")
    update.add_argument("--allow-dirty", action="store_true", help="Allow git pull even when local edits are present")
    update.add_argument("--editable-skills", action="store_true", help="Also refresh editable Codex skill links")
    update.add_argument("--plugin-link", help="Where the local plugin symlink should point")
    update.add_argument("--marketplace-file", help="Codex plugin marketplace/settings JSON file")
    update.add_argument("--editable-skills-dir", help="Destination directory for editable skill symlinks")
    update.add_argument("--project", help="Optional project folder for doctor checks")

    doctor = sub.add_parser("doctor", help="Check install and optional project health")
    doctor.add_argument("--project", help="Optional project folder")

    init = sub.add_parser(
        "init",
        help="Create or refresh a simplified CEO-report workspace",
        epilog="--company-name, --company-url, --company-description, --report-prompt-context, and --repo are saved to "
        "<project>/knowledge/wiki/.dzcto/config.json and persist across refreshes. You can also edit that file by hand.",
    )
    init.add_argument("project", nargs="?", help="Project folder, such as ~/Documents/Acme. Optional when --artifacts-dir is provided.")
    init.add_argument("--artifacts-dir", help="Folder that directly stores CEO report artifacts, index.html, reports/, and .dzcto/")
    init.add_argument("--profile", help="Named global profile in ~/.dzcto/config.json, such as getmusic")
    init.add_argument("--company-name", help="Company name; persisted as companyName in .dzcto/config.json")
    init.add_argument("--company-description", help="Short company summary; persisted as companyDescription in .dzcto/config.json")
    init.add_argument("--company-url", help="Company URL; persisted as companyUrl in .dzcto/config.json")
    init.add_argument("--report-prompt-context", help="Extra context appended to report and operating prompt cards; persisted as reportPromptContext in .dzcto/config.json")
    init.add_argument("--weekly-range", help="Default CEO weekly report range, such as previous_completed_week or last_7_days")
    init.add_argument("--weekly-start-day", help="Default weekly report start day, such as Monday")
    init.add_argument("--weekly-end-day", help="Default weekly report end day, such as Sunday")
    init.add_argument("--weekly-lookback-days", type=int, help="Default rolling lookback days for weekly CEO reports")
    init.add_argument("--ceo-report-tone", help="Tone guidance for CEO reports; persisted as ceoReportTone in .dzcto/config.json")
    init.add_argument("--no-sample-report", action="store_true", help="Skip the first-run sample CEO report")
    init.add_argument("--no-save-preferences", action="store_true", help="Do not update ~/.dzcto/config.json")
    init.add_argument("--no-switch-default", action="store_true", help="Update the named profile without making it the global default")
    init.add_argument("--repo", action="append", default=[], help="Read-only code repository path; may be repeated. Persisted as codeRepos in .dzcto/config.json")

    install_command = sub.add_parser("install-command", help="Install a stable dzcto command shim, such as ~/.local/bin/dzcto")
    install_command.add_argument("--dest", default=str(DEFAULT_COMMAND_DEST), help="Destination command path")
    install_command.add_argument("--force", action="store_true", help="Replace an existing command at --dest")

    status = sub.add_parser("status", help=argparse.SUPPRESS)
    status.add_argument("project", help="Artifact/report folder or legacy project folder")
    status.add_argument("--json", action="store_true", help="Print JSON")

    claude_desktop = sub.add_parser("package-claude-desktop", help="Build an uploadable Claude Desktop custom skill zip")
    claude_desktop.add_argument("--output", help="Zip output path")

    evidence = sub.add_parser("evidence", help=argparse.SUPPRESS)
    evidence.add_argument("--artifacts-dir", help="Folder that directly stores reports and .dzcto/config.json")
    evidence.add_argument("--profile", help="Named global profile to use when --artifacts-dir is omitted")
    evidence.add_argument("--repo", action="append", default=[], help="Additional read-only code repository path; may be repeated")
    evidence.add_argument("--start", help="Window start date, YYYY-MM-DD. Defaults to --end minus --days + 1")
    evidence.add_argument("--end", help="Window end date, YYYY-MM-DD. Defaults to today")
    evidence.add_argument("--days", type=int, default=7, help="Default window length when --start is omitted")
    evidence.add_argument("--output-json", help="Write evidence JSON to this path")
    evidence.add_argument("--json", action="store_true", help="Print evidence JSON")

    window = sub.add_parser("window", help=argparse.SUPPRESS)
    window.add_argument("--artifacts-dir", help="Folder that directly stores reports and .dzcto/config.json")
    window.add_argument("--profile", help="Named global profile to use when --artifacts-dir is omitted")
    window.add_argument("--as-of", help="Run date, YYYY-MM-DD. Defaults to today")

    artifact = sub.add_parser("artifact", help="Generate a structured report artifact")
    artifact.add_argument("--project")
    artifact.add_argument("--artifacts-dir", help="Folder that directly stores index.html, reports/, and .dzcto/")
    artifact.add_argument("--profile", help="Named global profile to use when --artifacts-dir is omitted")
    artifact.add_argument("--kind", required=True)
    artifact.add_argument("--title", required=True)
    artifact.add_argument("--date")
    artifact.add_argument("--data-file")
    artifact.add_argument("--body-file")
    artifact.add_argument("--open", action="store_true", help="Open the rendered report and print a share recipe")

    sub._choices_actions = [action for action in sub._choices_actions if action.help != argparse.SUPPRESS]

    args = parser.parse_args(argv)

    if args.command == "help":
        print_help_topic(args.topic, resolve_project(args.project) if args.project else None)
        return 0

    if args.command == "quickstart":
        print_quickstart(resolve_project(args.project) if args.project else None)
        return 0

    if args.command == "version":
        print(TOOL_VERSION)
        return 0

    if args.command == "setup":
        total = 3 + (1 if args.editable_skills else 0) + (1 if args.wiki_project else 0)
        progress = Progress(total)
        progress.step("Install Codex plugin marketplace entry")
        setup_args = []
        if args.plugin_link:
            setup_args.extend(["--plugin-link", args.plugin_link])
        if args.marketplace_file:
            setup_args.extend(["--marketplace-file", args.marketplace_file])
        code = run_script("install_local_marketplace.py", setup_args)
        if code:
            return code
        if args.editable_skills:
            progress.step("Install editable Codex skill links")
            skill_args = []
            if args.editable_skills_dir:
                skill_args.extend(["--dest-dir", args.editable_skills_dir])
            code = run_script("install_local_skills.py", skill_args)
            if code:
                return code
        if args.wiki_project:
            progress.step("Initialize project wiki")
            init_args = ["--project", str(resolve_project(args.wiki_project)), "--init"]
            if args.company_name:
                init_args.extend(["--company-name", args.company_name])
            if args.company_description:
                init_args.extend(["--company-description", args.company_description])
            if args.company_url:
                init_args.extend(["--company-url", args.company_url])
            if args.report_prompt_context:
                init_args.extend(["--report-prompt-context", args.report_prompt_context])
            for repo in args.repo:
                init_args.extend(["--repo", repo])
            code = run_script("dzcto_artifact.py", init_args)
            if code:
                return code
        progress.step("Run install doctor")
        doctor_args = ["--project", str(resolve_project(args.wiki_project))] if args.wiki_project else []
        code = run_script("dzcto_doctor.py", doctor_args)
        if code:
            return code
        progress.step("Next step", "restart Codex Desktop or start a fresh session")
        return 0

    if args.command == "update":
        return update_local_install(args)

    if args.command == "doctor":
        doctor_args = ["--project", args.project] if args.project else []
        return run_script("dzcto_doctor.py", doctor_args)

    if args.command == "init":
        init_args = ["--init"]
        if args.project:
            init_args.extend(["--project", str(resolve_project(args.project))])
        if args.artifacts_dir:
            init_args.extend(["--artifacts-dir", str(Path(args.artifacts_dir).expanduser().resolve())])
        if args.profile:
            init_args.extend(["--profile", args.profile])
        if args.company_name:
            init_args.extend(["--company-name", args.company_name])
        if args.company_description:
            init_args.extend(["--company-description", args.company_description])
        if args.company_url:
            init_args.extend(["--company-url", args.company_url])
        if args.report_prompt_context:
            init_args.extend(["--report-prompt-context", args.report_prompt_context])
        if args.weekly_range:
            init_args.extend(["--weekly-range", args.weekly_range])
        if args.weekly_start_day:
            init_args.extend(["--weekly-start-day", args.weekly_start_day])
        if args.weekly_end_day:
            init_args.extend(["--weekly-end-day", args.weekly_end_day])
        if args.weekly_lookback_days is not None:
            init_args.extend(["--weekly-lookback-days", str(args.weekly_lookback_days)])
        if args.ceo_report_tone:
            init_args.extend(["--ceo-report-tone", args.ceo_report_tone])
        if args.no_sample_report:
            init_args.append("--no-sample-report")
        if args.no_save_preferences:
            init_args.append("--no-save-preferences")
        if args.no_switch_default:
            init_args.append("--no-switch-default")
        for repo in args.repo:
            init_args.extend(["--repo", repo])
        return run_script("dzcto_artifact.py", init_args)

    if args.command == "install-command":
        progress = Progress(2)
        install_command_shim(Path(args.dest), args.force, progress)
        progress.step("Next step", "open a new shell or make sure the destination directory is on PATH")
        return 0

    if args.command == "status":
        return print_project_status(resolve_project(args.project), as_json=args.json)

    if args.command == "package-claude-desktop":
        output = Path(args.output).expanduser().resolve() if args.output else None
        path = package_claude_desktop(output)
        print(path)
        return 0

    if args.command == "evidence":
        return run_evidence(args)

    if args.command == "window":
        return run_window(args)

    if args.command == "artifact":
        artifact_args = ["--kind", args.kind, "--title", args.title]
        if args.project:
            artifact_args.extend(["--project", args.project])
        if args.artifacts_dir:
            artifact_args.extend(["--artifacts-dir", args.artifacts_dir])
        if args.profile:
            artifact_args.extend(["--profile", args.profile])
        if args.date:
            artifact_args.extend(["--date", args.date])
        if args.data_file:
            artifact_args.extend(["--data-file", args.data_file])
        if args.body_file:
            artifact_args.extend(["--body-file", args.body_file])
        if args.open:
            artifact_args.append("--open")
        return run_script("dzcto_artifact.py", artifact_args)

    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))

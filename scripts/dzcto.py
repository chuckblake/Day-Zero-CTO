#!/usr/bin/env python3
"""User-facing Day Zero CTO command wrapper."""

from __future__ import annotations

import argparse
import datetime as dt
import http.server
import json
import mimetypes
import os
import re
import subprocess
import sys
import textwrap
import urllib.parse
import zipfile
from pathlib import Path
from typing import Any

from dzcto_artifact import (
    CORE_DOCS,
    REPORT_FOLDERS,
    active_registry_risks,
    array_value,
    build_decision_registry,
    build_risk_registry,
    cadence_alerts,
    core_doc_html_name,
    dates_in_text,
    decision_detail_relative_path,
    display_command,
    due_decision_entries,
    due_risk_entries,
    item_headline,
    parse_cadence_rules,
    registry_decisions,
    read_learning_items,
    report_lead_summary,
    report_run_date,
    read_risk_entries,
    risk_detail_relative_path,
    severity_rank,
    snippet,
    text_value,
    value_at,
)
from dzcto_common import (
    TOOL_NAME,
    TOOL_VERSION,
    ensure_sidecar,
    read_json,
    redact,
    redacted_json_text,
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


def require_existing_wiki(project: Path) -> None:
    """Stop commands that operate on an existing project from silently creating
    the wrong directory when an agent passes a company NAME instead of the
    project FOLDER path."""
    wiki = wiki_root_for_project(project)
    if not wiki.exists():
        sys.stderr.write(
            f"No Day Zero CTO wiki found at {wiki}.\n"
            f'Pass the project FOLDER path (for example "$HOME/Documents/Acme CTO"), '
            f"not the company name.\n"
            f"If that resolved path is correct and the project is new, run `dzcto init` on it first.\n"
        )
        raise SystemExit(2)


def refresh_project(project: Path) -> int:
    return run_script("dzcto_artifact.py", ["--project", str(project), "--init"])


def sh_quote(value: str) -> str:
    return "'" + value.replace("'", "'\"'\"'") + "'"


def shell_project(project: Path | None) -> str:
    return f'"{project}"' if project else '"$HOME/Documents/Acme CTO"'


ISSUE_REF_PATTERN = re.compile(r"(?:[A-Z][A-Z0-9]+-\d+|#\d+|GH-\d+)", re.I)
TEST_FILE_PATTERN = re.compile(r"(^|/)(test|tests|spec|__tests__)/|(_test|_spec|\.test|\.spec)\.", re.I)
SOURCE_FILE_PATTERN = re.compile(r"\.(rb|py|js|jsx|ts|tsx|go|rs|java|kt|swift|php|cs|sql)$", re.I)
DEPENDENCY_FILE_PATTERN = re.compile(r"(^|/)(Gemfile|Gemfile\.lock|package\.json|package-lock\.json|pnpm-lock\.yaml|yarn\.lock|requirements.*\.txt|pyproject\.toml|poetry\.lock|go\.mod|go\.sum|Cargo\.toml|Cargo\.lock)$", re.I)
HIGH_ATTENTION_PATTERNS = [
    ("Security or auth", re.compile(r"(auth|authorization|permission|security|session|jwt|password|credential|secret|token|csp|csrf)", re.I)),
    ("PHI / privacy / compliance", re.compile(r"(phi|hipaa|patient|claim|billing|payment|diagnosis|medical|privacy|compliance|audit)", re.I)),
    ("Data model or migration", re.compile(r"(schema|migration|db/|database|model|policy)", re.I)),
    ("Infrastructure or deploy", re.compile(r"(deploy|docker|kamal|terraform|infra|ci|github/workflows|heroku|kubernetes|helm)", re.I)),
]


def repo_git(repo: Path, args: list[str]) -> subprocess.CompletedProcess[str]:
    try:
        return subprocess.run(["git", "-C", str(repo), *args], check=False, capture_output=True, text=True)
    except FileNotFoundError:
        raise SystemExit("Missing git command. Install Git before running codebase accountability.")


def repo_git_text(repo: Path, args: list[str]) -> str:
    result = repo_git(repo, args)
    return result.stdout.strip() if result.returncode == 0 else ""


def project_code_repos(project: Path, extra_repos: list[str] | None = None) -> list[Path]:
    wiki_root = wiki_root_for_project(project)
    config = read_json(sidecar_dir(wiki_root) / "config.json", {})
    values = [str(item) for item in config.get("codeRepos", []) if str(item).strip()] if isinstance(config, dict) else []
    values.extend(extra_repos or [])
    if not values and (project / ".git").exists():
        values.append(str(project))

    repos: list[Path] = []
    seen: set[str] = set()
    for value in values:
        path = Path(value).expanduser().resolve()
        key = str(path)
        if key not in seen:
            seen.add(key)
            repos.append(path)
    return repos


def latest_structured_report_data(wiki_root: Path, kind: str) -> dict[str, Any] | None:
    report_dir = wiki_root / "reports" / kind
    paths = [path for path in sorted(report_dir.glob("*.json"), reverse=True) if path.name != "data.json"]
    for path in paths:
        data = read_json(path, None)
        if isinstance(data, dict):
            return data
    return None


def accountability_since(project: Path, explicit_since: str | None, days: int) -> tuple[str, str]:
    if explicit_since:
        return explicit_since, "explicit --since"
    return f"{max(days, 1)} days ago", f"default {max(days, 1)} day window"


def parse_commit_rows(output: str) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for line in output.splitlines():
        parts = line.split("\t", 4)
        if len(parts) != 5:
            continue
        full, short, date, author, subject = parts
        rows.append({"full": full, "short": short, "date": date, "author": author, "subject": subject})
    return rows


def commit_files(repo: Path, commit: str) -> list[str]:
    output = repo_git_text(repo, ["show", "--pretty=format:", "--name-only", "--no-renames", commit])
    return [line.strip() for line in output.splitlines() if line.strip()]


def subsystem_for(path: str) -> str:
    parts = Path(path).parts
    if not parts:
        return "(root)"
    if len(parts) == 1:
        return "(root)"
    return parts[0]


def unique_sorted(values: list[str]) -> list[str]:
    return sorted({value for value in values if value})


def build_codebase_accountability_data(project: Path, repos: list[Path], *, since_expr: str, since_reason: str) -> dict[str, Any]:
    generated_at = utc_now()
    management_exceptions: list[dict[str, str]] = []
    changed_subsystems: list[dict[str, str]] = []
    provenance: list[dict[str, str]] = []
    guardrail_checks: list[dict[str, str]] = []
    agent_activity_map: dict[str, dict[str, Any]] = {}
    agent_activity: list[dict[str, str]] = []
    change_units: list[dict[str, str]] = []
    risk_signals: list[dict[str, str]] = []
    decision_points: list[dict[str, str]] = []
    questions: list[dict[str, str]] = []
    sources: list[str] = []

    total_commits = 0
    total_files = 0
    all_issue_refs: list[str] = []
    dirty_repos = 0

    wiki_root = wiki_root_for_project(project)
    guardrails_path = wiki_root / "core" / "ENGINEERING_GUARDRAILS.md"
    guardrails_text = guardrails_path.read_text(encoding="utf-8", errors="replace") if guardrails_path.exists() else ""
    if guardrails_path.exists():
        guardrail_checks.append(
            {
                "guardrail": "Engineering guardrails source",
                "status": "Present",
                "evidence": "core/ENGINEERING_GUARDRAILS.md exists.",
                "action": "Keep this file current with the invariants one CTO expects agents to preserve.",
            }
        )
        sources.append(str(guardrails_path.relative_to(wiki_root)))
    else:
        finding = "No ENGINEERING_GUARDRAILS.md source file is configured"
        evidence = "The accountability report can inspect code movement, but there is no explicit invariant list to compare agent work against."
        action = "Create knowledge/wiki/core/ENGINEERING_GUARDRAILS.md with architectural, security, privacy, data-flow, and review-owner rules."
        management_exceptions.append({"severity": "Medium", "finding": finding, "evidence": evidence, "action": action, "owner": "CTO"})
        guardrail_checks.append({"guardrail": "Engineering guardrails source", "status": "Needs setup", "evidence": evidence, "action": action})
        decision_points.append({"decision": "Define codebase accountability guardrails", "context": evidence, "owner": "CTO", "needed_by": "Before relying on agent-fleet reports as an oversight layer"})

    for repo in repos:
        repo_label = repo.name
        sources.append(str(repo))
        if not repo.exists() or not (repo / ".git").exists():
            finding = f"Configured repo is not a readable Git repository: {repo}"
            management_exceptions.append({"severity": "High", "finding": finding, "evidence": str(repo), "action": "Fix the configured codeRepos entry or remove it from .dzcto/config.json.", "owner": "CTO"})
            risk_signals.append({"risk": finding, "evidence": str(repo), "impact": "Accountability report cannot cover work happening in this source.", "severity": "High", "mitigation": "Fix or remove the repo path.", "source": "Codebase Accountability report"})
            continue

        branch = repo_git_text(repo, ["branch", "--show-current"]) or "detached"
        head = repo_git_text(repo, ["rev-parse", "--short", "HEAD"]) or "unknown"
        dirty_lines = [line for line in repo_git_text(repo, ["status", "--porcelain"]).splitlines() if line.strip()]
        if dirty_lines:
            dirty_repos += 1
            finding = f"{repo_label} has uncommitted local changes"
            evidence = f"{len(dirty_lines)} dirty working-tree entries on {branch}@{head}."
            action = "Commit, stash, or intentionally exclude local work before treating the report as a clean post-merge accountability view."
            management_exceptions.append({"severity": "Medium", "finding": finding, "evidence": evidence, "action": action, "owner": "Repo owner"})
            risk_signals.append({"risk": finding, "evidence": evidence, "impact": "Uncommitted changes can hide agent output from PR, issue, and review provenance.", "severity": "Medium", "mitigation": action, "source": "Codebase Accountability report"})

        log_output = repo_git_text(
            repo,
            [
                "log",
                f"--since={since_expr}",
                "--date=short",
                "--pretty=format:%H%x09%h%x09%ad%x09%an%x09%s",
                "--max-count=200",
            ],
        )
        commits = parse_commit_rows(log_output)
        total_commits += len(commits)

        touched_files: list[str] = []
        commit_issue_refs: list[str] = []
        for commit in commits[:80]:
            refs = ISSUE_REF_PATTERN.findall(commit["subject"])
            commit_issue_refs.extend(refs)
            actor = commit["author"] or "Unknown"
            actor_entry = agent_activity_map.setdefault(actor, {"commits": 0, "repos": set(), "examples": []})
            actor_entry["commits"] += 1
            actor_entry["repos"].add(repo_label)
            if len(actor_entry["examples"]) < 3:
                actor_entry["examples"].append(f"{repo_label}:{commit['short']} {commit['subject']}")
            files = commit_files(repo, commit["full"])
            touched_files.extend(files)
            if len(change_units) < 40:
                change_units.append(
                    {
                        "repo": repo_label,
                        "commit": commit["short"],
                        "date": commit["date"],
                        "actor": actor,
                        "intent": commit["subject"],
                        "refs": ", ".join(refs) if refs else "No issue ref",
                    }
                )

        touched_files = unique_sorted(touched_files)
        total_files += len(touched_files)
        all_issue_refs.extend(commit_issue_refs)

        subsystem_counts: dict[str, int] = {}
        for path in touched_files:
            subsystem = subsystem_for(path)
            subsystem_counts[subsystem] = subsystem_counts.get(subsystem, 0) + 1
        for subsystem, count in sorted(subsystem_counts.items(), key=lambda item: (-item[1], item[0]))[:8]:
            changed_subsystems.append(
                {
                    "repo": repo_label,
                    "subsystem": subsystem,
                    "files": str(count),
                    "commits": str(len(commits)),
                    "evidence": f"{branch}@{head}; {len(touched_files)} changed files in window.",
                }
            )

        provenance.extend(
            [
                {"repo": repo_label, "signal": "Branch / HEAD", "value": f"{branch}@{head}", "evidence": "Read from local Git."},
                {"repo": repo_label, "signal": "Commits in window", "value": str(len(commits)), "evidence": since_expr},
                {"repo": repo_label, "signal": "Issue refs in subjects", "value": str(len(set(commit_issue_refs))), "evidence": ", ".join(sorted(set(commit_issue_refs))[:8]) or "None detected"},
                {"repo": repo_label, "signal": "Working tree", "value": "Dirty" if dirty_lines else "Clean", "evidence": f"{len(dirty_lines)} dirty entries"},
            ]
        )

        sensitive_files = [
            path
            for path in touched_files
            if any(pattern.search(path) for _label, pattern in HIGH_ATTENTION_PATTERNS)
        ]
        repo_high_attention_hits: list[str] = []
        dependency_files = [path for path in touched_files if DEPENDENCY_FILE_PATTERN.search(path)]
        test_files = [path for path in touched_files if TEST_FILE_PATTERN.search(path)]
        source_files = [path for path in touched_files if SOURCE_FILE_PATTERN.search(path) and not TEST_FILE_PATTERN.search(path)]

        if commits and not commit_issue_refs:
            finding = f"{repo_label} commits lack issue or intent references"
            evidence = f"{len(commits)} commits since {since_expr}; no Linear/GitHub-style refs found in subjects."
            action = "Add issue IDs to future agent tasks/PRs or record the intent in the accountability brief before merge."
            management_exceptions.append({"severity": "Medium", "finding": finding, "evidence": evidence, "action": action, "owner": "Repo owner"})
            risk_signals.append({"risk": finding, "evidence": evidence, "impact": "One CTO cannot reconstruct agent intent at fleet scale without queryable provenance.", "severity": "Medium", "mitigation": action, "source": "Codebase Accountability report"})
            questions.append({"title": f"What work intent explains {repo_label}'s unreferenced commits?", "body": "Add the missing issue/PR/agent assignment link or decide that this repo does not require issue-level provenance."})

        if sensitive_files:
            finding = f"{repo_label} touched high-attention files"
            evidence = "; ".join(sensitive_files[:8])
            action = "Confirm reviewer-of-record and whether any risk or decision row should be updated."
            management_exceptions.append({"severity": "High", "finding": finding, "evidence": evidence, "action": action, "owner": "CTO / repo owner"})
            risk_signals.append({"risk": finding, "evidence": evidence, "impact": "Security, privacy, compliance, data-model, or deploy boundaries may have shifted.", "severity": "High", "mitigation": action, "source": "Codebase Accountability report"})
            repo_high_attention_hits.extend(f"{repo_label}:{path}" for path in sensitive_files)

        if dependency_files:
            finding = f"{repo_label} changed dependency or lock files"
            evidence = "; ".join(dependency_files[:8])
            action = "Confirm dependency-change intent, update/rollback plan, and whether CI or staging smoke tests covered it."
            management_exceptions.append({"severity": "Medium", "finding": finding, "evidence": evidence, "action": action, "owner": "Repo owner"})
            risk_signals.append({"risk": finding, "evidence": evidence, "impact": "Dependency drift can introduce security, compatibility, or deployment risk without an explicit decision.", "severity": "Medium", "mitigation": action, "source": "Codebase Accountability report"})
            decision_points.append({"decision": f"Accept dependency changes in {repo_label}", "context": evidence, "owner": "Repo owner", "needed_by": "Before release if not already reviewed"})

        if source_files and not test_files:
            finding = f"{repo_label} changed source files without test-file evidence"
            evidence = f"{len(source_files)} source files changed; no test/spec files in the same commit window."
            action = "Confirm whether coverage exists elsewhere or add the missing test/eval follow-up."
            management_exceptions.append({"severity": "Medium", "finding": finding, "evidence": evidence, "action": action, "owner": "Repo owner"})
            risk_signals.append({"risk": finding, "evidence": evidence, "impact": "Agent output may be shipping behavior changes without visible validation.", "severity": "Medium", "mitigation": action, "source": "Codebase Accountability report"})

        if guardrails_text and repo_high_attention_hits and re.search(r"phi|hipaa|privacy|security|auth", guardrails_text, re.I):
            guardrail_checks.append(
                {
                    "guardrail": f"{repo_label} high-attention boundary review",
                    "status": "Review needed",
                    "evidence": "; ".join(repo_high_attention_hits[:6]),
                    "action": "Compare the touched files against ENGINEERING_GUARDRAILS.md before accepting the change as routine.",
                }
            )

    for actor, payload in sorted(agent_activity_map.items(), key=lambda item: (-int(item[1]["commits"]), item[0].lower()))[:20]:
        agent_activity.append(
            {
                "actor": actor,
                "commits": str(payload["commits"]),
                "repos": ", ".join(sorted(payload["repos"])),
                "evidence": "; ".join(payload["examples"]),
            }
        )

    if not repos:
        finding = "No code repositories are configured"
        evidence = "No --repo values were supplied and .dzcto/config.json has no codeRepos entries."
        action = "Run dzcto init <project> --repo <path> or pass --repo when generating this report."
        management_exceptions.append({"severity": "High", "finding": finding, "evidence": evidence, "action": action, "owner": "CTO"})
        risk_signals.append({"risk": finding, "evidence": evidence, "impact": "The accountability report has no codebase evidence to oversee.", "severity": "High", "mitigation": action, "source": "Codebase Accountability report"})

    if total_commits == 0 and repos:
        questions.append({"title": "Was there intentionally no repo movement in this window?", "body": f"No commits were found since {since_expr}. Confirm the date window or configured repos if work happened elsewhere."})

    exception_count = len(management_exceptions)
    high_exception_count = sum(1 for item in management_exceptions if item.get("severity") == "High")
    actor_count = len(agent_activity_map)
    issue_ref_count = len(set(all_issue_refs))
    attention = "No high-severity exceptions surfaced." if high_exception_count == 0 else f"{high_exception_count} high-severity exception{'s' if high_exception_count != 1 else ''} need review."
    executive_read = (
        f"Reviewed {len(repos)} repo{'s' if len(repos) != 1 else ''} since {since_expr} ({since_reason}). "
        f"Found {total_commits} commit{'s' if total_commits != 1 else ''}, {total_files} touched file{'s' if total_files != 1 else ''}, "
        f"{actor_count} author/agent signal{'s' if actor_count != 1 else ''}, and {issue_ref_count} issue reference{'s' if issue_ref_count != 1 else ''}. "
        f"{attention} Use this as a management-by-exception brief; promote durable exposure into Risks, durable choices into Decisions, and guardrail gaps into ENGINEERING_GUARDRAILS.md."
    )

    return {
        "executive_read": executive_read,
        "review_window": {"since": since_expr, "since_reason": since_reason, "until": generated_at},
        "metrics": [
            {"label": "Repos", "value": len(repos), "detail": "Configured/read-only sources"},
            {"label": "Commits", "value": total_commits, "detail": f"Since {since_expr}"},
            {"label": "Files", "value": total_files, "detail": "Unique touched paths"},
            {"label": "Exceptions", "value": exception_count, "detail": f"{high_exception_count} high"},
            {"label": "Issue refs", "value": issue_ref_count, "detail": "Commit-subject refs"},
            {"label": "Dirty repos", "value": dirty_repos, "detail": "Uncommitted local state"},
        ],
        "management_exceptions": management_exceptions,
        "changed_subsystems": changed_subsystems,
        "provenance": provenance,
        "guardrail_checks": guardrail_checks,
        "agent_activity": agent_activity,
        "change_units": change_units,
        "risks": risk_signals,
        "decisions": decision_points,
        "questions": questions,
        "sources": sources,
    }


def run_codebase_accountability(args: argparse.Namespace) -> int:
    project = resolve_project(args.project)
    require_existing_wiki(project)
    wiki_root = wiki_root_for_project(project)
    since_expr, since_reason = accountability_since(project, args.since, args.days)
    repos = project_code_repos(project, args.repo)
    data = build_codebase_accountability_data(project, repos, since_expr=since_expr, since_reason=since_reason)

    generated_dir = sidecar_dir(wiki_root) / "generated"
    generated_dir.mkdir(parents=True, exist_ok=True)
    report_date = args.date or dt.date.today().isoformat()
    data_path = Path(args.output_json).expanduser().resolve() if args.output_json else generated_dir / f"codebase-accountability-{report_date}.json"
    data_path.parent.mkdir(parents=True, exist_ok=True)
    data_path.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    if args.json:
        print(json.dumps(data, indent=2, sort_keys=True))

    if args.no_artifact:
        if not args.json:
            print(data_path)
        return 0

    artifact_args = [
        "--project",
        str(project),
        "--kind",
        "codebase-accountability",
        "--title",
        args.title,
        "--date",
        report_date,
        "--data-file",
        str(data_path),
    ]
    return run_script("dzcto_artifact.py", artifact_args)


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


def snapshot_title_date(value: dt.date) -> str:
    return f"{value.month}/{value.day}/{str(value.year)[-2:]}"


def report_json_date(path: Path) -> dt.date | None:
    value = report_run_date(path)
    if value == "Unknown date":
        return None
    try:
        return dt.date.fromisoformat(value)
    except ValueError:
        return None


def snapshot_report_entries(wiki_root: Path, start: dt.date, end: dt.date) -> list[dict[str, Any]]:
    entries: list[dict[str, Any]] = []
    reports_dir = wiki_root / "reports"
    for kind, label in REPORT_FOLDERS.items():
        if kind == "snapshot":
            continue
        for json_path in sorted((reports_dir / kind).glob("*.json"), reverse=True):
            if json_path.name == "data.json":
                continue
            report_date = report_json_date(json_path)
            if not report_date or report_date < start or report_date > end:
                continue
            data = read_json(json_path, {})
            if not isinstance(data, dict):
                continue
            html_path = json_path.with_suffix(".html")
            href = html_path.relative_to(wiki_root).as_posix() if html_path.exists() else ""
            summary = report_lead_summary(data) or ""
            entries.append(
                {
                    "kind": kind,
                    "label": label,
                    "date": report_date.isoformat(),
                    "path": json_path,
                    "href": href,
                    "summary": snippet(summary, 240),
                    "data": data,
                }
            )
    return sorted(entries, key=lambda item: (item["date"], item["label"]), reverse=True)


def latest_snapshot_entries_by_kind(entries: list[dict[str, Any]]) -> list[dict[str, Any]]:
    latest: dict[str, dict[str, Any]] = {}
    for entry in entries:
        kind = str(entry.get("kind") or "")
        if kind and kind not in latest:
            latest[kind] = entry
    return list(latest.values())


def snapshot_entry_by_kind(entries: list[dict[str, Any]], kind: str) -> dict[str, Any] | None:
    for entry in entries:
        if entry.get("kind") == kind:
            return entry
    return None


def snapshot_metric_value(data: dict[str, Any], *keys: str) -> str:
    wanted = {re.sub(r"[^a-z0-9]+", "", key.lower()) for key in keys}
    metrics = value_at(data, "metrics")
    if isinstance(metrics, dict):
        for key, value in metrics.items():
            if re.sub(r"[^a-z0-9]+", "", str(key).lower()) in wanted:
                return text_value(value)
    for metric in array_value(metrics):
        if not isinstance(metric, dict):
            continue
        label = text_value(value_at(metric, "label", "name", "title"))
        if re.sub(r"[^a-z0-9]+", "", label.lower()) in wanted:
            return text_value(value_at(metric, "value", "count", "status"))
    return ""


def snapshot_report_datetime(value: str) -> dt.datetime | None:
    text = value.strip()
    if not text:
        return None
    try:
        return dt.datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        pass
    try:
        return dt.datetime.combine(dt.date.fromisoformat(text[:10]), dt.time.min)
    except ValueError:
        return None


def snapshot_date_sort_value(value: str) -> dt.date:
    dates = dates_in_text(value)
    return min(dates) if dates else dt.date.max


def snapshot_deadline_sort_key(value: str) -> tuple[int, dt.date, str]:
    text = value.strip()
    lower = text.lower()
    date_value = snapshot_date_sort_value(text)
    if date_value != dt.date.max:
        return (0, date_value, lower)
    if "today" in lower or "now" in lower:
        return (1, dt.date.min, lower)
    if "this week" in lower:
        return (2, dt.date.min, lower)
    if lower.startswith("before "):
        return (3, dt.date.min, lower)
    if "needs date" in lower:
        return (4, dt.date.max, lower)
    return (5, dt.date.max, lower)


def priority_done_when(title: str, body: str) -> str:
    text = f"{title} {body}".lower()
    if "csp" in text or "content security policy" in text:
        return "CSP is enforced in production, or a dated exception is logged."
    if "sentry" in text or "posthog" in text or "phi" in text:
        return "Sentry/PostHog payloads are audited and PHI scrub tests or notes are recorded."
    if "image_processing" in text or "pr #271" in text:
        return "PR #271 is merged only after staging document-upload and variant tests pass, or explicitly held."
    if "beta launch gate" in text:
        return "A dated beta launch gate list exists with 5-7 must-haves, owners, and release criteria."
    if "arw-98" in text or "eval" in text or "accuracy" in text:
        return "Eval coverage is expanded and the remaining predicate disposition is recorded."
    if "reducto" in text:
        return "Queue-on-outage is built, or manual retry is accepted in DECISIONS.md with a review date."
    if "guardrail" in text or "invariant" in text:
        return "ENGINEERING_GUARDRAILS.md exists with architecture, privacy, data-flow, and reviewer rules."
    if "hipaa" in text or "classification" in text:
        return "Legal classification opinion is received or the next dated owner follow-up is logged."
    return "The source report records a concrete completion condition, owner, and date."


def add_unique_snapshot_item(items: list[dict[str, str]], item: dict[str, str], seen: set[str], *, limit: int = 12) -> None:
    title = item.get("title", "").strip()
    if not title:
        return
    key = re.sub(r"\W+", " ", f"{title} {item.get('body', '')}".lower()).strip()
    if key in seen:
        return
    seen.add(key)
    items.append(item)
    del items[limit:]


def snapshot_item_from_report(entry: dict[str, Any], raw: Any, *, prefix: str = "") -> dict[str, str]:
    title = item_headline(raw)
    if prefix and title:
        title = f"{prefix}: {title}"
    body = ""
    owner = ""
    if isinstance(raw, dict):
        body = text_value(value_at(raw, "body", "detail", "details", "summary", "context", "why", "impact", "mitigation", "rationale", "note", "notes"))
        owner = text_value(value_at(raw, "owner", "owner_horizon", "responsible", "needed_by", "done_when"))
    if body == title:
        body = ""
    return {
        "title": title,
        "body": snippet(body, 220),
        "owner": owner,
        "source": f"{entry['label']} / {entry['date']}",
    }


def snapshot_items_from_reports(entries: list[dict[str, Any]], specs: dict[str, list[tuple[str, str]]], *, limit: int = 12) -> list[dict[str, str]]:
    items: list[dict[str, str]] = []
    seen: set[str] = set()
    for entry in entries:
        for field, prefix in specs.get(entry["kind"], []):
            for raw in array_value(value_at(entry["data"], field)):
                add_unique_snapshot_item(items, snapshot_item_from_report(entry, raw, prefix=prefix), seen, limit=limit)
                if len(items) >= limit:
                    return items
    return items


def snapshot_priority_rows(entries: list[dict[str, Any]], due_risks: list[dict[str, Any]], cadence_due: list[dict[str, Any]], *, limit: int = 5) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    seen: set[str] = set()

    def add(priority: str, owner: str, why: str, done_when: str, source: str) -> None:
        key = priority.lower()
        if not priority or key in seen:
            return
        seen.add(key)
        concrete_done_when = done_when if done_when and done_when != "Own the next explicit step." else priority_done_when(priority, why)
        rows.append({"priority": priority, "owner": owner or "CTO", "why": snippet(why, 180), "done_when": snippet(concrete_done_when, 220), "source": source})
        del rows[limit:]

    for risk in due_risks:
        add(
            f"Review risk: {text_value(value_at(risk, 'title', 'risk'))}",
            text_value(value_at(risk, "owner", "responsible")) or "CTO",
            f"{text_value(value_at(risk, 'severity'))} / next review {text_value(value_at(risk, 'review'))}",
            text_value(value_at(risk, "mitigation", "action", "plan")) or "",
            "Risk register",
        )
        if len(rows) >= limit:
            return rows

    for alert in cadence_due:
        add(
            f"Run cadence: {text_value(alert.get('label'))}",
            "CTO",
            text_value(alert.get("reason")),
            text_value(alert.get("command")),
            "Operating cadence",
        )
        if len(rows) >= limit:
            return rows

    specs = {
        "weekly-reviews": [("next_week_focus", ""), ("next_focus", ""), ("priorities", "")],
        "engineering-risk": [("mitigations", "Mitigate")],
        "ceo-updates": [("next", "Next")],
        "codebase-accountability": [("management_exceptions", "Resolve exception")],
    }
    for entry in entries:
        for field, prefix in specs.get(entry["kind"], []):
            for raw in array_value(value_at(entry["data"], field)):
                item = snapshot_item_from_report(entry, raw, prefix=prefix)
                done_when = ""
                if isinstance(raw, dict):
                    done_when = text_value(value_at(raw, "done_when", "definition_of_done", "success", "outcome"))
                add(item["title"], item.get("owner", ""), item.get("body", ""), done_when, item["source"])
                if len(rows) >= limit:
                    return rows
    return rows


def snapshot_risk_rows(risks: list[dict[str, Any]], due_risks: list[dict[str, Any]], entries: list[dict[str, Any]], *, limit: int = 6) -> list[dict[str, str]]:
    due_titles = {text_value(value_at(risk, "title", "risk")).lower() for risk in due_risks}
    ranked = sorted(
        risks,
        key=lambda risk: (
            severity_rank(text_value(value_at(risk, "severity", "status"))),
            0 if text_value(value_at(risk, "title", "risk")).lower() in due_titles else 1,
            snapshot_date_sort_value(text_value(value_at(risk, "review", "next_review", "due"))),
            text_value(value_at(risk, "title", "risk")).lower(),
        ),
    )
    rows = []
    seen: set[str] = set()
    for risk in ranked[:limit]:
        title = text_value(value_at(risk, "title", "risk"))
        if not title:
            continue
        seen.add(title.lower())
        rows.append(
            {
                "risk": title,
                "severity": text_value(value_at(risk, "severity", "status")),
                "owner": text_value(value_at(risk, "owner", "responsible")),
                "review": text_value(value_at(risk, "review", "next_review", "due")),
                "mitigation": snippet(text_value(value_at(risk, "mitigation", "action", "plan")), 220),
            }
        )

    return rows


def snapshot_decision_rows(decisions: list[dict[str, Any]], due_decisions: list[dict[str, Any]], entries: list[dict[str, Any]], *, limit: int = 8) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    seen: set[str] = set()

    def add(decision: str, context: str, owner: str, needed_by: str, source: str) -> None:
        key = decision.lower()
        if not decision or key in seen:
            return
        seen.add(key)
        deadline = needed_by
        if not deadline and re.search(r"\bthis week\b", f"{decision} {context}", re.I):
            deadline = "This week"
        elif not deadline and re.search(r"\bbefore beta\b", f"{decision} {context}", re.I):
            deadline = "Before beta launch"
        rows.append({"decision": decision, "context": snippet(context, 220), "owner": owner or "CTO", "needed_by": deadline or "Needs date", "source": source})
        del rows[limit:]

    for decision in due_decisions:
        add(
            text_value(value_at(decision, "title", "decision")),
            text_value(value_at(decision, "context", "rationale")),
            text_value(value_at(decision, "owner", "responsible")),
            text_value(value_at(decision, "when", "revisitTrigger", "needed_by")),
            "Decision log",
        )
    specs = {
        "weekly-reviews": [("decisions_needed", ""), ("decisions", "")],
        "ceo-updates": [("asks_decisions", ""), ("asks", ""), ("decisions", "")],
        "codebase-accountability": [("decisions", ""), ("decision_points", "")],
    }
    for entry in entries:
        for field, _prefix in specs.get(entry["kind"], []):
            for raw in array_value(value_at(entry["data"], field)):
                if isinstance(raw, dict):
                    add(
                        item_headline(raw),
                        text_value(value_at(raw, "context", "detail", "details", "summary", "why")),
                        text_value(value_at(raw, "owner", "responsible")),
                        text_value(value_at(raw, "needed_by", "due", "urgency", "horizon")),
                        f"{entry['label']} / {entry['date']}",
                    )
                else:
                    add(text_value(raw), "", "", "Needs date", f"{entry['label']} / {entry['date']}")
                if len(rows) >= limit:
                    return sorted(rows, key=lambda row: (*snapshot_deadline_sort_key(row.get("needed_by", "")), row.get("decision", "")))
    if not rows and decisions:
        for decision in decisions[-limit:]:
            add(
                text_value(value_at(decision, "title", "decision")),
                text_value(value_at(decision, "context", "rationale")),
                text_value(value_at(decision, "owner", "responsible")),
                text_value(value_at(decision, "when", "revisitTrigger")),
                "Decision log",
            )
    return sorted(rows, key=lambda row: (*snapshot_deadline_sort_key(row.get("needed_by", "")), row.get("decision", "")))


def snapshot_operating_rows(cadence_due: list[dict[str, Any]], learning_items: list[dict[str, Any]], report_entries: list[dict[str, Any]], end: dt.date) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    if cadence_due:
        for alert in cadence_due[:6]:
            rows.append({"signal": f"Cadence due: {alert['label']}", "status": "Due", "detail": alert["reason"], "source": "Operating cadence"})
    else:
        rows.append({"signal": "Operating cadence", "status": "Current", "detail": "No cadence items are due today or overdue.", "source": "Operating cadence"})

    learning_due = []
    for item in learning_items:
        due_on = text_value(item.get("due_on"))
        try:
            due_date = dt.date.fromisoformat(due_on)
        except ValueError:
            continue
        if due_date <= end and int(item.get("seen_count", 0) or 0) > 0:
            learning_due.append(item)
    rows.append(
        {
            "signal": "Learning",
            "status": f"{len(learning_due)} due",
            "detail": f"{len(learning_items)} active learning items tracked.",
            "source": "Learning",
        }
    )
    report_kinds = sorted({entry["label"] for entry in report_entries})
    rows.append(
        {
            "signal": "Report coverage",
            "status": f"{len(report_entries)} reports",
            "detail": ", ".join(report_kinds) if report_kinds else "No report artifacts found in the snapshot window.",
            "source": "Reports",
        }
    )
    return rows


def snapshot_outcome_rows(latest_entries: list[dict[str, Any]], *, limit: int = 6) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    seen: set[str] = set()
    preferred = [
        ("Beta users", ("beta_users",)),
        ("Eval scenarios", ("eval_scenarios", "ai_eval_scenarios")),
        ("Billing rules live", ("billing_rules_live", "rule_predicates_shipped")),
        ("Open PRs", ("open_prs",)),
        ("Commits this week", ("commits_this_week", "commits")),
        ("Incidents", ("incidents",)),
    ]
    source_order = ["ceo-updates", "weekly-reviews", "engineering-risk", "codebase-accountability"]
    ordered_entries = [entry for kind in source_order for entry in latest_entries if entry.get("kind") == kind]
    for label, keys in preferred:
        for entry in ordered_entries:
            value = snapshot_metric_value(entry["data"], *keys)
            if not value:
                continue
            key = label.lower()
            if key in seen:
                break
            seen.add(key)
            rows.append({"signal": label, "value": value, "source": f"{entry['label']} / {entry['date']}"})
            break
        if len(rows) >= limit:
            break
    return rows


def snapshot_agent_activity_audit(project: Path, latest_entries: list[dict[str, Any]], start: dt.date) -> list[dict[str, str]]:
    entry = snapshot_entry_by_kind(latest_entries, "codebase-accountability")
    if not entry:
        return [
            {
                "signal": "Codebase accountability",
                "status": "Missing",
                "detail": "No codebase accountability report exists for this snapshot.",
                "action": f'dzcto codebase-accountability "{project}" --since {start.isoformat()}',
            }
        ]

    data = entry["data"]
    window = value_at(data, "review_window") if isinstance(value_at(data, "review_window"), dict) else {}
    since = text_value((window or {}).get("since"))
    since_dt = snapshot_report_datetime(since)
    coverage_gap = bool(since_dt and since_dt.date() > start)
    rows: list[dict[str, str]] = []
    if coverage_gap:
        rows.append(
            {
                "signal": "Coverage window",
                "status": "Needs rerun",
                "detail": f"Latest accountability report starts {since}; snapshot starts {start.isoformat()}.",
                "action": f'dzcto codebase-accountability "{project}" --since {start.isoformat()}',
            }
        )
    else:
        rows.append(
            {
                "signal": "Coverage window",
                "status": "Covered",
                "detail": f"Latest accountability report covers since {since or 'the configured window'}.",
                "action": "Use the report links below for commit-level evidence.",
            }
        )

    commits = snapshot_metric_value(data, "Commits") or "0"
    files = snapshot_metric_value(data, "Files") or "0"
    issue_refs = snapshot_metric_value(data, "Issue refs") or "0"
    actor_rows = array_value(value_at(data, "agent_activity", "authors", "agents"))
    if actor_rows:
        top_actor = actor_rows[0] if isinstance(actor_rows[0], dict) else {}
        detail = f"{len(actor_rows)} actor signal(s); top actor {text_value(value_at(top_actor, 'actor', 'name')) or 'Unknown'} with {text_value(value_at(top_actor, 'commits')) or 'unknown'} commit(s)."
    else:
        detail = f"{commits} commit(s), {files} touched file(s), {issue_refs} issue reference(s); no author/agent activity captured."
    rows.append(
        {
            "signal": "Agent / human attribution",
            "status": "Partial" if commits != "0" else "No activity captured",
            "detail": detail,
            "action": "Record agent ID and reviewer-of-record in issues, PRs, or commit subjects for future runs.",
        }
    )

    guardrails = array_value(value_at(data, "guardrail_checks", "guardrails"))
    needs_guardrails = any(re.search(r"needs|missing|setup", text_value(value_at(item, "status", "guardrail", "evidence")), re.I) for item in guardrails if isinstance(item, dict))
    rows.append(
        {
            "signal": "Engineering invariants",
            "status": "Needs setup" if needs_guardrails else "Present",
            "detail": "No ENGINEERING_GUARDRAILS.md source file is configured." if needs_guardrails else "Guardrail source exists for accountability checks.",
            "action": "Create or maintain core/ENGINEERING_GUARDRAILS.md with privacy, architecture, data-flow, deploy, and review rules.",
        }
    )
    return rows


def snapshot_change_rows(
    risks: list[dict[str, Any]],
    high_risks: list[dict[str, Any]],
    due_risks: list[dict[str, Any]],
    decisions: list[dict[str, str]],
    outcome_rows: list[dict[str, str]],
    latest_entries: list[dict[str, Any]],
) -> list[dict[str, str]]:
    rows = [
        {
            "signal": "Risk posture",
            "value": f"{len(risks)} active / {len(high_risks)} high or critical / {len(due_risks)} due",
            "detail": "Baseline for comparison if no previous Snapshot exists.",
        },
        {
            "signal": "Decision load",
            "value": f"{len(decisions)} decisions or asks",
            "detail": f"{sum(1 for row in decisions if row.get('needed_by') == 'Needs date')} need explicit dates.",
        },
    ]
    accountability = snapshot_entry_by_kind(latest_entries, "codebase-accountability")
    if accountability:
        commits = snapshot_metric_value(accountability["data"], "Commits") or "0"
        files = snapshot_metric_value(accountability["data"], "Files") or "0"
        rows.append(
            {
                "signal": "Codebase movement",
                "value": f"{commits} commits / {files} files",
                "detail": f"{accountability['label']} / {accountability['date']}",
            }
        )
    outcome_summary = ", ".join(f"{row['signal']}: {row['value']}" for row in outcome_rows[:3])
    if outcome_summary:
        rows.append({"signal": "Outcome signals", "value": outcome_summary, "detail": "Product/readiness metrics surfaced from latest reports."})
    return rows[:4]


def snapshot_tldr_rows(
    entries: list[dict[str, Any]],
    risks: list[dict[str, Any]],
    high_risks: list[dict[str, Any]],
    due_risks: list[dict[str, Any]],
    decisions: list[dict[str, str]],
    priorities: list[dict[str, str]],
    audit_rows: list[dict[str, str]],
) -> list[dict[str, str]]:
    needs_attention = bool(high_risks or due_risks or any(row.get("status") in {"Needs rerun", "Needs setup", "Missing"} for row in audit_rows))
    status = "Yellow" if needs_attention else "Green"
    status_detail = (
        f"{len(high_risks)} high/critical risk(s), {len(due_risks)} risk review(s) due, {len(decisions)} decision/ask row(s)."
        if needs_attention
        else "No high/critical risks, due risk reviews, or accountability setup gaps are visible."
    )

    ceo_entry = snapshot_entry_by_kind(entries, "ceo-updates")
    one_thing = ""
    if ceo_entry:
        one_thing = text_value(value_at(ceo_entry["data"], "headline")) or report_lead_summary(ceo_entry["data"], 220)
    if not one_thing and priorities:
        one_thing = priorities[0]["priority"]
    decision = next((row for row in decisions if snapshot_deadline_sort_key(row.get("needed_by", ""))[0] <= 2), decisions[0] if decisions else {})
    decision_read = "No formal decision is due in the current snapshot."
    if decision:
        decision_read = f"{decision['decision']} — owner {decision['owner']}, needed by {decision['needed_by']}."

    return [
        {"label": "Overall status", "value": f"{status} — {status_detail}"},
        {"label": "One thing to know", "value": one_thing or "No report summary is available yet."},
        {"label": "Decision needed this week", "value": decision_read},
    ]


def snapshot_communication_rows(
    direction: str,
    entries: list[dict[str, Any]],
    priorities: list[dict[str, str]],
    decisions: list[dict[str, str]],
    risks: list[dict[str, str]],
    audit_rows: list[dict[str, str]],
    *,
    limit: int = 3,
) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    if direction == "up":
        ceo_entry = snapshot_entry_by_kind(entries, "ceo-updates")
        if ceo_entry:
            headline = text_value(value_at(ceo_entry["data"], "headline")) or report_lead_summary(ceo_entry["data"], 200)
            rows.append({"title": "CEO read", "body": headline, "source": f"{ceo_entry['label']} / {ceo_entry['date']}"})
        if decisions:
            rows.append({"title": "Decision needed", "body": f"{decisions[0]['decision']} — {decisions[0]['needed_by']}.", "source": decisions[0]["source"]})
        if risks:
            rows.append({"title": "Risk posture", "body": f"{risks[0]['risk']} remains the top canonical risk to manage.", "source": "Risk register"})
    else:
        for priority in priorities[:2]:
            rows.append({"title": priority["priority"], "body": priority["done_when"], "source": priority["source"]})
        gap = next((row for row in audit_rows if row.get("status") in {"Needs rerun", "Needs setup", "Missing"}), None)
        if gap:
            rows.append({"title": gap["signal"], "body": gap["action"], "source": "Codebase Accountability"})
    return rows[:limit]


def build_snapshot_data(project: Path, *, start: dt.date, end: dt.date) -> dict[str, Any]:
    wiki_root = wiki_root_for_project(project)
    reports_dir = wiki_root / "reports"
    core_dir = wiki_root / "core"
    learning_dir = wiki_root / "learning"
    entries = snapshot_report_entries(wiki_root, start, end)
    latest_entries = latest_snapshot_entries_by_kind(entries)

    risk_registry = build_risk_registry(wiki_root)
    risks = active_registry_risks(risk_registry)
    due_risks = due_risk_entries(risks, end)
    high_risks = [risk for risk in risks if severity_rank(text_value(value_at(risk, "severity", "status"))) <= severity_rank("High")]

    decision_registry = build_decision_registry(wiki_root)
    decisions = registry_decisions(decision_registry)
    due_decisions = due_decision_entries(decisions, end)

    cadence_rules = parse_cadence_rules(core_dir / "OPERATING_CADENCE.md")
    cadence_due = cadence_alerts(cadence_rules, reports_dir, end)
    learning_items = read_learning_items(learning_dir)

    priorities = snapshot_priority_rows(latest_entries, due_risks, cadence_due)
    application_state = [
        {"title": entry["label"], "body": entry["summary"], "source": f"{entry['label']} / {entry['date']}"}
        for entry in latest_entries
        if entry["summary"]
    ][:8]
    risk_rows = snapshot_risk_rows(risks, due_risks, entries)
    decision_rows = snapshot_decision_rows(decisions, due_decisions, entries)
    operating_rows = snapshot_operating_rows(cadence_due, learning_items, entries, end)
    outcome_rows = snapshot_outcome_rows(latest_entries)
    agent_activity_audit = snapshot_agent_activity_audit(project, latest_entries, start)
    changed_since_last_week = snapshot_change_rows(risks, high_risks, due_risks, decision_rows, outcome_rows, latest_entries)
    tldr = snapshot_tldr_rows(latest_entries, risks, high_risks, due_risks, decision_rows, priorities, agent_activity_audit)
    communicate_up = snapshot_communication_rows("up", latest_entries, priorities, decision_rows, risk_rows, agent_activity_audit)
    communicate_down = snapshot_communication_rows("down", latest_entries, priorities, decision_rows, risk_rows, agent_activity_audit)
    report_rollup = [
        {"report": entry["label"], "date": entry["date"], "summary": entry["summary"], "source": entry["href"] or str(entry["path"].relative_to(wiki_root))}
        for entry in latest_entries
    ]
    snapshot_sources = [
        {"title": f"{entry['label']} / {entry['date']}", "href": entry["href"] or str(entry["path"].relative_to(wiki_root))}
        for entry in entries
    ]
    snapshot_sources.extend(
        [
            {"title": "Risk register", "href": "core/RISKS.md"},
            {"title": "Decision log", "href": "core/DECISIONS.md"},
            {"title": "Operating cadence", "href": "core/OPERATING_CADENCE.md"},
            {"title": "Learning items", "href": "learning/items.json"},
        ]
    )

    executive_read = (
        f"Snapshot for {start.isoformat()} through {end.isoformat()}: {len(entries)} report artifact"
        f"{'s' if len(entries) != 1 else ''}, {len(risks)} active risk{'s' if len(risks) != 1 else ''} "
        f"({len(high_risks)} high or critical), {len(due_risks)} risk review{'s' if len(due_risks) != 1 else ''} due, "
        f"{len(due_decisions)} decision review{'s' if len(due_decisions) != 1 else ''} due, and "
        f"{len(cadence_due)} cadence item{'s' if len(cadence_due) != 1 else ''} due. "
        "Use this as the single CTO readout: communicate up from the Communicate Up section, communicate down from the team-facing section, and run priorities from the priority table."
    )

    return {
        "executive_read": executive_read,
        "window": {"start": start.isoformat(), "end": end.isoformat()},
        "tldr": tldr,
        "changed_since_last_week": changed_since_last_week,
        "metrics": [
            {"label": "Reports", "value": len(entries), "detail": "Included in window"},
            {"label": "Active risks", "value": len(risks), "detail": f"{len(high_risks)} high/critical"},
            {"label": "Risk reviews", "value": len(due_risks), "detail": "Due by window end"},
            {"label": "Decision reviews", "value": len(due_decisions), "detail": "Due or triggered"},
            {"label": "Cadence due", "value": len(cadence_due), "detail": "Due by window end"},
        ],
        "communicate_up": communicate_up,
        "communicate_down": communicate_down,
        "priorities": priorities,
        "application_state": application_state,
        "risks": risk_rows,
        "decisions": decision_rows,
        "operating_signals": operating_rows,
        "outcome_signals": outcome_rows,
        "agent_activity_audit": agent_activity_audit,
        "report_rollup": report_rollup,
        "sources": snapshot_sources,
    }


def run_snapshot(args: argparse.Namespace) -> int:
    project = resolve_project(args.project)
    require_existing_wiki(project)
    wiki_root = wiki_root_for_project(project)
    start, end = snapshot_window(args)
    data = build_snapshot_data(project, start=start, end=end)

    generated_dir = sidecar_dir(wiki_root) / "generated"
    generated_dir.mkdir(parents=True, exist_ok=True)
    report_date = args.date or end.isoformat()
    title = args.title or f"Day Zero CTO Snapshot Report {snapshot_title_date(start)}-{snapshot_title_date(end)}"
    data_path = Path(args.output_json).expanduser().resolve() if args.output_json else generated_dir / f"snapshot-{start.isoformat()}-{end.isoformat()}.json"
    data_path.parent.mkdir(parents=True, exist_ok=True)
    data_path.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    if args.json:
        print(json.dumps(data, indent=2, sort_keys=True))

    if args.no_artifact:
        if not args.json:
            print(data_path)
        return 0

    return run_script(
        "dzcto_artifact.py",
        [
            "--project",
            str(project),
            "--kind",
            "snapshot",
            "--title",
            title,
            "--date",
            report_date,
            "--data-file",
            str(data_path),
        ],
    )


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
                 --company-name "Acme" \\
                 --weekly-range "previous_completed_week" \\
                 --weekly-start-day "Monday" \\
                 --weekly-end-day "Sunday" \\
                 --ceo-report-tone "Direct, concise, business-facing, calm about risk, explicit about asks."

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
              Ask for artifact/report location, weekly report defaults, CEO report tone, then create index.html.
          /dzcto-ceo-report-weekly
              Generate a CEO report using the weekly defaults captured by init.
          /dzcto-ceo-report
              Ask for a concrete date range and generate a CEO report for that range.

        Local helper
          dzcto init --artifacts-dir {artifacts_arg} [--company-name <name>] [--company-description <summary>] [--company-url <url>]
                     [--weekly-range <range>] [--weekly-start-day <day>] [--weekly-end-day <day>]
                     [--weekly-lookback-days N] [--ceo-report-tone <text>] [--repo <path> ...]
              Create or refresh the artifact folder, .dzcto/config.json, reports/ceo-updates/, and index.html.
          dzcto artifact --artifacts-dir {artifacts_arg} --kind ceo-updates --title <title>
                         [--date YYYY-MM-DD] [--data-file <json>] [--body-file <html>]
              Render a CEO report and refresh the index. Prefer --data-file.
          dzcto setup
              Install the local Codex plugin marketplace entry.
          dzcto install-command
              Create a stable shell command, usually ~/.local/bin/dzcto.
          dzcto update
              Pull or relink the local install, then run doctor.
          dzcto doctor
              Check install health, manifests, helper syntax, and wrappers.
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

            Init captures weekly defaults and tone:
              dzcto init --artifacts-dir {artifacts_arg} --weekly-range previous_completed_week --weekly-start-day Monday --weekly-end-day Sunday --ceo-report-tone "<tone>"

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


def risks_missing_review_dates(core_dir: Path) -> list[str]:
    risks = read_risk_entries(core_dir)
    return [risk["title"] for risk in risks if not dates_in_text(risk.get("review", ""))]


def project_status_checks(project: Path) -> list[dict[str, str]]:
    wiki_root = wiki_root_for_project(project)
    core_dir = wiki_root / "core"
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
        str(company_name).strip() if has_real_value(company_name) else "Missing from .dzcto/config.json or Strategy title",
        f"dzcto init {sh_quote(str(project))} --company-name \"<name>\"",
    )
    add(
        "pass" if has_real_value(company_description) else "warn",
        "Company description",
        "Captured" if has_real_value(company_description) else "Add a Product Thesis or run init with --company-description",
        f"dzcto init {sh_quote(str(project))} --company-description \"<summary>\"",
    )
    add(
        "pass" if repos else "warn",
        "Read-only repos",
        f"{len(repos)} configured" if repos else "No repo paths configured",
        f"dzcto init {sh_quote(str(project))} --repo \"<repo path>\"",
    )

    core_sources = [doc for doc in CORE_DOCS if (core_dir / doc).exists()]
    add(
        "pass" if len(core_sources) == len(CORE_DOCS) else "warn",
        "Core context sources",
        f"{len(core_sources)}/{len(CORE_DOCS)} source files present",
        "Use day-zero-cto:refine-core-context to fill missing core docs",
    )

    cadence_rules = parse_cadence_rules(core_dir / "OPERATING_CADENCE.md")
    add(
        "pass" if cadence_rules else "warn",
        "Cadence rules",
        f"{len(cadence_rules)} rules configured" if cadence_rules else "No Index Cadence Rules table found",
        "Use day-zero-cto:refine-core-context for Operating Cadence",
    )

    risks = read_risk_entries(core_dir)
    missing_risk_dates = risks_missing_review_dates(core_dir)
    add(
        "pass" if not missing_risk_dates else "warn",
        "Risk review dates",
        f"All {len(risks)} active risks have calendar review dates" if not missing_risk_dates else f"{len(missing_risk_dates)} risk(s) missing a calendar review date",
        "Use day-zero-cto:review-risks to add a date fallback to every active risk",
    )

    report_count = 0
    for folder in REPORT_FOLDERS:
        report_count += len(list((wiki_root / "reports" / folder).glob("*.html")))
    add(
        "pass" if report_count else "warn",
        "Reports",
        f"{report_count} generated reports" if report_count else "No reports generated yet",
        "Use the dashboard AI prompt cards to run the first reports",
    )

    learning_items = read_json(wiki_root / "learning" / "items.json", [])
    learning_count = len(learning_items) if isinstance(learning_items, list) else 0
    add(
        "pass" if learning_count else "warn",
        "Learning seed",
        f"{learning_count} learning items" if learning_count else "No learning items yet",
        f"dzcto learning --project {sh_quote(str(project))} --stats",
    )

    stale = check_stale(project)
    stale_count = sum(1 for check in stale["checks"] if check["status"] in {"stale", "fail"})
    add(
        "pass" if stale_count == 0 else "warn",
        "Generated artifacts",
        "Current" if stale_count == 0 else f"{stale_count} stale/failing checks",
        f"dzcto check-stale {sh_quote(str(project))}",
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


def agent_context(project: Path, repos: list[str]) -> str:
    if not repos:
        return f"Use project folder `{project}`. No read-only code repo is configured; ask for repo access if code evidence is needed."
    if len(repos) == 1:
        return f"Use project folder `{project}`. Use read-only code repo `{repos[0]}`."
    repo_list = ", ".join(f"`{repo}`" for repo in repos)
    return f"Use project folder `{project}`. Use read-only code repos: {repo_list}."


def print_lfg_action(action: dict[str, Any], *, as_json: bool = False) -> int:
    if as_json:
        print(json.dumps(action, indent=2, sort_keys=True))
        return 0
    print("Day Zero CTO LFG")
    print()
    print(f"Next best action: {action['label']}")
    print(f"Why: {action['why']}")
    if action.get("command"):
        print()
        print("Run:")
        print(f"  {action['command']}")
    if action.get("prompt"):
        print()
        print("Prompt:")
        print(textwrap.indent(action["prompt"], "  "))
    return 0


def next_lfg_action(project: Path) -> dict[str, Any]:
    wiki_root = wiki_root_for_project(project)
    core_dir = wiki_root / "core"
    reports_dir = wiki_root / "reports"
    learning_dir = wiki_root / "learning"
    today = dt.date.today()
    repos = project_repos(wiki_root)
    context = agent_context(project, repos)

    checks = project_status_checks(project)
    setup_issue = next((check for check in checks if check["status"] in {"fail", "warn"}), None)
    if setup_issue:
        return {
            "kind": "setup",
            "label": f"Setup: {setup_issue['label']}",
            "why": setup_issue["detail"],
            "command": setup_issue.get("command") or f"dzcto status {sh_quote(str(project))}",
            "prompt": "",
        }

    cadence_rules = parse_cadence_rules(core_dir / "OPERATING_CADENCE.md")
    alerts = cadence_alerts(cadence_rules, reports_dir, today)
    if alerts:
        alert = alerts[0]
        command = display_command(str(alert.get("command") or ""))
        return {
            "kind": "cadence",
            "label": f"Run cadence: {alert['label']}",
            "why": alert["reason"],
            "command": command,
            "prompt": f"{command} {context}".strip() if command else "",
        }

    risk_registry = build_risk_registry(wiki_root)
    risks = active_registry_risks(risk_registry)
    due_risks = due_risk_entries(risks, today)
    intake_risk_signals = [signal for signal in risk_registry.get("signals", []) if isinstance(signal, dict) and signal.get("status") == "Intake"]
    critical_risks = [risk for risk in risks if risk.get("severity") == "Critical"]
    weak_risks = [
        risk
        for risk in risks
        if not has_real_value(risk.get("mitigation")) or not has_real_value(risk.get("owner")) or not dates_in_text(risk.get("review", ""))
    ]
    risk_targets = due_risks or intake_risk_signals or critical_risks or weak_risks
    if risk_targets:
        target = risk_targets[0]
        target_title = str(target.get("title") or target.get("risk") or "the highest priority risk")
        reason = (
            f"{len(due_risks)} risk review(s) due."
            if due_risks
            else f"{len(intake_risk_signals)} report risk signal(s) need promotion, merge, or dismissal."
            if intake_risk_signals
            else f"{len(critical_risks)} critical risk(s) need attention."
            if critical_risks
            else f"{len(weak_risks)} active risk(s) are missing mitigation, owner, or calendar review date."
        )
        return {
            "kind": "risk",
            "label": f"Review risks: {target_title}",
            "why": reason,
            "command": f"dzcto help reports --project {sh_quote(str(project))}",
            "prompt": f"Use the Day Zero CTO review-risks workflow. Start with `{target_title}` and then continue through any due risks or intake signals. Let me keep active, update, close, punt, merge, dismiss, or mark evidence needed one item at a time. If a formal choice is made while addressing a risk, log it in core/DECISIONS.md. {context}",
        }

    decision_registry = build_decision_registry(wiki_root)
    decisions = registry_decisions(decision_registry)
    due_decisions = due_decision_entries(decisions, today)
    intake_decision_signals = [signal for signal in decision_registry.get("signals", []) if isinstance(signal, dict) and signal.get("status") == "Intake"]
    decision_targets = due_decisions or intake_decision_signals
    if decision_targets:
        target = decision_targets[0]
        target_title = str(target.get("title") or target.get("decision") or "the highest priority decision")
        reason = (
            f"{len(due_decisions)} decision revisit trigger(s) are due or marked triggered."
            if due_decisions
            else f"{len(intake_decision_signals)} report decision signal(s) need promotion or dismissal."
        )
        return {
            "kind": "decision",
            "label": f"Review decisions: {target_title}",
            "why": reason,
            "command": f"dzcto help reports --project {sh_quote(str(project))}",
            "prompt": f"Use the Day Zero CTO review-decisions workflow. Start with `{target_title}` and then continue through any due decision reviews or intake signals. Treat DECISIONS.md as the durable record of choices already taken; promote only durable decisions and dismiss ordinary asks or open questions. {context}",
        }

    learning_items = read_learning_items(learning_dir)
    if learning_items:
        return {
            "kind": "learning",
            "label": "Run learning",
            "why": "Setup, cadence, risks, and decisions do not have urgent work queued.",
            "command": f"dzcto learning --project {sh_quote(str(project))} --select",
            "prompt": f"Run a Day Zero CTO learning prompt. {context}",
        }
    return {
        "kind": "learning",
        "label": "Seed learning",
        "why": "Setup, cadence, risks, and decisions do not have urgent work queued, and no learning items exist yet.",
        "command": f"dzcto help learning --project {sh_quote(str(project))}",
        "prompt": f"Use the Day Zero CTO learning workflow to seed the first useful startup CTO system concepts, then teach one item. {context}",
    }


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
        progress.note('After that, run commands like: dzcto serve "$HOME/Documents/Arwen CTO"')


def check_stale(project: Path) -> dict[str, Any]:
    wiki_root = wiki_root_for_project(project)
    sidecar = sidecar_dir(wiki_root)
    checks: list[dict[str, Any]] = []

    def add(status: str, label: str, detail: str = "", command: str | None = None) -> None:
        entry: dict[str, Any] = {"status": status, "label": label, "detail": detail}
        if command:
            entry["command"] = command
        checks.append(entry)

    if not wiki_root.exists():
        add("fail", "Knowledge wiki", f"Missing {wiki_root}", f"dzcto init {project}")
        return {"ok": False, "stale": True, "checks": checks}

    if not (wiki_root / "index.html").exists():
        add("stale", "Wiki index", "Missing index.html", f"dzcto init {project}")
    else:
        add("pass", "Wiki index", "index.html exists")

    for doc in CORE_DOCS:
        html_path = wiki_root / "core" / core_doc_html_name(doc)
        if html_path.exists():
            add("pass", f"Core HTML {html_path.name}", "Generated core context page exists")
        else:
            add("stale", f"Core HTML {html_path.name}", f"Missing generated page for core/{doc}", f"dzcto refresh {project}")

    for relative, label in [("risks/registry.json", "Risk registry"), ("decisions/registry.json", "Decision registry")]:
        if (wiki_root / relative).exists():
            add("pass", label, f"{relative} exists")
        else:
            add("stale", label, f"Missing generated {relative}", f"dzcto refresh {project}")

    risk_registry = build_risk_registry(wiki_root)
    missing_risk_pages = []
    risk_count = 0
    for risk in risk_registry.get("risks", []):
        if not isinstance(risk, dict):
            continue
        risk_count += 1
        risk_id = str(risk.get("id") or risk.get("title") or "")
        relative = str(risk.get("detailPath") or risk_detail_relative_path(risk_id))
        if not (wiki_root / relative).exists():
            missing_risk_pages.append(relative)
    if missing_risk_pages:
        add("stale", "Risk detail pages", f"Missing {len(missing_risk_pages)} of {risk_count}: {', '.join(missing_risk_pages[:3])}", f"dzcto refresh {project}")
    elif risk_count:
        add("pass", "Risk detail pages", f"All {risk_count} generated risk detail pages exist")

    decision_registry = build_decision_registry(wiki_root)
    missing_decision_pages = []
    decision_count = 0
    for decision in decision_registry.get("decisions", []):
        if not isinstance(decision, dict):
            continue
        decision_count += 1
        decision_id = str(decision.get("id") or decision.get("title") or "")
        relative = str(decision.get("detailPath") or decision_detail_relative_path(decision_id))
        if not (wiki_root / relative).exists():
            missing_decision_pages.append(relative)
    if missing_decision_pages:
        add("stale", "Decision detail pages", f"Missing {len(missing_decision_pages)} of {decision_count}: {', '.join(missing_decision_pages[:3])}", f"dzcto refresh {project}")
    elif decision_count:
        add("pass", "Decision detail pages", f"All {decision_count} generated decision detail pages exist")

    config = read_json(sidecar / "config.json", None)
    manifest = read_json(sidecar / "manifest.json", None)
    diagnostics = read_json(sidecar / "diagnostics.json", None)

    if config is None:
        add("stale", "Sidecar config", "Missing .dzcto/config.json", f"dzcto init {project}")
    else:
        add("pass", "Sidecar config", f"schema {config.get('schemaVersion', 'unknown')}")

    if diagnostics is None:
        add("warn", "Diagnostics", "Missing .dzcto/diagnostics.json", f"dzcto doctor --project {project}")
    else:
        add("pass", "Diagnostics", f"last run {diagnostics.get('lastRunAt', 'unknown')}")

    if manifest is None:
        add("stale", "Manifest", "Missing .dzcto/manifest.json", f"dzcto init {project}")
    else:
        version = manifest.get("toolVersion")
        if version != TOOL_VERSION:
            add("stale", "Generator version", f"Manifest has {version or 'unknown'}, current is {TOOL_VERSION}", f"dzcto init {project}")
        else:
            add("pass", "Generator version", TOOL_VERSION)

        for artifact in manifest.get("artifacts", []):
            relative = artifact.get("relativePath")
            if not relative:
                continue
            if not (wiki_root / relative).exists():
                add("stale", f"Artifact {relative}", "Listed in manifest but file is missing", f"dzcto init {project}")

    cadence_rules = parse_cadence_rules(wiki_root / "core" / "OPERATING_CADENCE.md")
    if not cadence_rules:
        add("warn", "Cadence rules", "No Index Cadence Rules found in core/OPERATING_CADENCE.md")
    else:
        alerts = cadence_alerts(cadence_rules, wiki_root / "reports", dt.date.today())
        if alerts:
            for alert in alerts:
                add("stale", alert["label"], alert["reason"], alert["command"])
        else:
            add("pass", "Cadence rules", "All scheduled report cadences are current")

    missing_risk_dates = risks_missing_review_dates(wiki_root / "core")
    if missing_risk_dates:
        preview = ", ".join(missing_risk_dates[:3])
        suffix = "" if len(missing_risk_dates) <= 3 else f" and {len(missing_risk_dates) - 3} more"
        add("warn", "Risk review dates", f"Missing calendar review date: {preview}{suffix}", f"dzcto refresh {project}")
    else:
        add("pass", "Risk review dates", "All parsed active risks have calendar review dates")

    stale = any(check["status"] in {"stale", "fail"} for check in checks)
    ok = not any(check["status"] == "fail" for check in checks)
    return {"ok": ok, "stale": stale, "checks": checks}


def print_stale_report(report: dict[str, Any]) -> None:
    checks = report["checks"]
    for index, check in enumerate(checks, start=1):
        detail = f" - {check['detail']}" if check.get("detail") else ""
        print(f"[{index}/{len(checks)}] {check['status'].upper()} {check['label']}{detail}")
        if check.get("command"):
            print(f"      Run: {check['command']}")
    print()
    if report["stale"]:
        print("Day Zero CTO artifacts need attention.")
    else:
        print("Day Zero CTO artifacts are current.")


def collect_issue_bundle(project: Path, output: Path | None, do_redact: bool) -> Path:
    wiki_root = wiki_root_for_project(project)
    sidecar = sidecar_dir(wiki_root)
    report = check_stale(project)
    ensure_sidecar(wiki_root, project, "collect-issue-bundle")
    bundle_path = output or sidecar / f"issue-bundle-{utc_now().replace(':', '').replace('Z', 'Z')}.zip"
    bundle_path.parent.mkdir(parents=True, exist_ok=True)

    def maybe_redact(value: Any) -> Any:
        return redact(value) if do_redact else value

    with zipfile.ZipFile(bundle_path, "w", compression=zipfile.ZIP_DEFLATED) as bundle:
        summary = [
            "# Day Zero CTO Issue Bundle",
            "",
            f"- Tool: {TOOL_NAME}",
            f"- Version: {TOOL_VERSION}",
            f"- Created: {utc_now()}",
            f"- Project hash only: configuration files are redacted by default.",
            "",
            "This bundle intentionally excludes raw reports, source documents, and code.",
            "",
        ]
        bundle.writestr("summary.md", "\n".join(summary))
        bundle.writestr("stale-check.json", redacted_json_text(report) if do_redact else json.dumps(report, indent=2, sort_keys=True) + "\n")
        for name in ["config.json", "manifest.json", "diagnostics.json"]:
            path = sidecar / name
            if path.exists():
                payload = read_json(path, {})
                bundle.writestr(f"sidecar/{name}", redacted_json_text(payload) if do_redact else json.dumps(payload, indent=2, sort_keys=True) + "\n")
        log_path = sidecar / "logs" / "latest.log"
        if log_path.exists():
            log_text = log_path.read_text(encoding="utf-8")
            bundle.writestr("logs/latest.log", str(maybe_redact(log_text)))
    return bundle_path


def claude_desktop_skill_markdown() -> str:
    return """---
name: day-zero-cto
description: "Run the simplified Day Zero CTO CEO-report workflow: initialize artifact storage, generate weekly CEO reports, and generate custom date-range CEO reports."
---

# Day Zero CTO

Use Day Zero CTO to help an early-stage technical leader turn engineering reality into CEO-facing reports.

## Surface Notes

- In Claude Desktop chat, create or update downloadable artifacts inside Claude's available workspace unless the user has provided a mounted writable folder.
- For local filesystem report indexes, ask the user to run the local helper from a terminal or from an agent with filesystem access: `dzcto init --artifacts-dir <dir>` and `dzcto artifact --artifacts-dir <dir> --kind ceo-updates ...`.
- If the helper lives under a versioned plugin cache path, ask the user to run `dzcto install-command` once to create a stable `~/.local/bin/dzcto` command.
- Do not write Day Zero CTO artifacts into a code repo unless the user explicitly asks.
- Treat code repos as read-only evidence.

## Workflows

Read the matching reference file when needed:

- `references/dzcto-init.md`: initialize artifact storage, weekly defaults, and CEO tone.
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


def serve_project(project: Path, host: str, port: int) -> int:
    wiki_root = wiki_root_for_project(project)
    if not (wiki_root / "index.html").exists():
        code = refresh_project(project)
        if code:
            return code

    class Handler(http.server.BaseHTTPRequestHandler):
        def log_message(self, format: str, *args: Any) -> None:
            return

        def send_text(self, status: int, body: str, content_type: str = "text/plain") -> None:
            data = body.encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", f"{content_type}; charset=utf-8")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def do_POST(self) -> None:
            if urllib.parse.urlparse(self.path).path != "/__dzcto/refresh":
                self.send_text(404, "Not found")
                return
            code = refresh_project(project)
            if code:
                self.send_text(500, json.dumps({"ok": False, "code": code}), "application/json")
                return
            self.send_text(200, json.dumps({"ok": True}), "application/json")

        def do_GET(self) -> None:
            parsed = urllib.parse.urlparse(self.path)
            raw_path = urllib.parse.unquote(parsed.path).lstrip("/") or "index.html"
            candidate = (wiki_root / raw_path).resolve()
            try:
                candidate.relative_to(wiki_root)
            except ValueError:
                self.send_text(403, "Forbidden")
                return
            if candidate.is_dir():
                candidate = candidate / "index.html"
            if not candidate.exists() or not candidate.is_file():
                self.send_text(404, "Not found")
                return
            content_type = mimetypes.guess_type(candidate.name)[0] or "application/octet-stream"
            data = candidate.read_bytes()
            self.send_response(200)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

    server = http.server.ThreadingHTTPServer((host, port), Handler)
    print(f"Serving Day Zero CTO wiki at http://{host}:{port}/")
    print("Press Ctrl-C to stop.")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print()
    finally:
        server.server_close()
    return 0


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(prog="dzcto", description="Day Zero CTO local skill helper")
    sub = parser.add_subparsers(dest="command", required=True)

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

    lfg = sub.add_parser("lfg", help="Pick the next best Day Zero CTO operating action")
    lfg.add_argument("project", help="Project folder")
    lfg.add_argument("--json", action="store_true", help="Print JSON")

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
    init.add_argument("--company-name", help="Company name; persisted as companyName in .dzcto/config.json")
    init.add_argument("--company-description", help="Short company summary; persisted as companyDescription in .dzcto/config.json")
    init.add_argument("--company-url", help="Company URL; persisted as companyUrl in .dzcto/config.json")
    init.add_argument("--report-prompt-context", help="Extra context appended to report and operating prompt cards; persisted as reportPromptContext in .dzcto/config.json")
    init.add_argument("--weekly-range", help="Default CEO weekly report range, such as previous_completed_week or last_7_days")
    init.add_argument("--weekly-start-day", help="Default weekly report start day, such as Monday")
    init.add_argument("--weekly-end-day", help="Default weekly report end day, such as Sunday")
    init.add_argument("--weekly-lookback-days", type=int, help="Default rolling lookback days for weekly CEO reports")
    init.add_argument("--ceo-report-tone", help="Tone guidance for CEO reports; persisted as ceoReportTone in .dzcto/config.json")
    init.add_argument("--repo", action="append", default=[], help="Read-only code repository path; may be repeated. Persisted as codeRepos in .dzcto/config.json")

    refresh = sub.add_parser("refresh", help="Refresh wiki indexes, core HTML pages, and cadence alerts")
    refresh.add_argument("project", help="Project folder")

    serve = sub.add_parser("serve", help="Serve the wiki locally so the HTML refresh button can run Python")
    serve.add_argument("project", help="Project folder")
    serve.add_argument("--host", default="127.0.0.1")
    serve.add_argument("--port", type=int, default=8765)

    install_command = sub.add_parser("install-command", help="Install a stable dzcto command shim, such as ~/.local/bin/dzcto")
    install_command.add_argument("--dest", default=str(DEFAULT_COMMAND_DEST), help="Destination command path")
    install_command.add_argument("--force", action="store_true", help="Replace an existing command at --dest")

    stale = sub.add_parser("check-stale", help="Check whether generated artifacts need attention")
    stale.add_argument("project", help="Project folder")
    stale.add_argument("--json", action="store_true", help="Print JSON")
    stale.add_argument("--fail-on-stale", action="store_true", help="Exit 1 when stale items are found")

    status = sub.add_parser("status", help="Show project setup checklist and operating health")
    status.add_argument("project", help="Project folder")
    status.add_argument("--json", action="store_true", help="Print JSON")

    bundle = sub.add_parser("collect-issue-bundle", help="Create a redacted troubleshooting bundle")
    bundle.add_argument("project", help="Project folder")
    bundle.add_argument("--output", help="Optional zip output path")
    bundle.add_argument("--no-redact", action="store_true", help="Do not redact config/log text")

    claude_desktop = sub.add_parser("package-claude-desktop", help="Build an uploadable Claude Desktop custom skill zip")
    claude_desktop.add_argument("--output", help="Zip output path")

    snapshot = sub.add_parser("snapshot", help="Generate the CTO snapshot report from current Day Zero CTO artifacts")
    snapshot.add_argument("project", help="Project folder")
    snapshot.add_argument("--start", help="Window start date, YYYY-MM-DD. Defaults to --end minus --days + 1")
    snapshot.add_argument("--end", help="Window end date, YYYY-MM-DD. Defaults to today")
    snapshot.add_argument("--days", type=int, default=7, help="Default window length when --start is omitted")
    snapshot.add_argument("--title", help="Report title; defaults to Day Zero CTO Snapshot Report <start>-<end>")
    snapshot.add_argument("--date", help="Report date; defaults to --end or today")
    snapshot.add_argument("--output-json", help="Write structured report JSON to this path")
    snapshot.add_argument("--json", action="store_true", help="Print structured JSON")
    snapshot.add_argument("--no-artifact", action="store_true", help="Only write/print JSON; do not render HTML artifact")

    accountability = sub.add_parser("codebase-accountability", help="Generate a codebase accountability report from local Git history")
    accountability.add_argument("project", help="Project folder")
    accountability.add_argument("--repo", action="append", default=[], help="Read-only code repository path; may be repeated")
    accountability.add_argument("--since", help="Git --since value; defaults to --days")
    accountability.add_argument("--days", type=int, default=7, help="Default rolling lookback window when --since is omitted")
    accountability.add_argument("--title", default="Codebase Accountability", help="Report title")
    accountability.add_argument("--date", help="Report date")
    accountability.add_argument("--output-json", help="Write structured report JSON to this path")
    accountability.add_argument("--json", action="store_true", help="Print structured JSON")
    accountability.add_argument("--no-artifact", action="store_true", help="Only write/print JSON; do not render HTML artifact")

    artifact = sub.add_parser("artifact", help="Generate a structured report artifact")
    artifact.add_argument("--project")
    artifact.add_argument("--artifacts-dir", help="Folder that directly stores index.html, reports/, and .dzcto/")
    artifact.add_argument("--kind", required=True)
    artifact.add_argument("--title", required=True)
    artifact.add_argument("--date")
    artifact.add_argument("--data-file")
    artifact.add_argument("--body-file")

    learning = sub.add_parser("learning", help="Manage spaced-repetition learning state")
    learning.add_argument("--project", required=True, help="Project folder")
    learning.add_argument("--date")
    learning_mode = learning.add_mutually_exclusive_group()
    learning_mode.add_argument("--select", action="store_true")
    learning_mode.add_argument("--add", action="store_true")
    learning_mode.add_argument("--seed-file")
    learning_mode.add_argument("--record")
    learning_mode.add_argument("--stats", action="store_true")
    learning.add_argument("--id")
    learning.add_argument("--title")
    learning.add_argument("--summary")
    learning.add_argument("--details")
    learning.add_argument("--details-file")
    learning.add_argument("--source")
    learning.add_argument("--tags")
    learning.add_argument("--note")

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

    if args.command == "lfg":
        return print_lfg_action(next_lfg_action(resolve_project(args.project)), as_json=args.json)

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
        if not args.project and not args.artifacts_dir:
            parser.error("dzcto init requires a project folder or --artifacts-dir")
        init_args = ["--init"]
        if args.project:
            init_args.extend(["--project", str(resolve_project(args.project))])
        if args.artifacts_dir:
            init_args.extend(["--artifacts-dir", str(Path(args.artifacts_dir).expanduser().resolve())])
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
        for repo in args.repo:
            init_args.extend(["--repo", repo])
        return run_script("dzcto_artifact.py", init_args)

    if args.command == "refresh":
        project = resolve_project(args.project)
        require_existing_wiki(project)
        return refresh_project(project)

    if args.command == "serve":
        project = resolve_project(args.project)
        require_existing_wiki(project)
        return serve_project(project, args.host, args.port)

    if args.command == "install-command":
        progress = Progress(2)
        install_command_shim(Path(args.dest), args.force, progress)
        progress.step("Next step", "open a new shell or make sure the destination directory is on PATH")
        return 0

    if args.command == "check-stale":
        project = resolve_project(args.project)
        report = check_stale(project)
        if args.json:
            print(json.dumps(report, indent=2, sort_keys=True))
        else:
            print_stale_report(report)
        return 1 if args.fail_on_stale and report["stale"] else 0

    if args.command == "status":
        return print_project_status(resolve_project(args.project), as_json=args.json)

    if args.command == "collect-issue-bundle":
        project = resolve_project(args.project)
        output = Path(args.output).expanduser().resolve() if args.output else None
        path = collect_issue_bundle(project, output, not args.no_redact)
        print(path)
        return 0

    if args.command == "package-claude-desktop":
        output = Path(args.output).expanduser().resolve() if args.output else None
        path = package_claude_desktop(output)
        print(path)
        return 0

    if args.command == "snapshot":
        return run_snapshot(args)

    if args.command == "codebase-accountability":
        return run_codebase_accountability(args)

    if args.command == "artifact":
        if not args.project and not args.artifacts_dir:
            parser.error("dzcto artifact requires --project or --artifacts-dir")
        artifact_args = ["--kind", args.kind, "--title", args.title]
        if args.project:
            artifact_args.extend(["--project", args.project])
        if args.artifacts_dir:
            artifact_args.extend(["--artifacts-dir", args.artifacts_dir])
        if args.date:
            artifact_args.extend(["--date", args.date])
        if args.data_file:
            artifact_args.extend(["--data-file", args.data_file])
        if args.body_file:
            artifact_args.extend(["--body-file", args.body_file])
        return run_script("dzcto_artifact.py", artifact_args)

    if args.command == "learning":
        learning_args = ["--project", args.project]
        for flag in ["date", "id", "title", "summary", "details", "details_file", "source", "tags", "note"]:
            value = getattr(args, flag)
            if value:
                learning_args.extend([f"--{flag.replace('_', '-')}", value])
        if args.select:
            learning_args.append("--select")
        if args.add:
            learning_args.append("--add")
        if args.seed_file:
            learning_args.extend(["--seed-file", args.seed_file])
        if args.record:
            learning_args.extend(["--record", args.record])
        if args.stats:
            learning_args.append("--stats")
        return run_script("dzcto_learning.py", learning_args)

    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))

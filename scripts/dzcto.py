#!/usr/bin/env python3
"""User-facing Day Zero CTO command wrapper."""

from __future__ import annotations

import argparse
import datetime as dt
import json
import subprocess
import sys
import zipfile
from pathlib import Path
from typing import Any

from dzcto_artifact import cadence_alerts, parse_cadence_rules
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


def script_path(name: str) -> Path:
    return Path(__file__).resolve().with_name(name)


def run_script(name: str, args: list[str]) -> int:
    return subprocess.call([sys.executable, str(script_path(name)), *args])


def resolve_project(path: str) -> Path:
    return Path(path).expanduser().resolve()


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


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(prog="dzcto", description="Day Zero CTO local skill helper")
    sub = parser.add_subparsers(dest="command", required=True)

    setup = sub.add_parser("setup", help="Install Day Zero CTO for Codex Desktop")
    setup.add_argument("--editable-skills", action="store_true", help="Also link skills into ~/.codex/skills for active Codex development")

    doctor = sub.add_parser("doctor", help="Check install and optional project health")
    doctor.add_argument("--project", help="Optional project folder")

    init = sub.add_parser("init", help="Create or refresh a project knowledge wiki")
    init.add_argument("project", help="Project folder, such as ~/Documents/Acme")

    stale = sub.add_parser("check-stale", help="Check whether generated artifacts need attention")
    stale.add_argument("project", help="Project folder")
    stale.add_argument("--json", action="store_true", help="Print JSON")
    stale.add_argument("--fail-on-stale", action="store_true", help="Exit 1 when stale items are found")

    bundle = sub.add_parser("collect-issue-bundle", help="Create a redacted troubleshooting bundle")
    bundle.add_argument("project", help="Project folder")
    bundle.add_argument("--output", help="Optional zip output path")
    bundle.add_argument("--no-redact", action="store_true", help="Do not redact config/log text")

    artifact = sub.add_parser("artifact", help="Generate a structured report artifact")
    artifact.add_argument("--project", required=True)
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

    if args.command == "setup":
        progress = Progress(4 if args.editable_skills else 3)
        progress.step("Install Codex plugin marketplace entry")
        code = run_script("install_local_marketplace.py", [])
        if code:
            return code
        if args.editable_skills:
            progress.step("Install editable Codex skill links")
            code = run_script("install_local_skills.py", [])
            if code:
                return code
        progress.step("Run install doctor")
        code = run_script("dzcto_doctor.py", [])
        if code:
            return code
        progress.step("Next step", "restart Codex Desktop or start a fresh session")
        return 0

    if args.command == "doctor":
        doctor_args = ["--project", args.project] if args.project else []
        return run_script("dzcto_doctor.py", doctor_args)

    if args.command == "init":
        project = resolve_project(args.project)
        return run_script("dzcto_artifact.py", ["--project", str(project), "--init"])

    if args.command == "check-stale":
        project = resolve_project(args.project)
        report = check_stale(project)
        if args.json:
            print(json.dumps(report, indent=2, sort_keys=True))
        else:
            print_stale_report(report)
        return 1 if args.fail_on_stale and report["stale"] else 0

    if args.command == "collect-issue-bundle":
        project = resolve_project(args.project)
        output = Path(args.output).expanduser().resolve() if args.output else None
        path = collect_issue_bundle(project, output, not args.no_redact)
        print(path)
        return 0

    if args.command == "artifact":
        artifact_args = ["--project", args.project, "--kind", args.kind, "--title", args.title]
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

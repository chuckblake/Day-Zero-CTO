#!/usr/bin/env python3
"""User-facing Day Zero CTO command wrapper."""

from __future__ import annotations

import argparse
import datetime as dt
import http.server
import json
import mimetypes
import subprocess
import sys
import urllib.parse
import zipfile
from pathlib import Path
from typing import Any

from dzcto_artifact import CORE_DOCS, cadence_alerts, core_doc_html_name, parse_cadence_rules
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


def refresh_project(project: Path) -> int:
    return run_script("dzcto_artifact.py", ["--project", str(project), "--init"])


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


def claude_desktop_skill_markdown() -> str:
    return """---
name: day-zero-cto
description: "Run Day Zero CTO workflows for early-stage technical leaders: onboarding, CTO context, tech stack mapping, risk reviews, weekly CTO reviews, CEO updates, decision help, CTO code review, and spaced-repetition learning. Use when the user asks for Day Zero CTO, CTO onboarding, startup technical leadership workflows, or durable CTO artifacts."
---

# Day Zero CTO

Use Day Zero CTO to help an early-stage technical leader organize company context, operating cadence, reports, decisions, risks, and learning.

## Surface Notes

- In Claude Desktop chat, create or update downloadable artifacts inside Claude's available workspace unless the user has provided a mounted writable folder.
- For local filesystem wikis, ask the user to run the local helper from a terminal or from an agent with filesystem access: `dzcto init`, `dzcto refresh`, `dzcto serve`, and `dzcto artifact`.
- Do not write Day Zero CTO artifacts into a code repo unless the user explicitly asks.
- Treat code repos as read-only evidence by default; multiple repos are allowed.

## Workflows

Read the matching reference file when needed:

- `references/bootstrap-cto-context.md`: onboarding and project wiki setup.
- `references/tech-stack.md`: codebase stack mapping.
- `references/review-engineering-risk.md`: engineering risk review.
- `references/weekly-cto-review.md`: weekly CTO operating review.
- `references/write-ceo-update.md`: CEO-facing update.
- `references/work-through-problem.md`: decision and problem walkthroughs.
- `references/cto-code-review.md`: startup CTO code review.
- `references/learning.md`: spaced-repetition learning.

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

    setup = sub.add_parser("setup", help="Install Day Zero CTO for Codex Desktop")
    setup.add_argument("--editable-skills", action="store_true", help="Also link skills into ~/.codex/skills for active Codex development")
    setup.add_argument("--plugin-link", help="Where to create the local plugin symlink")
    setup.add_argument("--marketplace-file", help="Codex plugin marketplace/settings JSON file")
    setup.add_argument("--editable-skills-dir", help="Destination directory for editable skill symlinks")
    setup.add_argument("--wiki-project", help="Optional project folder to initialize during setup")
    setup.add_argument("--company-name")
    setup.add_argument("--company-description")
    setup.add_argument("--company-url")
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

    init = sub.add_parser("init", help="Create or refresh a project knowledge wiki")
    init.add_argument("project", help="Project folder, such as ~/Documents/Acme")
    init.add_argument("--company-name")
    init.add_argument("--company-description")
    init.add_argument("--company-url")
    init.add_argument("--repo", action="append", default=[], help="Read-only code repository path; may be repeated")

    refresh = sub.add_parser("refresh", help="Refresh wiki indexes, core HTML pages, and cadence alerts")
    refresh.add_argument("project", help="Project folder")

    serve = sub.add_parser("serve", help="Serve the wiki locally so the HTML refresh button can run Python")
    serve.add_argument("project", help="Project folder")
    serve.add_argument("--host", default="127.0.0.1")
    serve.add_argument("--port", type=int, default=8765)

    stale = sub.add_parser("check-stale", help="Check whether generated artifacts need attention")
    stale.add_argument("project", help="Project folder")
    stale.add_argument("--json", action="store_true", help="Print JSON")
    stale.add_argument("--fail-on-stale", action="store_true", help="Exit 1 when stale items are found")

    bundle = sub.add_parser("collect-issue-bundle", help="Create a redacted troubleshooting bundle")
    bundle.add_argument("project", help="Project folder")
    bundle.add_argument("--output", help="Optional zip output path")
    bundle.add_argument("--no-redact", action="store_true", help="Do not redact config/log text")

    claude_desktop = sub.add_parser("package-claude-desktop", help="Build an uploadable Claude Desktop custom skill zip")
    claude_desktop.add_argument("--output", help="Zip output path")

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
        project = resolve_project(args.project)
        init_args = ["--project", str(project), "--init"]
        if args.company_name:
            init_args.extend(["--company-name", args.company_name])
        if args.company_description:
            init_args.extend(["--company-description", args.company_description])
        if args.company_url:
            init_args.extend(["--company-url", args.company_url])
        for repo in args.repo:
            init_args.extend(["--repo", repo])
        return run_script("dzcto_artifact.py", init_args)

    if args.command == "refresh":
        return refresh_project(resolve_project(args.project))

    if args.command == "serve":
        return serve_project(resolve_project(args.project), args.host, args.port)

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

    if args.command == "package-claude-desktop":
        output = Path(args.output).expanduser().resolve() if args.output else None
        path = package_claude_desktop(output)
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

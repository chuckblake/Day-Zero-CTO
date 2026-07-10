#!/usr/bin/env python3
"""Preflight checks for Day Zero CTO installs."""

from __future__ import annotations

import argparse
import ast
import json
import os
import sys
from pathlib import Path
from typing import Any

from dzcto_common import sidecar_dir


REPO_ROOT = Path(__file__).resolve().parents[1]
REQUIRED_PYTHON = (3, 10)


def check(result: list[dict[str, Any]], status: str, label: str, detail: str = "") -> None:
    result.append({"status": status, "label": label, "detail": detail})


def executable(path: Path) -> bool:
    return path.exists() and os.access(path, os.X_OK)


def compile_script(path: Path) -> tuple[bool, str]:
    try:
        ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    except SyntaxError as error:
        return False, str(error)
    return True, ""


def run_checks(project: Path | None) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []

    if sys.version_info >= REQUIRED_PYTHON:
        check(results, "pass", "Python runtime", f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}")
    else:
        check(
            results,
            "fail",
            "Python runtime",
            f"Python {REQUIRED_PYTHON[0]}.{REQUIRED_PYTHON[1]}+ required; found {sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}",
        )

    for relative in [
        ".codex-plugin/plugin.json",
        ".claude-plugin/plugin.json",
        ".claude-plugin/marketplace.json",
    ]:
        path = REPO_ROOT / relative
        if not path.exists():
            check(results, "fail", relative, "Missing file")
            continue
        try:
            json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as error:
            check(results, "fail", relative, f"Invalid JSON: {error}")
        else:
            check(results, "pass", relative, "Valid JSON")

    skills_dir = REPO_ROOT / "skills"
    if not skills_dir.exists():
        check(results, "fail", "skills/", "Missing skills directory")
    else:
        skill_count = len([path for path in skills_dir.iterdir() if (path / "SKILL.md").exists()])
        check(results, "pass" if skill_count else "fail", "skills/", f"{skill_count} skills with SKILL.md")

    for relative in [
        "scripts/dzcto_artifact.py",
        "scripts/dzcto.py",
        "scripts/dzcto_common.py",
        "scripts/dzcto_learning.py",
        "scripts/dzcto_doctor.py",
        "scripts/dzcto_progress.py",
        "scripts/install_local_marketplace.py",
        "scripts/install_local_skills.py",
        "scripts/uninstall_local.py",
    ]:
        path = REPO_ROOT / relative
        if not path.exists():
            check(results, "fail", relative, "Missing file")
            continue
        ok, detail = compile_script(path)
        check(results, "pass" if ok else "fail", relative, "Syntax OK" if ok else detail)

    for relative in ["bin/dzcto", "bin/dzcto-artifact", "bin/dzcto-learning", "bin/dzcto-doctor"]:
        path = REPO_ROOT / relative
        check(results, "pass" if executable(path) else "fail", relative, "Executable" if executable(path) else "Missing or not executable")

    if project:
        parent = project if project.exists() else project.parent
        if not parent.exists():
            check(results, "fail", "Project folder", f"Parent does not exist: {parent}")
        elif not os.access(parent, os.W_OK):
            check(results, "fail", "Project folder", f"Not writable: {parent}")
        else:
            check(results, "pass", "Project folder", str(project))

        wiki = project / "knowledge" / "wiki"
        if wiki.exists():
            check(results, "pass", "Knowledge wiki", str(wiki))
            sidecar = sidecar_dir(wiki)
            for name in ["config.json", "manifest.json", "diagnostics.json", "logs/latest.log"]:
                path = sidecar / name
                check(results, "pass" if path.exists() else "warn", f"Sidecar {name}", "Present" if path.exists() else "Missing; run dzcto init")
            for relative in ["index.html", "reports/ceo-updates"]:
                path = wiki / relative
                check(results, "pass" if path.exists() else "warn", relative, "Present" if path.exists() else "Missing; rerun dzcto init")
        else:
            check(results, "warn", "Knowledge wiki", f"Not created yet; run dzcto init {project}")

    return results


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description="Check Day Zero CTO install health")
    parser.add_argument("--project", help="Optional project folder to check")
    parser.add_argument("--json", action="store_true", help="Print machine-readable JSON")
    args = parser.parse_args(argv)

    project = Path(args.project).expanduser().resolve() if args.project else None
    results = run_checks(project)
    failed = [result for result in results if result["status"] == "fail"]

    if args.json:
        checks = [dict(result, index=index, total=len(results)) for index, result in enumerate(results, start=1)]
        print(json.dumps({"ok": not failed, "checks": checks}, indent=2))
    else:
        icons = {"pass": "PASS", "warn": "WARN", "fail": "FAIL"}
        for index, result in enumerate(results, start=1):
            detail = f" - {result['detail']}" if result.get("detail") else ""
            print(f"[{index}/{len(results)}] {icons[result['status']]} {result['label']}{detail}")
        print()
        print("Day Zero CTO install is ready." if not failed else "Day Zero CTO install needs attention.")

    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))

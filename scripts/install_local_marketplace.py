#!/usr/bin/env python3
"""Install Day Zero CTO into the local Codex Desktop plugin marketplace."""

from __future__ import annotations

import json
import os
from pathlib import Path

from dzcto_progress import Progress


REPO_ROOT = Path(__file__).resolve().parents[1]
PLUGIN_NAME = "day-zero-cto"
PLUGIN_LINK = Path.home() / "plugins" / PLUGIN_NAME
MARKETPLACE_PATH = Path.home() / ".agents" / "plugins" / "marketplace.json"


def read_marketplace(progress: Progress) -> dict:
    if MARKETPLACE_PATH.exists():
        try:
            payload = json.loads(MARKETPLACE_PATH.read_text(encoding="utf-8"))
            progress.note(f"Loaded existing marketplace: {MARKETPLACE_PATH}")
            return payload if isinstance(payload, dict) else {}
        except json.JSONDecodeError:
            progress.note(f"Existing marketplace was invalid JSON; rewriting: {MARKETPLACE_PATH}")
            return {}
    progress.note(f"No marketplace yet; creating: {MARKETPLACE_PATH}")
    return {
        "name": "personal",
        "interface": {
            "displayName": "Personal",
        },
        "plugins": [],
    }


def write_marketplace_entry(progress: Progress) -> None:
    MARKETPLACE_PATH.parent.mkdir(parents=True, exist_ok=True)
    payload = read_marketplace(progress)
    payload.setdefault("plugins", [])

    entry = {
        "name": PLUGIN_NAME,
        "source": {
            "source": "local",
            "path": f"./plugins/{PLUGIN_NAME}",
        },
        "policy": {
            "installation": "AVAILABLE",
            "authentication": "ON_INSTALL",
        },
        "category": "Productivity",
    }

    for index, plugin in enumerate(payload["plugins"]):
        if isinstance(plugin, dict) and plugin.get("name") == PLUGIN_NAME:
            payload["plugins"][index] = entry
            progress.note("Updated existing day-zero-cto marketplace entry")
            break
    else:
        payload["plugins"].append(entry)
        progress.note("Added day-zero-cto marketplace entry")

    MARKETPLACE_PATH.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def link_plugin(progress: Progress) -> None:
    PLUGIN_LINK.parent.mkdir(parents=True, exist_ok=True)

    if PLUGIN_LINK.is_symlink():
        current_target = (PLUGIN_LINK.parent / os.readlink(PLUGIN_LINK)).resolve()
        if current_target != REPO_ROOT:
            PLUGIN_LINK.unlink()
            PLUGIN_LINK.symlink_to(REPO_ROOT)
            progress.note(f"Repointed plugin link: {PLUGIN_LINK} -> {REPO_ROOT}")
        else:
            progress.note(f"Plugin link already correct: {PLUGIN_LINK} -> {REPO_ROOT}")
    elif PLUGIN_LINK.exists():
        raise SystemExit(f"{PLUGIN_LINK} already exists and is not a symlink. Move it aside, then rerun this script.")
    else:
        PLUGIN_LINK.symlink_to(REPO_ROOT)
        progress.note(f"Created plugin link: {PLUGIN_LINK} -> {REPO_ROOT}")


def main() -> int:
    progress = Progress(6)
    progress.step("Verify install target", "Codex Desktop local plugin marketplace")
    progress.step("Locate repo", str(REPO_ROOT))
    progress.step("Create or update plugin symlink")
    link_plugin(progress)
    progress.step("Create or update marketplace entry")
    write_marketplace_entry(progress)
    progress.step("Summarize install")
    progress.note(f"Plugin link: {PLUGIN_LINK} -> {REPO_ROOT}")
    progress.note(f"Marketplace: {MARKETPLACE_PATH}")
    progress.step("Next step", "Restart Codex Desktop or start a fresh session")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

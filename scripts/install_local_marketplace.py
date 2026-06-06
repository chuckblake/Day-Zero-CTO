#!/usr/bin/env python3
"""Install Day Zero CTO into the local Codex Desktop plugin marketplace."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

from dzcto_progress import Progress


REPO_ROOT = Path(__file__).resolve().parents[1]
PLUGIN_NAME = "day-zero-cto"
DEFAULT_PLUGIN_LINK = Path.home() / "plugins" / PLUGIN_NAME
DEFAULT_MARKETPLACE_PATH = Path.home() / ".agents" / "plugins" / "marketplace.json"


def absolute_without_resolving(path: str) -> Path:
    expanded = Path(path).expanduser()
    return expanded if expanded.is_absolute() else (Path.cwd() / expanded).absolute()


def plugin_source_path(plugin_link: Path, marketplace_path: Path) -> str:
    if plugin_link == DEFAULT_PLUGIN_LINK and marketplace_path == DEFAULT_MARKETPLACE_PATH:
        return f"./plugins/{PLUGIN_NAME}"
    return str(plugin_link)


def read_marketplace(progress: Progress, marketplace_path: Path) -> dict:
    if marketplace_path.exists():
        try:
            payload = json.loads(marketplace_path.read_text(encoding="utf-8"))
            progress.note(f"Loaded existing marketplace: {marketplace_path}")
            return payload if isinstance(payload, dict) else {}
        except json.JSONDecodeError:
            progress.note(f"Existing marketplace was invalid JSON; rewriting: {marketplace_path}")
            return {}
    progress.note(f"No marketplace yet; creating: {marketplace_path}")
    return {
        "name": "personal",
        "interface": {
            "displayName": "Personal",
        },
        "plugins": [],
    }


def write_marketplace_entry(progress: Progress, plugin_link: Path, marketplace_path: Path) -> None:
    marketplace_path.parent.mkdir(parents=True, exist_ok=True)
    payload = read_marketplace(progress, marketplace_path)
    payload.setdefault("plugins", [])

    entry = {
        "name": PLUGIN_NAME,
        "source": {
            "source": "local",
            "path": plugin_source_path(plugin_link, marketplace_path),
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

    marketplace_path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def link_plugin(progress: Progress, plugin_link: Path) -> None:
    plugin_link.parent.mkdir(parents=True, exist_ok=True)

    if plugin_link.is_symlink():
        current_target = (plugin_link.parent / os.readlink(plugin_link)).resolve()
        if current_target != REPO_ROOT:
            plugin_link.unlink()
            plugin_link.symlink_to(REPO_ROOT)
            progress.note(f"Repointed plugin link: {plugin_link} -> {REPO_ROOT}")
        else:
            progress.note(f"Plugin link already correct: {plugin_link} -> {REPO_ROOT}")
    elif plugin_link.exists():
        raise SystemExit(f"{plugin_link} already exists and is not a symlink. Move it aside, then rerun this script.")
    else:
        plugin_link.symlink_to(REPO_ROOT)
        progress.note(f"Created plugin link: {plugin_link} -> {REPO_ROOT}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Install Day Zero CTO into a local Codex Desktop plugin marketplace")
    parser.add_argument("--plugin-link", default=str(DEFAULT_PLUGIN_LINK), help="Where to create the local plugin symlink")
    parser.add_argument("--marketplace-file", default=str(DEFAULT_MARKETPLACE_PATH), help="Codex plugin marketplace/settings JSON file")
    args = parser.parse_args()

    plugin_link = absolute_without_resolving(args.plugin_link)
    marketplace_path = absolute_without_resolving(args.marketplace_file)

    progress = Progress(6)
    progress.step("Verify install target", "Codex Desktop local plugin marketplace")
    progress.step("Locate repo", str(REPO_ROOT))
    progress.step("Create or update plugin symlink")
    link_plugin(progress, plugin_link)
    progress.step("Create or update marketplace entry")
    write_marketplace_entry(progress, plugin_link, marketplace_path)
    progress.step("Summarize install")
    progress.note(f"Plugin link: {plugin_link} -> {REPO_ROOT}")
    progress.note(f"Marketplace: {marketplace_path}")
    progress.step("Next step", "Restart Codex Desktop or start a fresh session")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

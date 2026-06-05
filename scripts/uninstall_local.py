#!/usr/bin/env python3
"""Remove local Day Zero CTO Codex Desktop install links safely."""

from __future__ import annotations

import json
import os
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
PLUGIN_NAME = "day-zero-cto"
PLUGIN_LINK = Path.home() / "plugins" / PLUGIN_NAME
MARKETPLACE_PATH = Path.home() / ".agents" / "plugins" / "marketplace.json"
SKILLS_DIR = REPO_ROOT / "skills"
DEST_DIR = Path.home() / ".codex" / "skills"


def resolved_symlink(path: Path) -> Path:
    return (path.parent / os.readlink(path)).resolve()


def remove_plugin_link() -> None:
    if not PLUGIN_LINK.exists() and not PLUGIN_LINK.is_symlink():
        print(f"No plugin link found at {PLUGIN_LINK}")
        return
    if not PLUGIN_LINK.is_symlink():
        print(f"Skipped {PLUGIN_LINK}: exists but is not a symlink")
        return

    target = resolved_symlink(PLUGIN_LINK)
    if target == REPO_ROOT:
        PLUGIN_LINK.unlink()
        print(f"Removed plugin link {PLUGIN_LINK}")
    else:
        print(f"Skipped {PLUGIN_LINK}: points to {target}, not {REPO_ROOT}")


def remove_marketplace_entry() -> None:
    if not MARKETPLACE_PATH.exists():
        print(f"No marketplace file found at {MARKETPLACE_PATH}")
        return

    payload = json.loads(MARKETPLACE_PATH.read_text(encoding="utf-8"))
    plugins = payload.get("plugins")
    if not isinstance(plugins, list):
        print(f"Skipped {MARKETPLACE_PATH}: no plugins array")
        return

    kept = [plugin for plugin in plugins if not (isinstance(plugin, dict) and plugin.get("name") == PLUGIN_NAME)]
    removed = len(plugins) - len(kept)
    if removed:
        payload["plugins"] = kept
        MARKETPLACE_PATH.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
        print(f"Removed {removed} marketplace entry from {MARKETPLACE_PATH}")
    else:
        print(f"No {PLUGIN_NAME} marketplace entry found")


def remove_editable_skill_links() -> None:
    if not DEST_DIR.exists() or not SKILLS_DIR.exists():
        print("No editable skill links to remove")
        return

    removed = 0
    for source in sorted(SKILLS_DIR.iterdir()):
        if not source.is_dir() or not (source / "SKILL.md").exists():
            continue
        destination = DEST_DIR / source.name
        if not destination.is_symlink():
            continue
        if resolved_symlink(destination) != source:
            continue
        destination.unlink()
        removed += 1
        print(f"Removed editable skill link {destination}")

    if not removed:
        print("No editable skill links pointed at this clone")


def main() -> int:
    remove_plugin_link()
    remove_marketplace_entry()
    remove_editable_skill_links()
    print("Local Day Zero CTO uninstall cleanup complete.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

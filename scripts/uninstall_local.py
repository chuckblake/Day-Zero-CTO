#!/usr/bin/env python3
"""Remove local Day Zero CTO Codex Desktop install links safely."""

from __future__ import annotations

import json
import os
from pathlib import Path

from dzcto_progress import Progress


REPO_ROOT = Path(__file__).resolve().parents[1]
PLUGIN_NAME = "day-zero-cto"
PLUGIN_LINK = Path.home() / "plugins" / PLUGIN_NAME
MARKETPLACE_PATH = Path.home() / ".agents" / "plugins" / "marketplace.json"
SKILLS_DIR = REPO_ROOT / "skills"
DEST_DIR = Path.home() / ".codex" / "skills"


def resolved_symlink(path: Path) -> Path:
    return (path.parent / os.readlink(path)).resolve()


def remove_plugin_link(progress: Progress) -> None:
    if not PLUGIN_LINK.exists() and not PLUGIN_LINK.is_symlink():
        progress.note(f"No plugin link found at {PLUGIN_LINK}")
        return
    if not PLUGIN_LINK.is_symlink():
        progress.note(f"Skipped {PLUGIN_LINK}: exists but is not a symlink")
        return

    target = resolved_symlink(PLUGIN_LINK)
    if target == REPO_ROOT:
        PLUGIN_LINK.unlink()
        progress.note(f"Removed plugin link {PLUGIN_LINK}")
    else:
        progress.note(f"Skipped {PLUGIN_LINK}: points to {target}, not {REPO_ROOT}")


def remove_marketplace_entry(progress: Progress) -> None:
    if not MARKETPLACE_PATH.exists():
        progress.note(f"No marketplace file found at {MARKETPLACE_PATH}")
        return

    payload = json.loads(MARKETPLACE_PATH.read_text(encoding="utf-8"))
    plugins = payload.get("plugins")
    if not isinstance(plugins, list):
        progress.note(f"Skipped {MARKETPLACE_PATH}: no plugins array")
        return

    kept = [plugin for plugin in plugins if not (isinstance(plugin, dict) and plugin.get("name") == PLUGIN_NAME)]
    removed = len(plugins) - len(kept)
    if removed:
        payload["plugins"] = kept
        MARKETPLACE_PATH.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
        progress.note(f"Removed {removed} marketplace entry from {MARKETPLACE_PATH}")
    else:
        progress.note(f"No {PLUGIN_NAME} marketplace entry found")


def editable_skill_links() -> list[Path]:
    if not DEST_DIR.exists() or not SKILLS_DIR.exists():
        return []

    links = []
    for source in sorted(SKILLS_DIR.iterdir()):
        if not source.is_dir() or not (source / "SKILL.md").exists():
            continue
        destination = DEST_DIR / source.name
        if not destination.is_symlink():
            continue
        if resolved_symlink(destination) != source:
            continue
        links.append(destination)
    return links


def remove_editable_skill_link(progress: Progress, destination: Path) -> None:
    destination.unlink()
    progress.note(f"Removed editable skill link {destination}")


def main() -> int:
    skill_links = editable_skill_links()
    progress = Progress(4 + len(skill_links) if skill_links else 5)
    progress.step("Verify uninstall target", "local Day Zero CTO links for this clone")
    progress.step("Remove Codex plugin symlink")
    remove_plugin_link(progress)
    progress.step("Remove Codex marketplace entry")
    remove_marketplace_entry(progress)
    if skill_links:
        for destination in skill_links:
            progress.step("Remove editable skill link", destination.name)
            remove_editable_skill_link(progress, destination)
    else:
        progress.step("Remove editable skill links", "none found")
        progress.note("No editable skill links pointed at this clone")
    progress.step("Next step", "run python3 scripts/install_local_marketplace.py to reinstall")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

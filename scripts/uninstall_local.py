#!/usr/bin/env python3
"""Remove local Day Zero CTO Codex Desktop install links safely."""

from __future__ import annotations

import json
import os
import argparse
from pathlib import Path

from dzcto_progress import Progress


REPO_ROOT = Path(__file__).resolve().parents[1]
PLUGIN_NAME = "day-zero-cto"
DEFAULT_PLUGIN_LINK = Path.home() / "plugins" / PLUGIN_NAME
DEFAULT_MARKETPLACE_PATH = Path.home() / ".agents" / "plugins" / "marketplace.json"
SKILLS_DIR = REPO_ROOT / "skills"
DEFAULT_DEST_DIR = Path.home() / ".codex" / "skills"


def absolute_without_resolving(path: str) -> Path:
    expanded = Path(path).expanduser()
    return expanded if expanded.is_absolute() else (Path.cwd() / expanded).absolute()


def resolved_symlink(path: Path) -> Path:
    return (path.parent / os.readlink(path)).resolve()


def remove_plugin_link(progress: Progress, plugin_link: Path) -> None:
    if not plugin_link.exists() and not plugin_link.is_symlink():
        progress.note(f"No plugin link found at {plugin_link}")
        return
    if not plugin_link.is_symlink():
        progress.note(f"Skipped {plugin_link}: exists but is not a symlink")
        return

    target = resolved_symlink(plugin_link)
    if target == REPO_ROOT:
        plugin_link.unlink()
        progress.note(f"Removed plugin link {plugin_link}")
    else:
        progress.note(f"Skipped {plugin_link}: points to {target}, not {REPO_ROOT}")


def remove_marketplace_entry(progress: Progress, marketplace_path: Path) -> None:
    if not marketplace_path.exists():
        progress.note(f"No marketplace file found at {marketplace_path}")
        return

    payload = json.loads(marketplace_path.read_text(encoding="utf-8"))
    plugins = payload.get("plugins")
    if not isinstance(plugins, list):
        progress.note(f"Skipped {marketplace_path}: no plugins array")
        return

    kept = [plugin for plugin in plugins if not (isinstance(plugin, dict) and plugin.get("name") == PLUGIN_NAME)]
    removed = len(plugins) - len(kept)
    if removed:
        payload["plugins"] = kept
        marketplace_path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
        progress.note(f"Removed {removed} marketplace entry from {marketplace_path}")
    else:
        progress.note(f"No {PLUGIN_NAME} marketplace entry found")


def editable_skill_links(dest_dir: Path) -> list[Path]:
    if not dest_dir.exists() or not SKILLS_DIR.exists():
        return []

    links = []
    for destination in sorted(dest_dir.iterdir()):
        if not destination.is_symlink():
            continue
        target = resolved_symlink(destination)
        if not str(target).startswith(str(SKILLS_DIR) + os.sep):
            continue
        links.append(destination)
    return links


def remove_editable_skill_link(progress: Progress, destination: Path) -> None:
    destination.unlink()
    progress.note(f"Removed editable skill link {destination}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Remove local Day Zero CTO Codex Desktop install links safely")
    parser.add_argument("--plugin-link", default=str(DEFAULT_PLUGIN_LINK), help="Plugin symlink to remove if it points at this clone")
    parser.add_argument("--marketplace-file", default=str(DEFAULT_MARKETPLACE_PATH), help="Codex plugin marketplace/settings JSON file")
    parser.add_argument("--editable-skills-dir", default=str(DEFAULT_DEST_DIR), help="Codex editable skills directory")
    args = parser.parse_args()

    plugin_link = absolute_without_resolving(args.plugin_link)
    marketplace_path = absolute_without_resolving(args.marketplace_file)
    dest_dir = absolute_without_resolving(args.editable_skills_dir)

    skill_links = editable_skill_links(dest_dir)
    progress = Progress(4 + len(skill_links) if skill_links else 5)
    progress.step("Verify uninstall target", "local Day Zero CTO links for this clone")
    progress.step("Remove Codex plugin symlink")
    remove_plugin_link(progress, plugin_link)
    progress.step("Remove Codex marketplace entry")
    remove_marketplace_entry(progress, marketplace_path)
    if skill_links:
        for destination in skill_links:
            progress.step("Remove editable skill link", destination.name)
            remove_editable_skill_link(progress, destination)
    else:
        progress.step("Remove editable skill links", "none found")
        progress.note("No editable skill links pointed at this clone")
    progress.step("Next step", "run bin/dzcto setup to reinstall")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

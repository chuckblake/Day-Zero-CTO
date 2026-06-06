#!/usr/bin/env python3
"""Install editable Day Zero CTO skills into Codex's local skills directory."""

from __future__ import annotations

import argparse
import os
from pathlib import Path

from dzcto_progress import Progress


REPO_ROOT = Path(__file__).resolve().parents[1]
SKILLS_DIR = REPO_ROOT / "skills"
DEFAULT_DEST_DIR = Path.home() / ".codex" / "skills"


def resolved_symlink(path: Path) -> Path:
    return (path.parent / os.readlink(path)).resolve()


def skill_sources() -> list[Path]:
    return sorted(source for source in SKILLS_DIR.iterdir() if source.is_dir() and (source / "SKILL.md").exists())


def stale_links(dest_dir: Path) -> list[Path]:
    if not dest_dir.exists():
        return []
    links = []
    for destination in sorted(dest_dir.iterdir()):
        if not destination.is_symlink():
            continue
        current_target = resolved_symlink(destination)
        if not str(current_target).startswith(str(SKILLS_DIR) + os.sep):
            continue
        if (current_target / "SKILL.md").exists():
            continue
        links.append(destination)
    return links


def main() -> int:
    parser = argparse.ArgumentParser(description="Install editable Day Zero CTO skills into a local skills directory")
    parser.add_argument("--dest-dir", default=str(DEFAULT_DEST_DIR), help="Destination skills directory")
    args = parser.parse_args()
    dest_dir = Path(args.dest_dir).expanduser().resolve()

    if not SKILLS_DIR.is_dir():
        raise SystemExit(f"Missing skills directory: {SKILLS_DIR}")

    sources = skill_sources()
    stale = stale_links(dest_dir)
    progress = Progress(5 + len(stale) + len(sources))
    progress.step("Verify install target", "Codex Desktop editable local skills only")
    progress.note("For Claude Code, use the plugin marketplace or launch with claude --plugin-dir; do not use this script.")
    progress.step("Verify skills source", str(SKILLS_DIR))
    progress.note(f"Found {len(sources)} skill folders")
    progress.step("Ensure Codex skills destination", str(dest_dir))
    dest_dir.mkdir(parents=True, exist_ok=True)

    progress.step("Remove stale editable skill links", f"{len(stale)} stale links")
    for destination in stale:
        progress.step("Remove stale link", destination.name)
        destination.unlink()
        progress.note(f"Removed {destination}")

    for source in sources:
        destination = dest_dir / source.name
        progress.step("Link editable skill", source.name)
        if destination.is_symlink():
            current_target = resolved_symlink(destination)
            if current_target == source:
                progress.note("Already linked")
                continue
            destination.unlink()
        elif destination.exists():
            raise SystemExit(f"{destination} already exists and is not a symlink. Move it aside, then rerun this script.")

        destination.symlink_to(source)
        progress.note(f"Linked {destination} -> {source}")

    progress.step("Next step", "Restart Codex Desktop or start a fresh session")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

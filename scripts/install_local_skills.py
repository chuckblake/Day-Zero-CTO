#!/usr/bin/env python3
"""Install editable Day Zero CTO skills into Codex's local skills directory."""

from __future__ import annotations

import os
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
SKILLS_DIR = REPO_ROOT / "skills"
DEST_DIR = Path.home() / ".codex" / "skills"


def resolved_symlink(path: Path) -> Path:
    return (path.parent / os.readlink(path)).resolve()


def main() -> int:
    if not SKILLS_DIR.is_dir():
        raise SystemExit(f"Missing skills directory: {SKILLS_DIR}")

    DEST_DIR.mkdir(parents=True, exist_ok=True)

    for destination in sorted(DEST_DIR.iterdir()):
        if not destination.is_symlink():
            continue
        current_target = resolved_symlink(destination)
        if not str(current_target).startswith(str(SKILLS_DIR) + os.sep):
            continue
        if (current_target / "SKILL.md").exists():
            continue
        destination.unlink()
        print(f"Removed stale {destination.name}")

    for source in sorted(SKILLS_DIR.iterdir()):
        if not source.is_dir() or not (source / "SKILL.md").exists():
            continue

        destination = DEST_DIR / source.name
        if destination.is_symlink():
            current_target = resolved_symlink(destination)
            if current_target == source:
                print(f"Already linked {source.name}")
                continue
            destination.unlink()
        elif destination.exists():
            raise SystemExit(f"{destination} already exists and is not a symlink. Move it aside, then rerun this script.")

        destination.symlink_to(source)
        print(f"Linked {source.name}")

    print(f"Installed editable Day Zero CTO skills into {DEST_DIR}.")
    print("Restart Codex Desktop or start a fresh session to reload skill metadata.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

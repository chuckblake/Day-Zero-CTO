#!/usr/bin/env python3
"""Install Day Zero CTO into the local Codex Desktop plugin marketplace."""

from __future__ import annotations

import json
import os
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
PLUGIN_NAME = "day-zero-cto"
PLUGIN_LINK = Path.home() / "plugins" / PLUGIN_NAME
MARKETPLACE_PATH = Path.home() / ".agents" / "plugins" / "marketplace.json"


def read_marketplace() -> dict:
    if MARKETPLACE_PATH.exists():
        try:
            payload = json.loads(MARKETPLACE_PATH.read_text(encoding="utf-8"))
            return payload if isinstance(payload, dict) else {}
        except json.JSONDecodeError:
            return {}
    return {
        "name": "personal",
        "interface": {
            "displayName": "Personal",
        },
        "plugins": [],
    }


def write_marketplace_entry() -> None:
    MARKETPLACE_PATH.parent.mkdir(parents=True, exist_ok=True)
    payload = read_marketplace()
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
            break
    else:
        payload["plugins"].append(entry)

    MARKETPLACE_PATH.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def link_plugin() -> None:
    PLUGIN_LINK.parent.mkdir(parents=True, exist_ok=True)

    if PLUGIN_LINK.is_symlink():
        current_target = (PLUGIN_LINK.parent / os.readlink(PLUGIN_LINK)).resolve()
        if current_target != REPO_ROOT:
            PLUGIN_LINK.unlink()
            PLUGIN_LINK.symlink_to(REPO_ROOT)
    elif PLUGIN_LINK.exists():
        raise SystemExit(f"{PLUGIN_LINK} already exists and is not a symlink. Move it aside, then rerun this script.")
    else:
        PLUGIN_LINK.symlink_to(REPO_ROOT)


def main() -> int:
    link_plugin()
    write_marketplace_entry()
    print(f"Installed {PLUGIN_NAME} for Codex Desktop.")
    print(f"Plugin link: {PLUGIN_LINK} -> {REPO_ROOT}")
    print(f"Marketplace: {MARKETPLACE_PATH}")
    print("Restart Codex Desktop to pick it up.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

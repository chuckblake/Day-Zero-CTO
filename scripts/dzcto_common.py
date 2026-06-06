"""Shared Day Zero CTO helper functions."""

from __future__ import annotations

import datetime as dt
import hashlib
import html
import json
import platform
import re
import sys
from pathlib import Path
from typing import Any


TOOL_NAME = "day-zero-cto"
TOOL_VERSION = "0.6.4"
SCHEMA_VERSION = "1.0"
SIDECAR_DIR_NAME = ".dzcto"


def utc_now() -> str:
    return dt.datetime.now(dt.UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def project_folder_from_wiki(wiki_root: Path) -> Path:
    return (wiki_root / ".." / "..").resolve()


def wiki_root_for_project(project: Path) -> Path:
    return project.expanduser().resolve() / "knowledge" / "wiki"


def sidecar_dir(wiki_root: Path) -> Path:
    return wiki_root / SIDECAR_DIR_NAME


def logs_dir(wiki_root: Path) -> Path:
    return sidecar_dir(wiki_root) / "logs"


def read_json(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return default


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def sha256_text(value: str) -> str:
    return "sha256:" + hashlib.sha256(value.encode("utf-8")).hexdigest()


def sha256_file(path: Path) -> str | None:
    if not path.exists() or not path.is_file():
        return None
    digest = hashlib.sha256()
    with path.open("rb") as file:
        for chunk in iter(lambda: file.read(1024 * 1024), b""):
            digest.update(chunk)
    return "sha256:" + digest.hexdigest()


def stable_json_hash(payload: Any) -> str:
    return sha256_text(json.dumps(payload, sort_keys=True, separators=(",", ":")))


def path_hash(path: Path) -> str:
    return sha256_text(str(path.expanduser().resolve()))


def log_event(wiki_root: Path, message: str) -> None:
    logs_dir(wiki_root).mkdir(parents=True, exist_ok=True)
    line = f"{utc_now()} {message}\n"
    (logs_dir(wiki_root) / "latest.log").write_text(line, encoding="utf-8")


def ensure_sidecar(wiki_root: Path, project_folder: Path | None = None, reason: str = "update") -> dict[str, Any]:
    project_folder = project_folder.expanduser().resolve() if project_folder else project_folder_from_wiki(wiki_root)
    sidecar = sidecar_dir(wiki_root)
    sidecar.mkdir(parents=True, exist_ok=True)
    logs_dir(wiki_root).mkdir(parents=True, exist_ok=True)

    now = utc_now()
    config_path = sidecar / "config.json"
    config = read_json(config_path, {})
    config.setdefault("tool", TOOL_NAME)
    config.setdefault("schemaVersion", SCHEMA_VERSION)
    config.setdefault("createdAt", now)
    config.update(
        {
            "toolVersion": TOOL_VERSION,
            "updatedAt": now,
            "projectFolder": str(project_folder),
            "wikiRoot": str(wiki_root.expanduser().resolve()),
            "artifactDirectory": str(wiki_root.expanduser().resolve()),
        }
    )
    write_json(config_path, config)

    manifest_path = sidecar / "manifest.json"
    manifest = read_json(manifest_path, {})
    manifest.setdefault("tool", TOOL_NAME)
    manifest.setdefault("schemaVersion", SCHEMA_VERSION)
    manifest.setdefault("artifacts", [])
    manifest.update({"toolVersion": TOOL_VERSION, "updatedAt": now})
    write_json(manifest_path, manifest)

    diagnostics_path = sidecar / "diagnostics.json"
    diagnostics = read_json(diagnostics_path, {})
    diagnostics.update(
        {
            "tool": TOOL_NAME,
            "toolVersion": TOOL_VERSION,
            "schemaVersion": SCHEMA_VERSION,
            "lastRunAt": now,
            "lastRunReason": reason,
            "pythonVersion": platform.python_version(),
            "platform": platform.platform(),
        }
    )
    write_json(diagnostics_path, diagnostics)
    log_event(wiki_root, f"{reason} tool={TOOL_NAME} version={TOOL_VERSION}")
    return config


def config_hash(wiki_root: Path) -> str:
    config = read_json(sidecar_dir(wiki_root) / "config.json", {})
    return stable_json_hash(config)


def provenance_payload(
    wiki_root: Path,
    *,
    artifact_id: str,
    artifact_kind: str,
    relative_path: str,
    title: str | None = None,
    generated_at: str | None = None,
    source_hashes: dict[str, str] | None = None,
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "tool": TOOL_NAME,
        "toolVersion": TOOL_VERSION,
        "schemaVersion": SCHEMA_VERSION,
        "generatedAt": generated_at or utc_now(),
        "artifactId": artifact_id,
        "artifactKind": artifact_kind,
        "relativePath": relative_path,
        "configHash": config_hash(wiki_root),
        "projectHash": path_hash(project_folder_from_wiki(wiki_root)),
        "sourceHashes": source_hashes or {},
    }
    if title:
        payload["title"] = title
    if extra:
        payload.update(extra)
    return payload


def provenance_block(payload: dict[str, Any]) -> str:
    raw = json.dumps(payload, indent=2, sort_keys=True).replace("</", "<\\/")
    return f'<script type="application/json" id="dzcto-provenance">\n{html.escape(raw, quote=False)}\n</script>'


def update_manifest(wiki_root: Path, artifact: dict[str, Any]) -> None:
    manifest_path = sidecar_dir(wiki_root) / "manifest.json"
    manifest = read_json(manifest_path, {})
    manifest.setdefault("tool", TOOL_NAME)
    manifest.setdefault("schemaVersion", SCHEMA_VERSION)
    manifest.setdefault("artifacts", [])
    manifest.update({"toolVersion": TOOL_VERSION, "updatedAt": utc_now()})
    artifacts = [item for item in manifest["artifacts"] if item.get("relativePath") != artifact.get("relativePath")]
    artifacts.append(artifact)
    manifest["artifacts"] = sorted(artifacts, key=lambda item: str(item.get("relativePath", "")))
    write_json(manifest_path, manifest)


def source_hashes(paths: list[Path]) -> dict[str, str]:
    hashes: dict[str, str] = {}
    for index, path in enumerate(paths, start=1):
        digest = sha256_file(path.expanduser())
        if digest:
            hashes[f"source-{index}:{path.name}"] = digest
    return hashes


SECRET_KEY_PATTERN = re.compile(r"(token|secret|password|api[_-]?key|credential|authorization)", re.I)
SECRET_VALUE_PATTERN = re.compile(r"(?i)(token|secret|password|api[_-]?key|authorization)(['\"\s:=]+)([^'\"\s,}]+)")
LOCAL_PATH_PATTERN = re.compile(r"(?<![\w.-])/(Users|home|private/tmp|tmp)/[^'\"\s,}]+")
LOCAL_PATH_KEYS = {"projectFolder", "wikiRoot", "artifactDirectory"}


def redact(value: Any) -> Any:
    if isinstance(value, dict):
        redacted: dict[str, Any] = {}
        for key, item in value.items():
            if str(key) in LOCAL_PATH_KEYS:
                redacted[key] = "<redacted path>"
            elif SECRET_KEY_PATTERN.search(str(key)):
                redacted[key] = "<redacted>"
            else:
                redacted[key] = redact(item)
        return redacted
    if isinstance(value, list):
        return [redact(item) for item in value]
    if isinstance(value, str):
        without_secrets = SECRET_VALUE_PATTERN.sub(r"\1\2<redacted>", value)
        return LOCAL_PATH_PATTERN.sub("<redacted path>", without_secrets)
    return value


def redacted_json_text(payload: Any) -> str:
    return json.dumps(redact(payload), indent=2, sort_keys=True) + "\n"


def repo_root() -> Path:
    return Path(__file__).resolve().parents[1]

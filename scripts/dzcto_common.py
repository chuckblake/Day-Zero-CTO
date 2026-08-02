"""Shared Day Zero CTO helper functions."""

from __future__ import annotations

import datetime as dt
import hashlib
import html
import json
import math
import platform
import re
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Any


TOOL_NAME = "day-zero-cto"
TOOL_VERSION = "0.9.4"
SCHEMA_VERSION = "1.0"
SIDECAR_DIR_NAME = ".dzcto"
GLOBAL_CONFIG_DIR = Path.home() / ".dzcto"
GLOBAL_CONFIG_FILE = GLOBAL_CONFIG_DIR / "config.json"


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


def read_global_config() -> dict[str, Any]:
    value = read_json(GLOBAL_CONFIG_FILE, {})
    return value if isinstance(value, dict) else {}


def write_global_config(payload: dict[str, Any]) -> None:
    write_json(GLOBAL_CONFIG_FILE, payload)


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


HIGH_CONFIDENCE = "high"
LOW_CONFIDENCE = "low"
REDACTION_PLACEHOLDER_TEMPLATE = "[REDACTED:{rule}]"


@dataclass(frozen=True)
class SecretFinding:
    rule: str
    confidence: str
    span: tuple[int, int]
    preview: str


@dataclass(frozen=True)
class SecretRule:
    name: str
    regex: re.Pattern[str]


PROVIDER_RULES = (
    SecretRule("github_pat", re.compile(r"(?<![\w-])(?:gh[pousr]_[A-Za-z0-9_]{12,}|github_pat_[A-Za-z0-9_]{20,})(?![\w-])")),
    SecretRule("aws_access_key", re.compile(r"(?<![\w-])(?:AKIA|ASIA)[A-Z0-9]{16}(?![\w-])")),
    SecretRule("openai_key", re.compile(r"(?<![\w-])sk-(?:proj-)?[A-Za-z0-9_-]{16,}(?![\w-])")),
    SecretRule("slack_token", re.compile(r"(?<![\w-])xox[baprs]-[A-Za-z0-9-]{10,}(?![\w-])")),
    SecretRule("google_api_key", re.compile(r"(?<![\w-])AIza[0-9A-Za-z_-]{20,40}(?![\w-])")),
    SecretRule("stripe_key", re.compile(r"(?<![\w-])(?:sk_live|rk_live)_[0-9A-Za-z]{16,}(?![\w-])")),
    SecretRule("sendgrid_key", re.compile(r"(?<![\w-])SG\.[A-Za-z0-9_-]{16,}\.[A-Za-z0-9_-]{16,}(?![\w-])")),
    SecretRule("pem_private_key", re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----[\s\S]*?(?:-----END [A-Z ]*PRIVATE KEY-----|$)")),
    SecretRule("jwt", re.compile(r"(?<![\w-])eyJ[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}(?![\w-])")),
)

ASSIGNMENT_RULE = re.compile(
    r"""
    (?P<key>\b(?:api[_-]?key|access[_-]?key|client[_-]?secret|private[_-]?key|token|secret|password|authorization|credential)\b)
    \s*[:=]\s*
    (?:
      (?P<quote>["'])(?P<quoted>[^"']+)(?P=quote)
      |
      (?P<bare>[^'"\s,}<]+)
    )
    """,
    re.I | re.X,
)
BENIGN_SHA_PATTERN = re.compile(r"^[0-9a-f]{7,64}$")
BENIGN_UUID_PATTERN = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$",
    re.I,
)
REDACTION_PLACEHOLDER_PATTERN = re.compile(r"^\[REDACTED:[A-Za-z0-9_-]+\]$")
LOCAL_PATH_PATTERN = re.compile(r"(?<![\w.-])/(Users|home|private/tmp|tmp)/[^'\"\s,}]+")
LOCAL_PATH_KEYS = {"projectFolder", "wikiRoot", "artifactDirectory"}
SECRET_KEY_EXACT = {
    "api-key",
    "api_key",
    "apikey",
    "authorization",
    "client-secret",
    "client_secret",
    "credential",
    "github-token",
    "github_token",
    "openai-api-key",
    "openai_api_key",
    "password",
    "private-key",
    "private_key",
    "secret",
    "token",
}
SECRET_KEY_SUFFIXES = (
    "_token",
    "-token",
    "_secret",
    "-secret",
    "_api_key",
    "-api-key",
    "_apikey",
    "-apikey",
    "_password",
    "-password",
    "_credential",
    "-credential",
)
SECRET_KEY_PREFIXES = (
    "authorization_",
    "authorization-",
    "credential_",
    "credential-",
    "password_",
    "password-",
    "secret_",
    "secret-",
)


def redaction_placeholder(rule: str) -> str:
    safe_rule = re.sub(r"[^A-Za-z0-9_-]+", "_", rule).strip("_") or "secret"
    return REDACTION_PLACEHOLDER_TEMPLATE.format(rule=safe_rule)


def masked_preview(value: str) -> str:
    return f"<masked len={len(value)}>"


def shannon_entropy(value: str) -> float:
    if not value:
        return 0.0
    counts = Counter(value)
    length = len(value)
    return -sum((count / length) * math.log2(count / length) for count in counts.values())


def is_benign_secret_shape(value: str) -> bool:
    stripped = value.strip()
    return (
        not stripped
        or REDACTION_PLACEHOLDER_PATTERN.match(stripped) is not None
        or stripped.startswith("data:")
        or BENIGN_SHA_PATTERN.match(stripped) is not None
        or BENIGN_UUID_PATTERN.match(stripped) is not None
    )


def assignment_value_is_secret(value: str) -> bool:
    stripped = value.strip()
    if is_benign_secret_shape(stripped):
        return False
    is_hex = re.fullmatch(r"[0-9A-Fa-f]+", stripped) is not None
    if len(stripped) < (16 if is_hex else 20):
        return False
    if re.fullmatch(r"[A-Za-z0-9_./+=:-]+", stripped) is None:
        return False
    return shannon_entropy(stripped) >= 3.0


def is_secret_key(key: str) -> bool:
    normalized = re.sub(r"\s+", "_", key.strip().lower())
    return (
        normalized in SECRET_KEY_EXACT
        or normalized.endswith(SECRET_KEY_SUFFIXES)
        or normalized.startswith(SECRET_KEY_PREFIXES)
    )


def _selected_findings(findings: list[SecretFinding]) -> list[SecretFinding]:
    priority = {HIGH_CONFIDENCE: 0, LOW_CONFIDENCE: 1}
    selected: list[SecretFinding] = []
    for finding in sorted(findings, key=lambda item: (priority.get(item.confidence, 9), item.span[0], -(item.span[1] - item.span[0]))):
        start, end = finding.span
        if any(start < existing.span[1] and existing.span[0] < end for existing in selected):
            continue
        selected.append(finding)
    return sorted(selected, key=lambda item: item.span)


def scan_secrets(text: str) -> list[SecretFinding]:
    if not text:
        return []
    findings: list[SecretFinding] = []
    for rule in PROVIDER_RULES:
        for match in rule.regex.finditer(text):
            findings.append(
                SecretFinding(
                    rule=rule.name,
                    confidence=HIGH_CONFIDENCE,
                    span=match.span(),
                    preview=masked_preview(match.group(0)),
                )
            )
    for match in ASSIGNMENT_RULE.finditer(text):
        value_group = "quoted" if match.group("quoted") is not None else "bare"
        value = match.group(value_group)
        if assignment_value_is_secret(value):
            findings.append(
                SecretFinding(
                    rule="generic_assignment",
                    confidence=LOW_CONFIDENCE,
                    span=match.span(value_group),
                    preview=masked_preview(value),
                )
            )
    return _selected_findings(findings)


def redact_text(value: str) -> tuple[str, list[SecretFinding]]:
    findings = scan_secrets(value)
    for match in LOCAL_PATH_PATTERN.finditer(value):
        findings.append(
            SecretFinding(
                rule="local_path",
                confidence=LOW_CONFIDENCE,
                span=match.span(),
                preview=masked_preview(match.group(0)),
            )
        )
    findings = _selected_findings(findings)
    redacted = value
    for finding in reversed(findings):
        start, end = finding.span
        redacted = f"{redacted[:start]}{redaction_placeholder(finding.rule)}{redacted[end:]}"
    return redacted, findings


def repo_root() -> Path:
    return Path(__file__).resolve().parents[1]

#!/usr/bin/env python3
"""Generate Day Zero CTO wiki indexes and report artifacts."""

from __future__ import annotations

import argparse
import datetime as dt
import html
import json
import math
import os
import re
import shlex
import sys
import urllib.error
import urllib.request
import webbrowser
from pathlib import Path
from typing import Any

from dzcto_common import (
    HIGH_CONFIDENCE,
    LOCAL_PATH_KEYS,
    LOW_CONFIDENCE,
    TOOL_VERSION,
    SecretFinding,
    ensure_sidecar,
    is_secret_key,
    provenance_block,
    provenance_payload,
    read_global_config,
    read_json,
    redact_text,
    redaction_placeholder,
    sidecar_dir,
    source_hashes as collect_source_hashes,
    update_manifest,
    utc_now,
    write_global_config,
    write_json,
)


REPORT_FOLDERS = {
    "snapshot": "Snapshot",
    "tech-stack": "Tech Stack",
    "engineering-risk": "Engineering Risk",
    "codebase-accountability": "Codebase Accountability",
    "weekly-reviews": "Weekly Reviews",
    "ceo-updates": "CEO Reports",
}

ACTIVE_REPORT_FOLDERS = {
    "ceo-updates": "CEO Reports",
}

UNKNOWN_VALUES = {"", "unknown", "tbd", "to be determined", "n/a", "none"}


def esc(value: Any) -> str:
    return html.escape("" if value is None else str(value), quote=True)


def slugify(value: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
    return slug or "artifact"


def pluralize(count: int, singular: str, plural: str | None = None) -> str:
    return f"{count} {singular if count == 1 else (plural or singular + 's')}"


def markdown_section(path: Path, heading: str) -> str | None:
    if not path.exists():
        return None

    lines = path.read_text(encoding="utf-8").splitlines()
    start = None
    pattern = re.compile(rf"^##+\s+{re.escape(heading)}\s*$", re.I)
    for index, line in enumerate(lines):
        if pattern.match(line):
            start = index + 1
            break

    if start is None:
        return None

    section: list[str] = []
    for line in lines[start:]:
        if re.match(r"^##+\s+\S", line):
            break
        section.append(line)
    text = "\n".join(section).strip()
    return text or None


def first_markdown_paragraph(text: str | None) -> str | None:
    if not text:
        return None

    for paragraph in re.split(r"\n{2,}", text):
        value = paragraph.strip()
        if value and not value.startswith(("|", "-", "1.")):
            return value
    return None


def plain_markdown(value: str | None) -> str:
    text = value or ""
    text = re.sub(r"`([^`]+)`", r"\1", text)
    text = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", text)
    text = re.sub(r"\*\*|__", "", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def plain_html(value: str | None) -> str:
    text = value or ""
    text = re.sub(r"<script\b[^>]*>.*?</script>", " ", text, flags=re.I | re.S)
    text = re.sub(r"<style\b[^>]*>.*?</style>", " ", text, flags=re.I | re.S)
    text = re.sub(r'<header\b[^>]*class=["\'][^"\']*sticky-nav[^"\']*["\'][^>]*>.*?</header>', " ", text, flags=re.I | re.S)
    text = re.sub(r'<header\b[^>]*class=["\'][^"\']*masthead[^"\']*["\'][^>]*>.*?</header>', " ", text, flags=re.I | re.S)
    text = re.sub(r'<aside\b[^>]*class=["\'][^"\']*shell-sidebar[^"\']*["\'][^>]*>.*?</aside>', " ", text, flags=re.I | re.S)
    text = re.sub(r'<div\b[^>]*class=["\'][^"\']*search[^"\']*["\'][^>]*>.*?</div>', " ", text, flags=re.I | re.S)
    text = re.sub(r'<nav\b[^>]*class=["\'][^"\']*(?:breadcrumbs|toc)[^"\']*["\'][^>]*>.*?</nav>', " ", text, flags=re.I | re.S)
    text = re.sub(r"<[^>]+>", " ", text)
    text = html.unescape(text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def snippet(value: str | None, limit: int = 180) -> str:
    text = plain_markdown(value) if value else ""
    if len(text) <= limit:
        return text
    return text[: limit - 1].rsplit(" ", 1)[0].rstrip() + "..."


def display_timestamp(value: str) -> str:
    return (value or "").replace("T", " ").replace("Z", " UTC")


def project_config(wiki_root: Path) -> dict[str, Any]:
    value = read_json(sidecar_dir(wiki_root) / "config.json", {})
    return value if isinstance(value, dict) else {}


def company_name(strategy_path: Path, project_folder: Path, config: dict[str, Any] | None = None) -> str:
    if config and str(config.get("companyName") or "").strip():
        return str(config["companyName"]).strip()
    if strategy_path.exists():
        for line in strategy_path.read_text(encoding="utf-8").splitlines():
            if line.startswith("# "):
                title = re.sub(r"\s+Strategy$", "", line[2:].strip(), flags=re.I)
                return title
    return project_folder.name


def company_description(strategy_path: Path, config: dict[str, Any] | None = None) -> str:
    configured = str((config or {}).get("companyDescription") or "").strip()
    if configured:
        return plain_markdown(configured)
    paragraph = (
        first_markdown_paragraph(markdown_section(strategy_path, "Product Thesis"))
        or first_markdown_paragraph(markdown_section(strategy_path, "Company"))
        or first_markdown_paragraph(markdown_section(strategy_path, "Stage"))
    )
    if paragraph and plain_markdown(paragraph).lower() in {"unknown", "tbd", "to be determined"}:
        paragraph = None
    fallback = "Company context has not been captured yet. Run /dzcto-init with a one-sentence company summary to enrich this report index."
    return plain_markdown(paragraph or fallback)


def dashboard_title(company: str) -> str:
    return f"{company} Day Zero CTO"


def has_real_value(value: Any) -> bool:
    if value is None:
        return False
    return str(value).strip().lower() not in UNKNOWN_VALUES


def has_captured_company_description(strategy_path: Path, config: dict[str, Any] | None = None) -> bool:
    if has_real_value((config or {}).get("companyDescription")):
        return True
    paragraph = (
        first_markdown_paragraph(markdown_section(strategy_path, "Product Thesis"))
        or first_markdown_paragraph(markdown_section(strategy_path, "Company"))
        or first_markdown_paragraph(markdown_section(strategy_path, "Stage"))
    )
    return has_real_value(plain_markdown(paragraph))


def fetch_company_description(url: str) -> str | None:
    if not url:
        return None
    try:
        request = urllib.request.Request(url, headers={"User-Agent": "DayZeroCTO/0.6"})
        with urllib.request.urlopen(request, timeout=8) as response:
            content_type = response.headers.get("content-type", "")
            if "text/html" not in content_type:
                return None
            html_text = response.read(250_000).decode("utf-8", errors="replace")
    except (urllib.error.URLError, TimeoutError, ValueError):
        return None

    meta = re.search(r'<meta\s+[^>]*(?:name|property)=["\'](?:description|og:description)["\'][^>]*content=["\']([^"\']+)["\']', html_text, re.I)
    if meta:
        return plain_markdown(html.unescape(meta.group(1)))
    title = re.search(r"<title[^>]*>(.*?)</title>", html_text, re.I | re.S)
    return plain_markdown(html.unescape(title.group(1))) if title else None


def apply_init_metadata(
    wiki_root: Path,
    project_folder: Path,
    *,
    company_name_value: str | None = None,
    company_description_value: str | None = None,
    company_url: str | None = None,
    report_prompt_context: str | None = None,
    weekly_range: str | None = None,
    weekly_start_day: str | None = None,
    weekly_end_day: str | None = None,
    weekly_lookback_days: int | None = None,
    ceo_report_tone: str | None = None,
    profile_name: str | None = None,
    repos: list[str] | None = None,
) -> None:
    if not any(
        [
            company_name_value,
            company_description_value,
            company_url,
            report_prompt_context,
            weekly_range,
            weekly_start_day,
            weekly_end_day,
            weekly_lookback_days,
            ceo_report_tone,
            profile_name,
            repos,
        ]
    ):
        return

    config_path = sidecar_dir(wiki_root) / "config.json"
    config = project_config(wiki_root)
    if company_name_value:
        config["companyName"] = company_name_value.strip()
    if company_url:
        config["companyUrl"] = company_url.strip()
    description = (company_description_value or "").strip()
    if company_url and not description:
        description = fetch_company_description(company_url) or ""
    if description:
        config["companyDescription"] = description
    if report_prompt_context and report_prompt_context.strip():
        config["reportPromptContext"] = report_prompt_context.strip()
    if ceo_report_tone and ceo_report_tone.strip():
        config["ceoReportTone"] = ceo_report_tone.strip()
    if profile_name and profile_name.strip():
        config["profile"] = profile_slug(profile_name)
        config["profileName"] = profile_slug(profile_name)
    weekly_defaults = config.get("weeklyReportDefaults")
    if not isinstance(weekly_defaults, dict):
        weekly_defaults = {}
    if weekly_range and weekly_range.strip():
        weekly_defaults["range"] = weekly_range.strip()
    if weekly_start_day and weekly_start_day.strip():
        weekly_defaults["startDay"] = weekly_start_day.strip()
    if weekly_end_day and weekly_end_day.strip():
        weekly_defaults["endDay"] = weekly_end_day.strip()
    if weekly_lookback_days is not None:
        weekly_defaults["lookbackDays"] = weekly_lookback_days
    if weekly_defaults:
        config["weeklyReportDefaults"] = weekly_defaults
    if repos:
        existing = [str(item) for item in config.get("codeRepos", []) if str(item).strip()]
        for repo in repos:
            value = str(Path(repo).expanduser()).strip()
            if value and value not in existing:
                existing.append(value)
        config["codeRepos"] = existing
    write_json(config_path, config)


def default_artifacts_dir_from_global() -> Path | None:
    profile = profile_from_global()
    for key in ("artifactsDir", "artifactDirectory", "defaultArtifactsDir", "wikiRoot"):
        value = str(profile.get(key) or "").strip()
        if value:
            return Path(value).expanduser().resolve()
    return None


def profile_slug(value: str | None, fallback: str = "default") -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", str(value or "").lower()).strip("-")
    return slug or fallback


def profile_name_for_config(config: dict[str, Any], wiki_root: Path, explicit_profile: str | None = None) -> str:
    if explicit_profile and explicit_profile.strip():
        return profile_slug(explicit_profile)
    for key in ("profile", "profileName", "companyName"):
        value = str(config.get(key) or "").strip()
        if value:
            return profile_slug(value)
    return profile_slug(wiki_root.name)


def legacy_global_profile(config: dict[str, Any]) -> dict[str, Any]:
    profile: dict[str, Any] = {}
    key_map = {
        "defaultArtifactsDir": "artifactsDir",
        "artifactsDir": "artifactsDir",
        "artifactDirectory": "artifactDirectory",
        "wikiRoot": "wikiRoot",
        "projectFolder": "projectFolder",
        "companyName": "companyName",
        "companyDescription": "companyDescription",
        "companyUrl": "companyUrl",
        "weeklyReportDefaults": "weeklyReportDefaults",
        "ceoReportTone": "ceoReportTone",
        "reportPromptContext": "reportPromptContext",
        "codeRepos": "codeRepos",
    }
    for source, destination in key_map.items():
        value = config.get(source)
        if value:
            profile[destination] = value
    return profile


def profiles_from_global(config: dict[str, Any] | None = None) -> dict[str, dict[str, Any]]:
    config = config or read_global_config()
    raw_profiles = config.get("profiles")
    profiles: dict[str, dict[str, Any]] = {}
    if isinstance(raw_profiles, dict):
        for name, value in raw_profiles.items():
            if isinstance(value, dict):
                profiles[profile_slug(str(name))] = value
    if not profiles:
        legacy = legacy_global_profile(config)
        if legacy:
            profiles[profile_slug(str(config.get("defaultProfile") or config.get("companyName") or "default"))] = legacy
    return profiles


def profile_from_global(profile_name: str | None = None) -> dict[str, Any]:
    config = read_global_config()
    profiles = profiles_from_global(config)
    if not profiles:
        return {}
    if profile_name and profile_name.strip():
        return profiles.get(profile_slug(profile_name), {})
    name = profile_slug(str(config.get("defaultProfile") or ""))
    if name in profiles:
        return profiles[name]
    return profiles.get(profile_slug(str(config.get("defaultProfile") or "")), {}) or next(iter(profiles.values()))


def default_artifacts_dir_for_profile(profile_name: str | None = None) -> Path | None:
    profile = profile_from_global(profile_name)
    for key in ("artifactsDir", "artifactDirectory", "defaultArtifactsDir", "wikiRoot"):
        value = str(profile.get(key) or "").strip()
        if value:
            return Path(value).expanduser().resolve()
    return None


def save_global_preferences(wiki_root: Path, project_folder: Path, profile_name: str | None = None, *, set_default: bool = True) -> str:
    config = project_config(wiki_root)
    profile_name = profile_name_for_config(config, wiki_root, profile_name)
    config["profile"] = profile_name
    config["profileName"] = profile_name
    write_json(sidecar_dir(wiki_root) / "config.json", config)
    global_config = read_global_config()
    profiles = profiles_from_global(global_config)
    profile = dict(profiles.get(profile_name, {}))
    profile.update(
        {
            "artifactsDir": str(wiki_root.expanduser().resolve()),
            "artifactDirectory": str(wiki_root.expanduser().resolve()),
            "projectFolder": str(project_folder.expanduser().resolve()),
        }
    )
    profile["profile"] = profile_name
    profile["profileName"] = profile_name
    profile["updatedAt"] = utc_now()
    profile["toolVersion"] = TOOL_VERSION
    for key in (
        "companyName",
        "companyDescription",
        "companyUrl",
        "weeklyReportDefaults",
        "ceoReportTone",
        "reportPromptContext",
        "codeRepos",
    ):
        value = config.get(key)
        if value:
            profile[key] = value
    profiles[profile_name] = profile
    global_config.update(
        {
            "tool": "day-zero-cto",
            "toolVersion": TOOL_VERSION,
            "schemaVersion": "1.0",
            "updatedAt": utc_now(),
            "profiles": profiles,
        }
    )
    if set_default or not str(global_config.get("defaultProfile") or "").strip():
        global_config["defaultProfile"] = profile_name
        global_config["defaultArtifactsDir"] = profile["artifactsDir"]
    write_global_config(global_config)
    return profile_name


def split_markdown_row(row: str) -> list[str]:
    return [cell.strip() for cell in row.strip().strip("|").split("|")]


def cadence_days(value: str | None) -> int | None:
    cadence = (value or "").lower()
    if match := re.search(r"every\s+(\d+)\s+days?", cadence):
        return int(match.group(1))
    if match := re.search(r"every\s+(\d+)\s+weeks?", cadence):
        return int(match.group(1)) * 7
    if match := re.search(r"every\s+(\d+)\s+months?", cadence):
        return int(match.group(1)) * 30
    if re.search(r"daily|once per day", cadence):
        return 1
    if re.search(r"weekly|once per week|every week", cadence):
        return 7
    if re.search(r"biweekly|every other week|fortnight", cadence):
        return 14
    if re.search(r"monthly|once per month|every month", cadence):
        return 30
    if re.search(r"quarterly|once per quarter|every quarter", cadence):
        return 90
    return None


def normalize_report_folder(value: str | None) -> str:
    folder = (value or "").strip().strip("/")
    if folder.startswith("reports/"):
        folder = folder.removeprefix("reports/")
    return folder


def parse_cadence_rules(cadence_path: Path) -> list[dict[str, Any]]:
    if not cadence_path.exists():
        return []

    lines = cadence_path.read_text(encoding="utf-8").splitlines()
    start = None
    for index, line in enumerate(lines):
        if re.match(r"^##+\s+Index Cadence Rules\s*$", line, re.I):
            start = index + 1
            break
    if start is None:
        return []

    section: list[str] = []
    for line in lines[start:]:
        if re.match(r"^##+\s+\S", line):
            break
        section.append(line)

    table_lines = [line for line in section if line.strip().startswith("|")]
    if len(table_lines) < 3:
        return []

    headers = [
        re.sub(r"(^_+|_+$)", "", re.sub(r"[^a-z0-9]+", "_", header.lower()))
        for header in split_markdown_row(table_lines[0])
    ]
    rules: list[dict[str, Any]] = []
    for row in table_lines[2:]:
        values = dict(zip(headers, split_markdown_row(row)))
        folder = normalize_report_folder(values.get("folder") or values.get("report_folder") or values.get("kind"))
        cadence = values.get("cadence") or values.get("frequency")
        day = (
            values.get("day")
            or values.get("weekday")
            or values.get("day_of_week")
            or values.get("schedule_day")
            or ""
        )
        command = values.get("command") or values.get("prompt") or values.get("run")
        prompt_context = (
            values.get("prompt_context")
            or values.get("report_prompt_context")
            or values.get("custom_prompt_context")
            or values.get("steering")
            or ""
        )
        label = values.get("report") or values.get("name") or REPORT_FOLDERS.get(str(folder), str(folder or ""))
        try:
            grace_days = int(values.get("grace_days") or values.get("grace") or 0)
        except ValueError:
            grace_days = 0
        interval_days = cadence_days(cadence)
        if folder and cadence and command and interval_days:
            rules.append(
                {
                    "label": label,
                    "folder": folder,
                    "cadence": cadence,
                    "day": str(day).strip(),
                    "command": command,
                    "prompt_context": str(prompt_context).strip(),
                    "grace_days": grace_days,
                    "interval_days": interval_days,
                }
            )
    return rules


def repo_context(repos: list[str]) -> str:
    if not repos:
        return "No read-only code repo is configured; ask for repo access if the work needs code or Git evidence."
    if len(repos) == 1:
        return f"Use read-only code repo `{repos[0]}`."
    repo_list = ", ".join(f"`{repo}`" for repo in repos)
    return f"Use read-only code repos: {repo_list}."


def configured_report_prompt_context(config: dict[str, Any] | None) -> str:
    config = config or {}
    for key in ("reportPromptContext", "promptContext", "customPromptContext"):
        value = config.get(key)
        if isinstance(value, list):
            text = " ".join(str(item).strip() for item in value if str(item).strip())
        else:
            text = str(value or "").strip()
        if text:
            return text
    return ""


def prompt_context(project_folder: Path, repos: list[str], custom_context: str = "") -> str:
    context = f"Use project folder `{project_folder}`. {repo_context(repos)}"
    if custom_context.strip():
        context = f"{context} Additional prompt context: {custom_context.strip()}"
    return context


def exact_prompt(base: str, project_folder: Path, repos: list[str], custom_context: str = "") -> str:
    return f"{base.strip()} {prompt_context(project_folder, repos, custom_context)}".strip()


def search_icon() -> str:
    return '<svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" aria-hidden="true"><circle cx="11" cy="11" r="7"></circle><path d="M21 21l-4.3-4.3"></path></svg>'


def search_control(prefix: str) -> str:
    return f"""
<div class="search">
  {search_icon()}
  <input type="search" placeholder="Search wiki..." data-dzcto-search data-search-index="{esc(prefix)}search-index.json" data-search-prefix="{esc(prefix)}" autocomplete="off">
  <button type="button" class="search-clear" data-dzcto-search-clear aria-label="Clear search">x</button>
  <div class="search-results" data-dzcto-search-results hidden></div>
</div>
"""


def breadcrumbs(prefix: str, items: list[tuple[str, str | None]], *, class_name: str = "breadcrumbs") -> str:
    parts = [f'<a href="{esc(prefix)}index.html">Dashboard</a>']
    for label, href in items:
        if href:
            parts.append(f'<a href="{esc(prefix + href)}">{esc(label)}</a>')
        else:
            parts.append(f"<span>{esc(label)}</span>")
    return f'<nav class="{esc(class_name)}" aria-label="Breadcrumb">{"<span>/</span>".join(parts)}</nav>'


def page_shell(
    content: str,
    *,
    prefix: str = "",
    eyebrow: str = "Command Center - Day Zero CTO",
    title: str = "Knowledge Wiki",
    subtitle: str = "",
    stamp: str = "",
    crumbs: list[tuple[str, str | None]] | None = None,
    sticky_title: str | None = None,
) -> str:
    breadcrumb_html = breadcrumbs(prefix, crumbs) if crumbs else ""
    stable_title = sticky_title or title
    return f"""
<header class="sticky-nav">
  <div class="sticky-main">
    <a class="sticky-home" href="{esc(prefix)}index.html">Dashboard</a>
    <a class="sticky-title" href="{esc(prefix)}index.html">{esc(stable_title)}</a>
  </div>
  <div class="sticky-actions">
    {search_control(prefix)}
    <button type="button" class="theme-btn" data-theme-toggle aria-label="Toggle light or dark theme"><span data-theme-label>Dark</span></button>
  </div>
</header>
<main class="app">
  <header class="masthead">
    <div>
      {breadcrumb_html}
      <a class="masthead-title-link" href="{esc(prefix)}index.html">
        <span class="eyebrow">{esc(eyebrow)}</span>
        <h1 class="title">{esc(title)}</h1>
      </a>
      {f'<p class="masthead-stamp">{esc(stamp)}</p>' if stamp else ''}
      {f'<p class="lede">{esc(subtitle)}</p>' if subtitle else ''}
    </div>
    <div class="masthead-side masthead-mobile-tools">
      {search_control(prefix)}
    </div>
  </header>
    {content}
  <footer class="app-footer">
    <span>Day Zero CTO skills v{esc(TOOL_VERSION)}</span>
  </footer>
</main>
"""


def copy_card(card_id: str, label: str, text: str, kind: str) -> str:
    return f"""<article class="cmd-card">
  <div class="cc-top">
    <div>
      <div class="cc-ttl">{esc(label)}</div>
      <div class="cc-kind">{esc(kind)}</div>
    </div>
    <button type="button" class="copy-btn" data-copy-target="{esc(card_id)}">Copy</button>
  </div>
  <pre id="{esc(card_id)}" class="cmd-pre">{esc(text)}</pre>
  <span class="copy-status" data-copy-status-for="{esc(card_id)}" aria-live="polite"></span>
</article>"""


def present(value: Any) -> bool:
    if value is None:
        return False
    if isinstance(value, str):
        return bool(value.strip())
    if isinstance(value, (list, dict)):
        return bool(value)
    return True


def array_value(value: Any) -> list[Any]:
    if value is None:
        return []
    if isinstance(value, list):
        return [item for item in value if present(item)]
    return [value] if present(value) else []


def value_at(data: dict[str, Any], *keys: str) -> Any:
    for key in keys:
        if key in data and present(data[key]):
            return data[key]
    return None


def text_value(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, list):
        return "; ".join(filter(None, (text_value(item) for item in value)))
    if isinstance(value, dict):
        return "; ".join(f"{key}: {text_value(item)}" for key, item in value.items() if text_value(item))
    return str(value).strip()


def html_paragraph(value: Any) -> str:
    text = text_value(value)
    return f"<p>{esc(text)}</p>" if text else ""


def title_label(value: Any) -> str:
    label = str(value).replace("_", " ").replace("-", " ").title()
    for original, replacement in {
        "Ai": "AI",
        "Api": "API",
        "Csp": "CSP",
        "Cto": "CTO",
        "Hipaa": "HIPAA",
        "Nsa": "NSA",
        "Phi": "PHI",
        "Pr": "PR",
        "Prs": "PRs",
        "Ui": "UI",
    }.items():
        label = re.sub(rf"\b{original}\b", replacement, label)
    return label


def render_text_section(title: str, value: Any) -> str:
    if not present(value):
        return ""
    return f"""
<section class="artifact-section">
  <h2>{esc(title)}</h2>
  {html_paragraph(value)}
</section>
"""


def render_metrics(metrics: Any) -> str:
    if isinstance(metrics, dict) and not any(key in metrics for key in ["label", "name", "title", "value", "count", "status"]):
        rows = [{"label": title_label(key), "value": value} for key, value in metrics.items() if present(value)]
    else:
        rows = array_value(metrics)
    if not rows:
        return ""

    cards = []
    for metric in rows:
        if isinstance(metric, dict):
            label = text_value(value_at(metric, "label", "name", "title"))
            value = text_value(value_at(metric, "value", "count", "status"))
            detail = text_value(value_at(metric, "detail", "note", "description"))
        else:
            label, value, detail = "Metric", text_value(metric), ""
        if not any([label, value, detail]):
            continue
        cards.append(
            f"""
<div class="metric">
  <span class="label">{esc(label)}</span>
  <span class="value">{esc(value)}</span>
  {f'<span class="detail">{esc(detail)}</span>' if detail else ''}
</div>
"""
        )
    if not cards:
        return ""
    return f'<div class="grid">\n{"".join(cards)}\n</div>'


def render_list_section(title: str, items: Any, empty_note: str | None = None) -> str:
    rows = array_value(items)
    if not rows:
        if not empty_note:
            return ""
        return f"""
<section class="artifact-section">
  <h2>{esc(title)}</h2>
  <p class="empty-item">{esc(empty_note)}</p>
</section>
"""

    list_items = []
    for item in rows:
        if isinstance(item, dict):
            title_text = text_value(value_at(item, "area", "title", "item", "name", "priority", "ask", "decision", "risk", "finding", "question", "prompt"))
            body = text_value(value_at(item, "body", "detail", "details", "summary", "context", "business_impact", "why", "impact", "rationale", "note", "notes"))
            status = text_value(value_at(item, "status"))
            owner = text_value(value_at(item, "owner", "owner_horizon", "needed_by", "done_when"))
            evidence = [text_value(entry) for entry in array_value(value_at(item, "evidence", "sources", "source"))]
            list_items.append(
                f"""
<li>
  {f'<strong>{esc(title_text)}</strong>' if title_text else ''}
  {f'<span>{esc(body)}</span>' if body else ''}
  {f'<span>{esc(status)}</span>' if status and status != body else ''}
  {f'<em>{esc(owner)}</em>' if owner else ''}
  {f'<small>Evidence: {esc("; ".join(filter(None, evidence)))}</small>' if any(evidence) else ''}
</li>
"""
            )
        else:
            list_items.append(f"<li><strong>{esc(text_value(item))}</strong></li>")
    return f"""
<section class="artifact-section">
  <h2>{esc(title)}</h2>
  <ul class="artifact-list">
    {"".join(list_items)}
  </ul>
</section>
"""



def source_entry_html(source: Any, *, prefix: str = "../../") -> str:
    title = ""
    href = ""
    detail = ""
    if isinstance(source, dict):
        title = text_value(value_at(source, "title", "label", "name", "source"))
        href = text_value(value_at(source, "href", "url", "path"))
        detail = text_value(value_at(source, "detail", "summary", "note"))
    else:
        title = text_value(source)
        href = title
    if not title:
        return ""

    resolved = ""
    if href and (isinstance(source, dict) or re.match(r"^(https?://|mailto:|#|/)", href) or re.search(r"\.(?:html|md|json)(?:#.*)?$", href)):
        resolved = source_href(href, prefix)
    label = esc(title)
    if resolved:
        label = f'<a href="{esc(resolved)}">{label}</a>'
    return f"""
<li>
  <strong>{label}</strong>
  {f'<span>{esc(detail)}</span>' if detail else ''}
</li>
"""


def cited_evidence_sources(data: dict[str, Any]) -> list[Any]:
    sources = array_value(value_at(data, "sources", "source_list", "evidence_sources"))
    return [source for source in sources if source_entry_html(source)]


def render_sources(data: dict[str, Any], empty_note: str | None = None) -> str:
    rows = [source_entry_html(source) for source in cited_evidence_sources(data)]
    if not rows:
        if not empty_note:
            return ""
        body = f'<p class="empty-item">{esc(empty_note)}</p>'
    else:
        body = f"""
  <ul class="artifact-list source-list">
    {"".join(rows)}
  </ul>
"""
    return f"""
<details class="artifact-section source-section">
  <summary>
    <span>Sources</span>
    <small>{esc(pluralize(len(rows), "source"))}</small>
  </summary>
  {body}
</details>
"""


def render_thin_evidence_banner() -> str:
    return """
<aside class="report-thin-evidence" aria-label="Thin evidence warning">
  <strong>No cited evidence</strong>
  <span>Claims in this report are not yet traceable to repo sources.</span>
</aside>
"""


def item_headline(item: Any) -> str:
    if isinstance(item, dict):
        for key in [
            "decision",
            "ask",
            "risk",
            "priority",
            "finding",
            "question",
            "title",
            "name",
            "technology",
            "component",
            "layer",
            "headline",
            "summary",
            "mitigation",
            "watchpoint",
        ]:
            value = text_value(value_at(item, key))
            if value:
                return value
        return text_value(item)
    return text_value(item)


def action_group(label: str, value: Any) -> tuple[str, list[str]]:
    items = [snippet(item_headline(item), 95) for item in array_value(value) if item_headline(item)]
    return label, items


def render_action_summary(kind: str, data: dict[str, Any]) -> str:
    groups_by_kind = {
        "ceo-updates": [
            action_group("Asks", value_at(data, "asks_decisions", "asks", "decisions")),
            action_group("Risks / Blockers", value_at(data, "risks_blockers", "risks", "blockers")),
            action_group("Next", value_at(data, "next", "up_next")),
        ],
    }
    groups = [(label, items) for label, items in groups_by_kind.get(kind, []) if items]
    if not groups:
        return ""

    # Suppress the card when it would merely restate the sections directly below.
    # It is pure duplication only when no group is truncated by the items[:2] slice
    # (max_group <= 2, so the card shows each group in full, not a condensed subset)
    # AND the body is short (total_items <= 3 signal rows across its sections, so
    # those rows are already visible without the top block). A >2-item group makes
    # the card a real triage subset; 4+ items total makes it useful navigation across
    # scattered section leads. In both of those cases the card stays.
    total_items = sum(len(items) for _, items in groups)
    max_group = max(len(items) for _, items in groups)
    if max_group <= 2 and total_items <= 3:
        return ""

    rows = []
    for label, items in groups:
        for item in items[:2]:
            rows.append(f'<li><strong>{esc(label)}</strong><span>{esc(item)}</span></li>')
    if not rows:
        return ""

    return f"""
<section class="report-attention" aria-label="Follow-up signals">
  <div class="attention-kicker">Follow-up signals</div>
  <ul>{''.join(rows[:6])}</ul>
</section>
"""


def render_ceo_update(data: dict[str, Any]) -> str:
    # The lead summary renders in the masthead deck (see report_lead_summary), not here.
    return "".join(
        [
            render_metrics(value_at(data, "metrics")),
            render_list_section("Progress", value_at(data, "progress"), "No progress to report for this window."),
            render_list_section("Risks / Blockers", value_at(data, "risks_blockers", "risks", "blockers"), "No risks or blockers this window."),
            render_list_section("Asks / Decisions", value_at(data, "asks_decisions", "asks", "decisions"), "No asks or decisions this window."),
            render_list_section("Next", value_at(data, "next", "up_next"), "Nothing queued for the next window."),
            render_sources(data, "No evidence sources recorded for this window."),
        ]
    )


def render_generic_report(data: dict[str, Any]) -> str:
    # The lead summary renders in the masthead deck (see report_lead_summary), not here.
    sections = []
    for section in array_value(value_at(data, "sections")):
        if not isinstance(section, dict):
            sections.append(render_list_section("Section", [section]))
            continue
        title = text_value(value_at(section, "title", "name"))
        content = value_at(section, "items", "body", "content", "details")
        sections.append(render_list_section(title, content) if isinstance(content, list) else render_text_section(title, content))
    return "".join([*sections, render_sources(data)])


REPORT_CHANGE_GROUPS: dict[str, list[tuple[str, tuple[str, ...]]]] = {
    "ceo-updates": [
        ("Progress", ("progress",)),
        ("Risks / Blockers", ("risks_blockers", "risks", "blockers")),
        ("Asks / Decisions", ("asks_decisions", "asks", "decisions")),
        ("Next", ("next", "up_next")),
    ],
}


def report_change_values(data: dict[str, Any], fields: tuple[str, ...]) -> list[str]:
    values: list[str] = []
    seen: set[str] = set()
    for field in fields:
        raw = value_at(data, field)
        items = array_value(raw) if isinstance(raw, list) else ([raw] if present(raw) else [])
        for item in items:
            value = item_headline(item)
            if not value:
                value = text_value(item)
            value = snippet(value, 110)
            key = value.lower()
            if value and key not in seen:
                seen.add(key)
                values.append(value)
    return values


def summarize_change_list(values: list[str], limit: int = 2) -> str:
    shown = values[:limit]
    text = "; ".join(shown)
    remaining = len(values) - len(shown)
    if remaining > 0:
        text = f"{text}; plus {pluralize(remaining, 'more item')}"
    return text


def format_metric_value(value: int | float, signed: bool = False) -> str:
    # Ints get thousands separators (":g" would render CEO-scale numbers like ARR
    # in scientific notation); floats keep the compact ":g" form.
    if isinstance(value, int):
        return f"{value:+,}" if signed else f"{value:,}"
    return f"{value:+g}" if signed else f"{value:g}"


def metric_delta_items(data: dict[str, Any], previous_data: dict[str, Any]) -> list[str]:
    current = data.get("metrics")
    previous = previous_data.get("metrics")
    if not isinstance(current, dict) or not isinstance(previous, dict):
        return []
    items: list[str] = []
    for label, value in current.items():
        prior = previous.get(label)
        if isinstance(value, bool) or isinstance(prior, bool):
            continue
        if not isinstance(value, (int, float)) or not isinstance(prior, (int, float)):
            continue
        if isinstance(value, float) and not math.isfinite(value):
            continue  # NaN != NaN would render a phantom delta on every run
        if isinstance(prior, float) and not math.isfinite(prior):
            continue
        if value == prior:
            continue
        try:
            rendered = (
                f"<li><strong>{esc(text_value(label))}:</strong> "
                f"{esc(format_metric_value(prior))} → {esc(format_metric_value(value))} "
                f"({esc(format_metric_value(value - prior, signed=True))})</li>"
            )
        except (OverflowError, ValueError):
            continue  # e.g. int too large for float math — skip the delta, never abort the write
        items.append(rendered)
    return items


CHANGE_NOTE_TEXT = {
    "cadence_fallback": "Prior report predates cadence tagging.",
    "no_weekly_prior": "No prior weekly report — compared against the most recent report of any type.",
    "overlap": "Overlapping windows — deltas may double-count.",
}


def report_changes_html(
    kind: str,
    data: dict[str, Any],
    previous_data: dict[str, Any] | None,
    previous_date: str,
    change_notes: list[str] | None = None,
) -> str:
    if kind != "ceo-updates":
        return ""
    per_group = True
    if not isinstance(previous_data, dict):
        if per_group:
            # The week-over-week section is always present on new CEO reports so the
            # canonical section list stays invariant (docs/ceo-report-template.md).
            return """
<section class="report-changes">
  <h2>Week over week</h2>
  <ul><li><strong>First report</strong> — no prior baseline.</li></ul>
</section>
"""
        return ""

    changes: list[str] = []
    metric_items: list[str] = []
    if per_group:
        for note in change_notes or []:
            text = CHANGE_NOTE_TEXT.get(note)
            if text:
                changes.append(f"<li><strong>Note:</strong> {esc(text)}</li>")
        metric_items = metric_delta_items(data, previous_data)
        changes.extend(metric_items)

    group_changes = 0
    not_comparable = 0
    for label, fields in REPORT_CHANGE_GROUPS.get(kind, []):
        if per_group and not any(field in previous_data for field in fields):
            changes.append(f"<li><strong>{esc(label)}:</strong> Not comparable — prior report lacked this section.</li>")
            not_comparable += 1
            continue
        current = report_change_values(data, fields)
        previous = report_change_values(previous_data, fields)
        current_keys = {value.lower() for value in current}
        previous_keys = {value.lower() for value in previous}
        added = [value for value in current if value.lower() not in previous_keys]
        removed = [value for value in previous if value.lower() not in current_keys]
        if per_group:
            # Per-group bound for ceo-updates: every group renders its adds and removals;
            # other kinds keep the legacy whole-section cap below.
            if not current and previous:
                changes.append(f"<li><strong>{esc(label)}:</strong> No items this window (prior listed: {esc(summarize_change_list(previous, 2))}).</li>")
                group_changes += 1
                continue
            if added:
                changes.append(f"<li><strong>{esc(label)}:</strong> Added: {esc(summarize_change_list(added, 3))}</li>")
                group_changes += 1
            if removed:
                changes.append(f"<li><strong>{esc(label)}:</strong> No longer listed: {esc(summarize_change_list(removed, 2))}</li>")
                group_changes += 1
            continue
        if added:
            changes.append(f"<li><strong>{esc(label)}:</strong> Added: {esc(summarize_change_list(added))}</li>")
            group_changes += 1
        if removed and len(changes) < 4:
            changes.append(f"<li><strong>{esc(label)}:</strong> No longer listed: {esc(summarize_change_list(removed, 1))}</li>")
            group_changes += 1
        if len(changes) >= 4:
            break

    # Skip the "no material changes" fallback when not-comparable lines rendered —
    # "not comparable" and "broadly consistent" would contradict each other.
    if (per_group and group_changes == 0 and not metric_items and not not_comparable) or not changes:
        current_summary = report_lead_summary(data, 160)
        previous_summary = report_lead_summary(previous_data, 160)
        if current_summary and current_summary != previous_summary:
            changes.append(f"<li><strong>Summary:</strong> Updated emphasis: {esc(current_summary)}</li>")
        else:
            changes.append("<li><strong>No material structured changes:</strong> This report is broadly consistent with the previous run.</li>")

    date_text = previous_date or "the previous run"
    heading = f"Significant changes since the last report was run on {date_text}"
    rendered = changes
    return f"""
<section class="report-changes">
  <h2>{esc(heading)}</h2>
  <ul>{''.join(rendered)}</ul>
</section>
"""


def render_structured_report(
    kind: str,
    data: dict[str, Any],
    previous_data: dict[str, Any] | None = None,
    previous_date: str = "",
    change_notes: list[str] | None = None,
) -> str:
    change_summary = report_changes_html(kind, data, previous_data, previous_date, change_notes)
    body = render_ceo_update(data) if kind == "ceo-updates" else render_generic_report(data)
    # The lead summary now lives in the masthead, so the follow-up-signals card
    # anchors deterministically at the top of the body for every kind.
    action_summary = render_action_summary(kind, data)
    rendered = f"{change_summary}{action_summary}{body}".strip() or render_generic_report(data)
    # A blank body is legitimate when the lead summary carries the report in the
    # masthead deck. Only surface a placeholder when nothing at all was captured.
    if not rendered.strip() and not report_lead_summary(data):
        rendered = '<p class="empty-item">No content yet.</p>'
    if not cited_evidence_sources(data):
        rendered = f"{render_thin_evidence_banner()}{rendered}"
    return rendered


ALLOWED_LINK_SCHEMES = {"http", "https", "mailto"}


def href_scheme_allowed(href: str) -> bool:
    """Return True for relative/anchor hrefs and http(s)/mailto schemes.

    Used to keep operator-authored Markdown links (core/RISKS.md, DECISIONS.md)
    from emitting javascript:/data:/vbscript: hrefs. This is a robustness guard
    on the operator's own content, not a remote-attacker defense.
    """
    href = (href or "").strip()
    if not href:
        return False
    # Reject the control chars browsers strip from inside URLs and that hide a
    # scheme (e.g. "java\tscript:alert(1)"). A regular space (0x20) is a valid
    # href character, so it is intentionally not in this range.
    if re.search(r"[\x00-\x1f\x7f]", href):
        return False
    match = re.match(r"^([a-zA-Z][a-zA-Z0-9+.\-]*):", href)
    if not match:
        # No scheme: relative path, ./, ../, #anchor, or //host. Allowed.
        return True
    return match.group(1).lower() in ALLOWED_LINK_SCHEMES


def report_run_date(path: Path) -> str:
    match = re.match(r"^(\d{4}-\d{2}-\d{2})-", path.name)
    return match.group(1) if match else "Unknown date"


def report_name(path: Path) -> str:
    return re.sub(r"^\d{4}-\d{2}-\d{2}-", "", path.stem).replace("-", " ")


def read_json_file(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return default


def date_value(value: Any) -> dt.date | None:
    try:
        return dt.date.fromisoformat(str(value))
    except ValueError:
        return None


def html_title(path: Path) -> str:
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return report_name(path)
    if match := re.search(r"<title[^>]*>(.*?)</title>", text, re.I | re.S):
        return plain_html(match.group(1)) or report_name(path)
    if match := re.search(r"<h1[^>]*>(.*?)</h1>", text, re.I | re.S):
        return plain_html(match.group(1)) or report_name(path)
    return report_name(path)


def report_summary(path: Path, limit: int = 190) -> str:
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""
    return snippet(plain_html(text), limit)


def report_lead_summary(data: Any, limit: int | None = None) -> str:
    """Lead one-line summary a report renders as its masthead deck.

    Reads the structured fields the body renderers lead with (executive_read,
    headline, summary) so previews and the masthead reuse the same sentence
    instead of re-parsing emitted HTML.
    """
    if not isinstance(data, dict):
        return ""
    text = text_value(value_at(data, "executive_read", "headline", "summary"))
    if not text:
        return ""
    return snippet(text, limit) if limit else text


def report_summary_for_path(path: Path, limit: int = 190) -> str:
    """Prefer the structured report summary; fall back to stripped HTML.

    Structured reports persist their source JSON next to the HTML, so the clean
    lead summary is read straight from it. Legacy --body-file reports without a
    sibling JSON fall back to the stripped-HTML snippet.
    """
    lead = report_lead_summary(read_json_file(path.with_suffix(".json"), None), limit)
    return lead or report_summary(path, limit)


CEO_REPORT_SCHEMA_VERSION = "ceo-report/1"
CEO_REPORT_TYPES = ("weekly", "ad_hoc")
DEFAULT_WEEKLY_CADENCE_DAYS = 7
NORTH_STAR_STREAK_WEEKS = 3


def validate_ceo_report(data: dict[str, Any]) -> list[str]:
    """Warn-only schema v1 check for ceo-updates report JSON (docs/ceo-report-template.md)."""
    warnings: list[str] = []
    for key in ("report_type", "company", "window", "headline", "progress", "risks_blockers", "asks_decisions", "next", "sources"):
        if key not in data:
            warnings.append(f"missing required field: {key}")
    report_type = data.get("report_type")
    if report_type is not None and report_type not in CEO_REPORT_TYPES:
        warnings.append(f"report_type must be one of {'/'.join(CEO_REPORT_TYPES)}, got: {report_type!r}")
    window = data.get("window")
    if window is not None:
        if not isinstance(window, dict):
            warnings.append("window must be an object with ISO start and end dates")
        else:
            start = date_value(window.get("start"))
            end = date_value(window.get("end"))
            if not start:
                warnings.append("window.start must be an ISO YYYY-MM-DD date")
            if not end:
                warnings.append("window.end must be an ISO YYYY-MM-DD date")
            if start and end and end < start:
                warnings.append("window.end is earlier than window.start")
    for field, required_key in (("progress", "area"), ("risks_blockers", "risk"), ("asks_decisions", "ask")):
        for item in array_value(data.get(field)):
            if not isinstance(item, dict):
                warnings.append(f"{field} items should be objects (schema v1), got bare value: {snippet(text_value(item), 40)!r}")
                break
            if required_key not in item:
                warnings.append(f"{field} items should carry {required_key!r} (schema v1)")
                break
    # This is only an empty-report tripwire. It cannot distinguish an intentional
    # quiet window from forgotten structure, and carried-forward risks correctly
    # suppress it.
    if not any(array_value(data.get(field)) for field in ("progress", "risks_blockers", "asks_decisions", "next")):
        warnings.append("report has no structured content; if the window was quiet, say so in headline")
    metrics = data.get("metrics")
    if metrics is not None:
        if not isinstance(metrics, dict):
            warnings.append("metrics must be a flat object of label -> scalar")
        else:
            for label, value in metrics.items():
                if isinstance(value, (dict, list)):
                    warnings.append(f"metrics[{label!r}] must be a scalar, got {type(value).__name__}")
    return warnings


def report_effective_date(json_path: Path, data: Any) -> str | None:
    """The date a report counts as, for prior-report ordering: window.end, else ISO filename prefix."""
    if isinstance(data, dict):
        window = data.get("window")
        if isinstance(window, dict):
            end = date_value(window.get("end"))
            if end:
                return end.isoformat()
    if match := re.match(r"^(\d{4}-\d{2}-\d{2})-", json_path.name):
        return match.group(1)
    return None


def weekly_report_dates(reports_dir: Path) -> list[dt.date]:
    dates: set[dt.date] = set()
    if not reports_dir.exists():
        return []
    for path in sorted(reports_dir.glob("*.json")):
        if path.name == "data.json":
            continue
        data = read_json_file(path, None)
        if not isinstance(data, dict):
            print(f"dzcto: skipping weekly-streak candidate {path.name} (unreadable JSON)", file=sys.stderr)
            continue
        if data.get("report_type") != "weekly":
            continue
        effective_date = date_value(report_effective_date(path, data))
        if effective_date is None:
            print(f"dzcto: skipping weekly-streak candidate {path.name} (no resolvable date)", file=sys.stderr)
            continue
        dates.add(effective_date)
    return sorted(dates, reverse=True)


def rounded_period_index(delta_days: int, cadence_days_value: int) -> int:
    # Avoid Python's banker's rounding; cadence buckets need stable half-up periods.
    return (delta_days * 2 + cadence_days_value) // (2 * cadence_days_value)


def weekly_streak(dates: list[dt.date], today: dt.date, cadence_days_value: int) -> int:
    cadence = cadence_days_value if cadence_days_value > 0 else DEFAULT_WEEKLY_CADENCE_DAYS
    ordered_dates = sorted(set(dates), reverse=True)
    if not ordered_dates:
        return 0

    latest = ordered_dates[0]
    if rounded_period_index((today - latest).days, cadence) >= 2:
        return 0

    periods = {
        rounded_period_index((latest - report_date).days, cadence)
        for report_date in ordered_dates
    }
    streak = 0
    while streak in periods:
        streak += 1
    return streak


def resolve_weekly_cadence_days(core_dir: Path, report_folder: str) -> int:
    target_folder = normalize_report_folder(report_folder)
    for rule in parse_cadence_rules(core_dir / "OPERATING_CADENCE.md"):
        if normalize_report_folder(str(rule.get("folder") or "")) != target_folder:
            continue
        try:
            interval_days = int(rule.get("interval_days") or 0)
        except (TypeError, ValueError):
            interval_days = 0
        if interval_days > 0:
            return interval_days
    return DEFAULT_WEEKLY_CADENCE_DAYS


def locate_prior_report(json_path: Path, data: dict[str, Any]) -> tuple[Path | None, dict[str, Any] | None, str, list[str]]:
    """Select the prior report to diff against (rules in docs/ceo-report-template.md).

    Returns (path, data, effective_date, notes). Notes may contain "cadence_fallback"
    (weekly report diffed against an untyped/ad-hoc prior because no weekly prior exists)
    and/or "overlap" (only overlapping-window priors were available).
    """
    current_type = data.get("report_type") if data.get("report_type") in CEO_REPORT_TYPES else "ad_hoc"
    window = data.get("window") if isinstance(data.get("window"), dict) else {}
    current_start = date_value(window.get("start"))
    current_end = date_value(window.get("end")) or date_value(report_effective_date(json_path, data))
    if current_start is None:
        current_start = current_end

    candidates: list[tuple[dt.date, str, Path, dict[str, Any], str]] = []
    for path in sorted(json_path.parent.glob("*.json")):
        if path.name == "data.json" or path.resolve() == json_path.resolve():
            continue
        cand = read_json_file(path, None)
        if not isinstance(cand, dict):
            print(f"dzcto: skipping prior-report candidate {path.name} (unreadable JSON)", file=sys.stderr)
            continue
        eff = date_value(report_effective_date(path, cand))
        if eff is None:
            print(f"dzcto: skipping prior-report candidate {path.name} (no resolvable date)", file=sys.stderr)
            continue
        cand_window = cand.get("window") if isinstance(cand.get("window"), dict) else {}
        if (
            current_start is not None
            and current_end is not None
            and date_value(cand_window.get("start")) == current_start
            and date_value(cand_window.get("end")) == current_end
        ):
            continue  # a rerun of the same window is not its own prior
        cand_type = cand.get("report_type") if cand.get("report_type") in CEO_REPORT_TYPES else "ad_hoc"
        candidates.append((eff, str(cand.get("generated_at") or ""), path, cand, cand_type))

    if current_end is None or not candidates:
        return None, None, "", []

    def newest(pool: list[tuple[dt.date, str, Path, dict[str, Any], str]]):
        return max(pool, default=None, key=lambda item: (item[0], item[1]))

    notes: list[str] = []
    chosen = None
    weekly_pool_missed = False
    if current_type == "weekly":
        # Same-cadence comparison orders by window.end with no overlap caveat:
        # rolling-lookback weekly windows overlap by design.
        chosen = newest([c for c in candidates if c[4] == "weekly" and c[0] < current_end])
        if chosen is None:
            weekly_pool_missed = True
    if chosen is None:
        chosen = newest([c for c in candidates if current_start is not None and c[0] < current_start])
        if chosen is None:
            # "<=" so a same-day prior (equal effective date, different window) is still
            # found instead of falsely claiming "first report"; self and same-window
            # reruns were already excluded above.
            chosen = newest([c for c in candidates if c[0] <= current_end])
            if chosen is not None:
                notes.append("overlap")
    if chosen is None:
        return None, None, "", []
    eff, _generated_at, path, cand, cand_type = chosen
    if weekly_pool_missed and cand_type != "weekly":
        # Name the situation accurately: untyped legacy priors predate cadence tagging;
        # a typed ad_hoc prior is simply not a weekly.
        notes.insert(0, "cadence_fallback" if cand.get("report_type") not in CEO_REPORT_TYPES else "no_weekly_prior")
    return path, cand, eff.isoformat(), notes


def source_href(href: str, prefix: str) -> str:
    href = (href or "").strip()
    if not href:
        return ""
    if not href_scheme_allowed(href):
        return ""
    if re.match(r"^(https?://|mailto:|#|/)", href) or href.startswith(("../", "./")):
        return href
    return prefix + href


def search_text_attr(*values: Any) -> str:
    return esc(plain_markdown(" ".join(text_value(value) for value in values)).lower())


def command_center_css() -> str:
    return """
:root {
  --bg: #f5f7f3;
  --surface: #fffffb;
  --surface-2: #eef3ee;
  --surface-3: #e1e9e2;
  --ink: #17211f;
  --ink-2: #40514e;
  --muted: #687874;
  --faint: #94a19d;
  --line: #d7ded8;
  --line-2: #c4cec7;
  --accent: #23685b;
  --accent-2: #164d44;
  --accent-soft: #dceee7;
  --accent-ink: #103a34;
  --crit: #ad3b35;
  --crit-soft: #f7e6e2;
  --crit-line: #e5b8b0;
  --high: #99651d;
  --high-soft: #f4ead7;
  --high-line: #dfc391;
  --med: #6f6a2a;
  --med-soft: #ecebd7;
  --med-line: #d1cd91;
  --low: #506270;
  --low-soft: #e3eaee;
  --low-line: #c5d0d7;
  --good: #237048;
  --good-soft: #dceee4;
  --good-line: #abd4bd;
  --r-sm: 7px;
  --r-md: 10px;
  --r-lg: 14px;
  --r-pill: 999px;
  --gap: 14px;
  --shadow-sm: 0 1px 2px rgba(23,33,31,.05), 0 1px 1px rgba(23,33,31,.04);
  --shadow-md: 0 12px 34px rgba(23,33,31,.1), 0 1px 4px rgba(23,33,31,.06);
  --ring: 0 0 0 3px rgba(35,104,91,.28);
  --nav-bg: rgba(245,247,243,.92);
  --display: Georgia, "Times New Roman", serif;
  --ui: -apple-system, BlinkMacSystemFont, "Segoe UI", "Helvetica Neue", Arial, sans-serif;
  --mono: ui-monospace, "SF Mono", SFMono-Regular, Menlo, Consolas, "Liberation Mono", monospace;
  --maxw: 1120px;
}
html[data-theme="dark"] {
  --bg: #101713;
  --surface: #17211d;
  --surface-2: #1d2a25;
  --surface-3: #263630;
  --ink: #eef4ef;
  --ink-2: #c8d4ce;
  --muted: #97a69f;
  --faint: #6f7e77;
  --line: #2c3b35;
  --line-2: #3a4b44;
  --accent: #7bc8b8;
  --accent-2: #a1d8cc;
  --accent-soft: #18362f;
  --accent-ink: #cbf2ea;
  --crit: #ff9a91;
  --crit-soft: #3a1b18;
  --crit-line: #65302a;
  --high: #e8b76f;
  --high-soft: #352714;
  --high-line: #5b421e;
  --med: #d7d06f;
  --med-soft: #303016;
  --med-line: #535127;
  --low: #acc0cc;
  --low-soft: #202d33;
  --low-line: #364850;
  --good: #74d6a3;
  --good-soft: #143323;
  --good-line: #245a3c;
  --shadow-sm: 0 1px 2px rgba(0,0,0,.4);
  --shadow-md: 0 8px 28px rgba(0,0,0,.5);
  --ring: 0 0 0 3px rgba(123,200,184,.32);
  --nav-bg: rgba(16,23,19,.92);
}
* { box-sizing: border-box; }
html { scroll-behavior: smooth; scroll-padding-top: 76px; }
body {
  margin: 0;
  background:
    linear-gradient(90deg, rgba(35,104,91,.08) 0, rgba(35,104,91,.08) 1px, transparent 1px) max(22px, calc((100vw - var(--maxw)) / 2)) 0 / 26px 100% no-repeat,
    radial-gradient(circle at top right, rgba(153,101,29,.11), transparent 310px),
    var(--bg);
  color: var(--ink);
  font-family: var(--ui);
  font-size: 15px;
  line-height: 1.5;
  -webkit-font-smoothing: antialiased;
  text-rendering: optimizeLegibility;
}
a { color: var(--accent); text-decoration: none; }
a:hover { text-decoration: underline; }
h1, h2, h3, h4 { margin: 0; line-height: 1.12; letter-spacing: 0; }
p { margin: 0; color: var(--ink-2); }
h1, h2, h3, h4, p, a, code, strong, span { overflow-wrap: anywhere; }
button, input, select { font-family: inherit; }
button { cursor: pointer; }
[hidden] { display: none !important; }
:focus-visible { outline: none; box-shadow: var(--ring); border-radius: 6px; }
.sticky-nav {
  position: sticky;
  top: 0;
  z-index: 50;
  display: grid;
  grid-template-columns: minmax(0, 1fr) auto;
  gap: 16px;
  align-items: center;
  min-height: 58px;
  padding: 9px max(18px, calc((100vw - var(--maxw)) / 2 + 26px));
  border-bottom: 1px solid var(--line);
  background: var(--nav-bg);
  backdrop-filter: blur(14px);
  box-shadow: 0 1px 2px rgba(23,33,31,.04);
}
.sticky-main { min-width: 0; display: grid; gap: 2px; }
.sticky-home { overflow: hidden; color: var(--muted); font-size: 12.5px; line-height: 1.25; text-overflow: ellipsis; white-space: nowrap; }
.sticky-home:hover { color: var(--accent); text-decoration: none; }
.sticky-title { display: block; overflow: hidden; color: var(--ink); font-size: 14px; font-weight: 800; line-height: 1.25; text-overflow: ellipsis; white-space: nowrap; }
.sticky-title:hover { color: var(--accent-ink); text-decoration: none; }
.sticky-crumbs { display: flex; align-items: center; flex-wrap: nowrap; gap: 6px; overflow: hidden; color: var(--muted); font-size: 11.5px; line-height: 1.25; white-space: nowrap; }
.sticky-crumbs a, .sticky-crumbs span { flex: 0 0 auto; color: var(--muted); }
.sticky-crumbs a:hover { color: var(--accent); text-decoration: none; }
.sticky-actions { display: flex; align-items: center; justify-content: flex-end; gap: 8px; min-width: 0; }
.sticky-actions .search { width: 240px; }
.sticky-actions .theme-btn { min-height: 32px; }
.app { max-width: var(--maxw); margin: 0 auto; padding: 46px 26px 92px; }
.masthead {
  display: grid;
  grid-template-columns: minmax(0, 1fr) auto;
  gap: 26px;
  align-items: start;
  margin-bottom: 32px;
  border-bottom: 1px solid var(--line);
  padding-bottom: 28px;
}
.eyebrow {
  display: inline-flex;
  align-items: center;
  gap: 9px;
  color: var(--accent);
  font-family: var(--mono);
  font-size: 11px;
  font-weight: 800;
  letter-spacing: 0;
  margin-bottom: 12px;
  text-transform: uppercase;
}
.eyebrow::before { content: ""; width: 22px; height: 2px; background: var(--high); border-radius: 2px; }
h1.title {
  max-width: 940px;
  color: var(--ink);
  font-family: var(--display);
  font-size: 46px;
  font-weight: 700;
  letter-spacing: 0;
}
.title .light { color: var(--muted); font-weight: 500; }
.lede {
  max-width: 880px;
  margin-top: 14px;
  color: var(--ink-2);
  font-size: 17px;
  line-height: 1.58;
}
.masthead-stamp { margin-top: 8px; color: var(--muted); font-family: var(--mono); font-size: 12px; }
.masthead-side { display: flex; flex-direction: column; align-items: flex-end; gap: 10px; min-width: min(300px, 100%); }
.masthead-mobile-tools { display: none; }
.util { display: flex; gap: 8px; justify-content: flex-end; }
.theme-btn, .icon-btn {
  min-height: 34px;
  border: 1px solid var(--line-2);
  background: var(--surface);
  color: var(--ink-2);
  border-radius: var(--r-sm);
  font-size: 12.5px;
  font-weight: 700;
  transition: .15s;
}
.theme-btn { display: inline-flex; align-items: center; gap: 7px; padding: 0 12px; }
.icon-btn { width: 34px; display: grid; place-items: center; }
.theme-btn:hover, .icon-btn:hover { border-color: var(--accent); color: var(--accent); }
.masthead-title-link { display: inline-block; color: inherit; text-decoration: none; }
.masthead-title-link:hover { text-decoration: none; }
.masthead-title-link:hover .title { color: var(--accent-ink); }
.search { position: relative; width: 280px; max-width: 100%; }
.search input {
  width: 100%;
  border: 1px solid var(--line-2);
  border-radius: var(--r-sm);
  background: var(--surface);
  color: var(--ink);
  font-size: 13.5px;
  padding: 9px 34px;
}
.search input::placeholder { color: var(--faint); }
.search svg { position: absolute; left: 11px; top: 50%; transform: translateY(-50%); color: var(--faint); pointer-events: none; }
.search-clear {
  display: none;
  position: absolute;
  right: 8px;
  top: 50%;
  transform: translateY(-50%);
  width: 18px;
  height: 18px;
  border: 0;
  border-radius: 50%;
  background: var(--surface-3);
  color: var(--muted);
  font-size: 11px;
  line-height: 1;
}
.search-results {
  position: absolute;
  z-index: 20;
  left: 0;
  right: 0;
  top: calc(100% + 7px);
  max-height: 58vh;
  overflow: auto;
  border: 1px solid var(--line);
  border-radius: var(--r-md);
  background: var(--surface);
  box-shadow: var(--shadow-md);
  padding: 6px;
}
.search-result { display: block; color: var(--ink); border-radius: var(--r-sm); padding: 9px; }
.search-result:hover, .search-result:focus { background: var(--surface-2); text-decoration: none; }
.search-result span, .search-result strong, .search-result p { display: block; }
.search-result span { color: var(--muted); font-size: 11px; font-weight: 800; margin-bottom: 2px; text-transform: uppercase; }
.search-result p { color: var(--muted); font-size: 12.5px; margin-top: 4px; }
.kpis { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 10px; margin: 4px 0 34px; }
.kpi {
  display: block;
  position: relative;
  overflow: hidden;
  background: var(--surface);
  border: 1px solid var(--line);
  border-radius: var(--r-sm);
  padding: 16px 16px 15px;
  box-shadow: var(--shadow-sm);
  color: var(--ink);
  text-decoration: none;
  transition: .15s;
}
.kpi:hover { border-color: var(--accent); box-shadow: var(--shadow-md); text-decoration: none; transform: translateY(-1px); }
.k-label { color: var(--muted); font-family: var(--mono); font-size: 10.5px; font-weight: 800; letter-spacing: 0; text-transform: uppercase; }
.k-val { display: flex; align-items: baseline; gap: 6px; margin-top: 8px; font-family: var(--display); font-size: 32px; font-weight: 700; line-height: 1; }
.k-val .unit { color: var(--faint); font-size: 13px; font-weight: 700; }
.k-sub { margin-top: 4px; color: var(--muted); font-size: 11.5px; }
.kpi[data-tone]::before { content: ""; position: absolute; inset: 0 auto 0 0; width: 3px; }
.kpi[data-tone="crit"]::before { background: var(--crit); }
.kpi[data-tone="good"]::before { background: var(--good); }
.kpi[data-tone="warn"]::before { background: var(--high); }
.kpi[data-tone="info"]::before { background: var(--accent); }
.kpi[data-tone="crit"] .k-val { color: var(--crit); }
.kpi[data-tone="good"] .k-val { color: var(--good); }
.setup-panel {
  margin: -8px 0 28px;
  overflow: hidden;
  border: 1px solid var(--line);
  border-radius: var(--r-lg);
  background: var(--surface);
  box-shadow: var(--shadow-sm);
}
.setup-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 14px;
  padding: 14px 18px;
  border-bottom: 1px solid var(--line);
  background: var(--surface-2);
}
.setup-head h2 { font-size: 16px; font-weight: 800; }
.setup-head p { margin-top: 2px; color: var(--muted); font-size: 12px; }
.setup-help {
  border: 1px solid var(--line-2);
  border-radius: var(--r-pill);
  background: var(--surface);
  color: var(--ink-2);
  padding: 5px 10px;
  font-size: 12px;
  font-weight: 800;
}
.setup-help:hover { border-color: var(--accent); color: var(--accent); text-decoration: none; }
.setup-list { display: grid; grid-template-columns: repeat(7, minmax(0, 1fr)); }
.setup-item {
  display: grid;
  grid-template-columns: auto minmax(0, 1fr);
  grid-template-rows: auto auto;
  gap: 2px 9px;
  min-height: 96px;
  padding: 13px;
  border-right: 1px solid var(--line);
  color: inherit;
  text-decoration: none;
}
.setup-item:last-child { border-right: 0; }
.setup-item:hover { background: var(--surface-2); text-decoration: none; }
.setup-mark { width: 10px; height: 10px; margin-top: 4px; border-radius: 50%; background: var(--high); box-shadow: 0 0 0 4px var(--high-soft); }
.setup-item[data-state="done"] .setup-mark { background: var(--good); box-shadow: 0 0 0 4px var(--good-soft); }
.setup-body { min-width: 0; }
.setup-title { display: block; color: var(--ink); font-size: 12.5px; font-weight: 800; }
.setup-detail { display: block; margin-top: 3px; color: var(--muted); font-size: 11px; line-height: 1.35; }
.setup-action { grid-column: 2; color: var(--accent); font-size: 10.5px; font-weight: 800; text-transform: uppercase; }
.setup-item[data-state="done"] .setup-action { color: var(--good); }
.setup-page-list .setup-list { grid-template-columns: 1fr; }
.setup-page-list .setup-item {
  grid-template-columns: auto minmax(0, 1fr) auto;
  grid-template-rows: auto;
  align-items: center;
  min-height: auto;
  padding: 15px 18px;
  border-right: 0;
  border-bottom: 1px solid var(--line);
}
.setup-page-list .setup-item:last-child { border-bottom: 0; }
.setup-page-list .setup-body { display: grid; gap: 3px; }
.setup-page-list .setup-title { font-size: 13.5px; }
.setup-page-list .setup-detail { font-size: 12.5px; }
.setup-page-list .setup-action { grid-column: auto; align-self: center; }
.setup-summary {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 18px;
  margin: -8px 0 26px;
  border: 1px solid var(--line);
  border-radius: var(--r-lg);
  background: var(--surface);
  box-shadow: var(--shadow-sm);
  padding: 16px 18px;
}
.setup-summary h2 { margin-top: 3px; font-size: 17px; font-weight: 800; }
.setup-summary p { margin-top: 4px; font-size: 12.5px; }
.setup-summary ul { display: flex; flex-wrap: wrap; gap: 7px; margin: 10px 0 0; padding: 0; list-style: none; }
.setup-summary li {
  border: 1px solid var(--high-line);
  border-radius: var(--r-pill);
  background: var(--high-soft);
  color: var(--high);
  padding: 4px 9px;
  font-size: 11px;
  font-weight: 800;
}
.setup-kicker { color: var(--muted); font-size: 11px; font-weight: 800; text-transform: uppercase; }
.setup-primary {
  flex: 0 0 auto;
  border: 1px solid var(--line-2);
  border-radius: var(--r-pill);
  background: var(--surface-2);
  color: var(--ink-2);
  padding: 8px 13px;
  font-size: 12px;
  font-weight: 800;
}
.setup-primary:hover { border-color: var(--accent); color: var(--accent); text-decoration: none; }
.setup-alert { border-color: var(--high-line); background: var(--high-soft); }
.setup-alert .setup-kicker, .setup-alert h2 { color: var(--high); }
.setup-alert .setup-primary { border-color: var(--high-line); background: var(--surface); color: var(--high); }
.setup-reference { opacity: .86; }
.setup-reference:hover { opacity: 1; }
.setup-reference .setup-primary { color: var(--good); border-color: var(--good-line); background: var(--good-soft); }
.sec-body > .setup-summary { margin: 0; }
.today {
  margin-bottom: 34px;
  overflow: hidden;
  background: var(--surface);
  border: 1px solid var(--line);
  border-radius: var(--r-lg);
  box-shadow: var(--shadow-md);
}
.today-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 14px;
  padding: 16px 20px;
  border-bottom: 1px solid var(--line);
  background: linear-gradient(180deg, var(--surface-2), var(--surface));
}
.today-head h2 { display: flex; align-items: center; gap: 10px; font-size: 16px; font-weight: 800; }
.stamp { color: var(--muted); font-family: var(--mono); font-size: 12px; }
.pulse { width: 8px; height: 8px; border-radius: 50%; background: var(--good); box-shadow: 0 0 0 4px var(--good-soft); }
.today-grid { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); }
.today-col { min-width: 0; padding: 18px 20px; border-right: 1px solid var(--line); }
.today-col:last-child { border-right: 0; }
.col-h { display: flex; align-items: center; gap: 7px; margin-bottom: 13px; color: var(--muted); font-size: 11.5px; font-weight: 800; letter-spacing: 0; text-transform: uppercase; }
.cnt { background: var(--surface-3); color: var(--ink-2); border-radius: var(--r-pill); padding: 1px 8px; font-size: 11px; }
.dec, .mini-risk, .cad-mini { border-top: 1px solid var(--line); padding: 9px 0; color: inherit; text-decoration: none; }
.dec:first-of-type, .mini-risk:first-of-type, .cad-mini:first-of-type { border-top: 0; padding-top: 2px; }
.dec { display: flex; gap: 11px; }
.dec:hover, .mini-risk:hover, .cad-mini:hover { color: inherit; text-decoration: none; }
.dec:hover .d-title, .mini-risk:hover .mr-title, .cad-mini:hover .cm-name { color: var(--accent); }
.idx { flex: 0 0 auto; width: 20px; height: 20px; border-radius: 6px; display: grid; place-items: center; margin-top: 1px; background: var(--accent-soft); color: var(--accent-ink); font-size: 11px; font-weight: 800; }
.d-title, .mr-title, .cm-name { color: var(--ink); font-size: 13.5px; font-weight: 700; }
.d-meta, .mr-meta, .cm-sub { display: flex; gap: 8px; flex-wrap: wrap; margin-top: 3px; color: var(--muted); font-size: 11.5px; }
.mini-risk { display: flex; align-items: center; gap: 10px; }
.sev-dot { width: 11px; height: 11px; border-radius: 50%; flex: 0 0 auto; }
.dot-crit { background: var(--crit); }
.dot-high { background: var(--high); }
.dot-med { background: var(--med); }
.dot-low { background: var(--low); }
.cad-mini { display: flex; align-items: center; justify-content: space-between; gap: 10px; }
.cm-when { color: var(--good); font-size: 11.5px; font-weight: 800; white-space: nowrap; }
.section { border-top: 1px solid var(--line); }
.section > summary { display: flex; align-items: center; gap: 14px; padding: 24px 0 20px; cursor: pointer; list-style: none; }
.section > summary::-webkit-details-marker, .risk > summary::-webkit-details-marker { display: none; }
.chev { width: 9px; height: 9px; border-right: 2px solid var(--faint); border-bottom: 2px solid var(--faint); transform: rotate(-45deg); transition: transform .18s ease; flex: 0 0 auto; }
.section[open] > summary .chev { transform: rotate(45deg); }
.sec-title { color: var(--ink); font-family: var(--display); font-size: 25px; font-weight: 700; white-space: nowrap; }
.sec-num { color: var(--high); font-family: var(--mono); font-size: 12px; font-weight: 800; }
.sec-meta { display: flex; align-items: center; gap: 10px; margin-left: auto; color: var(--muted); font-size: 13px; text-align: right; }
.sec-body { padding: 2px 0 34px; }
.toolbar { display: flex; align-items: center; gap: 10px; flex-wrap: wrap; margin-bottom: 16px; }
.tb-label { color: var(--muted); font-size: 12px; font-weight: 700; }
.chipset { display: inline-flex; gap: 6px; flex-wrap: wrap; }
.chip {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  border: 1px solid var(--line-2);
  background: var(--surface);
  color: var(--ink-2);
  border-radius: var(--r-pill);
  padding: 5px 11px;
  font-size: 12px;
  font-weight: 700;
  transition: .12s;
}
.chip:hover { border-color: var(--accent); color: var(--accent); }
.chip[aria-pressed="true"] { background: var(--accent); border-color: var(--accent); color: #fff; }
.chip .swatch { width: 8px; height: 8px; border-radius: 50%; }
.tb-spacer { flex: 1; }
.count-pill { color: var(--muted); font-family: var(--mono); font-size: 12px; }
.risk-list { display: grid; gap: 10px; }
.risk {
  overflow: hidden;
  border: 1px solid var(--line);
  border-radius: var(--r-md);
  background: var(--surface);
  box-shadow: var(--shadow-sm);
}
.risk > summary { display: grid; grid-template-columns: auto 1fr auto; align-items: center; gap: 13px; padding: 13px 15px; cursor: pointer; list-style: none; }
.r-main { min-width: 0; }
.r-title { color: var(--ink); font-size: 14.5px; font-weight: 700; }
.r-sub { display: flex; align-items: center; gap: 9px; flex-wrap: wrap; margin-top: 3px; color: var(--muted); font-size: 12px; }
.r-right { display: flex; align-items: center; gap: 12px; }
.r-chev { width: 8px; height: 8px; border-right: 2px solid var(--faint); border-bottom: 2px solid var(--faint); transform: rotate(45deg); transition: transform .18s; }
.risk[open] .r-chev { transform: rotate(225deg); }
.r-detail { display: grid; gap: 12px; margin-top: -1px; padding: 14px 15px 16px 39px; border-top: 1px solid var(--line); }
.rf-k { margin-bottom: 3px; color: var(--faint); font-size: 10.5px; font-weight: 800; letter-spacing: 0; text-transform: uppercase; }
.rf-v { color: var(--ink-2); font-size: 13px; line-height: 1.5; }
.r-field-grid { display: grid; grid-template-columns: repeat(3, 1fr); gap: 12px; }
.sev-badge, .tag { display: inline-block; border-radius: var(--r-pill); padding: 3px 9px; font-size: 11px; font-weight: 800; letter-spacing: 0; text-transform: uppercase; white-space: nowrap; }
.b-crit, .high { color: var(--crit); background: var(--crit-soft); }
.b-high { color: var(--high); background: var(--high-soft); }
.b-med, .medium { color: var(--med); background: var(--med-soft); }
.b-low, .ready, .low { color: var(--low); background: var(--low-soft); }
.report-stack { display: grid; gap: 14px; }
.reports, .reports-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 10px; }
.report, .report-card {
  display: flex;
  flex-direction: column;
  gap: 11px;
  border: 1px solid var(--line);
  border-radius: var(--r-sm);
  background: var(--surface);
  box-shadow: var(--shadow-sm);
  padding: 16px 17px 15px;
  color: var(--ink);
}
.report:hover, .report-card:hover { border-color: var(--accent); box-shadow: var(--shadow-md); text-decoration: none; transform: translateY(-1px); }
.report.empty, .report-card.empty { background: var(--surface-2); border-style: dashed; box-shadow: none; }
.report-primary {
  border-color: var(--accent);
  background: var(--surface);
  box-shadow: var(--shadow-md);
}
.report-primary.empty { border-style: solid; border-color: var(--high-line); background: var(--high-soft); }
.report-subhead {
  display: flex;
  align-items: flex-end;
  justify-content: space-between;
  gap: 16px;
  padding: 5px 1px 0;
}
.report-subhead h3 { color: var(--ink); font-size: 15px; font-weight: 800; }
.report-subhead p { margin-top: 3px; color: var(--muted); font-size: 12px; }
.report-subhead span { color: var(--muted); font-size: 12px; white-space: nowrap; }
.rp-top { display: flex; align-items: flex-start; justify-content: space-between; gap: 12px; }
.rp-head { display: grid; gap: 3px; min-width: 0; }
.rp-role { color: var(--muted); font-family: var(--mono); font-size: 10px; font-weight: 800; letter-spacing: 0; text-transform: uppercase; }
.rp-name, .report-title { color: var(--ink); font-size: 15.5px; font-weight: 800; }
.rp-count, .report-count, .rp-open-top { color: var(--muted); background: var(--surface-3); border-radius: var(--r-pill); padding: 3px 9px; font-family: var(--mono); font-size: 10px; font-weight: 800; text-transform: uppercase; white-space: nowrap; }
.rp-open-top { border: 1px solid var(--line-2); color: var(--accent); background: var(--surface); }
.rp-open-top:hover { border-color: var(--accent); color: var(--accent-ink); text-decoration: none; }
.rp-purpose { color: var(--muted); font-size: 12px; line-height: 1.45; }
.rp-prev { color: var(--ink-2); font-size: 13px; line-height: 1.55; }
.report-command {
  display: block;
  width: fit-content;
  max-width: 100%;
  overflow-wrap: anywhere;
}
.report-history { display: grid; gap: 6px; border-top: 1px solid var(--line); padding-top: 9px; }
.rh-label { color: var(--faint); font-size: 10.5px; font-weight: 800; letter-spacing: 0; text-transform: uppercase; }
.rh-item { display: grid; grid-template-columns: 78px minmax(0, 1fr); gap: 9px; color: var(--ink-2); font-size: 11.5px; line-height: 1.35; }
.rh-item:hover { color: var(--accent); text-decoration: none; }
.rh-item span { color: var(--muted); font-family: var(--mono); }
.rh-item strong { min-width: 0; overflow: hidden; color: inherit; font-weight: 750; text-overflow: ellipsis; white-space: nowrap; }
.rh-more { color: var(--muted); font-size: 11px; }
.rp-foot { display: flex; align-items: center; justify-content: space-between; gap: 10px; margin-top: auto; padding-top: 4px; }
.rp-date, .report-date { color: var(--muted); font-family: var(--mono); font-size: 11.5px; }
.rp-open { color: var(--accent); font-size: 12.5px; font-weight: 800; }
.report-list { display: grid; gap: 8px; margin: 0; padding: 0; list-style: none; }
.report-link { display: grid; grid-template-columns: 94px minmax(0, 1fr); gap: 10px; align-items: baseline; }
.core { display: grid; grid-template-columns: repeat(5, 1fr); gap: var(--gap); }
.core-card {
  display: flex;
  flex-direction: column;
  gap: 7px;
  color: var(--ink);
  border: 1px solid var(--line);
  border-radius: var(--r-md);
  background: var(--surface);
  box-shadow: var(--shadow-sm);
  padding: 15px;
  transition: .15s;
}
.core-card:hover { border-color: var(--accent); box-shadow: var(--shadow-md); transform: translateY(-1px); text-decoration: none; }
.cc-ico { width: 30px; height: 30px; display: grid; place-items: center; border-radius: 8px; background: var(--accent-soft); color: var(--accent); font-weight: 800; }
.cc-name, .core-title { color: var(--ink); font-size: 14px; font-weight: 800; margin-top: 3px; }
.cc-desc, .core-desc, .core-file { color: var(--muted); font-size: 12px; line-height: 1.45; }
.cc-stat { margin-top: auto; padding-top: 8px; color: var(--accent); font-size: 11.5px; font-weight: 800; }
.missing-card { background: var(--surface-2); border-style: dashed; }
.learn, .learning-grid { display: grid; grid-template-columns: 280px 1fr; gap: var(--gap); align-items: start; }
.learn-panel, .learning-card {
  display: block;
  color: var(--ink);
  border: 1px solid var(--line);
  border-radius: var(--r-md);
  background: var(--surface);
  box-shadow: var(--shadow-sm);
  padding: 17px;
}
.learn-panel:hover, .learning-card:hover { border-color: var(--accent); text-decoration: none; }
.lp-h, .learning-title { color: var(--ink); font-size: 14px; font-weight: 800; }
.lp-sub, .learning-meta { color: var(--muted); font-size: 12px; margin-top: 4px; }
.learn-stats, .summary, .grid { display: grid; grid-template-columns: repeat(3, 1fr); gap: 10px; margin: 16px 0 24px; }
.learn-stats .ls, .metric { background: var(--surface); border: 1px solid var(--line); border-left: 4px solid var(--accent); border-radius: var(--r-sm); padding: 12px 12px 11px; text-align: left; box-shadow: var(--shadow-sm); }
.learn-stats b, .metric .value, .metric strong { display: block; color: var(--ink); font-family: var(--display); font-size: 27px; font-weight: 700; line-height: 1; }
.learn-stats span, .metric .label, .metric span { color: var(--muted); font-family: var(--mono); font-size: 10.5px; font-weight: 800; letter-spacing: 0; text-transform: uppercase; }
.metric .detail { display: block; margin-top: 4px; color: var(--muted); font-size: 12px; text-transform: none; }
.mastery { margin-top: 6px; }
.m-bar { height: 7px; overflow: hidden; background: var(--surface-3); border-radius: var(--r-pill); }
.m-fill { height: 100%; background: var(--accent); border-radius: var(--r-pill); }
.m-txt { margin-top: 6px; color: var(--muted); font-size: 11.5px; }
.learn-items { columns: 2; column-gap: var(--gap); }
.li-card { break-inside: avoid; margin-bottom: 10px; border: 1px solid var(--line); border-radius: var(--r-sm); background: var(--surface); padding: 11px 13px; }
.li-new { color: var(--accent); font-size: 9.5px; font-weight: 800; letter-spacing: 0; text-transform: uppercase; }
.li-t { color: var(--ink); font-size: 12.5px; font-weight: 800; }
.li-d { margin-top: 4px; color: var(--muted); font-size: 11.5px; line-height: 1.45; }
.cmd-groups, .command-groups { display: grid; gap: 22px; }
.cmd-group-h, .command-group h3 { margin-bottom: 12px; color: var(--muted); font-size: 13px; font-weight: 800; letter-spacing: 0; text-transform: uppercase; }
.cmd-grid, .copy-grid { display: grid; grid-template-columns: 1fr 1fr; gap: var(--gap); }
.cmd-card {
  border: 1px solid var(--line);
  border-radius: var(--r-md);
  background: var(--surface);
  box-shadow: var(--shadow-sm);
  padding: 14px 15px;
}
.cc-top { display: flex; align-items: flex-start; justify-content: space-between; gap: 12px; }
.cc-ttl { color: var(--ink); font-size: 13.5px; font-weight: 800; }
.cc-kind { color: var(--faint); font-size: 10px; font-weight: 800; letter-spacing: 0; margin-top: 2px; text-transform: uppercase; }
.copy-btn {
  flex: 0 0 auto;
  display: inline-flex;
  align-items: center;
  gap: 6px;
  border: 1px solid var(--line-2);
  background: var(--surface-2);
  color: var(--ink-2);
  border-radius: var(--r-sm);
  padding: 6px 11px;
  font-size: 12px;
  font-weight: 800;
  transition: .12s;
}
.copy-btn:hover { border-color: var(--accent); color: var(--accent); }
.copy-btn.ok { background: var(--good-soft); border-color: var(--good-line); color: var(--good); }
.cmd-pre, pre {
  margin: 11px 0 0;
  max-height: 160px;
  overflow: auto;
  white-space: pre-wrap;
  overflow-wrap: anywhere;
  border: 1px solid var(--line);
  border-radius: var(--r-sm);
  background: var(--surface-2);
  color: var(--ink-2);
  padding: 11px 12px;
  font-family: var(--mono);
  font-size: 12px;
  line-height: 1.5;
}
.copy-status { display: block; min-height: 18px; margin-top: 7px; color: var(--good); font-size: 13px; }
.breadcrumbs { display: flex; align-items: center; flex-wrap: wrap; gap: 7px; margin-bottom: 12px; color: var(--muted); font-size: 13px; }
.breadcrumbs span { color: var(--muted); }
.table-filter {
  display: flex;
  align-items: flex-end;
  flex-wrap: wrap;
  gap: 9px;
  margin: 16px 0 10px;
  border: 1px solid var(--line);
  border-radius: var(--r-md);
  background: var(--surface-2);
  padding: 11px;
}
.filter-field { display: grid; gap: 4px; min-width: 150px; }
.filter-search-field { min-width: min(280px, 100%); flex: 1 1 260px; }
.filter-field span { color: var(--muted); font-size: 10.5px; font-weight: 800; text-transform: uppercase; }
.filter-field input, .filter-field select {
  min-height: 34px;
  border: 1px solid var(--line-2);
  border-radius: var(--r-sm);
  background: var(--surface);
  color: var(--ink);
  padding: 6px 9px;
  font-size: 13px;
}
.filter-clear {
  min-height: 34px;
  border: 1px solid var(--line-2);
  border-radius: var(--r-sm);
  background: var(--surface);
  color: var(--ink-2);
  padding: 0 11px;
  font-size: 12px;
  font-weight: 800;
}
.filter-clear:hover { border-color: var(--accent); color: var(--accent); }
.filter-count { margin-left: auto; color: var(--muted); font-family: var(--mono); font-size: 12px; line-height: 34px; }
.status-grid { display: grid; grid-template-columns: repeat(4, 1fr); gap: var(--gap); margin: 20px 0 24px; }
.status-card, .cadence-alert, .cadence-ok {
  border: 1px solid var(--line);
  border-radius: var(--r-md);
  background: var(--surface);
  box-shadow: var(--shadow-sm);
  padding: 14px;
}
.status-card span { display: block; color: var(--muted); font-size: 11px; font-weight: 800; text-transform: uppercase; }
.status-card strong { display: block; margin-top: 6px; color: var(--ink); font-size: 22px; }
.status-good, .cadence-ok { background: var(--good-soft); border-color: var(--good-line); }
.status-warn, .cadence-alert { background: var(--med-soft); border-color: var(--med-line); }
.status-danger { background: var(--crit-soft); border-color: var(--crit-line); }
.cadence-list { display: grid; gap: 10px; }
.cadence-alert code { display: block; margin-top: 8px; white-space: normal; overflow-wrap: anywhere; }
.current-read {
  margin: 8px 0 26px;
  border-left: 4px solid var(--accent);
  background: var(--surface-2);
  border-radius: var(--r-md);
  padding: 14px 16px;
}
.current-read h2 { color: var(--muted); font-size: 11px; font-weight: 800; letter-spacing: 0; text-transform: uppercase; }
.current-read p { margin-top: 5px; max-width: 980px; color: var(--ink-2); font-size: 14px; line-height: 1.55; }
.report-body {
  position: relative;
  max-width: 920px;
  margin: 0 auto;
}
.report-body::before {
  content: "";
  position: absolute;
  top: 0;
  bottom: 0;
  left: -34px;
  width: 2px;
  background: linear-gradient(var(--accent), var(--line) 42%, transparent);
}
.artifact-section { margin-top: 32px; border-top: 1px solid var(--line); padding-top: 24px; }
.artifact-section:first-of-type { margin-top: 0; border-top: 0; padding-top: 0; }
.artifact-section h2 {
  color: var(--ink);
  font-family: var(--display);
  font-size: 24px;
  font-weight: 700;
}
.artifact-note { margin: 8px 0 14px; color: var(--ink-2); font-size: 13px; line-height: 1.5; }
.artifact-list { display: grid; gap: 0; margin: 16px 0 26px; padding: 0; list-style: none; }
.artifact-list li {
  display: grid;
  gap: 3px;
  border-top: 1px solid var(--line);
  padding: 12px 0;
  color: var(--ink-2);
  font-size: 14px;
  line-height: 1.55;
}
.artifact-list li:first-child { border-top: 0; padding-top: 0; }
.artifact-list strong { color: var(--ink); font-weight: 800; }
.artifact-list span, .artifact-list em, .artifact-list small { display: block; margin-top: 3px; color: var(--muted); }
.artifact-list em, .artifact-list small { font-size: 13px; font-style: normal; }
.snapshot-tldr ul {
  display: grid;
  gap: 10px;
  margin: 14px 0 0;
  padding: 0;
  list-style: none;
}
.snapshot-tldr li {
  display: grid;
  grid-template-columns: 180px minmax(0, 1fr);
  gap: 18px;
  border-top: 1px solid var(--line);
  padding-top: 10px;
  color: var(--ink-2);
  font-size: 14px;
  line-height: 1.5;
}
.snapshot-tldr li:first-child { border-top: 0; padding-top: 0; }
.snapshot-tldr strong { color: var(--ink); font-weight: 850; }
.snapshot-communication-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 24px;
}
.snapshot-communication h3 { margin: 0 0 10px; color: var(--muted); font-size: 11px; font-weight: 800; letter-spacing: 0; text-transform: uppercase; }
.snapshot-communication ul { display: grid; gap: 10px; margin: 0; padding: 0; list-style: none; }
.snapshot-communication li { border-top: 1px solid var(--line); padding-top: 10px; color: var(--ink-2); font-size: 14px; line-height: 1.5; }
.snapshot-communication li:first-child { border-top: 0; padding-top: 0; }
.snapshot-communication strong { display: block; color: var(--ink); font-weight: 850; }
.snapshot-communication span, .snapshot-communication small { display: block; margin-top: 3px; color: var(--muted); }
.source-section > summary, .appendix-section > summary {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  cursor: pointer;
  list-style: none;
}
.source-section > summary::-webkit-details-marker, .appendix-section > summary::-webkit-details-marker { display: none; }
.source-section > summary span, .appendix-section > summary span { color: var(--ink); font-family: var(--display); font-size: 24px; font-weight: 700; }
.source-section > summary small, .appendix-section > summary small { color: var(--muted); font-family: var(--mono); font-size: 11px; font-weight: 800; text-transform: uppercase; }
.source-list, .appendix-body { margin-top: 16px; }
.report-body > p:first-child {
  max-width: none;
  color: var(--ink-2);
  font-size: 15px;
  line-height: 1.58;
}
.report-thin-evidence {
  display: flex;
  align-items: baseline;
  gap: 10px;
  margin: 0 0 18px;
  border: 1px solid var(--med-line);
  border-left: 5px solid var(--med);
  border-radius: var(--r-sm);
  background: var(--med-soft);
  padding: 10px 12px;
  color: var(--ink-2);
  font-size: 13px;
  line-height: 1.45;
}
.report-thin-evidence strong { color: var(--med); font-size: 11px; font-weight: 850; text-transform: uppercase; white-space: nowrap; }
.report-changes {
  margin: 0 0 10px;
  border: 1px solid var(--line);
  border-left: 5px solid var(--accent);
  border-radius: var(--r-sm);
  background: var(--surface);
  box-shadow: var(--shadow-sm);
  padding: 15px 16px 14px;
}
.report-changes h2 { color: var(--ink); font-size: 15px; font-weight: 850; letter-spacing: 0; }
.report-changes ul { display: grid; gap: 8px; margin: 10px 0 0; padding: 0; list-style: none; }
.report-changes li { color: var(--ink-2); font-size: 13px; line-height: 1.45; }
.report-changes li strong { color: var(--accent-ink); font-family: var(--mono); font-size: 11px; font-weight: 800; text-transform: uppercase; }
.report-attention {
  max-width: none;
  margin: 18px 0 6px;
  border-top: 1px solid var(--line);
  padding-top: 15px;
}
.attention-kicker { color: var(--muted); font-family: var(--mono); font-size: 11px; font-weight: 800; letter-spacing: 0; text-transform: uppercase; }
.report-attention ul { display: grid; gap: 7px; margin: 8px 0 0; padding: 0; list-style: none; }
.report-attention li { display: grid; grid-template-columns: 132px minmax(0, 1fr); gap: 12px; color: var(--ink-2); font-size: 12.5px; line-height: 1.45; }
.report-attention li strong { color: var(--ink); font-size: 11px; font-weight: 800; text-transform: uppercase; }
.help-accordion { display: grid; gap: 10px; }
.help-panel {
  overflow: hidden;
  border: 1px solid var(--line);
  border-radius: var(--r-md);
  background: var(--surface);
  box-shadow: var(--shadow-sm);
}
.help-panel > summary {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  padding: 14px 16px;
  cursor: pointer;
  list-style: none;
  background: var(--surface);
}
.help-panel > summary::-webkit-details-marker { display: none; }
.help-panel > summary span { color: var(--ink); font-size: 14px; font-weight: 800; }
.help-panel > summary small { color: var(--muted); font-size: 12px; font-weight: 700; text-align: right; }
.help-panel[open] > summary { border-bottom: 1px solid var(--line); background: var(--surface-2); }
.help-panel-body { padding: 16px; }
.help-guide { display: grid; grid-template-columns: repeat(2, 1fr); gap: 12px 18px; }
.help-guide-row {
  display: grid;
  grid-template-columns: minmax(88px, .22fr) minmax(0, 1fr);
  gap: 8px 14px;
  align-items: start;
  padding: 10px 0;
  border-top: 1px solid var(--line);
}
.help-guide-row:first-child { border-top: 0; padding-top: 0; }
.help-guide-row h3 { color: var(--ink); font-size: 14px; font-weight: 800; }
.help-guide-row p { color: var(--ink-2); font-size: 12.5px; line-height: 1.45; }
.help-guide-row code { display: block; grid-column: 1 / -1; white-space: normal; overflow-wrap: anywhere; }
.command-reference table code { white-space: normal; overflow-wrap: anywhere; }
.prose { max-width: none; }
.prose h2, .prose h3, .prose h4 { margin-top: 28px; }
.prose p, .prose ul { max-width: 900px; margin-top: 12px; }
.empty-item, .no-results { color: var(--faint); font-size: 13px; }
.cell-empty { color: var(--faint); }
.no-results { border: 1px dashed var(--line-2); border-radius: var(--r-md); padding: 22px; text-align: center; }
.markdown-table { width: 100%; overflow-x: auto; }
.markdown-table table { min-width: 100%; }
.markdown-table tr[id] { scroll-margin-top: 24px; }
.markdown-table tr:target { outline: 3px solid var(--accent); outline-offset: -3px; box-shadow: inset 4px 0 0 var(--accent); }
.markdown-table tr:target td { background: var(--accent-soft); }
.registry-title-link { color: var(--ink); text-decoration: none; }
.registry-title-link:hover { color: var(--accent); text-decoration: none; }
.item-summary {
  display: grid;
  gap: 9px;
  max-width: 980px;
  margin: 2px 0 18px;
  border-left: 4px solid var(--accent);
  border-radius: var(--r-md);
  background: var(--surface-2);
  padding: 14px 16px;
}
.item-summary p { color: var(--ink-2); font-size: 14px; line-height: 1.55; }
.item-id { color: var(--muted); font-size: 11px; font-weight: 800; text-transform: uppercase; }
.item-meta-grid {
  display: grid;
  grid-template-columns: repeat(5, minmax(0, 1fr));
  gap: var(--gap);
  margin: 0 0 22px;
}
.item-meta {
  min-width: 0;
  border: 1px solid var(--line);
  border-radius: var(--r-md);
  background: var(--surface);
  box-shadow: var(--shadow-sm);
  padding: 13px 14px;
}
.item-meta > span:first-child {
  display: block;
  margin-bottom: 6px;
  color: var(--muted);
  font-size: 10.5px;
  font-weight: 800;
  text-transform: uppercase;
}
.item-meta strong { display: block; color: var(--ink); font-size: 13.5px; line-height: 1.35; }
.item-field-grid { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: var(--gap); }
.item-field {
  border-top: 1px solid var(--line);
  padding-top: 14px;
}
.item-field h2 { color: var(--muted); font-size: 11px; font-weight: 800; text-transform: uppercase; }
.item-field p { margin-top: 6px; color: var(--ink-2); font-size: 14px; line-height: 1.55; }
.section-heading-line {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  gap: 14px;
}
.section-heading-line h2 { font-size: 20px; }
.section-heading-line span { color: var(--muted); font-size: 12px; font-weight: 800; }
.reference-list { display: grid; gap: 10px; margin-top: 14px; }
.reference-card {
  border: 1px solid var(--line);
  border-radius: var(--r-md);
  background: var(--surface);
  box-shadow: var(--shadow-sm);
  padding: 14px 15px;
}
.reference-top {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 14px;
}
.reference-top h3 { color: var(--ink); font-size: 14px; font-weight: 800; }
.reference-top p, .reference-card p { margin-top: 4px; color: var(--ink-2); font-size: 12.5px; line-height: 1.45; }
.reference-card p strong { color: var(--muted); font-size: 10.5px; text-transform: uppercase; }
.reference-link { flex: 0 0 auto; }
.reference-meta {
  display: flex;
  flex-wrap: wrap;
  gap: 6px 10px;
  margin: 8px 0 3px;
  color: var(--muted);
  font-size: 11px;
  font-weight: 800;
  text-transform: uppercase;
}
.source-footnote {
  display: flex;
  justify-content: flex-end;
  flex-wrap: wrap;
  gap: 8px 12px;
  margin-top: 18px;
  padding-top: 12px;
  border-top: 1px solid var(--line);
  color: var(--muted);
  font-size: 12px;
}
.source-footnote span { color: var(--muted); }
table { width: 100%; border-collapse: collapse; margin: 14px 0 22px; font-size: 14px; }
th, td { border: 1px solid var(--line); padding: 9px; text-align: left; vertical-align: top; }
th { background: var(--surface-3); color: var(--ink); }
code { border: 1px solid var(--line); border-radius: 6px; background: var(--surface-2); padding: 1px 5px; }
.app-footer {
  display: flex;
  justify-content: flex-end;
  margin-top: 34px;
  padding-top: 18px;
  border-top: 1px solid var(--line);
  color: var(--muted);
  font-size: 12px;
  font-weight: 800;
}
@media (max-width: 1040px) {
  .kpis { grid-template-columns: repeat(2, minmax(0, 1fr)); }
  .setup-list { grid-template-columns: repeat(3, 1fr); }
  .setup-item { border-bottom: 1px solid var(--line); }
  .core { grid-template-columns: repeat(3, 1fr); }
  .status-grid { grid-template-columns: repeat(2, 1fr); }
  .item-meta-grid { grid-template-columns: repeat(3, 1fr); }
}
@media (max-width: 860px) {
  .sticky-nav { grid-template-columns: minmax(0, 1fr) auto; padding: 8px 16px; }
  .sticky-actions .search { display: none; }
  .masthead { grid-template-columns: 1fr; }
  .masthead-mobile-tools { display: flex; }
  .masthead-side { align-items: stretch; }
  .util { justify-content: flex-end; }
  .search { width: 100%; }
  .today-grid { grid-template-columns: 1fr; }
  .today-col { border-right: 0; border-bottom: 1px solid var(--line); }
  .today-col:last-child { border-bottom: 0; }
  .reports, .reports-grid, .cmd-grid, .copy-grid, .learn, .learning-grid { grid-template-columns: 1fr; }
  .setup-summary { align-items: flex-start; flex-direction: column; }
  .setup-primary { width: 100%; text-align: center; }
  .report-attention li { grid-template-columns: 1fr; gap: 2px; }
  .report-thin-evidence { align-items: flex-start; flex-direction: column; gap: 3px; }
  .snapshot-tldr li, .snapshot-communication-grid { grid-template-columns: 1fr; }
  .help-guide { grid-template-columns: 1fr; }
  .help-guide-row { grid-template-columns: 1fr; gap: 6px; }
  .item-field-grid { grid-template-columns: 1fr; }
  .report-body { max-width: none; }
  .report-body::before { display: none; }
  h1.title { font-size: 34px; }
}
@media (max-width: 560px) {
  .app { padding: 24px 16px 70px; }
  .kpis, .core, .status-grid, .summary, .grid, .item-meta-grid { grid-template-columns: 1fr; }
  .report-subhead { align-items: flex-start; flex-direction: column; gap: 4px; }
  .setup-list { grid-template-columns: 1fr; }
  .setup-item { min-height: auto; border-right: 0; border-bottom: 1px solid var(--line); }
  .setup-page-list .setup-item { grid-template-columns: auto minmax(0, 1fr); }
  .setup-page-list .setup-action { grid-column: 2; margin-top: 4px; }
  .help-panel > summary { align-items: flex-start; flex-direction: column; }
  .help-panel > summary small { text-align: left; }
  .app-footer { justify-content: flex-start; }
  .r-field-grid { grid-template-columns: 1fr; }
  .risk > summary { grid-template-columns: auto 1fr; }
  .r-right { grid-column: 2; justify-content: space-between; }
  .sec-title { white-space: normal; }
  .learn-items { columns: 1; }
  .reference-top { flex-direction: column; }
  h1.title { font-size: 31px; }
}
@media print {
  .sticky-nav, .masthead-side, .toolbar { display: none !important; }
  body { background: #fff; }
  .app { max-width: none; }
}
"""


def base_css() -> str:
    return command_center_css()


def refresh_script() -> str:
    return """
<script>
(() => {
  const $ = (selector, root = document) => root.querySelector(selector);
  const $$ = (selector, root = document) => Array.from(root.querySelectorAll(selector));

  function escapeHtml(value) {
    return String(value || '').replace(/[&<>"']/g, (char) => ({
      '&': '&amp;',
      '<': '&lt;',
      '>': '&gt;',
      '"': '&quot;',
      "'": '&#39;',
    }[char]));
  }

  function normalizedTerms(value) {
    return String(value || '').toLowerCase().split(/\\s+/).filter((term) => term.length > 1);
  }

  function setTheme(theme) {
    document.documentElement.setAttribute('data-theme', theme);
    try { localStorage.setItem('dzcto-theme', theme); } catch (error) {}
    $$('[data-theme-label]').forEach((label) => {
      label.textContent = theme === 'dark' ? 'Light' : 'Dark';
    });
  }

  try {
    setTheme(localStorage.getItem('dzcto-theme') || 'light');
  } catch (error) {
    setTheme('light');
  }

  $$('[data-theme-toggle]').forEach((button) => {
    button.addEventListener('click', () => {
      setTheme(document.documentElement.getAttribute('data-theme') === 'dark' ? 'light' : 'dark');
    });
  });

  async function copyText(text) {
    if (navigator.clipboard && window.isSecureContext) {
      try {
        await navigator.clipboard.writeText(text);
        return true;
      } catch (error) {}
    }
    const textarea = document.createElement('textarea');
    textarea.value = text;
    textarea.setAttribute('readonly', '');
    textarea.style.position = 'fixed';
    textarea.style.left = '-9999px';
    document.body.appendChild(textarea);
    textarea.focus();
    textarea.select();
    textarea.setSelectionRange(0, textarea.value.length);
    const ok = document.execCommand('copy');
    textarea.remove();
    return ok;
  }

  document.addEventListener('click', async (event) => {
    const copyButton = event.target.closest('[data-copy-target]');
    if (!copyButton) return;
    const target = document.getElementById(copyButton.dataset.copyTarget);
    const copyStatus = document.querySelector(`[data-copy-status-for="${copyButton.dataset.copyTarget}"]`);
    if (!target) return;
    try {
      const copied = await copyText(target.textContent.trim());
      copyButton.classList.toggle('ok', copied);
      copyButton.textContent = copied ? 'Copied' : 'Select';
      if (copyStatus) copyStatus.textContent = copied ? 'Copied' : 'Selected';
      if (!copied) {
        const range = document.createRange();
        range.selectNodeContents(target);
        const selection = window.getSelection();
        selection.removeAllRanges();
        selection.addRange(range);
      }
      setTimeout(() => {
        copyButton.classList.remove('ok');
        copyButton.textContent = 'Copy';
        if (copyStatus) copyStatus.textContent = '';
      }, 1600);
    } catch (error) {
      if (copyStatus) copyStatus.textContent = 'Select the text and copy manually';
    }
  });

  function scoreEntry(entry, terms) {
    const title = String(entry.title || '').toLowerCase();
    const kind = String(entry.kind || '').toLowerCase();
    const text = `${entry.title || ''} ${entry.kind || ''} ${entry.section || ''} ${entry.summary || ''} ${entry.text || ''}`.toLowerCase();
    let score = 0;
    for (const term of terms) {
      if (!text.includes(term)) return 0;
      if (title.startsWith(term)) score += 12;
      if (title.includes(term)) score += 8;
      if (kind.includes(term)) score += 4;
      score += 1;
    }
    return score;
  }

  async function loadSearchIndex(input) {
    if (input._dzctoIndex) return input._dzctoIndex;
    try {
      const response = await fetch(input.dataset.searchIndex || 'search-index.json');
      if (!response.ok) throw new Error('Search index unavailable');
      const payload = await response.json();
      input._dzctoIndex = Array.isArray(payload.entries) ? payload.entries : [];
    } catch (error) {
      input._dzctoIndex = [];
    }
    return input._dzctoIndex;
  }

  function prefixedUrl(prefix, url) {
    const value = String(url || 'index.html');
    if (/^(https?:|file:|\\/|#)/.test(value)) return value;
    return `${prefix || ''}${value}`;
  }

  function renderSearchResults(input, container, results, query) {
    if (!query.trim()) {
      container.hidden = true;
      container.innerHTML = '';
      return;
    }
    if (!results.length) {
      container.hidden = false;
      container.innerHTML = '<div class="search-result"><strong>No matches</strong><p>Try a report type, decision, risk, or stack term.</p></div>';
      return;
    }
    const prefix = input.dataset.searchPrefix || '';
    container.hidden = false;
    container.innerHTML = results.slice(0, 8).map(({ entry }) => `
      <a class="search-result" href="${escapeHtml(prefixedUrl(prefix, entry.url))}">
        <span>${escapeHtml([entry.kind, entry.date].filter(Boolean).join(' / '))}</span>
        <strong>${escapeHtml(entry.title)}</strong>
        <p>${escapeHtml(entry.summary)}</p>
      </a>
    `).join('');
  }

  function applyDashboardFilters(query) {
    const q = query.trim().toLowerCase();
    let visibleReports = 0;
    $$('.report[data-search-text], .report-card[data-search-text]').forEach((item) => {
      const visible = !q || item.dataset.searchText.includes(q);
      item.hidden = !visible;
      if (visible) visibleReports += 1;
    });
    const reportCount = $('[data-report-count]');
    if (reportCount && q) reportCount.textContent = `${visibleReports} matching`;
    if (q) {
      const reportSection = $('#sec-reports');
      if (reportSection) reportSection.open = true;
    }
  }

  document.querySelectorAll('[data-dzcto-search]').forEach((input) => {
    const search = input.closest('.search');
    const container = search?.querySelector('[data-dzcto-search-results]');
    const clear = search?.querySelector('[data-dzcto-search-clear]');
    if (!container) return;
    const runSearch = async () => {
      if (clear) clear.style.display = input.value ? 'block' : 'none';
      applyDashboardFilters(input.value);
      const terms = normalizedTerms(input.value);
      const entries = await loadSearchIndex(input);
      const results = entries
        .map((entry) => ({ entry, score: scoreEntry(entry, terms) }))
        .filter((result) => result.score > 0)
        .sort((a, b) => b.score - a.score);
      renderSearchResults(input, container, results, input.value);
    };
    input.addEventListener('input', runSearch);
    input.addEventListener('keydown', (event) => {
      if (event.key === 'Escape') {
        input.value = '';
        container.hidden = true;
        if (clear) clear.style.display = 'none';
        applyDashboardFilters('');
      }
    });
    if (clear) clear.addEventListener('click', () => {
      input.value = '';
      container.hidden = true;
      clear.style.display = 'none';
      applyDashboardFilters('');
      input.focus();
    });
  });

  function filterDatasetKey(key) {
    return `filter${String(key || '').replace(/(^|-)([a-z])/g, (_match, _sep, char) => char.toUpperCase())}`;
  }

  document.querySelectorAll('[data-table-filter-controls]').forEach((controls) => {
    const tableId = controls.dataset.tableFilterControls;
    const tableWrap = tableId ? document.getElementById(tableId) : null;
    if (!tableWrap) return;

    const rows = Array.from(tableWrap.querySelectorAll('tbody tr'));
    const search = controls.querySelector('[data-table-filter-search]');
    const selects = Array.from(controls.querySelectorAll('[data-table-filter-select]'));
    const clear = controls.querySelector('[data-table-filter-clear]');
    const count = controls.querySelector('[data-table-filter-count]');

    const applyTableFilters = () => {
      const query = String(search?.value || '').trim().toLowerCase();
      let visible = 0;
      rows.forEach((row) => {
        const text = String(row.dataset.filterText || '').toLowerCase();
        let show = !query || text.includes(query);
        selects.forEach((select) => {
          if (!show || !select.value) return;
          const rowValue = String(row.dataset[filterDatasetKey(select.dataset.tableFilterSelect)] || '');
          const rowValues = rowValue.split('|').map((value) => value.trim()).filter(Boolean);
          show = rowValues.includes(select.value);
        });
        row.hidden = !show;
        if (show) visible += 1;
      });
      if (count) count.textContent = `${visible} of ${rows.length} shown`;
    };

    if (search) search.addEventListener('input', applyTableFilters);
    selects.forEach((select) => select.addEventListener('change', applyTableFilters));
    if (clear) clear.addEventListener('click', () => {
      if (search) search.value = '';
      selects.forEach((select) => select.value = '');
      applyTableFilters();
      if (search) search.focus();
    });
    applyTableFilters();
  });

  function openSectionFromHash() {
    const id = decodeURIComponent(String(window.location.hash || '').replace(/^#/, ''));
    if (!id) return;
    const target = document.getElementById(id);
    const section = target?.matches('details.section') ? target : target?.closest('details.section');
    if (section) section.open = true;
  }

  window.addEventListener('hashchange', openSectionFromHash);
  openSectionFromHash();

  document.addEventListener('keydown', (event) => {
    const active = document.activeElement;
    const typing = active && ['INPUT', 'TEXTAREA', 'SELECT'].includes(active.tagName);
    if (event.key === 'Escape' && typing) {
      active.blur();
      return;
    }
    if (typing || event.metaKey || event.ctrlKey || event.altKey) return;
    if (event.key === '/') {
      const input = $('[data-dzcto-search]');
      if (input) {
        event.preventDefault();
        input.focus();
      }
      return;
    }
    if (event.key === 'd' || event.key === 'D') {
      setTheme(document.documentElement.getAttribute('data-theme') === 'dark' ? 'light' : 'dark');
      return;
    }
    if (event.key === 'e' || event.key === 'E') {
      const sections = $$('.section');
      const shouldOpen = sections.some((section) => !section.open);
      sections.forEach((section) => section.open = shouldOpen);
      return;
    }
    if (/^[1-5]$/.test(event.key)) {
      const section = $$('.section')[Number(event.key) - 1];
      if (section) {
        section.open = true;
        section.scrollIntoView({ behavior: 'smooth', block: 'start' });
      }
    }
  });

})();
</script>
"""


def write_html_page(path: Path, title: str, body: str, provenance: dict[str, Any]) -> None:
    path.write_text(
        f"""<!doctype html>
<html lang="en" data-theme="light">
  <head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <title>{esc(title)}</title>
    <style>{base_css()}</style>
  </head>
  <body>
    {body}
    {provenance_block(provenance)}
    {refresh_script()}
  </body>
</html>
""",
        encoding="utf-8",
    )


def render_report_page(title: str, date: str, kind: str, body: str, provenance: dict[str, Any], sticky_title: str, lede: str = "") -> str:
    safe_title = esc(title)
    # When the report carries a lead summary, it becomes the masthead deck and the
    # date drops to a small stamp; otherwise the date stays as the lede (legacy).
    lede_text = (lede or "").strip()
    subtitle = lede_text or date
    stamp = date if lede_text else ""
    content = f"""
    <div class="report-body">
      {body}
    </div>
"""
    return f"""<!doctype html>
<html lang="en" data-theme="light">
  <head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <title>{safe_title}</title>
    <style>{base_css()}</style>
  </head>
  <body>
    {page_shell(content, prefix="../../", eyebrow=f"{REPORT_FOLDERS[kind]} - Day Zero CTO", title=title, subtitle=subtitle, stamp=stamp, crumbs=[("Reports", "index.html#sec-reports"), (REPORT_FOLDERS[kind], None)], sticky_title=sticky_title)}
    {provenance_block(provenance)}
    {refresh_script()}
  </body>
</html>
"""


def report_title_from_data(data: dict[str, Any], fallback_path: Path) -> str:
    window = data.get("window") if isinstance(data.get("window"), dict) else {}
    start = text_value(window.get("start"))
    end = text_value(window.get("end"))
    if start and end:
        return f"CEO Report {start} to {end}"
    html_path = fallback_path.with_suffix(".html")
    if html_path.exists():
        return html_title(html_path)
    return title_label(report_name(fallback_path))


def refresh_existing_report_pages(wiki_root: Path, stable_title: str, *, report_folder: str = "ceo-updates") -> int:
    reports_dir = wiki_root / "reports" / report_folder
    if not reports_dir.exists():
        return 0

    refreshed = 0
    for json_path in sorted(reports_dir.glob("*.json")):
        if json_path.name == "data.json":
            continue
        report_path = json_path.with_suffix(".html")
        if not report_path.exists():
            continue
        data = read_json_file(json_path, None)
        if not isinstance(data, dict):
            print(f"dzcto: skipping report format refresh for {json_path.name} (unreadable JSON)", file=sys.stderr)
            continue

        structured_data = sanitize_current_report_data(dict(data))
        report_date = report_effective_date(json_path, structured_data) or report_run_date(report_path)
        previous_data: dict[str, Any] | None = None
        previous_date = ""
        change_notes: list[str] = []
        if report_folder == "ceo-updates":
            prior_path, previous_data, previous_date, change_notes = locate_prior_report(json_path, structured_data)
            previous_data = sanitize_prior_report_data(previous_data)
            structured_data["prior_report"] = prior_path.relative_to(wiki_root).as_posix() if prior_path else None
        body = render_structured_report(
            report_folder,
            structured_data,
            previous_data=previous_data,
            previous_date=previous_date,
            change_notes=change_notes,
        )
        title = report_title_from_data(structured_data, json_path)
        relative_path = report_path.relative_to(wiki_root).as_posix()
        provenance = provenance_payload(
            wiki_root,
            artifact_id=f"{report_folder}:{report_path.stem}",
            artifact_kind=report_folder,
            relative_path=relative_path,
            title=title,
            generated_at=utc_now(),
            source_hashes=collect_source_hashes([json_path]),
            extra={"reportDate": report_date, "formatRefresh": True},
        )
        report_path.write_text(
            render_report_page(title, report_date, report_folder, body, provenance, stable_title, lede=report_lead_summary(structured_data)),
            encoding="utf-8",
        )
        update_manifest(wiki_root, provenance)
        refreshed += 1
    return refreshed


def prune_manifest_report_artifacts(wiki_root: Path) -> None:
    manifest_path = sidecar_dir(wiki_root) / "manifest.json"
    manifest = read_json(manifest_path, {})
    artifacts = manifest.get("artifacts") if isinstance(manifest, dict) else None
    if not isinstance(artifacts, list):
        return
    pruned = []
    changed = False
    for artifact in artifacts:
        if not isinstance(artifact, dict):
            pruned.append(artifact)
            continue
        relative = str(artifact.get("relativePath") or "")
        if relative.startswith("reports/"):
            parts = relative.split("/")
            if len(parts) > 1 and parts[1] not in REPORT_FOLDERS:
                changed = True
                continue
        pruned.append(artifact)
    if changed:
        manifest["artifacts"] = pruned
        manifest["updatedAt"] = utc_now()
        write_json(manifest_path, manifest)


def render_index(wiki_root: Path, project_folder: Path, today: dt.date | None = None) -> None:
    core_dir = wiki_root / "core"
    reports_dir = wiki_root / "reports"
    ensure_sidecar(wiki_root, project_folder, "render-index")
    today = today or dt.date.today()

    config = project_config(wiki_root)
    strategy_path = core_dir / "STRATEGY.md"
    company = company_name(strategy_path, project_folder, config)
    description = company_description(strategy_path, config)
    stable_title = dashboard_title(company)
    prune_manifest_report_artifacts(wiki_root)
    repos = [str(item).strip() for item in (config.get("codeRepos", []) or []) if str(item).strip()]
    repo_count = len(repos)
    report_folder = "ceo-updates"
    report_label = ACTIVE_REPORT_FOLDERS[report_folder]
    report_links = sorted((reports_dir / report_folder).glob("*.html"), reverse=True)
    report_count = len(report_links)
    latest_href = report_links[0].relative_to(wiki_root).as_posix() if report_links else "#sec-reports"
    latest_date = report_run_date(report_links[0]) if report_links else "No reports yet"
    weekly_cadence = resolve_weekly_cadence_days(core_dir, report_folder)
    weekly_streak_count = weekly_streak(weekly_report_dates(reports_dir / report_folder), today, weekly_cadence)
    if weekly_streak_count == 0:
        weekly_streak_sub = "Start a weekly report"
    elif weekly_streak_count >= NORTH_STAR_STREAK_WEEKS:
        weekly_streak_sub = "North Star met"
    else:
        weekly_streak_sub = f"of {NORTH_STAR_STREAK_WEEKS} - North Star"
    weekly_defaults = config.get("weeklyReportDefaults") if isinstance(config.get("weeklyReportDefaults"), dict) else {}
    weekly_range = text_value(weekly_defaults.get("range")) or "not_configured"
    weekly_start = text_value(weekly_defaults.get("startDay")) or "Not set"
    weekly_end = text_value(weekly_defaults.get("endDay")) or "Not set"
    lookback = text_value(weekly_defaults.get("lookbackDays"))
    if weekly_range == "since_last_report":
        weekly_label = weekly_range
        weekly_kpi_value = "Since last"
    else:
        weekly_label = f"{weekly_range}; {weekly_start} to {weekly_end}"
        if lookback:
            weekly_label = f"{weekly_label}; {lookback} days"
        weekly_kpi_value = "Needed" if weekly_range == "not_configured" else f"{weekly_start[:3]} to {weekly_end[:3]}"
    tone = text_value(config.get("ceoReportTone")) or "direct, concise, business-facing, calm about risk, explicit about asks"
    artifact_dir = text_value(config.get("artifactDirectory")) or str(wiki_root)
    profile_name = profile_name_for_config(config, wiki_root)
    report_prompt_context = configured_report_prompt_context(config)

    def command_card(card_id: str, label: str, command: str) -> str:
        return copy_card(card_id, label, command, "Command")

    init_command_parts = [
        "dzcto init",
        "--artifacts-dir",
        shlex.quote(artifact_dir),
        "--profile",
        shlex.quote(profile_name),
        "--company-name",
        shlex.quote(company),
    ]
    if has_captured_company_description(strategy_path, config):
        init_command_parts.extend(["--company-description", shlex.quote(description)])

    weekly_prompt = exact_prompt(
        f"Run /dzcto-ceo-report-weekly for {company} using DZ CTO profile `{profile_name}`. Use the configured weekly defaults ({weekly_label}) and CEO tone guidance: {tone}.",
        project_folder,
        repos,
        report_prompt_context,
    )
    custom_prompt = exact_prompt(
        f"Run /dzcto-ceo-report for {company} using DZ CTO profile `{profile_name}`. Ask for a concrete start and end date, then write the CEO report using tone guidance: {tone}.",
        project_folder,
        repos,
        report_prompt_context,
    )
    prompt_items = [
        copy_card("ai-prompt-weekly-ceo-report", "/dzcto-ceo-report-weekly", weekly_prompt, "Prompt"),
        copy_card("ai-prompt-custom-ceo-report", "/dzcto-ceo-report", custom_prompt, "Prompt"),
    ]
    command_items = [
        command_card("local-command-init", "Refresh Init", " ".join(init_command_parts)),
        command_card("local-command-serve", "Serve Index", f'python3 -m http.server 8765 --directory "{artifact_dir}"'),
    ]

    if report_links:
        report_items = []
        for index, path in enumerate(report_links[:12]):
            href = path.relative_to(wiki_root).as_posix()
            title = html_title(path)
            date = report_run_date(path)
            summary = report_summary_for_path(path, 180) or title
            card_class = "report report-primary" if index == 0 else "report"
            report_items.append(
                f"""<a class="{card_class}" href="{esc(href)}" data-search-text="{search_text_attr(title, date, summary)}">
  <div class="rp-top">
    <div class="rp-head"><span class="rp-role">CEO report</span><span class="rp-name">{esc(title)}</span><span class="rp-date">{esc(date)}</span></div>
    <span class="rp-open-top">Open</span>
  </div>
  <p class="rp-prev">{esc(summary)}</p>
</a>"""
            )
        reports_html = f'<div class="reports reports-supporting">{"".join(report_items)}</div>'
    else:
        reports_html = f"""<article class="report report-primary empty" data-search-text="No CEO reports generated yet">
  <div class="rp-top">
    <div class="rp-head"><span class="rp-role">CEO report</span><span class="rp-name">{esc(report_label)}</span><span class="rp-date">No reports yet</span></div>
    <span class="rp-count">Start here</span>
  </div>
  <p class="rp-purpose">Run /dzcto-ceo-report-weekly for the default weekly window, or /dzcto-ceo-report for a custom date range.</p>
</article>"""

    generated_at = utc_now()
    provenance = provenance_payload(
        wiki_root,
        artifact_id="wiki-index",
        artifact_kind="wiki-index",
        relative_path="index.html",
        title=f"{company} Day Zero CTO CEO Reports",
        generated_at=generated_at,
    )
    content = f"""
  <div class="kpis">
    <a class="kpi" href="{esc(latest_href)}">
      <div class="k-label">CEO reports</div>
      <div class="k-val">{esc(report_count)}</div>
      <div class="k-sub">{esc(latest_date)}</div>
    </a>
    <div class="kpi" data-tone="{esc('good' if weekly_streak_count >= NORTH_STAR_STREAK_WEEKS else 'warn' if weekly_streak_count == 0 else 'info')}">
      <div class="k-label">Weekly streak</div>
      <div class="k-val">{esc(weekly_streak_count)}</div>
      <div class="k-sub">{esc(weekly_streak_sub)}</div>
    </div>
    <div class="kpi">
      <div class="k-label">Weekly default</div>
      <div class="k-val">{esc(weekly_kpi_value)}</div>
      <div class="k-sub">{esc(weekly_range)}</div>
    </div>
    <div class="kpi">
      <div class="k-label">Evidence repos</div>
      <div class="k-val">{esc(repo_count)}</div>
      <div class="k-sub">Read-only sources</div>
    </div>
  </div>

  <details class="section" id="sec-reports" open>
    <summary>
      <span class="chev" aria-hidden="true"></span>
      <span class="sec-num">01</span>
      <span class="sec-title">CEO Reports</span>
      <span class="sec-meta" data-report-count>{esc(pluralize(report_count, "report"))}</span>
    </summary>
    <div class="sec-body">
      {reports_html}
    </div>
  </details>

  <details class="section" id="sec-settings" open>
    <summary>
      <span class="chev" aria-hidden="true"></span>
      <span class="sec-num">02</span>
      <span class="sec-title">Defaults</span>
      <span class="sec-meta">CEO report settings</span>
    </summary>
    <div class="sec-body">
      <div class="reports reports-supporting">
        <article class="report">
          <div class="rp-top"><div class="rp-head"><span class="rp-role">Weekly range</span><span class="rp-name">{esc(weekly_label)}</span></div></div>
          <p class="rp-prev">Used by /dzcto-ceo-report-weekly.</p>
        </article>
        <article class="report">
          <div class="rp-top"><div class="rp-head"><span class="rp-role">Tone</span><span class="rp-name">CEO report voice</span></div></div>
          <p class="rp-prev">{esc(tone)}</p>
        </article>
      </div>
    </div>
  </details>

  <details class="section" id="sec-prompts">
    <summary>
      <span class="chev" aria-hidden="true"></span>
      <span class="sec-num">03</span>
      <span class="sec-title">Commands</span>
      <span class="sec-meta">copy prompts</span>
    </summary>
    <div class="sec-body">
      <div class="copy-grid">{''.join(prompt_items)}{''.join(command_items)}</div>
    </div>
  </details>
"""
    body = page_shell(
        content,
        eyebrow="CEO Reports - Day Zero CTO",
        title=dashboard_title(company),
        subtitle=description,
        stamp=f"Last updated {display_timestamp(generated_at)}",
        sticky_title=dashboard_title(company),
    )
    write_html_page(wiki_root / "index.html", dashboard_title(company), body, provenance)
    update_manifest(wiki_root, provenance)


LocatedSecretFinding = tuple[str, SecretFinding]


def child_secret_location(parent: str, key: str) -> str:
    if not parent:
        return key
    if key.startswith("["):
        return f"{parent}{key}"
    return f"{parent}.{key}"


def synthetic_secret_finding(rule: str, confidence: str = LOW_CONFIDENCE) -> SecretFinding:
    return SecretFinding(rule=rule, confidence=confidence, span=(0, 0), preview="<masked len=0>")


def sanitize_report_value(value: Any, location: str = "") -> tuple[Any, list[LocatedSecretFinding]]:
    findings: list[LocatedSecretFinding] = []
    if isinstance(value, dict):
        redacted: dict[Any, Any] = {}
        for key, item in value.items():
            key_text = str(key)
            redacted_key_text, key_findings = redact_text(key_text)
            location_key = redacted_key_text if key_findings else key_text
            child_location = child_secret_location(location, location_key)
            findings.extend((f"{child_location}<key>", finding) for finding in key_findings)

            sanitized_item, child_findings = sanitize_report_value(item, child_location)
            findings.extend(child_findings)
            output_key = redacted_key_text if key_findings else key

            if key_text in LOCAL_PATH_KEYS:
                findings.append((child_location, synthetic_secret_finding("local_path_key")))
                redacted[output_key] = redaction_placeholder("local_path")
            elif is_secret_key(key_text):
                findings.append((child_location, synthetic_secret_finding("secret_key")))
                redacted[output_key] = redaction_placeholder("secret_key")
            else:
                redacted[output_key] = sanitized_item
        return redacted, findings
    if isinstance(value, list):
        redacted_items = []
        for index, item in enumerate(value):
            child_location = child_secret_location(location, f"[{index}]")
            sanitized_item, child_findings = sanitize_report_value(item, child_location)
            redacted_items.append(sanitized_item)
            findings.extend(child_findings)
        return redacted_items, findings
    if isinstance(value, str):
        redacted_text, text_findings = redact_text(value)
        return redacted_text, [(location or "value", finding) for finding in text_findings]
    return value, findings


def print_secret_blocks(findings: list[LocatedSecretFinding], *, block_all: bool = False) -> None:
    blocked = [
        (location, finding)
        for location, finding in findings
        if block_all or finding.confidence == HIGH_CONFIDENCE
    ]
    for location, finding in blocked:
        print(
            f"dzcto: secret detected in {location}: rule={finding.rule} ({finding.preview})",
            file=sys.stderr,
        )
    if blocked:
        raise SystemExit(1)


def print_secret_redactions(findings: list[LocatedSecretFinding], *, label: str = "value(s)") -> None:
    if not findings:
        return
    rules = ", ".join(sorted({finding.rule for _location, finding in findings}))
    print(f"dzcto: redacted {len(findings)} {label}: {rules}", file=sys.stderr)


def enforce_safe_report_title(title: str) -> None:
    _redacted, findings = redact_text(title)
    print_secret_blocks([("title", finding) for finding in findings], block_all=True)


def sanitize_current_report_data(data: dict[str, Any]) -> dict[str, Any]:
    sanitized, findings = sanitize_report_value(data)
    print_secret_blocks(findings)
    print_secret_redactions([item for item in findings if item[1].confidence == LOW_CONFIDENCE])
    return sanitized


def sanitize_current_report_body(body: str) -> str:
    redacted, findings = redact_text(body)
    located = [(f"body@{finding.span[0]}", finding) for finding in findings]
    print_secret_blocks(located)
    print_secret_redactions([item for item in located if item[1].confidence == LOW_CONFIDENCE])
    return redacted


def sanitize_prior_report_data(data: dict[str, Any] | None) -> dict[str, Any] | None:
    if data is None:
        return None
    sanitized, findings = sanitize_report_value(data)
    print_secret_redactions(findings, label="prior-report value(s)")
    return sanitized


def emit_open_and_share(report_path: Path) -> None:
    """Print sharing guidance and best-effort open a rendered report."""
    print(f"dzcto: report ready to share: {report_path}", file=sys.stderr)
    print('dzcto: share as PDF: in the browser, press Cmd/Ctrl+P and choose "Save as PDF".', file=sys.stderr)
    if os.environ.get("DZCTO_NO_OPEN"):
        return
    try:
        # The default macOS backend is non-blocking; custom BROWSER commands may not be.
        opened = webbrowser.open(report_path.as_uri())
        if opened:
            print("dzcto: opened the report in the default browser", file=sys.stderr)
        else:
            print("dzcto: the default browser did not accept the report; open the path above manually", file=sys.stderr)
    except Exception as exc:  # pragma: no cover - backend failures are environment-specific
        print(f"dzcto: could not open the report in the default browser: {exc}", file=sys.stderr)


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description="Generate Day Zero CTO artifacts")
    parser.add_argument("--project", help="Project folder; creates/uses PATH/knowledge/wiki")
    parser.add_argument("--artifacts-dir", help="Folder that directly stores index.html, reports/, and .dzcto/")
    parser.add_argument("--profile", help="Named global profile in ~/.dzcto/config.json, such as getmusic")
    parser.add_argument("--home", help="Legacy: wiki root folder")
    parser.add_argument("--kind", choices=["ceo-updates"])
    parser.add_argument("--title")
    parser.add_argument("--date", help="Report date (YYYY-MM-DD); derived from the report JSON's window.end when omitted")
    parser.add_argument("--body-file", help="Legacy: raw HTML body file")
    parser.add_argument("--data-file", help="Structured JSON report data file")
    parser.add_argument("--open", action="store_true", help="Open the rendered report and print a share recipe")
    parser.add_argument("--init", action="store_true")
    parser.add_argument("--company-name", help="Company name to store in wiki metadata")
    parser.add_argument("--company-description", help="Short company description to store in wiki metadata")
    parser.add_argument("--company-url", help="Company website URL; used as context and optional description source")
    parser.add_argument("--report-prompt-context", help="Extra context appended to report and operating prompt cards")
    parser.add_argument("--weekly-range", help="Default CEO weekly report range, such as previous_completed_week or last_7_days")
    parser.add_argument("--weekly-start-day", help="Default weekly report start day, such as Monday")
    parser.add_argument("--weekly-end-day", help="Default weekly report end day, such as Sunday")
    parser.add_argument("--weekly-lookback-days", type=int, help="Default rolling lookback days for weekly CEO reports")
    parser.add_argument("--ceo-report-tone", help="Tone guidance for CEO reports")
    parser.add_argument("--no-save-preferences", action="store_true", help="Do not update ~/.dzcto/config.json during init")
    parser.add_argument("--no-switch-default", action="store_true", help="Update the named profile without making it the global default")
    parser.add_argument("--repo", action="append", default=[], help="Read-only code repository path; may be repeated")
    args = parser.parse_args(argv)

    if not args.project and not args.home and not args.artifacts_dir:
        default_artifacts_dir = default_artifacts_dir_for_profile(args.profile)
        if default_artifacts_dir:
            args.artifacts_dir = str(default_artifacts_dir)
        else:
            profile_hint = f" for profile {args.profile!r}" if args.profile else ""
            parser.error(f"--project, --artifacts-dir, or --home is required. Run dzcto init --artifacts-dir <path>{profile_hint} once to save preferences.")

    if args.artifacts_dir:
        wiki_root = Path(args.artifacts_dir).expanduser().resolve()
        if not args.init and not wiki_root.exists():
            raise SystemExit(
                f"--artifacts-dir path does not exist: {wiki_root}\n"
                f"  If the report workspace is new, run `dzcto init --artifacts-dir <path>` first."
            )
        project_folder = Path(args.project).expanduser().resolve() if args.project else wiki_root
    elif args.project:
        project_folder = Path(args.project).expanduser().resolve()
        if not project_folder.exists():
            raise SystemExit(
                f"--project path does not exist: {project_folder}\n"
                f"  --project must be the project FOLDER path (e.g. ~/Documents/Acme\\ CTO), not a company name.\n"
                f"  Use '.' if you are already inside the project folder."
            )
        if not project_folder.is_dir():
            raise SystemExit(
                f"--project must be a directory, got: {project_folder}\n"
                f"  --project must be the project FOLDER path (e.g. ~/Documents/Acme\\ CTO), not a company name."
            )
        wiki_root = project_folder / "knowledge" / "wiki"
        # A real simplified workspace has .dzcto/config.json written during init. A
        # directory that exists but lacks this file is almost certainly a ghost tree
        # created by a prior run that resolved a company name as a relative path.
        # (--init legitimately creates the workspace from scratch, so it is exempt.)
        if not args.init and not (sidecar_dir(wiki_root) / "config.json").exists():
            parent_wiki = project_folder.parent / "knowledge" / "wiki"
            hint = (
                f"  The parent folder '{project_folder.parent}' looks like the correct project folder."
                if (sidecar_dir(parent_wiki) / "config.json").exists()
                else "  If the project is new, run `dzcto init` on it first."
            )
            raise SystemExit(
                f"No Day Zero CTO workspace found at {wiki_root} (missing .dzcto/config.json).\n"
                f"  --project must be the project FOLDER path (e.g. ~/Documents/Acme\\ CTO), not a company name.\n"
                f"{hint}"
            )
    else:
        wiki_root = Path(args.home).expanduser().resolve()
        project_folder = (wiki_root / ".." / "..").resolve()

    if not args.init:
        if not args.kind:
            parser.error("--kind is required unless --init is used")
        if not args.title:
            parser.error("--title is required unless --init is used")
        enforce_safe_report_title(args.title)

    core_dir = wiki_root / "core"
    reports_dir = wiki_root / "reports"

    report_folder = args.kind or "ceo-updates"
    (reports_dir / report_folder).mkdir(parents=True, exist_ok=True)
    ensure_sidecar(wiki_root, project_folder, "init" if args.init else "generate-artifact")
    apply_init_metadata(
        wiki_root,
        project_folder,
        company_name_value=args.company_name,
        company_description_value=args.company_description,
        company_url=args.company_url,
        report_prompt_context=args.report_prompt_context,
        weekly_range=args.weekly_range,
        weekly_start_day=args.weekly_start_day,
        weekly_end_day=args.weekly_end_day,
        weekly_lookback_days=args.weekly_lookback_days,
        ceo_report_tone=args.ceo_report_tone,
        profile_name=args.profile,
        repos=args.repo,
    )
    if args.init and not args.no_save_preferences:
        saved_profile = save_global_preferences(wiki_root, project_folder, args.profile, set_default=not args.no_switch_default)
        args.profile = saved_profile
    company = company_name(core_dir / "STRATEGY.md", project_folder, project_config(wiki_root))
    stable_title = dashboard_title(company)

    if args.init:
        refreshed = refresh_existing_report_pages(wiki_root, stable_title, report_folder=report_folder)
        if refreshed:
            print(f"dzcto: refreshed {pluralize(refreshed, 'existing report')} with the current report format", file=sys.stderr)

    written_report: Path | None = None
    if not args.init:
        report_sources: list[Path] = []
        structured_data: dict[str, Any] | None = None
        body = ""
        if args.data_file:
            data_path = Path(args.data_file).expanduser()
            report_sources.append(data_path)
            data = json.loads(data_path.read_text(encoding="utf-8"))
            if not isinstance(data, dict):
                raise SystemExit("--data-file must contain a JSON object")
            structured_data = data
        elif args.body_file:
            body_path = Path(args.body_file).expanduser()
            report_sources.append(body_path)
            body = body_path.read_text(encoding="utf-8")
        else:
            # No explicit data or body source — auto-load data.json from the report
            # folder if it exists so that `dzcto artifact --kind X --title Y` works
            # without always needing an explicit --data-file flag.
            auto_data_path = reports_dir / args.kind / "data.json"
            if auto_data_path.exists():
                data = json.loads(auto_data_path.read_text(encoding="utf-8"))
                if isinstance(data, dict):
                    report_sources.append(auto_data_path)
                    structured_data = data
                else:
                    body = sys.stdin.read()
            else:
                body = sys.stdin.read()

        report_date = args.date or dt.date.today().isoformat()
        if structured_data is not None:
            if args.kind == "ceo-updates":
                # Stamp renderer-owned metadata before sanitizing and validating so
                # warnings reflect what actually ships (company is documented as
                # "filled from the profile when absent").
                structured_data.setdefault("schema_version", CEO_REPORT_SCHEMA_VERSION)
                structured_data.setdefault("generated_at", utc_now())
                structured_data.setdefault("company", company)
            structured_data = sanitize_current_report_data(structured_data)
            if not cited_evidence_sources(structured_data):
                print(
                    "dzcto: no cited evidence sources; report ships with thin evidence "
                    "(add sources[] to make claims traceable)",
                    file=sys.stderr,
                )
            if args.kind == "ceo-updates":
                for warning in validate_ceo_report(structured_data):
                    print(f"dzcto: ceo-report schema warning: {warning}", file=sys.stderr)
                window = structured_data.get("window")
                window_end = date_value(window.get("end")) if isinstance(window, dict) else None
                if window_end:
                    if args.date and args.date != window_end.isoformat():
                        print(
                            f"dzcto: --date {args.date} disagrees with window.end {window_end.isoformat()}; using window.end",
                            file=sys.stderr,
                        )
                    report_date = window_end.isoformat()
        else:
            body = sanitize_current_report_body(body)

        slug = slugify(f"{report_date} {args.title}")
        report_path = reports_dir / args.kind / f"{slug}.html"

        if structured_data is not None:
            previous_data: dict[str, Any] | None = None
            previous_date = ""
            change_notes: list[str] = []
            if args.kind == "ceo-updates":
                prior_path, previous_data, previous_date, change_notes = locate_prior_report(
                    report_path.with_suffix(".json"), structured_data
                )
                previous_data = sanitize_prior_report_data(previous_data)
                structured_data["prior_report"] = prior_path.relative_to(wiki_root).as_posix() if prior_path else None
            body = render_structured_report(
                args.kind,
                structured_data,
                previous_data=previous_data,
                previous_date=previous_date,
                change_notes=change_notes,
            )

        relative_path = report_path.relative_to(wiki_root).as_posix()
        provenance = provenance_payload(
            wiki_root,
            artifact_id=f"{args.kind}:{slug}",
            artifact_kind=args.kind,
            relative_path=relative_path,
            title=args.title,
            generated_at=utc_now(),
            source_hashes=collect_source_hashes(report_sources),
            extra={"reportDate": report_date},
        )
        report_path.write_text(render_report_page(args.title, report_date, args.kind, body, provenance, stable_title, lede=report_lead_summary(structured_data)), encoding="utf-8")
        if structured_data is not None:
            write_json(report_path.with_suffix(".json"), structured_data)
            write_json(reports_dir / args.kind / "data.json", structured_data)
        update_manifest(wiki_root, provenance)
        written_report = report_path

    render_index(wiki_root, project_folder)
    print(written_report or wiki_root / "index.html")
    if written_report and args.open:
        emit_open_and_share(written_report)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))

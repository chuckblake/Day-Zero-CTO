#!/usr/bin/env python3
"""Generate Day Zero CTO wiki indexes and report artifacts."""

from __future__ import annotations

import argparse
import datetime as dt
import html
import json
import re
import sys
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

from dzcto_common import (
    TOOL_VERSION,
    ensure_sidecar,
    provenance_block,
    provenance_payload,
    read_json,
    sha256_text,
    sidecar_dir,
    source_hashes as collect_source_hashes,
    update_manifest,
    utc_now,
    write_json,
)


REPORT_FOLDERS = {
    "tech-stack": "Tech Stack",
    "engineering-risk": "Engineering Risk",
    "weekly-reviews": "Weekly Reviews",
    "ceo-updates": "CEO Updates",
}

RISK_SIGNAL_REPORT_FIELDS = {
    "tech-stack": ("risks_watchpoints", "risks", "watchpoints"),
    "engineering-risk": ("top_risks", "risks", "watchpoints"),
    "weekly-reviews": ("risks",),
    "ceo-updates": ("risks_blockers", "risks", "blockers"),
}

DECISION_SIGNAL_REPORT_FIELDS = {
    "weekly-reviews": ("decisions_needed", "decisions"),
    "ceo-updates": ("asks_decisions", "asks", "decisions"),
    "engineering-risk": ("decisions", "decision_points"),
    "tech-stack": ("decisions", "decision_points"),
}

RISK_REGISTRY_SCHEMA_VERSION = "1.0"
RISK_REGISTRY_RELATIVE_PATH = "risks/registry.json"
RISK_ACTIVE_STATUSES = {"active", "open", "monitoring", "needs_evidence", "punted"}
DECISION_REGISTRY_SCHEMA_VERSION = "1.0"
DECISION_REGISTRY_RELATIVE_PATH = "decisions/registry.json"

THEME_PATTERNS = [
    ("AI accuracy", r"\b(ai|llm|model|claude|eval|accuracy|predicate|prompt)\b"),
    ("security and privacy", r"\b(security|privacy|phi|hipaa|soc|compliance|csp|sentry|posthog|audit)\b"),
    ("vendor dependency", r"\b(vendor|reducto|stripe|anthropic|s3|third[- ]party|outage|credit)\b"),
    ("Rails infrastructure", r"\b(rails|solid|queue|cache|cable|postgres|redis|kamal|deploy|dependency)\b"),
    ("product readiness", r"\b(beta|launch|customer|gtm|billing|user|channel|tpa|employer)\b"),
    ("team and process", r"\b(team|owner|founder|hiring|bus factor|runbook|process|cadence)\b"),
]

TABLE_FILTER_PROFILES = {
    "decisions": [
        ("date", "Date", ("date", "decision_date", "decided", "when")),
        ("owner", "Owner", ("owner", "responsible")),
        ("options", "Options", ("options_considered", "options", "alternatives")),
        ("status", "Revisit", ("revisit_trigger", "revisit", "needed_by", "due", "status")),
    ],
    "risks": [
        ("owner", "Owner", ("owner", "responsible", "owner_horizon")),
        ("source", "Source", ("source", "sources", "origin", "report", "reported_from")),
        ("status", "Severity / Likelihood", ("status", "severity", "priority", "likelihood")),
        ("date", "Review", ("review", "review_date", "next_review", "due", "horizon", "needed_by")),
    ],
    "risk-signals": [
        ("status", "Status", ("status",)),
        ("source", "Source", ("source",)),
        ("severity", "Severity", ("severity",)),
    ],
}

CORE_DOCS = [
    "STRATEGY.md",
    "TEAM.md",
    "OPERATING_CADENCE.md",
    "DECISIONS.md",
    "RISKS.md",
]

CORE_DOC_META = {
    "STRATEGY.md": ("Strategy", "Stage, thesis, goals, constraints, and non-goals."),
    "TEAM.md": ("Team", "People, roles, ownership, and open questions."),
    "OPERATING_CADENCE.md": ("Operating Cadence", "Reviews, updates, planning rhythm, and ceremonies."),
    "DECISIONS.md": ("Decisions", "Durable choices, rationale, owners, and revisit triggers."),
    "RISKS.md": ("Risks", "Risk register, mitigations, owners, and review dates."),
}

# Skill an agent should run to populate each core doc when it is still empty.
CORE_DOC_EMPTY_ACTION = {
    "DECISIONS.md": "day-zero-cto:review-decisions",
    "RISKS.md": "day-zero-cto:review-risks",
}


CORE_DOC_HTML = {
    "STRATEGY.md": "strategy.html",
    "TEAM.md": "team.html",
    "OPERATING_CADENCE.md": "operating-cadence.html",
    "DECISIONS.md": "decisions.html",
    "RISKS.md": "risks.html",
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


def project_config(wiki_root: Path) -> dict[str, Any]:
    value = read_json(sidecar_dir(wiki_root) / "config.json", {})
    return value if isinstance(value, dict) else {}


def company_name(strategy_path: Path, project_folder: Path, config: dict[str, Any] | None = None) -> str:
    if strategy_path.exists():
        for line in strategy_path.read_text(encoding="utf-8").splitlines():
            if line.startswith("# "):
                title = re.sub(r"\s+Strategy$", "", line[2:].strip(), flags=re.I)
                return title
    if config and str(config.get("companyName") or "").strip():
        return str(config["companyName"]).strip()
    return project_folder.name


def company_description(strategy_path: Path, config: dict[str, Any] | None = None) -> str:
    paragraph = (
        first_markdown_paragraph(markdown_section(strategy_path, "Product Thesis"))
        or first_markdown_paragraph(markdown_section(strategy_path, "Company"))
        or first_markdown_paragraph(markdown_section(strategy_path, "Stage"))
    )
    if paragraph and plain_markdown(paragraph).lower() in {"unknown", "tbd", "to be determined"}:
        paragraph = None
    configured = str((config or {}).get("companyDescription") or "").strip()
    fallback = "Company context has not been captured yet. Add a Product Thesis section to the Strategy source file to enrich this summary."
    return plain_markdown(paragraph or configured or fallback)


def dashboard_title(company: str) -> str:
    return f"{company} Day Zero CTO"


def has_real_value(value: Any) -> bool:
    if value is None:
        return False
    return str(value).strip().lower() not in UNKNOWN_VALUES


def has_captured_company_description(strategy_path: Path, config: dict[str, Any] | None = None) -> bool:
    paragraph = (
        first_markdown_paragraph(markdown_section(strategy_path, "Product Thesis"))
        or first_markdown_paragraph(markdown_section(strategy_path, "Company"))
        or first_markdown_paragraph(markdown_section(strategy_path, "Stage"))
    )
    if has_real_value(plain_markdown(paragraph)):
        return True
    return has_real_value((config or {}).get("companyDescription"))


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
    repos: list[str] | None = None,
) -> None:
    if not any([company_name_value, company_description_value, company_url, report_prompt_context, repos]):
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
    if repos:
        existing = [str(item) for item in config.get("codeRepos", []) if str(item).strip()]
        for repo in repos:
            value = str(Path(repo).expanduser()).strip()
            if value and value not in existing:
                existing.append(value)
        config["codeRepos"] = existing
    write_json(config_path, config)

    strategy_path = wiki_root / "core" / "STRATEGY.md"
    if not strategy_path.exists() and (company_name_value or description or company_url):
        name = company_name_value or project_folder.name
        source_line = f"\nSource: {company_url}\n" if company_url else ""
        strategy_path.write_text(
            f"""# {name} Strategy

## Company

{description or "Unknown"}
{source_line}
## Stage

Unknown

## Product Thesis

{description or "Unknown"}

## Current Goals

Unknown

## Constraints

Unknown

## Non-Goals

Unknown
""",
            encoding="utf-8",
        )


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


def latest_report_date(reports_dir: Path, folder: str) -> dt.date | None:
    dates: list[dt.date] = []
    for path in (reports_dir / folder).glob("*.html"):
        match = re.match(r"^(\d{4}-\d{2}-\d{2})-", path.name)
        if not match:
            continue
        try:
            dates.append(dt.date.fromisoformat(match.group(1)))
        except ValueError:
            pass
    return max(dates) if dates else None


def cadence_alerts(cadence_rules: list[dict[str, Any]], reports_dir: Path, today: dt.date) -> list[dict[str, Any]]:
    alerts: list[dict[str, Any]] = []
    for rule in cadence_rules:
        latest = latest_report_date(reports_dir, rule["folder"])
        if latest:
            due_date = latest + dt.timedelta(days=rule["interval_days"] + rule["grace_days"])
            if today < due_date:
                continue
            reason = f"Last run {latest.isoformat()}; due {due_date.isoformat()}."
        else:
            due_date = today
            reason = f"No {rule['label']} report has been generated yet."

        alert = dict(rule)
        alert.update({"latest_date": latest, "due_date": due_date, "reason": reason})
        alerts.append(alert)
    return alerts


def display_command(command: str) -> str:
    text = re.sub(
        r"\s*Use project folder `[^`]+`(?:\s+and read-only code repo `[^`]+`)?\.?",
        "",
        command or "",
        flags=re.I,
    )
    text = re.sub(r"\s*Use read-only code repo `[^`]+`\.?", "", text, flags=re.I)
    return text.strip()


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


def combine_prompt_context(*values: str | None) -> str:
    return " ".join(str(value).strip() for value in values if str(value or "").strip())


def prompt_context(project_folder: Path, repos: list[str], custom_context: str = "") -> str:
    context = f"Use project folder `{project_folder}`. {repo_context(repos)}"
    if custom_context.strip():
        context = f"{context} Additional prompt context: {custom_context.strip()}"
    return context


def exact_prompt(base: str, project_folder: Path, repos: list[str], custom_context: str = "") -> str:
    return f"{base.strip()} {prompt_context(project_folder, repos, custom_context)}".strip()


def enrich_ai_prompt(label: str, prompt: str) -> str:
    if re.search(r"weekly\s+cto|weekly\s+review", f"{label} {prompt}", re.I) and "read-only local Git history" not in prompt:
        return f"{prompt.strip()} Prefer read-only local Git history for the review window when available; do not run mutating Git commands."
    return prompt


def default_ai_prompts(company: str, project_folder: Path, repos: list[str], report_prompt_context: str = "") -> list[tuple[str, str]]:
    return [
        (
            "Weekly CTO Review",
            exact_prompt(
                f"Run the weekly CTO review for {company}. Prefer read-only local Git history for the review window when available; do not run mutating Git commands.",
                project_folder,
                repos,
                report_prompt_context,
            ),
        ),
        ("CEO Update", exact_prompt(f"Write the CEO engineering update for {company}.", project_folder, repos, report_prompt_context)),
        ("Tech Stack", exact_prompt(f"Review the connected codebase(s) and create a Tech Stack report for {company}.", project_folder, repos, report_prompt_context)),
        ("Engineering Risk Review", exact_prompt(f"Run the engineering risk review for {company}.", project_folder, repos, report_prompt_context)),
        (
            "Review Risks",
            exact_prompt(
                f"Use the Day Zero CTO review-risks workflow to walk the risk register for {company}. Prioritize risks whose next review is due, severity is high, or mitigation is unclear, and let me keep active, update, close, punt, or mark evidence needed one item at a time. If we make a formal choice while addressing a risk, log that choice in core/DECISIONS.md.",
                project_folder,
                repos,
                report_prompt_context,
            ),
        ),
        ("Learning", exact_prompt(f"Run a Day Zero CTO learning prompt for {company}.", project_folder, repos)),
        (
            "Review Decisions",
            exact_prompt(
                f"Use the Day Zero CTO review-decisions workflow to walk the decision log for {company}. Treat DECISIONS.md as recorded decisions, use Revisit Trigger to choose what needs review, and let me reaffirm, supersede, punt, or mark evidence needed one item at a time.",
                project_folder,
                repos,
            ),
        ),
        (
            "Refine Strategy",
            exact_prompt(
                f"Use the Day Zero CTO refine-core-context workflow to refine core/STRATEGY.md for {company}. Interview me section by section, draft updates for approval, write the approved Markdown source, and refresh the wiki.",
                project_folder,
                repos,
            ),
        ),
        (
            "Refine Team",
            exact_prompt(
                f"Use the Day Zero CTO refine-core-context workflow to refine core/TEAM.md for {company}. Interview me section by section, draft updates for approval, write the approved Markdown source, and refresh the wiki.",
                project_folder,
                repos,
            ),
        ),
        (
            "Refine Operating Cadence",
            exact_prompt(
                f"Use the Day Zero CTO refine-core-context workflow to refine core/OPERATING_CADENCE.md for {company}, including Index Cadence Rules and weekday intent for recurring rituals if useful. Interview me section by section, draft updates for approval, write the approved Markdown source, and refresh the wiki.",
                project_folder,
                repos,
            ),
        ),
        (
            "Refine Decisions",
            exact_prompt(
                f"Use the Day Zero CTO refine-core-context workflow to refine core/DECISIONS.md for {company}. Interview me about missing or stale decisions, draft updates for approval, write the approved Markdown source, and refresh the wiki.",
                project_folder,
                repos,
            ),
        ),
        (
            "Refine Risks",
            exact_prompt(
                f"Use the Day Zero CTO refine-core-context workflow to refine core/RISKS.md for {company}. Interview me about current risks, draft risk register updates for approval, write the approved Markdown source, and refresh the wiki.",
                project_folder,
                repos,
            ),
        ),
    ]


def local_helper_commands(project_folder: Path) -> list[tuple[str, str]]:
    return [
        ("Next Best Action", f'dzcto lfg "{project_folder}"'),
        ("Project Status", f'dzcto status "{project_folder}"'),
        ("Check Stale", f'dzcto check-stale "{project_folder}"'),
        ("Refresh Wiki", f'dzcto refresh "{project_folder}"'),
        ("Serve Dashboard", f'dzcto serve "{project_folder}"'),
        ("Quickstart Help", f'dzcto quickstart --project "{project_folder}"'),
        ("Install Stable Command", "dzcto install-command"),
        ("Doctor", f'dzcto doctor --project "{project_folder}"'),
        ("Update Day Zero CTO", f'dzcto update --project "{project_folder}"'),
        ("Issue Bundle", f'dzcto collect-issue-bundle "{project_folder}"'),
    ]


def setup_checklist_items(
    *,
    wiki_root: Path,
    strategy_path: Path,
    config: dict[str, Any],
    core_ready: int,
    cadence_rules: list[dict[str, Any]],
    report_count: int,
    learning_items: list[dict[str, Any]],
    repos: list[str],
) -> list[dict[str, str]]:
    def item(label: str, done: bool, detail: str, href: str, action: str) -> dict[str, str]:
        return {
            "label": label,
            "state": "done" if done else "next",
            "status": "Done" if done else "Next",
            "detail": detail,
            "href": href,
            "action": action,
        }

    return [
        item(
            "Company context",
            has_captured_company_description(strategy_path, config),
            "Description is captured" if has_captured_company_description(strategy_path, config) else "Add the company thesis or summary",
            "core/strategy.html",
            "Refine Strategy",
        ),
        item(
            "Read-only repos",
            bool(repos),
            f"{len(repos)} repo path{'s' if len(repos) != 1 else ''} configured" if repos else "Connect code evidence when available",
            "#sec-help",
            "Run init with --repo",
        ),
        item(
            "Core context",
            core_ready == len(CORE_DOCS),
            f"{core_ready}/{len(CORE_DOCS)} source files ready",
            "#sec-core",
            "Refine core docs",
        ),
        item(
            "Operating cadence",
            bool(cadence_rules),
            f"{len(cadence_rules)} recurring ritual{'s' if len(cadence_rules) != 1 else ''} tracked" if cadence_rules else "Add Index Cadence Rules",
            "core/operating-cadence.html",
            "Refine Cadence",
        ),
        item(
            "First reports",
            report_count > 0,
            f"{report_count} report artifact{'s' if report_count != 1 else ''}" if report_count else "Run Tech Stack, Risk, Weekly, or CEO update",
            "#sec-reports",
            "Run first report",
        ),
        item(
            "Learning seed",
            bool(active_learning_items(learning_items)),
            f"{len(active_learning_items(learning_items))} active item{'s' if len(active_learning_items(learning_items)) != 1 else ''}" if active_learning_items(learning_items) else "Seed the first system concepts",
            "learning/index.html",
            "Run Learning",
        ),
        item(
            "Generated pages",
            all((wiki_root / "core" / core_doc_html_name(doc)).exists() for doc in CORE_DOCS),
            "HTML pages generated" if all((wiki_root / "core" / core_doc_html_name(doc)).exists() for doc in CORE_DOCS) else "Refresh the wiki",
            "#sec-help",
            "Refresh Wiki",
        ),
    ]


def setup_link(href: str, prefix: str = "") -> str:
    if href.startswith("#"):
        return href if not prefix else f"{prefix}index.html{href}"
    if re.match(r"^(https?:|file:|/)", href):
        return href
    return f"{prefix}{href}"


def setup_checklist_rows(items: list[dict[str, str]], prefix: str = "") -> str:
    return "\n".join(
        f"""<a class="setup-item" data-state="{esc(item["state"])}" href="{esc(setup_link(item["href"], prefix))}">
  <span class="setup-mark" aria-hidden="true"></span>
  <span class="setup-body">
    <span class="setup-title">{esc(item["label"])}</span>
    <span class="setup-detail">{esc(item["detail"])}</span>
  </span>
  <span class="setup-action">{esc(item["status"] if item["state"] == "done" else item["action"])}</span>
</a>"""
        for item in items
    )


def setup_checklist_html(items: list[dict[str, str]], prefix: str = "") -> str:
    complete = sum(1 for item in items if item["state"] == "done")
    rows = setup_checklist_rows(items, prefix)
    return f"""
  <section class="setup-panel setup-page-list" id="sec-setup" aria-label="Setup checklist">
    <div class="setup-head">
      <div>
        <h2>Setup Checklist</h2>
        <p>{esc(complete)} of {esc(len(items))} complete</p>
      </div>
      <a class="setup-help" href="{esc(setup_link("#sec-help", prefix))}">Help</a>
    </div>
    <div class="setup-list">{rows}</div>
  </section>
"""


def setup_dashboard_summary_html(items: list[dict[str, str]], *, section_id: str | None = "sec-setup") -> str:
    complete = sum(1 for item in items if item["state"] == "done")
    remaining = len(items) - complete
    id_attr = f' id="{esc(section_id)}"' if section_id else ""
    if remaining:
        next_items = [item for item in items if item["state"] != "done"][:3]
        preview = "".join(f"<li>{esc(item['label'])}: {esc(item['action'])}</li>" for item in next_items)
        return f"""
  <section class="setup-summary setup-alert"{id_attr} aria-label="Setup needs attention">
    <div>
      <span class="setup-kicker">Setup needs attention</span>
      <h2>{esc(remaining)} of {esc(len(items))} setup items remain</h2>
      <p>Finish these before treating the command center as fully operational.</p>
      <ul>{preview}</ul>
    </div>
    <a class="setup-primary" href="setup/index.html">Open checklist</a>
  </section>
"""
    return f"""
  <section class="setup-summary setup-reference"{id_attr} aria-label="Setup reference">
    <div>
      <span class="setup-kicker">Setup complete</span>
      <h2>Setup checklist is complete</h2>
      <p>The full onboarding checklist is kept as a reference page for audits, handoffs, and future project changes.</p>
    </div>
    <a class="setup-primary" href="setup/index.html">View reference</a>
  </section>
"""


def dashboard_setup_section_html(items: list[dict[str, str]], *, section_number: str = "05") -> str:
    complete = sum(1 for item in items if item["state"] == "done")
    return f"""
  <details class="section" id="sec-setup">
    <summary>
      <span class="chev" aria-hidden="true"></span>
      <span class="sec-num">{esc(section_number)}</span>
      <span class="sec-title">Setup</span>
      <span class="sec-meta">Reference / {esc(complete)} of {esc(len(items))} complete</span>
    </summary>
    <div class="sec-body">
      {setup_dashboard_summary_html(items, section_id=None)}
    </div>
  </details>
"""


def dashboard_help_html(project_folder: Path, ai_prompt_items: list[str], local_command_items: list[str], *, section_number: str = "04") -> str:
    project = str(project_folder)
    copy_card_count = len(ai_prompt_items) + len(local_command_items)
    help_cards = [
        (
            "Start",
            "Ask the helper for the next best action, then use setup checks and the served dashboard when something looks off.",
            f'dzcto lfg "{project}"',
        ),
        (
            "Edit",
            "Update source Markdown under knowledge/wiki/core. The Risks page is generated from core/RISKS.md and report signals, not edited in HTML.",
            f'dzcto help editing --project "{project}"',
        ),
        (
            "Operate",
            "Run weekly reviews, CEO updates, risk reviews, decision reviews, learning, and tech-stack reports from prompt cards.",
            f'dzcto help reports --project "{project}"',
        ),
        (
            "Check",
            "Use status, doctor, check-stale, and issue bundles when setup or generated pages look wrong.",
            f'dzcto help troubleshooting --project "{project}"',
        ),
    ]
    command_rows = [
        ("quickstart", f'dzcto quickstart --project "{project}"', "Print the shortest self-serve setup path."),
        ("help", f'dzcto help commands --project "{project}"', "Show complete workflow and command help."),
        ("lfg", f'dzcto lfg "{project}"', "Pick the next best action: setup, cadence, risks, decisions, then learning."),
        ("version", "dzcto version", "Print the installed helper version."),
        ("setup", 'dzcto setup --wiki-project "<project>" --company-name "<name>"', "Install the local Codex plugin entry and optionally initialize a wiki."),
        ("update", f'dzcto update --project "{project}"', "Pull or relink the local install and run doctor."),
        ("install-command", "dzcto install-command", "Create a stable shell command such as ~/.local/bin/dzcto."),
        ("init", f'dzcto init "{project}" --company-name "<name>" --company-description "<summary>"', "Create or refresh the project wiki and metadata."),
        ("refresh", f'dzcto refresh "{project}"', "Regenerate dashboard, core pages, structured report pages, search index, learning index, and cadence alerts."),
        ("serve", f'dzcto serve "{project}"', "Serve the wiki locally for search and refresh support."),
        ("status", f'dzcto status "{project}"', "Show setup checklist and operating health."),
        ("doctor", f'dzcto doctor --project "{project}"', "Check install, manifests, helper syntax, wrappers, and project files."),
        ("check-stale", f'dzcto check-stale "{project}"', "Check generated artifacts, version drift, missing files, and cadence due state."),
        ("artifact", f'dzcto artifact --project "{project}" --kind weekly-reviews --title "Weekly CTO Review" --data-file weekly.json', "Generate durable HTML reports from structured data."),
        ("learning", f'dzcto learning --project "{project}" --select', "Manage spaced-repetition learning items and reviews."),
        ("collect-issue-bundle", f'dzcto collect-issue-bundle "{project}"', "Create a redacted troubleshooting bundle."),
        ("package-claude-desktop", "dzcto package-claude-desktop", "Build an uploadable Claude Desktop custom skill zip."),
    ]
    guide_html = "\n".join(
        f"""<div class="help-guide-row">
  <h3>{esc(title)}</h3>
  <p>{esc(detail)}</p>
  <code>{esc(command)}</code>
</div>"""
        for title, detail, command in help_cards
    )
    rows_html = "\n".join(
        f"<tr><td><code>{esc(name)}</code></td><td><code>{esc(example)}</code></td><td>{esc(purpose)}</td></tr>"
        for name, example, purpose in command_rows
    )
    return f"""
  <details class="section" id="sec-help">
    <summary>
      <span class="chev" aria-hidden="true"></span>
      <span class="sec-num">{esc(section_number)}</span>
      <span class="sec-title">Help</span>
      <span class="sec-meta">Self-serve guide / {pluralize(copy_card_count, "copy card")}</span>
    </summary>
    <div class="sec-body">
      <div class="help-accordion">
        <details class="help-panel" open>
          <summary><span>Guide</span><small>Start, edit, operate, and check this project</small></summary>
          <div class="help-panel-body help-guide">{guide_html}</div>
        </details>
        <details class="help-panel">
          <summary><span>Command Reference</span><small>{esc(len(command_rows))} local helper commands</small></summary>
          <div class="help-panel-body command-reference">
            <table>
              <thead><tr><th>Command</th><th>Example</th><th>Use when</th></tr></thead>
              <tbody>{rows_html}</tbody>
            </table>
          </div>
        </details>
        <details class="help-panel">
          <summary><span>AI Prompts</span><small>{pluralize(len(ai_prompt_items), "copy card")}</small></summary>
          <div class="help-panel-body">
            <div class="cmd-grid">{''.join(ai_prompt_items)}</div>
          </div>
        </details>
        <details class="help-panel">
          <summary><span>Local Commands</span><small>{pluralize(len(local_command_items), "copy card")}</small></summary>
          <div class="help-panel-body">
            <div class="cmd-grid">{''.join(local_command_items)}</div>
          </div>
        </details>
      </div>
    </div>
  </details>
"""


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


def render_list_section(title: str, items: Any) -> str:
    rows = array_value(items)
    if not rows:
        return ""

    list_items = []
    for item in rows:
        if isinstance(item, dict):
            title_text = text_value(value_at(item, "title", "item", "name", "priority", "ask", "decision", "risk", "finding", "question", "prompt"))
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


def severity_class(value: Any) -> str:
    text = text_value(value).lower()
    if re.search(r"high|critical|block", text):
        return "high"
    if re.search(r"medium|moderate|watch", text):
        return "medium"
    return "ready"


TABLE_VALUE_ALIASES = {
    "context": ("context", "detail", "details", "rationale", "why"),
    "decision": ("decision", "title", "name", "ask"),
    "done_when": ("done_when", "definition_of_done", "success", "outcome"),
    "evidence": ("evidence", "detail", "details", "signal", "source"),
    "impact": ("impact", "business_impact", "why"),
    "mitigation": ("mitigation", "recommendation", "next_step", "action", "plan"),
    "needed_by": ("needed_by", "urgency", "due", "due_by", "horizon"),
    "owner": ("owner", "responsible"),
    "owner_horizon": ("owner_horizon", "owner", "horizon"),
    "priority": ("priority", "title", "name", "item"),
    "risk": ("risk", "title", "name", "finding"),
    "severity": ("severity", "priority", "status"),
}


def table_value(row: dict[str, Any], key: str) -> Any:
    return value_at(row, *TABLE_VALUE_ALIASES.get(key, (key,)))


def render_table_section(title: str, rows: Any, columns: list[tuple[str, str]]) -> str:
    values = [row for row in array_value(rows) if isinstance(row, dict)]
    if not values:
        return ""

    headers = "".join(f"<th>{esc(label)}</th>" for label, _key in columns)
    table_rows = []
    for row in values:
        cells = []
        for _label, key in columns:
            value = table_value(row, key)
            if re.search(r"severity|likelihood|status", key, re.I) and present(value):
                cell = f'<span class="tag {severity_class(value)}">{esc(text_value(value))}</span>'
            elif present(value):
                cell = esc(text_value(value))
            else:
                cell = '<span class="cell-empty" title="Not captured">&mdash;</span>'
            cells.append(f"<td>{cell}</td>")
        table_rows.append(f"<tr>{''.join(cells)}</tr>")
    return f"""
<section class="artifact-section">
  <h2>{esc(title)}</h2>
  <div class="markdown-table">
    <table>
      <thead><tr>{headers}</tr></thead>
      <tbody>{''.join(table_rows)}</tbody>
    </table>
  </div>
</section>
"""


def render_candidate_risk_section(title: str, rows: Any, source_label: str, risk_registry: dict[str, Any] | None = None) -> str:
    values = []
    for row in array_value(rows):
        if isinstance(row, dict):
            enriched = dict(row)
            source = text_value(value_at(enriched, "source", "sources", "origin", "report"))
            enriched["source"] = source or source_label
            values.append(enriched)
        elif present(row):
            values.append({"risk": text_value(row), "source": source_label})
    if not values:
        return ""

    has_registry = bool(risk_registry)
    header_labels = ["Risk", "Registry", "Evidence", "Impact", "Severity", "Mitigation", "Source"] if has_registry else ["Risk", "Evidence", "Impact", "Severity", "Mitigation", "Source"]
    headers = "".join(f"<th>{esc(label)}</th>" for label in header_labels)
    table_rows = []
    registry_risks = [risk for risk in (risk_registry or {}).get("risks", []) if isinstance(risk, dict)]
    for row in values:
        match = match_risk_signal({"title": item_headline(row)}, registry_risks) if risk_registry else {}
        cells = []
        keys = ["risk", "registry", "evidence", "impact", "severity", "mitigation", "source"] if has_registry else ["risk", "evidence", "impact", "severity", "mitigation", "source"]
        for key in keys:
            if key == "evidence":
                value = value_at(row, "evidence", "detail", "details", "signal")
            elif key == "impact":
                value = value_at(row, "impact", "business_impact", "why")
            elif key == "mitigation":
                value = value_at(row, "mitigation", "recommendation", "next_step", "action", "plan")
            elif key == "registry" and risk_registry:
                if match:
                    cell = f'<a href="{esc(source_href(match["detailPath"], "../../"))}"><code>{esc(match["id"])}</code></a>'
                else:
                    cell = '<a href="../../core/risks.html#risk-signals">Intake signal</a>'
                cells.append(f"<td>{cell}</td>")
                continue
            elif key == "risk":
                value = item_headline(row)
                if match:
                    cell = f'<a class="registry-title-link" href="{esc(source_href(match["detailPath"], "../../"))}">{esc(text_value(value))}</a>'
                    cells.append(f"<td>{cell}</td>")
                    continue
            else:
                value = value_at(row, key)
            if key == "severity" and present(value):
                cell = f'<span class="tag {severity_class(value)}">{esc(text_value(value))}</span>'
            elif present(value):
                cell = esc(text_value(value))
            else:
                cell = '<span class="cell-empty" title="Not captured">&mdash;</span>'
            cells.append(f"<td>{cell}</td>")
        table_rows.append(f"<tr>{''.join(cells)}</tr>")

    return f"""
<section class="artifact-section">
  <h2>{esc(title)}</h2>
  <p class="artifact-note">Candidate signals from this report. Manage the operating risk register on the <a href="../../core/risks.html#risk-signals">Risks page</a>; promote actionable items into <code>core/RISKS.md</code> with an owner, mitigation, review date, and source before relying on them in the command center.</p>
  <div class="markdown-table">
    <table>
      <thead><tr>{headers}</tr></thead>
      <tbody>{''.join(table_rows)}</tbody>
    </table>
  </div>
</section>
"""


def render_sources(data: dict[str, Any]) -> str:
    return render_list_section("Sources", value_at(data, "sources", "source_list", "evidence_sources"))


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
    if kind == "tech-stack":
        return ""

    groups_by_kind = {
        "weekly-reviews": [
            action_group("Decisions", value_at(data, "decisions_needed", "decisions")),
            action_group("Risks", value_at(data, "risks")),
            action_group("Next Focus", value_at(data, "next_week_focus", "next_focus", "priorities")),
        ],
        "ceo-updates": [
            action_group("Asks", value_at(data, "asks_decisions", "asks", "decisions")),
            action_group("Risks / Blockers", value_at(data, "risks_blockers", "risks", "blockers")),
            action_group("Next", value_at(data, "next", "up_next")),
        ],
        "engineering-risk": [
            action_group("Top Risks", value_at(data, "top_risks", "risks")),
            action_group("Mitigations", value_at(data, "mitigations")),
            action_group("Watchpoints", value_at(data, "watchpoints")),
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


def render_weekly_review(data: dict[str, Any]) -> str:
    # The lead summary renders in the masthead deck (see report_lead_summary), not here.
    return "".join(
        [
            render_metrics(value_at(data, "metrics")),
            render_list_section("Shipped / Learned", value_at(data, "shipped_learned", "shipped", "learned")),
            render_table_section("Risks", value_at(data, "risks"), [("Risk", "risk"), ("Evidence", "evidence"), ("Business Impact", "impact"), ("Severity", "severity"), ("Mitigation", "mitigation")]),
            render_table_section("Decisions Needed", value_at(data, "decisions_needed", "decisions"), [("Decision", "decision"), ("Context", "context"), ("Owner", "owner"), ("Needed By", "needed_by")]),
            render_list_section("Team and Process", value_at(data, "team_process", "team_and_process")),
            render_table_section("Next-Week Focus", value_at(data, "next_week_focus", "next_focus", "priorities"), [("Priority", "priority"), ("Owner", "owner"), ("Why", "why"), ("Done When", "done_when")]),
            render_list_section("CEO-Update Seeds", value_at(data, "ceo_update_seeds", "ceo_seeds")),
            render_sources(data),
        ]
    )


def render_ceo_update(data: dict[str, Any]) -> str:
    # The lead summary renders in the masthead deck (see report_lead_summary), not here.
    return "".join(
        [
            render_metrics(value_at(data, "metrics")),
            render_list_section("Progress", value_at(data, "progress")),
            render_list_section("Risks / Blockers", value_at(data, "risks_blockers", "risks", "blockers")),
            render_list_section("Asks / Decisions", value_at(data, "asks_decisions", "asks", "decisions")),
            render_list_section("Next", value_at(data, "next", "up_next")),
            render_sources(data),
        ]
    )


def render_engineering_risk(data: dict[str, Any]) -> str:
    # The lead summary renders in the masthead deck (see report_lead_summary), not here.
    return "".join(
        [
            render_metrics(value_at(data, "metrics")),
            render_table_section("Top Risks", value_at(data, "top_risks", "risks"), [("Risk", "risk"), ("Evidence", "evidence"), ("Business Impact", "impact"), ("Likelihood", "likelihood"), ("Severity", "severity"), ("Mitigation", "mitigation"), ("Owner / Horizon", "owner_horizon")]),
            render_list_section("Mitigations", value_at(data, "mitigations")),
            render_list_section("Watchpoints", value_at(data, "watchpoints")),
            render_sources(data),
        ]
    )


def render_tech_stack(data: dict[str, Any], risk_registry: dict[str, Any] | None = None) -> str:
    # The lead summary renders in the masthead deck (see report_lead_summary), not here.
    return "".join(
        [
            render_table_section("Stack Components", value_at(data, "stack_components", "components"), [("Layer", "layer"), ("Technology", "technology"), ("Evidence", "evidence"), ("Notes", "notes")]),
            render_text_section("Architecture Shape", value_at(data, "architecture_shape", "architecture")),
            render_list_section("Data and Storage", value_at(data, "data_storage", "data_and_storage")),
            render_list_section("Integrations", value_at(data, "integrations")),
            render_list_section("Infrastructure and Operations", value_at(data, "infrastructure_operations", "infrastructure", "operations")),
            render_list_section("Development Tooling", value_at(data, "development_tooling", "dev_tooling")),
            render_candidate_risk_section("Candidate Risks and Watchpoints", value_at(data, "risks_watchpoints", "risks", "watchpoints"), "Tech Stack report", risk_registry),
            render_list_section("Onboarding Notes", value_at(data, "onboarding_notes", "notes")),
            render_sources(data),
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


def render_structured_report(kind: str, data: dict[str, Any], risk_registry: dict[str, Any] | None = None, decision_registry: dict[str, Any] | None = None) -> str:
    if kind == "tech-stack":
        body = render_tech_stack(data, risk_registry)
    else:
        renderers = {
            "weekly-reviews": render_weekly_review,
            "ceo-updates": render_ceo_update,
            "engineering-risk": render_engineering_risk,
        }
        body = renderers.get(kind, render_generic_report)(data)
    # The lead summary now lives in the masthead, so the follow-up-signals card
    # anchors deterministically at the top of the body for every kind.
    action_summary = render_action_summary(kind, data)
    rendered = f"{action_summary}{body}".strip() or render_generic_report(data)
    # A blank body is legitimate when the lead summary carries the report in the
    # masthead deck. Only surface a placeholder when nothing at all was captured.
    if not rendered.strip() and not report_lead_summary(data):
        return '<p class="empty-item">No content yet.</p>'
    return rendered


def core_doc_html_name(doc: str) -> str:
    return CORE_DOC_HTML.get(doc, f"{slugify(Path(doc).stem)}.html")


def stable_anchor_id(prefix: str, value: str) -> str:
    slug = slugify(plain_markdown(value))
    return f"{prefix}-{slug or 'item'}"


def short_hash(value: str, length: int = 10) -> str:
    return sha256_text(value).split(":", 1)[1][:length]


def risk_id_for_title(title: str) -> str:
    return stable_anchor_id("risk", title)


def decision_id_for_title(title: str) -> str:
    return stable_anchor_id("decision", title)


def risk_detail_relative_path(risk_id: str) -> str:
    return f"risks/{slugify(risk_id)}.html"


def decision_detail_relative_path(decision_id: str) -> str:
    return f"decisions/{slugify(decision_id)}.html"


def risk_id_from_row(row: dict[str, str], title: str) -> str:
    explicit = plain_markdown(value_from_row(row, "id", "risk_id"))
    if explicit:
        return slugify(explicit) if not explicit.lower().startswith("risk-") else slugify(explicit)
    return risk_id_for_title(title)


def decision_id_from_row(row: dict[str, str], title: str) -> str:
    explicit = plain_markdown(value_from_row(row, "id", "decision_id"))
    if explicit:
        return slugify(explicit) if not explicit.lower().startswith("decision-") else slugify(explicit)
    return decision_id_for_title(title)


def signal_id_for(kind: str, href: str, title: str) -> str:
    return f"signal-{short_hash('|'.join([kind, href, risk_match_text(title)]))}"


def decision_signal_id_for(kind: str, href: str, title: str) -> str:
    return f"decision-signal-{short_hash('|'.join([kind, href, decision_match_text(title)]))}"


def unique_anchor_id(prefix: str, value: str, used_ids: set[str]) -> str:
    base = stable_anchor_id(prefix, value)
    anchor = base
    suffix = 2
    while anchor in used_ids:
        anchor = f"{base}-{suffix}"
        suffix += 1
    used_ids.add(anchor)
    return anchor


def risk_anchor(value: str) -> str:
    return stable_anchor_id("risk", value)


def markdown_links(value: str) -> list[dict[str, str]]:
    links: list[dict[str, str]] = []
    for match in re.finditer(r"\[([^\]]+)\]\(([^)]+)\)", value or ""):
        label = plain_markdown(match.group(1))
        href = match.group(2).strip()
        if label or href:
            links.append({"label": label or href, "href": href})
    return links


def reference_list(label: str, href: str = "", *, kind: str = "") -> list[dict[str, str]]:
    label = plain_markdown(label)
    href = href.strip()
    if not label and not href:
        return []
    item = {"label": label or href}
    if href:
        item["href"] = href
    if kind:
        item["kind"] = kind
    return [item]


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


def inline_markdown(value: str) -> str:
    text = esc(value)
    text = re.sub(r"`([^`]+)`", r"<code>\1</code>", text)
    text = re.sub(r"\*\*([^*]+)\*\*", r"<strong>\1</strong>", text)

    def _link(match: re.Match[str]) -> str:
        # value was already esc()'d above, so the captured href is single-escaped;
        # emit it raw (re-escaping would turn & into &amp;amp;). The guard only
        # decides whether to keep the <a>, dropping disallowed-scheme links to text.
        label, href = match.group(1), match.group(2)
        if href_scheme_allowed(href):
            return f'<a href="{href}">{label}</a>'
        return label

    text = re.sub(r"\[([^\]]+)\]\(([^)]+)\)", _link, text)
    return text


def table_filter_columns(headers: list[str], profile: str | None) -> list[dict[str, Any]]:
    if not profile:
        return []
    normalized_headers = [normalize_key(plain_markdown(header)) for header in headers]
    columns: list[dict[str, Any]] = []
    for key, label, aliases in TABLE_FILTER_PROFILES.get(profile, []):
        for index, header in enumerate(normalized_headers):
            if header in {normalize_key(alias) for alias in aliases}:
                columns.append({"key": key, "label": label, "index": index})
                break
    return columns


def table_filter_controls(table_id: str, rows: list[list[str]], columns: list[dict[str, Any]]) -> str:
    if not columns:
        return ""

    def filter_values(value: str) -> list[str]:
        return [part.strip() for part in plain_markdown(value).split("|") if has_real_value(part)]

    controls = [
        f"""<label class="filter-field filter-search-field">
  <span>Filter</span>
  <input type="search" data-table-filter-search placeholder="Search rows">
</label>"""
    ]
    for column in columns:
        values = sorted(
            {
                value
                for row in rows
                if column["index"] < len(row)
                for value in filter_values(row[column["index"]])
            },
            key=str.lower,
        )
        if not values:
            continue
        options = "".join(f'<option value="{esc(value)}">{esc(snippet(value, 54))}</option>' for value in values)
        controls.append(
            f"""<label class="filter-field">
  <span>{esc(column["label"])}</span>
  <select data-table-filter-select="{esc(column["key"])}">
    <option value="">All</option>
    {options}
  </select>
</label>"""
        )

    if len(controls) == 1:
        return ""

    return f"""
<div class="table-filter" data-table-filter-controls="{esc(table_id)}">
  {''.join(controls)}
  <button type="button" class="filter-clear" data-table-filter-clear>Clear</button>
  <span class="filter-count" data-table-filter-count>{esc(len(rows))} rows</span>
</div>
"""


def render_markdown_table(
    lines: list[str],
    row_anchor_prefix: str | None = None,
    used_anchor_ids: set[str] | None = None,
    filter_profile: str | None = None,
) -> str:
    rows = [split_markdown_row(line) for line in lines]
    if len(rows) < 2:
        return ""
    header_cells = rows[0]
    data_rows = rows[2:]
    headers = "".join(f"<th>{inline_markdown(cell)}</th>" for cell in header_cells)
    body_rows = []
    used_anchor_ids = used_anchor_ids if used_anchor_ids is not None else set()
    filter_columns = table_filter_columns(header_cells, filter_profile)
    table_id = unique_anchor_id("table", f"{filter_profile or 'markdown'}-{header_cells[0] if header_cells else 'rows'}", used_anchor_ids)
    for row in data_rows:
        anchor_attr = ""
        if row_anchor_prefix and row:
            anchor_attr = f' id="{esc(unique_anchor_id(row_anchor_prefix, row[0], used_anchor_ids))}"'
        filter_attrs = [f' data-filter-text="{search_text_attr(*row)}"']
        for column in filter_columns:
            value = plain_markdown(row[column["index"]]).strip() if column["index"] < len(row) else ""
            filter_attrs.append(f' data-filter-{esc(column["key"])}="{esc(value)}"')
        body_rows.append(f"<tr{anchor_attr}{''.join(filter_attrs)}>" + "".join(f"<td>{inline_markdown(cell)}</td>" for cell in row) + "</tr>")
    controls = table_filter_controls(table_id, data_rows, filter_columns)
    return f'{controls}<div class="markdown-table" id="{esc(table_id)}" data-filterable-table><table><thead><tr>{headers}</tr></thead><tbody>{"".join(body_rows)}</tbody></table></div>'


def markdown_to_html(markdown: str, table_anchor_prefix: str | None = None, table_filter_profile: str | None = None) -> str:
    lines = markdown.splitlines()
    blocks: list[str] = []
    paragraph: list[str] = []
    list_items: list[str] = []
    table_lines: list[str] = []
    in_code = False
    code_lines: list[str] = []
    used_anchor_ids: set[str] = set()

    def flush_paragraph() -> None:
        nonlocal paragraph
        if paragraph:
            blocks.append(f"<p>{inline_markdown(' '.join(paragraph).strip())}</p>")
            paragraph = []

    def flush_list() -> None:
        nonlocal list_items
        if list_items:
            blocks.append("<ul>" + "".join(f"<li>{inline_markdown(item)}</li>" for item in list_items) + "</ul>")
            list_items = []

    def flush_table() -> None:
        nonlocal table_lines
        if table_lines:
            rendered = render_markdown_table(table_lines, row_anchor_prefix=table_anchor_prefix, used_anchor_ids=used_anchor_ids, filter_profile=table_filter_profile)
            if rendered:
                blocks.append(rendered)
            table_lines = []

    for line in lines:
        stripped = line.strip()
        if stripped.startswith("```"):
            if in_code:
                blocks.append(f"<pre><code>{esc(chr(10).join(code_lines))}</code></pre>")
                code_lines = []
                in_code = False
            else:
                flush_paragraph()
                flush_list()
                flush_table()
                in_code = True
            continue
        if in_code:
            code_lines.append(line)
            continue
        if not stripped:
            flush_paragraph()
            flush_list()
            flush_table()
            continue
        if stripped.startswith("|"):
            flush_paragraph()
            flush_list()
            table_lines.append(stripped)
            continue
        flush_table()
        if match := re.match(r"^(#{1,4})\s+(.+)$", stripped):
            flush_paragraph()
            flush_list()
            level = min(len(match.group(1)) + 1, 4)
            blocks.append(f"<h{level}>{inline_markdown(match.group(2))}</h{level}>")
            continue
        if match := re.match(r"^[-*]\s+(.+)$", stripped):
            flush_paragraph()
            list_items.append(match.group(1))
            continue
        flush_list()
        paragraph.append(stripped)

    flush_paragraph()
    flush_list()
    flush_table()
    if in_code:
        blocks.append(f"<pre><code>{esc(chr(10).join(code_lines))}</code></pre>")
    return "\n".join(blocks) or '<p class="empty-item">No content yet.</p>'


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


def read_learning_items(learning_dir: Path) -> list[dict[str, Any]]:
    value = read_json_file(learning_dir / "items.json", [])
    return value if isinstance(value, list) else []


def read_learning_reviews(learning_dir: Path) -> list[dict[str, Any]]:
    path = learning_dir / "reviews.jsonl"
    if not path.exists():
        return []
    reviews = []
    for line in path.read_text(encoding="utf-8").splitlines():
        try:
            value = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(value, dict):
            reviews.append(value)
    return reviews


def date_value(value: Any) -> dt.date | None:
    try:
        return dt.date.fromisoformat(str(value))
    except ValueError:
        return None


def active_learning_items(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [item for item in items if item.get("status", "active") == "active"]


def learning_counts(items: list[dict[str, Any]], today: dt.date) -> dict[str, int]:
    active = active_learning_items(items)
    new_count = sum(1 for item in active if int(item.get("seen_count", 0) or 0) == 0)
    due_count = 0
    for item in active:
        due_on = date_value(item.get("due_on"))
        if int(item.get("seen_count", 0) or 0) > 0 and due_on and due_on <= today:
            due_count += 1
    return {"active": len(active), "due": due_count, "new": new_count}


def learning_summary(items: list[dict[str, Any]], today: dt.date) -> str:
    counts = learning_counts(items, today)
    parts = [pluralize(counts["active"], "learning item")]
    if counts["due"]:
        parts.append(f"{counts['due']} due")
    if counts["new"]:
        parts.append(f"{counts['new']} new")
    return " / ".join(parts)


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


def search_entry(
    *,
    title: str,
    kind: str,
    url: str,
    text: str,
    summary: str | None = None,
    date: str | None = None,
    section: str | None = None,
) -> dict[str, str]:
    haystack = plain_html(text)
    return {
        "title": title,
        "kind": kind,
        "url": url,
        "summary": snippet(summary or haystack),
        "date": date or "",
        "section": section or "",
        "text": haystack,
    }


def write_search_index(
    wiki_root: Path,
    project_folder: Path,
    *,
    company: str,
    description: str,
    core_pages: list[dict[str, Any]],
    report_entries: list[tuple[str, str, list[Path]]],
    learning_items: list[dict[str, Any]],
    setup_items: list[dict[str, str]] | None = None,
    risk_registry: dict[str, Any] | None = None,
    decision_registry: dict[str, Any] | None = None,
) -> None:
    setup_items = setup_items or []
    setup_complete = sum(1 for item in setup_items if item.get("state") == "done")
    entries: list[dict[str, str]] = [
        search_entry(
            title=f"{company} Day Zero CTO",
            kind="Dashboard",
            url="index.html",
            text=f"{company} {description} cadence core context reports learning commands",
            summary=description,
        )
    ]
    if setup_items:
        entries.append(
            search_entry(
                title=f"{company} Setup Checklist",
                kind="Setup",
                url="setup/index.html",
                text=" ".join(f"{item.get('label', '')} {item.get('detail', '')} {item.get('action', '')}" for item in setup_items),
                summary=f"{setup_complete} of {len(setup_items)} setup items complete.",
                section="setup",
            )
        )

    core_dir = wiki_root / "core"
    for page in core_pages:
        if not page["source_exists"]:
            continue
        source_path = core_dir / page["doc"]
        source_text = source_path.read_text(encoding="utf-8", errors="replace")
        if page["doc"] == "RISKS.md":
            registry = risk_registry or build_risk_registry(wiki_root)
            risk_text = " ".join(
                f"{risk.get('id', '')} {risk.get('title', '')} {risk.get('status', '')} {risk.get('severity', '')} {risk.get('owner', '')} {risk.get('source', '')} {risk.get('evidence', '')} {risk.get('impact', '')} {risk.get('mitigation', '')}"
                for risk in registry.get("risks", [])
                if isinstance(risk, dict)
            )
            signal_text = " ".join(
                f"{signal.get('title', '')} {signal.get('severity', '')} {signal.get('status', '')} {signal.get('source_label', '')} {signal.get('evidence', '')} {signal.get('impact', '')} {signal.get('mitigation', '')} {signal.get('matchedRiskId', '')}"
                for signal in registry.get("signals", [])
                if isinstance(signal, dict)
            )
            source_text = f"{source_text}\n\nCanonical Risk Registry\n{risk_text}\n\nRisk Signals From Reports\n{signal_text}"
        elif page["doc"] == "DECISIONS.md":
            registry = decision_registry or build_decision_registry(wiki_root)
            decision_text = " ".join(
                f"{decision.get('id', '')} {decision.get('title', '')} {decision.get('status', '')} {decision.get('date', '')} {decision.get('owner', '')} {decision.get('context', '')} {decision.get('options', '')} {decision.get('rationale', '')} {decision.get('revisitTrigger', '')}"
                for decision in registry.get("decisions", [])
                if isinstance(decision, dict)
            )
            signal_text = " ".join(
                f"{signal.get('title', '')} {signal.get('status', '')} {signal.get('source_label', '')} {signal.get('context', '')} {signal.get('matchedDecisionId', '')}"
                for signal in registry.get("signals", [])
                if isinstance(signal, dict)
            )
            source_text = f"{source_text}\n\nCanonical Decision Registry\n{decision_text}\n\nDecision Signals From Reports\n{signal_text}"
        entries.append(
            search_entry(
                title=page["title"],
                kind="Core",
                url=page["html"],
                text=source_text,
                summary=page["description"],
                section=page["doc"],
            )
        )

    if risk_registry:
        for risk in risk_registry.get("risks", []):
            if not isinstance(risk, dict):
                continue
            risk_id = text_value(risk.get("id")) or risk_id_for_title(text_value(risk.get("title")))
            entries.append(
                search_entry(
                    title=text_value(risk.get("title")) or risk_id,
                    kind="Risk",
                    url=text_value(risk.get("detailPath")) or risk_detail_relative_path(risk_id),
                    text=" ".join(
                        text_value(risk.get(field))
                        for field in ("id", "title", "status", "severity", "owner", "source", "review", "evidence", "impact", "mitigation", "category")
                    ),
                    summary=text_value(risk.get("impact") or risk.get("evidence") or risk.get("mitigation")),
                    date=text_value(risk.get("review")),
                    section="risks",
                )
            )

    if decision_registry:
        for decision in decision_registry.get("decisions", []):
            if not isinstance(decision, dict):
                continue
            decision_id = text_value(decision.get("id")) or decision_id_for_title(text_value(decision.get("title")))
            entries.append(
                search_entry(
                    title=text_value(decision.get("title")) or decision_id,
                    kind="Decision",
                    url=text_value(decision.get("detailPath")) or decision_detail_relative_path(decision_id),
                    text=" ".join(
                        text_value(decision.get(field))
                        for field in ("id", "title", "status", "date", "owner", "source", "context", "options", "rationale", "revisitTrigger")
                    ),
                    summary=text_value(decision.get("rationale") or decision.get("context")),
                    date=text_value(decision.get("date")),
                    section="decisions",
                )
            )

    for folder, label, links in report_entries:
        for path in links:
            html_text = path.read_text(encoding="utf-8", errors="replace")
            entries.append(
                search_entry(
                    title=html_title(path),
                    kind=label,
                    url=path.relative_to(wiki_root).as_posix(),
                    text=html_text,
                    summary=report_summary_for_path(path) or plain_html(html_text),
                    date=report_run_date(path),
                    section=folder,
                )
            )

    for item in active_learning_items(learning_items):
        title = text_value(item.get("title") or item.get("id") or "Learning item")
        summary = text_value(item.get("summary"))
        details = text_value(item.get("details") or item.get("detail"))
        entries.append(
            search_entry(
                title=title,
                kind="Learning",
                url="learning/index.html",
                text=f"{title} {summary} {details} {text_value(item.get('source'))} {text_value(item.get('tags'))}",
                summary=summary or details,
                date=text_value(item.get("due_on")),
                section="learning",
            )
        )

    payload = {
        "generatedAt": utc_now(),
        "projectFolder": str(project_folder),
        "entries": entries,
    }
    write_json(wiki_root / "search-index.json", payload)


def learning_item_status(item: dict[str, Any], today: dt.date) -> str:
    if int(item.get("seen_count", 0) or 0) == 0:
        return "New"
    due_on = date_value(item.get("due_on"))
    return "Due" if due_on and due_on <= today else "Scheduled"


def read_learning_checklist_progress(learning_dir: Path) -> dict[str, Any]:
    checklist_dir = learning_dir / "checklists"
    paths = sorted(checklist_dir.glob("*.md"), reverse=True)
    if not paths:
        return {"path": None, "confirmed": 0, "total": 0, "percent": 0}

    path = paths[0]
    confirmed = 0
    total = 0
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.startswith("- ["):
            total += 1
            if line.lower().startswith("- [x]"):
                confirmed += 1

    percent = round((confirmed / total) * 100) if total else 0
    return {"path": path, "confirmed": confirmed, "total": total, "percent": percent}


def normalize_key(value: str) -> str:
    return re.sub(r"(^_+|_+$)", "", re.sub(r"[^a-z0-9]+", "_", value.lower()))


def markdown_tables_with_sections(path: Path) -> list[tuple[str, list[dict[str, str]]]]:
    if not path.exists():
        return []

    tables: list[tuple[str, list[dict[str, str]]]] = []
    lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    index = 0
    section = ""
    while index < len(lines):
        heading = re.match(r"^#{1,6}\s+(.+?)\s*$", lines[index].strip())
        if heading:
            section = plain_markdown(heading.group(1))
            index += 1
            continue

        if not lines[index].strip().startswith("|"):
            index += 1
            continue

        table_lines: list[str] = []
        while index < len(lines) and lines[index].strip().startswith("|"):
            table_lines.append(lines[index].strip())
            index += 1

        if len(table_lines) < 2:
            continue
        rows = [split_markdown_row(line) for line in table_lines]
        headers = [normalize_key(header) for header in rows[0]]
        body_rows = rows[2:] if len(rows) > 2 and all(re.match(r"^:?-+:?$", cell.strip()) for cell in rows[1]) else rows[1:]
        table: list[dict[str, str]] = []
        for row in body_rows:
            values = {headers[col]: row[col].strip() for col in range(min(len(headers), len(row)))}
            if any(values.values()):
                table.append(values)
        if table:
            tables.append((section, table))
    return tables


def markdown_tables(path: Path) -> list[list[dict[str, str]]]:
    return [table for _section, table in markdown_tables_with_sections(path)]


def value_from_row(row: dict[str, str], *keys: str) -> str:
    for key in keys:
        normalized = normalize_key(key)
        if row.get(normalized):
            return row[normalized].strip()
    return ""


def markdown_heading_items(path: Path, *, limit: int = 8) -> list[dict[str, str]]:
    if not path.exists():
        return []

    items: list[dict[str, str]] = []
    current: dict[str, str] | None = None
    body: list[str] = []
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        if match := re.match(r"^#{2,4}\s+(.+)$", line.strip()):
            if current:
                current["summary"] = plain_markdown("\n".join(body))
                items.append(current)
                if len(items) >= limit:
                    return items
            current = {"title": plain_markdown(match.group(1))}
            body = []
            continue
        if current and line.strip():
            body.append(line.strip())
    if current and len(items) < limit:
        current["summary"] = plain_markdown("\n".join(body))
        items.append(current)
    return items


def normalize_severity(value: str) -> str:
    text = value.lower()
    if re.search(r"critical|blocker|urgent", text):
        return "Critical"
    if re.search(r"high|severe", text):
        return "High"
    if re.search(r"medium|moderate|watch", text):
        return "Medium"
    return "Low"


def severity_token(value: str) -> str:
    return {"Critical": "crit", "High": "high", "Medium": "med", "Low": "low"}.get(value, "low")


def severity_rank(value: str) -> int:
    return {"Critical": 0, "High": 1, "Medium": 2, "Low": 3}.get(value, 3)


def limit_entries(items: list[dict[str, str]], limit: int | None) -> list[dict[str, str]]:
    return items if limit is None else items[:limit]


def normalize_risk_status(value: str, *, default: str = "Active") -> str:
    text = plain_markdown(value).lower()
    if re.search(r"\b(closed|resolved|retired|accepted|absorbed)\b", text):
        return "Closed"
    if re.search(r"\b(needs evidence|evidence needed|needs_evidence)\b", text):
        return "Needs evidence"
    if re.search(r"\b(punted|deferred)\b", text):
        return "Punted"
    if re.search(r"\b(monitor|watch|monitoring)\b", text):
        return "Monitoring"
    if re.search(r"\b(active|open)\b", text):
        return "Active"
    return default


def risk_status_key(value: str) -> str:
    return normalize_key(value or "Active")


def risk_is_active(risk: dict[str, Any]) -> bool:
    return risk_status_key(str(risk.get("status") or "Active")) in RISK_ACTIVE_STATUSES


def source_references_from_cell(value: str, fallback: str = "Risk register") -> list[dict[str, str]]:
    links = markdown_links(value)
    if links:
        return links
    label = plain_markdown(value) or fallback
    return reference_list(label)


def read_risk_source_entries(core_dir: Path, *, limit: int | None = None, include_closed: bool = True) -> list[dict[str, Any]]:
    path = core_dir / "RISKS.md"
    risks: list[dict[str, Any]] = []
    for section, table in markdown_tables_with_sections(path):
        section_key = normalize_key(section)
        if section_key in {"review_history", "risk_review_history"}:
            continue
        is_closed_section = section_key == "closed_risks"
        for row in table:
            is_closed_row = is_closed_section or "closed_date" in row or "prior_mitigation" in row
            if is_closed_row and not include_closed:
                continue
            title = value_from_row(row, "risk", "title", "finding", "issue", "name") or next(iter(row.values()), "")
            if not title:
                continue
            severity_source = value_from_row(row, "severity", "priority", "status", "likelihood") or title
            source_cell = value_from_row(row, "source", "sources", "origin", "report", "reported_from")
            source = plain_markdown(source_cell)
            evidence = value_from_row(row, "evidence", "signal")
            if not evidence and not source:
                evidence = source_cell
            status = "Closed" if is_closed_row else normalize_risk_status(value_from_row(row, "risk_status", "state", "status"))
            review = plain_markdown(value_from_row(row, "review", "review_date", "next_review", "due", "horizon", "needed_by")) or "Unscheduled"
            risk = {
                "id": risk_id_from_row(row, title),
                "title": plain_markdown(title),
                "status": status,
                "severity": normalize_severity(severity_source),
                "category": plain_markdown(value_from_row(row, "category", "area", "type")),
                "owner": plain_markdown(value_from_row(row, "owner", "responsible", "owner_horizon")) or "Unassigned",
                "nextReview": review,
                "review": review,
                "source": source or "Risk register",
                "sourceLinks": source_references_from_cell(source_cell),
                "evidence": plain_markdown(evidence),
                "impact": plain_markdown(value_from_row(row, "impact", "business_impact", "why")),
                "mitigation": plain_markdown(value_from_row(row, "mitigation", "next_step", "action", "plan")),
                "markdownAnchor": risk_anchor(title),
                "sourceDocument": "core/RISKS.md",
                "sourceSection": section,
            }
            closed_date = plain_markdown(value_from_row(row, "closed_date", "closed", "resolved"))
            if closed_date:
                risk["closedDate"] = closed_date
            risks.append(risk)
    if risks:
        return limit_entries(sorted(risks, key=lambda item: (risk_status_key(item["status"]) != "active", severity_rank(item["severity"]), item["title"].lower())), limit)

    fallback = []
    for item in markdown_heading_items(path):
        title = item["title"]
        fallback.append(
            {
                "id": risk_id_for_title(title),
                "title": title,
                "status": "Active",
                "severity": normalize_severity(title),
                "category": "Core context",
                "owner": "Unassigned",
                "nextReview": "Unscheduled",
                "review": "Unscheduled",
                "source": "Risk register",
                "sourceLinks": reference_list("Risk register"),
                "evidence": item.get("summary", ""),
                "impact": "",
                "mitigation": "",
                "markdownAnchor": risk_anchor(title),
                "sourceDocument": "core/RISKS.md",
                "sourceSection": "",
            }
        )
    return limit_entries(sorted(fallback, key=lambda item: (severity_rank(item["severity"]), item["title"].lower())), limit)


def read_risk_entries(core_dir: Path, *, limit: int | None = None) -> list[dict[str, Any]]:
    risks = [risk for risk in read_risk_source_entries(core_dir, include_closed=False) if risk_is_active(risk)]
    return limit_entries(sorted(risks, key=lambda item: (severity_rank(item["severity"]), item["title"].lower())), limit)


def read_decision_source_entries(core_dir: Path, *, limit: int | None = None) -> list[dict[str, Any]]:
    path = core_dir / "DECISIONS.md"
    decisions: list[dict[str, Any]] = []
    for section, table in markdown_tables_with_sections(path):
        if normalize_key(section) in {"review_history", "decision_review_history"}:
            continue
        for row in table:
            title = value_from_row(row, "decision", "title", "question", "ask", "name") or next(iter(row.values()), "")
            if not title:
                continue
            rationale = plain_markdown(value_from_row(row, "rationale", "why", "notes", "summary"))
            context = plain_markdown(value_from_row(row, "context", "problem", "background")) or rationale
            revisit = plain_markdown(value_from_row(row, "revisit_trigger", "revisit", "needed_by", "due", "status"))
            source_cell = value_from_row(row, "source", "sources", "origin", "report", "reported_from")
            decisions.append(
                {
                    "id": decision_id_from_row(row, title),
                    "title": plain_markdown(title),
                    "status": "Recorded",
                    "date": plain_markdown(value_from_row(row, "date", "decision_date", "decided", "when")) or "Unknown",
                    "owner": plain_markdown(value_from_row(row, "owner", "responsible")) or "Founder",
                    "when": revisit or "Review trigger",
                    "revisitTrigger": revisit or "Review trigger",
                    "context": context,
                    "options": plain_markdown(value_from_row(row, "options_considered", "options", "alternatives")),
                    "rationale": rationale,
                    "source": plain_markdown(source_cell) or "Decision log",
                    "sourceLinks": source_references_from_cell(source_cell, fallback="Decision log"),
                    "markdownAnchor": decision_id_for_title(title),
                    "sourceDocument": "core/DECISIONS.md",
                    "sourceSection": section,
                }
            )
    if decisions:
        return limit_entries(decisions, limit)

    fallback = [
        {
            "id": decision_id_for_title(item["title"]),
            "title": item["title"],
            "status": "Recorded",
            "date": "Unknown",
            "owner": "Founder",
            "when": "Review",
            "revisitTrigger": "Review",
            "context": item.get("summary", ""),
            "options": "",
            "rationale": item.get("summary", ""),
            "source": "Decision log",
            "sourceLinks": reference_list("Decision log"),
            "markdownAnchor": decision_id_for_title(item["title"]),
            "sourceDocument": "core/DECISIONS.md",
            "sourceSection": "",
        }
        for item in markdown_heading_items(path, limit=8)
    ]
    return limit_entries(fallback, limit)


def read_decision_entries(core_dir: Path, *, limit: int | None = None) -> list[dict[str, Any]]:
    return read_decision_source_entries(core_dir, limit=limit)


def dates_in_text(value: str) -> list[dt.date]:
    dates: list[dt.date] = []
    for match in re.finditer(r"\b(\d{4})[-/](\d{1,2})[-/](\d{1,2})\b", value):
        try:
            dates.append(dt.date(int(match.group(1)), int(match.group(2)), int(match.group(3))))
        except ValueError:
            pass
    return dates


def decision_review_due(decision: dict[str, str], today: dt.date) -> bool:
    trigger = plain_markdown(decision.get("when") or "").strip()
    if not has_real_value(trigger):
        return False
    normalized = trigger.lower()
    if re.search(r"\b(no review|not due|none|n/a|unscheduled|no revisit)\b", normalized):
        return False

    dates = dates_in_text(normalized)
    if dates:
        return min(dates) <= today

    return bool(
        re.search(
            r"\b(overdue|due today|due now|review now|revisit now|needs review|review needed|triggered|condition met|asap|pending decision|needs decision|blocked)\b",
            normalized,
        )
    )


def due_decision_entries(decisions: list[dict[str, str]], today: dt.date) -> list[dict[str, str]]:
    return [decision for decision in decisions if decision_review_due(decision, today)]


def risk_review_due(risk: dict[str, str], today: dt.date) -> bool:
    review = plain_markdown(risk.get("review") or "").strip()
    if not has_real_value(review):
        return False
    normalized = review.lower()
    if re.search(r"\b(no review|not due|none|n/a|unscheduled|no revisit)\b", normalized):
        return False

    dates = dates_in_text(normalized)
    if dates:
        return min(dates) <= today

    return bool(
        re.search(
            r"\b(overdue|due today|due now|review now|needs review|review needed|triggered|condition met|asap|blocked)\b",
            normalized,
        )
    )


def due_risk_entries(risks: list[dict[str, str]], today: dt.date) -> list[dict[str, str]]:
    return [risk for risk in risks if risk_review_due(risk, today)]


def sortable_date_key(value: str, fallback_index: int = 0) -> tuple[int, int, int, int]:
    text = plain_markdown(value).lower()
    if match := re.search(r"\b(\d{4})[-/](\d{1,2})[-/](\d{1,2})\b", text):
        return (int(match.group(1)), int(match.group(2)), int(match.group(3)), fallback_index)
    if match := re.search(r"\b(\d{4})[-/](\d{1,2})\b", text):
        return (int(match.group(1)), int(match.group(2)), 1, fallback_index)
    if match := re.search(r"\bpre[- ]?(\d{4})\b", text):
        return (int(match.group(1)) - 1, 12, 31, fallback_index)
    if match := re.search(r"\b(\d{4})\b", text):
        return (int(match.group(1)), 1, 1, fallback_index)
    return (0, 0, 0, fallback_index)


def phrase_list(values: list[str], *, fallback: str = "captured operating judgment") -> str:
    clean = [value for value in values if value]
    if not clean:
        return fallback
    if len(clean) == 1:
        return clean[0]
    if len(clean) == 2:
        return f"{clean[0]} and {clean[1]}"
    return f"{', '.join(clean[:-1])}, and {clean[-1]}"


def top_themes(entries: list[dict[str, str]], fields: list[str]) -> list[str]:
    scores = {label: 0 for label, _pattern in THEME_PATTERNS}
    last_index = max(len(entries) - 1, 0)
    for index, entry in enumerate(entries):
        text = " ".join(entry.get(field, "") for field in fields).lower()
        # Skew the generated read toward frequent themes and the newest third of the log.
        weight = 2 if index >= max(last_index - max(len(entries) // 3, 1), 0) else 1
        for label, pattern in THEME_PATTERNS:
            if re.search(pattern, text):
                scores[label] += weight
    ranked = [label for label, score in sorted(scores.items(), key=lambda item: (-item[1], item[0])) if score]
    return ranked[:3]


def risk_match_text(value: str) -> str:
    text = plain_markdown(value).lower()
    text = re.sub(r"\bcsp\b", "content security policy", text)
    text = re.sub(r"\bphi\b", "protected health information", text)
    text = re.sub(r"[^a-z0-9]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def risk_words(value: str) -> set[str]:
    stop = {
        "and",
        "are",
        "before",
        "from",
        "into",
        "is",
        "not",
        "the",
        "this",
        "with",
        "without",
        "risk",
        "risks",
        "review",
    }
    return {word for word in risk_match_text(value).split() if len(word) > 2 and word not in stop}


def decision_match_text(value: str) -> str:
    text = plain_markdown(value).lower()
    text = re.sub(r"\bpr\b", "pull request", text)
    text = re.sub(r"[^a-z0-9]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def decision_words(value: str) -> set[str]:
    stop = {
        "and",
        "are",
        "ask",
        "asks",
        "before",
        "decide",
        "decision",
        "decisions",
        "from",
        "into",
        "needed",
        "needs",
        "question",
        "the",
        "this",
        "with",
    }
    return {word for word in decision_match_text(value).split() if len(word) > 2 and word not in stop}


def risk_titles_by_status(core_dir: Path) -> tuple[list[str], list[str]]:
    risks = read_risk_source_entries(core_dir, include_closed=True)
    active = [risk["title"] for risk in risks if risk_is_active(risk)]
    closed = [risk["title"] for risk in risks if not risk_is_active(risk)]
    return active, closed


def risk_title_matches(title: str, candidates: list[str]) -> bool:
    title_text = risk_match_text(title)
    title_words = risk_words(title)
    if not title_words:
        return False
    for candidate in candidates:
        candidate_text = risk_match_text(candidate)
        if title_text == candidate_text or title_text in candidate_text or candidate_text in title_text:
            return True
        candidate_words = risk_words(candidate)
        if not candidate_words:
            continue
        if candidate_words <= title_words or title_words <= candidate_words:
            return True
        overlap = len(title_words & candidate_words)
        if overlap >= 2 and overlap / max(len(title_words), 1) >= 0.5:
            return True
    return False


def decision_title_matches(title: str, candidates: list[str]) -> bool:
    title_text = decision_match_text(title)
    title_words = decision_words(title)
    if not title_words:
        return False
    for candidate in candidates:
        candidate_text = decision_match_text(candidate)
        if title_text == candidate_text or title_text in candidate_text or candidate_text in title_text:
            return True
        candidate_words = decision_words(candidate)
        if not candidate_words:
            continue
        if candidate_words <= title_words or title_words <= candidate_words:
            return True
        overlap = len(title_words & candidate_words)
        if overlap >= 2 and overlap / max(len(title_words), 1) >= 0.5:
            return True
    return False


def matching_report_html(json_path: Path) -> Path | None:
    if json_path.name != "data.json":
        html_path = json_path.with_suffix(".html")
        if html_path.exists():
            return html_path
    html_links = sorted(json_path.parent.glob("*.html"), reverse=True)
    return html_links[0] if html_links else None


def report_risk_signal_json_paths(wiki_root: Path) -> list[Path]:
    reports_dir = wiki_root / "reports"
    paths: list[Path] = []
    for kind in RISK_SIGNAL_REPORT_FIELDS:
        json_paths = sorted((reports_dir / kind).glob("*.json"), reverse=True)
        if len(json_paths) > 1:
            json_paths = [path for path in json_paths if path.name != "data.json"]
        paths.extend(json_paths)
    return paths


def report_risk_signal_items(kind: str, data: dict[str, Any]) -> list[Any]:
    items: list[Any] = []
    for field in RISK_SIGNAL_REPORT_FIELDS.get(kind, ()):
        items.extend(array_value(value_at(data, field)))
    return items


def risk_signal_from_item(item: Any, *, kind: str, source_label: str, source_kind: str, href: str, date: str) -> dict[str, Any] | None:
    if isinstance(item, dict):
        title = item_headline(item)
        if not title:
            return None
        severity_source = text_value(value_at(item, "severity", "priority", "status", "likelihood")) or title
        evidence = text_value(value_at(item, "evidence", "detail", "details", "signal", "context"))
        impact = text_value(value_at(item, "impact", "business_impact", "why"))
        mitigation = text_value(value_at(item, "mitigation", "recommendation", "next_step", "action", "plan"))
    else:
        title = text_value(item)
        if not title:
            return None
        severity_source = title
        evidence = ""
        impact = ""
        mitigation = ""
    return {
        "id": signal_id_for(kind, href, title),
        "title": plain_markdown(title),
        "severity": normalize_severity(severity_source),
        "evidence": plain_markdown(evidence),
        "impact": plain_markdown(impact),
        "mitigation": plain_markdown(mitigation),
        "source_label": source_label,
        "source_kind": source_kind,
        "sourceLinks": reference_list(source_label, href, kind=source_kind),
        "href": href,
        "date": date,
        "kind": kind,
    }


def read_report_risk_signals_raw(wiki_root: Path) -> list[dict[str, Any]]:
    signals: list[dict[str, Any]] = []
    for json_path in report_risk_signal_json_paths(wiki_root):
        kind = json_path.parent.name
        label = REPORT_FOLDERS.get(kind, kind)
        data = read_json_file(json_path, {})
        if not isinstance(data, dict):
            continue
        html_path = matching_report_html(json_path)
        date = report_run_date(html_path) if html_path else "Unknown date"
        href = html_path.relative_to(wiki_root).as_posix() if html_path else ""
        source_label = f"{label} / {date}"
        for item in report_risk_signal_items(kind, data):
            signal = risk_signal_from_item(item, kind=kind, source_label=source_label, source_kind=label, href=href, date=date)
            if signal:
                signals.append(signal)
    return signals


def dedupe_report_risk_signals(signals: list[dict[str, Any]]) -> list[dict[str, Any]]:
    by_key: dict[str, dict[str, Any]] = {}
    for signal in signals:
        key = risk_match_text(signal["title"])
        existing = by_key.get(key)
        if not existing:
            by_key[key] = signal
            continue
        if severity_rank(signal["severity"]) < severity_rank(existing["severity"]):
            existing["severity"] = signal["severity"]
        if signal["href"] and signal["href"] not in existing["href"].split(" | "):
            existing["href"] = " | ".join(filter(None, [existing["href"], signal["href"]]))
            existing["source_label"] = " | ".join(filter(None, [existing["source_label"], signal["source_label"]]))
            existing["sourceLinks"] = [*existing.get("sourceLinks", []), *signal.get("sourceLinks", [])]
        if signal["source_kind"] and signal["source_kind"] not in existing["source_kind"].split(" | "):
            existing["source_kind"] = " | ".join(filter(None, [existing["source_kind"], signal["source_kind"]]))
        for field in ("evidence", "impact", "mitigation"):
            if signal[field] and signal[field] not in existing[field]:
                existing[field] = " ".join(filter(None, [existing[field], signal[field]])).strip()

    return sorted(
        by_key.values(),
        key=lambda item: (severity_rank(item["severity"]), sortable_date_key(item["date"], 0)),
    )


def read_report_risk_signals(wiki_root: Path) -> list[dict[str, Any]]:
    return dedupe_report_risk_signals(read_report_risk_signals_raw(wiki_root))


def report_decision_signal_json_paths(wiki_root: Path) -> list[Path]:
    reports_dir = wiki_root / "reports"
    paths: list[Path] = []
    for kind in DECISION_SIGNAL_REPORT_FIELDS:
        json_paths = sorted((reports_dir / kind).glob("*.json"), reverse=True)
        if len(json_paths) > 1:
            json_paths = [path for path in json_paths if path.name != "data.json"]
        paths.extend(json_paths)
    return paths


def report_decision_signal_items(kind: str, data: dict[str, Any]) -> list[Any]:
    items: list[Any] = []
    for field in DECISION_SIGNAL_REPORT_FIELDS.get(kind, ()):
        items.extend(array_value(value_at(data, field)))
    return items


def decision_signal_from_item(item: Any, *, kind: str, source_label: str, source_kind: str, href: str, date: str) -> dict[str, Any] | None:
    if isinstance(item, dict):
        title = item_headline(item)
        if not title:
            return None
        context = text_value(value_at(item, "context", "detail", "details", "body", "summary", "why"))
        owner = text_value(value_at(item, "owner", "responsible", "needed_by"))
        options = text_value(value_at(item, "options", "options_considered", "alternatives"))
    else:
        title = text_value(item)
        if not title:
            return None
        context = ""
        owner = ""
        options = ""
    return {
        "id": decision_signal_id_for(kind, href, title),
        "title": plain_markdown(title),
        "context": plain_markdown(context),
        "owner": plain_markdown(owner),
        "options": plain_markdown(options),
        "source_label": source_label,
        "source_kind": source_kind,
        "sourceLinks": reference_list(source_label, href, kind=source_kind),
        "href": href,
        "date": date,
        "kind": kind,
    }


def read_report_decision_signals_raw(wiki_root: Path) -> list[dict[str, Any]]:
    signals: list[dict[str, Any]] = []
    for json_path in report_decision_signal_json_paths(wiki_root):
        kind = json_path.parent.name
        label = REPORT_FOLDERS.get(kind, kind)
        data = read_json_file(json_path, {})
        if not isinstance(data, dict):
            continue
        html_path = matching_report_html(json_path)
        date = report_run_date(html_path) if html_path else "Unknown date"
        href = html_path.relative_to(wiki_root).as_posix() if html_path else ""
        source_label = f"{label} / {date}"
        for item in report_decision_signal_items(kind, data):
            signal = decision_signal_from_item(item, kind=kind, source_label=source_label, source_kind=label, href=href, date=date)
            if signal:
                signals.append(signal)
    return signals


def dedupe_report_decision_signals(signals: list[dict[str, Any]]) -> list[dict[str, Any]]:
    by_key: dict[str, dict[str, Any]] = {}
    for signal in signals:
        key = decision_match_text(signal["title"])
        existing = by_key.get(key)
        if not existing:
            by_key[key] = signal
            continue
        if signal["href"] and signal["href"] not in existing["href"].split(" | "):
            existing["href"] = " | ".join(filter(None, [existing["href"], signal["href"]]))
            existing["source_label"] = " | ".join(filter(None, [existing["source_label"], signal["source_label"]]))
            existing["sourceLinks"] = [*existing.get("sourceLinks", []), *signal.get("sourceLinks", [])]
        if signal["source_kind"] and signal["source_kind"] not in existing["source_kind"].split(" | "):
            existing["source_kind"] = " | ".join(filter(None, [existing["source_kind"], signal["source_kind"]]))
        for field in ("context", "owner", "options"):
            if signal[field] and signal[field] not in existing[field]:
                existing[field] = " ".join(filter(None, [existing[field], signal[field]])).strip()

    return sorted(by_key.values(), key=lambda item: (sortable_date_key(item["date"], 0), item["title"].lower()))


def read_report_decision_signals(wiki_root: Path) -> list[dict[str, Any]]:
    return dedupe_report_decision_signals(read_report_decision_signals_raw(wiki_root))


def match_risk_signal(signal: dict[str, Any], risks: list[dict[str, Any]]) -> dict[str, str]:
    for risk in risks:
        if risk_title_matches(signal.get("title", ""), [risk.get("title", "")]):
            risk_id = text_value(risk.get("id")) or risk_id_for_title(text_value(risk.get("title")))
            return {
                "id": risk_id,
                "title": risk["title"],
                "status": risk.get("status", "Active"),
                "detailPath": text_value(risk.get("detailPath")) or risk_detail_relative_path(risk_id),
            }
    return {}


def match_decision_signal(signal: dict[str, Any], decisions: list[dict[str, Any]]) -> dict[str, str]:
    for decision in decisions:
        if decision_title_matches(signal.get("title", ""), [decision.get("title", "")]):
            decision_id = text_value(decision.get("id")) or decision_id_for_title(text_value(decision.get("title")))
            return {
                "id": decision_id,
                "title": decision["title"],
                "status": decision.get("status", "Recorded"),
                "detailPath": text_value(decision.get("detailPath")) or decision_detail_relative_path(decision_id),
            }
    return {}


def build_risk_registry(wiki_root: Path) -> dict[str, Any]:
    core_dir = wiki_root / "core"
    risks = read_risk_source_entries(core_dir, include_closed=True)
    for risk in risks:
        risk_id = text_value(risk.get("id")) or risk_id_for_title(text_value(risk.get("title")))
        risk["id"] = risk_id
        risk["detailPath"] = risk_detail_relative_path(risk_id)
    signals = read_report_risk_signals_raw(wiki_root)
    for signal in signals:
        match = match_risk_signal(signal, risks)
        if match:
            signal["status"] = "Matched"
            signal["matchedRiskId"] = match["id"]
            signal["matchedRiskTitle"] = match["title"]
            signal["matchedRiskStatus"] = match["status"]
            signal["matchedRiskPath"] = match["detailPath"]
        else:
            signal["status"] = "Intake"
            signal["matchedRiskId"] = ""
            signal["matchedRiskTitle"] = ""
            signal["matchedRiskStatus"] = ""
            signal["matchedRiskPath"] = ""
    return {
        "schemaVersion": RISK_REGISTRY_SCHEMA_VERSION,
        "generatedAt": utc_now(),
        "source": "core/RISKS.md",
        "risks": risks,
        "signals": sorted(signals, key=lambda item: (item.get("status") != "Intake", severity_rank(item.get("severity", "")), item.get("title", "").lower())),
    }


def build_decision_registry(wiki_root: Path) -> dict[str, Any]:
    core_dir = wiki_root / "core"
    decisions = read_decision_source_entries(core_dir)
    for decision in decisions:
        decision_id = text_value(decision.get("id")) or decision_id_for_title(text_value(decision.get("title")))
        decision["id"] = decision_id
        decision["detailPath"] = decision_detail_relative_path(decision_id)
    signals = read_report_decision_signals_raw(wiki_root)
    for signal in signals:
        match = match_decision_signal(signal, decisions)
        if match:
            signal["status"] = "Matched"
            signal["matchedDecisionId"] = match["id"]
            signal["matchedDecisionTitle"] = match["title"]
            signal["matchedDecisionStatus"] = match["status"]
            signal["matchedDecisionPath"] = match["detailPath"]
        else:
            signal["status"] = "Intake"
            signal["matchedDecisionId"] = ""
            signal["matchedDecisionTitle"] = ""
            signal["matchedDecisionStatus"] = ""
            signal["matchedDecisionPath"] = ""
    return {
        "schemaVersion": DECISION_REGISTRY_SCHEMA_VERSION,
        "generatedAt": utc_now(),
        "source": "core/DECISIONS.md",
        "decisions": decisions,
        "signals": sorted(signals, key=lambda item: (item.get("status") != "Intake", sortable_date_key(item.get("date", ""), 0), item.get("title", "").lower())),
    }


def write_risk_registry(wiki_root: Path, project_folder: Path) -> dict[str, Any]:
    registry = build_risk_registry(wiki_root)
    write_json(wiki_root / RISK_REGISTRY_RELATIVE_PATH, registry)
    provenance = provenance_payload(
        wiki_root,
        artifact_id="risk-registry",
        artifact_kind="risk-registry",
        relative_path=RISK_REGISTRY_RELATIVE_PATH,
        title="Risk Registry",
        generated_at=registry["generatedAt"],
        source_hashes=collect_source_hashes([wiki_root / "core" / "RISKS.md", *report_risk_signal_json_paths(wiki_root)]),
    )
    update_manifest(wiki_root, provenance)
    return registry


def write_decision_registry(wiki_root: Path, project_folder: Path) -> dict[str, Any]:
    registry = build_decision_registry(wiki_root)
    write_json(wiki_root / DECISION_REGISTRY_RELATIVE_PATH, registry)
    provenance = provenance_payload(
        wiki_root,
        artifact_id="decision-registry",
        artifact_kind="decision-registry",
        relative_path=DECISION_REGISTRY_RELATIVE_PATH,
        title="Decision Registry",
        generated_at=registry["generatedAt"],
        source_hashes=collect_source_hashes([wiki_root / "core" / "DECISIONS.md", *report_decision_signal_json_paths(wiki_root)]),
    )
    update_manifest(wiki_root, provenance)
    return registry


def active_registry_risks(registry: dict[str, Any]) -> list[dict[str, Any]]:
    risks = [risk for risk in registry.get("risks", []) if isinstance(risk, dict) and risk_is_active(risk)]
    return sorted(risks, key=lambda item: (severity_rank(item.get("severity", "")), item.get("title", "").lower()))


def registry_decisions(registry: dict[str, Any]) -> list[dict[str, Any]]:
    decisions = [decision for decision in registry.get("decisions", []) if isinstance(decision, dict)]
    return sorted(decisions, key=lambda item: sortable_date_key(item.get("date", ""), 0))


def risk_signal_status(signal: dict[str, str], active_titles: list[str], closed_titles: list[str]) -> str:
    if risk_title_matches(signal["title"], active_titles):
        return "In active register"
    if risk_title_matches(signal["title"], closed_titles):
        return "Closed or accepted"
    return "Needs promotion"


def core_current_read_html(title: str, summary: str) -> str:
    return f"""
  <section class="current-read" aria-label="Generated current read">
    <div>
      <h2>Current Read</h2>
      <p>{esc(summary)}</p>
    </div>
  </section>
"""


def source_href(href: str, prefix: str) -> str:
    href = (href or "").strip()
    if not href:
        return ""
    if not href_scheme_allowed(href):
        return ""
    if re.match(r"^(https?://|mailto:|#|/)", href) or href.startswith(("../", "./")):
        return href
    return prefix + href


def source_links_html(links: Any, *, prefix: str = "../", fallback: str = "") -> str:
    values = []
    seen: set[tuple[str, str]] = set()
    for link in array_value(links):
        if isinstance(link, dict):
            label = text_value(link.get("label") or link.get("title") or link.get("href"))
            href = text_value(link.get("href") or link.get("url"))
        else:
            label = text_value(link)
            href = ""
        if not label and not href:
            continue
        key = (label, href)
        if key in seen:
            continue
        seen.add(key)
        resolved = source_href(href, prefix) if href else ""
        if resolved:
            values.append(f'<a href="{esc(resolved)}">{esc(label or href)}</a>')
        else:
            # No href, or a disallowed scheme that source_href rejected: render
            # the label as plain text rather than a dead <a href="">.
            values.append(esc(label or href))
    if not values and fallback:
        values.append(esc(fallback))
    return " / ".join(values)


def registry_filter_controls(table_id: str, rows: list[dict[str, str]], columns: list[dict[str, str]]) -> str:
    filter_rows = [[row.get(column["key"], "") for column in columns] for row in rows]
    control_columns = [{"key": column["key"], "label": column["label"], "index": index} for index, column in enumerate(columns)]
    return table_filter_controls(table_id, filter_rows, control_columns)


def decisions_current_read(registry: dict[str, Any]) -> str:
    decisions = registry_decisions(registry)
    signals = [signal for signal in registry.get("signals", []) if isinstance(signal, dict)]
    intake = [signal for signal in signals if signal.get("status") == "Intake"]
    if not decisions:
        if intake:
            return f"No recorded decisions are captured yet, but {len(intake)} report signal(s) may need promotion into DECISIONS.md. Review the intake queue below and record only durable choices with date, rationale, owner, and revisit trigger."
        return "No recorded decisions are captured yet. Add dated decision rows to DECISIONS.md so future reviews can distinguish durable choices from open questions."

    ordered = sorted(enumerate(decisions), key=lambda item: sortable_date_key(item[1].get("date", ""), item[0]))
    recent = [decision for _index, decision in ordered[-2:]]
    themes = top_themes(decisions, ["title", "context", "options", "rationale", "when"])
    trigger_values = [snippet(decision.get("when", ""), 72) for decision in decisions if has_real_value(decision.get("when"))]
    trigger_counts: dict[str, int] = {}
    for trigger in trigger_values:
        trigger_counts[trigger] = trigger_counts.get(trigger, 0) + 1
    trigger_examples = [trigger for trigger, _count in sorted(trigger_counts.items(), key=lambda item: (-item[1], item[0]))[:2]]

    return " ".join(
        [
            f"The decision log has {len(decisions)} recorded choices, with recurring themes around {phrase_list(themes)}.",
            f"The newest entries are {phrase_list([decision['title'] for decision in recent], fallback='the latest recorded choices')}.",
            f"Reports add {len(signals)} decision signal(s), with {len(intake)} still in intake and not yet recorded as durable choices.",
            f"Revisit pressure is mostly tied to {phrase_list(trigger_examples, fallback='explicit trigger conditions')}, so rows should read as historical decisions unless a trigger is due or marked met.",
            "Use the log below as the durable history; when a review reaffirms, supersedes, or punts a choice, update the source Markdown and regenerate this read.",
        ]
    )


def risks_current_read(registry: dict[str, Any]) -> str:
    risks = active_registry_risks(registry)
    signals = [signal for signal in registry.get("signals", []) if isinstance(signal, dict)]
    unpromoted = [signal for signal in signals if signal.get("status") == "Intake"]

    if not risks and not signals:
        return "No active risks or report risk signals are captured yet. Add rows to RISKS.md or run a Tech Stack or Engineering Risk report so the register can become the operating source of truth."

    high_count = sum(1 for risk in risks if risk["severity"] in {"Critical", "High"})
    themes = top_themes(risks + signals, ["title", "source", "evidence", "impact", "mitigation"])
    due_candidates = sorted(
        [risk for risk in risks if dates_in_text(risk.get("review", ""))],
        key=lambda risk: min(dates_in_text(risk.get("review", ""))),
    )[:2]
    due_text = phrase_list(
        [f"{risk['title']} ({risk['review']})" for risk in due_candidates],
        fallback="the dated next-review fields in the register",
    )

    return " ".join(
        [
            f"The active risk register has {len(risks)} risks, including {high_count} high or critical items, with themes around {phrase_list(themes)}.",
            f"Near-term review attention is on {due_text}.",
            f"Reports add {len(signals)} risk signals, with {len(unpromoted)} still needing promotion, merge, or dismissal from the canonical register.",
            "The Markdown log below remains the source of truth; report signals keep source links so risks can be traced back to the review that surfaced them.",
        ]
    )


def risk_registry_html(registry: dict[str, Any], *, prefix: str = "../") -> str:
    risks = [risk for risk in registry.get("risks", []) if isinstance(risk, dict)]
    if not risks:
        return ""

    rows = []
    filter_rows: list[dict[str, str]] = []
    for risk in risks:
        risk_id = text_value(risk.get("id")) or risk_id_for_title(text_value(risk.get("title")))
        detail_href = source_href(text_value(risk.get("detailPath")) or risk_detail_relative_path(risk_id), prefix)
        status = text_value(risk.get("status") or "Active")
        severity = text_value(risk.get("severity") or "Low")
        owner = text_value(risk.get("owner") or "Unassigned")
        source = text_value(risk.get("source") or "Risk register")
        review = text_value(risk.get("review") or risk.get("nextReview") or "Unscheduled")
        source_html = source_links_html(risk.get("sourceLinks"), prefix=prefix, fallback=source)
        filter_rows.append({"status": status, "severity": severity, "owner": owner, "source": source, "review": review})
        rows.append(
            f"""<tr id="{esc(risk_id)}" data-filter-text="{search_text_attr(risk_id, risk.get("title"), status, severity, owner, source, review, risk.get("evidence"), risk.get("impact"), risk.get("mitigation"))}" data-filter-status="{esc(status)}" data-filter-severity="{esc(severity)}" data-filter-owner="{esc(owner)}" data-filter-source="{esc(source)}" data-filter-review="{esc(review)}">
  <td><a href="{esc(detail_href)}"><code>{esc(risk_id)}</code></a></td>
  <td><a class="registry-title-link" href="{esc(detail_href)}"><strong>{esc(risk.get("title", ""))}</strong></a><br><span>{esc(risk.get("category", ""))}</span></td>
  <td><span class="tag {severity_class(severity)}">{esc(status)}</span></td>
  <td><span class="sev-badge b-{severity_token(severity)}">{esc(severity)}</span></td>
  <td>{esc(owner)}</td>
  <td>{source_html}</td>
  <td>{esc(review)}</td>
  <td>{esc(risk.get("mitigation", ""))}</td>
</tr>"""
        )

    table_id = "canonical-risk-registry"
    controls = registry_filter_controls(
        table_id,
        filter_rows,
        [
            {"key": "status", "label": "Status"},
            {"key": "severity", "label": "Severity"},
            {"key": "owner", "label": "Owner"},
            {"key": "source", "label": "Source"},
            {"key": "review", "label": "Review"},
        ],
    )
    return f"""
  <section class="artifact-section" id="canonical-risks">
    <h2>Canonical Risk Registry</h2>
    <p class="artifact-note">Generated from <code>core/RISKS.md</code>. Each row has a stable ID for links from dashboards and report evidence; edit the Markdown source, then run <code>dzcto refresh</code>.</p>
    {controls}
    <div class="markdown-table" id="{esc(table_id)}" data-filterable-table>
      <table>
        <thead><tr><th>ID</th><th>Risk</th><th>Status</th><th>Severity</th><th>Owner</th><th>Source</th><th>Next Review</th><th>Mitigation</th></tr></thead>
        <tbody>{''.join(rows)}</tbody>
      </table>
    </div>
  </section>
"""


def decision_registry_html(registry: dict[str, Any], *, prefix: str = "../") -> str:
    decisions = registry_decisions(registry)
    if not decisions:
        return ""

    rows = []
    filter_rows: list[dict[str, str]] = []
    for decision in decisions:
        decision_id = text_value(decision.get("id")) or decision_id_for_title(text_value(decision.get("title")))
        detail_href = source_href(text_value(decision.get("detailPath")) or decision_detail_relative_path(decision_id), prefix)
        status = text_value(decision.get("status") or "Recorded")
        owner = text_value(decision.get("owner") or "Founder")
        date = text_value(decision.get("date") or "Unknown")
        revisit = text_value(decision.get("revisitTrigger") or decision.get("when") or "Review trigger")
        source = text_value(decision.get("source") or "Decision log")
        source_html = source_links_html(decision.get("sourceLinks"), prefix=prefix, fallback=source)
        filter_rows.append({"status": status, "owner": owner, "date": date, "source": source})
        rows.append(
            f"""<tr id="{esc(decision_id)}" data-filter-text="{search_text_attr(decision_id, decision.get("title"), status, owner, date, source, decision.get("context"), decision.get("options"), decision.get("rationale"), revisit)}" data-filter-status="{esc(status)}" data-filter-owner="{esc(owner)}" data-filter-date="{esc(date)}" data-filter-source="{esc(source)}">
  <td><a href="{esc(detail_href)}"><code>{esc(decision_id)}</code></a></td>
  <td>{esc(date)}</td>
  <td><a class="registry-title-link" href="{esc(detail_href)}"><strong>{esc(decision.get("title", ""))}</strong></a><br><span>{esc(decision.get("context", ""))}</span></td>
  <td>{esc(decision.get("options", ""))}</td>
  <td>{esc(decision.get("rationale", ""))}</td>
  <td>{esc(owner)}</td>
  <td>{esc(revisit)}</td>
  <td>{source_html}</td>
</tr>"""
        )

    table_id = "canonical-decision-registry"
    controls = registry_filter_controls(
        table_id,
        filter_rows,
        [
            {"key": "status", "label": "Status"},
            {"key": "owner", "label": "Owner"},
            {"key": "date", "label": "Date"},
            {"key": "source", "label": "Source"},
        ],
    )
    return f"""
  <section class="artifact-section" id="canonical-decisions">
    <h2>Canonical Decision Registry</h2>
    <p class="artifact-note">Generated from <code>core/DECISIONS.md</code>. This is the durable decision history; report signals below are intake until promoted into the Markdown source.</p>
    {controls}
    <div class="markdown-table" id="{esc(table_id)}" data-filterable-table>
      <table>
        <thead><tr><th>ID</th><th>Date</th><th>Decision</th><th>Options</th><th>Rationale</th><th>Owner</th><th>Revisit Trigger</th><th>Source</th></tr></thead>
        <tbody>{''.join(rows)}</tbody>
      </table>
    </div>
  </section>
"""


def report_risk_signals_html(registry: dict[str, Any], *, prefix: str = "../") -> str:
    signals = [signal for signal in registry.get("signals", []) if isinstance(signal, dict)]
    if not signals:
        return ""

    rows = []
    filter_rows: list[dict[str, str]] = []
    for signal in signals[:24]:
        status = text_value(signal.get("status") or "Intake")
        tone = "ready" if status == "Matched" else "medium"
        source_kind = text_value(signal.get("source_kind"))
        filter_rows.append({"severity": signal.get("severity", ""), "status": status, "source": source_kind})
        source_html = source_links_html(signal.get("sourceLinks"), prefix=prefix, fallback=text_value(signal.get("source_label")))
        detail = signal["evidence"] or signal["impact"] or "No detail captured in the structured report data."
        if signal.get("matchedRiskId"):
            matched_path = text_value(signal.get("matchedRiskPath")) or risk_detail_relative_path(text_value(signal.get("matchedRiskId")))
            action = f"""Linked to <a href="{esc(source_href(matched_path, prefix))}"><code>{esc(signal["matchedRiskId"])}</code></a>."""
            title_html = f"""<a class="registry-title-link" href="{esc(source_href(matched_path, prefix))}"><strong>{esc(signal["title"])}</strong></a>"""
        else:
            action = esc(signal["mitigation"] or "Promote into RISKS.md with owner, mitigation, source, and next review date.")
            title_html = f"""<strong>{esc(signal["title"])}</strong>"""
        rows.append(
            f"""<tr id="{esc(signal.get("id", ""))}" data-filter-text="{search_text_attr(signal["title"], signal["severity"], status, signal["source_label"], source_kind, detail, signal.get("mitigation", ""), signal.get("matchedRiskId", ""))}" data-filter-severity="{esc(signal["severity"])}" data-filter-status="{esc(status)}" data-filter-source="{esc(source_kind)}">
  <td>{title_html}<br><span class="sev-badge b-{severity_token(signal["severity"])}">{esc(signal["severity"])}</span></td>
  <td><span class="tag {tone}">{esc(status)}</span></td>
  <td>{source_html}</td>
  <td>{esc(detail)}</td>
  <td>{action}</td>
</tr>"""
        )

    table_id = "risk-signal-table"
    controls = registry_filter_controls(
        table_id,
        filter_rows,
        [
            {"key": "severity", "label": "Severity"},
            {"key": "status", "label": "Status"},
            {"key": "source", "label": "Source"},
        ],
    )

    return f"""
  <section class="artifact-section risk-signals" id="risk-signals">
    <h2>Risk Signals From Reports</h2>
    <p class="artifact-note">Generated from structured Tech Stack, Engineering Risk, Weekly Review, and CEO Update report data. Use this as an intake queue; promote actionable signals into <code>RISKS.md</code> so they get an owner, mitigation, source, and dated next review.</p>
    {controls}
    <div class="markdown-table" id="{esc(table_id)}" data-filterable-table>
      <table>
        <thead><tr><th>Signal</th><th>Status</th><th>Source</th><th>Evidence</th><th>Action</th></tr></thead>
        <tbody>{''.join(rows)}</tbody>
      </table>
    </div>
  </section>
"""


def report_decision_signals_html(registry: dict[str, Any], *, prefix: str = "../") -> str:
    signals = [signal for signal in registry.get("signals", []) if isinstance(signal, dict)]
    if not signals:
        return ""

    rows = []
    filter_rows: list[dict[str, str]] = []
    for signal in signals[:24]:
        status = text_value(signal.get("status") or "Intake")
        source_kind = text_value(signal.get("source_kind"))
        filter_rows.append({"status": status, "source": source_kind, "date": text_value(signal.get("date"))})
        source_html = source_links_html(signal.get("sourceLinks"), prefix=prefix, fallback=text_value(signal.get("source_label")))
        if signal.get("matchedDecisionId"):
            matched_path = text_value(signal.get("matchedDecisionPath")) or decision_detail_relative_path(text_value(signal.get("matchedDecisionId")))
            action = f"""Linked to <a href="{esc(source_href(matched_path, prefix))}"><code>{esc(signal["matchedDecisionId"])}</code></a>."""
            title_html = f"""<a class="registry-title-link" href="{esc(source_href(matched_path, prefix))}"><strong>{esc(signal.get("title", ""))}</strong></a>"""
        else:
            action = "Promote into DECISIONS.md when this is a durable choice, not merely an ask or open question."
            title_html = f"""<strong>{esc(signal.get("title", ""))}</strong>"""
        rows.append(
            f"""<tr id="{esc(signal.get("id", ""))}" data-filter-text="{search_text_attr(signal.get("title"), status, source_kind, signal.get("date"), signal.get("context"), signal.get("owner"), signal.get("matchedDecisionId", ""))}" data-filter-status="{esc(status)}" data-filter-source="{esc(source_kind)}" data-filter-date="{esc(signal.get("date", ""))}">
  <td>{title_html}</td>
  <td><span class="tag {'ready' if status == 'Matched' else 'medium'}">{esc(status)}</span></td>
  <td>{source_html}</td>
  <td>{esc(signal.get("context", "") or signal.get("options", "") or "No detail captured in the structured report data.")}</td>
  <td>{action}</td>
</tr>"""
        )

    table_id = "decision-signal-table"
    controls = registry_filter_controls(
        table_id,
        filter_rows,
        [
            {"key": "status", "label": "Status"},
            {"key": "source", "label": "Source"},
            {"key": "date", "label": "Date"},
        ],
    )
    return f"""
  <section class="artifact-section" id="decision-signals">
    <h2>Decision Signals From Reports</h2>
    <p class="artifact-note">Generated from structured report asks and decision fields. Use this as an intake queue; record only durable choices in <code>DECISIONS.md</code>.</p>
    {controls}
    <div class="markdown-table" id="{esc(table_id)}" data-filterable-table>
      <table>
        <thead><tr><th>Signal</th><th>Status</th><th>Source</th><th>Context</th><th>Action</th></tr></thead>
        <tbody>{''.join(rows)}</tbody>
      </table>
    </div>
  </section>
"""


def item_value_html(value: Any, fallback: str = "Not captured") -> str:
    text = text_value(value)
    if not has_real_value(text):
        return f'<span class="empty-item">{esc(fallback)}</span>'
    return inline_markdown(text)


def item_meta_card(label: str, value: Any, *, value_is_html: bool = False) -> str:
    value_html = str(value) if value_is_html else item_value_html(value)
    return f"""<div class="item-meta">
  <span>{esc(label)}</span>
  <strong>{value_html}</strong>
</div>"""


def item_field_html(label: str, value: Any, *, required: bool = False, fallback: str = "Not captured") -> str:
    if not required and not has_real_value(text_value(value)):
        return ""
    return f"""<section class="item-field">
  <h2>{esc(label)}</h2>
  <p>{item_value_html(value, fallback)}</p>
</section>"""


def registry_source_card(
    *,
    item_id: str,
    title: str,
    source_document: str,
    source_section: str,
    source_links: Any,
    prefix: str,
    table_href: str,
) -> str:
    source_links = source_links_html(source_links, prefix=prefix, fallback=source_document)
    section_html = f"<p><strong>Section</strong> {esc(source_section)}</p>" if has_real_value(source_section) else ""
    return f"""<article class="reference-card">
  <div class="reference-top">
    <div>
      <h3>{esc(title)}</h3>
      <p>{source_links}</p>
    </div>
    <a class="reference-link" href="{esc(source_href(table_href, prefix))}"><code>{esc(item_id)}</code></a>
  </div>
  {section_html}
</article>"""


def item_reference_card(signal: dict[str, Any], *, prefix: str, item_kind: str) -> str:
    source_html = source_links_html(signal.get("sourceLinks"), prefix=prefix, fallback=text_value(signal.get("source_label")))
    source_kind = text_value(signal.get("source_kind") or signal.get("kind") or "Report")
    date = text_value(signal.get("date"))
    if item_kind == "risk":
        badge = f'<span class="sev-badge b-{severity_token(text_value(signal.get("severity")))}">{esc(signal.get("severity") or "Low")}</span>'
        fields = [
            ("Evidence", signal.get("evidence")),
            ("Impact", signal.get("impact")),
            ("Mitigation", signal.get("mitigation")),
        ]
    else:
        badge = f'<span class="tag ready">{esc(signal.get("status") or "Matched")}</span>'
        fields = [
            ("Context", signal.get("context")),
            ("Options", signal.get("options")),
            ("Owner", signal.get("owner")),
        ]
    field_html = "\n".join(
        f'<p><strong>{esc(label)}</strong> {item_value_html(value)}</p>'
        for label, value in fields
        if has_real_value(text_value(value))
    )
    if not field_html:
        field_html = '<p class="empty-item">No additional structured detail was captured in this report signal.</p>'
    return f"""<article class="reference-card" id="{esc(signal.get("id", ""))}">
  <div class="reference-top">
    <div>
      <h3>{esc(signal.get("title", ""))}</h3>
      <p>{source_html}</p>
    </div>
    {badge}
  </div>
  <div class="reference-meta">
    <span>{esc(source_kind)}</span>
    {f'<span>{esc(date)}</span>' if date else ''}
  </div>
  {field_html}
</article>"""


def item_references_html(
    *,
    item_id: str,
    canonical_card: str,
    signals: list[dict[str, Any]],
    prefix: str,
    item_kind: str,
) -> str:
    signal_cards = "\n".join(item_reference_card(signal, prefix=prefix, item_kind=item_kind) for signal in signals)
    count = len(signals) + 1
    return f"""
  <section class="artifact-section item-references" id="references">
    <div class="section-heading-line">
      <h2>Referenced By</h2>
      <span>{esc(pluralize(count, "reference"))}</span>
    </div>
    <div class="reference-list">
      {canonical_card}
      {signal_cards if signal_cards else '<p class="empty-item">No report signals currently reference this item.</p>'}
    </div>
  </section>
"""


def risk_detail_html(risk: dict[str, Any], registry: dict[str, Any], *, prefix: str = "../") -> str:
    risk_id = text_value(risk.get("id")) or risk_id_for_title(text_value(risk.get("title")))
    status = text_value(risk.get("status") or "Active")
    severity = text_value(risk.get("severity") or "Low")
    owner = text_value(risk.get("owner") or "Unassigned")
    review = text_value(risk.get("review") or risk.get("nextReview") or "Unscheduled")
    source = text_value(risk.get("source") or "Risk register")
    source_html = source_links_html(risk.get("sourceLinks"), prefix=prefix, fallback=source)
    source_doc = text_value(risk.get("sourceDocument") or "core/RISKS.md")
    signals = [
        signal
        for signal in registry.get("signals", [])
        if isinstance(signal, dict) and text_value(signal.get("matchedRiskId")) == risk_id
    ]
    canonical_card = registry_source_card(
        item_id=risk_id,
        title="Canonical risk row",
        source_document=source_doc,
        source_section=text_value(risk.get("sourceSection")),
        source_links=risk.get("sourceLinks"),
        prefix=prefix,
        table_href=f"core/risks.html#{risk_id}",
    )
    return f"""
  <section class="item-summary">
    <div class="item-id"><code>{esc(risk_id)}</code></div>
    <p>{esc(risk.get("impact") or risk.get("evidence") or risk.get("mitigation") or "Canonical operating risk.")}</p>
  </section>
  <div class="item-meta-grid">
    {item_meta_card("Status", f'<span class="tag {severity_class(status)}">{esc(status)}</span>', value_is_html=True)}
    {item_meta_card("Severity", f'<span class="sev-badge b-{severity_token(severity)}">{esc(severity)}</span>', value_is_html=True)}
    {item_meta_card("Owner", owner)}
    {item_meta_card("Next Review", review)}
    {item_meta_card("Source", source_html, value_is_html=True)}
  </div>
  <div class="item-field-grid">
    {item_field_html("Evidence", risk.get("evidence"), required=True)}
    {item_field_html("Business Impact", risk.get("impact"), required=True)}
    {item_field_html("Mitigation", risk.get("mitigation"), required=True)}
    {item_field_html("Category", risk.get("category"))}
  </div>
  {item_references_html(item_id=risk_id, canonical_card=canonical_card, signals=signals, prefix=prefix, item_kind="risk")}
  <div class="source-footnote">
    <span>Source <code>{esc(source_doc)}</code> / generated risk detail</span>
    <span>Updated {esc(dt.date.today().isoformat())}</span>
  </div>
"""


def decision_detail_html(decision: dict[str, Any], registry: dict[str, Any], *, prefix: str = "../") -> str:
    decision_id = text_value(decision.get("id")) or decision_id_for_title(text_value(decision.get("title")))
    status = text_value(decision.get("status") or "Recorded")
    owner = text_value(decision.get("owner") or "Founder")
    date = text_value(decision.get("date") or "Unknown")
    revisit = text_value(decision.get("revisitTrigger") or decision.get("when") or "Review trigger")
    source = text_value(decision.get("source") or "Decision log")
    source_html = source_links_html(decision.get("sourceLinks"), prefix=prefix, fallback=source)
    source_doc = text_value(decision.get("sourceDocument") or "core/DECISIONS.md")
    signals = [
        signal
        for signal in registry.get("signals", [])
        if isinstance(signal, dict) and text_value(signal.get("matchedDecisionId")) == decision_id
    ]
    canonical_card = registry_source_card(
        item_id=decision_id,
        title="Canonical decision row",
        source_document=source_doc,
        source_section=text_value(decision.get("sourceSection")),
        source_links=decision.get("sourceLinks"),
        prefix=prefix,
        table_href=f"core/decisions.html#{decision_id}",
    )
    return f"""
  <section class="item-summary">
    <div class="item-id"><code>{esc(decision_id)}</code></div>
    <p>{esc(decision.get("rationale") or decision.get("context") or "Canonical recorded decision.")}</p>
  </section>
  <div class="item-meta-grid">
    {item_meta_card("Status", f'<span class="tag ready">{esc(status)}</span>', value_is_html=True)}
    {item_meta_card("Date", date)}
    {item_meta_card("Owner", owner)}
    {item_meta_card("Revisit Trigger", revisit)}
    {item_meta_card("Source", source_html, value_is_html=True)}
  </div>
  <div class="item-field-grid">
    {item_field_html("Context", decision.get("context"), required=True)}
    {item_field_html("Options Considered", decision.get("options"), required=True)}
    {item_field_html("Rationale", decision.get("rationale"), required=True)}
  </div>
  {item_references_html(item_id=decision_id, canonical_card=canonical_card, signals=signals, prefix=prefix, item_kind="decision")}
  <div class="source-footnote">
    <span>Source <code>{esc(source_doc)}</code> / generated decision detail</span>
    <span>Updated {esc(dt.date.today().isoformat())}</span>
  </div>
"""


def relative_date(value: dt.date | None, today: dt.date) -> str:
    if not value:
        return "unscheduled"
    delta = (value - today).days
    if delta == 0:
        return "today"
    if delta < 0:
        return f"{abs(delta)}d ago"
    if delta < 7:
        return f"in {delta}d"
    if delta < 31:
        return f"in {round(delta / 7)}w"
    return f"in {round(delta / 30)}mo"


def cadence_rows(cadence_rules: list[dict[str, Any]], reports_dir: Path, today: dt.date) -> list[dict[str, str]]:
    rows = []
    for rule in cadence_rules:
        latest = latest_report_date(reports_dir, rule["folder"])
        next_due = latest + dt.timedelta(days=rule["interval_days"]) if latest else today
        rows.append(
            {
                "name": str(rule["label"]),
                "cadence": str(rule["cadence"]),
                "day": str(rule.get("day") or ""),
                "last": latest.isoformat() if latest else "No runs",
                "next": relative_date(next_due, today),
            }
        )
    return rows


def core_icon(doc: str) -> str:
    return {
        "STRATEGY.md": "S",
        "TEAM.md": "T",
        "OPERATING_CADENCE.md": "C",
        "DECISIONS.md": "D",
        "RISKS.md": "R",
    }.get(doc, "C")


def search_text_attr(*values: Any) -> str:
    return esc(plain_markdown(" ".join(text_value(value) for value in values)).lower())


def command_center_css() -> str:
    return """
:root {
  --bg: #f4f6f9;
  --surface: #ffffff;
  --surface-2: #f7f9fb;
  --surface-3: #eef2f6;
  --ink: #131b29;
  --ink-2: #3c4858;
  --muted: #687587;
  --faint: #97a2b1;
  --line: #e0e6ee;
  --line-2: #d3dbe5;
  --accent: #11657f;
  --accent-2: #0c4d62;
  --accent-soft: #e4f1f4;
  --accent-ink: #0a3a4a;
  --crit: #b3261e;
  --crit-soft: #fbe6e4;
  --crit-line: #f0c2bd;
  --high: #b5560c;
  --high-soft: #fbecdd;
  --high-line: #f1cda6;
  --med: #8a6500;
  --med-soft: #f7f0d8;
  --med-line: #e5d49b;
  --low: #4a5a6e;
  --low-soft: #eaeef3;
  --low-line: #d2dae3;
  --good: #176a44;
  --good-soft: #e3f4ec;
  --good-line: #b4ddc6;
  --r-sm: 7px;
  --r-md: 10px;
  --r-lg: 14px;
  --r-pill: 999px;
  --gap: 14px;
  --shadow-sm: 0 1px 2px rgba(19,27,41,.05), 0 1px 1px rgba(19,27,41,.04);
  --shadow-md: 0 4px 16px rgba(19,27,41,.08), 0 1px 3px rgba(19,27,41,.05);
  --ring: 0 0 0 3px rgba(17,101,127,.28);
  --nav-bg: rgba(244,246,249,.92);
  --ui: -apple-system, BlinkMacSystemFont, "Segoe UI", "Helvetica Neue", Arial, sans-serif;
  --mono: ui-monospace, "SF Mono", SFMono-Regular, Menlo, Consolas, "Liberation Mono", monospace;
  --maxw: 1220px;
}
html[data-theme="dark"] {
  --bg: #0c121b;
  --surface: #131c28;
  --surface-2: #18222f;
  --surface-3: #1f2a39;
  --ink: #eaf0f7;
  --ink-2: #c2cdda;
  --muted: #8c99a9;
  --faint: #5f6e80;
  --line: #243140;
  --line-2: #2d3c4d;
  --accent: #4db6d4;
  --accent-2: #74cbe4;
  --accent-soft: #16323d;
  --accent-ink: #aee0ef;
  --crit: #ff8e84;
  --crit-soft: #3a1714;
  --crit-line: #5e231d;
  --high: #f0a85e;
  --high-soft: #37220f;
  --high-line: #5a3818;
  --med: #e0c25a;
  --med-soft: #322a10;
  --med-line: #524417;
  --low: #9fb0c2;
  --low-soft: #1d2733;
  --low-line: #2c3a4a;
  --good: #5fd197;
  --good-soft: #10291d;
  --good-line: #1d4632;
  --shadow-sm: 0 1px 2px rgba(0,0,0,.4);
  --shadow-md: 0 8px 28px rgba(0,0,0,.5);
  --ring: 0 0 0 3px rgba(77,182,212,.32);
  --nav-bg: rgba(12,18,27,.92);
}
* { box-sizing: border-box; }
html { scroll-behavior: smooth; scroll-padding-top: 76px; }
body {
  margin: 0;
  background: var(--bg);
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
  min-height: 54px;
  padding: 8px max(18px, calc((100vw - var(--maxw)) / 2 + 26px));
  border-bottom: 1px solid var(--line);
  background: var(--nav-bg);
  backdrop-filter: blur(14px);
  box-shadow: 0 1px 2px rgba(19,27,41,.04);
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
.app { max-width: var(--maxw); margin: 0 auto; padding: 38px 26px 90px; }
.masthead { display: grid; grid-template-columns: 1fr auto; gap: 26px; align-items: start; margin-bottom: 26px; }
.eyebrow {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  color: var(--accent);
  font-size: 12px;
  font-weight: 800;
  letter-spacing: 0;
  margin-bottom: 12px;
  text-transform: uppercase;
}
.eyebrow::before { content: ""; width: 18px; height: 2px; background: var(--accent); border-radius: 2px; }
h1.title { font-size: 38px; font-weight: 800; }
.title .light { color: var(--muted); font-weight: 500; }
.lede { max-width: 680px; margin-top: 12px; color: var(--ink-2); font-size: 15.5px; }
.masthead-stamp { margin-top: 8px; color: var(--muted); font-family: var(--mono); font-size: 12px; }
.masthead-side { display: flex; flex-direction: column; align-items: flex-end; gap: 10px; min-width: min(300px, 100%); }
.masthead-mobile-tools { display: none; }
.util { display: flex; gap: 8px; justify-content: flex-end; }
.theme-btn, .icon-btn {
  min-height: 34px;
  border: 1px solid var(--line-2);
  background: var(--surface);
  color: var(--ink-2);
  border-radius: var(--r-md);
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
  border-radius: var(--r-md);
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
.kpis { display: grid; grid-template-columns: repeat(6, 1fr); gap: var(--gap); margin: 6px 0 30px; }
.kpi {
  display: block;
  position: relative;
  overflow: hidden;
  background: var(--surface);
  border: 1px solid var(--line);
  border-radius: var(--r-md);
  padding: 14px 15px;
  box-shadow: var(--shadow-sm);
  color: var(--ink);
  text-decoration: none;
  transition: .15s;
}
.kpi:hover { border-color: var(--accent); box-shadow: var(--shadow-md); text-decoration: none; transform: translateY(-1px); }
.k-label { color: var(--muted); font-size: 11px; font-weight: 800; letter-spacing: 0; text-transform: uppercase; }
.k-val { display: flex; align-items: baseline; gap: 6px; margin-top: 7px; font-size: 26px; font-weight: 800; }
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
.section > summary { display: flex; align-items: center; gap: 14px; padding: 22px 2px 20px; cursor: pointer; list-style: none; }
.section > summary::-webkit-details-marker, .risk > summary::-webkit-details-marker { display: none; }
.chev { width: 9px; height: 9px; border-right: 2px solid var(--faint); border-bottom: 2px solid var(--faint); transform: rotate(-45deg); transition: transform .18s ease; flex: 0 0 auto; }
.section[open] > summary .chev { transform: rotate(45deg); }
.sec-title { color: var(--ink); font-size: 21px; font-weight: 800; white-space: nowrap; }
.sec-num { color: var(--faint); font-family: var(--mono); font-size: 12px; font-weight: 600; }
.sec-meta { display: flex; align-items: center; gap: 10px; margin-left: auto; color: var(--muted); font-size: 13px; text-align: right; }
.sec-body { padding: 4px 0 30px; }
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
.reports, .reports-grid { display: grid; grid-template-columns: 1fr 1fr; gap: var(--gap); }
.report, .report-card {
  display: flex;
  flex-direction: column;
  gap: 10px;
  border: 1px solid var(--line);
  border-radius: var(--r-md);
  background: var(--surface);
  box-shadow: var(--shadow-sm);
  padding: 16px 17px;
  color: var(--ink);
}
.report:hover, .report-card:hover { border-color: var(--accent); text-decoration: none; }
.report.empty, .report-card.empty { background: var(--surface-2); border-style: dashed; box-shadow: none; }
.rp-top { display: flex; align-items: flex-start; justify-content: space-between; gap: 10px; }
.rp-name, .report-title { color: var(--ink); font-size: 15px; font-weight: 800; }
.rp-count, .report-count { color: var(--muted); background: var(--surface-3); border-radius: var(--r-pill); padding: 3px 9px; font-size: 10.5px; font-weight: 800; text-transform: uppercase; white-space: nowrap; }
.rp-prev { color: var(--ink-2); font-size: 12.5px; line-height: 1.55; }
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
.learn-stats, .summary, .grid { display: grid; grid-template-columns: repeat(3, 1fr); gap: 8px; margin: 14px 0; }
.learn-stats .ls, .metric { background: var(--surface-2); border: 1px solid var(--line); border-radius: var(--r-sm); padding: 9px 10px; text-align: center; }
.learn-stats b, .metric .value, .metric strong { display: block; color: var(--ink); font-size: 20px; font-weight: 800; }
.learn-stats span, .metric .label, .metric span { color: var(--muted); font-size: 10.5px; font-weight: 800; letter-spacing: 0; text-transform: uppercase; }
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
.artifact-section { margin-top: 30px; border-top: 1px solid var(--line); padding-top: 22px; }
.artifact-section:first-of-type { margin-top: 0; border-top: 0; padding-top: 0; }
.artifact-note { margin: 8px 0 14px; color: var(--ink-2); font-size: 13px; line-height: 1.5; }
.artifact-list { display: grid; gap: 11px; margin: 16px 0 24px; padding-left: 22px; list-style: disc; }
.artifact-list li { padding: 0 0 0 2px; color: var(--ink-2); font-size: 14px; line-height: 1.55; }
.artifact-list li::marker { color: var(--accent); }
.artifact-list strong { color: var(--ink); font-weight: 800; }
.artifact-list span, .artifact-list em, .artifact-list small { display: block; margin-top: 3px; color: var(--muted); }
.artifact-list em, .artifact-list small { font-size: 13px; font-style: normal; }
.report-body > p:first-child {
  max-width: 980px;
  color: var(--ink-2);
  font-size: 15px;
  line-height: 1.58;
}
.report-attention {
  max-width: 980px;
  margin: 16px 0 4px;
  border-top: 1px solid var(--line);
  padding-top: 13px;
}
.attention-kicker { color: var(--muted); font-size: 11px; font-weight: 800; letter-spacing: 0; text-transform: uppercase; }
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
  .kpis { grid-template-columns: repeat(3, 1fr); }
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
  .help-guide { grid-template-columns: 1fr; }
  .help-guide-row { grid-template-columns: 1fr; gap: 6px; }
  .item-field-grid { grid-template-columns: 1fr; }
  h1.title { font-size: 30px; }
}
@media (max-width: 560px) {
  .app { padding: 24px 16px 70px; }
  .kpis, .core, .status-grid, .summary, .grid, .item-meta-grid { grid-template-columns: 1fr 1fr; }
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


def write_learning_index(wiki_root: Path, project_folder: Path, company: str, items: list[dict[str, Any]], reviews: list[dict[str, Any]], today: dt.date) -> None:
    learning_dir = wiki_root / "learning"
    learning_dir.mkdir(parents=True, exist_ok=True)
    ensure_sidecar(wiki_root, project_folder, "render-learning-index")
    active = sorted(
        active_learning_items(items),
        key=lambda item: (
            0 if int(item.get("seen_count", 0) or 0) == 0 else 1,
            str(item.get("due_on", "")),
            str(item.get("title", "")).lower(),
        ),
    )

    if active:
        item_rows = "".join(
            f"""
<tr>
  <td><strong>{esc(item.get("title"))}</strong><br><span>{esc(item.get("summary"))}</span></td>
  <td>{esc(learning_item_status(item, today))}</td>
  <td>{esc(item.get("due_on") or "Unknown")}</td>
  <td>{esc(item.get("box", 0))}</td>
  <td>{esc(item.get("seen_count", 0))}</td>
  <td>{esc(item.get("last_rating") or "Not reviewed")}</td>
  <td>{esc(item.get("source") or "Unknown")}</td>
</tr>
"""
            for item in active
        )
    else:
        item_rows = '<tr><td colspan="7" class="empty-item">No learning items yet. Run the learning skill to add the first system concept.</td></tr>'

    if reviews:
        review_rows = "\n".join(
            f"<li><strong>{esc(review.get('reviewed_on'))}</strong> {esc(review.get('title') or review.get('id'))} - {esc(review.get('rating_label') or review.get('rating'))}, next due {esc(review.get('due_on'))}</li>"
            for review in reversed(reviews[-12:])
        )
    else:
        review_rows = '<li class="empty-item">No reviews logged yet.</li>'

    counts = learning_counts(items, today)
    checklist = read_learning_checklist_progress(learning_dir)
    checklist_path = checklist.get("path")
    checklist_html = (
        f'<p><a href="{esc(checklist_path.relative_to(learning_dir).as_posix())}">Mastery checklist</a>: {esc(checklist["confirmed"])} of {esc(checklist["total"])} confirmed ({esc(checklist["percent"])}%).</p>'
        if checklist_path
        else '<p class="empty-item">No mastery checklist yet. Seed or run learning to create one.</p>'
    )
    generated_at = utc_now()
    provenance = provenance_payload(
        wiki_root,
        artifact_id="learning-index",
        artifact_kind="learning-index",
        relative_path="learning/index.html",
        title=f"{company} Learning",
        generated_at=generated_at,
    )
    content = f"""
  <div class="summary">
    <div class="metric"><span>Active</span><strong>{counts["active"]}</strong></div>
    <div class="metric"><span>Due</span><strong>{counts["due"]}</strong></div>
    <div class="metric"><span>New</span><strong>{counts["new"]}</strong></div>
  </div>
  <section class="artifact-section">
    <h2>How Scoring Works</h2>
    <p>Reply with <code>Needs Work</code>, <code>Familiar</code>, or <code>Confident</code>. Needs Work brings the item back tomorrow, Familiar moves it forward one box, and Confident moves it forward two boxes.</p>
  </section>
  <section class="artifact-section">
    <h2>Mastery Checklist</h2>
    {checklist_html}
  </section>
  <section class="artifact-section">
    <h2>Items</h2>
    <table>
      <thead>
        <tr><th>Item</th><th>Status</th><th>Due</th><th>Box</th><th>Seen</th><th>Last rating</th><th>Source</th></tr>
      </thead>
      <tbody>{item_rows}</tbody>
    </table>
  </section>
  <section class="artifact-section">
    <h2>Recent Reviews</h2>
    <ul>{review_rows}</ul>
  </section>
"""
    body = page_shell(
        content,
        prefix="../",
        eyebrow="Learning - Day Zero CTO",
        title=f"{company} Learning",
        subtitle="Spaced repetition for system knowledge. Each prompt teaches one concept, records a self-rating, updates the mastery checklist, and schedules the next review.",
        crumbs=[("Learning", None)],
        sticky_title=dashboard_title(company),
    )
    write_html_page(learning_dir / "index.html", f"{company} Learning", body, provenance)
    update_manifest(wiki_root, provenance)


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


def refresh_structured_report_pages(
    wiki_root: Path,
    project_folder: Path,
    sticky_title: str,
    *,
    risk_registry: dict[str, Any] | None = None,
    decision_registry: dict[str, Any] | None = None,
) -> None:
    reports_dir = wiki_root / "reports"
    for kind in REPORT_FOLDERS:
        report_dir = reports_dir / kind
        if not report_dir.exists():
            continue
        for json_path in sorted(report_dir.glob("*.json")):
            if json_path.name == "data.json":
                continue
            report_path = json_path.with_suffix(".html")
            if not report_path.exists():
                continue
            data = read_json_file(json_path, {})
            if not isinstance(data, dict):
                continue
            title = html_title(report_path) or report_name(report_path)
            date = report_run_date(report_path)
            body = render_structured_report(kind, data, risk_registry=risk_registry, decision_registry=decision_registry)
            provenance = provenance_payload(
                wiki_root,
                artifact_id=f"{kind}:{report_path.stem}",
                artifact_kind=kind,
                relative_path=report_path.relative_to(wiki_root).as_posix(),
                title=title,
                generated_at=utc_now(),
                source_hashes=collect_source_hashes([json_path]),
                extra={"reportDate": date},
            )
            report_path.write_text(render_report_page(title, date, kind, body, provenance, sticky_title, lede=report_lead_summary(data)), encoding="utf-8")
            update_manifest(wiki_root, provenance)


def write_setup_page(wiki_root: Path, project_folder: Path, company: str, setup_items: list[dict[str, str]]) -> None:
    setup_dir = wiki_root / "setup"
    setup_dir.mkdir(parents=True, exist_ok=True)
    ensure_sidecar(wiki_root, project_folder, "render-setup-page")
    complete = sum(1 for item in setup_items if item["state"] == "done")
    remaining = len(setup_items) - complete
    status = "Complete" if remaining == 0 else "Needs attention"
    status_class = "status-good" if remaining == 0 else "status-warn"
    generated_at = utc_now()
    provenance = provenance_payload(
        wiki_root,
        artifact_id="setup-checklist",
        artifact_kind="setup-checklist",
        relative_path="setup/index.html",
        title=f"{company} Setup Checklist",
        generated_at=generated_at,
    )
    content = f"""
  <div class="status-grid">
    <div class="status-card {status_class}"><span>Status</span><strong>{esc(status)}</strong></div>
    <div class="status-card"><span>Complete</span><strong>{esc(complete)}/{esc(len(setup_items))}</strong></div>
    <div class="status-card"><span>Remaining</span><strong>{esc(remaining)}</strong></div>
    <div class="status-card"><span>Updated</span><strong>{esc(dt.date.today().isoformat())}</strong></div>
  </div>
  {setup_checklist_html(setup_items, prefix="../")}
  <section class="artifact-section prose">
    <h2>How to Use This Page</h2>
    <p>This checklist is the setup reference for the Day Zero CTO command center. If the dashboard highlights setup, finish the items here first. After everything is complete, keep this page as a lightweight audit and handoff reference.</p>
    <p>For terminal checks, run <code>dzcto status "{esc(project_folder)}"</code>. For guided updates to Strategy, Team, Operating Cadence, Decisions, or Risks, ask an agent to use <code>day-zero-cto:refine-core-context</code>.</p>
  </section>
"""
    body = page_shell(
        content,
        prefix="../",
        eyebrow="Setup - Day Zero CTO",
        title=f"{company} Setup Checklist",
        subtitle="Onboarding readiness, setup health, and what must be complete before relying on the command center.",
        crumbs=[("Setup", None)],
        sticky_title=dashboard_title(company),
    )
    write_html_page(setup_dir / "index.html", f"{company} Setup Checklist", body, provenance)
    update_manifest(wiki_root, provenance)


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


def remove_manifest_artifacts(wiki_root: Path, relative_paths: set[str]) -> None:
    if not relative_paths:
        return
    manifest_path = sidecar_dir(wiki_root) / "manifest.json"
    manifest = read_json(manifest_path, {})
    artifacts = manifest.get("artifacts") if isinstance(manifest, dict) else None
    if not isinstance(artifacts, list):
        return
    kept = [artifact for artifact in artifacts if not isinstance(artifact, dict) or str(artifact.get("relativePath") or "") not in relative_paths]
    if len(kept) != len(artifacts):
        manifest["artifacts"] = kept
        manifest["updatedAt"] = utc_now()
        write_json(manifest_path, manifest)


def prune_detail_pages(wiki_root: Path, directory_name: str, valid_relative_paths: set[str], artifact_kind: str) -> None:
    detail_dir = wiki_root / directory_name
    if not detail_dir.exists():
        return
    valid_names = {Path(relative).name for relative in valid_relative_paths}
    removed: set[str] = set()
    marker = f'"artifactKind": "{artifact_kind}"'
    for path in detail_dir.glob("*.html"):
        if path.name in valid_names:
            continue
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            text = ""
        if marker not in text:
            continue
        path.unlink()
        removed.add(path.relative_to(wiki_root).as_posix())
    remove_manifest_artifacts(wiki_root, removed)


def write_risk_detail_pages(wiki_root: Path, project_folder: Path, registry: dict[str, Any], sticky_title: str) -> None:
    risk_dir = wiki_root / "risks"
    risk_dir.mkdir(parents=True, exist_ok=True)
    source_hashes = collect_source_hashes([wiki_root / "core" / "RISKS.md", *report_risk_signal_json_paths(wiki_root)])
    valid_paths: set[str] = set()
    for risk in registry.get("risks", []):
        if not isinstance(risk, dict):
            continue
        risk_id = text_value(risk.get("id")) or risk_id_for_title(text_value(risk.get("title")))
        relative_path = text_value(risk.get("detailPath")) or risk_detail_relative_path(risk_id)
        risk["detailPath"] = relative_path
        valid_paths.add(relative_path)
        generated_at = utc_now()
        provenance = provenance_payload(
            wiki_root,
            artifact_id=f"risk:{risk_id}",
            artifact_kind="risk-detail",
            relative_path=relative_path,
            title=text_value(risk.get("title")) or risk_id,
            generated_at=generated_at,
            source_hashes=source_hashes,
            extra={"registryId": risk_id, "sourceDocument": "core/RISKS.md"},
        )
        body = page_shell(
            risk_detail_html(risk, registry, prefix="../"),
            prefix="../",
            eyebrow="Risk - Day Zero CTO",
            title=text_value(risk.get("title")) or risk_id,
            subtitle="Canonical risk detail, source fields, and report references.",
            crumbs=[("Core", "core/risks.html"), ("Risks", "core/risks.html"), (risk_id, None)],
            sticky_title=sticky_title,
        )
        write_html_page(wiki_root / relative_path, text_value(risk.get("title")) or risk_id, body, provenance)
        update_manifest(wiki_root, provenance)
    prune_detail_pages(wiki_root, "risks", valid_paths, "risk-detail")


def write_decision_detail_pages(wiki_root: Path, project_folder: Path, registry: dict[str, Any], sticky_title: str) -> None:
    decision_dir = wiki_root / "decisions"
    decision_dir.mkdir(parents=True, exist_ok=True)
    source_hashes = collect_source_hashes([wiki_root / "core" / "DECISIONS.md", *report_decision_signal_json_paths(wiki_root)])
    valid_paths: set[str] = set()
    for decision in registry.get("decisions", []):
        if not isinstance(decision, dict):
            continue
        decision_id = text_value(decision.get("id")) or decision_id_for_title(text_value(decision.get("title")))
        relative_path = text_value(decision.get("detailPath")) or decision_detail_relative_path(decision_id)
        decision["detailPath"] = relative_path
        valid_paths.add(relative_path)
        generated_at = utc_now()
        provenance = provenance_payload(
            wiki_root,
            artifact_id=f"decision:{decision_id}",
            artifact_kind="decision-detail",
            relative_path=relative_path,
            title=text_value(decision.get("title")) or decision_id,
            generated_at=generated_at,
            source_hashes=source_hashes,
            extra={"registryId": decision_id, "sourceDocument": "core/DECISIONS.md"},
        )
        body = page_shell(
            decision_detail_html(decision, registry, prefix="../"),
            prefix="../",
            eyebrow="Decision - Day Zero CTO",
            title=text_value(decision.get("title")) or decision_id,
            subtitle="Canonical decision detail, source fields, and report references.",
            crumbs=[("Core", "core/decisions.html"), ("Decisions", "core/decisions.html"), (decision_id, None)],
            sticky_title=sticky_title,
        )
        write_html_page(wiki_root / relative_path, text_value(decision.get("title")) or decision_id, body, provenance)
        update_manifest(wiki_root, provenance)
    prune_detail_pages(wiki_root, "decisions", valid_paths, "decision-detail")


def write_core_pages(
    wiki_root: Path,
    project_folder: Path,
    *,
    risk_registry: dict[str, Any] | None = None,
    decision_registry: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    core_dir = wiki_root / "core"
    core_dir.mkdir(parents=True, exist_ok=True)
    stable_title = dashboard_title(company_name(core_dir / "STRATEGY.md", project_folder, project_config(wiki_root)))
    risk_registry = risk_registry or build_risk_registry(wiki_root)
    decision_registry = decision_registry or build_decision_registry(wiki_root)
    pages: list[dict[str, Any]] = []
    for doc in CORE_DOCS:
        title, description = CORE_DOC_META.get(doc, (doc, "Core CTO context."))
        source_path = core_dir / doc
        relative_path = f"core/{core_doc_html_name(doc)}"
        if source_path.exists():
            source_text = source_path.read_text(encoding="utf-8")
            source_paths = [source_path]
            if doc == "RISKS.md":
                source_paths.extend(report_risk_signal_json_paths(wiki_root))
                content_html = risk_registry_html(risk_registry, prefix="../")
            elif doc == "DECISIONS.md":
                source_paths.extend(report_decision_signal_json_paths(wiki_root))
                content_html = decision_registry_html(decision_registry, prefix="../")
            else:
                content_html = f"""
  <section class="artifact-section prose">
    {markdown_to_html(source_text)}
  </section>
"""
            source_hash = collect_source_hashes(source_paths)
        else:
            action = CORE_DOC_EMPTY_ACTION.get(doc, "day-zero-cto:refine-core-context")
            content_html = f"""
  <section class="artifact-section prose">
    <p class="empty-item">No {esc(title.lower())} context captured yet. Ask your agent to use <code>{esc(action)}</code> to set it up, then run <code>dzcto refresh</code>.</p>
  </section>
"""
            source_hash = {}

        current_read_html = ""
        extra_core_html = ""
        if source_path.exists() and doc == "DECISIONS.md":
            current_read_html = core_current_read_html(title, decisions_current_read(decision_registry))
            extra_core_html = report_decision_signals_html(decision_registry, prefix="../")
        elif source_path.exists() and doc == "RISKS.md":
            current_read_html = core_current_read_html(title, risks_current_read(risk_registry))
            extra_core_html = report_risk_signals_html(risk_registry, prefix="../")

        provenance = provenance_payload(
            wiki_root,
            artifact_id=f"core:{Path(doc).stem.lower()}",
            artifact_kind="core-context",
            relative_path=relative_path,
            title=title,
            generated_at=utc_now(),
            source_hashes=source_hash,
        )
        content = f"""
  {current_read_html}
  {extra_core_html}
  {content_html}
  <div class="source-footnote">
    <span>Source <code>{esc(doc)}</code>{' / generated registry' if doc in {'RISKS.md', 'DECISIONS.md'} else ''}</span>
    <span>Updated {esc(dt.date.today().isoformat())}</span>
  </div>
"""
        body = page_shell(content, prefix="../", eyebrow="Core Context - Day Zero CTO", title=title, subtitle=description, crumbs=[("Core", "index.html#sec-core"), (title, None)], sticky_title=stable_title)
        write_html_page(wiki_root / relative_path, title, body, provenance)
        update_manifest(wiki_root, provenance)
        pages.append(
            {
                "doc": doc,
                "title": title,
                "description": description,
                "html": relative_path,
                "source_exists": source_path.exists(),
            }
        )
    return pages


def render_index(wiki_root: Path, project_folder: Path) -> None:
    core_dir = wiki_root / "core"
    reports_dir = wiki_root / "reports"
    learning_dir = wiki_root / "learning"
    today = dt.date.today()
    ensure_sidecar(wiki_root, project_folder, "render-index")

    config = project_config(wiki_root)
    strategy_path = core_dir / "STRATEGY.md"
    company = company_name(strategy_path, project_folder, config)
    description = company_description(strategy_path, config)
    stable_title = dashboard_title(company)
    prune_manifest_report_artifacts(wiki_root)
    risk_registry = write_risk_registry(wiki_root, project_folder)
    decision_registry = write_decision_registry(wiki_root, project_folder)
    write_risk_detail_pages(wiki_root, project_folder, risk_registry, stable_title)
    write_decision_detail_pages(wiki_root, project_folder, decision_registry, stable_title)
    refresh_structured_report_pages(wiki_root, project_folder, stable_title, risk_registry=risk_registry, decision_registry=decision_registry)
    core_pages = write_core_pages(wiki_root, project_folder, risk_registry=risk_registry, decision_registry=decision_registry)
    core_ready = sum(1 for page in core_pages if page["source_exists"])

    report_entries = [(folder, label, sorted((reports_dir / folder).glob("*.html"), reverse=True)) for folder, label in REPORT_FOLDERS.items()]
    report_count = sum(len(links) for _folder, _label, links in report_entries)
    tech_stack_links = next((links for folder, _label, links in report_entries if folder == "tech-stack"), [])
    tech_stack_href = tech_stack_links[0].relative_to(wiki_root).as_posix() if tech_stack_links else "#sec-reports"
    report_sections = []
    for folder, label, links in report_entries:
        latest = report_run_date(links[0]) if links else ""
        if links:
            latest_path = links[0]
            href = latest_path.relative_to(wiki_root).as_posix()
            preview = report_summary_for_path(latest_path) or "Generated report artifact."
            history_items = []
            history_search = []
            for path in links[1:4]:
                item_href = path.relative_to(wiki_root).as_posix()
                item_title = html_title(path)
                item_date = report_run_date(path)
                history_search.extend([item_title, item_date, report_summary(path)])
                history_items.append(
                    f"""<a class="rh-item" href="{esc(item_href)}">
  <span>{esc(item_date)}</span>
  <strong>{esc(item_title)}</strong>
</a>"""
                )
            history_more = f'<span class="rh-more">{esc(len(links) - 4)} older</span>' if len(links) > 4 else ""
            history_html = (
                f"""<div class="report-history">
  <div class="rh-label">Previous</div>
  {''.join(history_items)}
  {history_more}
</div>"""
                if history_items or history_more
                else ""
            )
            open_label = "Open latest" if len(links) > 1 else "Open report"
            report_sections.append(
                f"""<article class="report" data-search-text="{search_text_attr(label, preview, latest, *history_search)}">
  <div class="rp-top"><span class="rp-name">{esc(label)}</span><span class="rp-count">{esc(pluralize(len(links), "report"))}</span></div>
  <p class="rp-prev">{esc(preview)}</p>
  {history_html}
  <div class="rp-foot"><span class="rp-date">{esc(latest)}</span><a class="rp-open" href="{esc(href)}">{esc(open_label)}</a></div>
</article>"""
            )
        else:
            report_sections.append(
                f"""<article class="report empty" data-search-text="{search_text_attr(label, 'No reports generated yet')}">
  <div class="rp-top"><span class="rp-name">{esc(label)}</span><span class="rp-count">No reports</span></div>
  <p class="rp-prev">No reports generated yet.</p>
  <div class="rp-foot"><span class="rp-date">No runs</span></div>
</article>"""
            )

    core_links = []
    for page in core_pages:
        card_class = "core-card" if page["source_exists"] else "core-card missing-card"
        core_links.append(
            f"""<a class="{card_class}" href="{esc(page["html"])}">
  <span class="cc-ico">{esc(core_icon(page["doc"]))}</span>
  <span class="cc-name">{esc(page["title"])}</span>
  <span class="cc-desc">{esc(page["description"])}</span>
  <span class="cc-stat">{'Ready' if page["source_exists"] else 'Needs source'}</span>
</a>"""
        )

    cadence_rules = parse_cadence_rules(core_dir / "OPERATING_CADENCE.md")
    alerts = cadence_alerts(cadence_rules, reports_dir, today)
    risks = active_registry_risks(risk_registry)
    decisions = registry_decisions(decision_registry)
    due_decisions = due_decision_entries(decisions, today)
    due_risks = due_risk_entries(risks, today)
    critical_risks = sum(1 for risk in risks if risk["severity"] == "Critical")
    learning_items = read_learning_items(learning_dir)
    learning_reviews = read_learning_reviews(learning_dir)
    write_learning_index(wiki_root, project_folder, company, learning_items, learning_reviews, today)

    if not cadence_rules:
        cadence_status_html = '<div class="cadence-alert"><strong>No cadence rules</strong><p>Add an Index Cadence Rules table to Operating Cadence when this project has recurring DZCTO reports.</p></div>'
        cadence_label = "No rules"
        cadence_class = "status-warn"
        cadence_tone_attr = ' data-tone="warn"'
    elif not alerts:
        cadence_status_html = '<div class="cadence-ok"><strong>Cadence current</strong><p>All scheduled Day Zero CTO report cadences are current.</p></div>'
        cadence_label = "Current"
        cadence_class = ""
        cadence_tone_attr = ""
    else:
        alert_cards = "\n".join(
            f'<div class="cadence-alert"><strong>{esc(alert["label"])}</strong><p>{esc(alert["reason"])}</p><code>{esc(display_command(alert["command"]))}</code></div>'
            for alert in alerts
        )
        cadence_status_html = f'<div class="cadence-list">{alert_cards}</div>'
        cadence_label = f"{len(alerts)} due"
        cadence_class = "status-danger"
        cadence_tone_attr = ' data-tone="crit"'
    cadence_class_attr = f" {cadence_class}" if cadence_class else ""

    if not cadence_rules:
        report_status = pluralize(report_count, "artifact")
    elif not alerts:
        report_status = f"{pluralize(report_count, 'artifact')} / All current"
    else:
        report_status = f"{pluralize(report_count, 'artifact')} / {pluralize(len(alerts), 'alert')}"
    risk_tone_attr = ' data-tone="crit"' if critical_risks else ' data-tone="warn"' if due_risks else ""
    risk_sub = f"{pluralize(len(due_risks), 'review')} due" if due_risks else "Open risk page"
    decision_tone_attr = ' data-tone="warn"' if due_decisions else ""
    decision_sub = f"{pluralize(len(due_decisions), 'review')} due" if due_decisions else "Recorded choices"
    learning_status = learning_summary(learning_items, today)
    learning_counts_value = learning_counts(learning_items, today)
    repos = [str(item).strip() for item in (config.get("codeRepos", []) or []) if str(item).strip()]
    repo_count = len(repos)
    setup_items = setup_checklist_items(
        wiki_root=wiki_root,
        strategy_path=strategy_path,
        config=config,
        core_ready=core_ready,
        cadence_rules=cadence_rules,
        report_count=report_count,
        learning_items=learning_items,
        repos=repos,
    )
    setup_remaining = any(item["state"] != "done" for item in setup_items)
    setup_top_html = setup_dashboard_summary_html(setup_items) if setup_remaining else ""
    setup_bottom_html = "" if setup_remaining else dashboard_setup_section_html(setup_items)
    write_setup_page(wiki_root, project_folder, company, setup_items)
    write_search_index(
        wiki_root,
        project_folder,
        company=company,
        description=description,
        core_pages=core_pages,
        report_entries=report_entries,
        learning_items=learning_items,
        setup_items=setup_items,
        risk_registry=risk_registry,
        decision_registry=decision_registry,
    )

    report_prompt_context = configured_report_prompt_context(config)
    ai_prompts = [
        (
            rule["label"],
            enrich_ai_prompt(
                rule["label"],
                exact_prompt(
                    display_command(rule["command"]),
                    project_folder,
                    repos,
                    combine_prompt_context(report_prompt_context, str(rule.get("prompt_context") or "")),
                ),
            ),
        )
        for rule in cadence_rules
        if display_command(rule["command"])
    ]
    ai_prompts.extend(default_ai_prompts(company, project_folder, repos, report_prompt_context))
    seen: set[str] = set()
    seen_labels: set[str] = set()
    ai_prompt_items = []
    for index, (label, prompt) in enumerate(ai_prompts, start=1):
        normalized = prompt.lower()
        normalized_label = label.lower()
        if not prompt or normalized in seen or normalized_label in seen_labels:
            continue
        seen.add(normalized)
        seen_labels.add(normalized_label)
        ai_prompt_items.append(copy_card(f"ai-prompt-{index}-{slugify(label)}", label, prompt, "Prompt"))

    local_command_items = [
        copy_card(f"local-command-{index}-{slugify(label)}", label, command, "Command")
        for index, (label, command) in enumerate(local_helper_commands(project_folder), start=1)
    ]
    help_html = dashboard_help_html(project_folder, ai_prompt_items, local_command_items)

    learning_cards = f"""
<a class="learning-card" href="learning/index.html">
  <span class="learning-title">Spaced Repetition</span>
  <span class="learning-meta">{esc(learning_status)}</span>
</a>
<div class="learning-card">
  <span class="learning-title">Mastery</span>
  <span class="learning-meta">{esc(learning_counts_value["active"] - learning_counts_value["new"])} seen / {esc(learning_counts_value["new"])} new</span>
</div>
"""

    decision_rows = (
        "\n".join(
            f"""<a class="dec" href="{esc(text_value(decision.get("detailPath")) or decision_detail_relative_path(text_value(decision.get("id")) or decision_id_for_title(decision["title"])))}" data-search-text="{search_text_attr(decision["title"], decision["owner"], decision["when"], decision["context"])}">
  <span class="idx">{index}</span>
  <div class="d-body">
    <div class="d-title">{esc(decision["title"])}</div>
    <div class="d-meta"><span class="owner-tag">{esc(decision["owner"])}</span><span>/</span><span>{esc(decision["when"])}</span></div>
  </div>
</a>"""
            for index, decision in enumerate(due_decisions[:5], start=1)
        )
        if due_decisions
        else '<p class="empty-item">No decision revisit triggers are due or marked triggered.</p>'
    )

    due_risk_rows = (
        "\n".join(
            f"""<a class="mini-risk" href="{esc(text_value(risk.get("detailPath")) or risk_detail_relative_path(text_value(risk.get("id")) or risk_id_for_title(risk["title"])))}">
  <span class="sev-dot dot-{severity_token(risk["severity"])}"></span>
  <div class="mr-body">
    <div class="mr-title">{esc(risk["title"])}</div>
    <div class="mr-meta">{esc(risk["severity"])} / {esc(risk["owner"])} / {esc(risk["source"])} / review {esc(risk["review"])}</div>
  </div>
</a>"""
            for risk in due_risks[:5]
        )
        if due_risks
        else '<p class="empty-item">No risk reviews are due today.</p>'
    )

    cadence_today_html = (
        "\n".join(
            f"""<a class="cad-mini" href="core/operating-cadence.html">
  <div>
    <div class="cm-name">{esc(alert["label"])}</div>
    <div class="cm-sub">{esc(alert["reason"])}</div>
  </div>
  <span class="cm-when">{esc(relative_date(alert["due_date"], today))}</span>
</a>"""
            for alert in alerts[:5]
        )
        if alerts
        else (
            '<p class="empty-item">No cadence items are due today.</p>'
            if cadence_rules
            else '<p class="empty-item">No cadence rules yet.</p>'
        )
    )

    learning_percent = 0
    if learning_counts_value["active"]:
        learning_percent = round(((learning_counts_value["active"] - learning_counts_value["new"]) / learning_counts_value["active"]) * 100)
    learning_items_preview = (
        "\n".join(
            f"""<div class="li-card">
  <span class="li-new">{esc(learning_item_status(item, today))}</span>
  <div class="li-t">{esc(text_value(item.get("title") or item.get("id") or "Learning item"))}</div>
  <div class="li-d">{esc(snippet(text_value(item.get("summary") or item.get("details") or item.get("detail")), 120))}</div>
</div>"""
            for item in active_learning_items(learning_items)[:8]
        )
        if active_learning_items(learning_items)
        else '<div class="li-card"><div class="li-t">No learning items yet</div><div class="li-d">Run the learning skill to seed the first system concepts.</div></div>'
    )

    generated_at = utc_now()
    provenance = provenance_payload(
        wiki_root,
        artifact_id="wiki-index",
        artifact_kind="wiki-index",
        relative_path="index.html",
        title=f"{company} Day Zero CTO Knowledge Wiki",
        generated_at=generated_at,
    )
    content = f"""
  <div class="kpis">
    <a class="kpi{cadence_class_attr}" href="core/operating-cadence.html"{cadence_tone_attr}>
      <div class="k-label">Cadence due</div>
      <div class="k-val">{esc(len(alerts))}<span class="unit">/ {esc(len(cadence_rules))}</span></div>
      <div class="k-sub">{esc(cadence_label)}</div>
    </a>
    <a class="kpi" href="core/risks.html"{risk_tone_attr}>
      <div class="k-label">Open risks</div>
      <div class="k-val">{esc(len(risks))}{f'<span class="unit">/ {critical_risks} crit</span>' if critical_risks else ''}</div>
      <div class="k-sub">{esc(risk_sub)}</div>
    </a>
    <a class="kpi" href="core/decisions.html"{decision_tone_attr}>
      <div class="k-label">Decisions</div>
      <div class="k-val">{esc(len(decisions))}</div>
      <div class="k-sub">{esc(decision_sub)}</div>
    </a>
    <a class="kpi" href="#sec-reports">
      <div class="k-label">Reports</div>
      <div class="k-val">{esc(report_count)}<span class="unit">/ {esc(len(REPORT_FOLDERS))}</span></div>
      <div class="k-sub">{esc(report_status)}</div>
    </a>
    <a class="kpi" href="learning/index.html">
      <div class="k-label">Learning due</div>
      <div class="k-val">{esc(learning_counts_value["due"])}<span class="unit">/ {esc(learning_counts_value["new"])} new</span></div>
      <div class="k-sub">Spaced repetition</div>
    </a>
    <a class="kpi" href="{esc(tech_stack_href)}">
      <div class="k-label">Repos</div>
      <div class="k-val">{esc(repo_count)}</div>
      <div class="k-sub">Read-only sources</div>
    </a>
  </div>

  {setup_top_html}

  <section class="today" aria-label="Today">
    <div class="today-head">
      <h2><span class="pulse" aria-hidden="true"></span>What needs you today</h2>
      <span class="stamp">{esc(today.isoformat())} / generated {esc(generated_at.replace("T", " ").replace("Z", " UTC"))}</span>
    </div>
    <div class="today-grid">
      <div class="today-col">
        <div class="col-h">Decision reviews due <span class="cnt">{esc(len(due_decisions))}</span></div>
        {decision_rows}
      </div>
      <div class="today-col">
        <div class="col-h">Risk reviews due <span class="cnt">{esc(len(due_risks))}</span></div>
        {due_risk_rows}
      </div>
      <div class="today-col">
        <div class="col-h">Operating cadence due <span class="cnt">{esc(len(alerts))}</span></div>
        {cadence_today_html}
      </div>
    </div>
  </section>

  <details class="section" id="sec-reports">
    <summary>
      <span class="chev" aria-hidden="true"></span>
      <span class="sec-num">01</span>
      <span class="sec-title">Reports</span>
      <span class="sec-meta" data-report-count>{esc(report_status)}</span>
    </summary>
    <div class="sec-body">
      <div class="reports">{''.join(report_sections)}</div>
    </div>
  </details>

  <details class="section" id="sec-core">
    <summary>
      <span class="chev" aria-hidden="true"></span>
      <span class="sec-num">02</span>
      <span class="sec-title">Core Context</span>
      <span class="sec-meta">{core_ready}/{len(CORE_DOCS)} ready</span>
    </summary>
    <div class="sec-body">
      <div class="core">{''.join(core_links)}</div>
    </div>
  </details>

  <details class="section" id="sec-learning">
    <summary>
      <span class="chev" aria-hidden="true"></span>
      <span class="sec-num">03</span>
      <span class="sec-title">Learning</span>
      <span class="sec-meta">{esc(learning_status)}</span>
    </summary>
    <div class="sec-body">
      <div class="learn">
        <a class="learn-panel" href="learning/index.html">
          <div class="lp-h">Spaced Repetition</div>
          <div class="lp-sub">One concept per prompt. Self-rate to schedule the next review.</div>
          <div class="learn-stats">
            <div class="ls"><b>{esc(learning_counts_value["active"])}</b><span>Active</span></div>
            <div class="ls"><b>{esc(learning_counts_value["due"])}</b><span>Due</span></div>
            <div class="ls"><b>{esc(learning_counts_value["new"])}</b><span>New</span></div>
          </div>
          <div class="mastery">
            <div class="m-bar"><div class="m-fill" style="width:{esc(learning_percent)}%"></div></div>
            <div class="m-txt">Mastery: {esc(learning_percent)}%</div>
          </div>
        </a>
        <div class="learn-items">{learning_items_preview}</div>
      </div>
    </div>
  </details>

  {help_html}

  {setup_bottom_html}
"""
    body = page_shell(
        content,
        eyebrow="Command Center - Day Zero CTO",
        title=dashboard_title(company),
        subtitle=description,
        sticky_title=dashboard_title(company),
    )
    write_html_page(wiki_root / "index.html", dashboard_title(company), body, provenance)
    update_manifest(wiki_root, provenance)


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description="Generate Day Zero CTO artifacts")
    parser.add_argument("--project", help="Project folder; creates/uses PATH/knowledge/wiki")
    parser.add_argument("--home", help="Legacy: wiki root folder")
    parser.add_argument("--kind", choices=REPORT_FOLDERS.keys())
    parser.add_argument("--title")
    parser.add_argument("--date", default=dt.date.today().isoformat())
    parser.add_argument("--body-file", help="Legacy: raw HTML body file")
    parser.add_argument("--data-file", help="Structured JSON report data file")
    parser.add_argument("--init", action="store_true")
    parser.add_argument("--company-name", help="Company name to store in wiki metadata")
    parser.add_argument("--company-description", help="Short company description to store in wiki metadata")
    parser.add_argument("--company-url", help="Company website URL; used as context and optional description source")
    parser.add_argument("--report-prompt-context", help="Extra context appended to report and operating prompt cards")
    parser.add_argument("--repo", action="append", default=[], help="Read-only code repository path; may be repeated")
    args = parser.parse_args(argv)

    if not args.project and not args.home:
        parser.error("--project or --home is required")

    wiki_root = Path(args.project).expanduser().resolve() / "knowledge" / "wiki" if args.project else Path(args.home).expanduser().resolve()
    project_folder = Path(args.project).expanduser().resolve() if args.project else (wiki_root / ".." / "..").resolve()
    core_dir = wiki_root / "core"
    reports_dir = wiki_root / "reports"
    learning_dir = wiki_root / "learning"

    core_dir.mkdir(parents=True, exist_ok=True)
    for folder in REPORT_FOLDERS:
        (reports_dir / folder).mkdir(parents=True, exist_ok=True)
    learning_dir.mkdir(parents=True, exist_ok=True)
    ensure_sidecar(wiki_root, project_folder, "init" if args.init else "generate-artifact")
    apply_init_metadata(
        wiki_root,
        project_folder,
        company_name_value=args.company_name,
        company_description_value=args.company_description,
        company_url=args.company_url,
        report_prompt_context=args.report_prompt_context,
        repos=args.repo,
    )
    stable_title = dashboard_title(company_name(core_dir / "STRATEGY.md", project_folder, project_config(wiki_root)))

    written_report: Path | None = None
    if not args.init:
        if not args.kind:
            parser.error("--kind is required unless --init is used")
        if not args.title:
            parser.error("--title is required unless --init is used")

        report_sources: list[Path] = []
        structured_data: dict[str, Any] | None = None
        if args.data_file:
            data_path = Path(args.data_file).expanduser()
            report_sources.append(data_path)
            data = json.loads(data_path.read_text(encoding="utf-8"))
            if not isinstance(data, dict):
                raise SystemExit("--data-file must contain a JSON object")
            structured_data = data
            body = render_structured_report(args.kind, data)
        elif args.body_file:
            body_path = Path(args.body_file).expanduser()
            report_sources.append(body_path)
            body = body_path.read_text(encoding="utf-8")
        else:
            body = sys.stdin.read()

        slug = slugify(f"{args.date} {args.title}")
        report_path = reports_dir / args.kind / f"{slug}.html"
        relative_path = report_path.relative_to(wiki_root).as_posix()
        provenance = provenance_payload(
            wiki_root,
            artifact_id=f"{args.kind}:{slug}",
            artifact_kind=args.kind,
            relative_path=relative_path,
            title=args.title,
            generated_at=utc_now(),
            source_hashes=collect_source_hashes(report_sources),
            extra={"reportDate": args.date},
        )
        report_path.write_text(render_report_page(args.title, args.date, args.kind, body, provenance, stable_title, lede=report_lead_summary(structured_data)), encoding="utf-8")
        if structured_data is not None:
            write_json(report_path.with_suffix(".json"), structured_data)
            write_json(reports_dir / args.kind / "data.json", structured_data)
        update_manifest(wiki_root, provenance)
        written_report = report_path

    render_index(wiki_root, project_folder)
    print(written_report or wiki_root / "index.html")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))

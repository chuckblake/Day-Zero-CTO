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
    "decisions": "Decisions",
    "code-reviews": "Code Reviews",
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
    repos: list[str] | None = None,
) -> None:
    if not any([company_name_value, company_description_value, company_url, repos]):
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


def prompt_context(project_folder: Path, repos: list[str]) -> str:
    return f"Use project folder `{project_folder}`. {repo_context(repos)}"


def exact_prompt(base: str, project_folder: Path, repos: list[str]) -> str:
    return f"{base.strip()} {prompt_context(project_folder, repos)}".strip()


def enrich_ai_prompt(label: str, prompt: str) -> str:
    if re.search(r"weekly\s+cto|weekly\s+review", f"{label} {prompt}", re.I) and "read-only local Git history" not in prompt:
        return f"{prompt.strip()} Prefer read-only local Git history for the review window when available; do not run mutating Git commands."
    return prompt


def default_ai_prompts(company: str, project_folder: Path, repos: list[str]) -> list[tuple[str, str]]:
    return [
        (
            "Weekly CTO Review",
            exact_prompt(
                f"Run the weekly CTO review for {company}. Prefer read-only local Git history for the review window when available; do not run mutating Git commands.",
                project_folder,
                repos,
            ),
        ),
        ("CEO Update", exact_prompt(f"Write the CEO engineering update for {company}.", project_folder, repos)),
        ("Tech Stack", exact_prompt(f"Review the connected codebase(s) and create a Tech Stack report for {company}.", project_folder, repos)),
        ("Engineering Risk Review", exact_prompt(f"Run the engineering risk review for {company}.", project_folder, repos)),
        ("Learning", exact_prompt(f"Run a Day Zero CTO learning prompt for {company}.", project_folder, repos)),
        ("Decision Help", exact_prompt(f"Help me work through a CTO decision for {company}: <decision or problem>.", project_folder, repos)),
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
        (
            "CTO Code Review",
            exact_prompt(
                f"Run a CTO code review for {company} against <branch, PR, or diff>. Treat the repo(s) as read-only unless I explicitly ask for code changes.",
                project_folder,
                repos,
            ),
        ),
    ]


def local_helper_commands(project_folder: Path) -> list[tuple[str, str]]:
    return [
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
            "#sec-commands",
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
            "#sec-commands",
            "Refresh Wiki",
        ),
    ]


def setup_checklist_html(items: list[dict[str, str]]) -> str:
    complete = sum(1 for item in items if item["state"] == "done")
    rows = "\n".join(
        f"""<a class="setup-item" data-state="{esc(item["state"])}" href="{esc(item["href"])}">
  <span class="setup-mark" aria-hidden="true"></span>
  <span class="setup-body">
    <span class="setup-title">{esc(item["label"])}</span>
    <span class="setup-detail">{esc(item["detail"])}</span>
  </span>
  <span class="setup-action">{esc(item["status"] if item["state"] == "done" else item["action"])}</span>
</a>"""
        for item in items
    )
    return f"""
  <section class="setup-panel" id="sec-setup" aria-label="Setup checklist">
    <div class="setup-head">
      <div>
        <h2>Setup Checklist</h2>
        <p>{esc(complete)} of {esc(len(items))} complete</p>
      </div>
      <a class="setup-help" href="#sec-commands">Commands</a>
    </div>
    <div class="setup-list">{rows}</div>
  </section>
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


def breadcrumbs(prefix: str, items: list[tuple[str, str | None]]) -> str:
    parts = [f'<a href="{esc(prefix)}index.html">Dashboard</a>']
    for label, href in items:
        if href:
            parts.append(f'<a href="{esc(prefix + href)}">{esc(label)}</a>')
        else:
            parts.append(f"<span>{esc(label)}</span>")
    return f'<nav class="breadcrumbs" aria-label="Breadcrumb">{"<span>/</span>".join(parts)}</nav>'


def page_shell(
    content: str,
    *,
    prefix: str = "",
    eyebrow: str = "Command Center - Day Zero CTO",
    title: str = "Knowledge Wiki",
    subtitle: str = "",
    crumbs: list[tuple[str, str | None]] | None = None,
) -> str:
    breadcrumb_html = breadcrumbs(prefix, crumbs) if crumbs else ""
    return f"""
<main class="app">
  <header class="masthead">
    <div>
      {breadcrumb_html}
      <a class="masthead-title-link" href="{esc(prefix)}index.html">
        <span class="eyebrow">{esc(eyebrow)}</span>
        <h1 class="title">{esc(title)}</h1>
      </a>
      {f'<p class="lede">{esc(subtitle)}</p>' if subtitle else ''}
    </div>
    <div class="masthead-side">
      <div class="util">
        <button type="button" class="theme-btn" data-theme-toggle aria-label="Toggle light or dark theme"><span data-theme-label>Dark</span></button>
      </div>
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
        cards.append(
            f"""
<div class="metric">
  <span class="label">{esc(label)}</span>
  <span class="value">{esc(value)}</span>
  {f'<span class="detail">{esc(detail)}</span>' if detail else ''}
</div>
"""
        )
    return f'<div class="grid">\n{"".join(cards)}\n</div>'


def render_list_section(title: str, items: Any) -> str:
    rows = array_value(items)
    if not rows:
        return ""

    list_items = []
    for item in rows:
        if isinstance(item, dict):
            title_text = text_value(value_at(item, "title", "name", "priority", "ask", "decision", "risk", "finding", "question", "prompt"))
            body = text_value(value_at(item, "body", "detail", "details", "summary", "why", "impact", "rationale", "note", "notes"))
            owner = text_value(value_at(item, "owner", "owner_horizon", "needed_by", "done_when"))
            evidence = [text_value(entry) for entry in array_value(value_at(item, "evidence", "sources", "source"))]
            list_items.append(
                f"""
<li>
  {f'<strong>{esc(title_text)}</strong>' if title_text else ''}
  {f'<span>{esc(body)}</span>' if body else ''}
  {f'<em>{esc(owner)}</em>' if owner else ''}
  {f'<small>Evidence: {esc("; ".join(filter(None, evidence)))}</small>' if any(evidence) else ''}
</li>
"""
            )
        else:
            list_items.append(f"<li>{esc(text_value(item))}</li>")
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


def render_table_section(title: str, rows: Any, columns: list[tuple[str, str]]) -> str:
    values = [row for row in array_value(rows) if isinstance(row, dict)]
    if not values:
        return ""

    headers = "".join(f"<th>{esc(label)}</th>" for label, _key in columns)
    table_rows = []
    for row in values:
        cells = []
        for _label, key in columns:
            value = value_at(row, key)
            if re.search(r"severity|likelihood|status", key, re.I) and present(value):
                cell = f'<span class="tag {severity_class(value)}">{esc(text_value(value))}</span>'
            else:
                cell = esc(text_value(value))
            cells.append(f"<td>{cell}</td>")
        table_rows.append(f"<tr>{''.join(cells)}</tr>")
    return f"""
<section class="artifact-section">
  <h2>{esc(title)}</h2>
  <table>
    <thead><tr>{headers}</tr></thead>
    <tbody>{''.join(table_rows)}</tbody>
  </table>
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
        "tech-stack": [
            action_group("Stack Risks", value_at(data, "risks_watchpoints", "risks", "watchpoints")),
            action_group("Onboarding", value_at(data, "onboarding_notes", "notes")),
            action_group("Integrations", value_at(data, "integrations")),
        ],
        "decisions": [
            action_group("Recommendation", value_at(data, "recommendation")),
            action_group("Follow-Ups", value_at(data, "follow_ups", "followups")),
            action_group("Watchpoints", value_at(data, "watchpoints")),
        ],
        "code-reviews": [
            action_group("Recommendation", value_at(data, "merge_recommendation", "recommendation")),
            action_group("Blocking", value_at(data, "blocking")),
            action_group("Questions", value_at(data, "questions")),
        ],
    }
    groups = [(label, items) for label, items in groups_by_kind.get(kind, []) if items]
    if not groups:
        return ""

    cards = []
    for label, items in groups:
        preview = "".join(f"<li>{esc(item)}</li>" for item in items[:3])
        cards.append(
            f"""
<article class="action-card">
  <div class="action-top"><span>{esc(label)}</span><strong>{esc(len(items))}</strong></div>
  <ul>{preview}</ul>
</article>
"""
        )
    return f"""
<section class="artifact-section action-summary">
  <h2>Action Summary</h2>
  <div class="action-grid">{''.join(cards)}</div>
</section>
"""


def render_weekly_review(data: dict[str, Any]) -> str:
    return "".join(
        [
            html_paragraph(value_at(data, "executive_read", "summary")),
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
    return "".join(
        [
            html_paragraph(value_at(data, "headline", "summary")),
            render_metrics(value_at(data, "metrics")),
            render_list_section("Progress", value_at(data, "progress")),
            render_list_section("Risks / Blockers", value_at(data, "risks_blockers", "risks", "blockers")),
            render_list_section("Asks / Decisions", value_at(data, "asks_decisions", "asks", "decisions")),
            render_list_section("Next", value_at(data, "next", "up_next")),
            render_sources(data),
        ]
    )


def render_engineering_risk(data: dict[str, Any]) -> str:
    return "".join(
        [
            html_paragraph(value_at(data, "executive_read", "summary")),
            render_metrics(value_at(data, "metrics")),
            render_table_section("Top Risks", value_at(data, "top_risks", "risks"), [("Risk", "risk"), ("Evidence", "evidence"), ("Business Impact", "impact"), ("Likelihood", "likelihood"), ("Severity", "severity"), ("Mitigation", "mitigation"), ("Owner / Horizon", "owner_horizon")]),
            render_list_section("Mitigations", value_at(data, "mitigations")),
            render_list_section("Watchpoints", value_at(data, "watchpoints")),
            render_sources(data),
        ]
    )


def render_tech_stack(data: dict[str, Any]) -> str:
    return "".join(
        [
            html_paragraph(value_at(data, "executive_read", "summary")),
            render_table_section("Stack Components", value_at(data, "stack_components", "components"), [("Layer", "layer"), ("Technology", "technology"), ("Evidence", "evidence"), ("Notes", "notes")]),
            render_text_section("Architecture Shape", value_at(data, "architecture_shape", "architecture")),
            render_list_section("Data and Storage", value_at(data, "data_storage", "data_and_storage")),
            render_list_section("Integrations", value_at(data, "integrations")),
            render_list_section("Infrastructure and Operations", value_at(data, "infrastructure_operations", "infrastructure", "operations")),
            render_list_section("Development Tooling", value_at(data, "development_tooling", "dev_tooling")),
            render_table_section("Risks and Watchpoints", value_at(data, "risks_watchpoints", "risks", "watchpoints"), [("Risk", "risk"), ("Evidence", "evidence"), ("Impact", "impact"), ("Severity", "severity"), ("Mitigation", "mitigation")]),
            render_list_section("Onboarding Notes", value_at(data, "onboarding_notes", "notes")),
            render_sources(data),
        ]
    )


def render_decision(data: dict[str, Any]) -> str:
    return "".join(
        [
            render_text_section("Decision", value_at(data, "decision")),
            render_text_section("Context", value_at(data, "context")),
            render_table_section("Options", value_at(data, "options"), [("Option", "option"), ("Upside", "upside"), ("Downside", "downside"), ("Reversibility", "reversibility")]),
            render_table_section("Tradeoffs", value_at(data, "tradeoffs"), [("Axis", "axis"), ("Implication", "implication"), ("Note", "note")]),
            render_text_section("Recommendation", value_at(data, "recommendation")),
            render_list_section("Watchpoints", value_at(data, "watchpoints")),
            render_list_section("Follow-Ups", value_at(data, "follow_ups", "followups")),
            render_sources(data),
        ]
    )


def render_code_review(data: dict[str, Any]) -> str:
    return "".join(
        [
            render_text_section("Merge Recommendation", value_at(data, "merge_recommendation", "recommendation")),
            render_table_section("Blocking", value_at(data, "blocking"), [("Finding", "finding"), ("Evidence", "evidence"), ("Impact", "impact"), ("Recommendation", "recommendation")]),
            render_table_section("FYI", value_at(data, "fyi"), [("Finding", "finding"), ("Evidence", "evidence"), ("Impact", "impact"), ("Recommendation", "recommendation")]),
            render_table_section("Questions", value_at(data, "questions"), [("Question", "question"), ("Why It Matters", "why"), ("Owner", "owner")]),
            render_text_section("Tests / Verification", value_at(data, "tests_verification", "verification")),
            render_text_section("Startup Risk Note", value_at(data, "startup_risk_note", "risk_note")),
            render_sources(data),
        ]
    )


def render_generic_report(data: dict[str, Any]) -> str:
    summary = html_paragraph(value_at(data, "summary", "executive_read", "headline"))
    sections = []
    for section in array_value(value_at(data, "sections")):
        if not isinstance(section, dict):
            sections.append(render_list_section("Section", [section]))
            continue
        title = text_value(value_at(section, "title", "name"))
        content = value_at(section, "items", "body", "content", "details")
        sections.append(render_list_section(title, content) if isinstance(content, list) else render_text_section(title, content))
    return "".join([summary, *sections, render_sources(data)])


def render_structured_report(kind: str, data: dict[str, Any]) -> str:
    renderers = {
        "tech-stack": render_tech_stack,
        "weekly-reviews": render_weekly_review,
        "ceo-updates": render_ceo_update,
        "engineering-risk": render_engineering_risk,
        "decisions": render_decision,
        "code-reviews": render_code_review,
    }
    body = renderers.get(kind, render_generic_report)(data)
    action_summary = render_action_summary(kind, data)
    return f"{action_summary}{body}".strip() or render_generic_report(data)


def core_doc_html_name(doc: str) -> str:
    return CORE_DOC_HTML.get(doc, f"{slugify(Path(doc).stem)}.html")


def inline_markdown(value: str) -> str:
    text = esc(value)
    text = re.sub(r"`([^`]+)`", r"<code>\1</code>", text)
    text = re.sub(r"\*\*([^*]+)\*\*", r"<strong>\1</strong>", text)
    text = re.sub(r"\[([^\]]+)\]\(([^)]+)\)", r'<a href="\2">\1</a>', text)
    return text


def render_markdown_table(lines: list[str]) -> str:
    rows = [split_markdown_row(line) for line in lines]
    if len(rows) < 2:
        return ""
    headers = "".join(f"<th>{inline_markdown(cell)}</th>" for cell in rows[0])
    body_rows = []
    for row in rows[2:]:
        body_rows.append("<tr>" + "".join(f"<td>{inline_markdown(cell)}</td>" for cell in row) + "</tr>")
    return f"<table><thead><tr>{headers}</tr></thead><tbody>{''.join(body_rows)}</tbody></table>"


def markdown_to_html(markdown: str) -> str:
    lines = markdown.splitlines()
    blocks: list[str] = []
    paragraph: list[str] = []
    list_items: list[str] = []
    table_lines: list[str] = []
    in_code = False
    code_lines: list[str] = []

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
            rendered = render_markdown_table(table_lines)
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
) -> None:
    entries: list[dict[str, str]] = [
        search_entry(
            title=f"{company} Day Zero CTO",
            kind="Dashboard",
            url="index.html",
            text=f"{company} {description} cadence core context reports learning commands",
            summary=description,
        )
    ]

    core_dir = wiki_root / "core"
    for page in core_pages:
        if not page["source_exists"]:
            continue
        source_path = core_dir / page["doc"]
        source_text = source_path.read_text(encoding="utf-8", errors="replace")
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

    for folder, label, links in report_entries:
        for path in links:
            html_text = path.read_text(encoding="utf-8", errors="replace")
            entries.append(
                search_entry(
                    title=html_title(path),
                    kind=label,
                    url=path.relative_to(wiki_root).as_posix(),
                    text=html_text,
                    summary=plain_html(html_text),
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


def markdown_tables(path: Path) -> list[list[dict[str, str]]]:
    if not path.exists():
        return []

    tables: list[list[dict[str, str]]] = []
    lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    index = 0
    while index < len(lines):
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
            tables.append(table)
    return tables


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


def read_risk_entries(core_dir: Path) -> list[dict[str, str]]:
    path = core_dir / "RISKS.md"
    risks: list[dict[str, str]] = []
    for table in markdown_tables(path):
        for row in table:
            title = value_from_row(row, "risk", "title", "finding", "issue", "name") or next(iter(row.values()), "")
            if not title:
                continue
            severity_source = value_from_row(row, "severity", "priority", "status", "likelihood") or title
            risks.append(
                {
                    "title": plain_markdown(title),
                    "severity": normalize_severity(severity_source),
                    "category": plain_markdown(value_from_row(row, "category", "area", "type")),
                    "owner": plain_markdown(value_from_row(row, "owner", "responsible", "owner_horizon")) or "Unassigned",
                    "review": plain_markdown(value_from_row(row, "review", "review_date", "next_review", "due", "horizon", "needed_by")) or "Unscheduled",
                    "evidence": plain_markdown(value_from_row(row, "evidence", "source", "sources", "signal")),
                    "impact": plain_markdown(value_from_row(row, "impact", "business_impact", "why")),
                    "mitigation": plain_markdown(value_from_row(row, "mitigation", "next_step", "action", "plan")),
                }
            )
    if risks:
        return sorted(risks, key=lambda item: (severity_rank(item["severity"]), item["title"].lower()))[:12]

    fallback = []
    for item in markdown_heading_items(path):
        title = item["title"]
        fallback.append(
            {
                "title": title,
                "severity": normalize_severity(title),
                "category": "Core context",
                "owner": "Unassigned",
                "review": "Unscheduled",
                "evidence": item.get("summary", ""),
                "impact": "",
                "mitigation": "",
            }
        )
    return sorted(fallback, key=lambda item: (severity_rank(item["severity"]), item["title"].lower()))[:12]


def read_decision_entries(core_dir: Path) -> list[dict[str, str]]:
    path = core_dir / "DECISIONS.md"
    decisions: list[dict[str, str]] = []
    for table in markdown_tables(path):
        for row in table:
            title = value_from_row(row, "decision", "title", "question", "ask", "name") or next(iter(row.values()), "")
            if not title:
                continue
            decisions.append(
                {
                    "title": plain_markdown(title),
                    "owner": plain_markdown(value_from_row(row, "owner", "responsible")) or "Founder",
                    "when": plain_markdown(value_from_row(row, "revisit_trigger", "revisit", "needed_by", "due", "status", "date")) or "Review trigger",
                    "context": plain_markdown(value_from_row(row, "context", "rationale", "why", "notes", "summary")),
                }
            )
    if decisions:
        return decisions[:8]

    return [
        {
            "title": item["title"],
            "owner": "Founder",
            "when": "Review",
            "context": item.get("summary", ""),
        }
        for item in markdown_heading_items(path, limit=8)
    ]


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
}
* { box-sizing: border-box; }
html { scroll-behavior: smooth; }
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
.masthead-side { display: flex; flex-direction: column; align-items: flex-end; gap: 10px; min-width: min(300px, 100%); }
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
.today-grid { display: grid; grid-template-columns: 1.35fr 1fr 1fr; }
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
.r-field-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 12px; }
.sev-badge, .tag { display: inline-block; border-radius: var(--r-pill); padding: 3px 9px; font-size: 11px; font-weight: 800; letter-spacing: 0; text-transform: uppercase; white-space: nowrap; }
.b-crit, .high { color: var(--crit); background: var(--crit-soft); }
.b-high { color: var(--high); background: var(--high-soft); }
.b-med, .medium { color: var(--med); background: var(--med-soft); }
.b-low, .ready { color: var(--low); background: var(--low-soft); }
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
.rp-cad, .report-count { color: var(--muted); background: var(--surface-3); border-radius: var(--r-pill); padding: 3px 9px; font-size: 10.5px; font-weight: 800; text-transform: uppercase; }
.rp-prev { color: var(--ink-2); font-size: 12.5px; line-height: 1.55; }
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
.toc { margin: 18px 0 24px; border: 1px solid var(--line); border-radius: var(--r-md); background: var(--surface-2); padding: 12px; }
.toc strong { display: block; margin-bottom: 8px; }
.toc-links { display: flex; flex-wrap: wrap; gap: 8px; }
.toc-links a { border: 1px solid var(--line); border-radius: var(--r-pill); background: var(--surface); color: var(--ink); font-size: 13px; font-weight: 800; padding: 5px 9px; }
.toc-links a:hover { background: var(--accent-soft); text-decoration: none; }
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
.artifact-section { margin-top: 30px; border-top: 1px solid var(--line); padding-top: 22px; }
.artifact-section:first-of-type { margin-top: 0; border-top: 0; padding-top: 0; }
.artifact-list { display: grid; gap: 10px; margin: 16px 0 24px; padding: 0; list-style: none; }
.artifact-list li { border: 1px solid var(--line); border-radius: var(--r-md); background: var(--surface); padding: 12px; }
.artifact-list strong, .artifact-list span, .artifact-list em, .artifact-list small { display: block; }
.artifact-list span, .artifact-list em, .artifact-list small { margin-top: 4px; color: var(--muted); }
.artifact-list em, .artifact-list small { font-size: 13px; font-style: normal; }
.action-summary { margin-top: 0; border-top: 0; padding-top: 0; }
.action-grid { display: grid; grid-template-columns: repeat(3, 1fr); gap: var(--gap); margin-top: 14px; }
.action-card {
  border: 1px solid var(--line);
  border-radius: var(--r-md);
  background: var(--surface);
  box-shadow: var(--shadow-sm);
  padding: 14px;
}
.action-top { display: flex; align-items: center; justify-content: space-between; gap: 10px; margin-bottom: 8px; }
.action-top span { color: var(--muted); font-size: 11px; font-weight: 800; text-transform: uppercase; }
.action-top strong { color: var(--ink); font-size: 22px; line-height: 1; }
.action-card ul { display: grid; gap: 7px; margin: 0; padding: 0; list-style: none; }
.action-card li { color: var(--ink-2); font-size: 12.5px; line-height: 1.4; }
.prose { max-width: 900px; }
.prose h2, .prose h3, .prose h4 { margin-top: 28px; }
.prose p, .prose ul { margin-top: 12px; }
.empty-item, .no-results { color: var(--faint); font-size: 13px; }
.no-results { border: 1px dashed var(--line-2); border-radius: var(--r-md); padding: 22px; text-align: center; }
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
}
@media (max-width: 860px) {
  .masthead { grid-template-columns: 1fr; }
  .masthead-side { align-items: stretch; }
  .util { justify-content: flex-end; }
  .search { width: 100%; }
  .today-grid { grid-template-columns: 1fr; }
  .today-col { border-right: 0; border-bottom: 1px solid var(--line); }
  .today-col:last-child { border-bottom: 0; }
  .reports, .reports-grid, .cmd-grid, .copy-grid, .learn, .learning-grid { grid-template-columns: 1fr; }
  .action-grid { grid-template-columns: 1fr; }
  h1.title { font-size: 30px; }
}
@media (max-width: 560px) {
  .app { padding: 24px 16px 70px; }
  .kpis, .core, .status-grid, .summary, .grid { grid-template-columns: 1fr 1fr; }
  .setup-list { grid-template-columns: 1fr; }
  .setup-item { min-height: auto; border-right: 0; border-bottom: 1px solid var(--line); }
  .app-footer { justify-content: flex-start; }
  .r-field-grid { grid-template-columns: 1fr; }
  .risk > summary { grid-template-columns: auto 1fr; }
  .r-right { grid-column: 2; justify-content: space-between; }
  .sec-title { white-space: normal; }
  .learn-items { columns: 1; }
}
@media print {
  .masthead-side, .toolbar { display: none !important; }
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
    const selected = $('.chip[aria-pressed="true"]')?.dataset.sev || 'all';
    let visibleRisks = 0;
    $$('.risk[data-search-text]').forEach((item) => {
      const matchesQuery = !q || item.dataset.searchText.includes(q);
      const matchesSeverity = selected === 'all' || item.dataset.sev === selected;
      const visible = matchesQuery && matchesSeverity;
      item.hidden = !visible;
      if (visible) visibleRisks += 1;
    });
    const riskCount = $('[data-risk-count]');
    if (riskCount) {
      const total = Number(riskCount.dataset.total || visibleRisks);
      riskCount.textContent = `${visibleRisks} of ${total} shown`;
    }
    let visibleReports = 0;
    $$('.report[data-search-text], .report-card[data-search-text]').forEach((item) => {
      const visible = !q || item.dataset.searchText.includes(q);
      item.hidden = !visible;
      if (visible) visibleReports += 1;
    });
    const reportCount = $('[data-report-count]');
    if (reportCount && q) reportCount.textContent = `${visibleReports} matching`;
    if (q) {
      const riskSection = $('#sec-risks');
      const reportSection = $('#sec-reports');
      if (riskSection) riskSection.open = true;
      if (reportSection) reportSection.open = true;
    }
  }

  $$('[data-sev]').forEach((chip) => {
    chip.addEventListener('click', () => {
      const group = chip.closest('.chipset');
      if (group) $$('[data-sev]', group).forEach((item) => item.setAttribute('aria-pressed', String(item === chip)));
      const input = $('[data-dzcto-search]');
      applyDashboardFilters(input ? input.value : '');
    });
  });

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

  document.querySelectorAll('[data-dzcto-toc]').forEach((toc) => {
    const scope = document.querySelector('[data-toc-scope]') || document.querySelector('main');
    const headings = Array.from(scope.querySelectorAll('h2, h3')).filter((heading) => heading.textContent.trim());
    if (headings.length < 2) {
      toc.hidden = true;
      return;
    }
    headings.forEach((heading) => {
      if (!heading.id) {
        heading.id = heading.textContent.trim().toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/^-|-$/g, '') || 'section';
      }
    });
    toc.hidden = false;
    toc.innerHTML = `<strong>On this page</strong><div class="toc-links">${
      headings.map((heading) => `<a href="#${escapeHtml(heading.id)}">${escapeHtml(heading.textContent.trim())}</a>`).join('')
    }</div>`;
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
  <nav class="toc" data-dzcto-toc hidden aria-label="Page sections"></nav>
  <div data-toc-scope>
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
        f"{content}\n  </div>",
        prefix="../",
        eyebrow="Learning - Day Zero CTO",
        title=f"{company} Learning",
        subtitle="Spaced repetition for system knowledge. Each prompt teaches one concept, records a self-rating, updates the mastery checklist, and schedules the next review.",
        crumbs=[("Learning", None)],
    )
    write_html_page(learning_dir / "index.html", f"{company} Learning", body, provenance)
    update_manifest(wiki_root, provenance)


def render_report_page(title: str, date: str, kind: str, body: str, provenance: dict[str, Any]) -> str:
    safe_title = esc(title)
    safe_date = esc(date)
    content = f"""
    <nav class="toc" data-dzcto-toc hidden aria-label="Page sections"></nav>
    <div data-toc-scope>
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
    {page_shell(content, prefix="../../", eyebrow=f"{REPORT_FOLDERS[kind]} - Day Zero CTO", title=title, subtitle=date, crumbs=[("Reports", "index.html#sec-reports"), (REPORT_FOLDERS[kind], None)])}
    {provenance_block(provenance)}
    {refresh_script()}
  </body>
</html>
"""


def write_core_pages(wiki_root: Path, project_folder: Path) -> list[dict[str, Any]]:
    core_dir = wiki_root / "core"
    core_dir.mkdir(parents=True, exist_ok=True)
    pages: list[dict[str, Any]] = []
    for doc in CORE_DOCS:
        title, description = CORE_DOC_META.get(doc, (doc, "Core CTO context."))
        source_path = core_dir / doc
        relative_path = f"core/{core_doc_html_name(doc)}"
        if source_path.exists():
            source_text = source_path.read_text(encoding="utf-8")
            content_html = markdown_to_html(source_text)
            source_hash = collect_source_hashes([source_path])
            status = "Ready"
        else:
            content_html = f'<p class="empty-item">{esc(doc)} has not been created yet.</p>'
            source_hash = {}
            status = "Missing source"

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
  <div class="status-grid">
    <div class="status-card {'status-good' if source_path.exists() else 'status-warn'}"><span>Status</span><strong>{esc(status)}</strong></div>
    <div class="status-card"><span>Source</span><strong>{esc(doc)}</strong></div>
    <div class="status-card"><span>Updated</span><strong>{esc(dt.date.today().isoformat())}</strong></div>
    <div class="status-card"><span>Page</span><strong>HTML</strong></div>
  </div>
  <nav class="toc" data-dzcto-toc hidden aria-label="Page sections"></nav>
  <section class="artifact-section prose" data-toc-scope>
    {content_html}
  </section>
"""
        body = page_shell(content, prefix="../", eyebrow="Core Context - Day Zero CTO", title=title, subtitle=description, crumbs=[("Core", "index.html#sec-core"), (title, None)])
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
    core_pages = write_core_pages(wiki_root, project_folder)
    core_ready = sum(1 for page in core_pages if page["source_exists"])

    report_entries = [(folder, label, sorted((reports_dir / folder).glob("*.html"), reverse=True)) for folder, label in REPORT_FOLDERS.items()]
    report_count = sum(len(links) for _folder, _label, links in report_entries)
    tech_stack_links = next((links for folder, _label, links in report_entries if folder == "tech-stack"), [])
    tech_stack_href = tech_stack_links[0].relative_to(wiki_root).as_posix() if tech_stack_links else "#sec-reports"
    report_sections = []
    for folder, label, links in report_entries:
        cadence_label = "Scheduled"
        latest = report_run_date(links[0]) if links else ""
        if links:
            latest_path = links[0]
            href = latest_path.relative_to(wiki_root).as_posix()
            preview = report_summary(latest_path) or "Generated report artifact."
            report_sections.append(
                f"""<a class="report" href="{esc(href)}" data-search-text="{search_text_attr(label, preview, latest)}">
  <div class="rp-top"><span class="rp-name">{esc(label)}</span><span class="rp-cad">{esc(cadence_label)}</span></div>
  <p class="rp-prev">{esc(preview)}</p>
  <div class="rp-foot"><span class="rp-date">{esc(latest)}</span><span class="rp-open">Open report</span></div>
</a>"""
            )
        else:
            report_sections.append(
                f"""<article class="report empty" data-search-text="{search_text_attr(label, 'No reports generated yet')}">
  <div class="rp-top"><span class="rp-name">{esc(label)}</span><span class="rp-cad">{esc(cadence_label)}</span></div>
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
    risks = read_risk_entries(core_dir)
    decisions = read_decision_entries(core_dir)
    critical_risks = sum(1 for risk in risks if risk["severity"] == "Critical")
    high_or_critical_risks = [risk for risk in risks if risk["severity"] in {"Critical", "High"}]
    cadence_preview_rows = cadence_rows(cadence_rules, reports_dir, today)
    learning_items = read_learning_items(learning_dir)
    learning_reviews = read_learning_reviews(learning_dir)
    write_learning_index(wiki_root, project_folder, company, learning_items, learning_reviews, today)
    write_search_index(
        wiki_root,
        project_folder,
        company=company,
        description=description,
        core_pages=core_pages,
        report_entries=report_entries,
        learning_items=learning_items,
    )

    if not cadence_rules:
        cadence_status_html = '<div class="cadence-alert"><strong>No cadence rules</strong><p>Add an Index Cadence Rules table to Operating Cadence when this project has recurring DZCTO reports.</p></div>'
        cadence_label = "No rules"
        cadence_class = "status-warn"
    elif not alerts:
        cadence_status_html = '<div class="cadence-ok"><strong>Cadence current</strong><p>All scheduled Day Zero CTO report cadences are current.</p></div>'
        cadence_label = "Current"
        cadence_class = "status-good"
    else:
        alert_cards = "\n".join(
            f'<div class="cadence-alert"><strong>{esc(alert["label"])}</strong><p>{esc(alert["reason"])}</p><code>{esc(display_command(alert["command"]))}</code></div>'
            for alert in alerts
        )
        cadence_status_html = f'<div class="cadence-list">{alert_cards}</div>'
        cadence_label = f"{len(alerts)} due"
        cadence_class = "status-danger"

    if not cadence_rules:
        report_status = pluralize(report_count, "artifact")
    elif not alerts:
        report_status = f"{pluralize(report_count, 'artifact')} / All current"
    else:
        report_status = f"{pluralize(report_count, 'artifact')} / {pluralize(len(alerts), 'alert')}"
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
    setup_html = setup_checklist_html(setup_items)

    ai_prompts = [
        (rule["label"], enrich_ai_prompt(rule["label"], exact_prompt(display_command(rule["command"]), project_folder, repos)))
        for rule in cadence_rules
        if display_command(rule["command"])
    ]
    ai_prompts.extend(default_ai_prompts(company, project_folder, repos))
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
    command_card_count = len(ai_prompt_items) + len(local_command_items)

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
            f"""<a class="dec" href="core/decisions.html" data-search-text="{search_text_attr(decision["title"], decision["owner"], decision["when"], decision["context"])}">
  <span class="idx">{index}</span>
  <div class="d-body">
    <div class="d-title">{esc(decision["title"])}</div>
    <div class="d-meta"><span class="owner-tag">{esc(decision["owner"])}</span><span>/</span><span>{esc(decision["when"])}</span></div>
  </div>
</a>"""
            for index, decision in enumerate(decisions[:5], start=1)
        )
        if decisions
        else '<p class="empty-item">No recorded decisions found.</p>'
    )

    top_risk_rows = (
        "\n".join(
            f"""<a class="mini-risk" href="core/risks.html">
  <span class="sev-dot dot-{severity_token(risk["severity"])}"></span>
  <div class="mr-body">
    <div class="mr-title">{esc(risk["title"])}</div>
    <div class="mr-meta">{esc(risk["severity"])} / {esc(risk["owner"])}</div>
  </div>
</a>"""
            for risk in high_or_critical_risks[:5]
        )
        if high_or_critical_risks
        else '<p class="empty-item">No high-priority risks found in core context.</p>'
    )

    cadence_preview_html = (
        "\n".join(
            f"""<a class="cad-mini" href="core/operating-cadence.html">
  <div>
    <div class="cm-name">{esc(row["name"])}</div>
    <div class="cm-sub">{esc(row["cadence"])}{f' / {esc(row["day"])}' if row["day"] else ''} / last {esc(row["last"])}</div>
  </div>
  <span class="cm-when">{esc(row["next"])}</span>
</a>"""
            for row in cadence_preview_rows[:5]
        )
        if cadence_preview_rows
        else '<p class="empty-item">No cadence rules yet.</p>'
    )

    risk_cards = (
        "\n".join(
            f"""<details class="risk" data-sev="{esc(risk["severity"])}" data-rank="{severity_rank(risk["severity"])}" data-search-text="{search_text_attr(*risk.values())}">
  <summary>
    <span class="sev-dot dot-{severity_token(risk["severity"])}"></span>
    <div class="r-main">
      <div class="r-title">{esc(risk["title"])}</div>
      <div class="r-sub">
        <span class="sev-badge b-{severity_token(risk["severity"])}">{esc(risk["severity"])}</span>
        {f'<span>{esc(risk["category"])}</span><span>/</span>' if risk["category"] else ''}
        <span>{esc(risk["owner"])}</span>
      </div>
    </div>
    <div class="r-right">
      <span class="count-pill">review {esc(risk["review"])}</span>
      <span class="r-chev" aria-hidden="true"></span>
    </div>
  </summary>
  <div class="r-detail">
    <div class="r-field"><div class="rf-k">Evidence</div><div class="rf-v">{esc(risk["evidence"] or "No evidence captured yet.")}</div></div>
    <div class="r-field"><div class="rf-k">Business impact</div><div class="rf-v">{esc(risk["impact"] or "Impact not captured yet.")}</div></div>
    <div class="r-field"><div class="rf-k">Mitigation</div><div class="rf-v">{esc(risk["mitigation"] or "Mitigation not captured yet.")}</div></div>
    <div class="r-field-grid">
      <div class="r-field"><div class="rf-k">Owner</div><div class="rf-v">{esc(risk["owner"])}</div></div>
      <div class="r-field"><div class="rf-k">Review</div><div class="rf-v">{esc(risk["review"])}</div></div>
    </div>
  </div>
</details>"""
            for risk in risks
        )
        if risks
        else '<div class="no-results">No risk rows found. Add a table or headings to core/RISKS.md.</div>'
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
    <a class="kpi {cadence_class}" href="core/operating-cadence.html" data-tone="{'crit' if alerts else 'good' if cadence_rules else 'warn'}">
      <div class="k-label">Cadence due</div>
      <div class="k-val">{esc(len(alerts))}<span class="unit">/ {esc(len(cadence_rules))}</span></div>
      <div class="k-sub">{esc(cadence_label)}</div>
    </a>
    <a class="kpi" href="#sec-risks" data-tone="{'crit' if critical_risks else 'warn' if high_or_critical_risks else 'good'}">
      <div class="k-label">Open risks</div>
      <div class="k-val">{esc(len(risks))}{f'<span class="unit">/ {critical_risks} crit</span>' if critical_risks else ''}</div>
      <div class="k-sub">Register tracked</div>
    </a>
    <a class="kpi" href="core/decisions.html" data-tone="{'warn' if decisions else 'good'}">
      <div class="k-label">Decisions</div>
      <div class="k-val">{esc(len(decisions))}</div>
      <div class="k-sub">Recorded choices</div>
    </a>
    <a class="kpi" href="#sec-reports" data-tone="info">
      <div class="k-label">Reports</div>
      <div class="k-val">{esc(report_count)}<span class="unit">/ {esc(len(REPORT_FOLDERS))}</span></div>
      <div class="k-sub">{esc(report_status)}</div>
    </a>
    <a class="kpi" href="learning/index.html">
      <div class="k-label">Learning due</div>
      <div class="k-val">{esc(learning_counts_value["due"])}<span class="unit">/ {esc(learning_counts_value["new"])} new</span></div>
      <div class="k-sub">Spaced repetition</div>
    </a>
    <a class="kpi" href="{esc(tech_stack_href)}" data-tone="good">
      <div class="k-label">Repos</div>
      <div class="k-val">{esc(repo_count)}</div>
      <div class="k-sub">Read-only sources</div>
    </a>
  </div>

  {setup_html}

  <section class="today" aria-label="Today">
    <div class="today-head">
      <h2><span class="pulse" aria-hidden="true"></span>What needs you today</h2>
      <span class="stamp">{esc(today.isoformat())} / generated {esc(generated_at.replace("T", " ").replace("Z", " UTC"))}</span>
    </div>
    <div class="today-grid">
      <div class="today-col">
        <div class="col-h">Decision revisit triggers <span class="cnt">{esc(len(decisions))}</span></div>
        {decision_rows}
      </div>
      <div class="today-col">
        <div class="col-h">Open risks by priority <span class="cnt">{esc(len(high_or_critical_risks))}</span></div>
        {top_risk_rows}
      </div>
      <div class="today-col">
        <div class="col-h">Operating cadence</div>
        {cadence_preview_html}
      </div>
    </div>
  </section>

  <details class="section" id="sec-risks" open>
    <summary>
      <span class="chev" aria-hidden="true"></span>
      <span class="sec-num">01</span>
      <span class="sec-title">Risk Register</span>
      <span class="sec-meta"><span data-risk-count data-total="{esc(len(risks))}">{esc(len(risks))} of {esc(len(risks))} shown</span></span>
    </summary>
    <div class="sec-body">
      <div class="toolbar">
        <span class="tb-label">Severity</span>
        <div class="chipset">
          <button type="button" class="chip" data-sev="all" aria-pressed="true">All</button>
          <button type="button" class="chip" data-sev="Critical" aria-pressed="false"><span class="swatch dot-crit"></span>Critical</button>
          <button type="button" class="chip" data-sev="High" aria-pressed="false"><span class="swatch dot-high"></span>High</button>
          <button type="button" class="chip" data-sev="Medium" aria-pressed="false"><span class="swatch dot-med"></span>Medium</button>
        </div>
        <span class="tb-spacer"></span>
        <span class="count-pill">{esc(critical_risks)} critical</span>
      </div>
      <div class="risk-list">{risk_cards}</div>
    </div>
  </details>

  <details class="section" id="sec-reports" open>
    <summary>
      <span class="chev" aria-hidden="true"></span>
      <span class="sec-num">02</span>
      <span class="sec-title">Reports</span>
      <span class="sec-meta" data-report-count>{esc(report_status)}</span>
    </summary>
    <div class="sec-body">
      <div class="reports">{''.join(report_sections)}</div>
    </div>
  </details>

  <details class="section" id="sec-core" open>
    <summary>
      <span class="chev" aria-hidden="true"></span>
      <span class="sec-num">03</span>
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
      <span class="sec-num">04</span>
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

  <details class="section" id="sec-commands">
    <summary>
      <span class="chev" aria-hidden="true"></span>
      <span class="sec-num">05</span>
      <span class="sec-title">Commands</span>
      <span class="sec-meta">{pluralize(command_card_count, "copy card")}</span>
    </summary>
    <div class="sec-body">
      <div class="cmd-groups">
        <section>
          <div class="cmd-group-h">AI Prompts</div>
          <div class="cmd-grid">{''.join(ai_prompt_items)}</div>
        </section>
        <section>
          <div class="cmd-group-h">Local Commands</div>
          <div class="cmd-grid">{''.join(local_command_items)}</div>
        </section>
      </div>
    </div>
  </details>
"""
    body = page_shell(
        content,
        eyebrow="Command Center - Day Zero CTO",
        title=f"{company} Day Zero CTO",
        subtitle=description,
    )
    write_html_page(wiki_root / "index.html", f"{company} Day Zero CTO", body, provenance)
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
        repos=args.repo,
    )

    written_report: Path | None = None
    if not args.init:
        if not args.kind:
            parser.error("--kind is required unless --init is used")
        if not args.title:
            parser.error("--title is required unless --init is used")

        report_sources: list[Path] = []
        if args.data_file:
            data_path = Path(args.data_file).expanduser()
            report_sources.append(data_path)
            data = json.loads(data_path.read_text(encoding="utf-8"))
            if not isinstance(data, dict):
                raise SystemExit("--data-file must contain a JSON object")
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
        report_path.write_text(render_report_page(args.title, args.date, args.kind, body, provenance), encoding="utf-8")
        update_manifest(wiki_root, provenance)
        written_report = report_path

    render_index(wiki_root, project_folder)
    print(written_report or wiki_root / "index.html")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))

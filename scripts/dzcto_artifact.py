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
    configured = str((config or {}).get("companyDescription") or "").strip()
    fallback = "Company context has not been captured yet. Add a Product Thesis section to the Strategy source file to enrich this summary."
    return plain_markdown(paragraph or configured or fallback)


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
        folder = values.get("folder") or values.get("report_folder") or values.get("kind")
        cadence = values.get("cadence") or values.get("frequency")
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
        ("Check Stale", f'dzcto check-stale "{project_folder}"'),
        ("Refresh Wiki", f'dzcto refresh "{project_folder}"'),
        ("Serve Dashboard", f'dzcto serve "{project_folder}"'),
        ("Doctor", f'dzcto doctor --project "{project_folder}"'),
        ("Issue Bundle", f'dzcto collect-issue-bundle "{project_folder}"'),
    ]


def copy_card(card_id: str, label: str, text: str, kind: str) -> str:
    button_label = f"Copy {kind}"
    return f"""<article class="copy-card">
  <div class="copy-card-header">
    <div>
      <strong>{esc(label)}</strong>
      <span>{esc(kind)}</span>
    </div>
    <button type="button" data-copy-target="{esc(card_id)}">{esc(button_label)}</button>
  </div>
  <pre id="{esc(card_id)}" class="copy-text">{esc(text)}</pre>
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
    return body.strip() or render_generic_report(data)


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
    return " · ".join(parts)


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


def base_css() -> str:
    return """
:root {
  --ink: #172033;
  --muted: #647084;
  --soft: #f5f7fa;
  --panel: #ffffff;
  --line: #d8e0ea;
  --accent: #145c78;
  --accent-soft: #e8f3f6;
  --warn: #9b5b00;
  --warn-soft: #fff4dd;
  --good: #176442;
  --good-soft: #e8f6ef;
  --danger: #9f1d25;
  --danger-soft: #ffe8eb;
}
* { box-sizing: border-box; }
body {
  margin: 0;
  color: var(--ink);
  background: linear-gradient(180deg, #f9fbfd 0, #fff 260px);
  font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
  line-height: 1.55;
}
main { width: 100%; max-width: 1180px; margin: 0 auto; padding: 36px 28px 64px; }
a { color: var(--accent); text-decoration: none; }
a:hover { text-decoration: underline; }
h1, h2, h3 { line-height: 1.15; letter-spacing: 0; margin: 0; }
h1 { font-size: 40px; }
h2 { font-size: 22px; }
h3 { font-size: 16px; }
p { color: var(--muted); margin: 0; }
h1, h2, h3, p, a, code, strong { overflow-wrap: anywhere; }
table { width: 100%; border-collapse: collapse; margin: 14px 0 22px; font-size: 14px; }
th, td { border: 1px solid var(--line); padding: 9px; text-align: left; vertical-align: top; }
th { background: var(--soft); color: var(--ink); }
code, pre { background: var(--soft); border: 1px solid var(--line); border-radius: 6px; }
code { padding: 1px 5px; }
pre { padding: 12px; overflow-x: auto; }
button {
  border: 1px solid #0f4f68;
  border-radius: 7px;
  background: var(--accent);
  color: #fff;
  cursor: pointer;
  font-weight: 700;
  padding: 9px 12px;
}
button:hover { background: #0f4f68; }
button:focus-visible, a:focus-visible, summary:focus-visible { outline: 3px solid #9bc7d6; outline-offset: 2px; }
.topbar { display: flex; justify-content: space-between; gap: 22px; align-items: flex-start; margin-bottom: 24px; }
.topbar > *, .status-card, .command-card, .core-card, .report-card, .learning-card, .help-command, .copy-card { min-width: 0; }
.eyebrow { color: var(--muted); font-size: 13px; font-weight: 800; letter-spacing: .08em; text-transform: uppercase; margin-bottom: 8px; }
.subtitle { max-width: 780px; margin-top: 10px; font-size: 17px; }
.actions { display: flex; flex-wrap: wrap; gap: 8px; align-items: center; justify-content: flex-end; }
.status-note { min-height: 20px; color: var(--muted); font-size: 13px; text-align: right; width: 100%; }
.status-grid { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 10px; margin: 22px 0; }
.status-card { border: 1px solid var(--line); border-radius: 8px; background: var(--panel); padding: 14px; }
.status-card span { display: block; color: var(--muted); font-size: 12px; font-weight: 800; text-transform: uppercase; }
.status-card strong { display: block; margin-top: 5px; font-size: 22px; }
.status-good { background: var(--good-soft); border-color: #afd9c4; }
.status-warn { background: var(--warn-soft); border-color: #ead49a; }
.status-danger { background: var(--danger-soft); border-color: #efb9bf; }
.command-strip { display: grid; grid-template-columns: 1.2fr 1fr; gap: 12px; margin: 18px 0 26px; }
.command-card, .cadence-alert, .cadence-ok { border: 1px solid var(--line); border-radius: 8px; background: var(--panel); padding: 14px; }
.command-card code, .cadence-alert code { display: block; margin-top: 8px; white-space: normal; overflow-wrap: anywhere; }
.wiki-details { border-top: 1px solid var(--line); padding: 22px 0; }
.wiki-details summary { display: flex; align-items: center; justify-content: space-between; gap: 18px; cursor: pointer; list-style: none; }
.wiki-details summary::-webkit-details-marker { display: none; }
.wiki-heading { display: flex; align-items: center; gap: 10px; font-size: 22px; font-weight: 800; line-height: 1.2; }
.wiki-chevron { width: 8px; height: 8px; border-right: 2px solid var(--muted); border-bottom: 2px solid var(--muted); transform: rotate(-45deg); transition: transform .15s ease; }
.wiki-details[open] .wiki-chevron { transform: rotate(45deg); }
.wiki-meta { color: var(--muted); font-size: 14px; text-align: right; white-space: nowrap; }
.wiki-body { margin-top: 14px; }
.core-grid { display: grid; grid-template-columns: repeat(5, minmax(0, 1fr)); gap: 10px; }
.core-card, .report-card, .learning-card, .help-command { border: 1px solid var(--line); border-radius: 8px; background: var(--panel); padding: 12px; color: var(--ink); }
.core-card:hover, .report-card:hover, .learning-card:hover { background: var(--soft); text-decoration: none; }
.core-title, .report-title, .learning-title, .help-command strong { display: block; font-weight: 800; }
.core-desc, .report-date, .report-count, .learning-meta, .help-command span { display: block; color: var(--muted); font-size: 13px; margin-top: 5px; }
.core-file { display: block; color: var(--muted); font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace; font-size: 12px; margin-top: 10px; }
.missing-card { background: var(--soft); }
.reports-grid { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 12px; }
.report-list { display: grid; gap: 8px; margin: 10px 0 0; padding: 0; list-style: none; }
.report-link { display: grid; grid-template-columns: 96px minmax(0, 1fr); gap: 10px; align-items: baseline; }
.report-date { font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace; margin-top: 0; }
.learning-grid, .help-grid, .copy-grid { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 10px; }
.help-command { display: grid; gap: 6px; }
.help-command code { display: block; white-space: normal; overflow-wrap: anywhere; }
.command-groups { display: grid; gap: 22px; }
.command-group h3 { margin-bottom: 10px; }
.copy-card { border: 1px solid var(--line); border-radius: 8px; background: var(--panel); padding: 12px; }
.copy-card-header { display: flex; justify-content: space-between; gap: 12px; align-items: flex-start; }
.copy-card-header strong, .copy-card-header span { display: block; }
.copy-card-header span { color: var(--muted); font-size: 12px; font-weight: 800; margin-top: 3px; text-transform: uppercase; }
.copy-card-header button { flex: 0 0 auto; padding: 7px 10px; }
.copy-text { margin: 12px 0 0; max-height: 136px; white-space: pre-wrap; overflow: auto; overflow-wrap: anywhere; font-size: 13px; }
.copy-status { display: block; min-height: 18px; margin-top: 7px; color: var(--good); font-size: 13px; }
.cadence-list { display: grid; gap: 10px; }
.cadence-alert { border-color: #e2b454; background: var(--warn-soft); }
.cadence-ok { border-color: #afd9c4; background: var(--good-soft); }
.artifact-section { margin-top: 30px; border-top: 1px solid var(--line); padding-top: 22px; }
.artifact-section:first-of-type { margin-top: 0; border-top: 0; padding-top: 0; }
.artifact-list { display: grid; gap: 10px; margin: 16px 0 24px; padding: 0; list-style: none; }
.artifact-list li { border: 1px solid var(--line); border-radius: 8px; padding: 12px; }
.artifact-list strong, .artifact-list span, .artifact-list em, .artifact-list small { display: block; }
.artifact-list span, .artifact-list em, .artifact-list small { margin-top: 4px; color: var(--muted); }
.artifact-list em, .artifact-list small { font-size: 13px; font-style: normal; }
.grid, .summary { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 12px; margin: 20px 0; }
.metric { border: 1px solid var(--line); border-radius: 8px; padding: 14px; background: var(--panel); }
.metric .label, .metric span { color: var(--muted); font-size: 13px; }
.metric .value, .metric strong { display: block; margin-top: 5px; font-size: 22px; font-weight: 800; color: var(--ink); }
.metric .detail { display: block; color: var(--muted); font-size: 13px; margin-top: 4px; }
.tag { display: inline-block; border-radius: 999px; padding: 2px 8px; font-size: 12px; font-weight: 800; white-space: nowrap; }
.high { color: var(--danger); background: var(--danger-soft); }
.medium { color: var(--warn); background: var(--warn-soft); }
.ready { color: var(--good); background: var(--good-soft); }
.empty-item { color: var(--muted); }
.nav { color: var(--muted); font-size: 14px; margin-bottom: 22px; }
.prose { max-width: 880px; }
.prose h2, .prose h3, .prose h4 { margin-top: 28px; }
.prose p, .prose ul { margin-top: 12px; }
@media (max-width: 920px) {
  main { padding: 30px 18px 52px; }
  h1 { font-size: 32px; }
  .topbar, .command-strip { grid-template-columns: 1fr; display: grid; }
  .actions { justify-content: flex-start; }
  .status-note { text-align: left; }
  .status-grid, .core-grid, .reports-grid, .learning-grid, .help-grid, .copy-grid, .summary, .grid { grid-template-columns: 1fr; }
  .report-link { grid-template-columns: 1fr; gap: 2px; }
  .wiki-details summary { align-items: flex-start; }
  .wiki-meta { text-align: left; white-space: normal; }
}
"""


def refresh_script() -> str:
    return """
<script>
(() => {
  const button = document.querySelector('[data-dzcto-refresh]');
  const status = document.querySelector('[data-dzcto-refresh-status]');
  if (button && status) {
    button.addEventListener('click', async () => {
      status.textContent = 'Refreshing...';
      if (location.protocol === 'file:') {
        status.textContent = 'Open with dzcto serve "<project folder>" to refresh from the browser.';
        return;
      }
      try {
        const response = await fetch('/__dzcto/refresh', { method: 'POST' });
        if (!response.ok) throw new Error(await response.text());
        status.textContent = 'Refreshed. Reloading...';
        location.reload();
      } catch (error) {
        status.textContent = 'Refresh failed. Run dzcto refresh "<project folder>" in a terminal.';
      }
    });
  }

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

  document.querySelectorAll('[data-copy-target]').forEach((copyButton) => {
    copyButton.addEventListener('click', async () => {
      const target = document.getElementById(copyButton.dataset.copyTarget);
      const copyStatus = document.querySelector(`[data-copy-status-for="${copyButton.dataset.copyTarget}"]`);
      if (!target) return;
      try {
        const copied = await copyText(target.textContent.trim());
        if (copied) {
          if (copyStatus) copyStatus.textContent = 'Copied';
          return;
        }
        const range = document.createRange();
        range.selectNodeContents(target);
        const selection = window.getSelection();
        selection.removeAllRanges();
        selection.addRange(range);
        if (copyStatus) copyStatus.textContent = 'Selected';
      } catch (error) {
        if (copyStatus) copyStatus.textContent = 'Select the text and copy manually';
      }
    });
  });
})();
</script>
"""


def write_html_page(path: Path, title: str, body: str, provenance: dict[str, Any]) -> None:
    path.write_text(
        f"""<!doctype html>
<html lang="en">
  <head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <title>{esc(title)}</title>
    <style>{base_css()}</style>
  </head>
  <body>
    {body}
    {provenance_block(provenance)}
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
    body = f"""
<main>
  <p class="nav"><a href="../index.html">Knowledge wiki index</a></p>
  <div class="topbar">
    <div>
      <p class="eyebrow">Learning</p>
      <h1>{esc(company)} Learning</h1>
      <p class="subtitle">Spaced repetition for system knowledge. Each prompt teaches one concept, records a self-rating, updates the mastery checklist, and schedules the next review.</p>
    </div>
  </div>
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
</main>
"""
    write_html_page(learning_dir / "index.html", f"{company} Learning", body, provenance)
    update_manifest(wiki_root, provenance)


def render_report_page(title: str, date: str, kind: str, body: str, provenance: dict[str, Any]) -> str:
    safe_title = esc(title)
    safe_date = esc(date)
    return f"""<!doctype html>
<html lang="en">
  <head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <title>{safe_title}</title>
    <style>{base_css()}</style>
  </head>
  <body>
    <main>
      <p class="nav"><a href="../../index.html">Knowledge wiki index</a></p>
      <div class="topbar">
        <div>
          <p class="eyebrow">{esc(REPORT_FOLDERS[kind])}</p>
          <h1>{safe_title}</h1>
          <p class="subtitle">{safe_date}</p>
        </div>
      </div>
      {body}
    </main>
    {provenance_block(provenance)}
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
        body = f"""
<main>
  <p class="nav"><a href="../index.html">Knowledge wiki index</a></p>
  <div class="topbar">
    <div>
      <p class="eyebrow">Core Context</p>
      <h1>{esc(title)}</h1>
      <p class="subtitle">{esc(description)}</p>
    </div>
  </div>
  <div class="status-grid">
    <div class="status-card {'status-good' if source_path.exists() else 'status-warn'}"><span>Status</span><strong>{esc(status)}</strong></div>
    <div class="status-card"><span>Source</span><strong>{esc(doc)}</strong></div>
    <div class="status-card"><span>Updated</span><strong>{esc(dt.date.today().isoformat())}</strong></div>
    <div class="status-card"><span>Page</span><strong>HTML</strong></div>
  </div>
  <section class="artifact-section prose">
    {content_html}
  </section>
</main>
"""
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
    report_sections = []
    for folder, label, links in report_entries:
        if links:
            items = "\n".join(
                f'<li class="report-link"><span class="report-date">{esc(report_run_date(path))}</span><a href="{esc(path.relative_to(wiki_root).as_posix())}">{esc(report_name(path))}</a></li>'
                for path in links[:5]
            )
        else:
            items = '<li class="empty-item">No reports yet.</li>'
        latest = report_run_date(links[0]) if links else "No runs"
        report_sections.append(
            f"""<article class="report-card">
  <span class="report-title">{esc(label)}</span>
  <span class="report-count">{pluralize(len(links), "artifact")} · latest {esc(latest)}</span>
  <ul class="report-list">{items}</ul>
</article>"""
        )

    core_links = []
    for page in core_pages:
        card_class = "core-card" if page["source_exists"] else "core-card missing-card"
        core_links.append(
            f"""<a class="{card_class}" href="{esc(page["html"])}">
  <span class="core-title">{esc(page["title"])}</span>
  <span class="core-desc">{esc(page["description"])}</span>
  <span class="core-file">{esc(Path(page["html"]).name)}</span>
</a>"""
        )

    cadence_rules = parse_cadence_rules(core_dir / "OPERATING_CADENCE.md")
    alerts = cadence_alerts(cadence_rules, reports_dir, today)
    learning_items = read_learning_items(learning_dir)
    learning_reviews = read_learning_reviews(learning_dir)
    write_learning_index(wiki_root, project_folder, company, learning_items, learning_reviews, today)

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
        report_status = f"{pluralize(report_count, 'artifact')} · All current"
    else:
        report_status = f"{pluralize(report_count, 'artifact')} · {pluralize(len(alerts), 'alert')}"
    learning_status = learning_summary(learning_items, today)
    learning_counts_value = learning_counts(learning_items, today)
    repos = [str(item).strip() for item in (config.get("codeRepos", []) or []) if str(item).strip()]
    repo_count = len(repos)

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
  <span class="learning-meta">{esc(learning_counts_value["active"] - learning_counts_value["new"])} seen · {esc(learning_counts_value["new"])} new</span>
</div>
"""

    generated_at = utc_now()
    provenance = provenance_payload(
        wiki_root,
        artifact_id="wiki-index",
        artifact_kind="wiki-index",
        relative_path="index.html",
        title=f"{company} Day Zero CTO Knowledge Wiki",
        generated_at=generated_at,
    )
    body = f"""
<main>
  <div class="topbar">
    <div>
      <p class="eyebrow">Command Center</p>
      <h1>{esc(company)} Day Zero CTO</h1>
      <p class="subtitle">{esc(description)}</p>
    </div>
    <div class="actions">
      <button type="button" data-dzcto-refresh>Refresh Cadence</button>
      <span class="status-note" data-dzcto-refresh-status></span>
    </div>
  </div>
  <div class="status-grid">
    <div class="status-card {cadence_class}"><span>Cadence</span><strong>{esc(cadence_label)}</strong></div>
    <div class="status-card"><span>Reports</span><strong>{esc(report_count)}</strong></div>
    <div class="status-card"><span>Learning Due</span><strong>{esc(learning_counts_value["due"])}</strong></div>
    <div class="status-card"><span>Repos</span><strong>{esc(repo_count)}</strong></div>
  </div>
  <div class="command-strip">
    <div class="command-card">
      <strong>Primary command</strong>
      <p>Run the next operating review from your agent or terminal.</p>
      <code>{esc(local_helper_commands(project_folder)[0][1])}</code>
    </div>
    <div class="command-card">
      <strong>Browser refresh</strong>
      <p>For the button to execute Python, open this wiki through the local server.</p>
      <code>{esc(local_helper_commands(project_folder)[2][1])}</code>
    </div>
  </div>
  <details class="wiki-details" open>
    <summary><span class="wiki-heading"><span class="wiki-chevron" aria-hidden="true"></span>Cadence</span><span class="wiki-meta">{esc(report_status)}</span></summary>
    <div class="wiki-body">{cadence_status_html}</div>
  </details>
  <details class="wiki-details" open>
    <summary><span class="wiki-heading"><span class="wiki-chevron" aria-hidden="true"></span>Core Context</span><span class="wiki-meta">{core_ready}/{len(CORE_DOCS)} ready</span></summary>
    <div class="wiki-body core-grid">{''.join(core_links)}</div>
  </details>
  <details class="wiki-details" open>
    <summary><span class="wiki-heading"><span class="wiki-chevron" aria-hidden="true"></span>Reports</span><span class="wiki-meta">{esc(report_status)}</span></summary>
    <div class="wiki-body reports-grid">{''.join(report_sections)}</div>
  </details>
  <details class="wiki-details" open>
    <summary><span class="wiki-heading"><span class="wiki-chevron" aria-hidden="true"></span>Learning</span><span class="wiki-meta">{esc(learning_status)}</span></summary>
    <div class="wiki-body learning-grid">{learning_cards}</div>
  </details>
  <details class="wiki-details">
    <summary><span class="wiki-heading"><span class="wiki-chevron" aria-hidden="true"></span>Commands</span><span class="wiki-meta">{pluralize(command_card_count, "copy card")}</span></summary>
    <div class="wiki-body command-groups">
      <section class="command-group">
        <h3>AI Prompts</h3>
        <div class="copy-grid">{''.join(ai_prompt_items)}</div>
      </section>
      <section class="command-group">
        <h3>Local Commands</h3>
        <div class="copy-grid">{''.join(local_command_items)}</div>
      </section>
    </div>
  </details>
</main>
{refresh_script()}
"""
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

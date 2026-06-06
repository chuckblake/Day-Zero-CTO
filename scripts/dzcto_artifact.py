#!/usr/bin/env python3
"""Generate Day Zero CTO wiki indexes and report artifacts.

Python-first helper for public installs. The older Ruby helper remains as a
compatibility fallback, but new docs and wrappers call this file.
"""

from __future__ import annotations

import argparse
import datetime as dt
import html
import json
import re
import sys
from pathlib import Path
from typing import Any

from dzcto_common import (
    ensure_sidecar,
    provenance_block,
    provenance_payload,
    source_hashes as collect_source_hashes,
    update_manifest,
    utc_now,
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


def esc(value: Any) -> str:
    return html.escape(str(value or ""), quote=True)


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


def company_name(strategy_path: Path, project_folder: Path) -> str:
    if strategy_path.exists():
        for line in strategy_path.read_text(encoding="utf-8").splitlines():
            if line.startswith("# "):
                title = re.sub(r"\s+Strategy$", "", line[2:].strip(), flags=re.I)
                return title
    return project_folder.name


def company_description(strategy_path: Path) -> str:
    paragraph = (
        first_markdown_paragraph(markdown_section(strategy_path, "Product Thesis"))
        or first_markdown_paragraph(markdown_section(strategy_path, "Stage"))
    )
    fallback = "Company context has not been captured yet. Add a Product Thesis section to core/STRATEGY.md to enrich this summary."
    return plain_markdown(paragraph or fallback)


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


def default_help_commands(company: str) -> list[tuple[str, str]]:
    return [
        ("Weekly CTO Review", f"Run the weekly CTO review for {company}."),
        ("CEO Update", f"Write the CEO engineering update for {company}."),
        ("Tech Stack", f"Review the codebase and create a Tech Stack report for {company}."),
        ("Engineering Risk Review", f"Run the engineering risk review for {company}."),
        ("Learning", f"Run a Day Zero CTO learning prompt for {company}."),
        ("Check Stale", 'dzcto check-stale "<project folder>"'),
        ("Doctor", 'dzcto doctor --project "<project folder>"'),
        ("Issue Bundle", 'dzcto collect-issue-bundle "<project folder>"'),
        ("Decision Help", f"Help me work through a CTO decision for {company}: <decision or problem>."),
        (
            "CTO Code Review",
            f"Run a CTO code review for {company} against <branch, PR, or diff>. Treat the repo as read-only unless I explicitly ask for code changes.",
        ),
    ]


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


def report_run_date(path: Path) -> str:
    match = re.match(r"^(\d{4}-\d{2}-\d{2})-", path.name)
    return match.group(1) if match else "Unknown date"


def report_name(path: Path) -> str:
    return re.sub(r"^\d{4}-\d{2}-\d{2}-", "", path.stem).replace("-", " ")


def display_file_name(path: Path) -> str:
    return re.sub(r"\.(html|md|txt)$", "", path.name, flags=re.I).replace("-", " ")


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
    learning_dir.joinpath("index.html").write_text(
        f"""<!doctype html>
<html lang="en">
  <head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <title>{esc(company)} Learning</title>
    <style>
      :root {{ --ink: #172033; --muted: #5d6a7d; --line: #d9e0ea; --soft: #f6f8fb; --accent: #185a7d; }}
      body {{ font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; line-height: 1.55; margin: 0; color: var(--ink); background: #fff; }}
      main {{ max-width: 980px; margin: 0 auto; padding: 44px 28px 64px; }}
      h1, h2 {{ line-height: 1.2; letter-spacing: 0; }}
      h1 {{ font-size: 34px; margin: 0 0 8px; }}
      h2 {{ font-size: 22px; margin-top: 32px; border-top: 1px solid var(--line); padding-top: 22px; }}
      p, span, li {{ color: var(--muted); }}
      a {{ color: var(--accent); }}
      .nav {{ color: var(--muted); font-size: 14px; margin-bottom: 22px; }}
      .summary {{ display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 12px; margin: 22px 0; }}
      .metric {{ border: 1px solid var(--line); border-radius: 8px; padding: 14px; }}
      .metric span {{ display: block; font-size: 13px; }}
      .metric strong {{ display: block; font-size: 22px; margin-top: 4px; }}
      table {{ width: 100%; border-collapse: collapse; margin-top: 14px; font-size: 14px; }}
      th, td {{ border: 1px solid var(--line); padding: 9px; text-align: left; vertical-align: top; }}
      th {{ background: var(--soft); }}
      code {{ background: var(--soft); border: 1px solid var(--line); border-radius: 4px; padding: 1px 4px; }}
      .empty-item {{ color: var(--muted); }}
      @media (max-width: 760px) {{ main {{ padding: 28px 18px 48px; }} .summary {{ grid-template-columns: 1fr; }} table {{ display: block; overflow-x: auto; }} }}
    </style>
  </head>
  <body>
    <main>
      <p class="nav"><a href="../index.html">Knowledge wiki index</a></p>
      <h1>{esc(company)} Learning</h1>
      <p>Spaced repetition for system knowledge. The learning skill presents one system concept, includes one quick check, records a self-rating, updates the mastery checklist, and schedules the next review from that answer.</p>
      <div class="summary">
        <div class="metric"><span>Active</span><strong>{counts["active"]}</strong></div>
        <div class="metric"><span>Due</span><strong>{counts["due"]}</strong></div>
        <div class="metric"><span>New</span><strong>{counts["new"]}</strong></div>
      </div>
      <h2>How Scoring Works</h2>
      <p>Reply with <code>Needs Work</code>, <code>Familiar</code>, or <code>Confident</code>. Needs Work brings the item back tomorrow, Familiar moves it forward one box, and Confident moves it forward two boxes.</p>
      <h2>Mastery Checklist</h2>
      {checklist_html}
      <h2>Items</h2>
      <table>
        <thead>
          <tr><th>Item</th><th>Status</th><th>Due</th><th>Box</th><th>Seen</th><th>Last rating</th><th>Source</th></tr>
        </thead>
        <tbody>{item_rows}</tbody>
      </table>
      <h2>Recent Reviews</h2>
      <ul>{review_rows}</ul>
    </main>
    {provenance_block(provenance)}
  </body>
</html>
""",
        encoding="utf-8",
    )
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
    <style>
      :root {{ --ink: #172033; --muted: #5d6a7d; --line: #d9e0ea; --soft: #f6f8fb; --accent: #185a7d; }}
      body {{ font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; line-height: 1.55; margin: 0; color: var(--ink); background: #fff; }}
      main {{ max-width: 980px; margin: 0 auto; padding: 44px 28px 64px; }}
      h1, h2, h3 {{ line-height: 1.2; letter-spacing: 0; }}
      h1 {{ font-size: 34px; margin: 0 0 6px; }}
      h2 {{ font-size: 23px; margin-top: 34px; border-top: 1px solid var(--line); padding-top: 24px; }}
      h3 {{ font-size: 18px; margin-top: 24px; }}
      .meta, .nav {{ color: var(--muted); }}
      .meta {{ margin: 0 0 30px; }}
      .nav {{ margin: 0 0 22px; font-size: 14px; }}
      a {{ color: var(--accent); }}
      table {{ border-collapse: collapse; width: 100%; margin: 16px 0 24px; font-size: 14px; }}
      th, td {{ border: 1px solid var(--line); padding: 9px; vertical-align: top; text-align: left; }}
      th {{ background: var(--soft); }}
      code {{ background: var(--soft); border: 1px solid var(--line); padding: 0.1rem 0.25rem; border-radius: 4px; }}
      .callout {{ background: var(--soft); border: 1px solid var(--line); border-radius: 8px; padding: 16px; margin: 18px 0; }}
      .artifact-section {{ margin-top: 34px; border-top: 1px solid var(--line); padding-top: 24px; }}
      .artifact-section:first-of-type {{ margin-top: 0; border-top: 0; padding-top: 0; }}
      .artifact-list {{ display: grid; gap: 10px; margin: 16px 0 24px; padding: 0; list-style: none; }}
      .artifact-list li {{ border: 1px solid var(--line); border-radius: 8px; padding: 12px; }}
      .artifact-list strong, .artifact-list span, .artifact-list em, .artifact-list small {{ display: block; }}
      .artifact-list span, .artifact-list em, .artifact-list small {{ margin-top: 4px; color: var(--muted); }}
      .artifact-list em, .artifact-list small {{ font-size: 13px; font-style: normal; }}
      .grid {{ display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 12px; margin: 20px 0 6px; }}
      .metric {{ border: 1px solid var(--line); border-radius: 8px; padding: 14px; background: #fff; }}
      .metric .label {{ color: var(--muted); font-size: 13px; }}
      .metric .value {{ display: block; margin-top: 5px; font-size: 22px; font-weight: 700; }}
      .metric .detail {{ display: block; color: var(--muted); font-size: 13px; margin-top: 4px; }}
      .tag {{ display: inline-block; border-radius: 999px; padding: 2px 8px; font-size: 12px; font-weight: 700; white-space: nowrap; }}
      .high {{ color: #9f1d25; background: #ffe8eb; }}
      .medium {{ color: #8a4b00; background: #fff4df; }}
      .ready {{ color: #16633d; background: #e8f6ef; }}
      .source-list {{ font-size: 14px; color: var(--muted); }}
      @media (max-width: 760px) {{ main {{ padding: 28px 18px 48px; }} .grid {{ grid-template-columns: 1fr; }} table {{ display: block; overflow-x: auto; }} }}
    </style>
  </head>
  <body>
    <main>
      <p class="nav"><a href="../../index.html">Knowledge wiki index</a></p>
      <h1>{safe_title}</h1>
      <p class="meta">{safe_date} · {esc(REPORT_FOLDERS[kind])}</p>
      {body}
    </main>
    {provenance_block(provenance)}
  </body>
</html>
"""


def render_index(wiki_root: Path, project_folder: Path) -> None:
    core_dir = wiki_root / "core"
    reports_dir = wiki_root / "reports"
    learning_dir = wiki_root / "learning"
    today = dt.date.today()
    ensure_sidecar(wiki_root, project_folder, "render-index")

    report_entries = [(folder, label, sorted((reports_dir / folder).glob("*.html"), reverse=True)) for folder, label in REPORT_FOLDERS.items()]
    report_count = sum(len(links) for _folder, _label, links in report_entries)
    report_sections = []
    for _folder, label, links in report_entries:
        if links:
            items = "\n".join(
                f'<li class="report-link"><span class="report-date">{esc(report_run_date(path))}</span><a href="{esc(path.relative_to(wiki_root).as_posix())}">{esc(report_name(path))}</a></li>'
                for path in links
            )
        else:
            items = '<li class="empty-item">No reports yet.</li>'
        report_sections.append(f'<section class="report-section"><h2>{esc(label)}</h2><ul class="report-list">{items}</ul></section>')

    core_links = []
    for doc in CORE_DOCS:
        title, description = CORE_DOC_META.get(doc, (doc, "Core CTO context."))
        path = core_dir / doc
        if path.exists():
            core_links.append(f'<a class="core-card" href="core/{esc(doc)}"><span class="core-title">{esc(title)}</span><span class="core-desc">{esc(description)}</span><span class="core-file">{esc(doc)}</span></a>')
        else:
            core_links.append(f'<div class="core-card missing-card"><span class="core-title">{esc(title)}</span><span class="core-desc">{esc(description)}</span><span class="core-file">{esc(doc)} not created yet</span></div>')

    handoff_paths = sorted(path for path in (wiki_root / "handoffs").glob("**/*") if path.is_file())
    handoff_links = (
        "\n".join(f'<li><a href="{esc(path.relative_to(wiki_root).as_posix())}">{esc(display_file_name(path))}</a></li>' for path in handoff_paths)
        if handoff_paths
        else '<li class="empty-item">No handoffs yet.</li>'
    )

    cadence_rules = parse_cadence_rules(core_dir / "OPERATING_CADENCE.md")
    alerts = cadence_alerts(cadence_rules, reports_dir, today)
    strategy_path = core_dir / "STRATEGY.md"
    company = company_name(strategy_path, project_folder)
    description = company_description(strategy_path)
    learning_items = read_learning_items(learning_dir)
    learning_reviews = read_learning_reviews(learning_dir)
    write_learning_index(wiki_root, project_folder, company, learning_items, learning_reviews, today)

    if not cadence_rules:
        cadence_status_html = ""
    elif not alerts:
        cadence_status_html = '<div class="cadence-watch"><h2>Cadence Watch</h2><p>All scheduled report cadences are current.</p></div>'
    else:
        alert_cards = "\n".join(
            f'<div class="cadence-alert"><div><strong>{esc(alert["label"])}</strong><span>{esc(alert["reason"])}</span></div><code>{esc(display_command(alert["command"]))}</code></div>'
            for alert in alerts
        )
        cadence_status_html = f'<div class="cadence-watch cadence-watch-alert"><h2>Cadence Alerts</h2><p>Generated from <a href="core/OPERATING_CADENCE.md">OPERATING_CADENCE.md</a>.</p><div class="cadence-list">{alert_cards}</div></div>'

    if not cadence_rules:
        report_status = pluralize(report_count, "artifact")
    elif not alerts:
        report_status = f"{pluralize(report_count, 'artifact')} · All current"
    else:
        report_status = f"{pluralize(report_count, 'artifact')} · {pluralize(len(alerts), 'alert')}"
    learning_status = learning_summary(learning_items, today)
    misc_status = pluralize(len(handoff_paths), "handoff")

    help_commands = [(rule["label"], display_command(rule["command"])) for rule in cadence_rules] + default_help_commands(company)
    seen: set[str] = set()
    help_items = []
    for label, command in help_commands:
        normalized = command.lower()
        if not command or normalized in seen:
            continue
        seen.add(normalized)
        help_items.append(f'<div class="help-command"><strong>{esc(label)}</strong><code>{esc(command)}</code></div>')

    generated_at = utc_now()
    provenance = provenance_payload(
        wiki_root,
        artifact_id="wiki-index",
        artifact_kind="wiki-index",
        relative_path="index.html",
        title=f"{company} Day Zero CTO Knowledge Wiki",
        generated_at=generated_at,
    )
    wiki_root.joinpath("index.html").write_text(
        f"""<!doctype html>
<html lang="en">
  <head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <title>{esc(company)} Day Zero CTO Knowledge Wiki</title>
    <style>
      :root {{ --ink: #172033; --muted: #5d6a7d; --line: #d9e0ea; --soft: #f6f8fb; --accent: #185a7d; }}
      body {{ font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; line-height: 1.55; margin: 0; color: var(--ink); background: #fff; }}
      main {{ max-width: 960px; margin: 0 auto; padding: 44px 28px 64px; }}
      h1, h2 {{ line-height: 1.2; letter-spacing: 0; }}
      h1 {{ font-size: 34px; margin: 0 0 8px; }}
      h2 {{ font-size: 22px; margin: 0 0 12px; }}
      p {{ color: var(--muted); margin: 0 0 18px; }}
      section {{ margin-top: 30px; border-top: 1px solid var(--line); padding-top: 24px; }}
      a {{ color: var(--accent); text-decoration: none; }}
      a:hover {{ text-decoration: underline; }}
      ul {{ margin: 12px 0 0 20px; padding: 0; }}
      li {{ margin: 6px 0; }}
      .company-label {{ color: var(--muted); font-size: 14px; font-weight: 700; margin: 0 0 8px; text-transform: uppercase; }}
      .company-description {{ font-size: 17px; margin-bottom: 12px; }}
      .report-list {{ margin-left: 0; list-style: none; }}
      .report-link {{ display: grid; grid-template-columns: 110px minmax(0, 1fr); gap: 14px; align-items: baseline; }}
      .report-date {{ color: var(--muted); font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace; font-size: 13px; }}
      .cadence-watch {{ margin: 6px 0 22px; }}
      .cadence-watch p {{ margin-bottom: 12px; }}
      .cadence-list {{ display: grid; gap: 10px; }}
      .cadence-alert {{ display: grid; grid-template-columns: minmax(0, 1fr); gap: 10px; border: 1px solid #e2b454; border-radius: 8px; background: #fff8e6; padding: 12px; }}
      .cadence-alert strong {{ display: block; margin-bottom: 2px; }}
      .cadence-alert span {{ color: var(--muted); font-size: 14px; }}
      .cadence-alert code {{ display: block; white-space: normal; overflow-wrap: anywhere; background: #fff; border: 1px solid #ead49a; border-radius: 6px; padding: 8px; color: var(--ink); }}
      .help-section p {{ max-width: 840px; }}
      .help-grid {{ display: grid; gap: 10px; margin-top: 14px; }}
      .help-command {{ display: grid; grid-template-columns: 180px minmax(0, 1fr); gap: 14px; align-items: start; border: 1px solid var(--line); border-radius: 8px; padding: 10px 12px; }}
      .help-command code {{ white-space: normal; overflow-wrap: anywhere; background: var(--soft); border: 1px solid var(--line); border-radius: 6px; padding: 7px; color: var(--ink); }}
      .wiki-details {{ margin-top: 30px; border-top: 1px solid var(--line); padding-top: 24px; }}
      .wiki-details summary {{ display: flex; align-items: center; justify-content: space-between; gap: 18px; cursor: pointer; list-style: none; }}
      .wiki-details summary::-webkit-details-marker {{ display: none; }}
      .wiki-heading {{ display: flex; align-items: center; gap: 10px; font-size: 22px; font-weight: 700; line-height: 1.2; }}
      .wiki-chevron {{ width: 8px; height: 8px; border-right: 2px solid var(--muted); border-bottom: 2px solid var(--muted); transform: rotate(-45deg); transition: transform 0.15s ease; }}
      .wiki-details[open] .wiki-chevron {{ transform: rotate(45deg); }}
      .wiki-meta {{ color: var(--muted); font-size: 14px; text-align: right; white-space: nowrap; }}
      .wiki-body {{ margin-top: 14px; }}
      .core-list {{ display: grid; grid-template-columns: 1fr; gap: 8px; margin-top: 12px; }}
      .core-card {{ display: grid; grid-template-columns: 220px minmax(0, 1fr) 190px; gap: 18px; align-items: center; box-sizing: border-box; border: 1px solid var(--line); border-radius: 8px; padding: 10px 12px; color: var(--ink); }}
      .core-card:hover {{ text-decoration: none; background: var(--soft); }}
      .core-title {{ font-weight: 700; }}
      .core-desc {{ color: var(--muted); font-size: 14px; }}
      .core-file {{ color: var(--muted); font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace; font-size: 12px; text-align: right; white-space: nowrap; }}
      .missing-card {{ background: var(--soft); }}
      .report-section {{ margin-top: 20px; border-top: 1px solid var(--line); padding-top: 18px; }}
      .report-section:first-of-type {{ margin-top: 0; border-top: 0; padding-top: 0; }}
      .misc-section {{ margin-top: 0; border-top: 0; padding-top: 0; }}
      .inline-meta {{ color: var(--muted); font-size: 14px; margin-left: 6px; }}
      .empty-item {{ color: var(--muted); }}
      @media (max-width: 760px) {{ main {{ padding: 28px 18px 48px; }} .report-link, .help-command {{ grid-template-columns: 1fr; gap: 4px; }} .wiki-details summary {{ align-items: flex-start; }} .wiki-meta {{ text-align: left; white-space: normal; }} .core-card {{ grid-template-columns: 1fr; gap: 3px; }} .core-file {{ text-align: left; white-space: normal; }} }}
    </style>
  </head>
  <body>
    <main>
      <p class="company-label">For {esc(company)}</p>
      <h1>{esc(company)} Day Zero CTO Knowledge Wiki</h1>
      <p class="company-description">{esc(description)}</p>
      <details class="wiki-details">
        <summary><span class="wiki-heading"><span class="wiki-chevron" aria-hidden="true"></span>Core Context</span><span class="wiki-meta">{pluralize(len(CORE_DOCS), "file")}</span></summary>
        <div class="wiki-body core-list">{''.join(core_links)}</div>
      </details>
      <details class="wiki-details">
        <summary><span class="wiki-heading"><span class="wiki-chevron" aria-hidden="true"></span>Reports</span><span class="wiki-meta">{esc(report_status)}</span></summary>
        <div class="wiki-body">{cadence_status_html}{''.join(report_sections)}</div>
      </details>
      <details class="wiki-details">
        <summary><span class="wiki-heading"><span class="wiki-chevron" aria-hidden="true"></span>Learning</span><span class="wiki-meta">{esc(learning_status)}</span></summary>
        <div class="wiki-body"><ul><li><a href="learning/index.html">Spaced repetition learning</a><span class="inline-meta">{esc(learning_status)}</span></li></ul></div>
      </details>
      <details class="wiki-details help-section">
        <summary><span class="wiki-heading"><span class="wiki-chevron" aria-hidden="true"></span>Help</span><span class="wiki-meta">{pluralize(len(help_items), "command")}</span></summary>
        <div class="wiki-body"><p>Ask your agent with one of these commands. Natural-language prompts can be pasted as-is; shell commands use <code>&lt;project folder&gt;</code> as a placeholder for this Day Zero CTO project folder.</p><div class="help-grid">{''.join(help_items)}</div></div>
      </details>
      <details class="wiki-details">
        <summary><span class="wiki-heading"><span class="wiki-chevron" aria-hidden="true"></span>Misc</span><span class="wiki-meta">{esc(misc_status)}</span></summary>
        <div class="wiki-body"><section class="misc-section"><h2>Handoffs</h2><ul>{handoff_links}</ul></section></div>
      </details>
    </main>
    {provenance_block(provenance)}
  </body>
</html>
""",
        encoding="utf-8",
    )
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
    (wiki_root / "handoffs").mkdir(parents=True, exist_ok=True)
    learning_dir.mkdir(parents=True, exist_ok=True)
    ensure_sidecar(wiki_root, project_folder, "init" if args.init else "generate-artifact")

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

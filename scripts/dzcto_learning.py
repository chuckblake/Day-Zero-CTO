#!/usr/bin/env python3
"""Manage Day Zero CTO spaced-repetition learning state."""

from __future__ import annotations

import argparse
import datetime as dt
import json
import re
import subprocess
import sys
from pathlib import Path
from typing import Any


TARGET_NEW_RATE = 0.35
RECENT_WINDOW = 12
REVIEW_PRESSURE_LIMIT = 3
STALE_REVIEW_DAYS = 3
INTERVALS = [1, 3, 7, 14, 30, 60]

RATINGS = {
    "needs_work": {
        "label": "Needs Work",
        "aliases": {"needs work", "needs_work", "work", "not", "no", "missed", "lost", "rough", "0"},
    },
    "familiar": {
        "label": "Familiar",
        "aliases": {"familiar", "neutral", "partial", "some", "fuzzy", "1"},
    },
    "confident": {
        "label": "Confident",
        "aliases": {"confident", "know", "solid", "clear", "got it", "2"},
    },
}


def slugify(value: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
    return slug or "learning-item"


def date_value(value: Any) -> dt.date | None:
    try:
        return dt.date.fromisoformat(str(value))
    except (TypeError, ValueError):
        return None


def wiki_root(project: Path) -> Path:
    return project / "knowledge" / "wiki"


def learning_dir(project: Path) -> Path:
    return wiki_root(project) / "learning"


def items_path(project: Path) -> Path:
    return learning_dir(project) / "items.json"


def reviews_path(project: Path) -> Path:
    return learning_dir(project) / "reviews.jsonl"


def current_path(project: Path) -> Path:
    return learning_dir(project) / "current.json"


def checklist_dir(project: Path) -> Path:
    return learning_dir(project) / "checklists"


def checklist_path(project: Path) -> Path:
    return checklist_dir(project) / "mastery.md"


def ensure_learning_dir(project: Path) -> None:
    learning_dir(project).mkdir(parents=True, exist_ok=True)
    checklist_dir(project).mkdir(parents=True, exist_ok=True)


def read_json(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return default


def load_items(project: Path) -> list[dict[str, Any]]:
    ensure_learning_dir(project)
    value = read_json(items_path(project), [])
    return value if isinstance(value, list) else []


def save_items(project: Path, items: list[dict[str, Any]]) -> None:
    ensure_learning_dir(project)
    items_path(project).write_text(json.dumps(items, indent=2) + "\n", encoding="utf-8")


def load_reviews(project: Path) -> list[dict[str, Any]]:
    ensure_learning_dir(project)
    path = reviews_path(project)
    if not path.exists():
        return []

    reviews: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        try:
            value = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(value, dict):
            reviews.append(value)
    return reviews


def append_review(project: Path, review: dict[str, Any]) -> None:
    ensure_learning_dir(project)
    with reviews_path(project).open("a", encoding="utf-8") as file:
        file.write(json.dumps(review, separators=(",", ":")) + "\n")


def load_current(project: Path) -> dict[str, Any] | None:
    value = read_json(current_path(project), None)
    return value if isinstance(value, dict) else None


def save_current(project: Path, item: dict[str, Any], kind: str, today: dt.date) -> None:
    current_path(project).write_text(
        json.dumps({"id": item["id"], "kind": kind, "selected_on": today.isoformat()}, indent=2) + "\n",
        encoding="utf-8",
    )


def clear_current(project: Path) -> None:
    current_path(project).unlink(missing_ok=True)


def refresh_index(project: Path) -> None:
    script = Path(__file__).resolve().with_name("dzcto_artifact.py")
    result = subprocess.run(
        [sys.executable, str(script), "--project", str(project), "--init"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        check=False,
    )
    if result.returncode != 0:
        print("Warning: failed to refresh wiki index", file=sys.stderr)


def rating_options() -> list[dict[str, str]]:
    return [{"rating": key, "label": config["label"]} for key, config in RATINGS.items()]


def normalize_rating(value: str | None) -> str | None:
    normalized = (value or "").strip().lower()
    for key, config in RATINGS.items():
        if normalized in config["aliases"]:
            return key
    return None


def active_items(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [item for item in items if item.get("status", "active") == "active"]


def sort_new_items(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return sorted(items, key=lambda item: (str(item.get("created_on", "")), str(item.get("title", "")).lower()))


def sort_due_items(items: list[dict[str, Any]], today: dt.date) -> list[dict[str, Any]]:
    return sorted(
        items,
        key=lambda item: (
            date_value(item.get("due_on")) or today,
            int(item.get("box", 0) or 0),
            str(item.get("last_seen_on", "")),
            str(item.get("title", "")).lower(),
        ),
    )


def choose_learning_item(items: list[dict[str, Any]], reviews: list[dict[str, Any]], today: dt.date) -> dict[str, Any]:
    active = active_items(items)
    new_items = [item for item in active if int(item.get("seen_count", 0) or 0) == 0]
    due_items = []
    for item in active:
        due_on = date_value(item.get("due_on"))
        if int(item.get("seen_count", 0) or 0) > 0 and due_on and due_on <= today:
            due_items.append(item)

    if not due_items and not new_items:
        return {
            "kind": "new_needed",
            "reason": "No due review items or unseen learning items exist. Create one new system concept from current project context.",
        }

    review_pressure = len(due_items) >= REVIEW_PRESSURE_LIMIT or any(
        (date_value(item.get("due_on")) or today) <= today - dt.timedelta(days=STALE_REVIEW_DAYS)
        for item in due_items
    )

    if due_items and review_pressure:
        kind = "review"
    elif due_items and new_items:
        recent = reviews[-RECENT_WINDOW:]
        recent_new_rate = 0.0 if not recent else sum(1 for review in recent if review.get("kind") == "new") / len(recent)
        kind = "new" if recent_new_rate < TARGET_NEW_RATE else "review"
    elif due_items:
        kind = "review"
    else:
        kind = "new"

    item = sort_due_items(due_items, today)[0] if kind == "review" else sort_new_items(new_items)[0]
    return {
        "kind": kind,
        "item": item,
        "reason": "Selected from due review items." if kind == "review" else "Selected from unseen learning items.",
    }


def unique_id(base: str, items: list[dict[str, Any]]) -> str:
    candidate = slugify(base)
    taken = {item.get("id") for item in items}
    if candidate not in taken:
        return candidate

    counter = 2
    while True:
        next_candidate = f"{candidate}-{counter}"
        if next_candidate not in taken:
            return next_candidate
        counter += 1


def item_payload(item: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": item.get("id"),
        "title": item.get("title"),
        "summary": item.get("summary"),
        "details": item.get("details"),
        "source": item.get("source"),
        "tags": item.get("tags") or [],
        "box": item.get("box", 0),
        "seen_count": item.get("seen_count", 0),
        "due_on": item.get("due_on"),
        "last_rating": item.get("last_rating"),
        "mastered_on": item.get("mastered_on"),
    }


def learning_stats(items: list[dict[str, Any]], today: dt.date) -> dict[str, int]:
    active = active_items(items)
    due = 0
    for item in active:
        due_on = date_value(item.get("due_on"))
        if int(item.get("seen_count", 0) or 0) > 0 and due_on and due_on <= today:
            due += 1
    unseen = sum(1 for item in active if int(item.get("seen_count", 0) or 0) == 0)
    mastered = sum(1 for item in active if item.get("mastered_on"))
    return {"active": len(active), "due": due, "new": unseen, "mastered": mastered}


def write_mastery_checklist(project: Path, items: list[dict[str, Any]], today: dt.date) -> dict[str, Any]:
    ensure_learning_dir(project)
    active = sorted(active_items(items), key=lambda item: str(item.get("title", "")).lower())
    total = len(active)
    confirmed = sum(1 for item in active if item.get("mastered_on"))

    lines = [
        "---",
        "source: Day Zero CTO learning",
        f"updated_on: {today.isoformat()}",
        "---",
        "",
        "# Learning Mastery Checklist",
        "",
        f"Progress: {confirmed}/{total} concepts confirmed",
        "",
        "## Active Concepts",
        "",
    ]

    if active:
        for item in active:
            mark = "x" if item.get("mastered_on") else " "
            source = item.get("source") or "Unknown"
            lines.append(f"- [{mark}] {item.get('title')} (`{item.get('id')}`) - {source}")
    else:
        lines.append("_No active learning items yet._")

    lines.append("")
    checklist_path(project).write_text("\n".join(lines), encoding="utf-8")
    percent = round((confirmed / total) * 100) if total else 0
    return {
        "path": str(checklist_path(project)),
        "confirmed": confirmed,
        "total": total,
        "percent": percent,
    }


def add_or_update_item(
    items: list[dict[str, Any]],
    today: dt.date,
    *,
    item_id: str | None,
    title: str,
    summary: str,
    details: str,
    source: str | None,
    tags: list[str],
    due_on: str | None = None,
    created_on: str | None = None,
) -> tuple[dict[str, Any], bool]:
    actual_id = item_id or unique_id(title, items)
    existing = next((item for item in items if item.get("id") == actual_id), None)
    item = existing or {
        "id": actual_id,
        "created_on": created_on or today.isoformat(),
        "seen_count": 0,
        "box": 0,
        "status": "active",
    }

    item.update(
        {
            "title": title,
            "summary": summary,
            "details": details or summary,
            "source": source or "Unknown",
            "tags": tags,
            "due_on": item.get("due_on") or due_on or today.isoformat(),
        }
    )

    if not existing:
        items.append(item)
    return item, existing is not None


def parse_tags(value: Any) -> list[str]:
    if isinstance(value, list):
        return [str(tag).strip() for tag in value if str(tag).strip()]
    return [tag.strip() for tag in str(value or "").split(",") if tag.strip()]


def compact(value: dict[str, Any]) -> dict[str, Any]:
    return {key: item for key, item in value.items() if item is not None}


def output(payload: dict[str, Any]) -> None:
    print(json.dumps(payload, indent=2))


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description="Manage Day Zero CTO learning")
    parser.add_argument("--project", required=True, help="Project folder; uses PATH/knowledge/wiki/learning")
    parser.add_argument("--date", default=dt.date.today().isoformat())
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--select", action="store_true", help="Select a learning item")
    mode.add_argument("--add", action="store_true", help="Add a learning item")
    mode.add_argument("--seed-file", help="Add multiple learning items from a JSON array")
    mode.add_argument("--record", help="Record rating: Needs Work, Familiar, or Confident")
    mode.add_argument("--stats", action="store_true", help="Print learning stats")
    parser.add_argument("--id", help="Learning item id")
    parser.add_argument("--title", help="Learning item title")
    parser.add_argument("--summary", help="One-sentence learning item summary")
    parser.add_argument("--details", help="Learning item explanation")
    parser.add_argument("--details-file", help="File containing learning item explanation")
    parser.add_argument("--source", help="Source file or artifact")
    parser.add_argument("--tags", help="Comma-separated tags")
    parser.add_argument("--note", help="Optional review note")
    args = parser.parse_args(argv)

    project = Path(args.project).expanduser().resolve()
    # Operating on a project whose wiki does not exist is almost always an agent
    # passing the company NAME instead of the project FOLDER path; fail loudly
    # rather than silently creating a stray directory. (Onboarding runs `dzcto
    # init` first, so the wiki already exists by the time learning items are seeded.)
    if not wiki_root(project).exists():
        raise SystemExit(
            f"No Day Zero CTO wiki found at {wiki_root(project)}.\n"
            f"--project must be the project FOLDER path (for example ~/Documents/Acme CTO), "
            f"not a company name.\n"
            f"If this project has not been set up yet, run `dzcto init` on the project folder first."
        )
    today = dt.date.fromisoformat(args.date)
    ensure_learning_dir(project)

    if args.add:
        if not args.title:
            raise SystemExit("--title is required with --add")
        if not args.summary:
            raise SystemExit("--summary is required with --add")

        items = load_items(project)
        details = Path(args.details_file).expanduser().read_text(encoding="utf-8") if args.details_file else (args.details or "")
        item, existed = add_or_update_item(
            items,
            today,
            item_id=args.id,
            title=args.title,
            summary=args.summary,
            details=details,
            source=args.source,
            tags=parse_tags(args.tags),
        )
        save_items(project, items)
        save_current(project, item, "new", today)
        checklist = write_mastery_checklist(project, items, today)
        refresh_index(project)
        output(
            {
                "status": "updated" if existed else "added",
                "kind": "new",
                "item": item_payload(item),
                "checklist": checklist,
                "rating_options": rating_options(),
            }
        )
        return 0

    if args.seed_file:
        seed_items = json.loads(Path(args.seed_file).expanduser().read_text(encoding="utf-8"))
        if not isinstance(seed_items, list):
            raise SystemExit("--seed-file must contain a JSON array")

        items = load_items(project)
        added: list[dict[str, Any]] = []
        updated: list[dict[str, Any]] = []
        for seed in seed_items:
            if not isinstance(seed, dict):
                continue
            title = str(seed.get("title") or "").strip()
            summary = str(seed.get("summary") or "").strip()
            if not title or not summary:
                continue
            item, existed = add_or_update_item(
                items,
                today,
                item_id=str(seed.get("id") or "").strip() or None,
                title=title,
                summary=summary,
                details=str(seed.get("details") or summary),
                source=str(seed.get("source") or "Onboarding"),
                tags=parse_tags(seed.get("tags")),
                due_on=str(seed.get("due_on") or today.isoformat()),
                created_on=str(seed.get("created_on") or today.isoformat()),
            )
            updated.append(item) if existed else added.append(item)

        save_items(project, items)
        checklist = write_mastery_checklist(project, items, today)
        refresh_index(project)
        output(
            {
                "status": "seeded",
                "added": len(added),
                "updated": len(updated),
                "items": [item_payload(item) for item in added + updated],
                "stats": learning_stats(items, today),
                "checklist": checklist,
                "rating_options": rating_options(),
            }
        )
        return 0

    if args.record:
        rating = normalize_rating(args.record)
        if not rating:
            raise SystemExit(f"Unknown rating '{args.record}'. Use Needs Work, Familiar, or Confident.")

        items = load_items(project)
        current = load_current(project)
        item_id = args.id or (current or {}).get("id")
        if not item_id:
            raise SystemExit("No current learning item. Run --select or pass --id.")

        item = next((candidate for candidate in items if candidate.get("id") == item_id), None)
        if not item:
            raise SystemExit(f"Unknown learning item id '{item_id}'")

        previous_box = int(item.get("box", 0) or 0)
        previous_seen_count = int(item.get("seen_count", 0) or 0)
        kind = (current or {}).get("kind") or ("new" if previous_seen_count == 0 else "review")

        if rating == "needs_work":
            next_box = max(previous_box - 1, 0)
        elif rating == "familiar":
            next_box = min(previous_box + 1, len(INTERVALS) - 1)
        else:
            next_box = min(previous_box + 2, len(INTERVALS) - 1)

        interval = 1 if rating == "needs_work" else INTERVALS[next_box]
        due_on = today + dt.timedelta(days=interval)
        item["box"] = next_box
        item["seen_count"] = previous_seen_count + 1
        item["last_seen_on"] = today.isoformat()
        item["last_rating"] = RATINGS[rating]["label"]
        item["due_on"] = due_on.isoformat()
        if rating == "confident":
            item["mastered_on"] = item.get("mastered_on") or today.isoformat()
        else:
            item.pop("mastered_on", None)

        review = compact(
            {
                "reviewed_on": today.isoformat(),
                "id": item.get("id"),
                "title": item.get("title"),
                "kind": kind,
                "rating": rating,
                "rating_label": RATINGS[rating]["label"],
                "previous_box": previous_box,
                "next_box": next_box,
                "previous_seen_count": previous_seen_count,
                "next_seen_count": item["seen_count"],
                "due_on": due_on.isoformat(),
                "mastered": rating == "confident",
                "note": args.note,
            }
        )

        save_items(project, items)
        append_review(project, review)
        clear_current(project)
        checklist = write_mastery_checklist(project, items, today)
        refresh_index(project)
        output({"status": "recorded", "review": review, "item": item_payload(item), "stats": learning_stats(items, today), "checklist": checklist})
        return 0

    if args.stats:
        items = load_items(project)
        checklist = write_mastery_checklist(project, items, today)
        refresh_index(project)
        output({"status": "stats", "stats": learning_stats(items, today), "checklist": checklist, "rating_options": rating_options()})
        return 0

    items = load_items(project)
    reviews = load_reviews(project)
    checklist = write_mastery_checklist(project, items, today)
    selection = choose_learning_item(items, reviews, today)
    algorithm = f"Review debt first; otherwise target {round((1 - TARGET_NEW_RATE) * 100)}% review and {round(TARGET_NEW_RATE * 100)}% new over the last {RECENT_WINDOW} logged sessions."

    if selection.get("item"):
        save_current(project, selection["item"], selection["kind"], today)
        refresh_index(project)
        output(
            {
                "status": "selected",
                "kind": selection["kind"],
                "reason": selection["reason"],
                "item": item_payload(selection["item"]),
                "checklist": checklist,
                "rating_options": rating_options(),
                "algorithm": algorithm,
            }
        )
    else:
        refresh_index(project)
        output(
            {
                "status": "new_needed",
                "kind": "new",
                "reason": selection["reason"],
                "checklist": checklist,
                "rating_options": rating_options(),
                "algorithm": algorithm,
            }
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))

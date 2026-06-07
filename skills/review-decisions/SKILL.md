---
name: review-decisions
description: "Review the Day Zero CTO decision log by walking the user through recorded decisions whose revisit triggers are due, unclear, or selected for review. Use when the user asks to review decisions, resolve open decision reviews, formalize a decision, punt a decision to a later date, revisit architectural choices, clean up pending-looking decisions, or work through DECISIONS.md one row at a time."
---

# Review Decisions

Run a decision-review ritual over the project decision log. `DECISIONS.md` is a record of decisions already taken; `Revisit Trigger` is what makes a row worth reviewing again. The generated `decisions/registry.json` and `core/decisions.html` page are indexes over the Markdown source plus report decision signals; do not edit them directly.

## Workflow

1. Resolve the Day Zero CTO project folder. Read `<project>/knowledge/wiki/core/DECISIONS.md`, plus `STRATEGY.md`, `RISKS.md`, recent relevant reports, and read-only repo evidence only as needed. If `<project>/knowledge/wiki/decisions/registry.json` exists, use it for stable decision IDs and matched report-signal context, but treat `DECISIONS.md` as the editable source.
2. Build the review queue from rows whose `Revisit Trigger` appears due, stale, unclear, blocked, or selected by the user. Also inspect unmatched report decision signals and promote only durable choices into `DECISIONS.md`; dismiss ordinary asks or open questions. If the user says "all decisions", walk every row. Do not describe every recorded row as pending.
3. For each queued decision, show a compact brief:
   - Original decision and date.
   - Context and rationale.
   - Revisit trigger.
   - Any current evidence or unknowns.
4. Ask the user for one outcome at a time:
   - `Reaffirm`: the original decision still stands.
   - `Supersede`: a new formal decision replaces or changes it.
   - `Punt`: no decision change now; set a later date or trigger.
   - `Needs evidence`: name the missing evidence and owner before deciding.
5. Draft the exact Markdown update and ask for approval before writing unless the user explicitly asked you to apply changes directly.
6. Preserve original decision history. Do not overwrite the original decision date with the review date. If a prior date is unknown but clearly predates current work, use an approximate date such as `Pre-2026` only when the user approves.
7. Update `<project>/knowledge/wiki/core/DECISIONS.md`:
   - Keep the main table as the decision log.
   - Use past-tense rationale for decisions already made.
   - Update `Revisit Trigger` when the review outcome is a punt or a new trigger is known.
   - Add or update a `## Review History` table when useful, with `Review Date`, `Decision`, `Outcome`, `Notes`, and `Next Revisit`.
8. Regenerate the wiki:

   ```bash
   dzcto refresh "<project folder>"
   ```

9. After refresh, the generated Decisions page should show an updated Current Read summary, any report-derived `Decision Signals From Reports`, and the canonical decision registry rendered from `DECISIONS.md`. Summarize decided, reaffirmed, superseded, punted, and evidence-needed items, plus the next review date or trigger for each punt.

## Standards

- Be explicit about "recorded decision" versus "decision needing review."
- Do not hand-edit generated Current Read summaries, registry JSON, or generated HTML; they regenerate from `DECISIONS.md` and structured report decision signals on refresh.
- Favor a clear punt over fake certainty: punt only with a date, event, owner, or evidence trigger.
- For architectural decisions already taken, make rationale read as historical explanation, not future justification.
- If the user makes a new decision in chat, capture the decision, rationale, owner, and revisit trigger before moving to the next item.
- Keep the loop calm and sequential; do not ask the user to review a large table all at once.

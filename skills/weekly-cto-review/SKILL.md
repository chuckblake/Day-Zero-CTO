---
name: weekly-cto-review
description: "Run a recurring startup CTO review and create a durable HTML weekly review in the project knowledge wiki. Use when the user asks for a weekly CTO review, engineering health check, startup operating review, leadership recap, next-week technical priorities, or a regular ceremony that summarizes delivery, risk, decisions, team/process health, and CEO-update material."
---

# Weekly CTO Review

Turn scattered engineering activity into a clear operating picture and next-week focus.

## Workflow

1. Resolve the project folder. If unknown, ask for it and recommend `~/Documents/<Company>/`. Durable outputs live under `<project>/knowledge/wiki/`.
2. Resolve an optional code repo pointer separately. Treat the code repo as read-only evidence unless the user explicitly asks for code changes.
3. Load context files from `<project>/knowledge/wiki/` if present: `core/STRATEGY.md`, `core/TEAM.md`, `core/OPERATING_CADENCE.md`, `core/DECISIONS.md`, `core/RISKS.md`, and recent reports.
4. Gather current evidence from available read-only sources: recent commits, open diffs, test/CI status, issues, project docs, incidents, and user-provided notes.
5. Compare progress against the company's current goals, not against generic engineering ideals.
6. Identify the smallest useful set of decisions, risks, and next actions.
7. Write the canonical review as an HTML artifact under `<project>/knowledge/wiki/reports/weekly-reviews/` and regenerate `<project>/knowledge/wiki/index.html`.
8. Summarize the review in chat and link to the generated artifact.

## Review Sections

- `Executive read`: one paragraph on the state of engineering.
- `Shipped / learned`: meaningful progress and what it changed.
- `Risks`: the risks most likely to threaten the current company goals.
- `Decisions needed`: choices that need founder, CEO, product, or engineering attention.
- `Team and process`: load, coordination, morale signals, review bottlenecks, hiring gaps, or meeting debt.
- `Next-week focus`: 3-5 priorities with clear owners when known.
- `CEO-update seeds`: bullets that can feed `write-ceo-update`.

## Durable Artifact

Use the helper script from this plugin:

```bash
scripts/dzcto-artifact.rb --project "<project folder>" --kind weekly-reviews --title "Weekly CTO Review" --body-file "<html body file>"
```

The report body should be HTML. Keep the chat response brief; the HTML file is the durable record.

## Standards

- Do not manufacture metrics. Say when evidence is missing.
- Prefer fewer sharper risks over a long risk catalog.
- Distinguish delivery slippage, product uncertainty, technical risk, and people/process risk.
- Preserve or update `core/RISKS.md` and `core/DECISIONS.md` only in the project knowledge wiki, and only when the user asks for durable follow-through.
- Do not write Day Zero CTO reports into the code repo by default.

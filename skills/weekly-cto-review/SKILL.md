---
name: weekly-cto-review
description: "Run a recurring startup CTO review. Use when the user asks for a weekly CTO review, engineering health check, startup operating review, leadership recap, next-week technical priorities, or a regular ceremony that summarizes delivery, risk, decisions, team/process health, and CEO-update material."
---

# Weekly CTO Review

Turn scattered engineering activity into a clear operating picture and next-week focus.

## Workflow

1. Load context files if present: `STRATEGY.md`, `TEAM.md`, `OPERATING_CADENCE.md`, `DECISIONS.md`, `RISKS.md`, and recent planning docs.
2. Gather current evidence from local sources that are available: recent commits, open diffs, test/CI status, issues, project docs, incidents, and user-provided notes.
3. Compare progress against the company's current goals, not against generic engineering ideals.
4. Identify the smallest useful set of decisions, risks, and next actions.
5. Produce a concise review. If the user wants an artifact, write it under `reports/cto-weekly/YYYY-MM-DD.md`.

## Review Sections

- `Executive read`: one paragraph on the state of engineering.
- `Shipped / learned`: meaningful progress and what it changed.
- `Risks`: the risks most likely to threaten the current company goals.
- `Decisions needed`: choices that need founder, CEO, product, or engineering attention.
- `Team and process`: load, coordination, morale signals, review bottlenecks, hiring gaps, or meeting debt.
- `Next-week focus`: 3-5 priorities with clear owners when known.
- `CEO-update seeds`: bullets that can feed `write-ceo-update`.

## Standards

- Do not manufacture metrics. Say when evidence is missing.
- Prefer fewer sharper risks over a long risk catalog.
- Distinguish delivery slippage, product uncertainty, technical risk, and people/process risk.
- Preserve or update `RISKS.md` and `DECISIONS.md` only when the user asks for durable follow-through.

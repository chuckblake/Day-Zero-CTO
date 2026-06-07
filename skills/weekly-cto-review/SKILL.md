---
name: weekly-cto-review
description: "Run the recurring Day Zero CTO weekly review and durable HTML report. Use for weekly CTO review, engineering health, startup operating review, leadership recap, next-week priorities, delivery, risks, decisions, team/process, or CEO-update seeds."
---

# Weekly CTO Review

Turn scattered engineering activity into a clear operating picture and next-week focus.

## Workflow

1. Resolve the project folder. If unknown, ask for it and recommend `~/Documents/<Company>/`. Durable outputs live under `<project>/knowledge/wiki/`.
2. Resolve one or more optional code repo pointers separately. Treat code repos as read-only evidence unless the user explicitly asks for code changes.
3. Load context files from `<project>/knowledge/wiki/` if present: `core/STRATEGY.md`, `core/TEAM.md`, `core/OPERATING_CADENCE.md`, `core/DECISIONS.md`, `core/RISKS.md`, and recent reports.
4. Gather current evidence from available read-only sources: recent commits, open diffs, test/CI status, issues, project docs, incidents, and user-provided notes. Prefer local read-only Git history when available.
5. Compare progress against the company's current goals, not against generic engineering ideals.
6. Identify the smallest useful set of decisions, risks, and next actions.
7. Write the canonical review as an HTML artifact under `<project>/knowledge/wiki/reports/weekly-reviews/`. The artifact command refreshes the dashboard automatically.
8. Summarize the review in chat and link to the generated artifact.

## Review Sections

- `Executive read`: one paragraph on the state of engineering.
- `Shipped / learned`: meaningful progress and what it changed.
- `Risks`: the risks most likely to threaten the current company goals.
- `Decisions needed`: choices that need founder, CEO, product, or engineering attention.
- `Team and process`: load, coordination, morale signals, review bottlenecks, hiring gaps, or meeting debt.
- `Next-week focus`: 3-5 priorities with clear owners when known.
- `CEO-update seeds`: bullets that can feed `write-ceo-update`.

## Git Evidence

For weekly reviews, repo access explains the system and Git history explains the week. Prefer read-only Git commands when available:

- `git status --short`
- `git log --since="<start date>" --date=short --pretty=format:"%h %ad %an %s"`
- `git diff --stat <base>..HEAD` when a safe base is known
- `git shortlog -sn --since="<start date>"` when contributor shape matters

Do not run network or mutating Git commands such as `git pull`, `git push`, `git checkout`, `git reset`, or branch-changing commands unless the user explicitly asks. If Git history is unavailable, still run the review from the project wiki, prior reports, user notes, and code snapshot, but label delivery/progress conclusions as limited by missing Git history.

## Durable Artifact

Write structured JSON report data, then use the helper from this plugin. Prefer the `dzcto` wrapper when it is on `PATH`; otherwise run the Python command from the plugin repo:

Required JSON fields: `executive_read`, `shipped_learned`, `risks`, `decisions_needed`, `team_process`, `next_week_focus`, `ceo_update_seeds`, and `sources`. Optional: `metrics`.

```bash
dzcto artifact --project "<project folder>" --kind weekly-reviews --title "Weekly CTO Review" --data-file "<json report data file>"

# Fallback when dzcto is not on PATH:
python3 scripts/dzcto.py artifact --project "<project folder>" --kind weekly-reviews --title "Weekly CTO Review" --data-file "<json report data file>"
```

The helper owns the HTML template; the agent owns the judgment and structured content. Keep the chat response brief; the HTML file is the durable record.

## Standards

- Do not manufacture metrics. Say when evidence is missing.
- Prefer fewer sharper risks over a long risk catalog.
- Distinguish delivery slippage, product uncertainty, technical risk, and people/process risk.
- Preserve or update `core/RISKS.md` and `core/DECISIONS.md` only in the project knowledge wiki, and only when the user asks for durable follow-through.
- Do not write Day Zero CTO reports into code repos by default.

---
name: write-ceo-update
description: "Write CEO-facing engineering updates for an early-stage startup and create a durable HTML CEO update in the project knowledge wiki. Use when the user asks for a CEO report, founder update, executive recap, weekly update, board-input draft, investor-friendly engineering summary, or help translating engineering work, risks, and decisions into business-facing language."
---

# Write CEO Update

Translate engineering reality into concise business signal for the CEO or founding team.

## Workflow

1. Identify the audience and time window. If unspecified, assume a weekly CEO update.
2. Resolve the project folder. If unknown, ask for it and recommend `~/Documents/<Company>/`. Durable outputs live under `<project>/knowledge/wiki/`.
3. Resolve an optional code repo pointer separately. Treat the code repo as read-only evidence unless the user explicitly asks for code changes.
4. Load relevant context: `core/STRATEGY.md`, recent `reports/weekly-reviews/` files, `core/RISKS.md`, `core/DECISIONS.md`, planning docs, incidents, recent commits, and user notes.
5. Extract only the information that changes business judgment: progress, blocked outcomes, customer impact, risk, asks, and upcoming decisions.
6. Draft the update in the requested tone. If no tone is specified, use direct, calm, non-defensive language.
7. Flag unsupported claims and missing evidence instead of smoothing over them.
8. Write the canonical update as an HTML artifact under `<project>/knowledge/wiki/reports/ceo-updates/` and regenerate `<project>/knowledge/wiki/index.html`.
9. Summarize the update in chat and link to the generated artifact.

## Default Structure

- `Headline`: the most important engineering truth this week.
- `Progress`: what moved and why it matters.
- `Risks / blockers`: what could affect revenue, customers, trust, runway, or delivery.
- `Asks / decisions`: what the CEO or founders need to decide or unblock.
- `Next`: what engineering is focusing on next.

## Durable Artifact

Write structured JSON report data, then use the helper from this plugin. Prefer the wrapper when it is on `PATH`; otherwise run the Python script from the plugin repo:

Required JSON fields: `headline`, `progress`, `risks_blockers`, `asks_decisions`, `next`, and `sources`. Optional: `metrics`.

```bash
dzcto-artifact --project "<project folder>" --kind ceo-updates --title "CEO Engineering Update" --data-file "<json report data file>"

# Fallback when dzcto-artifact is not on PATH:
python3 scripts/dzcto_artifact.py --project "<project folder>" --kind ceo-updates --title "CEO Engineering Update" --data-file "<json report data file>"
```

The helper owns the HTML template; the agent owns the judgment and structured content. Keep the chat response brief; the HTML file is the durable record.

## Standards

- Avoid technical detail unless it changes a business decision.
- Do not oversell progress or hide uncertainty.
- Make asks explicit.
- Preserve nuance when the news is mixed: confidence, caveats, and tradeoffs belong in the update.
- Do not write CEO updates into the code repo by default.

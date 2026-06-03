---
name: write-ceo-update
description: "Write CEO-facing engineering updates for an early-stage startup. Use when the user asks for a CEO report, founder update, executive recap, weekly update, board-input draft, investor-friendly engineering summary, or help translating engineering work, risks, and decisions into business-facing language."
---

# Write CEO Update

Translate engineering reality into concise business signal for the CEO or founding team.

## Workflow

1. Identify the audience and time window. If unspecified, assume a weekly CEO update.
2. Load relevant context: `STRATEGY.md`, recent `reports/cto-weekly/` files, `RISKS.md`, `DECISIONS.md`, planning docs, incidents, recent commits, and user notes.
3. Extract only the information that changes business judgment: progress, blocked outcomes, customer impact, risk, asks, and upcoming decisions.
4. Draft the update in the requested tone. If no tone is specified, use direct, calm, non-defensive language.
5. Flag unsupported claims and missing evidence instead of smoothing over them.

## Default Structure

- `Headline`: the most important engineering truth this week.
- `Progress`: what moved and why it matters.
- `Risks / blockers`: what could affect revenue, customers, trust, runway, or delivery.
- `Asks / decisions`: what the CEO or founders need to decide or unblock.
- `Next`: what engineering is focusing on next.

## Standards

- Avoid technical detail unless it changes a business decision.
- Do not oversell progress or hide uncertainty.
- Make asks explicit.
- Preserve nuance when the news is mixed: confidence, caveats, and tradeoffs belong in the update.

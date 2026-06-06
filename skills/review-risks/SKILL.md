---
name: review-risks
description: "Review the Day Zero CTO risk register by walking the user through active risks whose next review is due, severity is high, mitigation is unclear, or the user selected them. Use when the user asks to review risks, resolve the risk register, close a risk, update risk severity, punt risk review to a later date, mark missing evidence, or work through RISKS.md one row at a time."
---

# Review Risks

Run a risk-register review ritual over `RISKS.md`. This is different from `review-engineering-risk`: that skill creates a fresh risk assessment report; this skill maintains the canonical risk register.

## Workflow

1. Resolve the Day Zero CTO project folder. Read `<project>/knowledge/wiki/core/RISKS.md`, plus `STRATEGY.md`, `DECISIONS.md`, recent relevant reports, and read-only repo evidence only as needed.
2. Build the review queue from risks whose next review appears due, stale, unclear, high/critical, blocked, missing mitigation, missing owner, or selected by the user. If the user says "all risks", walk every row.
3. For each queued risk, show a compact brief:
   - Risk and current severity or likelihood.
   - Evidence.
   - Business impact.
   - Owner.
   - Current mitigation.
   - Next review date or trigger.
4. Ask the user for one outcome at a time:
   - `Keep active`: risk still stands; update next review if needed.
   - `Update`: change severity, evidence, impact, owner, mitigation, or review trigger.
   - `Close`: risk is no longer material; capture why.
   - `Punt`: no update now; set a later date, event, owner, or evidence trigger.
   - `Needs evidence`: name the missing evidence and owner before deciding.
5. Draft the exact Markdown update and ask for approval before writing unless the user explicitly asked you to apply changes directly.
6. Preserve risk history. Do not erase useful evidence or mitigation notes just because the risk changes state.
7. Update `<project>/knowledge/wiki/core/RISKS.md`:
   - Keep the main table as the active risk register when possible.
   - Update severity, owner, mitigation, and next review from the approved outcome.
   - Move closed risks to a `## Closed Risks` table when useful, with `Closed Date`, `Risk`, `Reason`, and `Prior Mitigation`.
   - Add or update a `## Review History` table when useful, with `Review Date`, `Risk`, `Outcome`, `Notes`, and `Next Review`.
8. When the review surfaces a major new risk or material change, optionally create a durable engineering-risk report with:

   ```bash
   dzcto artifact --project "<project folder>" --kind engineering-risk --title "<risk review title>" --data-file "<json report data file>"
   ```

9. Regenerate the wiki:

   ```bash
   dzcto refresh "<project folder>"
   ```

10. Summarize active, updated, closed, punted, and evidence-needed risks, plus next review dates or triggers.

## Standards

- Treat risks as operating objects, not prose. Every active risk needs an owner, mitigation, and next review date or trigger when possible.
- Favor a clear punt over fake certainty: punt only with a date, event, owner, or evidence trigger.
- Use evidence labels when a risk is based on code, docs, reports, incidents, customer feedback, compliance requirements, or user judgment.
- Close risks only when the user agrees they are no longer material or have been absorbed into normal operations.
- Keep the loop calm and sequential; do not ask the user to review a large table all at once.

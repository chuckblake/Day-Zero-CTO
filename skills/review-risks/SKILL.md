---
name: review-risks
description: "Review the Day Zero CTO risk register by walking the user through active risks whose next review is due, severity is high, mitigation is unclear, or the user selected them, and log formal decisions made while addressing those risks. Use when the user asks to review risks, resolve the risk register, close a risk, update risk severity, choose or accept a mitigation, punt risk review to a later date, mark missing evidence, log decisions from risk review, or work through RISKS.md one row at a time."
---

# Review Risks

Run a risk-register review ritual over `RISKS.md`. This is different from `review-engineering-risk`: that skill creates a fresh risk assessment report; this skill maintains the canonical risk register.

## Workflow

1. Resolve the Day Zero CTO project folder. Read `<project>/knowledge/wiki/core/RISKS.md`, `<project>/knowledge/wiki/core/DECISIONS.md`, plus `STRATEGY.md`, recent relevant reports, and read-only repo evidence only as needed.
2. Build the review queue from risks whose next review appears due, stale, unclear, high/critical, blocked, missing mitigation, missing owner, or selected by the user. If the user says "all risks", walk every row.
3. For each queued risk, show a compact brief:
   - Risk and current severity or likelihood.
   - Evidence.
   - Business impact.
   - Owner.
   - Current mitigation.
   - Source.
   - Next review date, plus any external trigger.
4. Ask the user for one outcome at a time:
   - `Keep active`: risk still stands; update next review if needed.
   - `Update`: change severity, evidence, impact, owner, mitigation, or review trigger.
   - `Close`: risk is no longer material; capture why.
   - `Punt`: no update now; set a later calendar date, plus any event, owner, or evidence trigger.
   - `Needs evidence`: name the missing evidence and owner before deciding.
5. When the outcome includes a formal choice, also draft a `DECISIONS.md` update. Examples that count as decisions:
   - Accepting a risk for now.
   - Choosing one mitigation path over another.
   - Changing architecture, vendor, security posture, process, staffing, or launch scope because of the risk.
   - Closing a risk because a policy or product direction changed.
   - Deferring a risk review based on an explicit operating principle, threshold, or external trigger.
6. Draft the exact Markdown updates for both `RISKS.md` and, when needed, `DECISIONS.md`; ask for approval before writing unless the user explicitly asked you to apply changes directly.
7. Preserve risk and decision history. Do not erase useful evidence, mitigation notes, or original decision rationale just because the risk changes state.
8. Update `<project>/knowledge/wiki/core/RISKS.md`:
   - Keep the main table as the active risk register when possible.
   - Update severity, owner, source, mitigation, and next review from the approved outcome.
   - Ensure every active risk has a calendar date in `Next Review`. External triggers are allowed, but only as an addition, such as `2026-07-06 or on receipt of legal opinion`.
   - Move closed risks to a `## Closed Risks` table when useful, with `Closed Date`, `Risk`, `Reason`, and `Prior Mitigation`.
   - Add or update a `## Review History` table when useful, with `Review Date`, `Risk`, `Outcome`, `Notes`, and `Next Review`.
9. Update `<project>/knowledge/wiki/core/DECISIONS.md` for risk-review decisions:
   - Add a decision row with date, decision, risk context, options considered, past-tense rationale, owner, and revisit trigger.
   - If an existing decision already covers the choice, preserve the original decision and add or update review history/revisit trigger instead of duplicating it.
   - Reference the related risk title in context or rationale so future reviews can trace the connection.
10. When the review surfaces a major new risk or material change, optionally create a durable engineering-risk report with:

   ```bash
   dzcto artifact --project "<project folder>" --kind engineering-risk --title "<risk review title>" --data-file "<json report data file>"
   ```

11. Regenerate the wiki:

   ```bash
   dzcto refresh "<project folder>"
   ```

12. After refresh, the generated Risks page should show the updated Current Read summary, the active source log, and any report-derived `Risk Signals From Reports`. Summarize active, updated, closed, punted, and evidence-needed risks, decisions logged or updated, plus next review dates and any external triggers.

## Standards

- Treat risks as operating objects, not prose. Every active risk needs an owner, source, mitigation, and a calendar next review date.
- Use `core/risks.html#risk-signals` as an intake view for report-derived risk candidates, but manage real operating risks in `RISKS.md`.
- Do not hand-edit generated Current Read summaries; they regenerate from `RISKS.md` and structured report risk signals on refresh.
- External triggers are useful context, but they do not replace a calendar review date because Day Zero CTO cannot observe most external events by itself.
- Favor a clear punt over fake certainty: punt only with a date, and optionally an event, owner, or evidence trigger.
- Use evidence labels when a risk is based on code, docs, reports, incidents, customer feedback, compliance requirements, or user judgment.
- Log decisions separately from risks. Risk rows track exposure and operating follow-up; `DECISIONS.md` tracks choices made while addressing those risks.
- Close risks only when the user agrees they are no longer material or have been absorbed into normal operations.
- Keep the loop calm and sequential; do not ask the user to review a large table all at once.

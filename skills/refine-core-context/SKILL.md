---
name: refine-core-context
description: "Refine, review, complete, or update Day Zero CTO core context after onboarding through a guided interview and approval loop. Use when the user wants to improve or correct STRATEGY.md, TEAM.md, OPERATING_CADENCE.md, DECISIONS.md, RISKS.md, the dashboard description, cadence rules, the risk register, the decision log, team context, operating rituals, or asks how to keep core wiki documents accurate without manually editing generated HTML."
---

# Refine Core Context

Update the project wiki's core CTO context by interviewing the user, drafting concrete Markdown changes, getting approval, and regenerating the HTML wiki.

## Workflow

1. Resolve the Day Zero CTO project folder. If the user did not provide it, look for `.dzcto/config.json` under likely `knowledge/wiki/` folders or ask one concise question. Treat configured code repos as read-only evidence.
2. Choose the target core document. If the user names one, use it. Otherwise ask which area to refine: Strategy, Team, Operating Cadence, Decisions, or Risks.
3. Read the current source file under `<project>/knowledge/wiki/core/`, related core files, `.dzcto/config.json`, and only the report or code evidence needed for the topic.
4. Run a focused interview one topic at a time. Do not send a giant intake form. Prefer 2-4 questions per pass, using what is already known to avoid asking for facts that are in the wiki.
5. For each section you can improve, draft the proposed Markdown or table rows and ask the user to approve, revise, or skip before writing. If the user explicitly asks you to apply changes without approval, proceed and summarize assumptions.
6. Write only the editable source Markdown under `<project>/knowledge/wiki/core/`. Preserve useful existing notes, mark uncertain material as `Unknown` or `Assumption:`, and avoid erasing history unless the user approves the replacement.
7. Regenerate the wiki:

   ```bash
   dzcto refresh "<project folder>"

   # Fallback when dzcto is not on PATH:
   python3 scripts/dzcto.py refresh "<project folder>"
   ```

8. Summarize changed sections, remaining unknowns, and the generated HTML page to review.

## Interview Guides

- `STRATEGY.md`: company stage, target customer and user, product thesis, current goals, constraints, non-goals, and the first real description paragraph used by the dashboard.
- `TEAM.md`: people, roles, ownership, decision rights, communication preferences, working agreements, gaps, and open questions.
- `OPERATING_CADENCE.md`: weekly review rhythm, CEO update rhythm, planning cycle, incident or reliability review rhythm, expected artifacts, and `## Index Cadence Rules` rows for dashboard due alerts.
- `DECISIONS.md`: recorded decisions already taken, original or approximate decision date, context, options considered, past-tense rationale, owner, revisit trigger, and optional review history.
- `RISKS.md`: risk, evidence, impact, likelihood or severity, owner, mitigation, next review date, and whether the risk should appear as high priority on the dashboard.

## Update Standards

- For substantive updates, prefer the interview-and-approval loop over direct file edits.
- For small typo or formatting fixes, direct edits to source Markdown are fine. Never edit generated `index.html` or `core/*.html` as the source of truth.
- Prefer compact Markdown tables for decision logs, risk registers, and cadence rules.
- Keep people context work-relevant and factual. Do not speculate about motives, health, or private personal matters.
- Use evidence labels or file references when a claim comes from docs, code, Git history, or a generated report.
- If a section is not ready, leave a clear question or `Unknown` rather than inventing an answer.

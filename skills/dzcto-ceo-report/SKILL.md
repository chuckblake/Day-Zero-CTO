---
name: dzcto-ceo-report
description: "Generate a simplified Day Zero CTO CEO report for an explicit date range."
---

# DZ CTO CEO Report

Create a CEO report for a user-selected date range.

## Workflow

1. Resolve the artifact/report folder. Look for `.dzcto/config.json` in the provided folder, or ask one concise question if no folder is known.
2. Ask for the report date range when the user did not provide it. Use concrete `YYYY-MM-DD` start and end dates.
3. Read `.dzcto/config.json` and use `ceoReportTone` when present. If no tone is configured, use direct, concise, business-facing language.
4. Gather evidence for only the requested range:
   - User notes in the conversation.
   - Existing report JSON/HTML under the artifact folder.
   - Optional read-only code repos from `codeRepos`; use non-mutating Git commands only.
5. Write a CEO-facing report focused on progress, business impact, risks or blockers, asks or decisions, and next focus.
6. Save structured JSON with these fields: `window`, `headline`, `progress`, `risks_blockers`, `asks_decisions`, `next`, `sources`, and optional `metrics`.
7. Render the artifact:

```bash
dzcto artifact \
  --artifacts-dir "<artifact/report folder>" \
  --kind ceo-updates \
  --title "CEO Report <start> to <end>" \
  --date "<end>" \
  --data-file "<json report data file>"
```

If `dzcto` is not on `PATH`, use:

```bash
python3 scripts/dzcto.py artifact \
  --artifacts-dir "<artifact/report folder>" \
  --kind ceo-updates \
  --title "CEO Report <start> to <end>" \
  --date "<end>" \
  --data-file "<json report data file>"
```

## Standards

- Keep technical detail subordinate to CEO judgment.
- Preserve nuance when news is mixed.
- Flag unsupported claims instead of smoothing them over.
- End with the generated report path and a brief summary.

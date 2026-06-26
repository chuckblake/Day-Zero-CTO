---
name: dzcto-ceo-report-weekly
description: "Generate the simplified Day Zero CTO weekly CEO report using the weekly defaults captured by dzcto-init."
---

# DZ CTO CEO Report Weekly

Create the CEO report for the configured weekly window.

## Workflow

1. Resolve the artifact/report folder. Look for `.dzcto/config.json` in the provided folder, or ask one concise question if no folder is known.
2. Read `.dzcto/config.json`. Use `weeklyReportDefaults` for the date window and `ceoReportTone` for the report voice.
3. If weekly defaults are missing, ask for the start and end dates or run `/dzcto-init` first.
4. Gather evidence for only the selected week:
   - User notes in the conversation.
   - Existing report JSON/HTML under the artifact folder.
   - Optional read-only code repos from `codeRepos`; use non-mutating Git commands only.
5. Write a CEO-facing report. Keep it business-facing: progress, impact, risk, asks, and what happens next. Do not include implementation detail unless it changes a CEO decision.
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

- Be direct, concise, and calm about uncertainty.
- Make asks and decisions explicit.
- Separate known facts from judgment.
- Do not write reports into a code repo unless the user explicitly chose that folder during init.
- End with the generated report path and a brief summary.

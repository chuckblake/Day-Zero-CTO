---
name: dzcto-ceo-report
description: "Generate a simplified Day Zero CTO CEO report for an explicit date range."
---

# DZ CTO CEO Report

Create a CEO report for a user-selected date range, following the canonical template in
`docs/ceo-report-template.md` (repo reference — the schema section below is self-contained,
so this skill works even where `docs/` is not installed).

## Workflow

1. Resolve the profile and artifact/report folder. First read `~/.dzcto/config.json`; if the user named a profile, use `profiles.<name>.artifactsDir`, otherwise use `defaultProfile`. If the user provided a folder, prefer that. If no folder is known, ask one concise question.
2. Ask for the report date range when the user did not provide it. Use concrete `YYYY-MM-DD` start and end dates.
3. Read `<artifact folder>/.dzcto/config.json` and use `ceoReportTone` when present. Fall back to the selected global profile. If no tone is configured, use direct, concise, business-facing language.
4. Gather evidence for only the requested range:
   - User notes in the conversation.
   - Existing report JSON/HTML under the artifact folder.
   - Optional read-only code repos from `codeRepos`; use non-mutating Git commands only.
   - Bad-news signals: check the available evidence within the requested range for reverts or reverted commits, failing or red CI, and slipped or descoped work.
5. Read the most recent prior report JSON in the report folder (when one exists) for narrative continuity. Carry still-true items forward verbatim — stable wording keeps the automatic week-over-week diff readable — and express continuity in the `headline` prose.
6. Write a CEO-facing report focused on progress, business impact, risks or blockers, asks or decisions, and next focus. If the requested range contains bad news, state it plainly in `headline`, `progress.status`, or `risks_blockers`; do not soften reversals, red CI, slipped work, or descopes. Save structured JSON per the schema below, with `report_type` set to `"ad_hoc"`.
7. Render the artifact (the report date is derived from `window.end`; do not pass `--date`):

```bash
dzcto artifact \
  --profile "<profile-name>" \
  --artifacts-dir "<artifact/report folder>" \
  --kind ceo-updates \
  --title "CEO Report <start> to <end>" \
  --data-file "<json report data file>"
```

If `dzcto` is not on `PATH`, use:

```bash
python3 scripts/dzcto.py artifact \
  --profile "<profile-name>" \
  --artifacts-dir "<artifact/report folder>" \
  --kind ceo-updates \
  --title "CEO Report <start> to <end>" \
  --data-file "<json report data file>"
```

## Report JSON schema (v1)

<!-- Keep this section byte-identical in dzcto-ceo-report/SKILL.md and
dzcto-ceo-report-weekly/SKILL.md; a unit test enforces the lockstep.
Canon: docs/ceo-report-template.md. -->

Save structured JSON with these fields:

- `report_type`: `"weekly"` for the weekly skill, `"ad_hoc"` for the date-range skill.
- `company`: company or product name.
- `window`: `{"start": "YYYY-MM-DD", "end": "YYYY-MM-DD"}` — ISO dates only, no label text.
- `headline`: one sentence — the most important engineering truth for the CEO.
- `progress`: array of `{"area", "status", "summary", "items": []}` objects.
- `risks_blockers`: array of `{"risk", "detail", "severity"}` objects.
- `asks_decisions`: array of `{"ask", "context", "owner"}` objects.
- `next`: array of strings.
- `metrics` (optional): flat object of `"label": scalar`; numeric values in consecutive reports render week-over-week deltas.
- `sources`: array of strings — the evidence used.

Do not author `schema_version`, `generated_at`, or `prior_report` — the renderer stamps them. The renderer also computes the week-over-week section from the prior report; never write that section yourself.

## Standards

- Keep technical detail subordinate to CEO judgment.
- Preserve nuance when news is mixed.
- Flag unsupported claims instead of smoothing them over.
- Surface bad news plainly rather than softening it.
- Use ISO `YYYY-MM-DD` dates in the title and `window`.
- Do not run or offer non-CEO Day Zero CTO workflows.
- End with the generated report path and a brief summary.

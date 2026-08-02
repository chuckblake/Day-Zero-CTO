---
name: dzcto-ceo-report-weekly
description: "Generate the simplified Day Zero CTO weekly CEO report using the weekly defaults captured by dzcto-init."
---

# DZ CTO CEO Report Weekly

Create the CEO report for the configured weekly window, following the canonical template in
`docs/ceo-report-template.md` (repo reference — the schema section below is self-contained,
so this skill works even where `docs/` is not installed).

## Workflow

1. Resolve the profile and artifact/report folder. First read `~/.dzcto/config.json`; if the user named a profile, use `profiles.<name>.artifactsDir`, otherwise use `defaultProfile`. If the user provided a folder, prefer that. If no folder is known, ask one concise question.
2. Resolve the reporting window before interpreting weekly defaults or collecting evidence. Run `dzcto window` first:

```bash
dzcto window \
  --profile "<profile-name>" \
  --artifacts-dir "<artifact/report folder>"
```

If `dzcto` is not on `PATH`, use:

```bash
python3 scripts/dzcto.py window \
  --profile "<profile-name>" \
  --artifacts-dir "<artifact/report folder>"
```

The command accepts an optional `--as-of "<YYYY-MM-DD>"` when the run date must be pinned and prints one JSON object.
3. Read `<artifact folder>/.dzcto/config.json` for `ceoReportTone`, falling back to the selected global profile, then branch on the window JSON:
   - For `mode: "since_last_report"` with `empty: false`, use its `start` and `end` verbatim. Do not reinterpret or recompute the dates.
   - For `empty: true`, report honestly that the range is already covered through `cursor.window_end` and do not call `dzcto evidence`; its `start` is after its `end`, which the evidence command rejects.
   - For `mode: "fallback"` or `mode: "day_based"`, use the existing day-based path unchanged: use `weeklyReportDefaults` for the date window, falling back to matching values in the selected global profile. If the required weekly defaults are missing, ask for the start and end dates or run `/dzcto-init` first.
4. Gather evidence for only the selected, non-empty week:
   - Run `dzcto evidence` for the exact window first. Treat its JSON as the primary grounding source, and carry its `sources` entries into the report `sources` array for every claim based on Git activity.
   - User notes in the conversation.
   - Existing report JSON/HTML under the artifact folder.
   - Low-activity signals: note when the week has few or no commits, PRs, or merges.
   - Bad-news signals: check the available evidence within the selected week for reverts or reverted commits, failing or red CI, and slipped or descoped work.

Collect the primary Git evidence with:

```bash
dzcto evidence \
  --profile "<profile-name>" \
  --artifacts-dir "<artifact/report folder>" \
  --start "<start>" \
  --end "<end>" \
  --output-json "<evidence snapshot path>" \
  --json
```

If `dzcto` is not on `PATH`, use:

```bash
python3 scripts/dzcto.py evidence \
  --profile "<profile-name>" \
  --artifacts-dir "<artifact/report folder>" \
  --start "<start>" \
  --end "<end>" \
  --output-json "<evidence snapshot path>" \
  --json
```

Pass the resolver's `start` and `end` verbatim for `mode: "since_last_report"` with `empty: false`. For `empty: true`, do not call `dzcto evidence`; tell the user the range is already covered through the cursor date instead.

If the collector reports no configured repositories, continue with the secondary evidence sources instead of treating that as an error.
5. Read the most recent prior report JSON in the report folder (when one exists) for narrative continuity. Carry still-true risks, asks, and next items forward verbatim — stable wording keeps the automatic week-over-week diff readable — and express continuity in the `headline` prose.
6. Write a CEO-facing report. Keep it business-facing: progress, impact, risk, asks, and what happens next. If the selected week is a quiet week, state that plainly in `headline`; never pad by manufacturing progress, inflating minor work, or restating old wins as new. Keep `metrics` with explicit zero values such as `prs_merged: 0` instead of dropping the key, and leave genuinely empty sections empty because the renderer labels them. If the selected week contains bad news, state it plainly in `headline`, `progress.status`, or `risks_blockers`; do not soften reversals, red CI, slipped work, or descopes. Do not include implementation detail unless it changes a CEO decision. Save structured JSON per the schema below, with `report_type` set to `"weekly"`.
7. Render the artifact (the report date is derived from `window.end`; do not pass `--date`). Pass the saved evidence snapshot with `--evidence-file` so the renderer can record whether the window had real work:

```bash
dzcto artifact \
  --profile "<profile-name>" \
  --artifacts-dir "<artifact/report folder>" \
  --kind ceo-updates \
  --title "CEO Report <start> to <end>" \
  --data-file "<json report data file>" \
  --evidence-file "<evidence snapshot path>" \
  --open
```

If `dzcto` is not on `PATH`, use:

```bash
python3 scripts/dzcto.py artifact \
  --profile "<profile-name>" \
  --artifacts-dir "<artifact/report folder>" \
  --kind ceo-updates \
  --title "CEO Report <start> to <end>" \
  --data-file "<json report data file>" \
  --evidence-file "<evidence snapshot path>" \
  --open
```

8. Relay the generated report path, that the helper opened it in the default browser, and the printed share recipe (`Cmd/Ctrl+P` → `Save as PDF`). Browser opening is best-effort; if it fails, still provide the path and recipe.

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

Do not author `schema_version`, `generated_at`, `prior_report`, `test_run`, or `work_evidence` — the renderer stamps them. The renderer also computes the week-over-week section from the prior report; never write that section yourself.

## Standards

- Be direct, concise, and calm about uncertainty.
- Make asks and decisions explicit.
- Separate known facts from judgment.
- Surface bad news plainly rather than softening it.
- Prefer an honest quiet-week report over skipping the week.
- Use ISO `YYYY-MM-DD` dates in the title and `window`.
- Do not write reports into a code repo unless the user explicitly chose that folder during init.
- Do not run or offer non-CEO Day Zero CTO workflows.
- End by relaying the generated report path, browser-open result, and printed share recipe.

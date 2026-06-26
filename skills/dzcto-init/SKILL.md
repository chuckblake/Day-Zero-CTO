---
name: dzcto-init
description: "Initialize the simplified Day Zero CTO CEO-report workspace: choose artifact/report location, weekly date defaults, CEO report tone, and create the report index."
---

# DZ CTO Init

Set up the small Day Zero CTO surface for CEO reports only. Do not run or offer Tech Stack, risk review, snapshot, learning, decision review, or any other Day Zero CTO workflow.

## Workflow

1. Resolve the artifact/report location. If the user has not given one, ask where reports should live. Prefer a durable folder outside the code repo. The helper creates an `index.html`, `reports/ceo-updates/`, and `.dzcto/config.json` in that location.
2. Resolve the company, CTO, or project profile name. If the user does not provide one, derive a short slug from the company/project, such as `getmusic`. This profile is how one global install supports multiple repos or CTO contexts.
3. Ask what weekly reporting window they want. Do not silently choose Monday-Sunday. Capture a concrete schedule such as `Fri-Thu`, `Mon-Sun`, `previous completed week ending Thursday`, or `rolling last 7 days`.
4. Convert that answer into helper flags:
   - `Fri-Thu` means `--weekly-range "previous_completed_week" --weekly-start-day "Friday" --weekly-end-day "Thursday"`.
   - `Mon-Sun` means `--weekly-range "previous_completed_week" --weekly-start-day "Monday" --weekly-end-day "Sunday"`.
   - `rolling last 7 days` means `--weekly-range "last_7_days" --weekly-lookback-days 7`.
5. Resolve the CEO report tone. Offer a short default such as `direct, concise, business-facing, calm about risk, explicit about asks`. Capture any user-specific language preference.
6. Optionally capture read-only code repo paths if the user wants report evidence from Git history or code. Treat these as evidence sources only.
7. Run the helper:

```bash
dzcto init \
  --artifacts-dir "<artifact/report folder>" \
  --profile "<profile-name>" \
  --company-name "<company name>" \
  --weekly-range "previous_completed_week" \
  --weekly-start-day "Monday" \
  --weekly-end-day "Sunday" \
  --ceo-report-tone "<tone guidance>"
```

If `dzcto` is not on `PATH`, run the plugin helper from the repo:

```bash
python3 scripts/dzcto.py init \
  --artifacts-dir "<artifact/report folder>" \
  --profile "<profile-name>" \
  --company-name "<company name>" \
  --weekly-range "previous_completed_week" \
  --weekly-start-day "Monday" \
  --weekly-end-day "Sunday" \
  --ceo-report-tone "<tone guidance>"
```

Add repeatable `--repo "<path>"` flags when read-only code repos should be saved as evidence sources.

The helper also saves these preferences to `~/.dzcto/config.json` under `profiles.<profile-name>`, including the artifact directory, weekly defaults, tone, and optional repos. It also updates `defaultProfile` unless `--no-switch-default` is used, so `/dzcto-ceo-report-weekly` and `/dzcto-ceo-report` can work from other repos later.

## Result

Confirm only the created index path, the profile name, the global preferences path, the stored weekly range defaults, the stored tone guidance, and the next command to run:

- `/dzcto-ceo-report-weekly` for the default weekly report.
- `/dzcto-ceo-report` for a custom date range.

Keep the response short and practical. Do not ask whether to run any other setup/report workflow.

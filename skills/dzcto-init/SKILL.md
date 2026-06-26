---
name: dzcto-init
description: "Initialize the simplified Day Zero CTO CEO-report workspace: choose artifact/report location, weekly date defaults, CEO report tone, and create the report index."
---

# DZ CTO Init

Set up the small Day Zero CTO surface for CEO reports only.

## Workflow

1. Resolve the artifact/report location. If the user has not given one, ask where reports should live. Prefer a durable folder outside the code repo. The helper creates an `index.html`, `reports/ceo-updates/`, and `.dzcto/config.json` in that location.
2. Resolve the company or project name if it is not obvious from the folder or conversation.
3. Resolve the default weekly report range. If the user has no preference, use `previous_completed_week`, with Monday as the week start and Sunday as the week end.
4. Resolve the CEO report tone. Offer a short default such as `direct, concise, business-facing, calm about risk, explicit about asks`. Capture any user-specific language preference.
5. Optionally capture read-only code repo paths if the user wants report evidence from Git history or code. Treat these as evidence sources only.
6. Run the helper:

```bash
dzcto init \
  --artifacts-dir "<artifact/report folder>" \
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
  --company-name "<company name>" \
  --weekly-range "previous_completed_week" \
  --weekly-start-day "Monday" \
  --weekly-end-day "Sunday" \
  --ceo-report-tone "<tone guidance>"
```

Add repeatable `--repo "<path>"` flags when read-only code repos should be saved as evidence sources.

## Result

Confirm the created index path, the stored weekly range defaults, the stored tone guidance, and the next command to run:

- `/dzcto-ceo-report-weekly` for the default weekly report.
- `/dzcto-ceo-report` for a custom date range.

Keep the response short and practical.

# Day Zero CTO

Day Zero CTO is intentionally small again: set up a place for reports, then generate CEO-facing engineering updates.

The active command surface is:

| Command | Purpose |
| --- | --- |
| `/dzcto-init` | Choose where artifacts/reports live, capture company context, set weekly report defaults, set CEO report tone, and create the report index. |
| `/dzcto-ceo-report-weekly` | Generate a CEO report using the weekly defaults from init. |
| `/dzcto-ceo-report` | Generate a CEO report for a date range the user provides. |

Everything else is legacy reference material for now. The old broad CTO workflows have been moved out of the active `skills/` folder.

## What Init Captures

`/dzcto-init` should collect:

- The artifact/report folder. This folder directly contains `index.html`, `reports/ceo-updates/`, and `.dzcto/config.json`.
- A profile name, such as `getmusic`, for the company/CTO context. This is how one DZ CTO install supports multiple repos or multiple CTO clients.
- A company name and one-sentence company context summary for the report index and CEO report prompts.
- Weekly report defaults. Init should ask for the schedule explicitly, such as `Fri-Thu`, `Mon-Sun`, or `rolling last 7 days`; it should not silently choose a default.
- CEO report tone guidance.
- Optional read-only code repo paths for evidence.

Init also writes one sample CEO report into a workspace that has no report yet, so you can open real generated output right after setup instead of wiring evidence first. It is labelled as an example in the page and is excluded from report counts, the weekly streak, prior-report comparison, and the since-last-report window, so it is never mistaken for or counted as real repo evidence. Pass `--no-sample-report` to skip it.

The equivalent helper command is:

```bash
dzcto init \
  --artifacts-dir "$HOME/Documents/Acme CEO Reports" \
  --profile "acme" \
  --company-name "Acme" \
  --company-description "Acme helps operators coordinate field service teams." \
  --weekly-range "previous_completed_week" \
  --weekly-start-day "Friday" \
  --weekly-end-day "Thursday" \
  --ceo-report-tone "Direct, concise, business-facing, calm about risk, explicit about asks."
```

For a Monday-through-Sunday reporting week:

```bash
dzcto init \
  --artifacts-dir "$HOME/Documents/Acme CEO Reports" \
  --profile "acme" \
  --company-name "Acme" \
  --company-description "Acme helps operators coordinate field service teams." \
  --weekly-range "previous_completed_week" \
  --weekly-start-day "Monday" \
  --weekly-end-day "Sunday" \
  --ceo-report-tone "Direct, concise, business-facing, calm about risk, explicit about asks."
```

The helper creates an index at:

```text
<artifacts-dir>/index.html
```

When run against an existing artifact folder, `dzcto init` refreshes the index and re-renders
existing structured CEO report HTML from sibling `.json` files so reports pick up the current
format. It does not rewrite the report JSON. Legacy body-only HTML without JSON is left as-is.

It also saves preferences to:

```text
~/.dzcto/config.json
```

That global config stores named profiles so the same skill can be used from any code repo:

```json
{
  "defaultProfile": "getmusic",
  "profiles": {
    "getmusic": {
      "artifactsDir": "/Users/chuck/dzcto/GetMusic",
      "companyName": "GetMusic",
      "companyDescription": "GetMusic helps artists plan, release, and promote music.",
      "weeklyReportDefaults": {
        "range": "previous_completed_week",
        "startDay": "Friday",
        "endDay": "Thursday"
      },
      "ceoReportTone": "Direct, concise, business-facing.",
      "codeRepos": ["/Users/chuck/code/getmusic"]
    },
    "client-two": {
      "artifactsDir": "/Users/chuck/dzcto/Client Two"
    }
  }
}
```

`range` also accepts `since_last_report`, an alternative to the day-based windows above. It starts
the weekly window the day after the previous weekly report's `window.end` and runs through the run
date, so every calendar day lands in exactly one report and a skipped week self-heals into a longer
one. It needs no `startDay` / `endDay`:

```json
"weeklyReportDefaults": { "range": "since_last_report" }
```

When no `--profile` is provided, report commands use `defaultProfile`. Use `--profile getmusic` to select a profile explicitly.

## CEO Reports

CEO reports are stored as durable HTML plus structured JSON under:

```text
<artifacts-dir>/reports/ceo-updates/
```

All reports follow the canonical template in [docs/ceo-report-template.md](docs/ceo-report-template.md),
including a week-over-week section that diffs against the prior report automatically.
Agents should write structured JSON (schema v1) with these fields:

| Field | Meaning |
| --- | --- |
| `schema_version` | `"ceo-report/1"`. Stamped by the renderer when absent. |
| `report_type` | `"weekly"` or `"ad_hoc"`. Drives week-over-week prior selection. |
| `company` | Company/product name. Filled from the profile when absent. |
| `window` | `{ "start": "YYYY-MM-DD", "end": "YYYY-MM-DD" }` — ISO dates for the report period. |
| `generated_at` | UTC ISO timestamp. Stamped by the renderer when absent. |
| `headline` | The most important engineering truth for the CEO. |
| `progress` | Array of `{ "area", "status", "summary", "items": [] }`. |
| `risks_blockers` | Array of `{ "risk", "detail", "severity" }`. |
| `asks_decisions` | Array of `{ "ask", "context", "owner" }`. |
| `next` | Array of strings — what engineering is focusing on next. |
| `metrics` | Optional flat `{ "label": scalar }` map; numeric values get week-over-week deltas. |
| `sources` | Notes, commits, reports, or files used as evidence. |
| `prior_report` | Written by the renderer — path of the report diffed against, or null. |

Render a report with (the report date is derived from `window.end`):

```bash
dzcto artifact \
  --artifacts-dir "$HOME/Documents/Acme CEO Reports" \
  --kind ceo-updates \
  --title "CEO Report 2026-06-15 to 2026-06-21" \
  --data-file "./ceo-report.json"
```

The index refreshes automatically after each report. To apply a newer report page format to
older structured reports, run `dzcto init --artifacts-dir "<artifacts-dir>" ...`; init re-renders
existing report HTML from the saved JSON.

Collect the configured repositories' read-only Git evidence for an exact report window with:

```bash
dzcto evidence \
  --profile "acme" \
  --start "2026-06-15" \
  --end "2026-06-21"
```

The command reads `codeRepos`, writes structured JSON under `<artifacts-dir>/.dzcto/generated/`, and is the primary Git grounding source for both CEO report skills.

## Config

Project config lives at:

```text
<artifacts-dir>/.dzcto/config.json
```

Useful keys:

| Key | Set via flag | Meaning |
| --- | --- | --- |
| `companyName` | `--company-name` | Company name shown on the report index. |
| `companyDescription` | `--company-description` | Short company summary. |
| `companyUrl` | `--company-url` | Company website URL kept as context. |
| `weeklyReportDefaults` | `--weekly-range`, `--weekly-start-day`, `--weekly-end-day`, `--weekly-lookback-days` | Defaults for `/dzcto-ceo-report-weekly`. Range values include `previous_completed_week`, `last_7_days`, and `since_last_report`; the latter starts the day after the previous weekly report's `window.end` and runs through the run date so every calendar day lands in exactly one report. |
| `ceoReportTone` | `--ceo-report-tone` | Tone guidance for CEO reports. |
| `reportPromptContext` | `--report-prompt-context` | Extra prompt steering appended to generated prompt cards. |
| `codeRepos` | `--repo` | Optional read-only evidence repos. |

## Install

Codex Desktop local install:

```bash
git clone https://github.com/chuckblake/Day-Zero-CTO.git
cd Day-Zero-CTO
bin/dzcto setup
```

Install a stable shell command:

```bash
bin/dzcto install-command
```

Update a local install:

```bash
bin/dzcto update
```

Validate:

```bash
bin/dzcto doctor
python3 -m py_compile scripts/*.py
```

## Helper Commands

The slash commands are the primary interface. The local helper still exists for deterministic file work:

| Command | Purpose |
| --- | --- |
| `dzcto init --artifacts-dir <dir> --profile <name> --company-description <summary>` | Create or refresh one CEO report workspace and save/update a global profile. |
| `dzcto artifact --profile <name> --kind ceo-updates --title <title> --data-file <json>` | Render a CEO report using a named global profile. If `--profile` is omitted, the helper uses `defaultProfile`. |
| `dzcto install-command` | Create `~/.local/bin/dzcto`. |
| `dzcto setup` | Install the local Codex plugin entry. |
| `dzcto update` | Pull/refresh a local install and run doctor. |
| `dzcto doctor` | Check helper and install health. |
| `dzcto version` | Print the installed helper version. |

## Repository Layout

```text
.codex-plugin/plugin.json
.claude-plugin/plugin.json
skills/
  dzcto-init/
  dzcto-ceo-report-weekly/
  dzcto-ceo-report/
scripts/
bin/
```

## Principles

- Start with CEO communication only.
- Keep reports outside the code repo unless the user explicitly chooses otherwise.
- Treat code repos as read-only evidence.
- Make asks and decisions explicit.
- Keep the generated index as a report index, not an operating system.

# Day Zero CTO

Day Zero CTO is intentionally small again: set up a place for reports, then generate CEO-facing engineering updates.

The active command surface is:

| Command | Purpose |
| --- | --- |
| `/dzcto-init` | Choose where artifacts/reports live, set weekly report defaults, set CEO report tone, and create the report index. |
| `/dzcto-ceo-report-weekly` | Generate a CEO report using the weekly defaults from init. |
| `/dzcto-ceo-report` | Generate a CEO report for a date range the user provides. |

Everything else is legacy reference material for now. The old broad CTO workflows have been moved out of the active `skills/` folder.

## What Init Captures

`/dzcto-init` should collect:

- The artifact/report folder. This folder directly contains `index.html`, `reports/ceo-updates/`, and `.dzcto/config.json`.
- Weekly report defaults. Init should ask for the schedule explicitly, such as `Fri-Thu`, `Mon-Sun`, or `rolling last 7 days`; it should not silently choose a default.
- CEO report tone guidance.
- Optional company metadata.
- Optional read-only code repo paths for evidence.

The equivalent helper command is:

```bash
dzcto init \
  --artifacts-dir "$HOME/Documents/Acme CEO Reports" \
  --company-name "Acme" \
  --weekly-range "previous_completed_week" \
  --weekly-start-day "Friday" \
  --weekly-end-day "Thursday" \
  --ceo-report-tone "Direct, concise, business-facing, calm about risk, explicit about asks."
```

For a Monday-through-Sunday reporting week:

```bash
dzcto init \
  --artifacts-dir "$HOME/Documents/Acme CEO Reports" \
  --company-name "Acme" \
  --weekly-range "previous_completed_week" \
  --weekly-start-day "Monday" \
  --weekly-end-day "Sunday" \
  --ceo-report-tone "Direct, concise, business-facing, calm about risk, explicit about asks."
```

The helper creates an index at:

```text
<artifacts-dir>/index.html
```

It also saves preferences to:

```text
~/.dzcto/config.json
```

That global config stores the default artifact directory, weekly schedule, CEO report tone, and optional evidence repos so the same skill can be used from any code repo.

## CEO Reports

CEO reports are stored as durable HTML plus structured JSON under:

```text
<artifacts-dir>/reports/ceo-updates/
```

Agents should write structured JSON with these fields:

| Field | Meaning |
| --- | --- |
| `window` | Start/end date and label for the report period. |
| `headline` | The most important engineering truth for the CEO. |
| `progress` | What moved and why it matters. |
| `risks_blockers` | Risks, blockers, or uncertainty that affects business judgment. |
| `asks_decisions` | Decisions or help needed from the CEO/founders. |
| `next` | What engineering is focusing on next. |
| `metrics` | Optional metric cards. |
| `sources` | Notes, commits, reports, or files used as evidence. |

Render a report with:

```bash
dzcto artifact \
  --artifacts-dir "$HOME/Documents/Acme CEO Reports" \
  --kind ceo-updates \
  --title "CEO Report 2026-06-15 to 2026-06-21" \
  --date "2026-06-21" \
  --data-file "./ceo-report.json"
```

The index refreshes automatically after each report.

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
| `weeklyReportDefaults` | `--weekly-range`, `--weekly-start-day`, `--weekly-end-day`, `--weekly-lookback-days` | Defaults for `/dzcto-ceo-report-weekly`. |
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
| `dzcto init --artifacts-dir <dir>` | Create or refresh the CEO report workspace. |
| `dzcto artifact --artifacts-dir <dir> --kind ceo-updates --title <title> --data-file <json>` | Render a CEO report and refresh the index. If `--artifacts-dir` is omitted, the helper uses `~/.dzcto/config.json`. |
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

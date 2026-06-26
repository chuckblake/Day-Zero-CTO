# Install Day Zero CTO For Agent Sessions

Day Zero CTO is currently a small CEO-report workflow. Install it when a user wants `/dzcto-init`, `/dzcto-ceo-report-weekly`, and `/dzcto-ceo-report`.

## Ask First

Before running `/dzcto-init`, gather:

- Artifact/report folder.
- Company or project name.
- Weekly report defaults: ask for the exact reporting week schedule, such as `Fri-Thu`, `Mon-Sun`, or `rolling last 7 days`. Do not silently choose a default.
- CEO report tone guidance.
- Optional company description or URL.
- Optional read-only code repo paths for evidence.

The artifact folder directly stores:

```text
index.html
reports/ceo-updates/
.dzcto/config.json
```

`dzcto init` also writes `~/.dzcto/config.json` with the default artifact folder, weekly schedule, CEO report tone, and optional evidence repos. That global preference file is what lets the same skills work from any repo later.

## Codex Desktop

```bash
git clone https://github.com/chuckblake/Day-Zero-CTO.git
cd Day-Zero-CTO
bin/dzcto setup
```

Report progress in small steps:

1. Clone the repo.
2. `cd` into the repo.
3. Run `bin/dzcto setup`.
4. Confirm setup reaches the final `Next step`.
5. Restart Codex Desktop or start a fresh session.

Install a stable command if useful:

```bash
bin/dzcto install-command
```

## Claude Code

```bash
claude plugin marketplace add chuckblake/Day-Zero-CTO
claude plugin install day-zero-cto@day-zero-cto
```

Inside interactive Claude Code:

```text
/plugin marketplace add chuckblake/Day-Zero-CTO
/plugin install day-zero-cto@day-zero-cto
```

After install, start a fresh session and confirm these commands appear:

```text
/day-zero-cto:dzcto-init
/day-zero-cto:dzcto-ceo-report-weekly
/day-zero-cto:dzcto-ceo-report
```

## Claude Desktop

Package an uploadable custom skill bundle:

```bash
git clone https://github.com/chuckblake/Day-Zero-CTO.git
cd Day-Zero-CTO
bin/dzcto package-claude-desktop
```

Upload `dist/day-zero-cto-claude-desktop.zip` where the user's Claude client and plan support custom skills.

## Useful Helper Commands

```bash
dzcto init \
  --artifacts-dir "$HOME/Documents/Acme CEO Reports" \
  --company-name "Acme" \
  --weekly-range "previous_completed_week" \
  --weekly-start-day "Friday" \
  --weekly-end-day "Thursday" \
  --ceo-report-tone "Direct, concise, business-facing, calm about risk, explicit about asks."

dzcto artifact \
  --artifacts-dir "$HOME/Documents/Acme CEO Reports" \
  --kind ceo-updates \
  --title "CEO Report 2026-06-15 to 2026-06-21" \
  --date "2026-06-21" \
  --data-file "./ceo-report.json"

dzcto doctor
dzcto version
```

## Verify

Codex Desktop:

```text
/dzcto-init
```

Claude Code:

```text
/day-zero-cto:dzcto-init
```

Expected result: the agent asks for report location, weekly defaults, and CEO report tone, then creates an index page that links CEO reports.

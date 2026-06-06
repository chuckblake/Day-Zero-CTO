# Day Zero CTO

Day Zero CTO is a cross-agent skill pack for the earliest version of the CTO job: making technical judgment, operating the engineering loop, and communicating clearly before the company has much process.

It supports Codex Desktop, Claude Code, and Claude Desktop custom-skill style usage from the same shared `skills/` and Python helper implementation.

The core idea is simple: build a portable CTO operating system that becomes company-specific through local context.

## What This Is

Day Zero CTO gives early-stage technical leaders a first set of repeatable CTO workflows:

- Think through hard technical, product, team, and process problems.
- Keep strategy, decisions, risks, team shape, and operating cadence in a project-level `knowledge/wiki` workspace.
- Run recurring CTO reviews that produce durable HTML artifacts.
- Turn engineering reality into CEO-facing updates stored outside the code repo.
- Map tech stacks across one or more read-only codebases.
- Teach system knowledge with spaced repetition.

It is intentionally small. The first version should earn trust by observing the company, naming reality clearly, and producing useful artifacts.

## Skill Set

| Skill | Purpose |
| --- | --- |
| `bootstrap-cto-context` | Onboard Day Zero CTO: choose artifact location, capture company context, connect read-only codebases, create core context, and offer initial reports and learning setup. |
| `refine-core-context` | Interview the user after onboarding to review, correct, and approve updates to core context files before refreshing the generated wiki. |
| `tech-stack` | Review one or more codebases and create a durable Tech Stack report. |
| `review-decisions` | Walk the decision log one recorded decision at a time, using revisit triggers to reaffirm, supersede, punt, or mark evidence needed. |
| `review-risks` | Walk the risk register one active risk at a time, using review dates, severity, mitigation state, and evidence gaps to keep, update, close, punt, mark evidence needed, and log formal choices to `DECISIONS.md`. |
| `weekly-cto-review` | Run the recurring engineering leadership review. |
| `write-ceo-update` | Translate engineering work, risks, and asks into CEO-facing signal. |
| `review-engineering-risk` | Find risks that threaten product, customers, delivery, trust, or runway. |
| `learning` | Teach one focused system concept and schedule it for spaced repetition. |

## Project Wiki

Each startup or engagement gets a project folder outside the code repo. During onboarding, Day Zero CTO should ask for the company name and project/engagement name first, then generate project folder options from those names before asking the user to choose.

Common defaults:

```text
~/Documents/<Company>/
~/Documents/<Company>/<Project>/
~/Documents/Day Zero CTO/<Company>/
~/Documents/<Project>/
```

Day Zero CTO creates and owns `knowledge/wiki/` inside that project folder. The `--wiki-project` or `dzcto init <project>` path controls both the directory name and where the wiki lands. Code repos are read-only evidence sources by default, and `--repo` can be repeated for products that span multiple repos.

Recommended folder shape:

```text
<Company>/
  knowledge/
    wiki/
      index.html
      .dzcto/
        config.json
        manifest.json
        diagnostics.json
        logs/
          latest.log
      core/
        STRATEGY.md
        strategy.html
        TEAM.md
        team.html
        OPERATING_CADENCE.md
        operating-cadence.html
        DECISIONS.md
        decisions.html
        RISKS.md
        risks.html
      reports/
        tech-stack/
        engineering-risk/
        weekly-reviews/
        ceo-updates/
      learning/
        index.html
        checklists/
```

All user-facing wiki pages are HTML. Core context starts as editable Markdown source under `core/`, then the helper renders matching HTML pages. The bookmarkable command center is `knowledge/wiki/index.html`.

Generated wiki pages use a compact command-center interface:

- Sticky top navigation with the current page title, breadcrumbs back to the dashboard, search, and theme toggle.
- Linked KPI strip for cadence, risks, decisions, reports, learning, and connected repos. The risk KPI opens the canonical Risks page rather than duplicating the register on the dashboard.
- A dedicated setup checklist page for company context, read-only repos, core context, cadence, first reports, learning, and generated pages.
- A linked `What needs you today` panel with only actionable due items: decision reviews due or triggered, risk reviews due today or overdue, and cadence items due today or overdue.
- Generated "Current Read" summaries on the Decisions and Risks core pages. These are regenerated from source rows on every refresh and stay short: one paragraph that emphasizes frequent and newer themes.
- Filterable Decisions and Risks pages for narrowing the source logs by owner, date/review timing, source, severity, likelihood, options, or revisit fields when those columns exist.
- A canonical Risks page with the active `core/RISKS.md` log plus a generated `Risk Signals From Reports` intake queue with source links back to Tech Stack, Engineering Risk, Weekly Review, and CEO Update artifacts.
- Report cards show factual artifact counts and, when a report folder has multiple artifacts, a compact previous-run list under the latest report.
- Report, core context, learning, and Help-document sections modeled after the Arwen command-center template.
- Top search across dashboard context, core docs, report artifacts, and active learning items.
- Breadcrumbs, sticky navigation, search, and a light/dark theme on generated pages.
- A visible footer showing the Day Zero CTO skills version used to generate the page.

The helper writes `knowledge/wiki/search-index.json` whenever it refreshes the wiki. Search works best through `dzcto serve "<project folder>"`, because browsers may block `file://` pages from fetching the JSON index.

The dashboard description under the title comes from the first real paragraph in `core/STRATEGY.md`, checked in this order: `Product Thesis`, `Company`, then `Stage`. If those sections are missing or only say `Unknown`, the helper falls back to `.dzcto/config.json` `companyDescription`, which is seeded by `dzcto init --company-description`. Edit the generated wiki description by changing `knowledge/wiki/core/STRATEGY.md`, not `index.html`, then refresh the wiki.

For substantive core context updates, ask an agent to use the `refine-core-context` skill. It runs a short interview, drafts section-level Markdown updates, asks for approval or edits, writes only the source Markdown under `knowledge/wiki/core/`, and refreshes the generated HTML. Direct file edits are still fine for small typo, formatting, or copy fixes; the source files are `STRATEGY.md`, `TEAM.md`, `OPERATING_CADENCE.md`, `DECISIONS.md`, and `RISKS.md`.

Risk information has one editable source of truth: `knowledge/wiki/core/RISKS.md`. The dashboard risk KPI, today-panel risk links, and `core/risks.html` are generated renderings from that Markdown and should be refreshed, not hand-edited. Use a `Source` column when possible so promoted risks can point back to a tech-stack report, engineering-risk review, audit, code evidence, customer signal, or founder judgment.

Report-specific risk sections, including Tech Stack risks and watchpoints, are candidate signals. They should not become a second operating risk list. The generated Risks page rolls structured report signals into `Risk Signals From Reports` so the user can promote, merge, or dismiss them from one place. Promote actionable items into `core/RISKS.md` with owner, mitigation, source, and review date before relying on them in the command center.

Risk reviews can create decisions. If handling a risk leads to a formal choice, such as accepting the risk, choosing a mitigation path, changing architecture or process, closing the risk because of a strategic direction, or deferring based on an explicit threshold, record that choice in `knowledge/wiki/core/DECISIONS.md`. Keep the risk row focused on exposure and follow-through; keep the decision row focused on the choice, rationale, owner, and revisit trigger.

Every active risk should carry a calendar date in its `Next Review` field. External triggers are welcome, but they should be additive, for example `2026-07-06 or on receipt of legal opinion`, because the local dashboard cannot detect most external events by itself. `dzcto status` and `dzcto check-stale` warn when parsed risks lack a calendar review date.

The index shows company information under the title, then a dashboard workspace:

- `What needs you today`: only items requiring action today: due or triggered decision reviews, risk reviews due today or overdue, and cadence items due today or overdue.
- `Setup`: a highlighted dashboard alert only while setup is incomplete; once complete it moves to the bottom of the page as a quieter reference link to `setup/index.html`.
- `Core Context`: links to generated HTML pages for strategy, team, cadence, decisions, and risks.
- `Reports`: latest report cards for each artifact kind.
- `Learning`: spaced-repetition state and mastery progress.
- `Help`: one expandable help document with the command reference, copyable AI prompts, and local helper commands with the exact project and repo context.

The hidden `.dzcto/` directory is the local metadata sidecar. It stores project config, connected repo paths, artifact manifests, diagnostics, and latest helper logs. Generated HTML pages embed a `dzcto-provenance` JSON block with tool version, generation time, config hash, source hashes when available, and artifact ID.

## Cadence Rules

`OPERATING_CADENCE.md` may include an `Index Cadence Rules` section. The helper reads this table whenever it regenerates the index and shows an alert when a scheduled Day Zero CTO report has never run or is due:

```markdown
## Index Cadence Rules

| Report | Folder | Cadence | Day | Grace Days | Command | Prompt Context |
| --- | --- | --- | --- | --- | --- | --- |
| Weekly CTO Review | weekly-reviews | weekly | Monday | 0 | Run the weekly CTO review for Acme. | Focus on beta readiness and evidence from the Rails app. |
```

Supported cadences include `daily`, `weekly`, `biweekly`, `monthly`, `quarterly`, and `every N days/weeks/months`.
The optional `Day` column is displayed on the dashboard cadence preview and can be a weekday or compact rule such as `First Friday`.
The optional `Prompt Context` column is appended to that cadence row's AI prompt card. For global report steering, set `reportPromptContext` in `<project>/knowledge/wiki/.dzcto/config.json`, or run `dzcto init "<project folder>" --report-prompt-context "<guidance>"`.

Use the `Refresh Wiki` local command card, or run `dzcto refresh`, when source Markdown or reports change. It regenerates core HTML pages, the dashboard, the search index, and cadence alerts:

```bash
dzcto serve "<project folder>"
```

Open the printed local URL for the best search experience. A plain `file://` page may not load the generated search index because browsers often block local JSON fetches.

The Help section is the simple cross-agent bridge. It contains the command reference plus copy cards. AI prompt cards copy exact prompts for Claude, Codex, or another agent, including the project folder and configured read-only repo paths. Local command cards copy deterministic `dzcto` commands for refresh, updates, stale checks, serving, diagnostics, and issue bundles.

Generated command centers include review prompts for Decisions and Risks, plus refinement prompts for Strategy, Team, Operating Cadence, Decisions, and Risks. Refinement prompts are meant for the conversational edit path: interview, draft, approve, write source Markdown, refresh.

Generated report pages include an `Action Summary` when structured report data contains decisions, risks, asks, next focus, blockers, mitigations, or review questions. The summary is intentionally compact so a CTO can open a report and immediately see what needs judgment or follow-through.

## Install

### Codex Desktop

Use this path when you want Day Zero CTO available as a Codex Desktop plugin:

```bash
git clone https://github.com/chuckblake/Day-Zero-CTO.git
cd Day-Zero-CTO
bin/dzcto setup
```

The installer requires Python 3.10+ and uses only the Python standard library. It prints small numbered progress steps such as `[1/5]`.

Default install locations:

- Plugin symlink: `~/plugins/day-zero-cto`
- Codex plugin marketplace/settings file: `~/.agents/plugins/marketplace.json`
- Optional editable skill symlinks: `~/.codex/skills`
- Optional stable command shim: `~/.local/bin/dzcto`

You can choose the wiki project folder, plugin link, marketplace/settings file, and editable skill directory during install:

```bash
bin/dzcto setup \
  --wiki-project "$HOME/Documents/Acme CTO" \
  --company-name "Acme" \
  --company-url "https://acme.example" \
  --report-prompt-context "Focus reports on beta readiness and enterprise buyer risk." \
  --repo "$HOME/code/acme-app" \
  --repo "$HOME/code/acme-api" \
  --plugin-link "$HOME/plugins/day-zero-cto" \
  --marketplace-file "$HOME/.agents/plugins/marketplace.json" \
  --editable-skills \
  --editable-skills-dir "$HOME/.codex/skills"
```

Use `--company-description` instead of `--company-url` when you want to provide the company summary yourself.

To install a stable `dzcto` command for your shell:

```bash
bin/dzcto install-command
```

This writes `~/.local/bin/dzcto` by default. Make sure `~/.local/bin` is on your `PATH`, then use the same command every time:

```bash
dzcto serve "$HOME/Documents/Acme CTO"
```

For self-serve help and setup checks:

```bash
dzcto quickstart
dzcto help commands
dzcto help onboarding
dzcto help editing
dzcto help reports
dzcto status "$HOME/Documents/Acme CTO"
dzcto version
```

To update an existing local Codex install from a Git clone:

```bash
bin/dzcto update
```

If you installed editable Codex skill links for development, refresh those links too:

```bash
bin/dzcto update --editable-skills
```

`dzcto update` runs `git pull --ff-only`, refreshes the local plugin marketplace entry, optionally refreshes editable skill symlinks, and runs doctor. It refuses to pull over local edits by default. Commit or stash local edits first, or use `bin/dzcto update --no-pull` when you only want to refresh local links after updating the folder another way.

Pass the same custom install paths you used during setup when they differ from the defaults:

```bash
bin/dzcto update \
  --plugin-link "$HOME/plugins/day-zero-cto" \
  --marketplace-file "$HOME/.agents/plugins/marketplace.json" \
  --editable-skills \
  --editable-skills-dir "$HOME/.codex/skills"
```

For a complete local reinstall from an existing clone:

```bash
python3 scripts/uninstall_local.py
bin/dzcto setup
```

`uninstall_local.py` only removes Day Zero CTO marketplace entries and symlinks that point at the current clone.

If you installed with custom settings paths, pass the matching paths to uninstall:

```bash
python3 scripts/uninstall_local.py \
  --plugin-link "$HOME/plugins/day-zero-cto" \
  --marketplace-file "$HOME/.agents/plugins/marketplace.json" \
  --editable-skills-dir "$HOME/.codex/skills"
```

### Claude Code

Claude Code can install Day Zero CTO as a plugin marketplace:

```bash
claude plugin marketplace add chuckblake/Day-Zero-CTO
claude plugin install day-zero-cto@day-zero-cto
```

Claude Code stores installed plugins under versioned cache folders. To avoid typing paths such as `~/.claude/plugins/cache/day-zero-cto/day-zero-cto/<version>/bin/dzcto`, run the installed helper once to create a stable shell command:

```bash
~/.claude/plugins/cache/day-zero-cto/day-zero-cto/<version>/bin/dzcto install-command
```

After that, use:

```bash
dzcto serve "$HOME/Documents/Acme CTO"
```

Inside interactive Claude Code:

```text
/plugin marketplace add chuckblake/Day-Zero-CTO
/plugin install day-zero-cto@day-zero-cto
```

For local development without installing:

```bash
git clone https://github.com/chuckblake/Day-Zero-CTO.git
claude --plugin-dir ./Day-Zero-CTO
```

To update a published Claude Code plugin install, use Claude Code's plugin update command:

```bash
claude plugin update day-zero-cto@day-zero-cto
```

For local `--plugin-dir` development, update the clone with Git:

```bash
cd Day-Zero-CTO
git pull --ff-only
```

Claude Code plugin install does not require Ruby. The installed `dzcto` helper command requires Python 3.10+ wherever Claude Code executes shell commands.

### Claude Desktop

Claude Desktop style usage is packaged as an uploadable custom skill bundle:

```bash
git clone https://github.com/chuckblake/Day-Zero-CTO.git
cd Day-Zero-CTO
bin/dzcto package-claude-desktop
```

Upload `dist/day-zero-cto-claude-desktop.zip` as a custom skill where your Claude plan/client supports custom skills.

To update a Claude Desktop custom skill bundle:

```bash
cd Day-Zero-CTO
git pull --ff-only
bin/dzcto package-claude-desktop
```

Then upload the new `dist/day-zero-cto-claude-desktop.zip`.

Claude Desktop chat can follow the Day Zero CTO procedures and create downloadable artifacts in its workspace. Durable local filesystem wikis, browser refresh, and stale checks still need a local helper with filesystem access, such as Codex Desktop, Claude Code, or a terminal running `dzcto init`, `dzcto artifact`, `dzcto refresh`, or `dzcto serve`.

## Command Reference

Run these from a session where the plugin `bin/` directory is on `PATH`, or from a local clone with `bin/dzcto`. For the terminal-native version of this table, run:

```bash
dzcto help commands
dzcto <command> -h
```

### Start and Help

| Command | Use when | Key options |
| --- | --- | --- |
| `dzcto quickstart` | Print the shortest self-serve setup path. | `--project <project>` for project-specific examples. |
| `dzcto help` | Print Day Zero CTO workflow help. With no topic, prints the command reference. | Topics: `onboarding`, `editing`, `reports`, `commands`, `serve`, `troubleshooting`, `learning`, `artifacts`; optional `--project <project>`. |
| `dzcto version` | Print the installed helper version. | None. |

### Install and Update

| Command | Use when | Key options |
| --- | --- | --- |
| `dzcto setup` | Install the local Codex plugin marketplace entry and optionally initialize a project wiki. | `--editable-skills`, `--plugin-link <path>`, `--marketplace-file <path>`, `--editable-skills-dir <path>`, `--wiki-project <project>`, `--company-name <name>`, `--company-description <summary>`, `--company-url <url>`, `--report-prompt-context <text>`, repeatable `--repo <path>`. |
| `dzcto update` | Pull latest changes or refresh local install links, then run doctor. | `--no-pull`, `--allow-dirty`, `--editable-skills`, `--plugin-link <path>`, `--marketplace-file <path>`, `--editable-skills-dir <path>`, `--project <project>`. |
| `dzcto install-command` | Create a stable shell command so users do not need versioned plugin cache paths. | `--dest <path>` defaults to `~/.local/bin/dzcto`; `--force` replaces an existing generated shim. |
| `dzcto package-claude-desktop` | Build an uploadable Claude Desktop custom skill zip. | `--output <zip>`; defaults to `dist/day-zero-cto-claude-desktop.zip`. |

### Project Wiki

| Command | Use when | Key options |
| --- | --- | --- |
| `dzcto init "<project folder>"` | Create or refresh `<project>/knowledge/wiki`, sidecar metadata, generated core pages, search index, and dashboard. | `--company-name <name>`, `--company-description <summary>`, `--company-url <url>`, `--report-prompt-context <text>`, repeatable `--repo <path>`. |
| `dzcto refresh "<project folder>"` | Regenerate dashboard, core HTML pages, structured report pages, learning index, search index, cadence alerts, and provenance. | Project folder argument. |
| `dzcto serve "<project folder>"` | Serve the wiki locally so search JSON loads reliably and local refresh works. | `--host 127.0.0.1`, `--port 8765`. |
| `dzcto status "<project folder>"` | Show the terminal setup checklist and operating health for the project. | `--json` for machine-readable output. |
| `dzcto doctor` | Check install health, manifests, helper syntax, wrappers, and optional project files. | `--project <project>`, `--json`. |
| `dzcto check-stale "<project folder>"` | Check stale generated pages, generator version drift, missing artifacts, and cadence due state. | `--json`, `--fail-on-stale`. |

### Reports and Artifacts

| Command | Use when | Key options |
| --- | --- | --- |
| `dzcto artifact` | Generate a durable HTML report and refresh the dashboard. Prefer structured JSON. | Required: `--project <project>`, `--kind <kind>`, `--title <title>`. Optional: `--date YYYY-MM-DD`, `--data-file <json>`, `--body-file <html>`. Kinds: `tech-stack`, `engineering-risk`, `weekly-reviews`, `ceo-updates`. |
| `dzcto collect-issue-bundle "<project folder>"` | Create a troubleshooting bundle with redacted sidecar metadata and stale checks. | `--output <zip>`, `--no-redact`. |

### Learning

| Command | Use when | Key options |
| --- | --- | --- |
| `dzcto learning --project <project> --select` | Select the next due or new learning item. | Optional `--date YYYY-MM-DD`. |
| `dzcto learning --project <project> --add` | Add one learning item. | `--id <id>`, `--title <title>`, `--summary <text>`, `--details <text>`, `--details-file <path>`, `--source <text>`, `--tags <csv>`. |
| `dzcto learning --project <project> --seed-file <json>` | Seed multiple learning items from a JSON file. | `--seed-file <json>`. |
| `dzcto learning --project <project> --record <rating>` | Record a review rating and schedule the next review. | `--id <id>`, `--note <text>`, optional `--date YYYY-MM-DD`; ratings include `Needs Work`, `Familiar`, and `Confident`. |
| `dzcto learning --project <project> --stats` | Print learning counts and progress. | `--stats`. |

### Skill Prompt Workflows

| Skill prompt | Use when |
| --- | --- |
| `day-zero-cto:refine-core-context` | Interview, draft, approve, write source Markdown, and refresh core context. |
| `day-zero-cto:review-decisions` | Walk recorded decisions one at a time and reaffirm, supersede, punt, or mark evidence needed. |
| `day-zero-cto:review-risks` | Walk active risks one at a time and keep, update, close, punt, mark evidence needed, or log decisions made while addressing the risk. |
| `day-zero-cto:review-engineering-risk` | Create a fresh engineering-risk report artifact. |

Generated dashboard pages also include a `Help` section with a project-specific command reference and copyable command cards.

## Report Payloads

Agents should write structured JSON and let `dzcto artifact` render HTML:

```bash
dzcto artifact --project "<project folder>" --kind weekly-reviews --title "Weekly CTO Review" --data-file "<json report data file>"
```

The supported report kinds have fixed section templates:

| Kind | Expected JSON fields |
| --- | --- |
| `tech-stack` | `executive_read`, `stack_components`, `architecture_shape`, `data_storage`, `integrations`, `infrastructure_operations`, `development_tooling`, `risks_watchpoints`, `onboarding_notes`, `sources` |
| `weekly-reviews` | `executive_read`, `shipped_learned`, `risks`, `decisions_needed`, `team_process`, `next_week_focus`, `ceo_update_seeds`, `sources` |
| `ceo-updates` | `headline`, `progress`, `risks_blockers`, `asks_decisions`, `next`, `sources` |
| `engineering-risk` | `executive_read`, `top_risks`, `mitigations`, `watchpoints`, `sources` |

Optional `metrics` are rendered as summary cards when present.

For `tech-stack`, `risks_watchpoints` rows are rendered as candidate risks, not as the active operating register. The helper stores structured report JSON next to generated report HTML, and `core/risks.html` reads that data into `Risk Signals From Reports` with links back to the source report. Include `source` when available, and promote any risk that needs ongoing review into `core/RISKS.md`.

## Repo Structure

```text
day-zero-cto/
├── .codex-plugin/
├── .claude-plugin/
├── .github/
├── bin/
│   ├── dzcto
│   ├── dzcto-artifact
│   ├── dzcto-doctor
│   └── dzcto-learning
├── skills/
│   ├── bootstrap-cto-context/
│   ├── refine-core-context/
│   ├── tech-stack/
│   ├── review-decisions/
│   ├── review-risks/
│   ├── weekly-cto-review/
│   ├── write-ceo-update/
│   ├── review-engineering-risk/
│   └── learning/
├── scripts/
│   ├── dzcto.py
│   ├── dzcto_artifact.py
│   ├── dzcto_common.py
│   ├── dzcto_doctor.py
│   ├── dzcto_learning.py
│   ├── install_local_marketplace.py
│   ├── install_local_skills.py
│   └── uninstall_local.py
├── AGENTS.md
├── INSTALL_FOR_AGENTS.md
└── README.md
```

`scripts/dzcto.py` is the canonical local command surface. It exposes `quickstart`, `help`, `version`, `setup`, `update`, `doctor`, `init`, `refresh`, `serve`, `install-command`, `status`, `check-stale`, `artifact`, `learning`, `collect-issue-bundle`, and `package-claude-desktop`.

`scripts/dzcto_artifact.py` owns HTML generation, sidecar metadata, generated core HTML pages, report templates, learning index rendering, cadence alerts, and the command-center index.

`scripts/dzcto_learning.py` manages spaced-repetition items under `knowledge/wiki/learning/`. It selects due or new items, records `Needs Work`, `Familiar`, and `Confident` ratings, writes a mastery checklist, and refreshes the wiki index after learning state changes.

Current runtime requirement: Python 3.10+. The helpers use only the Python standard library. Run `bin/dzcto doctor` to check runtime, manifests, wrappers, helper syntax, and an optional project folder.

## Agent Handoff

If another agent session needs to install or update Day Zero CTO, point it at:

```text
https://raw.githubusercontent.com/chuckblake/Day-Zero-CTO/main/INSTALL_FOR_AGENTS.md
```

## Usage

Install or load this plugin, then ask for one of the workflows in natural language:

- "Onboard Day Zero CTO for this startup. Use `~/Documents/Acme CTO` as the project folder, company name `Acme`, company URL `https://acme.example`, and read-only repos `~/code/acme-app` and `~/code/acme-api`."
- "Refine the Strategy core context for this startup. Interview me section by section and let me approve the Markdown before updating the wiki."
- "Review the decision log for this startup. Walk me through each revisit trigger and let me reaffirm, supersede, punt, or mark evidence needed."
- "Create a Tech Stack report from the connected codebases and write it into the project knowledge wiki."
- "Run the weekly CTO review and write the HTML report into the project knowledge wiki."
- "Write a CEO update from this week's engineering work."
- "Review engineering risk before launch. Treat the code repos as read-only."
- "Review this PR as a startup CTO and save a durable review artifact."
- "Run a Day Zero CTO learning prompt."

## Design Principles

- Keep the context small enough that future agents will actually read it.
- Keep Day Zero CTO artifacts in the project `knowledge/wiki`, not the active code repo.
- Treat code repos as read-only evidence unless the user explicitly asks for code changes.
- Ground advice in local evidence: code, docs, decisions, risks, incidents, and user notes.
- Label assumptions instead of laundering uncertainty into confidence.
- Prefer startup-relevant judgment over generic best practices.
- Produce durable HTML artifacts for every user-facing page.
- Use spaced repetition to help the user retain system knowledge over time.

## License

Day Zero CTO is released under the MIT License. See `LICENSE`.

## Acknowledgements

The learning workflow borrows broad teaching-process ideas such as one-question-at-a-time practice, visible progress, and mastery confirmation from the open-source `teach` skill in [`alexknowshtml/claude-skills`](https://github.com/alexknowshtml/claude-skills/blob/main/teach/SKILL.md). Day Zero CTO implements those ideas independently in its own spaced-repetition workflow.

The Decisions and Risks "Current Read" pattern is inspired by the broad product idea in [`garrytan/gbrain`](https://github.com/garrytan/gbrain): keep durable source material and present a short synthesized read above it. GBrain is MIT licensed, and Day Zero CTO does not include GBrain code; this repo independently implements the idea for local CTO decision and risk logs.

## Roadmap Ideas

Likely next skills:

- `write-decision-memo`
- `run-incident-review`
- `plan-engineering-week`
- `hiring-scorecard`
- `fundraise-tech-diligence`
- `customer-commitment-review`
- `architecture-pressure-test`

The right next skill should come from usage: which CTO job keeps recurring, has enough structure to encode, and benefits from local context.

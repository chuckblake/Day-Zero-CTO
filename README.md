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
- Review code through the lens of startup risk and leverage.
- Teach system knowledge with spaced repetition.

It is intentionally small. The first version should earn trust by observing the company, naming reality clearly, and producing useful artifacts.

## Skill Set

| Skill | Purpose |
| --- | --- |
| `bootstrap-cto-context` | Onboard Day Zero CTO: choose artifact location, capture company context, connect read-only codebases, create core context, and offer initial reports and learning setup. |
| `refine-core-context` | Interview the user after onboarding to review, correct, and approve updates to core context files before refreshing the generated wiki. |
| `tech-stack` | Review one or more codebases and create a durable Tech Stack report. |
| `work-through-problem` | Reason through ambiguous CTO decisions and tradeoffs. |
| `weekly-cto-review` | Run the recurring engineering leadership review. |
| `write-ceo-update` | Translate engineering work, risks, and asks into CEO-facing signal. |
| `review-engineering-risk` | Find risks that threaten product, customers, delivery, trust, or runway. |
| `cto-code-review` | Review code with a startup CTO lens: correctness, trust, operability, speed, and maintainability. |
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
        decisions/
        code-reviews/
      learning/
        index.html
        checklists/
```

All user-facing wiki pages are HTML. Core context starts as editable Markdown source under `core/`, then the helper renders matching HTML pages. The bookmarkable command center is `knowledge/wiki/index.html`.

Generated wiki pages use a compact command-center interface:

- KPI strip for cadence, risks, decisions, reports, learning, and connected repos.
- A `What needs you today` panel with decisions, high-priority risks, and operating cadence.
- Risk register cards parsed from `core/RISKS.md` tables or headings, with severity filtering.
- Report, core context, learning, and command sections modeled after the Arwen command-center template.
- Top search across dashboard context, core docs, report artifacts, and active learning items.
- Breadcrumbs, automatic page tables of contents, and a light/dark theme on generated pages.
- A visible footer showing the Day Zero CTO skills version used to generate the page.

The helper writes `knowledge/wiki/search-index.json` whenever it refreshes the wiki. Search works best through `dzcto serve "<project folder>"`, because browsers may block `file://` pages from fetching the JSON index.

The dashboard description under the title comes from the first real paragraph in `core/STRATEGY.md`, checked in this order: `Product Thesis`, `Company`, then `Stage`. If those sections are missing or only say `Unknown`, the helper falls back to `.dzcto/config.json` `companyDescription`, which is seeded by `dzcto init --company-description`. Edit the generated wiki description by changing `knowledge/wiki/core/STRATEGY.md`, not `index.html`, then refresh the wiki.

For substantive core context updates, ask an agent to use the `refine-core-context` skill. It runs a short interview, drafts section-level Markdown updates, asks for approval or edits, writes only the source Markdown under `knowledge/wiki/core/`, and refreshes the generated HTML. Direct file edits are still fine for small typo, formatting, or copy fixes; the source files are `STRATEGY.md`, `TEAM.md`, `OPERATING_CADENCE.md`, `DECISIONS.md`, and `RISKS.md`.

The index shows company information under the title, then a dashboard workspace:

- `What needs you today`: decisions, priority risks, and cadence from core context.
- `Risk Register`: severity-filterable cards from `core/RISKS.md`.
- `Core Context`: links to generated HTML pages for strategy, team, cadence, decisions, and risks.
- `Reports`: latest report cards for each artifact kind.
- `Learning`: spaced-repetition state and mastery progress.
- `Commands`: copyable AI prompts and local helper commands with the exact project and repo context.

The hidden `.dzcto/` directory is the local metadata sidecar. It stores project config, connected repo paths, artifact manifests, diagnostics, and latest helper logs. Generated HTML pages embed a `dzcto-provenance` JSON block with tool version, generation time, config hash, source hashes when available, and artifact ID.

## Cadence Rules

`OPERATING_CADENCE.md` may include an `Index Cadence Rules` section. The helper reads this table whenever it regenerates the index and shows an alert when a scheduled Day Zero CTO report has never run or is due:

```markdown
## Index Cadence Rules

| Report | Folder | Cadence | Grace Days | Command |
| --- | --- | --- | --- | --- |
| Weekly CTO Review | weekly-reviews | weekly | 0 | Run the weekly CTO review for Acme. |
```

Supported cadences include `daily`, `weekly`, `biweekly`, `monthly`, `quarterly`, and `every N days/weeks/months`.

The dashboard `Refresh Wiki` button reruns `dzcto refresh` only when the wiki is served through the local helper. It regenerates core HTML pages, the dashboard, the search index, and cadence alerts:

```bash
dzcto serve "<project folder>"
```

Open the printed local URL and click `Refresh Wiki`. A plain `file://` page cannot run Python directly, and may not load the generated search index, so the button will tell the user to use `dzcto serve`.

The Commands section is the simple cross-agent bridge. AI prompt cards copy exact prompts for Claude, Codex, or another agent, including the project folder and configured read-only repo paths. Local command cards copy deterministic `dzcto` commands for refresh, updates, stale checks, serving, diagnostics, and issue bundles.

Generated command centers include refinement prompts for Strategy, Team, Operating Cadence, Decisions, and Risks. These prompts are meant for the conversational edit path: interview, draft, approve, write source Markdown, refresh.

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

## Helper Commands

Run these from a session where the plugin `bin/` directory is on `PATH`, or from a local clone with `bin/dzcto`.

```bash
dzcto install-command
dzcto setup
dzcto update
dzcto init "<project folder>" --company-name "<name>" --company-description "<summary>" --repo "<repo path>"
dzcto refresh "<project folder>"
dzcto serve "<project folder>"
dzcto doctor --project "<project folder>"
dzcto check-stale "<project folder>"
dzcto collect-issue-bundle "<project folder>"
dzcto package-claude-desktop
```

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
| `decisions` | `decision`, `context`, `options`, `tradeoffs`, `recommendation`, `watchpoints`, `follow_ups`, `sources` |
| `code-reviews` | `merge_recommendation`, `blocking`, `fyi`, `questions`, `tests_verification`, `startup_risk_note`, `sources` |

Optional `metrics` are rendered as summary cards when present.

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
│   ├── work-through-problem/
│   ├── weekly-cto-review/
│   ├── write-ceo-update/
│   ├── review-engineering-risk/
│   ├── cto-code-review/
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

`scripts/dzcto.py` is the canonical local command surface. It exposes `setup`, `update`, `doctor`, `init`, `refresh`, `serve`, `artifact`, `learning`, `check-stale`, `collect-issue-bundle`, and `package-claude-desktop`.

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

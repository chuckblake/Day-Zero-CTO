# Day Zero CTO

Day Zero CTO is a cross-agent skill pack for the earliest version of the CTO job: making technical judgment, operating the engineering loop, and communicating clearly before the company has much process.

It supports Codex Desktop and Claude Code from the same shared `skills/` and `scripts/` implementation.

The core idea is simple: do not build a generic executive coach. Build a portable CTO operating system that becomes company-specific through local context.

Day Zero CTO is adjacent to AI shipping stacks, but it is not trying to be another virtual engineering team. It is the leadership wrapper around that work: the context, cadence, decisions, risk register, codebase map, and executive communication that make shipping fit the company.

## What This Is

Day Zero CTO gives early-stage technical leaders a first set of repeatable CTO workflows:

- Think through hard technical, product, team, and process problems.
- Keep a lightweight memory of strategy, decisions, risks, team shape, and operating cadence in a project-level `knowledge/wiki` workspace.
- Run recurring CTO reviews that produce durable HTML artifacts.
- Turn engineering reality into CEO-facing updates stored outside the code repo.
- Map the tech stack so future agents and technical leaders can understand the codebase quickly.
- Review code through the lens of startup risk and leverage.
- Teach system knowledge with spaced repetition.

It is intentionally small. The first version should earn trust by observing the company, naming reality clearly, and producing useful artifacts.

## First Skill Set

| Skill | Purpose |
| --- | --- |
| `bootstrap-cto-context` | Onboard Day Zero CTO: choose artifact location, connect read-only codebases, create core context, and offer initial reports and learning setup. |
| `tech-stack` | Review the codebase and create a durable Tech Stack report. |
| `work-through-problem` | Reason through ambiguous CTO decisions and tradeoffs. |
| `weekly-cto-review` | Run the recurring engineering leadership review. |
| `write-ceo-update` | Translate engineering work, risks, and asks into CEO-facing signal. |
| `review-engineering-risk` | Find risks that threaten product, customers, delivery, trust, or runway. |
| `cto-code-review` | Review code with a startup CTO lens: correctness, trust, operability, speed, and maintainability. |
| `learning` | Teach one focused system concept and schedule it for spaced repetition. |

## Context Files

The pack works best when each startup or engagement has a project folder outside the code repo, for example:

```text
~/Documents/<Company>/
```

Day Zero CTO creates and owns `knowledge/wiki/` inside that project folder. Code repos are read-only evidence sources by default. Day Zero CTO context and reports should live in the project knowledge wiki unless the user explicitly asks to write into a code repo.

Recommended folder shape:

```text
<Company>/
  knowledge/
    wiki/
      index.html
      core/
        STRATEGY.md
        TEAM.md
        OPERATING_CADENCE.md
        DECISIONS.md
        RISKS.md
      reports/
        tech-stack/
        engineering-risk/
        weekly-reviews/
        ceo-updates/
        decisions/
        code-reviews/
      learning/
      handoffs/
```

The `knowledge/wiki/index.html` file is the bookmarkable front door for the workspace. It identifies the company and shows company context from `core/STRATEGY.md` under the title. The page organizes the workspace into collapsible sections: Core Context, Reports, Learning, Help, and Misc. Reports show run dates next to links and include cadence status from `core/OPERATING_CADENCE.md`; Help contains commands the user can run in their agent; Misc contains handoffs and other non-report artifacts.

Core files:

- `STRATEGY.md`: stage, customer, product thesis, current goals, constraints, and non-goals.
- `TEAM.md`: people, roles, ownership, responsibilities, and communication preferences.
- `OPERATING_CADENCE.md`: weekly review, CEO update rhythm, planning cycle, incident reviews, and expected artifacts.
- `DECISIONS.md`: decision log with context, options, rationale, owner, and revisit trigger.
- `RISKS.md`: risk register with evidence, impact, likelihood, owner, mitigation, and review date.

The `bootstrap-cto-context` skill can create these files under `knowledge/wiki/core/` and mark missing information as `Unknown` instead of inventing company facts.

`OPERATING_CADENCE.md` may include an `Index Cadence Rules` section. The helper reads this table whenever it regenerates the index and shows an alert when a scheduled report has never run or is due:

```markdown
## Index Cadence Rules

| Report | Folder | Cadence | Grace Days | Command |
| --- | --- | --- | --- | --- |
| Weekly CTO Review | weekly-reviews | weekly | 0 | Run the weekly CTO review for Acme. Use project folder `~/Documents/Acme`. |
```

Supported cadences include `daily`, `weekly`, `biweekly`, `monthly`, `quarterly`, and `every N days/weeks/months`.

## Repo Structure

```text
day-zero-cto/
├── .codex-plugin/
│   └── plugin.json
├── .claude-plugin/
│   ├── plugin.json
│   └── marketplace.json
├── bin/
│   ├── dzcto-artifact
│   ├── dzcto-doctor
│   └── dzcto-learning
├── skills/
│   ├── bootstrap-cto-context/
│   ├── tech-stack/
│   ├── work-through-problem/
│   ├── weekly-cto-review/
│   ├── write-ceo-update/
│   ├── review-engineering-risk/
│   ├── cto-code-review/
│   └── learning/
├── scripts/
│   ├── dzcto_artifact.py
│   ├── dzcto_doctor.py
│   ├── dzcto_learning.py
│   ├── install_local_marketplace.py
│   ├── install_local_skills.py
│   ├── uninstall_local.py
│   ├── dzcto-artifact.rb
│   ├── dzcto-learning.rb
│   ├── install-local-marketplace.rb
│   └── install-local-skills.rb
├── AGENTS.md
├── INSTALL_FOR_AGENTS.md
└── README.md
```

Each skill is a normal skill folder with a `SKILL.md` file. `agents/openai.yaml` files are Codex UI metadata. Claude Code reads the shared `SKILL.md` files through the plugin.

`scripts/dzcto_artifact.py` is the shared report helper. It ensures the project `knowledge/wiki` shape exists, writes HTML reports under `knowledge/wiki/reports/<kind>/`, keeps handoffs under `knowledge/wiki/handoffs/`, derives company context from `core/STRATEGY.md`, evaluates cadence alerts from `core/OPERATING_CADENCE.md`, renders `knowledge/wiki/learning/index.html`, and regenerates `knowledge/wiki/index.html` with collapsible Core Context, Reports, Learning, Help, and Misc sections.

Report bodies are template-rendered from structured JSON via `--data-file`. The agent supplies judgment and report facts; the helper owns the HTML structure, styling, ordering, escaping, and repeated section layout. Raw `--body-file` HTML remains as a legacy fallback.

`scripts/dzcto_learning.py` manages spaced-repetition learning items under `knowledge/wiki/learning/`. It selects due or new items, records `Needs Work`, `Familiar`, and `Confident` ratings, writes a mastery checklist under `knowledge/wiki/learning/checklists/`, and refreshes the wiki index after learning state changes.

`bin/dzcto-artifact`, `bin/dzcto-learning`, and `bin/dzcto-doctor` are convenience wrappers. Claude Code adds plugin `bin/` executables to the Bash tool `PATH`; Codex users can run the Python scripts directly or run the wrappers from the repo.

Current runtime requirement: Python 3.10+. The helpers use only the Python standard library. The older Ruby helpers remain as a legacy fallback for existing local installs, but new public install instructions and wrappers are Python-first. Run `bin/dzcto-doctor` to check the runtime, manifests, wrappers, helper syntax, and optional project folder before promising generated artifacts.

## Report Payloads

Agents should write structured JSON and let `dzcto-artifact` render HTML:

```bash
dzcto-artifact --project "<project folder>" --kind weekly-reviews --title "Weekly CTO Review" --data-file "<json report data file>"
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

## Install

### Codex Desktop

Clone the repo, run the local marketplace installer, then restart Codex Desktop:

```bash
git clone https://github.com/chuckblake/Day-Zero-CTO.git
cd Day-Zero-CTO
python3 scripts/install_local_marketplace.py
bin/dzcto-doctor
```

The installer requires Python 3.10+ and uses only the Python standard library.

The installer points `~/plugins/day-zero-cto` at your clone and creates or updates `~/.agents/plugins/marketplace.json` with this plugin entry:

```json
{
  "name": "day-zero-cto",
  "source": {
    "source": "local",
    "path": "./plugins/day-zero-cto"
  },
  "policy": {
    "installation": "AVAILABLE",
    "authentication": "ON_INSTALL"
  },
  "category": "Productivity"
}
```

Because `~/plugins/day-zero-cto` is a symlink to your clone, future `git pull` updates flow into the local Codex plugin.

For active skill development, symlink the individual skills directly into Codex's local skills directory:

```bash
python3 scripts/install_local_skills.py
```

This development installer requires Python 3.10+.

This links each folder under `skills/` into `~/.codex/skills/`. Edit the skill files in this repo, then restart Codex Desktop or start a fresh session to reload skill metadata.

To refresh an existing local Codex install after pulling changes:

```bash
git pull
python3 scripts/install_local_marketplace.py
bin/dzcto-doctor
```

For a complete local reinstall from an existing clone:

```bash
python3 scripts/uninstall_local.py
python3 scripts/install_local_marketplace.py
bin/dzcto-doctor
```

`uninstall_local.py` only removes the Day Zero CTO Codex marketplace entry plus plugin and editable-skill symlinks that point at the current clone. It skips unrelated files and non-symlink directories.

For a complete reinstall from a fresh clone, remove the old clone after running the uninstall helper from it, clone again, then run:

```bash
python3 scripts/install_local_marketplace.py
bin/dzcto-doctor
```

### Claude Code

Claude Code can install Day Zero CTO as a plugin marketplace:

```bash
claude plugin marketplace add chuckblake/Day-Zero-CTO
claude plugin install day-zero-cto@day-zero-cto
```

The plugin can be installed without Ruby. Running Day Zero CTO artifact and learning helpers requires Python 3.10+ on the machine where Claude Code executes shell commands. The wrappers print a clear error if `python3` is missing.

Inside interactive Claude Code, use the slash-command equivalents:

```text
/plugin marketplace add chuckblake/Day-Zero-CTO
/plugin install day-zero-cto@day-zero-cto
```

For local development without installing:

```bash
git clone https://github.com/chuckblake/Day-Zero-CTO.git
claude --plugin-dir ./Day-Zero-CTO
```

After published updates:

```bash
claude plugin update day-zero-cto@day-zero-cto
```

Claude Code plugin skills are namespaced. For example:

```text
/day-zero-cto:bootstrap-cto-context Onboard Day Zero CTO for this startup. Use project folder `~/Documents/Acme`.
```

### Agent Handoff

If another agent session needs to install or update Day Zero CTO, point it at:

```text
https://raw.githubusercontent.com/chuckblake/Day-Zero-CTO/main/INSTALL_FOR_AGENTS.md
```

That file includes both Codex Desktop and Claude Code install paths plus the first useful prompt.

## Usage

Install or load this plugin, then ask for one of the workflows in natural language:

- "Onboard Day Zero CTO for this startup. Use `~/Documents/Acme` as the project folder and `~/code/acme-app` as the read-only code repo."
- "Create a Tech Stack report from the codebase and write it into the project knowledge wiki."
- "Run the weekly CTO review and write the HTML report into the project knowledge wiki."
- "Write a CEO update from this week's engineering work."
- "Review engineering risk before launch. Treat the code repo as read-only."
- "Review this PR as a startup CTO and save a durable review artifact."
- "Run a Day Zero CTO learning prompt."

## Design Principles

- Keep the context small enough that future agents will actually read it.
- Keep Day Zero CTO artifacts in the project `knowledge/wiki`, not the active code repo.
- Treat code repos as read-only evidence unless the user explicitly asks for code changes.
- Ground advice in local evidence: code, docs, decisions, risks, incidents, and user notes.
- Label assumptions instead of laundering uncertainty into confidence.
- Prefer startup-relevant judgment over generic best practices.
- Produce durable HTML artifacts for reports and reviews, then keep `index.html` current.
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

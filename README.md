# Day Zero CTO

Day Zero CTO is a Codex Desktop skill pack for the earliest version of the CTO job: making technical judgment, operating the engineering loop, and communicating clearly before the company has much process.

The core idea is simple: do not build a generic executive coach. Build a portable CTO operating system that becomes company-specific through local context.

This is adjacent to AI shipping stacks, but it is not trying to be another virtual engineering team. Day Zero CTO is the leadership wrapper around that work: the context, cadence, decisions, risk register, people conversations, and executive communication that make shipping fit the company.

## What This Is

Day Zero CTO gives Builder a first set of repeatable CTO workflows:

- Think through hard technical, product, team, and process problems.
- Keep a lightweight memory of strategy, decisions, risks, team shape, and operating cadence in a dedicated Day Zero CTO workspace.
- Run recurring CTO reviews that produce durable HTML artifacts.
- Turn engineering reality into CEO-facing updates stored outside the code repo.
- Review code through the lens of startup risk and leverage.
- Prepare useful one-on-one conversations.

It is intentionally small. The first version should earn trust by observing the company, naming reality clearly, and producing useful artifacts.

## First Skill Set

| Skill | Purpose |
| --- | --- |
| `bootstrap-cto-context` | Create or refresh the local context files the rest of the pack depends on. |
| `work-through-problem` | Reason through ambiguous CTO decisions and tradeoffs. |
| `weekly-cto-review` | Run the recurring engineering leadership review. |
| `write-ceo-update` | Translate engineering work, risks, and asks into CEO-facing signal. |
| `review-engineering-risk` | Find risks that threaten product, customers, delivery, trust, or runway. |
| `prep-one-on-one` | Prepare practical CTO one-on-ones with engineers, managers, cofounders, or partners. |
| `cto-code-review` | Review code with a startup CTO lens: correctness, trust, operability, speed, and maintainability. |

## Context Files

The pack works best when each startup or engagement has a dedicated Day Zero CTO home folder outside the code repo, for example:

```text
~/Documents/<Company>/Day Zero CTO/
```

Code repos are read-only evidence sources by default. Day Zero CTO context and reports should live in the Day Zero CTO home unless the user explicitly asks to write into a code repo.

Recommended folder shape:

```text
Day Zero CTO/
  index.html
  core/
    STRATEGY.md
    TEAM.md
    OPERATING_CADENCE.md
    DECISIONS.md
    RISKS.md
  reports/
    engineering-risk/
    weekly-reviews/
    ceo-updates/
    one-on-ones/
    decisions/
    code-reviews/
  handoffs/
```

The `index.html` file is the bookmarkable front door for the workspace. It links to core docs, latest reports, and historical artifacts.

Core files:

- `STRATEGY.md`: stage, customer, product thesis, current goals, constraints, and non-goals.
- `TEAM.md`: people, roles, ownership, responsibilities, and communication preferences.
- `OPERATING_CADENCE.md`: weekly review, CEO update rhythm, planning cycle, one-on-ones, and incident reviews.
- `DECISIONS.md`: decision log with context, options, rationale, owner, and revisit trigger.
- `RISKS.md`: risk register with evidence, impact, likelihood, owner, mitigation, and review date.

The `bootstrap-cto-context` skill can create these files under `core/` and mark missing information as `Unknown` instead of inventing company facts.

## Repo Structure

```text
day-zero-cto/
├── .codex-plugin/
│   └── plugin.json
├── skills/
│   ├── bootstrap-cto-context/
│   ├── work-through-problem/
│   ├── weekly-cto-review/
│   ├── write-ceo-update/
│   ├── review-engineering-risk/
│   ├── prep-one-on-one/
│   └── cto-code-review/
├── scripts/
│   ├── dzcto-artifact.rb
│   └── install-local-marketplace.rb
└── README.md
```

Each skill is a normal Codex skill folder with a `SKILL.md` file and optional `agents/openai.yaml` UI metadata.

`scripts/dzcto-artifact.rb` is the shared report helper. It ensures the Day Zero CTO folder shape exists, writes HTML reports under `reports/<kind>/`, and regenerates `index.html`.

## Install

### Local Plugin Marketplace

Clone the repo, run the installer, then restart Codex Desktop:

```bash
git clone https://github.com/chuckblake/Day-Zero-CTO.git
cd Day-Zero-CTO
ruby scripts/install-local-marketplace.rb
```

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

To refresh an existing local install after pulling changes:

```bash
git pull
ruby scripts/install-local-marketplace.rb
```

### Skill-Only Install

If you only want the individual skills without the plugin marketplace card, install them into Codex's skills directory:

```bash
python3 ~/.codex/skills/.system/skill-installer/scripts/install-skill-from-github.py \
  --repo chuckblake/Day-Zero-CTO \
  --path skills/bootstrap-cto-context \
  --path skills/work-through-problem \
  --path skills/weekly-cto-review \
  --path skills/write-ceo-update \
  --path skills/review-engineering-risk \
  --path skills/prep-one-on-one \
  --path skills/cto-code-review
```

Restart Codex Desktop after either install path.

## Usage

In Codex Desktop, install or load this plugin, then ask for one of the workflows in natural language:

- "Bootstrap Day Zero CTO context for this startup. Use `~/Documents/Acme/Day Zero CTO` as the home folder and `~/code/acme-app` as the read-only code repo."
- "Run the weekly CTO review and write the HTML report into the Day Zero CTO folder."
- "Write a CEO update from this week's engineering work."
- "Review engineering risk before launch. Treat the code repo as read-only."
- "Help me prep a one-on-one with our backend lead."
- "Review this PR as a startup CTO and save a durable review artifact."

## Design Principles

- Keep the context small enough that future agents will actually read it.
- Keep Day Zero CTO artifacts in the Day Zero CTO home folder, not the active code repo.
- Treat code repos as read-only evidence unless the user explicitly asks for code changes.
- Ground advice in local evidence: code, docs, decisions, risks, incidents, and user notes.
- Label assumptions instead of laundering uncertainty into confidence.
- Prefer startup-relevant judgment over generic best practices.
- Produce durable HTML artifacts for reports and reviews, then keep `index.html` current.

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

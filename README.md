# Day Zero CTO

Day Zero CTO is a Codex Desktop skill pack for the earliest version of the CTO job: making technical judgment, operating the engineering loop, and communicating clearly before the company has much process.

The core idea is simple: do not build a generic executive coach. Build a portable CTO operating system that becomes company-specific through local context.

This is adjacent to AI shipping stacks, but it is not trying to be another virtual engineering team. Day Zero CTO is the leadership wrapper around that work: the context, cadence, decisions, risk register, people conversations, and executive communication that make shipping fit the company.

## What This Is

Day Zero CTO gives Builder a first set of repeatable CTO workflows:

- Think through hard technical, product, team, and process problems.
- Keep a lightweight memory of strategy, decisions, risks, team shape, and operating cadence.
- Run recurring CTO reviews.
- Turn engineering reality into CEO-facing updates.
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

The pack works best when the target startup repo keeps a few lightweight markdown files:

- `STRATEGY.md`: stage, customer, product thesis, current goals, constraints, and non-goals.
- `TEAM.md`: people, roles, ownership, responsibilities, and communication preferences.
- `OPERATING_CADENCE.md`: weekly review, CEO update rhythm, planning cycle, one-on-ones, and incident reviews.
- `DECISIONS.md`: decision log with context, options, rationale, owner, and revisit trigger.
- `RISKS.md`: risk register with evidence, impact, likelihood, owner, mitigation, and review date.

The `bootstrap-cto-context` skill can create these files and mark missing information as `Unknown` instead of inventing company facts.

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
└── README.md
```

Each skill is a normal Codex skill folder with a `SKILL.md` file and optional `agents/openai.yaml` UI metadata.

## Usage

In Codex Desktop, install or load this plugin, then ask for one of the workflows in natural language:

- "Bootstrap Day Zero CTO context for this startup."
- "Run the weekly CTO review."
- "Write a CEO update from this week's engineering work."
- "Review engineering risk before launch."
- "Help me prep a one-on-one with our backend lead."
- "Review this PR as a startup CTO."

## Design Principles

- Keep the context small enough that future agents will actually read it.
- Ground advice in local evidence: code, docs, decisions, risks, incidents, and user notes.
- Label assumptions instead of laundering uncertainty into confidence.
- Prefer startup-relevant judgment over generic best practices.
- Produce durable artifacts only when they will help the next decision.

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

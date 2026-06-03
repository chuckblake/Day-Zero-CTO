---
name: bootstrap-cto-context
description: "Create or refresh the Day Zero CTO context files for a startup. Use when setting up the CTO operating system in a repo, onboarding Codex to company strategy/team/process context, starting a new startup workspace, or repairing missing STRATEGY.md, TEAM.md, OPERATING_CADENCE.md, DECISIONS.md, RISKS.md, and related local context files."
---

# Bootstrap CTO Context

Establish the small set of durable files that make later Day Zero CTO skills company-specific instead of generic.

## Workflow

1. Inspect the repo root for existing context files: `STRATEGY.md`, `TEAM.md`, `OPERATING_CADENCE.md`, `DECISIONS.md`, `RISKS.md`, `README.md`, and obvious product or planning docs.
2. Read only the files needed to understand the company stage, product thesis, team, cadence, and current risks.
3. If important facts are missing and cannot be inferred from local context, ask one concise question or mark the field as `Unknown`.
4. Create or update the core files below when the user asked for setup. Preserve useful existing content; do not erase user notes.
5. Summarize what was created, what remains unknown, and which Day Zero CTO skill should run next.

## Core Files

Use these files unless the repo already has an equivalent convention:

- `STRATEGY.md`: stage, target customer, product thesis, current business goals, constraints, and non-goals.
- `TEAM.md`: people, roles, responsibilities, reporting relationships, open questions, and communication preferences.
- `OPERATING_CADENCE.md`: weekly review, CEO update rhythm, planning cycle, one-on-one rhythm, incident review rhythm, and expected artifacts.
- `DECISIONS.md`: date, decision, context, options considered, rationale, owner, and revisit trigger.
- `RISKS.md`: risk, evidence, impact, likelihood, owner, mitigation, and next review date.

## Standards

- Do not invent company facts. Use `Unknown` or `Assumption:` when evidence is thin.
- Keep files short enough that future agents will actually read them.
- Prefer plain markdown tables for decision and risk registers.
- Treat private people context carefully. Record work-relevant observations, not speculation about motives, health, or personal circumstances.
- Use repo-relative file references inside generated documents.

---
name: bootstrap-cto-context
description: "Create or refresh the Day Zero CTO home folder and core context files for a startup. Use when setting up the CTO operating system, onboarding Codex to company strategy/team/process context, starting a new startup workspace, choosing where durable CTO artifacts should live, connecting an optional read-only code repo evidence source, or repairing missing STRATEGY.md, TEAM.md, OPERATING_CADENCE.md, DECISIONS.md, RISKS.md, and index.html files."
---

# Bootstrap CTO Context

Establish the Day Zero CTO artifact workspace and the small set of durable files that make later skills company-specific instead of generic.

## Workflow

1. Ask the user to confirm the Day Zero CTO home folder before creating or updating durable docs. Recommend a path outside the code repo, such as `~/Documents/<Company>/Day Zero CTO/`.
2. If the folder does not exist, offer to create it. Use `scripts/dzcto-artifact.rb --home <path> --init` from this plugin to create the standard folder structure and `index.html`.
3. Ask separately for an optional code repo pointer. Treat that repo as a read-only evidence source for product docs, architecture docs, implementation evidence, plans, compliance docs, commits, and tests.
4. Inspect any existing files in the Day Zero CTO home folder, especially `core/STRATEGY.md`, `core/TEAM.md`, `core/OPERATING_CADENCE.md`, `core/DECISIONS.md`, `core/RISKS.md`, `index.html`, and relevant report folders.
5. Read only the code repo files needed to understand the company stage, product thesis, team, cadence, and current risks.
6. If important facts are missing and cannot be inferred from local context, ask one concise question or mark the field as `Unknown`.
7. Create or update the core files below inside `<Day Zero CTO home>/core/`. Preserve useful existing content; do not erase user notes.
8. Regenerate `<Day Zero CTO home>/index.html` with `scripts/dzcto-artifact.rb --home <path> --init`.
9. Summarize what was created, what remains unknown, where the Day Zero CTO home lives, what code repo is being used read-only, and which Day Zero CTO skill should run next.

## Core Files

Use these files under `<Day Zero CTO home>/core/` unless the user chooses an equivalent Day Zero CTO artifact convention:

- `STRATEGY.md`: stage, target customer, product thesis, current business goals, constraints, and non-goals.
- `TEAM.md`: people, roles, responsibilities, reporting relationships, open questions, and communication preferences.
- `OPERATING_CADENCE.md`: weekly review, CEO update rhythm, planning cycle, one-on-one rhythm, incident review rhythm, and expected artifacts.
- `DECISIONS.md`: date, decision, context, options considered, rationale, owner, and revisit trigger.
- `RISKS.md`: risk, evidence, impact, likelihood, owner, mitigation, and next review date.

## Standards

- Do not invent company facts. Use `Unknown` or `Assumption:` when evidence is thin.
- Do not write Day Zero CTO files into a code repo unless the user explicitly asks for that.
- Treat the code repo as read-only by default.
- Keep files short enough that future agents will actually read them.
- Prefer plain markdown tables for decision and risk registers.
- Treat private people context carefully. Record work-relevant observations, not speculation about motives, health, or personal circumstances.
- Use file references that make the source clear. For code evidence, use paths relative to the code repo. For Day Zero CTO artifacts, use paths relative to the Day Zero CTO home.

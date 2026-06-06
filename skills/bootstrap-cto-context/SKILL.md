---
name: bootstrap-cto-context
description: "Onboard Day Zero CTO for a startup by creating or refreshing the project knowledge wiki, asking for the Day Zero CTO artifact location, company name, company description or website URL, optional read-only codebase locations, setting up core CTO context, offering to run initial reports, and optionally seeding the first 25 spaced-repetition learning items. Use when setting up the CTO operating system, onboarding the agent to company strategy/team/process context, starting a new startup workspace, choosing where durable CTO artifacts should live, connecting read-only codebase evidence sources, or repairing missing core context, generated HTML core pages, and knowledge/wiki/index.html files."
---

# Onboard Day Zero CTO

Establish the project `knowledge/wiki` workspace, connect read-only codebase evidence, and offer a complete first onboarding pass.

## Workflow

1. Ask for the Day Zero CTO project folder before creating or updating durable docs. Recommend a path outside any code repo, such as `~/Documents/<Company>/`. This is the durable artifact location and determines the wiki directory name.
2. Ask for company name plus either a short company description or a company website URL to use as initial context. If the user gives a URL, use it as evidence and let the helper store it; do not over-scrape or invent details.
3. Ask separately for one or more optional codebase locations. Treat all codebases as read-only evidence sources for product docs, architecture docs, implementation evidence, plans, compliance docs, commits, and tests.
4. If the project folder does not exist, offer to create it. Use `dzcto init "<project folder>" --company-name "<name>" --company-description "<description>" --company-url "<url>" --repo "<repo path>"` when the wrapper is available, repeating `--repo` for multiple repos. Fallback: `python3 scripts/dzcto.py init ...` from this plugin repo. This creates `<project>/knowledge/wiki/`, `knowledge/wiki/.dzcto/` sidecar metadata, generated HTML core pages, and `knowledge/wiki/index.html`.
5. Inspect any existing files in `<project>/knowledge/wiki/`, especially source files in `core/`, generated `core/*.html`, `index.html`, and relevant report folders.
6. Read only the codebase files needed to understand company stage, product thesis, team, cadence, current risks, and stack shape.
7. If important facts are missing and cannot be inferred from local context, ask one concise question or mark the field as `Unknown`.
8. Create or update the source core files below inside `<project>/knowledge/wiki/core/`. Preserve useful existing content; do not erase user notes. The helper renders user-facing `core/*.html` pages from these sources.
9. Regenerate `<project>/knowledge/wiki/index.html` with `dzcto refresh "<project folder>"` or `python3 scripts/dzcto.py refresh "<project folder>"`. The generated index should identify the company, show only company context under the title, and present a command-center dashboard with Cadence, Core Context, Reports, Learning, and Commands sections. New report artifacts should use structured JSON via `--data-file`; raw `--body-file` HTML is only a legacy fallback.
10. Ask: `Do you want to complete onboarding now?` If yes, offer these run-now options: Tech Stack, Engineering Risk Review, Weekly CTO Review, CEO Update, CTO Code Review if a branch/diff exists, and Initial Learning Seed.
11. If the user chooses Initial Learning Seed, create exactly 25 evidence-backed learning items when enough evidence exists. Write them to a JSON array and run:

   ```bash
   dzcto learning --project "<project folder>" --seed-file "<json learning seed file>"

   # Fallback when dzcto is not on PATH:
   python3 scripts/dzcto.py learning --project "<project folder>" --seed-file "<json learning seed file>"
   ```

12. Summarize what was created, what remains unknown, where the project folder and knowledge wiki live, what codebase locations are being used read-only, which onboarding options were run, and which Day Zero CTO skill should run next.

## Core Files

Use these files under `<project>/knowledge/wiki/core/` unless the user chooses an equivalent Day Zero CTO artifact convention:

- `STRATEGY.md`: stage, target customer, product thesis, current business goals, constraints, and non-goals.
- `TEAM.md`: people, roles, responsibilities, reporting relationships, open questions, and communication preferences.
- `OPERATING_CADENCE.md`: weekly review, CEO update rhythm, planning cycle, incident review rhythm, expected artifacts, and optional `## Index Cadence Rules` table with `Report`, `Folder`, `Cadence`, `Grace Days`, and `Command` columns for wiki due-alerts. Commands should be Day Zero CTO skill prompts or `dzcto` helper commands, not coding workflow commands.
- `DECISIONS.md`: date, decision, context, options considered, rationale, owner, and revisit trigger.
- `RISKS.md`: risk, evidence, impact, likelihood, owner, mitigation, and next review date.

## Onboarding Options

- `Tech Stack`: recommended when a codebase is available; creates `reports/tech-stack/`.
- `Engineering Risk Review`: recommended after Tech Stack; creates `reports/engineering-risk/`.
- `Weekly CTO Review`: useful when there is enough recent work signal; creates `reports/weekly-reviews/`.
- `CEO Update`: useful when the user wants an executive-facing summary; creates `reports/ceo-updates/`.
- `CTO Code Review`: only when a branch, PR, or diff is specified; creates `reports/code-reviews/`.
- `Initial Learning Seed`: create 25 learning items from company context, Tech Stack findings, risk register, decisions, docs, and codebase evidence. Do not invent items just to reach 25; if evidence is thin, explain how many were safely created.

## Standards

- Do not invent company facts. Use `Unknown` or `Assumption:` when evidence is thin.
- Do not write Day Zero CTO files into a code repo unless the user explicitly asks for that.
- Treat code repos as read-only by default.
- Keep files short enough that future agents will actually read them.
- Prefer plain markdown tables for decision and risk registers.
- Treat private people context carefully. Record work-relevant observations, not speculation about motives, health, or personal circumstances.
- Use file references that make the source clear. For code evidence, use paths relative to the relevant code repo. For Day Zero CTO artifacts, use paths relative to `<project>/knowledge/wiki/`.

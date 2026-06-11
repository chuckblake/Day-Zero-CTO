---
name: bootstrap-cto-context
description: "Onboard Day Zero CTO: choose project/company name, create or refresh knowledge/wiki, connect read-only repos, seed core context, reports, learning, setup checklist, and index. Use for setup, new startup workspace, missing wiki, or repair."
---

# Onboard Day Zero CTO

Establish the project `knowledge/wiki` workspace, connect read-only codebase evidence, and offer a complete first onboarding pass.

## Workflow

1. Ask for the company name and project/engagement name first. If one name covers both, confirm that and use it for both. Do not ask for the knowledge directory before collecting these names unless the user already supplied a path.
2. Generate 3-4 default project folder options from the names and ask the user to choose or provide a custom path. Recommend a path outside any code repo. Good defaults:
   - `~/Documents/<Company>/` when the project is company-wide or the project name equals the company name.
   - `~/Documents/<Company>/<Project>/` when the company has multiple products, engagements, or workstreams.
   - `~/Documents/Day Zero CTO/<Company>/` when the user wants a central folder for multiple Day Zero CTO projects.
   - `~/Documents/<Project>/` when the project name is already the recognizable workspace name.
3. Sanitize suggested path segments for the filesystem: remove slashes, colons, and control characters; collapse repeated spaces; preserve readable capitalization. Explain that the chosen project folder will contain `knowledge/wiki/`.
4. Ask for either a short company/project description or a company website URL to use as initial context. If the user gives a URL, use it as evidence and let the helper store it; do not over-scrape or invent details.
5. Ask separately for one or more optional codebase locations. Treat all codebases as read-only evidence sources for product docs, architecture docs, implementation evidence, plans, compliance docs, commits, and tests.
6. If the project folder does not exist, offer to create it. Use `dzcto init "<project folder>" --company-name "<company name>" --company-description "<description>" --company-url "<url>" --repo "<repo path>"` when the wrapper is available, repeating `--repo` for multiple repos. Fallback: `python3 scripts/dzcto.py init ...` from this plugin repo. This creates `<project>/knowledge/wiki/`, `knowledge/wiki/.dzcto/` sidecar metadata, generated HTML core pages, and `knowledge/wiki/index.html`.
7. Inspect any existing files in `<project>/knowledge/wiki/`, especially source files in `core/`, generated `core/*.html`, `index.html`, and relevant report folders.
8. Read only the codebase files needed to understand company stage, product thesis, team, cadence, current risks, and stack shape.
9. If important facts are missing and cannot be inferred from local context, ask one concise question or mark the field as `Unknown`.
10. Create or update the source core files below inside `<project>/knowledge/wiki/core/`. Preserve useful existing content; do not erase user notes. The helper renders user-facing `core/*.html` pages from these sources.
11. Regenerate `<project>/knowledge/wiki/index.html` with `dzcto refresh "<project folder>"` or `python3 scripts/dzcto.py refresh "<project folder>"`. The generated index should identify the company, show only company context under the title, and present a command-center dashboard with setup alert/reference, Cadence, Core Context, Reports, Learning, and one expandable Help document. The report section should present Snapshot as the primary CTO readout and Weekly, CEO, Engineering Risk, Tech Stack, and Codebase Accountability as drill-down reports. The full setup checklist should live on `setup/index.html`; the dashboard should highlight setup only when incomplete and become a quiet reference once complete. The risk KPI should link to `core/risks.html`; do not duplicate the full risk register on the homepage. Help should include the project-specific command reference, copyable AI prompts with the exact project folder and read-only repo paths, plus copyable local helper commands. New report artifacts should use structured JSON via `--data-file`; raw `--body-file` HTML is only a legacy fallback.
12. Ask: `Do you want to complete onboarding now?` If yes, offer these run-now options: Tech Stack, Engineering Risk Review, Codebase Accountability, Snapshot Report, Weekly CTO Review, CEO Update, Review Risks, Review Decisions, and Initial Learning Seed.
13. If the user chooses Initial Learning Seed, create up to 25 evidence-backed learning items (usually 25 when evidence is rich). Write them to a JSON array and run:

   ```bash
   dzcto learning --project "<project folder>" --seed-file "<json learning seed file>"

   # Fallback when dzcto is not on PATH:
   python3 scripts/dzcto.py learning --project "<project folder>" --seed-file "<json learning seed file>"
   ```

14. Run or recommend `dzcto status "<project folder>"` so the user has a terminal checklist that matches the dashboard setup checklist.
15. Summarize what was created, what remains unknown, where the project folder and knowledge wiki live, what codebase locations are being used read-only, which onboarding options were run, and which Day Zero CTO skill should run next.

## Core Files

Use these files under `<project>/knowledge/wiki/core/` unless the user chooses an equivalent Day Zero CTO artifact convention:

- `STRATEGY.md`: stage, target customer, product thesis, current business goals, constraints, and non-goals.
- `TEAM.md`: people, roles, responsibilities, reporting relationships, open questions, and communication preferences.
- `OPERATING_CADENCE.md`: weekly review, CEO update rhythm, planning cycle, incident review rhythm, expected artifacts, and optional `## Index Cadence Rules` table with `Report`, `Folder`, `Cadence`, `Day`, `Grace Days`, `Command`, and optional `Prompt Context` columns for wiki due-alerts and prompt steering. Ask for or propose weekday intent for recurring reports. Commands should be Day Zero CTO skill prompts or `dzcto` helper commands, not coding workflow commands.
- `DECISIONS.md`: recorded decisions already taken, original or approximate date, context, options considered, past-tense rationale, owner, and revisit trigger.
- `RISKS.md`: risk, source, evidence, impact, likelihood, owner, mitigation, and calendar next review date. External triggers are allowed, but each active risk still needs a date fallback.

## Onboarding Options

- `Tech Stack`: recommended when a codebase is available; creates `reports/tech-stack/`.
- `Engineering Risk Review`: recommended after Tech Stack; creates `reports/engineering-risk/`.
- `Codebase Accountability`: recommended when local Git history or many coding agents matter; creates `reports/codebase-accountability/`.
- `Snapshot Report`: recommended after there is at least one useful supporting report; creates `reports/snapshot/` and becomes the primary readout.
- `Review Risks`: useful when the user wants to maintain the active risk register one risk at a time; updates `core/RISKS.md`.
- `Review Decisions`: useful when the user wants to revisit recorded decisions one at a time; updates `core/DECISIONS.md`.
- `Weekly CTO Review`: useful when there is enough recent work signal; creates a supporting operating-detail report under `reports/weekly-reviews/`.
- `CEO Update`: useful when the user wants an executive-facing communication draft; creates a supporting report under `reports/ceo-updates/`.
- `Initial Learning Seed`: create up to 25 learning items from company context, Tech Stack findings, risk register, decisions, docs, and codebase evidence. Do not invent items just to reach 25; if evidence is thin, explain how many were safely created.

## Standards

- Do not invent company facts. Use `Unknown` or `Assumption:` when evidence is thin.
- Do not write Day Zero CTO files into a code repo unless the user explicitly asks for that.
- Treat code repos as read-only by default.
- Keep files short enough that future agents will actually read them.
- Prefer plain markdown tables for decision and risk registers.
- Generated Decisions and Risks pages include short regenerated Current Read summaries, signal intake sections, canonical registries, and per-item detail pages built from source Markdown. Do not hand-edit summaries, registry JSON, detail pages, or generated HTML; update source Markdown or structured report data, then refresh.
- Tech Stack, Engineering Risk, Weekly Review, and CEO Update report risks are candidate signals. They roll up to `core/risks.html#risk-signals` and match to stable risk detail pages when possible; promote actionable items into `core/RISKS.md` with source, owner, mitigation, and a calendar next review date.
- Report asks and decision fields are candidate decision signals until promoted into `core/DECISIONS.md`.
- Treat private people context carefully. Record work-relevant observations, not speculation about motives, health, or personal circumstances.
- Use file references that make the source clear. For code evidence, use paths relative to the relevant code repo. For Day Zero CTO artifacts, use paths relative to `<project>/knowledge/wiki/`.

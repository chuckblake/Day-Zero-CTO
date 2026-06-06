# Day Zero CTO Agent Notes

This repo is a cross-agent skill/plugin bundle for Codex Desktop, Claude Code, and Claude Desktop custom-skill style usage.

## Layout

- `.codex-plugin/plugin.json` is the Codex Desktop plugin manifest.
- `.claude-plugin/plugin.json` is the Claude Code plugin manifest.
- `.claude-plugin/marketplace.json` lets Claude Code add this repo as a marketplace.
- `skills/<skill>/SKILL.md` holds shared skill instructions. Keep these agent-neutral.
- `skills/<skill>/agents/openai.yaml` is Codex UI metadata; Claude Code can ignore it.
- `scripts/` holds deterministic Python helpers used by the skills.
- `bin/` exposes helper wrappers for Claude Code plugin installs and local convenience. `bin/dzcto` is the canonical wrapper; `dzcto-artifact`, `dzcto-learning`, and `dzcto-doctor` are compatibility aliases.
- `INSTALL_FOR_AGENTS.md` is the pasteable install handoff for Codex Desktop, Claude Code, Claude Desktop, and future agent sessions.

## Editing Rules

- Keep Day Zero CTO artifacts in the user's project `knowledge/wiki`, not in a code repo.
- Onboarding should ask for company name and project/engagement name before asking for the project folder, then generate sensible default folder options from those names.
- Treat user code repos as read-only evidence unless the user explicitly asks for code changes.
- Support multiple read-only codebase paths when the user provides them.
- Keep skill bodies concise and procedural. Do not add per-skill README files.
- Prefer shared helper behavior in `scripts/` and expose stable wrappers in `bin/` when useful.
- Installer and doctor scripts should print small numbered progress steps such as `[1/6]`, because users often watch these through an agent transcript.
- `dzcto install-command` should remain the stable way to create `~/.local/bin/dzcto` so users do not need versioned Claude or Codex cache paths.
- Keep `dzcto quickstart`, `dzcto help`, `dzcto status`, and `dzcto version` working as the self-serve front door for users who are not reading the README.
- Local install updates should go through `dzcto update`, which uses `git pull --ff-only`, refreshes local plugin/skill links, and runs doctor. Do not tell users to remember a manual `git pull` plus `setup` sequence for Codex Desktop local installs.
- Keep the skill route primary for users. Add deterministic local helper behavior under `dzcto` before introducing provider-specific complexity.
- Generated wiki HTML should be template-rendered by helpers, include embedded `dzcto-provenance` JSON, and update `knowledge/wiki/.dzcto/` sidecar metadata.
- All user-facing wiki pages should be HTML. Core context Markdown files are editable source, then rendered to generated `core/*.html` pages.
- Generated pages should keep a visible footer with the Day Zero CTO skills version so users can identify what regenerated the wiki.
- For substantive updates to core context Markdown, prefer the `refine-core-context` skill: interview the user, draft section updates, get approval, write source Markdown, then refresh the wiki. Direct Markdown edits are fine for small corrections.
- Treat `core/DECISIONS.md` as a log of decisions already taken. Use the `review-decisions` skill and each row's `Revisit Trigger` when deciding what needs review.
- Treat `core/RISKS.md` as the active risk register and editable source of truth. Dashboard risk cards and `core/risks.html` are generated from it. Report risk tables are candidate signals until promoted into `core/RISKS.md`. Use the `review-risks` skill when walking risks one by one to keep, update, close, punt, or mark evidence needed. Every active risk must have a calendar `Next Review` date and should carry a `Source`; external triggers may be included but cannot replace the date. If a risk review produces a formal choice, log that choice in `core/DECISIONS.md` instead of burying it only in risk notes.
- `core/OPERATING_CADENCE.md` `Index Cadence Rules` may include a `Prompt Context` column for per-report prompt steering. `.dzcto/config.json` may include `reportPromptContext` for global report prompt steering.
- The index should use the command-center sections: Setup alert/reference, Cadence, Core Context, Reports, Learning, and one expandable Help document. The full setup checklist should live on `setup/index.html`; the dashboard should highlight setup near the top only when incomplete and move setup to a quiet bottom-of-page reference once complete. The "What needs you today" panel should show only actionable due-today or overdue items, not future cadence previews or high-priority-but-not-due risks. Help should include the project-specific command reference, copyable AI prompts with exact project/repo context, and copyable local helper commands. Do not restore a separate Commands section, Misc, handoffs, or one-on-one sections.
- When adding or changing install behavior, update `README.md` and `INSTALL_FOR_AGENTS.md`.
- When releasing plugin-facing changes, bump both `.codex-plugin/plugin.json` and `.claude-plugin/plugin.json`; if the Claude marketplace entry has a version, bump it too.
- Do not add a root `CLAUDE.md` file to this plugin repo; Claude Code's plugin validator warns that it is not loaded as plugin context. Put Claude install instructions in `README.md` and `INSTALL_FOR_AGENTS.md`.

## Validation

- Validate JSON manifests after edits.
- Run `python3 -m py_compile` on Python scripts after changing them.
- Smoke-test `dzcto init`, `dzcto artifact`, `dzcto check-stale`, `dzcto collect-issue-bundle`, and `dzcto package-claude-desktop` against a temporary project folder after changing artifact or install behavior.
- Smoke-test at least one structured JSON report with `--data-file` after changing report rendering.

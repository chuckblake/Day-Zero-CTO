# Day Zero CTO Agent Notes

This repo is a cross-agent skill/plugin bundle for Codex Desktop, Claude Code, and Claude Desktop custom-skill style usage.

Current product scope is intentionally small: `/dzcto-init`, `/dzcto-ceo-report-weekly`, and `/dzcto-ceo-report`. Keep the active `skills/` directory focused on those commands. Do not keep inactive legacy `SKILL.md` files anywhere in the plugin tree; some installers may scan all `SKILL.md` files.

## Layout

- `.codex-plugin/plugin.json` is the Codex Desktop plugin manifest.
- `.claude-plugin/plugin.json` is the Claude Code plugin manifest.
- `.claude-plugin/marketplace.json` lets Claude Code add this repo as a marketplace.
- `skills/<skill>/SKILL.md` holds active shared skill instructions. Keep these agent-neutral.
- `skills/<skill>/agents/openai.yaml` is Codex UI metadata; Claude Code can ignore it.
- `scripts/` holds deterministic Python helpers used by the skills.
- `bin/` exposes helper wrappers for Claude Code plugin installs and local convenience. `bin/dzcto` is the canonical wrapper; `dzcto-artifact`, `dzcto-learning`, and `dzcto-doctor` are compatibility aliases.
- `INSTALL_FOR_AGENTS.md` is the pasteable install handoff for Codex Desktop, Claude Code, Claude Desktop, and future agent sessions.

## Editing Rules

- Keep Day Zero CTO artifacts in the user's chosen artifact/report folder, not in a code repo unless the user explicitly chooses that folder.
- `/dzcto-init` should ask for artifact/report location, company/project name, one-sentence company context, weekly report defaults such as `Fri-Thu`, and CEO report tone. It must not silently choose a reporting week.
- Treat user code repos as read-only evidence unless the user explicitly asks for code changes.
- Support multiple read-only codebase paths when the user provides them.
- Keep skill bodies concise and procedural. Do not add per-skill README files.
- Prefer shared helper behavior in `scripts/` and expose stable wrappers in `bin/` when useful.
- Installer and doctor scripts should print small numbered progress steps such as `[1/6]`, because users often watch these through an agent transcript.
- `dzcto install-command` should remain the stable way to create `~/.local/bin/dzcto` so users do not need versioned Claude or Codex cache paths.
- Keep `dzcto quickstart`, `dzcto help`, `dzcto status`, and `dzcto version` working as the self-serve front door for users who are not reading the README.
- Local install updates should go through `dzcto update`, which uses `git pull --ff-only`, refreshes local plugin/skill links, and runs doctor. Do not tell users to remember a manual `git pull` plus `setup` sequence for Codex Desktop local installs.
- Keep the skill route primary for users. Add deterministic local helper behavior under `dzcto` before introducing provider-specific complexity.
- Generated report/index HTML should be template-rendered by helpers, include embedded `dzcto-provenance` JSON, and update `.dzcto/` sidecar metadata.
- The active generated index is a CEO report index, not a full CTO command center.
- Generated pages should keep a visible footer with the Day Zero CTO skills version so users can identify what regenerated the wiki.
- Generated pages should include sticky top navigation with breadcrumbs back to the dashboard, page title, search, and theme toggle.
- The artifact-local `.dzcto/config.json` stores one CEO report workspace. The global `~/.dzcto/config.json` stores `defaultProfile` and `profiles.<name>` objects so the same install supports multiple repos or CTO contexts by default.
- The index should link CEO reports, show the weekly defaults and tone, and expose copyable prompts for `/dzcto-ceo-report-weekly` and `/dzcto-ceo-report`.
- Generated report list sections such as Progress, Risks / Blockers, Asks / Decisions, Watchpoints, and Sources should render as simple bold-led lists, not bordered cards. Keep cards for action summaries, KPIs, repeated dashboard objects, and genuinely framed tools.
- When adding or changing install behavior, update `README.md` and `INSTALL_FOR_AGENTS.md`.
- When releasing plugin-facing changes, bump both `.codex-plugin/plugin.json` and `.claude-plugin/plugin.json`; if the Claude marketplace entry has a version, bump it too.
- Do not add a root `CLAUDE.md` file to this plugin repo; Claude Code's plugin validator warns that it is not loaded as plugin context. Put Claude install instructions in `README.md` and `INSTALL_FOR_AGENTS.md`.

## Validation

- Validate JSON manifests after edits.
- Run `python3 -m py_compile` on Python scripts after changing them.
- Smoke-test `dzcto init --artifacts-dir` and `dzcto artifact --artifacts-dir --kind ceo-updates --data-file` against a temporary folder after changing artifact behavior.
- Validate package generation when changing active skills or Claude Desktop packaging.

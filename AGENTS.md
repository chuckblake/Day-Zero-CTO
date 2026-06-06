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
- Treat user code repos as read-only evidence unless the user explicitly asks for code changes.
- Support multiple read-only codebase paths when the user provides them.
- Keep skill bodies concise and procedural. Do not add per-skill README files.
- Prefer shared helper behavior in `scripts/` and expose stable wrappers in `bin/` when useful.
- Installer and doctor scripts should print small numbered progress steps such as `[1/6]`, because users often watch these through an agent transcript.
- Keep the skill route primary for users. Add deterministic local helper behavior under `dzcto` before introducing provider-specific complexity.
- Generated wiki HTML should be template-rendered by helpers, include embedded `dzcto-provenance` JSON, and update `knowledge/wiki/.dzcto/` sidecar metadata.
- All user-facing wiki pages should be HTML. Core context Markdown files are editable source, then rendered to generated `core/*.html` pages.
- The index should use the command-center sections: Cadence, Core Context, Reports, Learning, and Commands. Do not restore Misc, handoffs, or one-on-one sections.
- When adding or changing install behavior, update `README.md` and `INSTALL_FOR_AGENTS.md`.
- When releasing plugin-facing changes, bump both `.codex-plugin/plugin.json` and `.claude-plugin/plugin.json`; if the Claude marketplace entry has a version, bump it too.
- Do not add a root `CLAUDE.md` file to this plugin repo; Claude Code's plugin validator warns that it is not loaded as plugin context. Put Claude install instructions in `README.md` and `INSTALL_FOR_AGENTS.md`.

## Validation

- Validate JSON manifests after edits.
- Run `python3 -m py_compile` on Python scripts after changing them.
- Smoke-test `dzcto init`, `dzcto artifact`, `dzcto check-stale`, `dzcto collect-issue-bundle`, and `dzcto package-claude-desktop` against a temporary project folder after changing artifact or install behavior.
- Smoke-test at least one structured JSON report with `--data-file` after changing report rendering.

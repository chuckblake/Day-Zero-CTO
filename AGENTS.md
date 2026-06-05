# Day Zero CTO Agent Notes

This repo is a cross-agent skill/plugin bundle for Codex Desktop and Claude Code.

## Layout

- `.codex-plugin/plugin.json` is the Codex Desktop plugin manifest.
- `.claude-plugin/plugin.json` is the Claude Code plugin manifest.
- `.claude-plugin/marketplace.json` lets Claude Code add this repo as a marketplace.
- `skills/<skill>/SKILL.md` holds shared skill instructions. Keep these agent-neutral.
- `skills/<skill>/agents/openai.yaml` is Codex UI metadata; Claude Code can ignore it.
- `scripts/` holds deterministic helpers used by the skills.
- `bin/` exposes helper wrappers for Claude Code plugin installs and local convenience. The wrappers currently require Ruby and should print a clear error if Ruby is absent.
- `INSTALL_FOR_AGENTS.md` is the pasteable install handoff for Codex Desktop, Claude Code, and future agent sessions.

## Editing Rules

- Keep Day Zero CTO artifacts in the user's project `knowledge/wiki`, not in a code repo.
- Treat user code repos as read-only evidence unless the user explicitly asks for code changes.
- Keep skill bodies concise and procedural. Do not add per-skill README files.
- Prefer shared helper behavior in `scripts/` and expose stable wrappers in `bin/` when useful.
- When adding or changing install behavior, update `README.md` and `INSTALL_FOR_AGENTS.md`.
- When releasing plugin-facing changes, bump both `.codex-plugin/plugin.json` and `.claude-plugin/plugin.json`; if the Claude marketplace entry has a version, bump it too.
- Do not add a root `CLAUDE.md` file to this plugin repo; Claude Code's plugin validator warns that it is not loaded as plugin context. Put Claude install instructions in `README.md` and `INSTALL_FOR_AGENTS.md`.

## Validation

- Validate JSON manifests after edits.
- Run `ruby -c` on Ruby scripts after changing them.
- Smoke-test at least one structured JSON report with `--data-file` after changing report rendering.
- Smoke-test artifact generation with a temporary project folder.

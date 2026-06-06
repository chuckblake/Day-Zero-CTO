# Install Day Zero CTO For Agent Sessions

Use this when another Codex Desktop or Claude Code session needs to install Day Zero CTO.

## What To Ask For

Ask the user for paths before running Day Zero CTO work:

- Day Zero CTO project folder: where durable artifacts should live, usually `~/Documents/<Company>/`.
- Codebase location: optional read-only evidence source, never the default destination for Day Zero CTO docs. Multiple codebases are allowed when the product spans repos.

Day Zero CTO writes to `<project>/knowledge/wiki/`. Generated artifacts also maintain local metadata under `<project>/knowledge/wiki/.dzcto/` so `dzcto check-stale` can detect stale reports, missing sidecars, cadence alerts, and version drift.

Runtime note: Day Zero CTO helpers require Python 3.10+ and use only the Python standard library. Do not assume a runtime exists on every user machine; run `bin/dzcto doctor` from the repo before promising generated artifacts.

## Codex Desktop

Clone the repo and install it as a local Codex plugin marketplace entry:

```bash
git clone https://github.com/chuckblake/Day-Zero-CTO.git
cd Day-Zero-CTO
bin/dzcto setup
```

Report progress in small steps:

1. Clone the repo.
2. `cd` into the repo.
3. Run `bin/dzcto setup`.
4. Confirm the setup output ends with `Day Zero CTO install is ready.`
5. Restart Codex Desktop or start a fresh session.

The setup and doctor commands print numbered progress such as `[1/3]` and `[1/18]`; relay failures with the step number.

For active Codex skill development only, symlink the shared skills into Codex's local skill directory:

```bash
python3 scripts/install_local_skills.py
```

Do not run `install_local_skills.py` for Claude Code. It is Codex Desktop-only and writes to `~/.codex/skills`.

After pulling updates:

```bash
git pull
bin/dzcto setup
```

For a complete local reinstall from an existing clone:

```bash
python3 scripts/uninstall_local.py
bin/dzcto setup
```

The uninstall helper only removes Day Zero CTO marketplace entries and symlinks that point at the current clone.

## Claude Code

Claude Code can install Day Zero CTO as a plugin marketplace:

```bash
claude plugin marketplace add chuckblake/Day-Zero-CTO
claude plugin install day-zero-cto@day-zero-cto
```

Report progress in small steps:

1. Run `claude plugin marketplace add chuckblake/Day-Zero-CTO`.
2. Run `claude plugin install day-zero-cto@day-zero-cto`.
3. Start a fresh Claude Code session.
4. Run `/help` and confirm Day Zero CTO skills appear.
5. If a local clone exists, run `python3 scripts/dzcto.py doctor`; otherwise run `dzcto doctor` from a session where the plugin `bin/` directory is on `PATH`.

Inside interactive Claude Code, the equivalent commands are:

```text
/plugin marketplace add chuckblake/Day-Zero-CTO
/plugin install day-zero-cto@day-zero-cto
```

For local development without installing:

```bash
git clone https://github.com/chuckblake/Day-Zero-CTO.git
claude --plugin-dir ./Day-Zero-CTO
```

Do not run `scripts/install_local_skills.py` for local Claude development; use `claude --plugin-dir` instead.

After pulling published updates:

```bash
claude plugin update day-zero-cto@day-zero-cto
```

Claude Code plugin install does not require Ruby. The installed `dzcto` helper command requires Python 3.10+. Older `dzcto-artifact`, `dzcto-learning`, and `dzcto-doctor` wrappers remain available for compatibility.

## Useful Helper Commands

Run these from a session where the plugin `bin/` directory is on `PATH`, or from a local clone with `bin/dzcto`.

```bash
dzcto init "<project folder>"
dzcto doctor --project "<project folder>"
dzcto check-stale "<project folder>"
dzcto collect-issue-bundle "<project folder>"
```

## Verify

Codex Desktop: ask for available Day Zero CTO skills or run a natural language prompt such as:

```text
Onboard Day Zero CTO for this startup. Use project folder `~/Documents/Acme`.
```

Claude Code: run `/help` or:

```text
/day-zero-cto:bootstrap-cto-context Onboard Day Zero CTO for this startup. Use project folder `~/Documents/Acme`.
```

## First Useful Prompt

```text
Onboard Day Zero CTO for this startup. Use project folder `<project folder>` and read-only codebase `<codebase path>`. Ask whether to complete onboarding now, including Tech Stack, Engineering Risk Review, Weekly CTO Review, CEO Update, CTO Code Review if a branch or diff exists, and seeding the first 25 learning items.
```

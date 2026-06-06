# Install Day Zero CTO For Agent Sessions

Use this when another Codex Desktop, Claude Code, Claude Desktop, or terminal-backed agent session needs to install Day Zero CTO.

## Ask First

Ask the user for these values before running Day Zero CTO work:

- Company name.
- Project or engagement name. If one name covers both, confirm that and use it for both.
- Project folder: generate options from the company/project names before asking the user to choose. Good defaults are `~/Documents/<Company>/`, `~/Documents/<Company>/<Project>/`, `~/Documents/Day Zero CTO/<Company>/`, and `~/Documents/<Project>/`. This controls the wiki directory name and location.
- Company description or company website URL.
- Optional read-only codebase paths. Multiple codebases are allowed.

Day Zero CTO writes user-facing HTML to `<project>/knowledge/wiki/` and metadata to `<project>/knowledge/wiki/.dzcto/`. Code repos are evidence sources, not the documentation destination, unless the user explicitly says otherwise. Generated wiki pages include an Arwen-style command center, KPI strip, today panel, risk register, report cards, top search, breadcrumbs, table-of-contents links, light/dark theme, and a local search index at `<project>/knowledge/wiki/search-index.json`.

Runtime note: helpers require Python 3.10+ and use only the Python standard library. Run `bin/dzcto doctor` from the repo before promising generated artifacts.

Server note: for the best generated-page experience, open the wiki through `bin/dzcto serve "<project folder>"`. The local server enables dashboard refresh and lets browser search fetch the generated JSON index reliably.

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
4. Confirm the setup output reaches the final `Next step`.
5. Restart Codex Desktop or start a fresh session.

The setup and doctor commands print numbered progress such as `[1/5]` and `[1/18]`; relay failures with the step number.

You can choose the wiki project folder and local Codex settings paths during install:

```bash
bin/dzcto setup \
  --wiki-project "$HOME/Documents/Acme CTO" \
  --company-name "Acme" \
  --company-description "Acme helps small teams manage customer onboarding." \
  --repo "$HOME/code/acme-app" \
  --repo "$HOME/code/acme-api" \
  --plugin-link "$HOME/plugins/day-zero-cto" \
  --marketplace-file "$HOME/.agents/plugins/marketplace.json"
```

For active Codex skill development only, symlink the shared skills into a chosen Codex local skill directory:

```bash
bin/dzcto setup --editable-skills --editable-skills-dir "$HOME/.codex/skills"
```

Do not run editable skill install for Claude Code. It is Codex Desktop-only and writes to a Codex skills directory.

To update an existing local Codex install from a Git clone:

```bash
bin/dzcto update
```

If editable Codex skill links were installed for development, refresh them too:

```bash
bin/dzcto update --editable-skills --editable-skills-dir "$HOME/.codex/skills"
```

`dzcto update` runs `git pull --ff-only`, refreshes the local plugin marketplace entry, optionally refreshes editable skill symlinks, and runs doctor. It refuses to pull over local edits by default. If the worktree is dirty, ask the user whether to commit/stash local edits, or run `bin/dzcto update --no-pull` only when the source folder was already updated another way.

If the user installed with custom settings paths, pass the same paths:

```bash
bin/dzcto update \
  --plugin-link "$HOME/plugins/day-zero-cto" \
  --marketplace-file "$HOME/.agents/plugins/marketplace.json" \
  --editable-skills \
  --editable-skills-dir "$HOME/.codex/skills"
```

For a complete local reinstall from an existing clone:

```bash
python3 scripts/uninstall_local.py
bin/dzcto setup
```

The uninstall helper only removes Day Zero CTO marketplace entries and symlinks that point at the current clone.

If the user installed with custom settings paths, pass the matching paths:

```bash
python3 scripts/uninstall_local.py \
  --plugin-link "$HOME/plugins/day-zero-cto" \
  --marketplace-file "$HOME/.agents/plugins/marketplace.json" \
  --editable-skills-dir "$HOME/.codex/skills"
```

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
5. Run `dzcto doctor` from a session where the plugin `bin/` directory is on `PATH`.

Inside interactive Claude Code:

```text
/plugin marketplace add chuckblake/Day-Zero-CTO
/plugin install day-zero-cto@day-zero-cto
```

For local development without installing:

```bash
git clone https://github.com/chuckblake/Day-Zero-CTO.git
claude --plugin-dir ./Day-Zero-CTO
```

After published updates:

```bash
claude plugin update day-zero-cto@day-zero-cto
```

For local `--plugin-dir` development, update the clone:

```bash
cd Day-Zero-CTO
git pull --ff-only
```

## Claude Desktop

Package an uploadable custom skill bundle:

```bash
git clone https://github.com/chuckblake/Day-Zero-CTO.git
cd Day-Zero-CTO
bin/dzcto package-claude-desktop
```

Upload `dist/day-zero-cto-claude-desktop.zip` as a custom skill where the user's Claude client and plan support custom skills.

To update the Claude Desktop custom skill bundle:

```bash
cd Day-Zero-CTO
git pull --ff-only
bin/dzcto package-claude-desktop
```

Then upload the new `dist/day-zero-cto-claude-desktop.zip`.

Claude Desktop can follow the skill procedures and produce downloadable artifacts in its workspace. Durable local filesystem wikis, stale checks, and browser refresh need a local helper with filesystem access, such as Codex Desktop, Claude Code, or a terminal running `dzcto`.

## Useful Commands

Run these from a session where the plugin `bin/` directory is on `PATH`, or from a local clone with `bin/dzcto`.

```bash
dzcto update
dzcto init "<project folder>" --company-name "<name>" --company-url "<url>" --repo "<repo path>"
dzcto refresh "<project folder>"
dzcto serve "<project folder>"
dzcto doctor --project "<project folder>"
dzcto check-stale "<project folder>"
dzcto collect-issue-bundle "<project folder>"
dzcto package-claude-desktop
```

Use `--company-description "<summary>"` instead of `--company-url "<url>"` when the user provides the description directly. Repeat `--repo` for multiple read-only codebases.

The generated wiki index has a Commands section with copy buttons. AI prompt cards copy exact prompts for Claude, Codex, or another agent with the project folder and configured read-only repo paths included. Local command cards copy deterministic `dzcto` commands, including update.

## Verify

Codex Desktop: ask for available Day Zero CTO skills or run:

```text
Onboard Day Zero CTO for this startup. Use project folder `~/Documents/Acme CTO`, company name `Acme`, company description `<short summary>`, and read-only repo `~/code/acme-app`.
```

Claude Code:

```text
/day-zero-cto:bootstrap-cto-context Onboard Day Zero CTO for this startup. Use project folder `~/Documents/Acme CTO`, company name `Acme`, company description `<short summary>`, and read-only repo `~/code/acme-app`.
```

## First Useful Prompt

```text
Onboard Day Zero CTO for this startup. Ask for the project folder, company name, company description or website URL, and one or more optional read-only codebase paths. Ask whether to complete onboarding now, including Tech Stack, Engineering Risk Review, Weekly CTO Review, CEO Update, CTO Code Review if a branch or diff exists, and seeding the first 25 learning items.
```

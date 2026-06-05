# Install Day Zero CTO For Agent Sessions

Use this when another Codex Desktop or Claude Code session needs to install Day Zero CTO.

## What To Ask For

Ask the user for two paths before running Day Zero CTO work:

- Project folder: where durable Day Zero CTO artifacts should live, usually `~/Documents/<Company>/`.
- Code repo: optional read-only evidence source, never the default destination for Day Zero CTO docs.

Day Zero CTO writes to `<project>/knowledge/wiki/`.

## Codex Desktop

Clone the repo and install it as a local Codex plugin marketplace entry:

```bash
git clone https://github.com/chuckblake/Day-Zero-CTO.git
cd Day-Zero-CTO
ruby scripts/install-local-marketplace.rb
```

Restart Codex Desktop or start a fresh session.

For active skill development, symlink the shared skills into Codex's local skill directory:

```bash
ruby scripts/install-local-skills.rb
```

After pulling updates:

```bash
git pull
ruby scripts/install-local-marketplace.rb
```

## Claude Code

Claude Code can install Day Zero CTO as a plugin marketplace:

```bash
claude plugin marketplace add chuckblake/Day-Zero-CTO
claude plugin install day-zero-cto@day-zero-cto
```

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

After pulling published updates:

```bash
claude plugin update day-zero-cto@day-zero-cto
```

## Verify

Codex Desktop: ask for available Day Zero CTO skills or run a natural language prompt such as:

```text
Bootstrap Day Zero CTO context for this startup. Use project folder `~/Documents/Acme`.
```

Claude Code: run `/help` or:

```text
/day-zero-cto:bootstrap-cto-context Bootstrap Day Zero CTO context for this startup. Use project folder `~/Documents/Acme`.
```

## First Useful Prompt

```text
Bootstrap Day Zero CTO context for this startup. Use project folder `<project folder>` and read-only code repo `<code repo>`.
```

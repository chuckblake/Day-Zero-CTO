---
name: Bug report
about: Report an install, skill, or helper command problem.
title: "[Bug]: "
labels: bug
assignees: ""
---

## What happened?

Describe the problem and what you expected instead.

## Environment

- Agent/client: Codex Desktop / Claude Code / other
- OS:
- Python version:
- Day Zero CTO version, if known:

## Reproduction

1.
2.
3.

## Diagnostics

Run `dzcto doctor` from a session where the plugin `bin/` directory is on `PATH`, or `bin/dzcto doctor` from a local clone, and paste the output here.

If this involves a project wiki, run:

```bash
dzcto collect-issue-bundle "<project folder>"
```

Attach the generated zip if it does not contain private information you cannot share.

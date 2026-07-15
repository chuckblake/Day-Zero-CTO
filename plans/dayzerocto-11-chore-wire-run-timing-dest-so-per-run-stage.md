---
title: "DAYZEROCTO-11: Wire run-timing dest so per-run stage timing collects here"
status: planned
priority: p2
created: 2026-07-15
effort: small
tags: [config, run-timing, cb-workflow]
issue_id: DAYZEROCTO-11
---

# DAYZEROCTO-11: Wire run-timing dest so per-run stage timing collects here

## Goal
Give this repo's cb runs a concrete `timing.dest` so the CBW-63 run-timing system
stops silently collecting nothing. Config-only: add a `timing:` line to `.claude/cb.yml`
pointing at the repo's vault logs dir, and ensure that dir exists.

## Context
`run-timing` reads `cfg("timing","enabled", default: true)` and `cfg("timing","dest", default: "")`.
This repo has no `timing:` key, so it is timing-enabled with an empty dest — every event call
is a fail-open no-op and preflight warns "timing.dest is empty". The fix mirrors what cb-workflow
and GetMusic already do and matches the CBW-70 recommendation `<vault>/cb-dev/<project>/logs`.

## Files
- Modify: `.claude/cb.yml` — add a `timing:` entry with `enabled: true` and the absolute `dest`.
- Create (if missing): `/Users/chuckblake/Documents/Code/chuck-vault/cb-dev/dzcto/logs` (dir).

## Plan
- [ ] Add `timing: { enabled: true, dest: /Users/chuckblake/Documents/Code/chuck-vault/cb-dev/dzcto/logs }` to `.claude/cb.yml` (near the `worklog:`/`hooks:` lines).
- [ ] Ensure the logs dir exists (`mkdir -p` the dest).
- [ ] Verify preflight no longer emits the "timing.dest is empty" warning.
- [ ] Confirm `run-timing` resolves the dest (a subsequent event/readme call writes there).

## Open Questions
None. Path and shape are fixed by the issue ACs and the run-timing/preflight contract.

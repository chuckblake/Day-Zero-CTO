---
title: "Wiring a new dzcto engine flag — thread it through all three CLI sites"
date: 2026-07-10
category: conventions
module: dzcto-cli
problem_type: convention
component: tooling
severity: medium
applies_when:
  - "Adding a new flag to the dzcto_artifact.py engine argparse"
  - "A dzcto artifact invocation errors with argparse 'unrecognized arguments'"
  - "Adding a best-effort side effect to a CLI whose STDOUT a skill parses"
symptoms:
  - "Both dzcto artifact --flag and the python3 scripts/dzcto.py artifact fallback fail with argparse 'unrecognized arguments'"
  - "A flag works when the engine is called directly but is silently ignored through the dzcto wrapper"
related_components: [development_workflow, documentation]
tags: [dzcto, cli, argparse, wrapper, passthrough, engine-flag, whitelist]
---

# Wiring a new dzcto engine flag — thread it through all three CLI sites

## Context

`scripts/dzcto.py` exposes an `artifact` subcommand that is a **thin wrapper**, not a passthrough. It does not exec `dzcto_artifact.py` with the user's raw argv. Instead it declares its own argparse subparser (a curated whitelist of flags) and then, in the dispatch body, **rebuilds** the argument list by hand before calling `run_script("dzcto_artifact.py", artifact_args)`. There is no `parse_known_args` passthrough and no `*extra` capture — an engine flag that is not explicitly whitelisted in *both* wrapper spots is invisible to the wrapper, and argparse rejects it as an "unrecognized argument."

That design creates a three-site wiring trap. Shipping the DAYZEROCTO-9 `--open` flag (after a report is written, best-effort open the rendered self-contained HTML in the default browser and print a Cmd/Ctrl+P "Save as PDF" share recipe) required declaring/handling the flag in the engine, re-declaring it on the wrapper subparser, and re-appending it in the wrapper's arg-list rebuild. Miss any one and a real user path breaks.

## Guidance

### Rule 1 — Wire a new engine flag in all THREE sites

A single new engine flag must appear in three places (confirmed line refs for `--open`):

**(a) Engine argparse** — `scripts/dzcto_artifact.py:6267`:
```python
parser.add_argument("--open", action="store_true", help="Open the rendered report and print a share recipe")
```

**(b) Wrapper subparser** — `scripts/dzcto.py:2336` (inside the `artifact = sub.add_parser("artifact", ...)` block):
```python
artifact.add_argument("--open", action="store_true", help="Open the rendered report and print a share recipe")
```

**(c) Wrapper passthrough / arg-list rebuild** — `scripts/dzcto.py:2524-2525` (inside `if args.command == "artifact":`):
```python
if args.open:
    artifact_args.append("--open")
return run_script("dzcto_artifact.py", artifact_args)
```

The builder starts from a fixed base (`artifact_args = ["--kind", args.kind, "--title", args.title]`) and conditionally `extend`/`append`s each whitelisted flag. This is the "whitelist, not passthrough" mechanism: any flag not added here never reaches the engine.

### Rule 2 — Side-effect output goes to STDERR, never STDOUT

The engine's STDOUT contract is a single line at `scripts/dzcto_artifact.py:6469`:
```python
print(written_report or wiki_root / "index.html")
```
The skill agent parses this one line to learn the report path, so all open/share chatter is emitted with `file=sys.stderr` in `emit_open_and_share`. Printing to STDOUT would corrupt the path the skill reads.

### Rule 3 — Gate-and-swallow for best-effort side effects

The open is gated on both a written report and the opt-in flag, and the browser launch is wrapped so no backend failure can break the run — `scripts/dzcto_artifact.py:6470`:
```python
if written_report and args.open:
    emit_open_and_share(written_report)
```
Inside `emit_open_and_share`, `webbrowser.open(...)` sits in `try/except Exception`, reporting failure to stderr rather than raising.

### Rule 4 — Provide an env-var test seam for un-mockable side effects

`DZCTO_NO_OPEN` short-circuits the launch before any browser spawn while still printing the recipe — `scripts/dzcto_artifact.py:6243-6244`:
```python
if os.environ.get("DZCTO_NO_OPEN"):
    return
```
This lets CI exercise the `--open` path end-to-end without spawning a browser.

## Why This Matters

- Skip site (b) or (c) and both user surfaces break: the thin `dzcto artifact --open` CLI (b fails at wrapper parse; c silently drops the flag so the engine never opens) and the `python3 scripts/dzcto.py artifact` fallback path.
- Print open/share text to STDOUT instead of STDERR and you corrupt the single-line path contract at `:6469` — the skill agent parses garbage instead of the report path.
- Omit the gate-and-swallow and a flaky or headless browser backend turns a best-effort convenience into a hard failure of the whole report run.
- Omit the `DZCTO_NO_OPEN` seam and CI (or any headless run exercising `--open`) actually spawns a browser.

## When to Apply

- Adding **any** new engine flag to `scripts/dzcto_artifact.py` that should be reachable through the `dzcto` wrapper — always wire all three sites; the wrapper will not forward it for you.
- Adding a best-effort side effect (open, notify, upload, copy-to-clipboard) to a CLI whose STDOUT is machine-parsed by a skill: keep STDOUT clean, gate the side effect behind opt-in plus precondition, swallow its exceptions, and add an env-var no-op seam for CI.

## Examples

- **`--open` across the three sites:** engine argparse `dzcto_artifact.py:6267` → wrapper subparser `dzcto.py:2336` → wrapper passthrough `dzcto.py:2524-2525`. Removing the last one alone reproduces the classic "works in the engine, silently ignored via the wrapper" failure.
- **`DZCTO_NO_OPEN` seam:** setting the env var makes `emit_open_and_share` print the "ready to share" and "Save as PDF" recipe lines to stderr and return before `webbrowser.open`, so tests assert the recipe without a browser ever launching.
- **Helper-computes / agent-narrates (supporting pattern):** the mechanical open and the fixed print-to-PDF recipe live entirely in the Python helper (`emit_open_and_share`), deterministic and headless-safe; the SKILL.md only narrates the recipe. Here the justification is reliability/determinism, not anti-hallucination.

## Related

- `../architecture-patterns/helper-computes-agent-narrates-2026-07-03.md` — the pattern this reinforces: mechanical open plus fixed PDF recipe live in the helper; SKILL.md only narrates. New wrinkle here: recipe/notice go to STDERR to protect the single-line STDOUT contract the skill parses, with `DZCTO_NO_OPEN` as a test seam.
- `../architecture-patterns/match-command-config-model-to-its-consumers-2026-07-09.md` — sibling dzcto-CLI change (DAYZEROCTO-7). Contrast: that one added an engine subcommand directly to `dzcto.py`; this one threads a flag through the `artifact` **wrapper**, which rebuilds/whitelists args rather than forwarding them — hence the three-site wiring.

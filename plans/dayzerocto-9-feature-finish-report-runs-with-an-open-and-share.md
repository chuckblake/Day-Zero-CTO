---
title: "DAYZEROCTO-9: Finish report runs with an open-and-share step"
type: feat
status: active
priority: p2
created: 2026-07-09
effort: small
tags: [ceo-report, skills, artifact, cli, share]
linear_id: DAYZEROCTO-9
---

# DAYZEROCTO-9: Finish report runs with an open-and-share step

## Goal

End a CEO report run by opening the rendered self-contained HTML in the default browser and emitting a concise print-to-PDF share recipe alongside the file path, so a completed run actually reaches the CEO instead of stopping at a filesystem path. The business contract (acceptance criteria) lives on the backlog issue `DAYZEROCTO-9`; this plan owns only the engineering response.

---

## Problem Frame

Both CEO report skills (`skills/dzcto-ceo-report`, `skills/dzcto-ceo-report-weekly`) end by rendering the artifact and printing the file path with a brief summary — the CTO is then on their own to find, open, and send it. The artifact is already share-ready: fully self-contained HTML with `@media print` CSS (`scripts/dzcto_artifact.py:5227`). The missing piece is a deterministic finishing step that (a) opens the rendered HTML and (b) prints a share recipe.

The prior learning `docs/solutions/architecture-patterns/helper-computes-agent-narrates-2026-07-03.md` governs where the behavior lives: mechanical, deterministic actions belong in the Python helper (`scripts/dzcto_artifact.py`); the SKILL.md agent only narrates. Opening a browser and printing a fixed recipe are mechanical side effects — putting them in the helper (behind an opt-in `--open` flag) makes the behavior reliable and testable rather than dependent on the agent remembering to shell out `open`. The justification here is **reliability/determinism**, not the anti-hallucination split.

---

## Requirements Trace

- R1. A completed report run opens (or offers to open) the rendered HTML in the default browser. (owned by issue AC)
- R2. The run ends with a concise share recipe (e.g. a print-to-PDF one-liner) alongside the file path. (owned by issue AC)
- R3. The change addresses the North Star funnel gap — "automated runs whose report nobody opens do not count." (owned by issue strategy grounding)
- R4 (engineering constraint). The two SKILL.md `## Report JSON schema (v1)` blocks stay byte-identical (enforced by `TestSkillSchemaLockstep`).
- R5 (engineering constraint). No external network dependency; the artifact stays a local self-contained file; browser-open is best-effort and never blocks or crashes the render.
- R6 (engineering constraint). The existing single-line stdout path contract (`scripts/dzcto_artifact.py:6449`) is preserved — the agent reads that line as "the path."

---

## Scope Boundaries

- In: an opt-in end-of-run open/share step delivered as a helper flag (`--open`) on the `artifact` command; the printed share-recipe text; a lockstep step-8 instruction in both CEO report skills; tests for the flag and the skill text.
- Out: auto-creating issues from audits; scheduling recurring runs; emailing/uploading/publishing the artifact anywhere; adding an in-page "Print / Save as PDF" button to the HTML (the `@media print` CSS + browser Cmd/Ctrl+P is the recipe); changing what the report contains.

---

## Context & Research

### Relevant Code and Patterns

- `scripts/dzcto_artifact.py:6237` — `main()` argparse for the `artifact` command; flags are declared explicitly here.
- `scripts/dzcto_artifact.py:6446-6450` — end of the render path: `written_report = report_path`, then `print(written_report or wiki_root / "index.html")` (line 6449) is the **sole stdout line** the SKILL agent parses as the path. New output must not disturb this.
- `scripts/dzcto_artifact.py:5227` — `@media print` CSS already present; this is the "print-to-PDF machinery" the recipe points at (open in browser → Cmd/Ctrl+P → Save as PDF).
- `scripts/dzcto.py:2327-2335` — the `artifact` subparser. **Non-obvious wiring:** `scripts/dzcto.py:2509-2523` does not forward unknown args; it whitelists each flag and rebuilds `artifact_args`. Both the installed `dzcto artifact` shim and the `python3 scripts/dzcto.py artifact` fallback route through here, so `--open` must be added to this subparser and appended in the passthrough — otherwise both entry points error with "unrecognized arguments."
- `skills/dzcto-ceo-report/SKILL.md` and `skills/dzcto-ceo-report-weekly/SKILL.md` — step 7 renders via `dzcto artifact ...` (fallback `python3 scripts/dzcto.py artifact ...`); then `## Report JSON schema (v1)`; then `## Standards`. The Standards list currently ends with "End with the generated report path and a brief summary." (weekly: line 102; ad_hoc: line 101). Everything above the schema header differs between the two skills already; only the schema block is byte-identical.
- `tests/test_dzcto_artifact.py:866` — `run_cli(*cli_args)` subprocess harness (captures stdout+stderr, `text=True`). `tests/test_dzcto_artifact.py:877` — `generate(data, title, *extra)` renders a ceo-updates artifact and accepts extra flags. Follow this to test `--open`.
- `tests/test_dzcto_artifact.py:785` — `TestSkillSchemaLockstep` slices the text between `## Report JSON schema (v1)` and the next `## ` heading and asserts byte-identity. `tests/test_dzcto_artifact.py:802` — `TestSkillBadNewsInstructions` is the model for lowercased-substring skill-text assertions.

### Institutional Learnings

- `docs/solutions/architecture-patterns/helper-computes-agent-narrates-2026-07-03.md` — mechanical work in the helper, narration in the SKILL; warn-only / best-effort side effects that degrade rather than block.

### External References

- None. The open uses only the Python stdlib `webbrowser` module (cross-platform, no network); no external research warranted.

---

## Key Technical Decisions

- **Helper flag, not agent shell-out.** Deliver the behavior as an opt-in `--open` flag on the `artifact` command rather than a SKILL instruction to run `open <path>`. Rationale: deterministic, testable, works headlessly, avoids a per-run permission prompt for the agent. Opt-in so non-CEO artifact callers are unaffected (only the two CEO skills pass `--open`).
- **Browser-open via stdlib `webbrowser`, best-effort.** Open `report_path` as a `file://` URI via `pathlib.Path.as_uri()` and `webbrowser.open(...)`, wrapped so any exception (no display, no browser, sandbox) is swallowed to stderr and never affects the exit code or the stdout path. No network.
- **Open + recipe fire only when a report was actually written.** Both the browser-open and the share recipe are gated on `written_report` being truthy; the bare `index.html` fallback (no report rendered) neither opens nor prints a recipe. This keeps U1's behavior single-valued.
- **No-launch test seam: `DZCTO_NO_OPEN` env gate.** When `--open` is set and a report was written, the share recipe is printed, but the actual `webbrowser.open()` call is skipped when `DZCTO_NO_OPEN` is truthy. Tests set it via `mock.patch.dict(os.environ, {"DZCTO_NO_OPEN": "1"})` — the `run_cli`/`generate` subprocess harness passes no `env=`, so the child inherits the parent's `os.environ` and no harness change is needed (add `import os` / `from unittest import mock` to the test module, which currently imports neither). Chosen over monkeypatching the engine because the harness runs the CLI as a subprocess; an env gate is the natural seam.
- **Recipe + open notice go to stderr; stdout stays the single path line.** Preserves R6. The SKILL agent still reads the path from stdout; the recipe/notice are advisory diagnostics on stderr that the agent relays.
- **Step-8 placement preserves the lockstep.** The new open/share instruction is added as step 8 (after the step-7 render block) — i.e. *before* `## Report JSON schema (v1)`. Nothing new is inserted between the schema header and `## Standards`, so `TestSkillSchemaLockstep`'s slice is untouched. The step-8 prose is identical in both skills.
- **Retire the stale finish line.** The Standards line "End with the generated report path and a brief summary." is replaced with one that references the opened report + share recipe, so the two skills don't carry two competing "how to finish" instructions.

---

## Open Questions

### Resolved During Planning

- Auto-open vs. "offer to open"? — The issue AC explicitly allows either. Resolved to **auto-open on `--open`, best-effort**, because a report run's whole point is that the artifact gets seen; best-effort + swallowed failures means the auto-open never harms a headless run (where it simply no-ops or is skipped via `DZCTO_NO_OPEN`), and the durable half of the AC — the share recipe — always prints regardless.
- Where does `--open` need wiring? — Three sites: the engine argparse in `dzcto_artifact.py`, the `artifact` subparser in `dzcto.py`, and the whitelist passthrough in `dzcto.py` (see U1/U2).
- Does the recipe risk breaking the path contract? — No, provided it is emitted to stderr (or strictly after the stdout path line). Chosen: stderr.

### Deferred to Implementation

- Exact recipe wording and exact stderr helper-function name — decided at implementation; recipe should name the file, the "open in a browser → Cmd/Ctrl+P → Save as PDF" path, and stay one to three short lines. If a materially new requirement surfaces, add it as a `ruby ~/.claude/skills/cb-lib/backlog comment DAYZEROCTO-9 "..."` note rather than a new AC here.

---

## Implementation Units

- U1. **Add `--open` to the artifact engine (open + share recipe, best-effort)**

**Goal:** Give `scripts/dzcto_artifact.py`'s `artifact` command an opt-in `--open` flag that, after the report is written, prints a share recipe to stderr and best-effort opens the rendered HTML in the default browser — without disturbing the stdout path line.

**Requirements:** R1, R2, R5, R6

**Dependencies:** None

**Files:**
- Modify: `scripts/dzcto_artifact.py`
- Test: `tests/test_dzcto_artifact.py`

**Approach:**
- Add `parser.add_argument("--open", action="store_true", help="Open the rendered report in the default browser and print a share recipe")` near the other `artifact` flags (`~:6237-6260`).
- After the existing `print(written_report or wiki_root / "index.html")` at `:6449` (keep that stdout line exactly as the sole stdout output), when `args.open` is set: emit the share recipe to `sys.stderr`, then attempt the browser open. Factor the recipe + open into a small helper (e.g. `emit_open_and_share(report_path)`).
- Browser open: compute `report_path.as_uri()` (`report_path` is absolute — derived from a resolved `wiki_root` — so `as_uri()` is always valid, incl. titles with spaces); skip the actual `webbrowser.open(uri)` when `os.environ.get("DZCTO_NO_OPEN")` is truthy; wrap the call in try/except so any failure is logged to stderr and swallowed (no crash, no exit-code change). Import `webbrowser` (stdlib) at module top with the other imports.
- Recipe text (stderr): name the file, and give the print-to-PDF one-liner (open in a browser, then Cmd/Ctrl+P → "Save as PDF"). Keep it to a few short lines.
- Gate on `written_report`: only fire open + recipe when a report was actually written; the bare `index.html` fallback does neither (matches the KTD decision, keeps behavior single-valued).
- Best-effort caveat to note in the helper: the try/except swallows *crashes* but not *blocking*. `webbrowser.GenericBrowser.open` does `return not p.wait()`, so a user with `BROWSER` set to a foreground command could hang the run. The default macOS backend (`MacOSXOSAScript`) is non-blocking, so realistic CTO runs are unaffected; leave a one-line comment rather than adding threading.

**Patterns to follow:**
- `docs/solutions/architecture-patterns/helper-computes-agent-narrates-2026-07-03.md` — best-effort side effect that degrades, never blocks.
- Existing stderr diagnostics in this file (e.g. the `--date` disagreement warning at `:6401`, schema warnings at `:6389`) as the model for advisory stderr output.

**Test scenarios:**
- Happy path: `generate(..., "--open")` under `mock.patch.dict(os.environ, {"DZCTO_NO_OPEN": "1"})` → stdout is still exactly the one report-path line (unchanged contract); stderr contains the share recipe (assert on a stable substring, e.g. "Save as PDF"). No browser spawns.
- Edge case: without `--open`, behavior is byte-identical to today — no recipe on stderr, stdout is the path.
- Error/best-effort: with `--open` and `DZCTO_NO_OPEN` unset but no usable browser (rely on the swallow path; can be exercised by pointing `BROWSER` at a non-existent command or asserting the process still exits 0 and prints the path) → exit code 0, path still on stdout. Keep this test env-safe so it never actually launches a browser in CI (prefer `DZCTO_NO_OPEN=1` for the deterministic assertions and a separate, lightweight no-crash assertion).
- Edge case: `report_path.as_uri()` is well-formed for a path with spaces (the slugified titles can contain them pre-slug) — assert no exception.

**Verification:**
- `python3 -m pytest tests/test_dzcto_artifact.py` passes; the stdout path line is unchanged with and without `--open`; the recipe appears only with `--open`.

---

- U2. **Thread `--open` through the `dzcto.py` artifact wrapper**

**Goal:** Make `dzcto artifact --open ...` and the `python3 scripts/dzcto.py artifact --open ...` fallback actually pass `--open` down to the engine, since the wrapper whitelists flags rather than forwarding them.

**Requirements:** R1, R2 (delivery path)

**Dependencies:** U1

**Files:**
- Modify: `scripts/dzcto.py`
- Test: `tests/test_dzcto_artifact.py` (or a sibling test that exercises `scripts/dzcto.py artifact`)

**Approach:**
- Add `artifact.add_argument("--open", action="store_true", ...)` to the `artifact` subparser (`scripts/dzcto.py:2327-2335`).
- In the `if args.command == "artifact":` block (`:2509-2523`), append `--open` to `artifact_args` when `args.open` is set, before `run_script("dzcto_artifact.py", artifact_args)`.

**Patterns to follow:**
- The existing conditional-append style in the same block (`if args.date: artifact_args.extend([...])`).

**Test scenarios:**
- Happy path: invoke `scripts/dzcto.py artifact --open ...` (with `DZCTO_NO_OPEN=1`) → exits 0, stdout carries the path line, stderr carries the recipe — proving the flag reached the engine through the wrapper.
- Edge case: `scripts/dzcto.py artifact ...` without `--open` still works and produces no recipe (no regression to the wrapper's existing flags).

**Verification:**
- Running the wrapper form with `--open` produces the same recipe/stderr behavior as calling `dzcto_artifact.py` directly.

---

- U3. **Add the lockstep open/share step to both CEO report skills**

**Goal:** Both skills instruct the agent to render with `--open`, add a step-8 open/share narration, and drop the stale "end with the path" Standards line — with the byte-identical schema block untouched.

**Requirements:** R1, R2, R3, R4

**Dependencies:** U1, U2

**Files:**
- Modify: `skills/dzcto-ceo-report/SKILL.md`
- Modify: `skills/dzcto-ceo-report-weekly/SKILL.md`
- Test: `tests/test_dzcto_artifact.py`

**Approach:**
- In step 7's render commands (both the `dzcto artifact` block and the `python3 scripts/dzcto.py artifact` fallback), add the `--open` flag in both skills.
- Add a new **step 8** immediately after the step-7 render block and *before* `## Report JSON schema (v1)`: instruct the agent that the render opened the report in the browser and to relay the printed share recipe to the user alongside the path. This step-8 prose must be identical in both files.
- Replace the Standards line "End with the generated report path and a brief summary." with one that references the opened report and the share recipe (e.g. "End by relaying the generated report path, that it was opened in the browser, and the printed share recipe."). This lives in `## Standards` (which already differs between the two skills), so wording can be shared but does not have to be byte-identical.
- Do not add or move any `## ` heading between `## Report JSON schema (v1)` and `## Standards`. Leave the schema block bytes untouched in both files.

**Patterns to follow:**
- The existing lockstep discipline: shared step wording added identically to both skills; `docs/ceo-report-template.md` remains canon.

**Test scenarios:**
- Happy path (new text-assertion test, modeled on `TestSkillBadNewsInstructions`): both skills contain `--open` and a share-recipe cue (e.g. lowercased substring "save as pdf" or "share recipe") somewhere after the step-7 render.
- Regression: `TestSkillSchemaLockstep` still passes (schema blocks byte-identical) — the step-8 insertion is outside its slice.
- Coherence: neither skill still contains the old "End with the generated report path and a brief summary." line (assert absence), so there is one finish instruction, not two.

**Verification:**
- `python3 -m pytest tests/test_dzcto_artifact.py` green, including the schema lockstep and the new skill-text assertions.

---

## System-Wide Impact

- **Interaction graph:** `--open` is opt-in; only the two CEO report skills pass it. Other `artifact` callers (`dzcto.py` codebase-accountability path at `:604-616`, snapshot at `:1304`) are unaffected because they never set `--open`.
- **Error propagation:** browser-open failures are swallowed to stderr; the render's exit code and stdout path are unchanged. A malformed/absent browser degrades to "recipe printed, nothing opened."
- **API surface parity:** the flag must be wired at both the engine (`dzcto_artifact.py`) and the wrapper (`dzcto.py`) because the wrapper whitelists flags — this is the parity trap the plan exists to prevent.
- **Unchanged invariants:** the single-line stdout path contract (`:6449`) and the byte-identical `## Report JSON schema (v1)` block are explicitly preserved; no report content changes.

---

## Risks & Dependencies

| Risk | Mitigation |
|------|------------|
| Tests spawn a real browser in CI | `DZCTO_NO_OPEN` env gate skips the actual `webbrowser.open()`; deterministic assertions run with it set. |
| Recipe output pollutes the stdout path the agent parses | Recipe + open notice go to stderr; stdout stays the single path line (assert in tests). |
| Step-8 insertion breaks the schema lockstep | Insert before `## Report JSON schema (v1)`; add no heading inside the schema→Standards span; regression-covered by `TestSkillSchemaLockstep`. |
| `--open` added to the engine but not the wrapper (or vice-versa) → "unrecognized arguments" | U2 wires both the subparser and the passthrough; a wrapper-form test exercises the full path. |
| Two competing finish instructions in the skills | U3 removes the stale Standards line and asserts its absence. |

---

## Sources & References

- Backlog issue: `DAYZEROCTO-9` (owns the acceptance criteria and strategy grounding)
- Related code: `scripts/dzcto_artifact.py` (`main`/`:6449`/`:5227`), `scripts/dzcto.py` (`:2327`, `:2509`), `skills/dzcto-ceo-report/SKILL.md`, `skills/dzcto-ceo-report-weekly/SKILL.md`
- Related tests: `tests/test_dzcto_artifact.py` (`TestSkillSchemaLockstep`, `TestSkillBadNewsInstructions`, `run_cli`/`generate` harness)
- Institutional learning: `docs/solutions/architecture-patterns/helper-computes-agent-narrates-2026-07-03.md`
- Canon: `docs/ceo-report-template.md`

## Decisions

### Bump all release surfaces to 0.9.2 — 2026-07-10

The active CEO report skills changed, so the Codex, Claude, Claude marketplace, and helper/footer versions move together under the repo release rule. Leaving any surface at 0.9.1 was rejected because installed plugin consumers and generated reports would disagree about which release produced the new behavior.

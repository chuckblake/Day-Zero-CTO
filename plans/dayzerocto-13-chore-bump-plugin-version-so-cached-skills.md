---
title: "DAYZEROCTO-13: Bump plugin version so cached skills pick up the since_last_report change"
status: planned
priority: p2
created: 2026-07-23
effort: small
tags: [release, versioning, plugin-cache, plumbing]
issue_id: DAYZEROCTO-13
---

# DAYZEROCTO-13: Bump plugin version so cached skills pick up the since_last_report change

## Goal

Move every declared plugin version from `0.9.2` to `0.9.3` so the Claude Code plugin
cache invalidates and picks up the `since_last_report` window changes merged in
DAYZEROCTO-12. Release plumbing only — no window logic or skill content changes.

## Prior Solutions

- `docs/solutions/conventions/dzcto-engine-flag-three-site-wiring-2026-07-10.md` — the closest
  analogue: a single logical change that is only correct when landed in *every* coordinated site;
  missing one site fails silently rather than loudly. Same shape here, with 5 sites instead of 3.
- `docs/solutions/conventions/skill-md-schema-lockstep-test-2026-07-03.md` — the repo's convention
  for mechanically enforcing values that must move together. Notes that "remember to also update
  the copy in X" is a test asking to be written; see Open Questions (deliberately out of scope here).

## Context

The version is pinned in **5 fields across 4 files**, which is more than the issue's AC list
enumerates. The catch-all in AC#2 ("any other file that pins the plugin version") covers the
extra one. Two independent sources confirm the full set:

- `AGENTS.md:41` — "When releasing plugin-facing changes, bump both `.codex-plugin/plugin.json`
  and `.claude-plugin/plugin.json`; if the Claude marketplace entry has a version, bump it too."
- The prior bump commit `33b6f29` (DAYZEROCTO-9) touched all four files together, and its plan
  records the rule explicitly: "the Codex, Claude, Claude marketplace, and helper/footer versions
  move together under the repo release rule."

Not every field serves the same purpose, and the plan should stay honest about that:

- `.claude-plugin/plugin.json` + `.claude-plugin/marketplace.json` are the **cache key** — these are
  what actually deliver the issue's goal (cache invalidation).
- `.codex-plugin/plugin.json` keeps the Codex install in step.
- `scripts/dzcto_common.py::TOOL_VERSION` is the rendered footer / Provenance version
  (`dzcto_artifact.py:622`, and the `toolVersion` field in sidecar metadata). It is bumped for
  release-rule consistency, **not** for cache invalidation. `dzcto version` also prints it.

Nothing mechanical enforces the five stay in sync: no test asserts version equality, and the repo
has **no CI workflows** (`.github/` contains only issue templates). So a partial bump would pass
every automated check — the verification below has to be done deliberately.

## Files

- Modify: `.claude-plugin/plugin.json` — `version` (1 field)
- Modify: `.claude-plugin/marketplace.json` — top-level `version` **and** the plugin-entry `version` (2 fields)
- Modify: `.codex-plugin/plugin.json` — `version` (1 field)
- Modify: `scripts/dzcto_common.py` — `TOOL_VERSION` (1 field, line 19)

## Tests

No new test is added (see Open Questions). Verification is by command:

- Test: `grep -rn '0\.9\.2' . --exclude-dir=.git` returns **no hits outside `plans/`** — the only
  legitimate remaining matches are historical references in archived plan files.
- Test: `grep -rn '0\.9\.3' . --exclude-dir=.git` shows exactly the 5 fields above.
- Test: `python3 -m json.tool` parses all three manifests cleanly after editing.
- Test: `python3 -m unittest discover -s tests` is green. No fixture currently pins `0.9.2`
  (verified by grep), but `TOOL_VERSION` renders into the artifact footer and provenance JSON and
  DAYZEROCTO-10 added a golden test — if a golden/provenance fixture turns out to pin the old
  version, update the fixture to match. That is still plumbing and stays in scope.
- Test: `dzcto doctor` still passes (AC#4).
- Test: `dzcto version` prints `0.9.3`.

## Plan

- [ ] Bump `version` to `0.9.3` in `.claude-plugin/plugin.json`.
- [ ] Bump **both** `version` fields to `0.9.3` in `.claude-plugin/marketplace.json` (top-level and the plugin entry).
- [ ] Bump `version` to `0.9.3` in `.codex-plugin/plugin.json`.
- [ ] Bump `TOOL_VERSION` to `"0.9.3"` in `scripts/dzcto_common.py`.
- [ ] Run the grep sweeps and confirm no `0.9.2` remains outside `plans/`, and that all 5 new fields are present.
- [ ] Run `python3 -m unittest discover -s tests`; update a golden/provenance fixture only if one pins the old version.
- [ ] Run `dzcto doctor` and `dzcto version` to confirm both are healthy and report `0.9.3`.

## Decisions

### Bumped `TOOL_VERSION` even though the ACs don't name it — 2026-07-23

The issue's AC list enumerates the three JSON manifests explicitly and covers the rest with a
catch-all ("any other file that pins the plugin version"). `scripts/dzcto_common.py::TOOL_VERSION`
is that other file. Bumping it was chosen over leaving it at `0.9.2` because the repo's release
rule requires the surfaces move together — recorded in the DAYZEROCTO-9 plan ("the Codex, Claude,
Claude marketplace, and helper/footer versions move together") and demonstrated by commit `33b6f29`,
which touched all four files. Leaving it behind would make `dzcto version` and the artifact footer
disagree with the installed plugin about which release produced the behavior.

### Did not add a version-lockstep test — 2026-07-23

Nothing mechanical keeps the 5 fields in sync, and this issue exists because a prior merge forgot
the bump, so a lockstep test is genuinely warranted. It was rejected *here* because the issue's
Scope names exactly two deliverables and constrains the work to "release plumbing only" — a new
test would be a third. Recorded as a backlog comment on DAYZEROCTO-13 recommending a follow-up
issue, leaving the widen/don't-widen call to the operator rather than taking it unilaterally on a
headless run.

## Open Questions

- **Cache-refresh verification (AC#3) is operator-side.** The repo change only makes invalidation
  possible; confirming the refreshed cache matches the repo requires
  `/plugin marketplace update day-zero-cto` (Claude Code) or `bin/dzcto update` (Codex) on the
  operator's machine. The issue's Scope explicitly accepts this as a manual step, so it is not a
  blocker for the PR — but the AC cannot be closed from CI.
- **A version-lockstep test is recommended but deliberately out of scope.** The issue exists
  precisely because a prior merge forgot the bump, and nothing mechanical prevents a recurrence.
  The issue's Scope names only two deliverables and constrains this to "release plumbing only", so
  adding a test here would be a third. Filed as a backlog comment on DAYZEROCTO-13 recommending a
  follow-up issue; the widen/don't-widen call belongs to the operator.

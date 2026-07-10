---
title: "DAYZEROCTO-8: Prune dead non-CEO-report machinery from renderer and CLI"
status: planned
priority: p2
created: 2026-07-10
effort: medium
tags: [ceo-report, dead-code, refactor, cli, renderer, dzcto-py, dzcto-artifact]
linear_id: DAYZEROCTO-8
---

# DAYZEROCTO-8: Prune dead non-CEO-report machinery from renderer and CLI

## Goal

Delete the unshipped rendering and CLI surface in `scripts/dzcto.py` and `scripts/dzcto_artifact.py`
so the CEO report path (`dzcto init` + `dzcto evidence` + `dzcto artifact --kind ceo-updates`) is the
whole maintained product surface — with zero behavior change to CEO report output and the full test
suite green at every commit. The business contract lives in `DAYZEROCTO-8`; this plan owns only the
engineering response.

---

## Problem Frame

`scripts/dzcto_artifact.py` (6,454 lines) and `scripts/dzcto.py` (2,547 lines) still carry renderers
for artifact kinds and CLI subcommands that no shipped skill can invoke. Only three skills ship —
`dzcto-init`, `dzcto-ceo-report`, `dzcto-ceo-report-weekly` — and between them they call exactly
three CLI commands (`init`, `evidence`, `artifact --kind ceo-updates`). Everything reachable only from
the retired/hidden surface is dead weight that every change to the report path has to navigate. The
repo's own guidance (`docs/solutions/best-practices/audit-for-dead-but-complete-machinery-2026-07-03.md`)
prescribes exactly the grep-callers audit this plan is built on.

**Discovery corrections (verified against source this session; recorded as a comment on
`DAYZEROCTO-8`):** the issue body's references are stale in three ways —
- The named kinds `command-center` / `onboarding` / `risk-register` are **not** real artifact kinds
  (zero matches in `scripts/`). The real dead `REPORT_FOLDERS` kinds are `snapshot`, `tech-stack`,
  `engineering-risk`, `codebase-accountability`, `weekly-reviews`; the issue's "risk-register" maps to
  the orphaned risk/decision-registry cluster.
- There are **9** dead `SUPPRESS` subcommands, not 7 — and `evidence` is `SUPPRESS`-hidden but **LIVE**
  (do not prune; a test guards its hidden-ness).
- Line numbers drifted (`render_structured_report` is at `scripts/dzcto_artifact.py:2011`, not 6164).

**DAYZEROCTO-7 coordination — resolved (verified against merged commit `99461ad`):** the salvage the
issue asks us to coordinate is superseded. DAYZEROCTO-7 shipped its own `build_evidence_data` and does
**not** use `commit_files` / `subsystem_for` / `build_codebase_accountability_data`; those feed only the
dead `codebase-accountability` path today and are safely deletable.

---

## Requirements Trace

Engineering constraints this plan must satisfy (the acceptance criteria live in `DAYZEROCTO-8`):

- R1. No renderer or CLI code path remains for artifact kinds / subcommands that no shipped skill
  invokes (or any retained path is explicitly quarantined with a documented rationale).
- R2. The CEO report pipeline — both report skills, the renderer, and the existing test suite — passes
  unchanged after the prune; CEO report output bytes are identical for a fixed input.
- R3. Every helper deletion is preceded by a call-site trace; shared helpers that the live CEO/evidence
  path depends on (`parse_commit_rows`, `snapshot_window`, and the `render_*` helpers used by
  `render_ceo_update`) survive.

---

## Scope Boundaries

- In: dead-code removal in `scripts/dzcto.py`, `scripts/dzcto_artifact.py`, `scripts/dzcto_common.py`,
  and lockstep surgical edits to the test suite.
- Out: any behavior change to CEO report output; auto-creating issues from audits; scheduling recurring
  audits; reformatting or refactoring live code beyond what deletion requires.
- Out: pruning the non-report support commands (`help`, `quickstart`, `version`, `setup`, `update`,
  `doctor`, `install-command`, `package-claude-desktop`) as dead machinery — they are not report
  machinery and stay. (This does not forbid the small, mechanical edits the prune forces on
  `scripts/dzcto_doctor.py`'s expected-scripts list — see U6 — or on `scripts/dzcto.py`'s import block —
  see U4/U5. "Don't prune the command" ≠ "never edit the file.")

---

## Context & Research

### Relevant Code and Patterns

**Live surface — must be preserved:**
- CLI (`scripts/dzcto.py`): `init` (2244), `evidence` (2306 → `run_evidence` 1320 → `build_evidence_data`
  262-333), `artifact` (2327 → shells to `dzcto_artifact.py`). Note `evidence` is `argparse.SUPPRESS`-hidden
  yet LIVE — guarded by `test_evidence_command_is_hidden_from_top_level_help` (`tests/test_dzcto_evidence.py:201`).
- Live kind: only `ceo-updates`. `render_structured_report` (`scripts/dzcto_artifact.py:2011-2044`) →
  `render_ceo_update` (1630) → `render_report_page` (5648) / `render_index` (5940, hardcodes
  `report_folder="ceo-updates"` at 5954). `ACTIVE_REPORT_FOLDERS` at 52-54.
- End-to-end write path: `dzcto evidence --json` → model writes report JSON → `dzcto artifact
  --kind ceo-updates --data-file …` → `dzcto_artifact.py` `main()` (6237-6444, renders at 6422, writes 6441).
- Shared helpers that MUST stay: `run_git` (80), `repo_git` (136), `repo_git_text` (143),
  `parse_commit_rows` (183, called by live evidence at 278 **and** dead builder at 418), `unique_sorted`
  (~317), `snapshot_window` (626, used by `run_evidence`), `evidence_*` (194/221/238/249), and the
  `render_ceo_update` helpers `render_metrics` (1252), `render_list_section` (1284), `render_sources`
  (1488), `render_generic_report` (1798), `render_report_page` (5648), `render_thin_evidence_banner`
  (1511), `render_index` (5940).

**Dead surface — prune:**
- 9 dead `SUPPRESS` subcommands + handlers in `scripts/dzcto.py`: `lfg` (→`next_lfg_action`/`print_lfg_action`
  2371), `refresh` (→`refresh_project` 2459), `serve` (→`serve_project` 2464), `check-stale`
  (→`check_stale`/`print_stale_report` 2475), `status` (→`print_project_status` 2484),
  `collect-issue-bundle` (→`collect_issue_bundle` 2487, def 1975-2008), `snapshot` (→`run_snapshot`
  2500), `codebase-accountability` (→`run_codebase_accountability` 2506, def 581), `learning`
  (→ shells to `dzcto_learning.py` 2525). Registration 2200-2355; dispatch 2359-2543.
- Now-dead commit-analysis machinery in `scripts/dzcto.py` (superseded by DAYZEROCTO-7): `commit_files`
  (330, called only at 432), `subsystem_for` (335, called only at 452),
  `build_codebase_accountability_data` (348-580, called only at 587), plus any `run_snapshot` /
  snapshot-builder helpers reachable only from `snapshot`.
- Dead artifact-kind renderers in `scripts/dzcto_artifact.py`: `render_snapshot_report` (1780) +
  `render_snapshot_tldr/communication/appendix/changes` (1693-1778); `render_tech_stack` (1657);
  `render_engineering_risk` (1644); `render_codebase_accountability` (1674); `render_weekly_review`
  (1614); `render_candidate_risk_section` (1388-1486, only called by the two dead renderers). Their
  dispatch branches in `render_structured_report` (2021-2033) and the `{"tech-stack","snapshot"}` branch
  in `render_action_summary` (1552).
- Orphaned risk/decision-registry cluster in `scripts/dzcto_artifact.py` — **verified zero external
  callers this session**: `write_risk_registry` (3630), `write_decision_registry` (3646),
  `write_risk_detail_pages` (5782), `write_decision_detail_pages` (5819), `write_core_pages` (5856),
  `write_search_index` (2681), and `build_risk_registry` (3568, referenced only inside the cluster at
  2724/3631/5866). This is the issue's "risk-register".
- Kind registry dicts — **only `REPORT_FOLDERS` (43-50) is live-indexed** (by the render path at 609 /
  5669 / 5736 / 6243). Keep that object and drop its non-`ceo-updates` rows (U3). The other three dicts
  are **transitively dead**: `REPORT_ROLES` (56-81) is read only by `report_role` (835), which itself has
  zero callers; `RISK_SIGNAL_REPORT_FIELDS` (83-89) and `DECISION_SIGNAL_REPORT_FIELDS` (91-97) are read
  only by `report_risk_signal_json_paths` (3350) / `report_decision_signal_json_paths` (3450), whose
  callers are all inside the dead registry cluster. These three dicts are removed **with** the cluster
  in U4, not narrowed in U3.
- Cross-module imports that break on deletion (**must be pruned in lockstep**): `scripts/dzcto.py:27`
  imports `build_risk_registry` from `dzcto_artifact` (deleted in U4); `scripts/dzcto.py:56-57` import
  `redact` / `redacted_json_text` from `dzcto_common` (deleted in U5). Their only call sites are inside
  dead handlers removed in U1, so the imports go stale the moment U1 lands, but the `import` lines
  themselves live in `dzcto.py` and must be removed by U4/U5 respectively or module load raises
  ImportError.
- Redaction lib in `scripts/dzcto_common.py` (`redact` / `redacted_json_text`): sole consumer is the
  dead `collect-issue-bundle`.

### Institutional Learnings

- `docs/solutions/best-practices/audit-for-dead-but-complete-machinery-2026-07-03.md` — trace the whole
  call chain (not just the first hop) before deleting; dead code is unvetted. Here the method is applied
  in reverse (delete rather than wire up), but the call-site-tracing discipline is identical.

---

## Key Technical Decisions

- **Delete, not quarantine.** Every candidate has a verified empty live-caller set, so deletion is
  cleaner than a documented quarantine. Quarantine is reserved only for anything Phase-3 re-verification
  unexpectedly finds an indirect caller for.
- **Phase by risk, keep every commit green.** Order: U1 (dead CLI/handlers) → U2 (dead renderers +
  lockstep test edits) → U3 (narrow `REPORT_FOLDERS` + `--kind`) → U4 (orphaned registry cluster + its
  three dead dicts + `dzcto.py` import prune) → U5 (redaction lib + `dzcto.py` import prune) → U6
  (`dzcto_learning.py`, decision-gated). U4/U5/U6 all depend on U1. Test-assertion and import-line edits
  ship in the **same** unit as the code they cover, so no intermediate commit is red (satisfies R2
  continuously).
- **`REPORT_FOLDERS` is live; the other three registry dicts are dead.** `REPORT_FOLDERS` is indexed by the
  live render/index path (609, 5669, 5736, 6243), so it stays. U3 narrows only the `--kind` choices and, by
  default, **keeps `REPORT_FOLDERS`'s label rows** so the live membership test — and CEO index output — is
  unchanged (removing the rows is deferred to opt-in; Open Question (d)). `REPORT_ROLES`,
  `RISK_SIGNAL_REPORT_FIELDS`, and `DECISION_SIGNAL_REPORT_FIELDS` are read only by functions that feed the
  dead registry cluster, so they are deleted whole with that cluster (U4). Narrowing `--kind` to
  `ceo-updates` is an intentional CLI tightening of an unshipped surface.
- **Prune cross-module imports in lockstep with the symbols they name.** Deleting `build_risk_registry`
  (U4) and `redact`/`redacted_json_text` (U5) each strands a module-level `import` in `scripts/dzcto.py`;
  those import lines are removed inside the same unit, so `dzcto.py` appears in both units' Files maps and
  both units sequence after U1 (which removes the last live call sites).
- **Byte-identical CEO output is the regression oracle.** Beyond the unit tests, render a `ceo-updates`
  artifact from a fixed data file before and after the whole prune and diff the HTML — it must be identical.

---

## Files

- Modify: `scripts/dzcto.py` — (U1) remove 9 dead subcommand registrations + dispatch arms + their
  handler functions; remove `commit_files`, `subsystem_for`, `build_codebase_accountability_data`,
  `run_snapshot`, `run_codebase_accountability` and any snapshot-only helpers. (U4) remove the stale
  `build_risk_registry` import at line 27. (U5) remove the stale `redact` / `redacted_json_text` imports
  at lines 56-57. Keep `init`/`evidence`/`artifact` and all shared git/evidence helpers.
- Modify: `scripts/dzcto_artifact.py` — (U2) remove dead renderers + their dispatch-dict entries; (U3)
  narrow the `--kind` choices to `ceo-updates` (keeping `REPORT_FOLDERS` label rows by default, AC-safe);
  (U4) delete the orphaned
  risk/decision-registry cluster and its three transitively-dead dicts (`REPORT_ROLES`,
  `RISK_SIGNAL_REPORT_FIELDS`, `DECISION_SIGNAL_REPORT_FIELDS`) plus their dead reader functions.
- Modify: `scripts/dzcto_common.py` — remove `redact` / `redacted_json_text` (once `collect-issue-bundle`
  is gone).
- Modify: `scripts/dzcto_doctor.py` — update the expected-scripts list (line ~86) only if
  `dzcto_learning.py` is deleted (see U6 / Open Questions).
- Delete (decision-gated): `scripts/dzcto_learning.py` — reachable only via the dead `learning` subcommand,
  but also referenced by `scripts/dzcto_doctor.py:86`.
- Modify (test): `tests/test_dzcto_artifact.py` — surgically remove embedded dead-renderer assertions at
  lines 458 (`report_changes_html("snapshot", …)`), 621 (`"weekly-reviews"`), 690 (`render_engineering_risk`),
  701-710 (`render_tech_stack`); keep every LIVE `ceo-updates` class intact.
- Delete (test): `tests/test_dzcto_secrets.py` — covers only the redaction lib; removed with it.
- Keep (test): `tests/test_dzcto_evidence.py` — all 9 tests live; unchanged, must stay green.

---

## Implementation Units

- U1. **Prune dead CLI subcommands, handlers, and superseded commit-analysis machinery (`dzcto.py`)**

**Goal:** Remove the 9 dead `SUPPRESS` subcommands and every function reachable only from them, leaving
`init` / `evidence` / `artifact` and the shared git/evidence helpers intact.

**Requirements:** R1, R2, R3

**Dependencies:** None

**Files:**
- Modify: `scripts/dzcto.py`
- Test: `tests/test_dzcto_evidence.py` (must stay green, unchanged)

**Approach:**
- Delete the registrations for `lfg`, `refresh`, `serve`, `check-stale`, `status`,
  `collect-issue-bundle`, `snapshot`, `codebase-accountability`, `learning` (in 2200-2355) and their
  dispatch arms (in 2359-2543). Leave `evidence`'s `SUPPRESS` registration exactly as-is.
- Delete the handler functions reachable only from those arms: `next_lfg_action`/`print_lfg_action`,
  `refresh_project`, `serve_project`, `check_stale`/`print_stale_report`, `print_project_status`,
  `collect_issue_bundle`, `run_snapshot` (+ snapshot-only builders), `run_codebase_accountability`,
  `build_codebase_accountability_data`, `commit_files`, `subsystem_for`.
- Before deleting each helper, grep its call sites to confirm the only callers are inside this dead set.
  Do NOT touch `run_git`, `repo_git`, `repo_git_text`, `parse_commit_rows`, `unique_sorted`,
  `snapshot_window`, or any `evidence_*` / `build_evidence_data` symbol.

**Patterns to follow:** the call-site audit method in
`docs/solutions/best-practices/audit-for-dead-but-complete-machinery-2026-07-03.md`.

**Test scenarios:**
- Happy path: `tests/test_dzcto_evidence.py` (all 9) still passes, including
  `test_evidence_command_is_hidden_from_top_level_help` — `evidence` remains registered and hidden.
- Edge case: `dzcto --help` no longer lists the removed commands and errors cleanly on
  `dzcto snapshot` / `dzcto codebase-accountability` (unknown command), while `dzcto init`,
  `dzcto evidence`, `dzcto artifact` still parse.
- Verify no remaining reference to any deleted symbol anywhere in `scripts/` or `tests/`.

**Verification:** full test suite green; `python -c "import scripts.dzcto"` (or the module's import path)
succeeds with no `NameError`; grep for each deleted function name returns only historical/no hits.

---

- U2. **Prune dead artifact-kind renderers + lockstep test-assertion edits (`dzcto_artifact.py`)**

**Goal:** Remove the renderers for `snapshot`, `tech-stack`, `engineering-risk`, `codebase-accountability`,
`weekly-reviews` and their dispatch branches, removing the matching dead assertions in the same commit.

**Requirements:** R1, R2, R3

**Dependencies:** None (independent of U1)

**Files:**
- Modify: `scripts/dzcto_artifact.py`
- Test: `tests/test_dzcto_artifact.py`

**Approach:**
- Delete `render_snapshot_report` (1780) + `render_snapshot_tldr/communication/appendix/changes`
  (1693-1778); `render_tech_stack` (1657); `render_engineering_risk` (1644); `render_codebase_accountability`
  (1674); `render_weekly_review` (1614); `render_candidate_risk_section` (1388-1486).
- Remove the corresponding entries from the string-keyed dispatch dict `render_structured_report` builds
  at 2028-2033 (`{"weekly-reviews": render_weekly_review, "ceo-updates": render_ceo_update,
  "engineering-risk": render_engineering_risk, …}`) **in the same edit as the function deletions** — this
  dict is rebuilt on every call including the live `ceo-updates` path, so deleting a function without
  removing its dict entry raises `NameError` on every render. Also remove the `{"tech-stack","snapshot"}`
  branch in `render_action_summary` (1552). Keep the `ceo-updates` entry and the `render_generic_report`
  fallback.
- In the SAME commit, remove the embedded dead-renderer assertions from otherwise-LIVE test classes:
  `tests/test_dzcto_artifact.py` lines 458 (`report_changes_html("snapshot", …)`), 621 (`"weekly-reviews"`
  in `TestThinEvidenceRendering`), 690 (`render_engineering_risk`), 701-710 (`render_tech_stack` inside
  `TestCeoQuietWindowRendering`). Do NOT delete the enclosing classes — they cover the live `ceo-updates`
  path.

**Patterns to follow:** `render_ceo_update` (1630) stays as the template for what a live renderer looks like.

**Test scenarios:**
- Happy path: `TestValidateCeoReport`, `TestWeeklyStreak`, `TestReportChangesHtml`,
  `TestCeoQuietWindowRendering`, `TestArtifactWritePath` all pass after the assertion edits.
- Integration: rendering `--kind ceo-updates` from a fixture produces byte-identical HTML vs. `main`
  before the change (regression oracle from Key Technical Decisions).
- Edge case: no `render_structured_report` branch references a removed renderer; a request for a removed
  kind falls through to the generic fallback or is rejected once dicts are narrowed in U3.

**Verification:** full test suite green; grep confirms no live reference to any deleted renderer.

---

- U3. **Narrow the live `REPORT_FOLDERS` dict and `--kind` choices to `ceo-updates` (`dzcto_artifact.py`)**

**Goal:** Narrow the CLI `--kind` choices to `ceo-updates` — the one behavior change that removes a dead
affordance — while keeping the live `REPORT_FOLDERS` membership behavior intact by default. (The other
three registry dicts are dead and removed in U4, not here.)

**Requirements:** R1, R2

**Dependencies:** U2 (renderers for the removed kinds must be gone first)

**Files:**
- Modify: `scripts/dzcto_artifact.py`
- Test: `tests/test_dzcto_artifact.py`

**Approach (AC-preserving default):**
- Narrow the `--kind` argparse `choices` (6243) so only `ceo-updates` is accepted. Because `choices` reads
  `REPORT_FOLDERS.keys()` today, do this without changing the manifest-membership behavior — e.g. pass an
  explicit `["ceo-updates"]` to `choices` rather than mutating the dict.
- **Keep `REPORT_FOLDERS`'s label rows intact** so the live membership test in
  `prune_manifest_report_artifacts` (5721, called by `render_index` at 5951) — `parts[1] not in
  REPORT_FOLDERS` (5736) — behaves identically and the CEO index output is byte-for-byte unchanged
  (satisfies AC "no behavior change to CEO report output"). The dead rows are harmless label strings, not
  a code path. See Open Question (d) for the opt-in alternative of removing them.
- Confirm `render_index` (5954) and `main()` still resolve `report_folder="ceo-updates"` unchanged.

**Test scenarios:**
- Happy path: `--kind ceo-updates` still parses and renders; the write path (`TestArtifactWritePath`) passes.
- Error path: `--kind snapshot` now exits with an argparse "invalid choice" error rather than dispatching.
- Integration: with a manifest that contains a historical non-`ceo-updates` artifact path, `render_index`
  produces the same index as before this change (membership behavior preserved) — the regression lock for
  the AC-preserving default.
- Edge case: any test that iterated `REPORT_FOLDERS` keys still passes.

**Verification:** full test suite green; `dzcto artifact --kind ceo-updates …` and the CEO index unchanged;
`--kind snapshot` rejected.

---

- U4. **Delete the orphaned risk/decision-registry island + its dead dicts + stale import (`dzcto_artifact.py`, `dzcto.py`)**

**Goal:** Remove the self-referential registry island — its writer functions, the reader functions and
dicts that feed only it, and the now-stale cross-module import in `dzcto.py`.

**Requirements:** R1, R2, R3

**Dependencies:** U1 (`build_risk_registry`'s live call sites at `dzcto.py:1200/1655/1875` are inside the
dead handlers `build_snapshot_data`/`next_lfg_action`/`check_stale` that U1 removes; only after U1 is the
import at `dzcto.py:27` truly stranded)

**Files:**
- Modify: `scripts/dzcto_artifact.py`
- Modify: `scripts/dzcto.py` (remove the stranded `build_risk_registry` import at line 27)

**Approach:**
- **Trace the whole island transitively before deleting** (per the audit doc's chain-tracing guidance),
  not just the first hop — the island is larger than any fixed list, so treat the names below as
  **candidate members, each pending its own per-symbol re-verification**, not a pre-cleared delete list.
  Candidate writers: `write_risk_registry` (3630), `write_decision_registry` (3646),
  `write_risk_detail_pages` (5782), `write_decision_detail_pages` (5819), `write_core_pages` (5856),
  `write_search_index` (2681); builder `build_risk_registry` (3568, referenced only inside the island at
  2724/3631/5866 within `dzcto_artifact.py`, plus the U1-removed call sites in `dzcto.py`); the reader
  chain `report_risk_signal_json_paths` (3350), `report_decision_signal_json_paths` (3450),
  `read_report_risk_signals(_raw)` (3446/3401), `read_report_decision_signals(_raw)` (3538), the
  `dedupe_report_*_signals` wrappers, and `report_role` (835) — all verified this session to bottom out
  with zero live callers; and the three transitively-dead dicts `REPORT_ROLES` (56-81),
  `RISK_SIGNAL_REPORT_FIELDS` (83-89), `DECISION_SIGNAL_REPORT_FIELDS` (91-97).
- Re-verify zero *live* callers for each candidate (grep excluding other island members and the
  U1-removed handlers). Delete only confirmed-dead members plus the `dzcto.py:27` import in the same
  commit. If any candidate turns out to have a live caller, keep it (and its transitive dependencies) and
  note the exception in Open Questions.

**Test scenarios:**
- Happy path: full suite green after deletion (nothing live referenced the island).
- Edge case: grep confirms no remaining reference to any deleted symbol/dict in `scripts/` or `tests/`.
- Integration: `python -c "import …dzcto"` succeeds — the stale `build_risk_registry` import at
  `dzcto.py:27` is gone, so module load raises no `ImportError`.

**Verification:** full test suite green; both `dzcto.py` and `dzcto_artifact.py` import cleanly.

---

- U5. **Remove the redaction lib and its test (`dzcto_common.py`, `test_dzcto_secrets.py`)**

**Goal:** Delete `redact` / `redacted_json_text` (dead once `collect-issue-bundle` is gone) and the test
that covers only them.

**Requirements:** R1, R2

**Dependencies:** U1 (`collect_issue_bundle`, the sole consumer, is removed there)

**Files:**
- Modify: `scripts/dzcto_common.py` (delete `redact` / `redacted_json_text`)
- Modify: `scripts/dzcto.py` (remove the stranded `redact` / `redacted_json_text` imports at lines 56-57)
- Delete: `tests/test_dzcto_secrets.py`

**Approach:**
- Confirm `redact` / `redacted_json_text` have no remaining callers after U1, then delete them from
  `dzcto_common.py` **and** remove the now-stale import of them at `dzcto.py:56-57` in the same commit —
  otherwise `dzcto.py` load raises `ImportError`. Delete `tests/test_dzcto_secrets.py` in the same commit.
- Do NOT touch `redact_text` / `redaction_placeholder` — those are LIVE (the CEO sanitize path uses them
  at `dzcto_artifact.py:6149/6210/6222`); only `redact` / `redacted_json_text` are dead.

**Test scenarios:**
- Happy path: full suite green after removal; `dzcto.py` and `dzcto_common` import cleanly.
- Edge case: grep confirms no live caller of `redact` / `redacted_json_text` remains, and `redact_text` /
  `redaction_placeholder` are untouched.

**Verification:** full test suite green; `dzcto.py` imports with no `ImportError`.

---

- U6. **Resolve `dzcto_learning.py` (decision-gated)**

**Goal:** Decide and execute delete-vs-leave for `scripts/dzcto_learning.py`, which is reachable only via
the dead `learning` subcommand (removed in U1) but is also referenced by `scripts/dzcto_doctor.py:86`.

**Requirements:** R1, R2

**Dependencies:** U1 (the `learning` subcommand is gone)

**Files:**
- Delete (if chosen): `scripts/dzcto_learning.py`
- Modify (if deleting): `scripts/dzcto_doctor.py` (remove the `dzcto_learning.py` entry from the
  expected-scripts list at ~86)

**Approach:**
- Default recommendation: delete `scripts/dzcto_learning.py` and drop its `dzcto_doctor.py` reference, so
  `doctor` no longer expects a file that no shipped surface uses. If the operator prefers to keep the file
  as a documented orphan (e.g. anticipated future reuse), leave both untouched and record the rationale.
  This is the one genuinely optional unit — see Open Questions (c).

**Test scenarios:**
- Happy path (delete): `dzcto doctor` runs clean with the narrowed expected-scripts list; full suite green.
- Edge case: no remaining reference to `dzcto_learning.py` in `scripts/` after deletion.

**Verification:** `dzcto doctor` exits 0; full test suite green.

---

## System-Wide Impact

- **Interaction graph:** the live CEO path (`init`/`evidence`/`artifact` → `render_ceo_update` →
  `render_report_page`/`render_index`) shares only `parse_commit_rows`, `snapshot_window`, and the
  `render_*` helpers with the dead surface — all explicitly preserved.
- **API surface parity:** `--kind` choices narrow to `ceo-updates`; `dzcto <dead-cmd>` becomes an unknown
  command. Both are intended tightenings of an unshipped surface, not user-facing regressions.
- **State lifecycle risks:** none — deletions only; no persisted data or migration involved.
- **Unchanged invariants:** CEO report output must be byte-identical for a fixed input; the evidence
  subcommand stays hidden-but-live; all `dzcto-init`/`dzcto-ceo-report(-weekly)` skill invocations behave
  identically.

---

## Risks & Dependencies

| Risk | Mitigation |
|------|------------|
| Deleting a helper the live CEO/evidence path secretly shares | Every helper deletion is preceded by a call-site grep (U1, U4, U5); the known shared helpers (`parse_commit_rows`, `snapshot_window`, `render_*`) are explicitly on the keep-list. |
| Deleting a symbol `dzcto.py` imports at module level → `ImportError` on load, whole suite red (not caught until that unit runs) | Known cases mapped: `build_risk_registry` (`dzcto.py:27`, pruned in U4) and `redact`/`redacted_json_text` (`dzcto.py:56-57`, pruned in U5). Both units list `dzcto.py` in Files, sequence after U1, and carry an import-clean verification. Implementer greps `from dzcto_artifact import` / `from dzcto_common import` for any other deleted name before finishing U4/U5. |
| `--kind`/`REPORT_FOLDERS` change silently alters live manifest pruning (`prune_manifest_report_artifacts:5736`) | U3's default keeps `REPORT_FOLDERS` label rows and narrows only `--kind`, so the membership test — and the CEO index output — is unchanged (AC-safe). Removing the rows is deferred to opt-in with operator sign-off; Open Questions (d). |
| A dead renderer's assertion lingers in a LIVE test class → red commit | Test-assertion edits ship in the same unit as the renderer deletion (U2), keeping every commit green. |
| Narrowing `--kind` silently breaks a caller | No shipped skill passes a non-`ceo-updates` kind (verified); change is gated behind U2 and covered by an argparse "invalid choice" test. |
| `dzcto_learning.py` deletion breaks `doctor` | U6 updates `dzcto_doctor.py`'s expected-scripts list in the same commit; unit is decision-gated. |
| Hidden dynamic dispatch (getattr/registry) reaches "dead" code | Re-verify zero callers at deletion time (U4 especially); quarantine rather than delete if an indirect caller appears. |

---

## Open Questions

### Resolved During Planning
- DAYZEROCTO-7 salvage coordination: **resolved** — 7 shipped its own `build_evidence_data`; the old
  commit-analysis machinery is dead and deletable (verified against `99461ad`).
- Which subcommands/kinds are live: **resolved** via source audit (see Context & Research); recorded as a
  correction comment on `DAYZEROCTO-8`.

### Deferred to Implementation
- (a) Narrowing `--kind` choices to `ceo-updates` removes a CLI affordance for the dead kinds. Assumed
  acceptable since no shipped skill uses them; confirm during U3 if any external caller is discovered.
- (b) Delete vs. quarantine for the orphaned registry cluster (U4) if re-verification unexpectedly finds
  an indirect caller — default is delete.
- (c) `dzcto_learning.py` (U6): delete wholesale (default) vs. leave as a documented orphan. Coupled to the
  `dzcto_doctor.py:86` reference either way.
- (d) `REPORT_FOLDERS` row removal is **deferred / opt-in**. Default (U3) keeps the label rows so
  `prune_manifest_report_artifacts` (5736) — CEO index output — is byte-for-byte unchanged, satisfying the
  "no behavior change to CEO report output" AC. Removing the dead rows would make the index drop historical
  non-`ceo-updates` manifest entries; that may be desirable housekeeping, but it is a CEO-output change, so
  it needs explicit operator sign-off before doing it (and a stale-manifest test to lock the new behavior).

---

## Sources & References

- Backlog issue: `DAYZEROCTO-8` (business contract; corrections recorded as a comment)
- Related code: `scripts/dzcto.py`, `scripts/dzcto_artifact.py`, `scripts/dzcto_common.py`,
  `scripts/dzcto_doctor.py`, `scripts/dzcto_learning.py`
- Tests: `tests/test_dzcto_artifact.py`, `tests/test_dzcto_evidence.py`, `tests/test_dzcto_secrets.py`
- Institutional learning: `docs/solutions/best-practices/audit-for-dead-but-complete-machinery-2026-07-03.md`
- Related plan: `plans/dayzerocto-7-feature-add-a-window-scoped-git-evidence.md` (superseding evidence collector)

## Decisions

### Keep `dzcto status`, narrowed to CEO-report workspace health — 2026-07-10

The repo-level `AGENTS.md` explicitly requires `dzcto status` to remain a self-serve front door, so
the command stays and now checks company context, repos, the CEO report directory, and `index.html`.
Deleting it per U1 was rejected because that would violate the active repository contract; retaining
its legacy risk, learning, cadence, and core-page checks was rejected because those depended on the
renderer island this issue removes.

### Keep the `dzcto-learning` compatibility alias, not the hidden umbrella command — 2026-07-10

The repo-level layout contract still names `bin/dzcto-learning` as a compatibility alias, so
`scripts/dzcto_learning.py`, its bin wrapper, and doctor checks remain. The hidden `dzcto learning`
subcommand was still removed because no shipped skill invokes it and the compatibility wrapper calls
the script directly.

### Retain live scanner coverage while deleting recursive redaction — 2026-07-10

`tests/test_dzcto_secrets.py` also covers `scan_secrets`, which the live CEO report sanitization path
still uses, so deleting the whole file as proposed in U5 would remove live regression coverage. Only
the tests for deleted `redact` / `redacted_json_text` behavior were removed; the scanner tests remain.

### Delete the full transitively unreachable renderer closure — 2026-07-10

The final call-site audit removed every top-level renderer/helper unreachable from `main`, the three
artifact helpers imported by `dzcto.py`, and the public helpers exercised by live tests. Keeping only
the plan's named roots was rejected because it would strand wrappers around deleted registry and
core-page helpers; the wider deletion stays within R1 and leaves no broken dormant call chains.

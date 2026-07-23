---
title: "DAYZEROCTO-12: Add since_last_report window mode so every day lands in exactly one weekly report"
type: feat
status: planned
priority: p2
created: 2026-07-23
effort: medium
tags: [ceo-report, weekly, window, cursor, cli, renderer, config]
issue_id: DAYZEROCTO-12
artifact_contract: ce-unified-plan/v1
artifact_readiness: implementation-ready
execution: code
---

# DAYZEROCTO-12: Add since_last_report window mode so every day lands in exactly one weekly report

## Goal

Move weekly CEO **report** window resolution out of agent prose and into a deterministic dzcto CLI
resolver, so a `since_last_report` range anchors each run on the **prior report**'s `window.end` and
runs through today. The business contract lives on DAYZEROCTO-12; this plan owns only the
engineering response.

---

## Problem Frame

Today no code resolves the weekly window. `weeklyReportDefaults` (`range`, `startDay`, `endDay`,
`lookbackDays`) is read by an **agent** — `skills/dzcto-ceo-report-weekly/SKILL.md` step 2 says
"Use `weeklyReportDefaults` for the date window" and then hands `--start`/`--end` to
`dzcto evidence`. Day-based values like `previous_completed_week` are ambiguous once you factor in
*which day the agent runs*, so two honest runs can overlap or leave a gap.

That is a textbook violation of the repo's own
`docs/solutions/architecture-patterns/helper-computes-agent-narrates-2026-07-03.md` pattern: a
mechanical, checkable computation is being left to narration. The fix is to give the CLI a
resolver that answers "what window does this run cover?" and reduce the skill to consuming and
narrating its JSON.

The cursor itself needs no new state — `report_effective_date` (`scripts/dzcto_artifact.py:1290`)
already establishes `window.end` as a report's authoritative effective date, and
`weekly_report_dates` (`:1303`) already walks the reports directory filtering on
`report_type == "weekly"`. This work reuses both.

---

## Requirements Trace

The acceptance criteria live on DAYZEROCTO-12. This plan traces to them as:

- R1. A recognized `since_last_report` value on `weeklyReportDefaults.range`, honored end-to-end
  (config write path → resolver → skill → index KPI surface). → U3, U5
- R2. Deterministic cursor resolution from the newest weekly **prior report**'s `window.end`. → U1, U2
- R3. Honest, machine-readable fallback when no prior weekly report exists. → U1, U2, U5
- R4. No new persisted state — the reports directory is the only cursor source. → U1
- R5. Self-healing long windows after a skipped cadence period. → U1 (no clamp, no cap)
- R6. Window length rendered beside the week-over-week metric deltas. → U4

---

## Scope Boundaries

- **Not** porting `previous_completed_week` / `last_7_days` / `lookbackDays` resolution into the
  CLI. This plan adds one new mode and an explicit *"not mine to resolve"* signal for the others;
  the skill keeps its existing day-based prose path. See Key Technical Decisions → KTD3.
- **Not** normalizing week-over-week metrics for varying window length. The issue explicitly accepts
  the reduced apples-to-apples comparison and asks only that window length be visible.
- **Not** recording per-report PR or evidence coverage. `window.end` is the only cursor.
- **Not** changing prior-report *diff baseline* selection (`locate_prior_report`
  `scripts/dzcto_artifact.py:1363`). The cursor and the diff baseline are different jobs with
  deliberately different rules — see KTD2.
- **Not** changing the report **artifact** section spine. AC#6 adds a line *inside* the existing
  "Week over week" section.
- Lands in this repo only (plugin + dzcto CLI), not in consumer repos.

### Deferred to Follow-Up Work

- Porting the day-based modes into the resolver so `dzcto window` becomes the single owner of all
  four range values: separate issue. Noted in Open Questions.

---

## Context & Research

### Relevant Code and Patterns

- `scripts/dzcto.py:91` `evidence_folder_and_repos` — the **artifact-folder / profile** config
  model. This is the model both CEO report skills use. The resolver must use it.
- `scripts/dzcto.py:238` `snapshot_window` — the existing window primitive. Deliberately **not**
  reused on the cursor path: it hard-fails when `start > end`, which is a legitimate state here.
- `scripts/dzcto.py:249` `run_evidence` — the shape a hidden, read-only, JSON-only handler takes.
- `scripts/dzcto.py:798-806` — the `evidence` subparser, registered with `help=argparse.SUPPRESS`;
  `:819` strips suppressed entries from top-level help.
- `scripts/dzcto.py:935` — the dispatch-body wiring. Missing this is the documented three-site trap.
- `scripts/dzcto.py:18` — `dzcto.py` **already imports** from `dzcto_artifact`, so reusing that
  module's date helpers costs no new coupling.
- `scripts/dzcto_artifact.py:1290` `report_effective_date`, `:1303` `weekly_report_dates`,
  `:1176` `read_json_file`, `:1185` `date_value` — the existing cursor-shaped reads.
- `scripts/dzcto_artifact.py:2917` — how the index locates the reports directory
  (`reports_dir / report_folder`, folder normalized by `normalize_report_folder` `:447`).
- `scripts/dzcto_artifact.py:266-278` `apply_init_metadata` — the `weeklyReportDefaults` write path.
- `scripts/dzcto_artifact.py:2924-2932`, `:2953-2957` — the index weekly KPI card and the copyable
  weekly prompt card, both built from `weekly_label`.
- `scripts/dzcto_artifact.py:994-1021` `metric_delta_items`, `:1031-1117` `report_changes_html` —
  the week-over-week section.
- `tests/test_dzcto_evidence.py` — the template for CLI-subcommand tests (hidden-command assertion
  `:201`, bad-input `:181`, real fixture dirs, macOS `/private` path-resolution gotcha `:179`).

### Institutional Learnings

- `docs/solutions/architecture-patterns/helper-computes-agent-narrates-2026-07-03.md` — the pattern
  this whole change restores.
- `docs/solutions/architecture-patterns/match-command-config-model-to-its-consumers-2026-07-09.md` —
  two `.dzcto/config.json` resolution models exist and picking the wrong one fails **silently**.
  Also: know a reused window primitive's bound semantics before reusing it.
- `docs/solutions/conventions/dzcto-engine-flag-three-site-wiring-2026-07-10.md` — CLI wiring is
  whitelist-based, not passthrough; STDOUT is a machine-parsed contract, side chatter goes to
  STDERR; provide a test seam for otherwise-unmockable inputs.
- `docs/solutions/design-patterns/cadence-scoped-prior-report-selection-2026-07-03.md` — boundary
  discipline around `window.end` and deliberate `<` vs `<=`.
- `docs/solutions/design-patterns/today-anchored-cadence-period-streak-2026-07-09.md` —
  today-anchored windows, warn-never-fail read paths, and the config-path testing trap.
- `docs/solutions/logic-errors/python-numeric-metric-delta-gotchas-2026-07-03.md` — the existing
  guards in `metric_delta_items` that U4 must not disturb.

### External References

None. Local prior art is strong and directly on point; no external research was run.

---

## Key Technical Decisions

- **KTD1 — A new hidden `dzcto window` subcommand, not a flag on `dzcto evidence`.** Window
  resolution and evidence collection are different concerns with different failure modes: the window
  is needed even when zero repos are configured, and it feeds three consumers (the `dzcto evidence`
  call, the report JSON `window` field, and the report title). Folding it into `evidence` would make
  the collector's output the only way to learn the window, and would give a "no configured repos"
  degradation path the power to also lose the window. A separate suppressed, read-only, JSON-only
  subparser mirrors `evidence` exactly and keeps each command answering one question.

- **KTD2 — The cursor is the newest report with `report_type: "weekly"`, not the newest report of
  any type.** `weeklyReportDefaults` governs the weekly cadence, so the cursor must be
  cadence-scoped the same way `weekly_report_dates` (`:1314`) already filters. An ad-hoc **CEO
  report** covering an arbitrary range must not advance the weekly cursor — if it did, an ad-hoc
  report would silently swallow days out of the weekly ritual, which is the exact gap this issue
  exists to close. Note the deliberate asymmetry with `locate_prior_report`, which *does* fall back
  to any type: that picks a **prior report** as a narrative comparison baseline (better to compare
  against something than nothing), while this picks a coverage ledger position (better to re-cover a
  few days than to skip them). Different jobs, different rules — record this in the code comment.

- **KTD3 — The resolver owns `since_last_report` only; every other `range` value returns an
  explicit `day_based` deferral.** The issue scopes this to adding one mode, and porting
  `previous_completed_week` weekday math would triple the diff. The resolver still answers for those
  configs — with `mode: "day_based"` and the configured value echoed back — so the skill's fallback
  is a *declared* branch rather than an accident. Making the resolver own all four modes is the
  natural follow-up and is recorded as deferred work.

- **KTD4 — Import the date helpers from `dzcto_artifact`; do not move them to `dzcto_common`.**
  `scripts/dzcto.py:18` already imports from `dzcto_artifact`, so the edge is paid for. Relocating
  `report_effective_date` / `date_value` into `dzcto_common` would churn renderer call sites for no
  behavioral gain, and duplicating them would create two definitions of "a report's effective date"
  — precisely the drift the golden template test exists to prevent.

- **KTD5 — An already-covered window is a legitimate, non-fatal result.** When the cursor's
  `window.end` is on or after today, the derived `start` exceeds `end`. The resolver reports that
  honestly (`days: 0`, `empty: true`) with a STDERR note rather than raising, consistent with the
  repo's warn-never-fail read paths. This is why `snapshot_window` is not reused: it would
  `SystemExit`. The consumer contract is that `empty: true` means **do not call `dzcto evidence`** —
  piping `start > end` into it hard-fails at `dzcto.py:245`.

- **KTD6 — No upper bound on window length.** A 14- or 30-day window after a skipped cadence period
  is the self-healing behavior working, not an anomaly. Emitting a warning would train operators to
  distrust a correct result. The resolver emits `days` and the report **artifact** surfaces it (U4);
  that is the whole mitigation.

- **KTD7 — An `--as-of` test seam.** "Today" is otherwise unmockable and would make every resolver
  test clock-dependent. A hidden `--as-of YYYY-MM-DD` flag pins the run date, mirroring the
  `DZCTO_NO_OPEN` seam pattern. Production callers never pass it.

- **KTD8 — `since_last_report` is accepted as a `range` value without adding validation.**
  `apply_init_metadata` (`:266-278`) stores `range` as free text today. Introducing an allow-list now
  would reject the existing untyped values operators already have on disk and turn a config typo
  into a hard init failure. The resolver's `day_based` branch already handles unknown values safely.

---

## High-Level Technical Design

> *This illustrates the intended approach and is directional guidance for review, not implementation
> specification. The implementing agent should treat it as context, not code to reproduce.*

Resolution outcomes, as a decision matrix:

| `weeklyReportDefaults.range` | Newest weekly prior report | Emitted `mode` | `start` | `end` | `empty` |
|---|---|---|---|---|---|
| `since_last_report` | exists, `window.end` < today | `since_last_report` | `window.end` + 1 day | today | `false` |
| `since_last_report` | exists, `window.end` >= today | `since_last_report` | `window.end` + 1 day | today | `true` (`days: 0`) |
| `since_last_report` | none / unreadable / undated | `fallback` | `null` | today | `false` |
| anything else (or unset) | n/a | `day_based` | `null` | today | `false` |

STDOUT contract (one JSON object, nothing else — STDERR carries skip and clamp notes):

    {
      "mode": "since_last_report",
      "range": "since_last_report",      // the configured value, echoed back
      "start": "2026-07-15",
      "end": "2026-07-23",
      "days": 9,
      "empty": false,
      "cursor": {
        "report": "reports/ceo-updates/2026-07-14-ceo-report-2026-07-08-to-2026-07-14.json",
        "window_end": "2026-07-14"
      },
      "fallback_reason": null            // e.g. "no_prior_weekly_report" when mode == "fallback"
    }

Consumer flow after this change:

```mermaid
sequenceDiagram
    participant S as dzcto-ceo-report-weekly (agent)
    participant W as dzcto window
    participant E as dzcto evidence
    S->>W: --profile / --artifacts-dir
    W-->>S: {mode, start, end, days, empty, cursor}
    alt mode == since_last_report and empty == false
        S->>E: --start / --end (verbatim)
        E-->>S: evidence JSON
    else empty == true
        S-->>S: narrate "already covered through <window.end>"; no evidence call
    else mode == fallback or day_based
        S-->>S: existing day-based defaults path
    end
```

---

## Implementation Units

- U1. **Cursor and window resolution helpers**

**Goal:** Pure, testable functions that find the newest weekly **prior report**'s `window.end` and
derive the run's window from it.

**Requirements:** R2, R3, R4, R5

**Dependencies:** None

**Files:**
- Modify: `scripts/dzcto.py`
- Test: `tests/test_dzcto_window.py`

**Approach:**
- Add a cursor reader that walks `<artifacts-dir>/reports/ceo-updates/*.json`, skipping
  `data.json`, keeping only `report_type == "weekly"`, and taking the newest resolvable
  `report_effective_date`. Reuse `report_effective_date`, `read_json_file`, and `date_value`
  imported from `dzcto_artifact` (KTD4); extend the existing `dzcto.py:18` import line.
- Derive the reports directory the same way `render_index` does (`dzcto_artifact.py:2917`) —
  `wiki_root / "reports" / normalize_report_folder("ceo-updates")` — rather than hardcoding a
  string, so the two stay in step.
- Add the window derivation: `start = cursor + 1 day`, `end = as_of or today`,
  `days = (end - start).days + 1` clamped at 0, `empty = start > end`.
- Warn-never-fail throughout: unreadable JSON, missing `window.end`, and a missing reports
  directory each produce a STDERR note and are treated as "no cursor", never an exception. Mirror
  the exact note style of `weekly_report_dates:1312` / `:1318`.
- Do **not** call `snapshot_window` (KTD5) and do **not** cap `days` (KTD6).

**Execution note:** Implement test-first — the edge cases (empty window, future cursor, corrupt
prior report) are the point of the unit, and they are all cheap to express as failing tests before
the derivation exists.

**Patterns to follow:**
- `scripts/dzcto_artifact.py:1303-1321` `weekly_report_dates` — the weekly-typed, skip-and-note walk.
- `scripts/dzcto.py:231-246` — module-local date parsing and validation style.

**Test scenarios:**
- Happy path: two weekly reports on disk with `window.end` `2026-07-07` and `2026-07-14`; `--as-of
  2026-07-23` → `start 2026-07-15`, `end 2026-07-23`, `days 9`, cursor names the `07-14` report.
- Happy path (self-heal, R5): newest weekly `window.end` `2026-07-02`, `--as-of 2026-07-23` →
  `days 21` (start `07-03` through `07-23`, both bounds inclusive), no warning emitted, no clamp.
- Edge case: newest weekly `window.end` equals the run date → `days 0`, `empty true`, `start`
  strictly greater than `end`.
- Edge case: newest weekly `window.end` is *after* the run date (hand-edited/clock skew) →
  `empty true`, `days 0`, STDERR note, no exception.
- Edge case: reports directory does not exist → no cursor, no exception.
- Edge case: only `data.json` present → no cursor (it is excluded like everywhere else).
- Error path: a report JSON that is unparseable → skipped with a STDERR note; a *valid* older
  weekly report is still selected as the cursor.
- Error path: newest weekly report has no `window` and a non-ISO filename → skipped with a note;
  falls through to the next resolvable weekly.
- Edge case (KTD2): the newest report on disk is `report_type: "ad_hoc"` with a later `window.end`
  than the newest weekly → the **weekly** report is chosen as the cursor.
- Edge case: a legacy report with no `report_type` at all → not treated as weekly, not chosen.

**Verification:**
- Cursor selection and window derivation are provable without a clock, a git repo, or a rendered
  report — only a fixture reports directory and `--as-of`.

---

- U2. **`dzcto window` subcommand — three-site wiring and JSON contract**

**Goal:** Expose U1 as a hidden, read-only, JSON-only subcommand consuming the same config model the
CEO report skills use.

**Requirements:** R2, R3

**Dependencies:** U1

**Files:**
- Modify: `scripts/dzcto.py`
- Test: `tests/test_dzcto_window.py`

**Approach:**
- Wire all three sites in `scripts/dzcto.py`: the handler function (beside `run_evidence` `:249`),
  the subparser registration (beside the `evidence` block `:798-806`, with
  `help=argparse.SUPPRESS`), and the dispatch body branch (beside `:935`). Missing any one is the
  documented failure mode.
- Flags mirror `evidence` where they overlap: `--artifacts-dir`, `--profile`, plus `--as-of`
  (KTD7). Resolve the artifact folder through `evidence_folder_and_repos`-style resolution — the
  **artifact-folder / profile** model, never the project-wiki model. Because this command needs no
  repos, either reuse the folder half of `evidence_folder_and_repos` or extract that half; do not
  reach for `wiki_root_for_project`.
- Emit exactly one JSON object on STDOUT (the shape in High-Level Technical Design). All notes,
  skips, and the empty-window advisory go to STDERR — the skill parses STDOUT.
- Branch on the configured `range`: `since_last_report` → U1's resolution; anything else (including
  unset) → `mode: "day_based"` with the configured value echoed in `range` (KTD3).
- Unresolvable artifact folder returns exit 2 with the same guidance message `run_evidence` uses
  (`:252-256`), not a traceback.

**Patterns to follow:**
- `scripts/dzcto.py:249-274` `run_evidence` — handler shape, folder-resolution failure message,
  JSON emission.
- `scripts/dzcto.py:798-806` and `:819` — suppressed subparser registration and the help filter.

**Test scenarios:**
- Happy path: fixture artifact folder with `weeklyReportDefaults.range = "since_last_report"` and
  two weekly reports → STDOUT parses as JSON with `mode "since_last_report"` and the expected
  `start`/`end`/`days`.
- Happy path: `range = "previous_completed_week"` → `mode "day_based"`, `range` echoed, `start`
  null, exit 0.
- Edge case: `weeklyReportDefaults` absent entirely → `mode "day_based"`, no crash.
- Edge case: `range = "since_last_report"` but no reports directory → `mode "fallback"`,
  `fallback_reason "no_prior_weekly_report"`, `end` = the run date.
- Integration: `--profile` alone (no `--artifacts-dir`), with a global profile supplying
  `artifactsDir`, resolves the same window — this is the config-model trap; assert the non-empty
  result, not just exit 0.
- Error path: neither `--artifacts-dir` nor a resolvable profile → exit 2 with the guidance
  message, nothing on STDOUT.
- Error path: `--as-of` given a non-ISO value → clear failure, not a traceback.
- Integration: STDOUT is a single parseable JSON document even when STDERR carries skip notes
  (assert by parsing STDOUT alone with STDERR captured separately).
- Integration: `dzcto --help` does not list `window` (mirrors
  `test_evidence_command_is_hidden_from_top_level_help` `tests/test_dzcto_evidence.py:201`), while
  `dzcto window --help` still works.

**Verification:**
- Both user surfaces work: the `dzcto` shim and the `python3 scripts/dzcto.py window` fallback the
  skills document.

---

- U3. **Config surface: recognize `since_last_report` on the index KPI and prompt cards**

**Goal:** Stop the report index from describing a cursor-mode profile in day-of-week terms.

**Requirements:** R1

**Dependencies:** None

**Files:**
- Modify: `scripts/dzcto_artifact.py`
- Test: `tests/test_dzcto_artifact.py`

**Approach:**
- `scripts/dzcto_artifact.py:2924-2932`: when `range == "since_last_report"`, build `weekly_label`
  without the `startDay`/`endDay` clause (those keys are meaningless for a cursor and may be stale
  leftovers), and replace the `weekly_kpi_value` day abbreviation — today
  `f"{weekly_start[:3]} to {weekly_end[:3]}"` would render a confident, wrong `"Fri to Thu"`.
- `:2953-2957`: the copyable weekly prompt card embeds `weekly_label`, so it inherits the fix
  automatically — assert that rather than duplicating logic.
- Leave `apply_init_metadata` (`:266-278`) unchanged (KTD8): `--weekly-range since_last_report`
  already persists correctly as free text.

**Patterns to follow:**
- The existing `not_configured` / `"Needed"` branch immediately above (`:2925`, `:2932`) — the
  established way this card special-cases a range value.

**Test scenarios:**
- Happy path: config with `range = "since_last_report"` → rendered index KPI does **not** contain a
  day-of-week abbreviation pair, and the label does not claim a start/end day.
- Edge case: `range = "since_last_report"` with stale `startDay`/`endDay` still present in config →
  those values do not leak into the label or the KPI.
- Happy path (regression): `range = "previous_completed_week"` with `startDay`/`endDay` renders
  exactly as before.
- Edge case: `range` unset → the existing `not_configured` / `"Needed"` behavior is unchanged.
- Integration: the copyable weekly prompt card text reflects the corrected label (proves the two
  surfaces share one source).

**Verification:**
- No surface on the generated index describes a cursor-mode profile as a fixed weekday range.

---

- U4. **Render window length beside the week-over-week deltas**

**Goal:** Make a varying-length window visible wherever its metrics are compared.

**Requirements:** R6

**Dependencies:** None

**Files:**
- Modify: `scripts/dzcto_artifact.py`
- Modify: `docs/ceo-report-template.md`
- Test: `tests/test_dzcto_artifact.py`

**Approach:**
- In `report_changes_html` (`:1031-1117`), emit a leading window line inside the existing
  `<section class="report-changes">` list — before the metric-delta items — naming this window's
  length and the **prior report**'s, e.g. *"Window: 9 days (2026-07-15 to 2026-07-23); prior 7
  days."* Reader sees the denominator before the numbers.
- Render it whenever a prior report exists and both windows have resolvable dates, **independent of
  whether any numeric delta rendered**. A report with no numeric metrics still needs its window
  length visible; gating on deltas would hide it exactly when metrics are sparse.
- Do not disturb the "no material structured changes" fallback at `:1101`. That condition tests
  `group_changes`, `metric_items`, and `not_comparable` — not the length of `changes` — so a window
  line must not be counted as a material change. Verify this explicitly.
- Derive both lengths from `window.start`/`window.end` via `date_value`; when either side is
  missing or unparseable, omit the line rather than guessing. Leave the "First report — no prior
  baseline" early return (`:1041-1050`) untouched.
- Update `docs/ceo-report-template.md` "Week-over-week semantics" (`:102-114`) so the canon
  describes the new line. The section **spine** (`:9-33`) is unchanged — this adds content inside
  section 3, so `test_spine_constant_matches_template_sections` stays green by construction.

**Execution note:** Run the existing week-over-week tests (`tests/test_dzcto_artifact.py:454-600`)
before writing the change. Several assert on rendered list content and may need updating; knowing
which ones fail *first* separates intended churn from a real regression.

**Patterns to follow:**
- `scripts/dzcto_artifact.py:1056-1061` — how notes are prepended ahead of metric items today.
- `scripts/dzcto_artifact.py:986-991` `format_metric_value` and the `esc()` discipline used on
  every rendered value in that function.

**Test scenarios:**
- Happy path: current window 9 days, prior 7 days, with numeric metric deltas → window line renders
  before the delta items and names both lengths.
- Happy path: equal-length windows (7 and 7) → the line still renders (its job is disclosure, not
  anomaly flagging).
- Edge case: prior report exists but current report has **no** numeric metrics → window line still
  renders.
- Edge case: identical reports that today produce "No material structured changes" → that line
  still renders, and the window line does not suppress it.
- Edge case: prior report lacks `window.start` → line omitted entirely; no partial or guessed
  length.
- Edge case: `window.start` after `window.end` on either report → line omitted rather than
  rendering a negative length.
- Edge case: single-day window (`start == end`) → renders as 1 day, not 0.
- Error path: non-ISO `window` values → line omitted; rendering never aborts (the repo's
  warn-never-fail rule).
- Integration: `test_spine_constant_matches_template_sections` and
  `test_template_spine_sections_render_in_order` still pass after the template edit.
- Integration: rendered window text is HTML-escaped like its neighbours.

**Verification:**
- Every week-over-week section with a resolvable prior states the window length; the section spine
  and the "first report" placeholder are unchanged.

---

- U5. **Rewire the weekly report skill to consume the resolver**

**Goal:** Reduce the skill from *interpreting* `weeklyReportDefaults` to *consuming* resolved JSON.

**Requirements:** R1, R3

**Dependencies:** U2, U3

**Files:**
- Modify: `skills/dzcto-ceo-report-weekly/SKILL.md`
- Modify: `skills/dzcto-init/SKILL.md`
- Test: `tests/test_dzcto_artifact.py`

**Approach:**
- `skills/dzcto-ceo-report-weekly/SKILL.md` steps 2-4: run `dzcto window` first and branch on
  `mode`. `since_last_report` with `empty: false` → pass `start`/`end` verbatim to
  `dzcto evidence`. `empty: true` → report honestly that the range is already covered through the
  cursor date and **do not** call `dzcto evidence` (KTD5: `start > end` hard-fails it). `fallback`
  or `day_based` → the existing day-based defaults path, unchanged.
- Include the `python3 scripts/dzcto.py window ...` fallback form alongside the `dzcto window`
  form, matching how the evidence step already documents both (`SKILL.md:35-44`).
- Do **not** touch the "Report JSON schema (v1)" section (`:75-94`) — it is byte-locked with
  `skills/dzcto-ceo-report/SKILL.md` by a unit test. No schema field changes are needed; `window`
  already exists.
- `skills/dzcto-init/SKILL.md` (`:17-18`, `:30`, `:44`): offer `since_last_report` as a range value
  alongside the `Fri-Thu` / `Mon-Sun` shorthands, describing it as gapless-by-construction.
- Keep the ad-hoc skill (`skills/dzcto-ceo-report/SKILL.md`) untouched — it is explicitly not
  cadence-scoped.

**Test scenarios:**
- Integration: the schema-lockstep test still passes (the two SKILL.md schema sections remain
  byte-identical).
- Happy path: assert `skills/dzcto-ceo-report-weekly/SKILL.md` instructs running the window
  resolver before the evidence collector, and documents both the `dzcto` and `python3` forms —
  mirroring the existing prompt-content assertions
  (`test_report_skills_prompt_quiet_window_authoring` `tests/test_dzcto_artifact.py:819`).
- Edge case: assert the skill documents the `empty: true` branch as "do not call evidence", since
  that is the one instruction whose omission produces a hard failure in a real run.
- Happy path: assert `skills/dzcto-init/SKILL.md` names `since_last_report`.

**Verification:**
- A weekly run on a `since_last_report` profile never decides its own dates; the skill only
  narrates what the resolver returned.

---

- U6. **Documentation and domain vocabulary**

**Goal:** Make the new range value discoverable everywhere the existing ones are documented.

**Requirements:** R1

**Dependencies:** U2, U5

**Files:**
- Modify: `README.md`
- Modify: `INSTALL_FOR_AGENTS.md`
- Modify: `CONCEPTS.md`
- Modify: `scripts/dzcto.py`

**Approach:**
- `README.md:80-83` (profile JSON example) and `:165` (config key table): document
  `since_last_report` as a `range` value and what it means.
- `INSTALL_FOR_AGENTS.md:93` and the `scripts/dzcto.py` quickstart/command-reference examples
  (`:296`, `:361`): leave `previous_completed_week` as the shown default, but mention the cursor
  value where ranges are enumerated. Do not silently change the canonical example — that would
  alter what every new install copies.
- `CONCEPTS.md`: add the **Report window** / cursor term under `## Reports`, defining the
  since-last-report window as the span from the prior weekly **report artifact**'s `window.end`
  through the run date, and noting that the cursor is weekly-scoped while the **prior report** diff
  baseline is not (KTD2). This term was identified during planning but is deliberately written here
  rather than at plan time, since its wording depends on the resolution semantics U1/U2 land.

**Test scenarios:**
- `Test expectation: none` — documentation and glossary only; no behavior changes. The
  `since_last_report` value's behavior is covered by U2, and the config-key documentation has no
  existing test to extend.

**Verification:**
- An operator reading only `README.md` can configure and understand cursor mode.

---

## System-Wide Impact

- **Interaction graph:** `dzcto window` (new) → the weekly report skill → `dzcto evidence` →
  `dzcto artifact`. The resolver is upstream of everything; a wrong window silently mis-scopes the
  whole report, so U1's tests are the load-bearing ones.
- **Error propagation:** Every read path in U1/U2 is warn-never-fail — skip with a STDERR note,
  never raise. The single hard failure is an unresolvable artifact folder (exit 2), matching
  `run_evidence`.
- **State lifecycle risks:** None — no new persisted state. The cursor is derived on every call from
  the reports directory (R4). The one ordering hazard is that a report **artifact** written for a
  window advances the cursor for the *next* run; a report written with the wrong window therefore
  poisons the following window too. Named here so an operator who spots a bad window knows to fix
  the report JSON's `window.end`, not just re-run.
- **API surface parity:** `dzcto window` must work through both documented invocation forms (the
  `dzcto` shim and `python3 scripts/dzcto.py`), like `evidence`.
- **Integration coverage:** The `--profile`-only resolution path (U2) is the config-model trap from
  the DAYZEROCTO-7 learning — it must be asserted with a *non-empty* expected result, because the
  wrong config model returns valid-but-empty output with no error.
- **Unchanged invariants:** The report JSON schema v1, the section spine, `locate_prior_report`'s
  diff-baseline rules, `apply_init_metadata`'s free-text `range` write path, and the existing
  day-based skill behavior for all other `range` values.

---

## Risks & Dependencies

| Risk | Mitigation |
|------|------------|
| The resolver binds to the project-wiki config model and silently returns no cursor | U2 uses the artifact-folder/profile model and asserts the `--profile`-only path yields a **non-empty** window (DAYZEROCTO-7 learning) |
| U4 breaks existing week-over-week tests that assert on rendered list content | U4's execution note runs those tests first; the "no material changes" interaction is an explicit test scenario |
| A cursor-mode profile ships with stale `startDay`/`endDay` and the index renders a confident wrong weekday range | U3 suppresses those fields for `since_last_report` on both the KPI card and the shared prompt card |
| The skill pipes an `empty: true` window into `dzcto evidence` and hard-fails mid-run | The `empty` flag is part of the STDOUT contract, U5 documents the no-evidence-call branch, and it has its own test scenario |
| Only two of the three CLI wiring sites get updated | U2 names all three explicitly; the hidden-command and both-invocation-form tests catch a missed site |
| An ad-hoc report advances the weekly cursor and silently drops days | KTD2 filters on `report_type == "weekly"`, with a dedicated test where an ad-hoc report has a later `window.end` |
| A long self-healed window reads as a bug to an operator | KTD6 renders window length (U4) instead of warning; the disclosure *is* the mitigation |

---

## Open Questions

### Resolved During Planning

- **Where does resolution live?** A new hidden `dzcto window` subcommand, not a flag on
  `dzcto evidence` — KTD1.
- **Which prior report is the cursor?** The newest `report_type: "weekly"` report — KTD2, with the
  deliberate asymmetry against `locate_prior_report` documented.
- **What is the no-prior-report fallback, and how is it signalled?** `mode: "fallback"` with
  `fallback_reason`, and the skill keeps its existing day-based path — KTD3.
- **Cursor at or after today?** Non-fatal: `days: 0`, `empty: true`, STDERR note; consumer must not
  call `dzcto evidence` — KTD5. This is why `snapshot_window` is not reused.
- **Cap on window length?** No — KTD6.
- **Where does window length render, and does it need deltas?** A leading line inside the existing
  week-over-week section, rendered independent of whether numeric deltas exist — U4.
- **Share the date helpers how?** Import from `dzcto_artifact`; the import edge already exists —
  KTD4.
- **Validate the `range` value?** No — KTD8.

### Deferred to Implementation

- Exact function and flag naming inside `scripts/dzcto.py` — settle it against the surrounding code
  when the file is open.
- Whether the artifact-folder half of `evidence_folder_and_repos` is reused as-is or extracted into
  a small shared resolver; both are acceptable, and the right call depends on how the repos half
  reads once split.
- The precise wording of the U4 window line — it should be checked against a rendered report before
  fixing the test assertions.
- Which specific existing week-over-week tests need updating; discoverable only by running them.

### Deferred to Follow-Up Work

- Porting `previous_completed_week` / `last_7_days` / `lookbackDays` into the resolver so
  `dzcto window` owns all four modes and the skill never interprets a date rule. Worth a separate
  issue once cursor mode has real usage.

---

## Sources & References

- Origin issue: DAYZEROCTO-12 (markdown backlog; owns the acceptance criteria)
- Canon: `docs/ceo-report-template.md`
- Learnings: `docs/solutions/architecture-patterns/match-command-config-model-to-its-consumers-2026-07-09.md`,
  `docs/solutions/conventions/dzcto-engine-flag-three-site-wiring-2026-07-10.md`,
  `docs/solutions/architecture-patterns/helper-computes-agent-narrates-2026-07-03.md`,
  `docs/solutions/design-patterns/cadence-scoped-prior-report-selection-2026-07-03.md`,
  `docs/solutions/design-patterns/today-anchored-cadence-period-streak-2026-07-09.md`
- Nearest sibling implementation: DAYZEROCTO-7 (`dzcto evidence`), `plans/dayzerocto-7-feature-add-a-window-scoped-git-evidence.md`

---

## Completeness / Wiring Surfaces

Derived from the `dzcto evidence` (DAYZEROCTO-7) and `weeklyReportDefaults.range` precedents. Each
bullet is checkable by opening the named file.

- [ ] `scripts/dzcto.py` — resolution helpers added beside `snapshot_window` (`:238`), **not**
      reusing it (KTD5). (U1)
- [ ] `scripts/dzcto.py:18` — `dzcto_artifact` import extended with the date/report helpers (KTD4). (U1)
- [ ] `scripts/dzcto.py` — handler function added beside `run_evidence` (`:249`). (U2)
- [ ] `scripts/dzcto.py:798-817` — subparser registered with `help=argparse.SUPPRESS`; confirm the
      `:819` `_choices_actions` filter still hides it from top-level help. (U2)
- [ ] `scripts/dzcto.py:935` — dispatch-body branch added. This is the documented three-site trap. (U2)
- [ ] Artifact-folder / profile config model used (`evidence_folder_and_repos` `:91`), never the
      project-wiki model. (U2)
- [ ] STDOUT emits exactly one JSON object; all notes go to STDERR. (U2)
- [ ] `--as-of` test seam present and unused by production callers. (U1, U2)
- [ ] `scripts/dzcto_artifact.py:266-278` `apply_init_metadata` — reviewed and deliberately left
      unchanged (KTD8). (U3)
- [ ] `scripts/dzcto_artifact.py:2924-2932` — index weekly KPI label and value corrected for
      cursor mode. (U3)
- [ ] `scripts/dzcto_artifact.py:2953-2957` — the copyable weekly prompt card reflects the
      corrected label. (U3)
- [ ] `scripts/dzcto_artifact.py:1031-1117` — window length rendered ahead of the metric deltas,
      without disturbing the `:1101` "no material changes" condition. (U4)
- [ ] `docs/ceo-report-template.md:102-114` — "Week-over-week semantics" documents the new line;
      the spine table (`:9-33`) is unchanged. (U4)
- [ ] `skills/dzcto-ceo-report-weekly/SKILL.md` — steps 2-4 consume `dzcto window`, both invocation
      forms documented, `empty: true` branch stated; schema section (`:75-94`) byte-unchanged. (U5)
- [ ] `skills/dzcto-init/SKILL.md:17-18, :30, :44` — `since_last_report` offered as a range value. (U5)
- [ ] `README.md:80-83` and `:165` — profile example and config key table document the value. (U6)
- [ ] `INSTALL_FOR_AGENTS.md:93`, `scripts/dzcto.py:296`, `scripts/dzcto.py:361` — range
      enumerations mention cursor mode; the canonical copy-paste example is not silently changed. (U6)
- [ ] `CONCEPTS.md` — the since-last-report window term added under `## Reports`. (U6)
- [ ] `tests/test_dzcto_window.py` — new, modelled on `tests/test_dzcto_evidence.py` (hidden
      command, bad input, real fixture dirs, macOS `/private` path resolution). (U1, U2)
- [ ] `tests/test_dzcto_artifact.py` — renderer, index KPI, spine, and skill-content coverage
      extended. (U3, U4, U5)

---

## Decisions

### The week-over-week window line must not contain an arrow — 2026-07-23

`tests/test_dzcto_artifact.py::test_disjoint_metrics_render_no_delta` asserts
`assertNotIn("→", html)` over the whole `report_changes_html` output, as a proxy for "no metric
delta rendered". The obvious phrasing for the new line — `2026-07-15 → 2026-07-23` — would have
tripped it and looked like a regression in unrelated metric logic. Picked `(start to end)`;
rejected the arrow form. The assertion is a reasonable proxy that a *new* arrow-bearing line
silently invalidates, so the constraint is worth keeping in view for any future addition to this
section.

### The README's canonical profile example keeps `previous_completed_week` — 2026-07-23

The first pass at U6 swapped the README's copy-paste profile block to `since_last_report`. That
block is what every new install copies, so replacing it would have changed the recommended default
for all new profiles. DAYZEROCTO-12 adds an option; it does not promote it. Kept the day-based
example and documented cursor mode beside it as an alternative.

### `plan-units status` cannot distinguish "not started" from "done" — 2026-07-23

With zero units committed, `partial` is `false`, and an untracked plan file alone satisfies the
"tree is dirty" half of the work postcondition. So `all in_progress` + `changes present` +
`partial == false` passed *vacuously* before any implementation existed, and a resume in that
window would have advanced to the ship stage on an empty branch. Only the durable marker's `stage`
field distinguishes the two states. Not fixed here — recorded because the next multi-unit run has
the same window between the issue transition and the first unit commit.

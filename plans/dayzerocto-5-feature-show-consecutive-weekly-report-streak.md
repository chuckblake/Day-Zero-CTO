---
title: "DAYZEROCTO-5: Show the consecutive-weekly-report streak on the report index"
status: planned
priority: p2
created: 2026-07-09
effort: small
tags: [ceo-report, index, north-star, cadence, streak, renderer]
linear_id: DAYZEROCTO-5
artifact_contract: ce-unified-plan/v1
artifact_readiness: implementation-ready
execution: code
product_contract_source: ce-plan-bootstrap
---

# DAYZEROCTO-5: Show the consecutive-weekly-report streak on the report index

## Goal

Compute the user's current run of consecutive weekly CEO reports from the sibling report JSON and render it as a KPI tile on the generated index, so the product's North Star ("three consecutive weeks") has a visible surface. The business contract lives on DAYZEROCTO-5; this plan owns only the engineering response.

---

## Problem Frame

The issue frames this as "largely assembly of existing data." The assembly is easy. **Two definitional decisions are the actual work**, and if they are left implicit the implementation will silently pick the wrong one:

**1. What does "current" mean?** A user who filed three weekly reports and then went quiet for a month has a *historical* run of three and a *current* streak of zero. Only the second reading serves the stated purpose ("nudging the user toward the weekly ritual") and the present-tense North Star. Anchoring to the latest report instead of to today produces a tile that congratulates a lapsed user forever — the exact opposite of a nudge.

**2. What does "consecutive" mean when windows overlap?** `docs/ceo-report-template.md` is explicit that weekly windows overlap by design (rolling lookback), and that weekly-vs-weekly comparison therefore carries no overlap caveat. So consecutiveness cannot be exact 7-day spacing, and it cannot be file adjacency. Naive adjacency counting also inflates the streak: two reruns three days apart would read as "week 2."

Both are resolved below (KTD1, KTD2). Everything else is wiring.

Secondary hazard, from `docs/solutions/logic-errors/python-numeric-metric-delta-gotchas-2026-07-03.md`: this computation runs on the same untrusted JSON that `validate_ceo_report()` only *warns* about. A report with a missing or non-ISO `window.end` must be skipped, never raised through `render_index()`. The index write path is warn-never-fail.

---

## Context

`render_index()` (`scripts/dzcto_artifact.py`) builds `index.html`. It already:

- reads `core/` and the project config (`weeklyReportDefaults`, tone, repos),
- globs `reports/ceo-updates/*.html` for the report list (line ~5840),
- renders a `<div class="kpis">` row of three `.kpi` tiles — CEO reports / Weekly default / Evidence repos.

The streak inputs live in the **sibling `.json`** files, not the HTML. Everything needed already exists:

| Primitive | Location | Use |
|---|---|---|
| `CEO_REPORT_TYPES = ("weekly", "ad_hoc")` | `scripts/dzcto_artifact.py` | distinguishes typed from legacy-untyped reports |
| `report_effective_date(json_path, data)` | same | `window.end` → ISO filename prefix → `None` |
| `date_value(value)` | same | ISO string → `dt.date`, `None` on garbage (never raises) |
| `read_json_file(path, default)` | same | tolerant read, `default` on `JSONDecodeError` |
| `parse_cadence_rules(cadence_path)` | same | parses `core/OPERATING_CADENCE.md` "Index Cadence Rules" into `{folder, interval_days, …}` |
| `cadence_days(value)` | same | `"weekly"` → 7, `"every 2 weeks"` → 14 |
| `esc(value)` | same | HTML escaping for all interpolated tile text |

`render_index(wiki_root, project_folder)` takes **no reference date**. `cadence_alerts()` does (`today: dt.date`), and `scripts/dzcto.py` supplies `dt.date.today()` at each call site. `render_index` is called once, from `main()` in `scripts/dzcto_artifact.py`.

`rg -i streak` returns zero hits — no dead-but-complete machinery to reuse (the audit that `docs/solutions/best-practices/audit-for-dead-but-complete-machinery-2026-07-03.md` asks for was run; this is genuinely new).

### Research grounding

- `docs/solutions/design-patterns/cadence-scoped-prior-report-selection-2026-07-03.md` — the closest prior art. `locate_prior_report()` already scopes a candidate pool by `report_type == "weekly"`, orders by effective date, excludes `data.json`, and treats untyped legacy reports as `ad_hoc`. Mirror those idioms rather than re-deriving them.
- `docs/solutions/architecture-patterns/helper-computes-agent-narrates-2026-07-03.md` — "anything checkable is computed by the helper." The streak is a checkable mechanical fact; it belongs entirely in the deterministic renderer, never in a SKILL.md or agent prose. No skill file changes.
- `docs/solutions/logic-errors/python-numeric-metric-delta-gotchas-2026-07-03.md` — wrap *parsing*, not just I/O; find edge cases by executing them, not by reasoning about them.
- `AGENTS.md` — "Keep cards for action summaries, KPIs, repeated dashboard objects." A fourth `.kpi` tile is the sanctioned surface. Validation is `python3 -m unittest discover -s tests` (unittest, **not** pytest).

---

## Key Technical Decisions

### KTD1. The streak is anchored to today, not to the latest report

`weekly_streak(dates, today, cadence_days)` takes an explicit `today`. If the most recent weekly report is two or more cadence periods behind `today`, the streak is **0** — the ritual lapsed. This is the load-bearing decision, and it follows directly from the issue's purpose (a nudge) and the North Star's present tense.

Consequence: `render_index()` needs a reference date it does not currently have. See U2.

Rejected alternative: count the run ending at the latest report regardless of age. Simpler, needs no plumbing, and wrong — it would show "3 weeks" to a user who last reported in April.

### KTD2. Consecutiveness is period bucketing, not pairwise gap measurement

Assign each weekly report a **period index** relative to the newest weekly report, rounding to the nearest cadence period:

    period(d) = round( (latest - d).days / cadence_days )

The streak is the length of the unbroken run of period indices starting at 0 (`0, 1, 2, …`), stopping at the first missing index.

This single rule does four jobs at once:

- **Overlap tolerance.** Rolling windows drifting a day or two land in the same period. With `cadence_days = 7`: a gap of 0–3 days is the same period, 4–10 days is the next period, 11+ days skips a period and breaks the streak. The boundary sits exactly halfway between "one period late" and "two periods" — the only tolerance that treats a late report as continuing and a missed week as a break.
- **Rerun de-duplication.** Two reports three days apart collapse into one period, so reruns cannot inflate the count.
- **Gap detection.** A missing period index *is* the gap week.
- **Liveness (KTD1).** Apply the same function to `today`: if `period_of(today) >= 2` relative to the latest weekly report, the user has missed a whole period → streak 0.

Implement the rounding as integer arithmetic — `(delta * 2 + cadence) // (2 * cadence)` — **not** Python's `round()`, which uses banker's rounding and would map a 3.5-period delta inconsistently.

### KTD3. Cadence comes from the configured rule, with 7 as the fallback

The acceptance criterion says "the configured weekly cadence." The configured cadence for the report folder lives in `core/OPERATING_CADENCE.md`, already parsed by `parse_cadence_rules()` into `interval_days`. Resolve in this order:

1. the `interval_days` of the cadence rule whose `folder` matches the report folder (`ceo-updates`), if such a rule exists;
2. otherwise `7`, as a named constant.

**The fallback is the common case, and that is expected.** `dzcto init` does not seed an `Index Cadence Rules` table — `dzcto doctor` warns "No Index Cadence Rules found in `core/OPERATING_CADENCE.md`" and points the user at `refine-core-context` to author one. So step 1 fires only for users who have configured their cadence explicitly. That is precisely the population the acceptance criterion's "configured weekly cadence" refers to; step 2 serves everyone else. Because the configured path is rarely exercised by real data, U1 must cover it with an explicit fixture (see test scenarios) rather than leave it as an unreachable branch.

`weeklyReportDefaults.range` is **not** a cadence source — values like `"last_7_days"` or `"Fri-Thu"` describe the *window shape*, not the repeat interval, and `cadence_days()` returns `None` for both.

Do **not** additionally apply the rule's `grace_days`. KTD2's rounding already carries a half-period tolerance; stacking `grace_days` on top would double-count it and let an 11-day gap read as continuous.

### KTD4. Two functions: a tolerant collector and a pure counter

Split IO from arithmetic so the arithmetic is trivially testable and the IO is trivially tolerant:

- `weekly_report_dates(reports_dir) -> list[dt.date]` — glob `*.json`, skip `data.json`, skip unreadable/non-dict payloads, keep only `report_type == "weekly"` (via `CEO_REPORT_TYPES`, so legacy untyped and `ad_hoc` both drop out), resolve each date with `report_effective_date()` + `date_value()`, drop unresolvable ones, de-duplicate, sort **descending (newest first)** — `weekly_streak()` measures every period index against `dates[0]`.
- `weekly_streak(dates, today, cadence_days) -> int` — pure. No filesystem, no config, no clock.

`render_index()` composes them. Tests exercise both directly, which satisfies "verifiable without relying on internal implementation details" without asserting on rendered HTML internals.

### KTD5. Ad-hoc and legacy reports are excluded by filtering, not by special-casing

"Ad-hoc reports neither extend nor break the streak" and "legacy reports are excluded" are the *same* behavior: neither is `report_type == "weekly"`, so neither enters the pool. There is no branch to write for either case, only a filter — and therefore no way for a legacy report to crash the computation.

### KTD6. Zero streak is a call to action, not a scolding

The tile always renders. Copy scales with state:

| Streak | Value | Sub |
|---|---|---|
| 0 | `0` | `Start a weekly report` |
| 1–2 | `1` / `2` | `of 3 — North Star` |
| ≥ 3 | actual count | `North Star met` |

`NORTH_STAR_STREAK_WEEKS = 3` is a named constant, not a literal scattered through the template.

---

## High-Level Technical Design

> *This illustrates the intended approach and is directional guidance for review, not implementation specification. The implementing agent should treat it as context, not code to reproduce.*

```
reports/ceo-updates/*.json
        │
        │  skip data.json; skip unreadable; keep report_type == "weekly"
        │  date = report_effective_date() -> date_value(); drop None
        ▼
   weekly_report_dates()  ──> [2026-06-25, 2026-06-18, 2026-06-11, 2026-05-21]
        │
        │  cadence = rule.interval_days for "ceo-updates", else 7
        ▼
   weekly_streak(dates, today=2026-06-29, cadence=7)

        latest = 2026-06-25
        liveness: period(today - latest = 4d) = 1  -> < 2, streak is live
        periods:  06-25 -> 0
                  06-18 -> 1
                  06-11 -> 2
                  05-21 -> 5      <- 3 and 4 missing: gap week, stop
        run from 0: {0,1,2}       -> streak = 3
        ▼
   render_index() -> fourth .kpi tile
```

Worked liveness cases (`cadence = 7`), for the test table:

| latest weekly | today | `period(today − latest)` | streak |
|---|---|---|---|
| 2026-06-25 | 2026-06-26 | 0 | live |
| 2026-06-25 | 2026-07-05 | 1 | live (10 days — late, not lapsed) |
| 2026-06-25 | 2026-07-06 | 2 | **0 — lapsed** |

---

## Files

- Modify: `scripts/dzcto_artifact.py` — add `NORTH_STAR_STREAK_WEEKS`, `DEFAULT_WEEKLY_CADENCE_DAYS`, `weekly_report_dates()`, `weekly_streak()`, `resolve_weekly_cadence_days()`; add `today` parameter and the KPI tile to `render_index()`
- Modify: `tests/test_dzcto_artifact.py` — add `TestWeeklyStreak` and `TestWeeklyReportDates`
- Modify: `AGENTS.md` — index-contents editing rule
- Modify: `CONCEPTS.md` — `### Weekly streak` under `## Reports`

---

## Plan

### U1. Streak primitives in `dzcto_artifact.py`

**Goal:** A tolerant collector and a pure counter, with no rendering concerns.

**Dependencies:** None.

**Files:**
- Modify: `scripts/dzcto_artifact.py`
- Test: `tests/test_dzcto_artifact.py`

**Approach:**
- Add `DEFAULT_WEEKLY_CADENCE_DAYS = 7` and `NORTH_STAR_STREAK_WEEKS = 3` next to `CEO_REPORT_TYPES`.
- `weekly_report_dates(reports_dir: Path) -> list[dt.date]` per KTD4. Sort descending; de-duplicate. Every skip is silent (the index write path is warn-never-fail) — but skipping an unreadable candidate may log to stderr, mirroring `locate_prior_report()`'s existing `print(..., file=sys.stderr)` for the same condition.
- `weekly_streak(dates, today, cadence_days) -> int` per KTD1/KTD2. Guard `cadence_days <= 0` → treat as `DEFAULT_WEEKLY_CADENCE_DAYS`. Empty list → 0. A single live weekly → 1.
- `resolve_weekly_cadence_days(core_dir, report_folder) -> int` per KTD3, built on `parse_cadence_rules()`.
- Integer rounding, not `round()`. Add a one-line comment naming banker's rounding as the reason, so a future reader does not "simplify" it back.

**Execution note:** Write the `weekly_streak` period table (the worked cases above) as failing tests first. This function is pure arithmetic over dates — the class of bug `python-numeric-metric-delta-gotchas` documents is exactly what a hand-checked table catches and eyeballing does not.

**Patterns to follow:**
- `locate_prior_report()` — candidate-pool construction, `data.json` exclusion, untyped-as-non-weekly coercion, stderr skip logging.
- `date_value()` / `read_json_file()` — tolerant parsing that returns `None`/default rather than raising.

**Test scenarios** (`TestWeeklyStreak`, pure — no filesystem):
- Happy path: three weeklies at 7-day spacing, `today` one day after the latest → `3`.
- Happy path: single live weekly → `1`.
- Edge case: empty list → `0`.
- Edge case: latest weekly 10 days before `today` → streak still counts (late, one period).
- Edge case: latest weekly 11 days before `today` → `0` (lapsed — the KTD1 boundary).
- Edge case: two reports 3 days apart collapse to one period → `2` for a three-file set, not `3` (rerun de-duplication).
- Edge case: 7, 7, **14**, 7 spacing → streak stops at the 14-day gap, returns the run before it.
- Edge case: duplicate identical dates → counted once.
- Edge case: `cadence_days = 14` → 14-day spacing continues the streak, 7-day spacing collapses into one period.
- Edge case: `cadence_days = 0` → falls back to 7 rather than dividing by zero.

**Test scenarios** (`TestWeeklyReportDates`, on a `tempfile` fixture, using the existing `v1_report()` / `write_report()` helpers):
- Happy path: two weekly reports → both dates, newest first.
- Edge case: `data.json` present with `report_type: "weekly"` → excluded.
- Edge case: `report_type: "ad_hoc"` → excluded.
- Error path: report with **no** `report_type` key (legacy) → excluded, no exception.
- Error path: report with `window.end: "not-a-date"` and no ISO filename prefix → skipped, no exception.
- Error path: file containing invalid JSON → skipped, no exception.
- Edge case: report with no `window` but an ISO filename prefix → date resolved from the filename.
- Edge case: empty directory, and non-existent directory → `[]` both times.

**Test scenarios** (`resolve_weekly_cadence_days`, on a `tempfile` `core/` directory):
- Happy path: an `OPERATING_CADENCE.md` containing an `## Index Cadence Rules` table with a `ceo-updates` row at `every 2 weeks` → `14`. This is the only coverage the configured path gets, since a fresh workspace never has the table. **The fixture row must populate the `command` column too** — `parse_cadence_rules` requires `folder and cadence and command and interval_days` all truthy before it emits a rule, so a row missing `command` silently yields no rule and the test would assert the fallback while appearing to test the configured path.
- Edge case: no `OPERATING_CADENCE.md` at all → `7`.
- Edge case: file present but no `Index Cadence Rules` section → `7`.
- Edge case: table present but no row for the report folder → `7`.

**Verification:**
- `python3 -m unittest discover -s tests` passes.
- No caller yet; `python3 -m py_compile scripts/dzcto_artifact.py` clean.

---

### U2. Render the streak tile in `render_index()`

**Goal:** Surface the streak as a fourth KPI tile, and give `render_index()` the reference date KTD1 requires.

**Dependencies:** U1.

**Files:**
- Modify: `scripts/dzcto_artifact.py`
- Test: `tests/test_dzcto_artifact.py`

**Approach:**
- Change the signature to `render_index(wiki_root, project_folder, today: dt.date | None = None)`; resolve `today or dt.date.today()` inside. The default keeps the single existing call site in `main()` unchanged and lets tests pin the date. This mirrors how `cadence_alerts()` already takes an explicit `today` while `scripts/dzcto.py` supplies `dt.date.today()`.
- Compose: `cadence = resolve_weekly_cadence_days(core_dir, report_folder)`; `streak = weekly_streak(weekly_report_dates(reports_dir / report_folder), today, cadence)`.
- Insert the tile into the existing `<div class="kpis">` block, after the "CEO reports" tile. Non-linking `<div class="kpi">`, matching the "Weekly default" and "Evidence repos" tiles. Every interpolated value goes through `esc()`.
- Label/value/sub copy per KTD6.

**Patterns to follow:**
- The three existing `.kpi` tiles in `render_index()`'s `content` f-string.
- `AGENTS.md`: KPIs are cards; report list sections are not.

**Test scenarios** (new index-level class; render into a `tempfile` wiki root):

> **Do not reach for the familiar `run_cli` / `generate` helpers here.** `TestArtifactWritePath` drives the CLI in a **subprocess**, which resolves `today` from the wall clock and cannot pin it — so live-vs-lapsed scenarios are unwritable that way. Call `artifact.render_index(workspace, workspace, today=<pinned date>)` **in-process** instead.
>
> No scaffolding is needed: `render_index()` runs against a bare temp directory containing only `reports/ceo-updates/` (`project_config` returns `{}`, `company_name` falls back to the folder name, `ensure_sidecar` creates `.dzcto/`). Verified by execution during planning.

- Happy path: two consecutive weeklies + pinned `today` → rendered `index.html` contains the streak label and the value `2`.
- Happy path: three consecutive weeklies → sub-text reads as North Star met, not `of 3`.
- Edge case: zero reports → tile renders with `0` and the call-to-action sub-text; the page does not crash.
- Edge case: lapsed streak (latest weekly 11+ days before pinned `today`) → tile shows `0`.
- Integration: a `reports/ceo-updates/` directory containing one malformed JSON alongside two good weeklies → `index.html` is still written, streak counts the two good ones. This is the warn-never-fail contract, and it is the scenario mocks would not prove.

**Verification:**
- `python3 -m unittest discover -s tests` passes.
- `dzcto artifact --artifacts-dir <tmp> --kind ceo-updates --data-file <fixture>` writes an index whose KPI row contains the streak tile (the smoke test `AGENTS.md` asks for after artifact-behavior changes).

> **Expect the smoke test to print `0`.** The CLI resolves `today` from the wall clock, and the `v1_report()` fixture windows are dated June 2026 — more than one period back, so the streak is correctly *lapsed*. The smoke test proves the tile renders; it says nothing about the count. Only the in-process, date-pinned tests can assert a positive streak. Do not "fix" a `0` here.

---

### U3. Document the streak

**Goal:** Keep the two files that describe the index and the domain vocabulary honest.

**Dependencies:** U2.

**Files:**
- Modify: `AGENTS.md`
- Modify: `CONCEPTS.md`

**Approach:**
- `AGENTS.md`: extend the existing editing rule "The index should link CEO reports, show the weekly defaults and tone, and expose copyable prompts…" to include the weekly streak.
- `CONCEPTS.md`: add `### Weekly streak` under `## Reports`, defining it as the count of consecutive cadence periods ending at today that contain a `weekly` report — a best-effort local signal, not the canonical North Star metric (per the issue's stated constraint).

**Test expectation:** none — documentation only, no behavioral change.

**Verification:**
- `CONCEPTS.md` defines the term a reader would hit in the tile.
- No skill files touched (KTD / `helper-computes-agent-narrates`): the streak is renderer-computed, so no `SKILL.md` schema-lockstep test is implicated.

---

## Assumptions

- `report_type: "weekly"` reports are produced on a weekly cadence by construction (`/dzcto-ceo-report-weekly`). A user who configures `ceo-updates` to a non-weekly cadence in `OPERATING_CADENCE.md` gets a streak measured in *their* configured periods — which is the literal reading of the acceptance criterion, and the behavior KTD3 delivers.
- Most workspaces have no `Index Cadence Rules` table (it is user-authored, not seeded by `init`), so most users get the `7`-day fallback. Verified against `scripts/dzcto.py`, where `doctor` warns on its absence.
- `render_index()` has exactly one caller (`main()` in `scripts/dzcto_artifact.py`). Verified by grep; the defaulted parameter makes this safe even if that changes.
- No golden/snapshot test currently locks `index.html`, so adding a KPI tile breaks nothing. Verified: `tests/test_dzcto_artifact.py` has no index-HTML assertions.

---

## Risks

| Risk | Mitigation |
|---|---|
| The rounding boundary (3 vs 4 days into the next period) is a judgment call and could surprise a user who reruns mid-week | It is the midpoint rule, documented in KTD2 and pinned by an explicit test table. Reruns of the *same* window overwrite the same file, so the common case never reaches the boundary. |
| `render_index()` gaining a parameter is an API change to a module-level function | Defaulted to `None` → `dt.date.today()`. The single caller is unchanged. |
| A malformed report JSON aborts the index write | U1 skips every unresolvable candidate; U2's integration test asserts the index is still written. Follows the warn-never-fail contract `validate_ceo_report()` already establishes. |
| Banker's rounding via `round()` silently shifts a boundary case | Integer arithmetic instead, with a comment naming the reason so it is not "simplified" back. |

---

## Scope Boundaries

- No telemetry, remote reporting, or persistence of the streak — it is recomputed from JSON on every index render.
- No auto-created issues, no scheduled audits.
- No change to the report JSON schema, `validate_ceo_report()`, or any `SKILL.md`. The streak is derived, not authored.
- No change to `locate_prior_report()` or the week-over-week diff machinery, despite the shared primitives.
- The tile does not attempt to detect the North Star's stated exclusions (test runs, unopened reports, no-work windows) — per the issue's constraint, those are not locally detectable.

---

## Open Questions

### Resolved during planning

- **Anchor to today or to the latest report?** Today. See KTD1 — anchoring to the latest report would congratulate a lapsed user indefinitely, inverting the feature's purpose.
- **What tolerance makes a streak "consecutive" when windows overlap by design?** Round-to-nearest cadence period; a skipped period index is the gap week. See KTD2.
- **Where does "the configured weekly cadence" come from?** `core/OPERATING_CADENCE.md` via `parse_cadence_rules()`, falling back to 7. Not `weeklyReportDefaults.range`, which describes window shape rather than repeat interval. See KTD3.
- **Does `render_index()` need plumbing for `today`?** Yes — it has no reference date today. Optional parameter, defaulted. See U2.
- **How do ad-hoc and legacy reports get handled without special-casing?** They are filtered out of the pool by the same `report_type == "weekly"` predicate. See KTD5.

### Deferred to implementation

- Exact tile copy strings and whether the sub-text needs a `title`/tooltip attribute — settle against the rendered page, not on paper.
- Whether `weekly_report_dates()` should log skipped candidates to stderr as `locate_prior_report()` does, or stay fully silent. The index renders on every command, so the noise budget is different; decide once the smoke test shows the real volume.

---

## Verification Contract

- `python3 -m unittest discover -s tests` passes, including `TestWeeklyStreak` and `TestWeeklyReportDates`.
- `python3 -m py_compile scripts/dzcto_artifact.py` is clean.
- `dzcto artifact --artifacts-dir <tmp> --kind ceo-updates --data-file <fixture>` renders an index whose KPI row contains a streak tile (value will read `0` — see U2).
- An artifact directory containing a malformed report JSON still produces `index.html`.

---

## Definition of Done

The acceptance criteria live on DAYZEROCTO-5. This plan is done when the engineering work that satisfies them is in place:

- U1–U3 landed; `python3 -m unittest discover -s tests` and `py_compile` both clean.
- `TestWeeklyStreak` pins the full period table from the High-Level Technical Design, including both sides of the 10-vs-11-day lapse boundary.
- `resolve_weekly_cadence_days` has fixture coverage for the configured path, not just the fallback.
- The malformed-JSON integration case proves the index still writes.
- `AGENTS.md` and `CONCEPTS.md` describe the new index element.

## Decisions

### Preserve half-up cadence bucketing — 2026-07-09

Kept KTD2's explicit integer arithmetic for cadence buckets instead of changing the exact half-period boundary for even cadences. Rejected a test that would make that tie case part of the public behavior; the count-level 14-day cadence test proves the configured cadence path without overfitting an ambiguity.

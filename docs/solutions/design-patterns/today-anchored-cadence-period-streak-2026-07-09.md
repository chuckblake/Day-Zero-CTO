---
title: "Today-anchored streaks via cadence-period bucketing"
date: 2026-07-09
category: design-patterns
module: dzcto_artifact report index
problem_type: design_pattern
component: tooling
severity: medium
applies_when:
  - "Computing a 'current' streak or consecutive-run metric over timestamped artifacts"
  - "The underlying time windows overlap by design or timestamps drift (rolling lookbacks, reruns)"
  - "A 'current/live' reading must reflect now, not the newest data point"
related_components:
  - testing_framework
  - documentation
tags: [streak, cadence, period-bucketing, today-anchoring, bankers-rounding, testability, warn-never-fail]
---

# Today-anchored streaks via cadence-period bucketing

## Context

DAYZEROCTO-5 needed to surface "the user's current run of consecutive weekly CEO
reports" as a KPI tile on the generated report index (`render_index()` in
`scripts/dzcto_artifact.py`). The issue framed it as "largely assembly of existing
data," but two definitional questions were the real work, and getting either wrong
silently produces a plausible-but-wrong number:

1. **What does "current" mean?** A user who filed three weeklies then went quiet has
   a *historical* run of 3 and a *current* streak of 0.
2. **What does "consecutive" mean when windows overlap?** Weekly report windows
   overlap by design (rolling lookback), so consecutiveness cannot mean exact 7-day
   spacing, and it cannot mean file adjacency — two reruns three days apart would
   read as "week 2."

## Guidance

Five design moves, each of which resolves one of the traps above.

### 1. Anchor the streak to `today`, not to the latest artifact

"Current streak" has two defensible readings, and only one serves a nudge: anchor to
the reference date, not the newest report. If the most recent qualifying report is
two or more cadence periods behind `today`, the streak is **0** — the ritual lapsed.
Anchoring to the latest report instead congratulates a lapsed user forever, inverting
the feature's purpose.

This forced plumbing an explicit `today` parameter into `render_index()`, which
previously had no reference date. Default it so existing callers are untouched, and
resolve the clock at the boundary:

```python
def render_index(wiki_root: Path, project_folder: Path, today: dt.date | None = None) -> None:
    ...
    today = today or dt.date.today()
```

The dependency-injected `today` is not incidental — **it is what makes the whole
computation testable**. Live-vs-lapsed scenarios can only be pinned by calling
`render_index(..., today=<fixed date>)` in-process.

### 2. Bucket into rounded cadence periods instead of measuring pairwise gaps

Assign each report a **period index** relative to the newest one, rounding to the
nearest cadence period; the streak is the unbroken run of indices `{0, 1, 2, ...}`,
stopping at the first missing index.

```python
period(d) = round((latest - d).days / cadence_days)
```

One rule does four jobs at once:

- **Overlap tolerance** — windows drifting a day or two land in the same period.
- **Rerun de-duplication** — two reports 3 days apart collapse into one period, so
  reruns cannot inflate the count.
- **Gap detection** — a missing period index *is* the gap week.
- **Liveness** — apply the same function to `today`; if its period index relative to
  the latest report is `>= 2`, a whole period was missed → streak 0.

### 3. Round with integer half-up arithmetic, never `round()`

Python's built-in `round()` uses banker's rounding, which maps the half-period
boundary inconsistently. Use integer arithmetic and comment *why*, so a future reader
doesn't "simplify" it back and silently shift a boundary case:

```python
def rounded_period_index(delta_days: int, cadence_days_value: int) -> int:
    # Avoid Python's banker's rounding; cadence buckets need stable half-up periods.
    return (delta_days * 2 + cadence_days_value) // (2 * cadence_days_value)
```

The exact behavior of the half-period tie on *even* cadences was deliberately **not**
made part of the public contract (no test pins it) — that ambiguity is a judgment
call, and locking it would be an overfit, brittle test. Don't add one.

### 4. Split a tolerant collector from a pure counter

Separate IO from arithmetic so each is trivially testable in its own way:

- `weekly_report_dates(reports_dir) -> list[dt.date]` — tolerant collector. Globs
  `*.json`, skips `data.json`, skips unreadable/non-dict payloads, keeps only
  `report_type == "weekly"`, resolves each date, drops unresolvable ones,
  de-duplicates, sorts newest-first. **Every skip is silent-to-the-user** (a
  stderr note at most): the index write path is warn-never-fail, so one malformed
  report must never abort the render.
- `weekly_streak(dates, today, cadence_days) -> int` — pure. No filesystem, no
  config, no clock. Test it with a hand-checked period table, because this is exactly
  the class of arithmetic-over-dates bug that eyeballing misses.

### 5. Exclude by filtering, not by special-casing

"Ad-hoc reports neither extend nor break the streak" and "legacy untyped reports are
excluded" are the *same* behavior: neither is `report_type == "weekly"`, so neither
enters the pool. There is no branch to write for either case — only a filter — and
therefore no way for a legacy report to crash the computation.

## Why This Matters

- **Correctness of a user-facing signal.** Today-anchoring is what makes the tile a
  nudge toward the ritual rather than a vanity badge that never resets. Period
  bucketing is what keeps a rerun or a one-day-late report from either inflating or
  falsely breaking the count.
- **A silent boundary bug is the failure mode.** Banker's rounding doesn't crash — it
  shifts one boundary case, producing a number that looks fine. The integer-arithmetic
  choice plus its comment is a guardrail against a well-meaning future "cleanup."
- **Testability is a design property, not an afterthought.** The pure counter and the
  injected `today` exist so the behavior can be pinned deterministically. A function
  that reads the wall clock internally cannot be tested for lapse behavior at all.

## When to Apply

- Any "current streak," "consecutive N," or "still-active run" metric derived from
  timestamped artifacts.
- Whenever the source timestamps can overlap, drift, or duplicate (rolling windows,
  reruns, idempotent regenerations).
- Whenever "current" must mean *as of now* rather than *as of the last data point*.

## Testing traps (learned here)

Three verification hazards surfaced during this work — each is a "green test that
proves nothing" or a misread-signal risk worth reusing as a checklist:

1. **A rarely-populated config path needs a fully-populated fixture.** Cadence is read
   from a user-authored `core/OPERATING_CADENCE.md` "Index Cadence Rules" table that
   `init` does not seed — so the 7-day fallback is the common case. `parse_cadence_rules`
   only emits a rule when `folder AND cadence AND command AND interval_days` are all
   truthy. A fixture that omits the `command` column silently yields *no* rule, so the
   test exercises the fallback while *appearing* to test the configured path and still
   passing. When testing a rarely-hit branch, populate **every** field the parser
   requires, and assert a value that only the configured path can produce (e.g. a
   14-day cadence, not 7).

2. **A subprocess CLI test cannot pin `today`.** The end-to-end tests drive the CLI in
   a subprocess, which reads `today` from the wall clock. With fixtures dated in the
   past, the CLI smoke test *correctly* prints `0` (lapsed) — that is not a bug to
   "fix." Positive-streak assertions require the in-process, date-pinned call
   (`render_index(..., today=<pinned>)`).

3. **Execute feasibility claims; don't assert them.** The plan claimed `render_index()`
   needed an `--init`-scaffolded wiki root; review falsified it by running it against a
   bare temp dir (`project_config` returns `{}`, `company_name` falls back to the
   folder name). A one-line execution beats a paragraph of reasoning about what the
   code "must" need.

## Examples

Worked period table (`cadence = 7`), which was written as failing tests *first*:

```
dates (newest first): 2026-06-25, 2026-06-18, 2026-06-11, 2026-05-21
today = 2026-06-29

liveness: period(today - latest = 4d) = 1  -> < 2, streak is live
periods:  06-25 -> 0
          06-18 -> 1
          06-11 -> 2
          05-21 -> 5     <- indices 3 and 4 missing: gap, stop
run from 0: {0, 1, 2}    -> streak = 3
```

Liveness boundary (the load-bearing `today`-anchoring cases):

| latest weekly | today      | period(today − latest) | streak         |
|---------------|------------|------------------------|----------------|
| 2026-06-25    | 2026-06-26 | 0                      | live           |
| 2026-06-25    | 2026-07-05 | 1                      | live (10d — late, not lapsed) |
| 2026-06-25    | 2026-07-06 | 2                      | **0 — lapsed** |

## Related

- `docs/solutions/design-patterns/cadence-scoped-prior-report-selection-2026-07-03.md`
  — closest prior art; shares the `report_type == "weekly"` filtering, effective-date
  resolution, and `data.json` exclusion idioms, but solves prior-report selection for
  diffing rather than streak counting. Note the deliberate anchor difference:
  prior-selection anchors to a report's `window.end` / effective date, whereas the
  streak anchors to **today** so a lapse registers even when no new report exists.
- `docs/solutions/logic-errors/python-numeric-metric-delta-gotchas-2026-07-03.md`
  — the "wrap parsing, find edge cases by executing them" discipline that the banker's
  rounding trap and the pure-counter test table both apply.
- `docs/solutions/architecture-patterns/helper-computes-agent-narrates-2026-07-03.md`
  — "anything checkable is computed by the helper"; the streak is a mechanical fact,
  so it lives entirely in the deterministic renderer, never in agent prose.
- `plans/dayzerocto-5-feature-show-consecutive-weekly-report-streak.md` — the plan
  (KTD1–KTD6) and commit `9f7b3da`.

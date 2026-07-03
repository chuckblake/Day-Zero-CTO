---
title: Cadence-scoped prior-report selection for period-over-period diffs
date: 2026-07-03
category: design-patterns
module: ceo-report
problem_type: design_pattern
component: tooling
severity: medium
applies_when:
  - "Generating period-over-period (week-over-week, month-over-month) diffs between report artifacts"
  - "Reports of mixed cadences (weekly, ad hoc, legacy untyped) live in the same folder"
  - "A regenerated report must not silently re-select a different comparison baseline"
tags: [report-diffing, week-over-week, prior-selection, cadence, provenance]
---

# Cadence-scoped prior-report selection for period-over-period diffs

## Context

The week-over-week section in CEO reports needs a "prior report" to diff against. The naive approach — most recent file by name — is cadence-blind: a weekly report could diff against yesterday's ad hoc report, producing a meaningless "week"-over-week. The selection logic in `locate_prior_report()` (`scripts/dzcto_artifact.py:2482`) encodes several decisions that survived adversarial review.

## Guidance

**1. Scope the prior pool by cadence first.** A weekly report diffs against the most recent prior *weekly*, ordered by effective date (`window.end`, falling back to the ISO filename prefix — see `report_effective_date`, `scripts/dzcto_artifact.py:2469`):

```python
if current_type == "weekly":
    # Same-cadence comparison orders by window.end with no overlap caveat:
    # rolling-lookback weekly windows overlap by design.
    chosen = newest([c for c in candidates if c[4] == "weekly" and c[0] < current_end])
```

Note the deliberate absence of an overlap warning within the same cadence: rolling-lookback weekly windows overlap by design, so overlap there is not an anomaly worth flagging.

**2. Fall back across cadences, but say so accurately.** When no prior weekly exists, fall back to the most recent report of any type — and distinguish *why* in the note shown to the reader:

```python
if weekly_pool_missed and cand_type != "weekly":
    # Name the situation accurately: untyped legacy priors predate cadence tagging;
    # a typed ad_hoc prior is simply not a weekly.
    notes.insert(0, "cadence_fallback" if cand.get("report_type") not in CEO_REPORT_TYPES else "no_weekly_prior")
```

```python
CHANGE_NOTE_TEXT = {
    "cadence_fallback": "Prior report predates cadence tagging.",
    "no_weekly_prior": "No prior weekly report — compared against the most recent report of any type.",
    "overlap": "Overlapping windows — deltas may double-count.",
}
```

An untyped legacy report gets "predates cadence tagging"; a typed ad hoc report gets "no prior weekly". Same code path, different honest explanations.

**3. Use `<=` in the last-resort fallback so same-day priors are found.** Strict `<` would make a second report generated the same day (different window) claim "first report — no baseline", which is false:

```python
# "<=" so a same-day prior (equal effective date, different window) is still
# found instead of falsely claiming "first report"; self and same-window
# reruns were already excluded above.
chosen = newest([c for c in candidates if c[0] <= current_end])
if chosen is not None:
    notes.append("overlap")
```

**4. Freeze the choice at write time.** The selected prior's path is recorded in the emitted report JSON (`structured_data["prior_report"]`, `scripts/dzcto_artifact.py:6168`) as an audit trail; nothing ever re-selects it. The diff chain is provenance, not a query result — any future re-render must honor the recorded baseline rather than re-running selection.

## Why This Matters

- Cadence-blind selection produces diffs that look authoritative but compare incomparable windows — worst-case in a CEO-facing artifact.
- Accurate fallback notes preserve trust: the report never claims a comparison it did not make.
- Freezing `prior_report` in the JSON makes the diff chain reproducible and auditable; the recorded baseline cannot be silently rewritten later.

## When to Apply

- Any artifact pipeline that diffs the current output against a prior one, where outputs have types/cadences
- When adding new report types: extend the scoped pool logic, don't bypass it
- When tempted to "just take the newest file" as a baseline

## Examples

Covered by `TestLocatePriorReport` and `TestReportChangesHtml` in `tests/test_dzcto_artifact.py` (weekly-scoped selection, fallback notes, same-day `<=` behavior).

## Related

- docs/solutions/architecture-patterns/helper-computes-agent-narrates-2026-07-03.md — who renders the diff this selection feeds
- docs/ceo-report-template.md — the canonical template whose week-over-week section consumes this selection

---
title: Python numeric gotchas in metric delta rendering (scientific notation, bool, NaN, OverflowError)
date: 2026-07-03
category: logic-errors
module: ceo-report
problem_type: logic_error
component: tooling
symptoms:
  - "Integer metrics at ARR scale (>= 1e6) rendered in scientific notation (1.2e+06) in CEO reports"
  - "Boolean metrics entered numeric delta math because Python bool is a subclass of int"
  - "An unchanged NaN metric rendered a phantom week-over-week delta on every run (NaN != NaN)"
  - "A huge int metric (10**400) raised OverflowError through float formatting and could abort the report write"
root_cause: logic_error
resolution_type: code_fix
severity: high
tags: [python, string-formatting, nan, bool, overflow, metrics, warn-never-fail]
---

# Python numeric gotchas in metric delta rendering

## Problem

The metric delta path in the CEO report renderer (dead code wired up for DAYZEROCTO-1) had four latent numeric bugs — none visible in happy-path testing, all caught by adversarial review and then verified by execution.

## Symptoms

- `f"{value:g}"` renders `1200000` as `1.2e+06` — exactly the ARR-scale numbers a CEO report exists to show.
- `isinstance(True, int)` is `True`, so a boolean metric passes an `(int, float)` type check and produces nonsense arithmetic (`True - False`).
- `json.loads` accepts bare `NaN`/`Infinity` (a Python extension beyond strict JSON), and since `NaN != NaN`, an *unchanged* NaN metric compares as changed and renders a phantom delta forever.
- `f"{10**400:g}"` raises `OverflowError` (int too large for the float path) — in a warn-never-fail write path, one absurd metric could abort the entire report write.

## What Didn't Work

- Using `:g` uniformly for "compact" numeric formatting — compact until the number matters most.
- Gating on `isinstance(value, (int, float))` alone — bool slips through.
- Detecting change via `value != prior` alone — NaN makes inequality unreliable.
- Assuming formatting can't raise — huge ints only fail when routed through float machinery.

## Solution

All four guards live in `format_metric_value` and `metric_delta_items` (`scripts/dzcto_artifact.py:1846-1881`):

```python
def format_metric_value(value: int | float, signed: bool = False) -> str:
    # Ints get thousands separators (":g" would render CEO-scale numbers like ARR
    # in scientific notation); floats keep the compact ":g" form.
    if isinstance(value, int):
        return f"{value:+,}" if signed else f"{value:,}"
    return f"{value:+g}" if signed else f"{value:g}"
```

```python
        if isinstance(value, bool) or isinstance(prior, bool):
            continue
        if not isinstance(value, (int, float)) or not isinstance(prior, (int, float)):
            continue
        if isinstance(value, float) and not math.isfinite(value):
            continue  # NaN != NaN would render a phantom delta on every run
        if isinstance(prior, float) and not math.isfinite(prior):
            continue
        if value == prior:
            continue
        try:
            rendered = (...)
        except (OverflowError, ValueError):
            continue  # e.g. int too large for float math — skip the delta, never abort the write
```

Ordering matters: the `bool` exclusion must precede the `(int, float)` check; the `math.isfinite` guards must precede the `value == prior` comparison.

## Why This Works

- Ints get `{:,}` (grouping, never scientific); only floats keep `:g`.
- Explicit `bool` exclusion closes the subclass loophole before any numeric logic runs.
- `math.isfinite` filters NaN/Infinity before equality comparison, so non-finite values can never produce a delta at all.
- `try/except (OverflowError, ValueError)` around the formatting honors the path's contract: warn or skip, never fail the write.

## Prevention

- In any warn-never-fail write path, wrap *formatting* — not just I/O — in try/except; formatting can raise.
- Treat `bool`-before-`int` and `isfinite`-before-`==` as standard guards whenever doing arithmetic on JSON-sourced "numbers".
- Regression tests in `tests/test_dzcto_artifact.py` (`TestReportChangesHtml`): `test_large_int_metrics_render_with_separators_not_scientific` (asserts `1,200,000 → 1,534,500` and `assertNotIn("e+", html)`), `test_huge_int_metric_never_aborts_rendering` (10**400), `test_nonfinite_and_bool_metrics_are_skipped`.
- Process note: all four were found by adversarial review of resurrected dead code and confirmed by actually executing the failure case before fixing — review claims about numeric edge cases should be execution-verified, not accepted from reasoning alone.

## Related Issues

- docs/solutions/best-practices/audit-for-dead-but-complete-machinery-2026-07-03.md — why this code was unvetted despite existing
- docs/solutions/architecture-patterns/helper-computes-agent-narrates-2026-07-03.md — the delta path these guards harden

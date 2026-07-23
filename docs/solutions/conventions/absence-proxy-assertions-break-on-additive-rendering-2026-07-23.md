---
title: "An absence-proxy assertion silently breaks when a new line legitimately uses the sentinel"
date: 2026-07-23
category: conventions
module: dzcto-renderer
problem_type: convention
component: testing
severity: medium
applies_when:
  - "Adding a new rendered line to a section that an existing test asserts over as a whole"
  - "A test asserts assertNotIn(<character>, html) as shorthand for 'this feature did not render'"
  - "Choosing the phrasing/separator for a new renderer output line"
symptoms:
  - "An unrelated test fails after adding a purely additive rendered line"
  - "A test named for feature A fails when feature B is added to the same section"
related_components: [documentation, development_workflow]
tags: [testing, proxy-assertion, renderer, week-over-week, additive-change, sentinel]
---

# An absence-proxy assertion silently breaks when a new line legitimately uses the sentinel

## Context

DAYZEROCTO-12 added a window-length disclosure line to the CEO report's week-over-week section
(`report_changes_html`, `scripts/dzcto_artifact.py`). The obvious phrasing mirrored the metric-delta
format already used one line below:

```
Window: 9 days (2026-07-15 → 2026-07-23); prior 7 days.
```

That phrasing would have failed `tests/test_dzcto_artifact.py::test_disjoint_metrics_render_no_delta`,
which asserts:

```python
self.assertNotIn("→", html)
```

The test is about **metric deltas**: when the current and prior reports share no numeric metric keys,
no delta should render. Rather than assert on the specific delta markup, it uses `→` as a *sentinel*
— a cheap proxy for "no delta line exists", valid only while `→` appears nowhere else in that
section's output.

The new line was in the same section and would have used the same character. The failure would have
read as a regression in metric-delta logic, in a test whose name mentions neither windows nor
rendering, on a branch that never touched `metric_delta_items`.

## Guidance

**Before adding a rendered line to an existing section, grep that section's tests for
`assertNotIn` / `refute_includes` on short strings or single characters.** A proxy assertion is
invisible from the production code — nothing in `report_changes_html` says "`→` is load-bearing for a
test three files away." The only way to find it is to look.

**Prefer a separator the section does not already use semantically.** DAYZEROCTO-12 shipped
`(2026-07-15 to 2026-07-23)` instead. That was not a cosmetic preference: `to` keeps the sentinel
meaningful, so `test_disjoint_metrics_render_no_delta` continues to test what it claims to.

**When a proxy assertion is genuinely in the way, tighten it rather than widen the production
output.** Prefer `assertNotIn("prs_merged:", html)` or a count of delta `<li>` elements to a bare
character check. Repointing the test at the thing it actually means is a smaller, more honest change
than reshaping rendered output to satisfy a proxy.

**Distinguish this from a real regression.** A test that fails because your additive change tripped
its sentinel is not telling you the feature is broken — it is telling you the *test's shorthand* no
longer holds. Read the assertion before "fixing" the feature.

## Why This Matters

Absence-proxy assertions are common because they are cheap to write and usually correct. Their
failure mode is asymmetric and unpleasant: they do not fail when the behavior they guard breaks —
they fail when an **unrelated, correct** change happens to use the sentinel. That inverts the signal.
An engineer who trusts the test name spends the debugging budget in `metric_delta_items`, which is
untouched and fine.

The cost of getting this wrong compounds: the natural "fix" is to relax the assertion to make the new
line pass, which silently deletes the coverage the test existed to provide. The disjoint-metrics case
then stops being checked at all, and nothing reports it.

## When to Apply

- Adding any line to a renderer whose output an existing test asserts over as a whole (a section, a
  page, a serialized blob).
- Choosing separators, arrows, bullets, or punctuation for new rendered output — check whether the
  character already carries meaning in that surface's tests.
- Triaging a test failure whose name has nothing to do with your change: read the assertion body
  before assuming the failure is real.
- Writing a new negative assertion: name the thing you mean (`assertNotIn("prs_merged:", html)`)
  rather than a sentinel that anything nearby could later use.

## Examples

**The trap, as it would have shipped:**

```python
# tests/test_dzcto_artifact.py
def test_disjoint_metrics_render_no_delta(self):
    previous = v1_report(metrics={"deploys": 2})
    html = artifact.report_changes_html("ceo-updates", v1_report(metrics={"prs_merged": 8}), previous, "d")
    self.assertNotIn("→", html)     # sentinel: valid only while nothing else renders an arrow
```

**What shipped instead** — the window line uses `to`, so the sentinel keeps its meaning:

```python
changes.append(
    f"<li><strong>Window:</strong> {esc(pluralize(current_days, 'day'))} "
    f"({esc(current_start.isoformat())} to {esc(current_end.isoformat())}); "
    f"prior {esc(pluralize(prior_days, 'day'))}.</li>"
)
```

**The pinning test added alongside it**, so the constraint is now explicit rather than folklore:

```python
def test_window_line_never_uses_an_arrow(self):
    # test_disjoint_metrics_render_no_delta asserts no "→" anywhere in the output,
    # so the window line must read "start to end" rather than "start → end".
```

## Related

- `../logic-errors/python-numeric-metric-delta-gotchas-2026-07-03.md` — the same
  `metric_delta_items` surface; that entry covers the numeric guards, this one covers the test
  shorthand guarding them.
- `../design-patterns/cadence-scoped-prior-report-selection-2026-07-03.md` — the week-over-week
  section's selection rules, whose output this line now sits above.

---
title: Audit for dead-but-complete machinery before building a feature
date: 2026-07-03
category: best-practices
module: ceo-report
problem_type: best_practice
component: development_workflow
severity: medium
applies_when:
  - "Planning a feature in a codebase that has been through prior iterations or scope cuts"
  - "A feature request sounds like something the codebase may have partially attempted before"
  - "Estimating effort for wiring-style work versus greenfield implementation"
tags: [dead-code, feature-planning, code-audit, estimation]
---

# Audit for dead-but-complete machinery before building a feature

## Context

DAYZEROCTO-1 asked for an automatic week-over-week section in CEO reports. The obvious plan was to build diff machinery from scratch. A pre-implementation audit of `scripts/dzcto_artifact.py` found the machinery already existed as dead code: `report_changes_html()` and the `previous_report_json_path()` prior-locator helper were fully written, but the only caller that ever supplied a prior report — `refresh_structured_report_pages` — itself had **zero call sites**, so the diff path never ran. The feature collapsed from "build a diff engine" into "wire up and harden existing code."

## Guidance

Before implementing a feature, spend a few minutes auditing for dead-but-complete machinery in the same domain:

1. Grep for domain vocabulary the feature would use (`changes`, `previous`, `prior`, `delta`, `diff`, `history`) across the modules you expect to touch.
2. For each hit that looks like real machinery, check for live callers (`grep -n "function_name("` and trace call sites). A complete function with zero callers is a candidate.
3. If found, re-scope the plan: wiring + hardening instead of greenfield. Treat the dead code as untested — it has never run in production, so it needs the same adversarial review a new implementation would get.

```bash
# Example audit from this feature
grep -n "report_changes_html\|previous_report" scripts/dzcto_artifact.py
# -> machinery fully written, but tracing callers showed the only caller that
#    supplied a prior (refresh_structured_report_pages) had no call sites
```

Note that the dead node may be a *caller*, not the machinery itself: here `report_changes_html` had a live call site, but it always received `previous_data=None` — the caller that supplied a real prior was the unreachable one. Trace the whole chain, not just the first hop.

The hardening caveat is not optional: this dead code, once wired up, contained four real numeric bugs (scientific-notation ints, bool-as-int, NaN phantom deltas, OverflowError on huge ints) — see the related logic-errors doc.

## Why This Matters

- Reuse cut most of the implementation cost; the plan became integration work with a known-good shape.
- Skipping the audit means re-implementing something that already exists, then owning two copies.
- The counterweight: dead code is unvetted code. "Wire up" without "harden" ships latent bugs that were never reachable before.

## When to Apply

- Before writing an implementation plan for any feature in a mature or previously-iterated codebase
- When a plan's first draft says "build X" and X sounds generic (diffing, caching, retries, pagination)
- During plan review, as a checklist question: "did we grep for existing machinery?"

## Examples

In this feature, the audit finding changed the plan document itself: `plans/dayzerocto-1-feature-standardize-ceo-report-template-with-week.md` records `report_changes_html` / `previous_report_json_path` as dead-but-complete, and the implementation wired them into `render_structured_report()` (called from the CLI write path at `scripts/dzcto_artifact.py:6164-6175`) instead of adding a parallel implementation.

## Related

- docs/solutions/logic-errors/python-numeric-metric-delta-gotchas-2026-07-03.md — the bugs found while hardening the wired-up dead code
- plans/dayzerocto-1-feature-standardize-ceo-report-template-with-week.md — the plan that recorded the audit finding

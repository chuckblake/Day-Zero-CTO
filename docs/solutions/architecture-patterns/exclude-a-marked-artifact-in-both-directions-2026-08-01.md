---
title: "A marked artifact must be excluded in both directions, not just as a candidate"
date: 2026-08-01
category: architecture-patterns
module: ceo-report
problem_type: architecture_pattern
component: tooling
related_components: [documentation, testing]
severity: high
applies_when:
  - "Adding a marker that excludes an artifact from a selection pool"
  - "A selection function takes both a CURRENT item and a pool of CANDIDATES"
  - "Introducing a demo, sample, fixture, or seeded artifact into a real data directory"
  - "Auditing a predicate-based guardrail for surfaces it does not cover"
tags: [single-source-of-truth, guardrail, predicate-reuse, selection-function, sample-data, symmetry]
---

# A marked artifact must be excluded in both directions, not just as a candidate

## Context

DAYZEROCTO-19 seeds a **sample report** into `reports/ceo-updates/` during `dzcto init`, so a
first-time reader can open real generated output before wiring any evidence. Because a sample must
never be mistaken for real work, the design followed the repo's existing pattern
(`shared-predicate-guardrail-single-dispatch-point`): one predicate, `is_sample_report(data)`, routed
through every surface that counts or cites reports.

Five consumers were enumerated up front and wired: the weekly streak, the since-last-report cursor,
the index KPI, `dzcto status`, and prior-report selection. Each got a test. The plan explicitly named
prior-report selection as the sharpest one, because `locate_prior_report` coerces an unknown
`report_type` to `ad_hoc` and therefore inherits no exclusion from the type field.

All five passed. The gate still had a hole.

`locate_prior_report(json_path, data)` takes **two** roles: `data` is the **current** report, and it
globs siblings as **candidates**. The exclusion had been added to the candidate loop only:

```python
for path in sorted(json_path.parent.glob("*.json")):
    cand = read_json_file(path, None)
    if is_sample_report(cand):
        continue          # a sample is never a prior  ✅
```

So the sample could never *be* a prior — but nothing stopped it from *having* one. `dzcto init` is
re-runnable and refreshes every existing report's HTML. Once real reports existed, the next init
re-rendered the sample and handed it the reader's most recent real report as a baseline, producing a
week-over-week section inside the sample that diffed fabricated content against real work: metric
deltas between fake and real numbers, and real progress items narrated as "no longer listed" — in the
shareable artifact, which is exactly where the claim does the most damage.

The write path looked safe and disguised it. `write_sample_report` passes `previous_data=None`
explicitly, so the *creation* path never showed the bug; only the *refresh* path did, and only after a
real report existed. Two conditions, neither present in the tests written for the five enumerated
surfaces.

## Guidance

**When a selection function takes both a current item and a candidate pool, an exclusion marker has
two sites, not one.** Ask explicitly: "can the marked artifact be the *subject* of this call, not just
a member of the pool?" For `locate_prior_report` the answer was yes, and the subject-side guard was
missing:

```python
def locate_prior_report(json_path, data):
    if is_sample_report(data):
        return None, None, "", []   # never HAS a prior
    ...
    for path in ...:
        if is_sample_report(cand):
            continue                # never IS a prior
```

**Enumerating consumers is not the same as enumerating roles.** The plan's consumer list was correct
and complete — five surfaces, five tests, all green. The defect lived *inside* one of those five, in a
role the consumer list had no vocabulary for. A checklist of call sites will not surface it; only
reading the signature and asking what each parameter means will.

**Distrust a guard whose safety depends on every call site remembering.** `previous_data=None` at the
one creation site was doing real work, which is precisely why the bug stayed invisible. Push the
guarantee into the function so it holds for callers that do not yet exist — the refresh path was
already such a caller.

**Seeded artifacts are re-processed by maintenance paths, not just creation paths.** A demo/sample/
fixture written into a real data directory will be picked up by every sweep, refresh, migration, and
reindex that directory has. Enumerate those too: here the format refresh deliberately *includes* the
sample (so it never goes stale), which is correct — and is exactly what re-triggered the defect.

**Test the second condition.** The bug needed *both* a sample *and* a real report *and* a re-run. Tests
covering "sample only" and "sample plus real report, first render" both passed. Reach for the state
that only appears after the workflow runs twice.

## Why This Matters

The failure inverts the guardrail's own purpose. The feature exists so a sample is never mistaken for
evidence-traceable work; the defect made the sample *narrate* the reader's real work — with real
project data, in the artifact that gets shared with a CEO. A reader has no way to tell that the
comparison is fabricated, because everything around it is real.

It is also a failure the surrounding process nearly missed. The plan named prior-report selection as
the highest-risk surface, the implementation guarded it, and a test asserted the guard. All three were
right about the direction they considered, and all three considered only one of the two.

## When to Apply

- Adding an `is_<marked>()` predicate and wiring it into selection, counting, or comparison surfaces.
- Reviewing any function whose signature carries both a subject and a collection of peers
  (`locate_prior`, `find_related`, `pick_baseline`, `nearest_neighbor`, dedupe/merge helpers).
- Introducing sample, demo, seed, or fixture data into a directory that real data also lives in.
- Auditing a guardrail after a bug: check whether the same predicate has an unguarded mirror role
  rather than assuming the consumer list was the whole surface.

## Related

- `shared-predicate-guardrail-single-dispatch-point-2026-07-09.md` — the parent pattern this
  extends. That entry establishes one predicate with N consumers; this one adds that a single
  consumer can need the predicate in more than one **role**, which a consumer count will not reveal.
- `../conventions/absence-proxy-assertions-break-on-additive-rendering-2026-07-23.md` — the sibling
  testing trap from the same renderer: there the test's shorthand silently constrains new output;
  here the test's *scenario* silently omits the state that exposes the bug.

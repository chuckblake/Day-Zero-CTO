---
title: "Characterize what already holds; build only what does not"
date: 2026-08-01
category: best-practices
module: ceo-report
problem_type: best_practice
component: tooling
related_components: [testing_framework, documentation]
severity: medium
applies_when:
  - "An issue's acceptance criteria describe behavior that may already partly exist"
  - "Planning a change against a Background section written from a quick code skim"
  - "Deciding whether a criterion needs new machinery or a regression test"
tags: [acceptance-criteria, characterization-test, scope-control, planning, dead-machinery]
---

# Characterize what already holds; build only what does not

## Context

Shipping DAYZEROCTO-15/16/17/18 as one group surfaced the same trap twice, in two unrelated
issues. Both issues' acceptance criteria described behavior that was **already partly true**, and
in both cases the issue's own Background section pointed at the wrong place:

1. **DAYZEROCTO-15** asked that "test or debug runs whose artifact is discarded do not contribute
   to the streak." Half of that was already guaranteed by construction: the streak pool is built by
   globbing `*.json` on disk, so a *deleted* artifact cannot enter it. Only the other half — a test
   run still sitting on disk — needed a mechanism.
2. **DAYZEROCTO-16** asked that "the streak is visible on the report index," and its Background said
   the streak was "only rendered as a KPI inside each generated report's HTML
   (scripts/dzcto_artifact.py:3232-3235)." That line reference is in fact inside `render_index()` —
   the KPI was **already on the index**. The genuine gap was the CLI tail.

Left unchecked, each would have produced real machinery for a case that cannot occur: a
deletion-tracking mechanism for artifacts that leave no trace, and a second index surface duplicating
one that already rendered.

## Guidance

**1. Resolve every acceptance criterion against the running code before planning work for it.**
Not against the issue's Background — against the code. An issue's Background is usually written from
a quick skim while filing, so a line reference in it is a *hint*, not a finding. Open the line. In
both cases above the cited line number was real and the prose about it was wrong.

**2. Split the criterion, and say in the plan which half is already satisfied.** Do not silently
narrow scope, and do not silently over-build. Write it down as a decision:

> **KTD6 — "Discarded" splits into an already-satisfied case and a real gap.**
> *Artifact genuinely deleted:* already excluded by construction. This needs a **characterization
> test, not new code.** *Test/debug run left on disk:* the real gap; needs a marker.

Naming it in the plan is what stops the implementer from re-deriving the question and guessing.

**3. Pay for the already-satisfied half with a test, not with code.** A characterization test costs
a few lines and converts "this happens to work" into "this is intentional and will keep working":

```python
def test_deleting_the_report_json_removes_it_from_the_streak_with_no_error(self):
    ...
    discarded.unlink()
    self.assertEqual(artifact.weekly_report_dates(self.folder), [dt.date(2026, 6, 25)])
```

The test is also the durable answer to the next person who reads the same acceptance criterion and
reaches for deletion tracking.

**4. Distinguish absent from excluded.** Once you have both halves, the vocabulary matters: a file
that is *gone* is absent, not excluded. That distinction propagated into the UI — an absent report
must not make the index claim a "paused" streak — and earned its own test.

## Why This Matters

- **Unbuilt machinery cannot rot.** This repo already carries two learnings about auditing for and
  deleting dead-but-complete machinery. Not building it is strictly cheaper than building, shipping,
  and later removing it.
- **A wrong Background is not a wrong issue.** The criteria in both issues were correct and worth
  shipping; only the diagnosis of *where* the gap was had drifted. Rejecting the issue would have
  been as wrong as implementing it literally.
- **Scope honesty compounds.** Both plans stated which half was pre-satisfied, so the PR reviewer
  can check the claim in one test rather than re-reading the whole diff to work out why an
  acceptance criterion has no corresponding code.

## When to Apply

- Any issue whose acceptance criteria are phrased as end states ("X does not count", "Y is visible")
  rather than as changes — end-state phrasing is silent about whether the end state already holds.
- Any Background section that cites a line number or file as evidence of a gap: open it first.
- Any criterion where the mechanism would have to observe something that leaves no trace (a deleted
  file, an unsent request, an unopened page). That shape is a strong hint the case is either already
  handled by construction or genuinely unobservable — both of which mean "do not build it."

## Examples

Two receipts from the same branch:

| Criterion | Reality | Response |
|---|---|---|
| Discarded test/debug runs do not count | Deleted artifacts already excluded by the glob | Characterization test |
| Test/debug run still on disk | No mechanism existed | `--test-run` marker + predicate branch |
| Streak visible on the report index | Already rendered as a KPI tile | Characterization test |
| Streak visible in CLI output | Nothing printed after a run | New stderr line on the write path |

## Related

- `docs/solutions/best-practices/audit-for-dead-but-complete-machinery-2026-07-03.md` — the
  after-the-fact version of this discipline; this learning is the before-the-fact one.
- `docs/solutions/best-practices/safely-delete-dead-but-complete-machinery-2026-07-10.md` — what it
  costs to remove machinery you should not have built.
- `docs/solutions/architecture-patterns/shared-predicate-guardrail-single-dispatch-point-2026-07-09.md`
  — the pattern the genuinely-missing halves were built on (one predicate, one dispatch point).
- `plans/dayzerocto-15-feature-exclude-no-work-and-discarded-runs-from.md` — KTD6 and KTD9 are the
  two decisions this learning generalizes.

---
title: Safely delete dead-but-complete machinery
date: 2026-07-10
category: best-practices
module: ceo-report
problem_type: best_practice
component: development_workflow
severity: medium
applies_when:
  - "Pruning a large cluster of confirmed-dead code from a multi-module codebase"
  - "A prune plan proposes deleting whole subsystems (renderers, registries, CLI subcommands)"
  - "Deleting a function that other modules may import at load time, not just call"
related_components: ["tooling", "testing_framework"]
tags: [dead-code, safe-deletion, pruning, import-break, regression-oracle, agents-md]
---

# Safely delete dead-but-complete machinery

## Context

DAYZEROCTO-8 pruned dead non-CEO-report machinery from a Python CLI. Measured from the prune commit `d02e1ad` (not `main...HEAD`, which lags by seven already-merged features), `scripts/dzcto.py` went 2,547 → 957 lines and `scripts/dzcto_artifact.py` went 6,454 → 3,281 lines — a net **−4,857 lines** across the whole commit. Deleted: retired hidden CLI subcommands and their handlers, five dead artifact-kind renderers (snapshot, tech-stack, engineering-risk, codebase-accountability, weekly-reviews), the orphaned risk/decision-registry cluster, and a recursive-redaction helper. Kept: the CEO report path (`init` + evidence + `artifact --kind ceo-updates`) and all shared helpers.

This is the **inverse** of `audit-for-dead-but-complete-machinery-2026-07-03.md`. That doc uses call-graph tracing to *find* dead-but-complete code and wire it up. This one uses the same tracing discipline to *delete* it safely. The tracing is identical; four failure modes are specific to deletion.

## Guidance

### 1. Prune stale `from X import` lines in lockstep — a call-site grep alone misses them

Deleting a top-level symbol raises `ImportError` at module load if any other module imports it, **even when every call site is already dead**. A call-site grep (`grep -n "build_risk_registry("`) shows zero live callers and green-lights deletion, but the module still fails to import because of a dangling `from` line.

In this prune, `scripts/dzcto.py` imported two now-deleted symbols:

```python
# scripts/dzcto.py — both had to be pruned in lockstep with the symbol deletions
from dzcto_artifact import ( ..., build_risk_registry, ... )   # build_risk_registry defined in dzcto_artifact.py
from dzcto_common   import ( ..., redact, redacted_json_text, ... )   # both defined in dzcto_common.py
```

The discipline: for every top-level symbol you delete, also grep `from <module> import` across the whole tree and remove the symbol from those import lists in the same pass. Import bindings are a second, invisible call graph.

```bash
# Before deleting build_risk_registry, find BOTH graphs:
grep -rn "build_risk_registry(" scripts/          # call sites (the obvious graph)
grep -rn "import.*build_risk_registry" scripts/   # import bindings (the graph a call-site grep misses)
```

### 2. Trace the whole transitive dead-island before declaring any member deletable

A "dead" function usually anchors a self-referential cluster whose members only call each other. Deleting the entry point without tracing the chain either leaves orphans behind or, worse, stops mid-cluster and leaves a half-wired subsystem.

The risk/decision-registry island deleted here: `build_risk_registry`, `build_decision_registry`, `active_registry_risks`, `render_candidate_risk_section`, `risk_id_for_title`, `stable_anchor_id`, `short_hash` (in `dzcto_artifact.py`), plus the snapshot consumers `snapshot_risk_rows`, `snapshot_decision_rows`, `risks_missing_review_dates` (in `dzcto.py`). Every member fed only other members and the five dead renderers. Trace the whole island — writers → readers → the dicts they pass — and delete it as one unit.

### 3. A byte-identical output oracle catches regressions the unit suite doesn't

For a large deletion, the load-bearing invariant is "the kept output didn't change." The 122-test `unittest` suite passed at every step, yet a supposedly-dead dependency still altered the rendered CEO report — a regression the unit suite did **not** catch. The oracle that caught it: render the `ceo-updates` artifact from a **fixed data file with a fixed clock** before and after the prune, and diff the two HTML files byte-for-byte. They must be identical; any diff is a real behavior change from something you thought was dead.

```bash
# Fixed input + fixed clock → deterministic output; the only variable is your deletion.
python3 scripts/dzcto.py artifact --kind ceo-updates --workspace fixtures/frozen > /tmp/before.html
# ... apply the prune ...
python3 scripts/dzcto.py artifact --kind ceo-updates --workspace fixtures/frozen > /tmp/after.html
diff /tmp/before.html /tmp/after.html   # MUST be empty
```

This was run manually for this prune (it lives in the DAYZEROCTO-8 plan, not as a committed test). See Prevention for the stronger version.

### 4. Reconcile the prune plan against AGENTS.md before deleting a public-ish surface

A deletion plan optimizes for "remove everything unreachable." AGENTS.md may require a surface to keep working regardless of internal reachability. Reconcile the two before deleting anything user-facing or aliased.

Here the plan proposed deleting the `status` subcommand and the `dzcto-learning` machinery, but AGENTS.md pinned both:

- Line 30 — "Keep `dzcto quickstart`, `dzcto help`, `dzcto status`, and `dzcto version` working as the self-serve front door."
- Line 15 — "`bin/dzcto` is the canonical wrapper; `dzcto-artifact`, `dzcto-learning`, and `dzcto-doctor` are compatibility aliases."

So `dzcto status` was **kept** (narrowed to CEO-workspace health) and `dzcto_learning.py` + `bin/dzcto-learning` were **kept**. Eight retired subcommands were removed, not nine.

## Why This Matters

- **Import-break trap**: a green call-site grep is a false all-clear. The module won't even import, and unit tests can't catch what fails at collection time — the failure surfaces only when something loads the module.
- **Dead-island tracing**: deleting the entry point of a cluster without tracing it leaves orphaned readers (a new, subtler dead island) or a broken half-subsystem.
- **Output oracle**: unit tests assert what someone thought to assert. A byte-identical diff of the real rendered output asserts *everything at once*, so it catches the dependency you misjudged as dead. It is the highest-signal check for a large deletion.
- **AGENTS.md reconciliation**: internal reachability and external contract are different truths. Deleting a reachable-only-by-contract surface passes every test and still breaks users.

## When to Apply

- Before deleting any top-level symbol imported by another module (do the lockstep import grep first)
- When a prune targets a cluster of functions rather than a single leaf
- Before deleting any CLI subcommand, alias, or other public-ish surface (reconcile against AGENTS.md)
- Whenever a deletion must preserve a rendered/serialized output verbatim — build a fixed-input, fixed-clock byte oracle

## Prevention

- **Two-graph deletion checklist**: for each deleted symbol, grep both `symbol(` (call sites) and `import.*symbol` / `from <module> import` (bindings); prune both in the same commit. Re-scan for references between passes.
- **Commit the byte oracle as a guardrail test.** The most reusable outcome of this prune is that the manual pre/post HTML diff should become a committed regression test: render `ceo-updates` from a frozen fixture under a fixed clock and assert byte-equality against a checked-in golden file. That way the *next* large deletion gets the oracle automatically instead of relying on someone remembering to run it by hand.
- **Reconcile against AGENTS.md as an explicit plan step.** Before executing a prune, diff the deletion list against every surface AGENTS.md pins, and record kept-despite-dead decisions in the plan's Decisions section.
- Run the suite with the project's actual runner — here `python3 -m unittest discover -s tests` (pytest is not installed); the "output oracle beats unit tests" lesson does not mean skipping the 122-test suite, it means adding the oracle on top of it.

## Related

- `docs/solutions/best-practices/audit-for-dead-but-complete-machinery-2026-07-03.md` — the primary sibling: the detection method this doc inverts into deletion. The call-graph tracing discipline is identical; only the action (wire-and-harden vs. delete) differs.
- `docs/solutions/conventions/skill-md-schema-lockstep-test-2026-07-03.md` — the other byte-identical-comparison-as-a-test in this repo (source-duplication lockstep vs. output-regression oracle); methodological cousin to guidance #3.
- `docs/solutions/architecture-patterns/helper-computes-agent-narrates-2026-07-03.md` — the CEO-report architecture this prune deliberately preserves (the "keep" side of the delete boundary).

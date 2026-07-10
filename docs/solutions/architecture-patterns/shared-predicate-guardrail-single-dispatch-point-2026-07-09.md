---
title: "One predicate, three consumers: a render-time guardrail that can't disagree with itself"
date: 2026-07-09
category: architecture-patterns
module: ceo-report
problem_type: architecture_pattern
component: tooling
related_components: [documentation, assistant]
severity: medium
applies_when:
  - "A warning, a visible annotation, and a count all need to agree about the same condition"
  - "Adding a warn-and-annotate guardrail (never hard-fail) to a render or write path"
  - "Deciding where to place a top-level guardrail when the underlying helper has many call sites"
  - "A validity check must use the exact same predicate the renderer uses to display"
tags: [single-source-of-truth, guardrail, warn-never-fail, evidence-sources, render-path, dispatch-point, predicate-reuse]
---

# One predicate, three consumers: a render-time guardrail that can't disagree with itself

## Context

DAYZEROCTO-6 added a render-time evidence check to `scripts/dzcto_artifact.py`: when a
structured report ships with zero *cited* evidence, the tool should (a) warn on the CLI
write path and (b) stamp a visible "thin-evidence" banner into the rendered artifact.

The trap in a feature like this is **internal disagreement**. If the CLI computes "has
evidence?" one way, the banner gate computes it a second way, and the visible Sources
section renders on a third rule, they drift: the artifact shows a Sources list but the CLI
warned it was empty (`warn-but-shows`), or the CLI stayed silent but no sources rendered
(`shows-but-warns`). Each consumer looks correct in isolation; together they lie.

A second trap is **placement**. The natural instinct is to add the banner inside
`render_sources`' empty branch — but `render_sources` has 7 call sites. Editing all 7, or
worse editing the shared function so every section that lists sources also emits a
top-level banner, is a ripple hazard.

## Guidance

**1. Make one predicate the single source of truth, and define "valid" as "what the
renderer would actually display."**

Extract a single helper and route every consumer through it:

```python
def cited_evidence_sources(data: dict[str, Any]) -> list[Any]:
    sources = array_value(value_at(data, "sources", "source_list", "evidence_sources"))
    return [source for source in sources if source_entry_html(source)]
```

The key move: "cited" is defined as **"renders to a non-empty `source_entry_html`"** —
the *exact same predicate* `render_sources` uses to decide whether to show a row. It is not
"the `sources` array is non-empty" (which would count blank/whitespace entries the renderer
silently drops). Because the CLI warning, the banner gate, and the visible Sources count all
call this one helper over the same *sanitized* `data`, they are structurally incapable of
skewing. Consistency isn't tested into existence; it's made unrepresentable.

**2. Centralize the top-level guardrail at the single dispatch point, not at the N call
sites of the shared helper.**

The banner belongs to the *report as a whole*, so it goes at the one place the whole report
is assembled — `render_structured_report` — not inside `render_sources`:

```python
def render_structured_report(...):
    ...
    if not cited_evidence_sources(data):
        rendered = f"{render_thin_evidence_banner()}{rendered}"
    return rendered
```

This is safe **because of a specific, verified codebase fact**: all 7 `render_sources(...)`
call sites pass the top-level report `data` dict, never a section or sub-dict. So a
top-level predicate over `data` means the same thing everywhere, and centralizing the
guardrail at the dispatch point is genuinely ripple-free. Verify the call-site invariant
before centralizing — it is the load-bearing assumption.

**3. Warn-and-annotate, never hard-fail — and scope the warning to reports that could
have evidence.**

An honest quiet-week report may legitimately cite thin evidence, so zero sources is a
warning, not an error. The CLI warning lives *inside* `if structured_data is not None:`, so
plain body-only reports (no structured data) don't spuriously warn:

```python
structured_data = sanitize_current_report_data(structured_data)
if not cited_evidence_sources(structured_data):
    print("dzcto: no cited evidence sources; report ships with thin evidence "
          "(add sources[] to make claims traceable)", file=sys.stderr)
```

**4. Reuse existing seams instead of building new infrastructure.** The write path already
had warn-only stderr conventions (`print_secret_redactions`, `validate_ceo_report`), and the
stylesheet already had `--med` / `--med-soft` warning color tokens. The banner and warning
slotted into both — no new logging layer, no new CSS system.

## Why This Matters

Guardrails that can disagree with themselves are worse than no guardrail: they train the
operator to distrust the tool. Routing every consumer through one predicate over one
sanitized input turns "keep three checks in sync" (a maintenance burden that decays) into
"there is only one check" (an invariant that can't decay). The same shape recurs across this
codebase — see the sibling patterns below — because it is the cheapest way to buy
consistency: collapse the surfaces onto one function rather than reconciling them.

Placement matters just as much as the predicate. A top-level condition (does *this report*
have evidence?) belongs at the top-level dispatch point, gated on a codebase invariant you
have verified, not sprayed across the call sites of a lower-level helper that happens to be
where the data is nearby.

## When to Apply

- Multiple surfaces (a warning, a badge/banner, a count, an export field) must reflect the
  same underlying condition — give them one predicate helper, not one each.
- The validity rule should match display exactly — define the predicate as "what the
  renderer would show," not a looser proxy like "array is non-empty."
- You're about to add a report-wide or artifact-wide guardrail and the obvious insertion
  point is a heavily-called shared helper — check whether a single dispatch point exists and
  whether every call site passes the same top-level object; if so, centralize there.
- The failing condition can be legitimate (quiet week, empty-by-design) — warn and annotate,
  don't block; and scope the warning so shapes that can't satisfy the check don't trip it.

## Examples

Before — three independent notions of "has evidence," free to drift:

```python
# render_sources: shows a row iff source_entry_html is non-empty
rows = [source_entry_html(s) for s in array_value(value_at(data, "sources", ...))]
rows = [r for r in rows if r]
# CLI (hypothetical divergent check): warns iff the raw array is empty
if not array_value(value_at(data, "sources", ...)):   # counts blank entries!
    warn(...)
# banner (hypothetical third rule): ...
```

After — one predicate, every consumer agrees by construction:

```python
def cited_evidence_sources(data):
    return [s for s in array_value(value_at(data, "sources", "source_list",
                                            "evidence_sources")) if source_entry_html(s)]

# render_sources, CLI warning, and banner gate all call cited_evidence_sources(data)
# over the same sanitized data — no warn-but-shows / shows-but-warns skew possible.
```

## Related

- `docs/solutions/logic-errors/quiet-week-diff-fabricates-reversal-2026-07-09.md` — same
  file and same render-path warn-only discipline; it added the `empty_note` on
  `render_sources`' empty branch, the very surface this banner sits on top of. A quiet-week
  report with no sources exercises both together.
- `docs/solutions/architecture-patterns/secret-scanning-shape-detection-and-split-fail-policy.md`
  — structural sibling ("one shared detector, N consumers, locate the fail policy
  deliberately"); note the deliberate contrast — that one *splits* block-vs-warn, this one
  is all-warn-never-block. Source of the write-path warn-only stderr convention reused here.
- `docs/solutions/architecture-patterns/helper-computes-agent-narrates-2026-07-03.md` —
  parent principle: verifiable facts get a renderer warning (never a block); this guardrail
  is an instance of that tier.
- `docs/solutions/design-patterns/today-anchored-cadence-period-streak-2026-07-09.md` —
  adjacent example of the same single-dispatch-point plumbing move (in `render_index`).

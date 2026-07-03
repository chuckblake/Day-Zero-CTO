---
title: "Helper computes, agent narrates — split mechanical facts from LLM prose"
date: 2026-07-03
category: architecture-patterns
module: ceo-report
problem_type: architecture_pattern
component: tooling
related_components: [assistant, documentation]
severity: medium
applies_when:
  - "An agent-driven pipeline produces artifacts containing both computed facts and narrative prose"
  - "Numbers, deltas, or comparisons appear in agent-generated output"
  - "Deciding whether a template rule belongs in code or in the agent prompt"
tags: [agent-architecture, hallucination, renderer, skill-design, deltas, conformance]
---

# Helper computes, agent narrates — split mechanical facts from LLM prose

## Context

CEO reports are produced by an agent (following a SKILL.md) plus a deterministic Python renderer (`scripts/dzcto_artifact.py`). The week-over-week section contains exactly the kind of content LLMs get wrong: numeric deltas and added/removed comparisons. The architecture question was where each responsibility lives.

## Guidance

**Anything checkable is computed by the helper; the agent only narrates.**

**1. The renderer computes all deltas — the agent is forbidden from writing them.** Metric deltas (`metric_delta_items`, `scripts/dzcto_artifact.py:1854`) and per-section added/removed diffs (`report_changes_html`, `:1928-1942`) are pure functions over the current and prior JSON. They cannot hallucinate. Both SKILL.md files state the boundary explicitly (line 64):

> "Do not author `schema_version`, `generated_at`, or `prior_report` — the renderer stamps them. The renderer also computes the week-over-week section from the prior report; never write that section yourself."

**2. The agent is instructed to keep the diff *readable*.** Mechanical string diffs are only useful if unchanged items keep stable wording, so the SKILL.md (line 21 in both skills) instructs:

> "Carry still-true items forward verbatim — stable wording keeps the automatic week-over-week diff readable — and express continuity in the `headline` prose."

The helper computes; the agent's job is to feed it diff-friendly input and narrate continuity in prose fields the diff ignores.

**3. Template conformance splits into two tiers:**

- **Verifiable → renderer warns.** `validate_ceo_report()` (`scripts/dzcto_artifact.py:2428`) is a warn-only schema check (missing fields, bad `report_type`, non-ISO windows, non-scalar metrics), printed to stderr at write time — never blocking the write.
- **Aspirational → agent is prompted.** Qualitative standards the renderer cannot check ("Keep technical detail subordinate to CEO judgment", "Flag unsupported claims instead of smoothing them over") live only in the skill prompt (`skills/dzcto-ceo-report/SKILL.md:66-72`).

Sorting each rule into the right tier is the design act: if code can check it, code checks it; prompts carry only what code cannot.

## Why This Matters

- Numbers in the output are trustworthy by construction — there is no path where the LLM invents a delta.
- Warn-only validation keeps the pipeline resilient: a malformed field degrades one section, never the whole report.
- Putting verifiable rules in prompts wastes prompt budget and still doesn't guarantee conformance; putting aspirational rules in code is impossible. The two-tier split is the only assignment that works.

## When to Apply

- Any skill/agent + helper-script pipeline emitting artifacts with computed content
- When reviewing a SKILL.md: ask of each instruction, "could the renderer check or compute this instead?"
- When a report section could be derived from stored data rather than authored

## Examples

The week-over-week section is entirely renderer-produced from `prior_report` JSON; the agent's `headline` narrates trajectory. Delta correctness is covered by `TestReportChangesHtml` in `tests/test_dzcto_artifact.py`; schema warnings by `TestValidateCeoReport`.

## Related

- docs/solutions/design-patterns/cadence-scoped-prior-report-selection-2026-07-03.md — how the renderer picks the prior it computes against
- docs/solutions/logic-errors/python-numeric-metric-delta-gotchas-2026-07-03.md — hardening the computed-delta path
- docs/ceo-report-template.md — the canonical template both tiers enforce

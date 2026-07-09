---
title: "Quiet-week week-over-week diff fabricates a reversal from an empty current group"
date: 2026-07-09
category: logic-errors
module: ceo-report
problem_type: logic_error
component: tooling
symptoms:
  - "On a quiet week, an empty current progress group against a populated prior report emitted every prior item under 'No longer listed', reading to a CEO as a reversal (e.g. 'we reverted the login')"
  - "The mechanically-computed 'Week over week' section manufactured bad news — implied shipped work was dropped when it was simply not restated this window"
  - "Required CEO sections (Progress, Risks / Blockers, Asks / Decisions, Next, Sources) vanished entirely when their arrays were empty instead of showing a labeled placeholder"
  - "No signal distinguished an intentionally quiet window from a forgetful or truncated report"
root_cause: logic_error
resolution_type: code_fix
severity: high
tags: [quiet-week, week-over-week-diff, ceo-report, false-reversal, empty-section, honest-reporting, shared-helper, boundary-case]
---

# Quiet-week week-over-week diff fabricates a reversal from an empty current group

## Problem

The "Week over week" section in `report_changes_html` (`scripts/dzcto_artifact.py`) is a mechanical set-difference over the current vs. prior report. On a genuinely quiet week — this week's `progress` group empty but the prior report listed items — the diff flagged **every** prior item under "No longer listed: …", which reads to a CEO as "we reverted shipped work." Manufacturing bad news is the mirror image of padding: both are the mechanically-computed section asserting something untrue.

## Symptoms

On a quiet week (agent submits an empty `progress` group, or empty `risks_blockers` / `asks_decisions` / `next`, against a populated prior report) the CEO would have seen:

- A **"Week over week"** line reading `Progress: No longer listed: <every item shipped last week>` — the set-difference over an empty current set flagged the entire prior list as removed, which parses as "we un-shipped all of last week's work."
- The required CEO sections **silently vanishing** from the HTML: `render_list_section` and `render_sources` returned `""` for empty input, so a quiet Progress/Risks/Asks/Next/Sources section disappeared entirely rather than saying "nothing this window." The report looked truncated or broken rather than honestly quiet.

## What Didn't Work

Three approaches were considered and rejected before the shipped fix:

- **(a) Infer a global "all sections empty ⇒ quiet mode."** Wrong: a correctly-authored quiet report still carries forward *still-true* risks, asks, and next-steps, so its sections are non-empty. The global inference would *miss* the real quiet reports (they have content) and *fire* on forgetful ones (agent dropped structure it should have kept) — exactly backwards. "Quiet week" is not "all sections empty"; the design must be per-section labeling, not a global flag.
- **(b) An authored `quiet_week: true` JSON field.** Rejected on three converging grounds: it is self-contradictable (an agent can set it true while sections are populated, or vice-versa); the byte-identical schema-lockstep between the weekly and ad-hoc report skills would force the field into the semantically-wrong `ad_hoc` skill; and a free-text variant would introduce a *new* untrusted egress input that the secret scanner would then have to cover.
- **(c) A global empty-state baked into the shared helpers.** `render_list_section` (18 call sites) and `render_sources` (7 call sites) are shared across six report kinds. Making the empty placeholder unconditional would leak strings like "None recorded" into tech-stack and engineering-risk reports, which legitimately omit empty sections.

## Solution

**(1) `report_changes_html` — new whole-group-empty branch.** Detect an entirely-empty current group against a populated prior and *name* the prior items without claiming removal. It sits *after* the `not_comparable` guard (prior lacked the section), so "not comparable" correctly wins over "empty current group." Partial removals still fall through to "No longer listed":

```python
if per_group and not any(field in previous_data for field in fields):
    changes.append(f"<li><strong>{esc(label)}:</strong> Not comparable — prior report lacked this section.</li>")
    not_comparable += 1
    continue
current = report_change_values(data, fields)
previous = report_change_values(previous_data, fields)
...
if per_group:
    if not current and previous:                                    # NEW branch
        changes.append(f"<li><strong>{esc(label)}:</strong> No items this window (prior listed: {esc(summarize_change_list(previous, 2))}).</li>")
        group_changes += 1
        continue
    if added:
        changes.append(f"<li><strong>{esc(label)}:</strong> Added: {esc(summarize_change_list(added, 3))}</li>")
        group_changes += 1
    if removed:                                                     # genuine partial removal
        changes.append(f"<li><strong>{esc(label)}:</strong> No longer listed: {esc(summarize_change_list(removed, 2))}</li>")
        group_changes += 1
    continue
```

**(2) Opt-in `empty_note` param on the two shared helpers.** Both gained a *defaulted* param so all existing call sites are untouched; only `render_ceo_update` opts in:

```python
def render_list_section(title, items, empty_note=None):
    rows = array_value(items)
    if not rows:
        if not empty_note:
            return ""                       # default: other report kinds still omit
        return f'<section class="artifact-section"><h2>{esc(title)}</h2><p class="empty-item">{esc(empty_note)}</p></section>'

# render_sources gained the same defaulted empty_note; only the CEO path passes it:
render_list_section("Progress", value_at(data, "progress"), "No progress to report for this window."),
render_list_section("Risks / Blockers", value_at(data, ...), "No risks or blockers this window."),
render_list_section("Asks / Decisions", value_at(data, ...), "No asks or decisions this window."),
render_list_section("Next", value_at(data, ...), "Nothing queued for the next window."),
render_sources(data, "No evidence sources recorded for this window."),
```

`render_sources` was the easy call site to miss (it has a different internal structure than `render_list_section`); a code review caught that it also needed the treatment.

**(3) `validate_ceo_report` — warn-only tripwire.** Fires only when *all four* required list sections are empty, and never blocks. The inline comment explicitly bounds what it can prove:

```python
# Only an empty-report tripwire. It cannot distinguish an intentional quiet
# window from forgotten structure (byte-identical JSON), and carried-forward
# risks correctly suppress it.
if not any(array_value(data.get(field)) for field in ("progress", "risks_blockers", "asks_decisions", "next")):
    warnings.append("report has no structured content; if the window was quiet, say so in headline")
```

## Why This Works

Emptiness is *code-checkable*, so the split is: **the renderer computes and labels the emptiness; the agent narrates the quietness** in prose. The helper mechanically stamps a per-section placeholder ("No risks or blockers this window."), and the *reason* it was quiet goes in the existing `headline` — which already flows through the secret scanner, so no new untrusted egress surface is created. Labeling is per-section, not a global flag, so a report that is quiet in Progress but active in Risks renders each section honestly.

The tripwire is deliberately **warn-only** because it *cannot* distinguish an intentional quiet week from a forgetful agent — the two produce byte-identical JSON — and it *won't* fire on the common carried-forward quiet week (still-true risks/asks/next keep those sections non-empty). A hard failure would either block honest quiet reports or give false confidence. The inline comment states this limitation so the next reader does not over-trust the check as a quiet-week detector.

## Prevention

- **Audit whether a mechanically-computed section can LIE in the boundary case you are adding, not just whether it is correct in the normal case.** When a section is a mechanical computation — a set-difference, a delta, a week-over-week diff — the review question is not "is it right on a normal week?" but "can it *lie* in the boundary case I am introducing?" Here the empty-vs-populated (quiet-week) case turned a correct set-difference into a fabricated reversal. Guardrails against padding must cut *both* ways: the same instinct that says "don't soften or omit bad news" must also say "don't fabricate it." An empty current set is a legitimate state, not a signal that everything was removed.
- **Empty-states on a shared renderer helper must be opt-in per call site, and you must regression-test the other consumers.** Add the behavior behind a defaulted param (`empty_note=None`) so the default preserves every existing call site, then opt in only where you mean it. Test the *other* consumers to prove the empty-state does not leak — `render_sources` was the easy call site to miss, and a code review is what caught that it also needed the param.

**Tests pinning these behaviors** (in `tests/test_dzcto_artifact.py`):

- Diff honesty: `test_empty_current_group_names_prior_without_claiming_removal`, `test_partial_group_removal_still_renders_no_longer_listed`, `test_not_comparable_wins_over_empty_current_group`.
- Opt-in placeholders + no leak into other kinds: `test_sparse_quiet_report_renders_required_empty_sections`, `test_populated_ceo_report_has_no_empty_placeholders`, `test_other_report_kinds_still_omit_empty_list_sections_and_sources`.
- Warn-only tripwire semantics: `test_empty_structured_report_warns_to_narrate_headline`, `test_carried_forward_risk_suppresses_empty_report_warning`.

## Related

- [helper-computes-agent-narrates](../architecture-patterns/helper-computes-agent-narrates-2026-07-03.md) — the pattern that computed content "cannot hallucinate." This doc **refines** that claim: a deterministic section can still emit a *falsehood* (a fabricated reversal) in a boundary case. Determinism guarantees consistency, not honesty at the edges.
- [python-numeric-metric-delta-gotchas](python-numeric-metric-delta-gotchas-2026-07-03.md) — sibling boundary bug in the same `report_changes_html` diff path (numeric formatting vs. empty-group semantics); both were happy-path-invisible and found by adversarial edge-case hunting.
- [today-anchored-cadence-period-streak](../design-patterns/today-anchored-cadence-period-streak-2026-07-09.md) — another mechanically-computed user-facing signal that goes plausible-but-wrong in a quiet/lapsed period; shares the warn-never-fail render discipline.
- [cadence-scoped-prior-report-selection](../design-patterns/cadence-scoped-prior-report-selection-2026-07-03.md) — chooses the prior report this diff runs against (upstream of the bug).

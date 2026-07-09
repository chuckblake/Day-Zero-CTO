---
title: "DAYZEROCTO-10: Add a golden test locking the template's section spine"
status: planned
priority: p2
created: 2026-07-09
effort: small
tags: [testing, ceo-report, renderer, template-drift]
linear_id: DAYZEROCTO-10
---

# DAYZEROCTO-10: Add a golden test locking the template's section spine

## Goal
Make the section-spine pact in `docs/ceo-report-template.md` mechanically enforced instead of
comment-enforced: one golden test renders a v1 CEO report and asserts the 11 sections appear in
the template's documented order, so the canonical doc and `scripts/dzcto_artifact.py` cannot
drift apart silently.

## Prior Solutions
- `docs/solutions/conventions/skill-md-schema-lockstep-test-2026-07-03.md` — the same drift class, already solved once: extract the contract text by a stable heading, assert its *existence* (`assertIn`) before comparing, and pair the test with an in-source guard comment so the editor is told the rule and the test catches them when they ignore it.
- `docs/solutions/architecture-patterns/helper-computes-agent-narrates-2026-07-03.md` — why the renderer (not the agent) owns section structure; that ownership is what makes the spine testable at all.

## Approach
The 11 sections are produced by two entry points, not one, so the test must compose them the way
`main()` does (`scripts/dzcto_artifact.py:6188`) to see the whole page:

- Sections 3–10 come from `render_structured_report("ceo-updates", data, previous_data=None, ...)`.
- Sections 1, 2, 11 (masthead, lede deck, footer) come from wrapping that body in
  `render_report_page(title, date, "ceo-updates", body, provenance, sticky_title, lede=report_lead_summary(data))`.

Passing `previous_data=None` exercises the always-present week-over-week placeholder
("First report — no prior baseline."), matching the template's rule that section 3 never
disappears on a first report.

Assert against **stable text/structural anchors**, not markup or styling — per the issue's
constraint that the test must survive CSS changes. Candidate anchors, most seen directly in the
renderer: `class="eyebrow"` (masthead), the `headline` string (lede), `<h2>Week over week</h2>`,
`aria-label="Follow-up signals"`, the `Progress` / `Risks / Blockers` / `Asks / Decisions` /
`Next` list-section headings, `<span>Sources</span>`, and `class="app-footer"` (footer). The
`Metrics` heading and the exact `"ceo-updates"` renderer key are inferred from the template's
spine table — confirm both against `render_metrics` and `REPORT_FOLDERS` while implementing.

Two assertions carry the acceptance criteria:

1. **Presence** — each of the 11 anchors is found in the rendered HTML (a removed or renamed
   section fails here with a message naming the section).
2. **Order** — `html.index(anchor)` is strictly increasing across the 11 anchors in template
   order (a reordered section fails here).

Drive the anchor list from a single ordered constant so the test reads as the spine table it
mirrors, and the failure message points back at `docs/ceo-report-template.md`.

## Files
- Modify: `tests/test_dzcto_artifact.py` — add `TestReportSectionSpine` (reuses the existing
  module-level `v1_report(**overrides)` fixture at line 16; no new fixture needed).

Explicitly untouched, per the issue's Scope: `scripts/dzcto_artifact.py` (renderer) and
`docs/ceo-report-template.md` (template). The test reads the spine from the template's table but
does not edit it.

## Plan
- [x] Add an ordered `SPINE` constant to `tests/test_dzcto_artifact.py` — 11 `(section_name, anchor)` pairs in template order.
- [x] Add `TestReportSectionSpine` that builds `v1_report()`, renders the body via `render_structured_report("ceo-updates", data, previous_data=None)`, and wraps it via `render_report_page(..., lede=report_lead_summary(data))`.
- [x] Assert every anchor is present, failing with the section name and a pointer to `docs/ceo-report-template.md`.
- [x] Assert anchor indices strictly increase across the spine, failing with the first out-of-order section pair.
- [x] Verify the test is real: temporarily reorder or delete one section in the renderer, confirm the test goes red, revert.
- [x] Run `python3 -m unittest discover -s tests` — the existing suite (40+ tests) stays green.

## Decisions

### Render the full 11-section spine with a longer fixture — 2026-07-09
Picked `v1_report(next=["Billing", "Launch"])` for the golden render so `render_action_summary`
keeps the Follow-up signals section. Rejected the default fixture unchanged because the renderer
intentionally suppresses that summary when it would duplicate a very short report, leaving only
10 rendered sections for the spine test.

### Keep page-chrome anchors structural, content anchors visible — 2026-07-09
Picked structural anchors for Masthead and Footer, where visible text is duplicated elsewhere in
the document, and visible section text for the report body wherever possible. Rejected using only
visible strings because the title and tool/version text can appear outside the spine order.

## Open Questions
- **Scope addition, not taken here.** The lockstep prior art pairs its test with an in-source guard
  comment telling the next editor the rule. The equivalent move would be a one-line note under the
  spine table in `docs/ceo-report-template.md` pointing at this test — but the issue's Scope puts
  "changing the renderer or template themselves" explicitly Out. Flagged on the backlog issue;
  needs an owner's call before anyone adds it. Not a deliverable of this plan.
- One judgment call left to implementation: whether the masthead and footer anchors should be CSS
  classes (`eyebrow`, `app-footer`) or visible text. Classes are proposed above because they are
  structural rather than cosmetic, but a future styling pass that renames them would require
  updating the test — an acceptable trade, since a renamed page-chrome class is a real change to
  the spine's rendering contract.

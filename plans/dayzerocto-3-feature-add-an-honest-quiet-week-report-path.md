---
title: "DAYZEROCTO-3: Add an honest quiet-week report path"
status: planned
priority: p1
created: 2026-07-09
effort: medium
tags: [ceo-report, renderer, skill-design, template, principle-ritual-over-highlights]
linear_id: DAYZEROCTO-3
---

# DAYZEROCTO-3: Add an honest quiet-week report path

## Goal

Give a low-activity reporting window a first-class, honest shape: the renderer stops manufacturing
bad news out of an empty week, required sections say "none this window" instead of vanishing, and
the weekly skill tells the agent how to write a quiet week without padding it.

---

## Problem Frame

Planning found the gap is worse than "sections disappear." Verified against source:

**1. The renderer actively invents bad news on a quiet week.** `report_changes_html` computes the
always-rendered *Week over week* section as a mechanical set-difference. When `progress` is empty
this week and the prior report had items, every prior item is emitted under `No longer listed:`.
Executing the real code against a quiet fixture:

```
Progress: No longer listed: Login shipped
Next: No longer listed: Billing; Launch
```

To a CEO that reads as *"we walked back the login and dropped the roadmap."* The template's own
rationale for that phrasing — "a mechanical diff cannot distinguish *completed* from *dropped*"
(`docs/ceo-report-template.md:89-90`) — has a third case it never considered: **neither**. Nothing
happened. Emitting a false reversal is the mirror image of padding, and it trips the same guardrail
("never omit or soften bad news … to make a report read better" cuts both ways: don't fabricate it
either). This section renders *above* everything else in the body, so any placeholder work below it
is cosmetic until this is fixed.

**2. Required sections vanish rather than render empty.** `render_list_section` returns `""` when
`array_value(items)` is empty (`scripts/dzcto_artifact.py:1284-1287`); so do `render_metrics` and
`render_sources`. A reader cannot distinguish *"no risks this week"* from *"the tool dropped the
Risks section."* Verified: a fully-quiet report's entire body is the Week-over-week strip alone.

**3. Nothing in the product acknowledges quiet weeks exist.** `rg -i quiet` over `skills/`,
`scripts/`, and `docs/` returns zero hits — only `PRODUCT_STRATEGY.md` matches, where the principle
lives. The weekly skill's writing step assumes there is progress to report.

The strategy principle ("Ritual over highlights") has no implementation surface, at exactly the
moment the user is most likely to break the ritual.

---

## Context

### Relevant code

| Site | What it does today |
| --- | --- |
| `scripts/dzcto_artifact.py:1898` `report_changes_html` | Always emits *Week over week* for `ceo-updates`. Empty current group + populated prior → `No longer listed: <all prior items>`. **The blocker.** |
| `scripts/dzcto_artifact.py:1284` `render_list_section` | Returns `""` on empty. **18 call sites across 6 report kinds** — a global behavior change would leak placeholders into tech-stack, engineering-risk, weekly-review, codebase-accountability. |
| `scripts/dzcto_artifact.py:1476` `render_sources` | Returns `""` on empty. **7 call sites across every report kind** — same shared-function hazard as `render_list_section`. |
| `scripts/dzcto_artifact.py:1252` `render_metrics` | Returns `""` on empty. `metrics` is the one *optional* schema key. |
| `scripts/dzcto_artifact.py:1604` `render_ceo_update` | Composes metrics → progress → risks → asks → next → sources. |
| `scripts/dzcto_artifact.py:1525` `render_action_summary` | *Follow-up signals* strip; self-suppresses when `max_group <= 2 and total_items <= 3`. |
| `scripts/dzcto_artifact.py:2435` `validate_ceo_report` | Warn-only. Checks key **presence**, not emptiness — `progress: []` validates clean. Called at `:6259`, stderr only, never blocks the write. |

### Verified facts that shape the design

- **`present(0)` is `True`** (`:1183-1190` falls through to `return True`). `present(False)` is `True`
  too. So `prs_merged: 0` renders a real `0` tile — zero-metrics do **not** silently vanish. The
  actual hazard is the agent *dropping the `metrics` key*, which kills the honest `8 → 0` delta
  (`metric_delta_items:1861` requires dict metrics in **both** reports).
- **The lockstep test covers only one block.** `TestSkillSchemaLockstep`
  (`tests/test_dzcto_artifact.py:393`) extracts `## Report JSON schema (v1)` up to the next `## `.
  Prose in Workflow and Standards is **outside** it and free to differ per skill. Carry-forward
  guidance already differs there today.
- **The golden spine test is not threatened.** `TestReportSectionSpine` (`:321`) asserts section
  order for a *populated* fixture. Placeholders render *inside* existing sections; no section is
  added, removed, or reordered. The spine table and `SPINE` constant need no change.
- **No existing test asserts that empty sections vanish.** Nothing to un-break.
- **`render_action_summary` suppresses only on a *sparse* quiet week.** Verified by execution: one
  carried risk → `""`; but two risks + one ask + one next (`total_items == 4`) clears the
  `total_items <= 3` threshold and the strip **renders**. Since KTD2 says a correctly authored quiet
  week carries items forward, *Follow-up signals* is present on realistic quiet weeks and absent only
  on very sparse ones. Any test asserting its absence must pin a sparse fixture.

### Prior Solutions

- `docs/solutions/architecture-patterns/helper-computes-agent-narrates-2026-07-03.md` — *"anything
  checkable is computed by the helper; the agent only narrates."* This decides the central question
  (see KTD1): emptiness is code-checkable, so the renderer computes and labels it. An agent-authored
  `quiet_week: true` would be the agent asserting a fact it can contradict.
- `docs/solutions/conventions/skill-md-schema-lockstep-test-2026-07-03.md` — any field added to the
  schema block lands byte-identical in **both** skills. Reinforces KTD1: no new field, no lockstep churn.
- `docs/solutions/best-practices/audit-for-dead-but-complete-machinery-2026-07-03.md` — grep for
  existing empty-state machinery before building new. Paid off: `.empty-item` is the established
  placeholder class (`:4951`), already used at `:2011`, `:2312`, `:4002`, `:5473`. Reuse, don't invent.
- `docs/solutions/logic-errors/python-numeric-metric-delta-gotchas-2026-07-03.md` — the specific
  numeric bugs are not in scope, but its contract is inherited: **this code runs in the warn-never-fail
  write path — degrade, never raise** — and *verify empties by execution, not by reasoning*.
- `docs/solutions/architecture-patterns/secret-scanning-shape-detection-and-split-fail-policy.md` —
  any new **free-text** authored field is a new egress input that must be enumerated in
  `sanitize_current_report_data`. Narrating quietness in the already-scanned `headline` costs nothing.
- `docs/solutions/design-patterns/cadence-scoped-prior-report-selection-2026-07-03.md` — the
  week-over-week machinery a quiet week leans on hardest; carry-forward-verbatim is what keeps its
  mechanical diff honest.

### Repo conventions that constrain this work

- `AGENTS.md:39` — report list sections "render as simple bold-led lists, not bordered cards."
  A quiet-week note is a muted paragraph, not a card.
- `AGENTS.md:47-49` — run `python3 -m py_compile`, then `python3 -m unittest discover -s tests`
  (65 tests currently), then smoke-test `dzcto artifact --kind ceo-updates` against a temp folder.
- `AGENTS.md:12` — skill instructions stay agent-neutral.
- `docs/ceo-report-template.md:7` — doc and renderer disagree ⇒ fix one of them *in the same change*.

---

## Key Technical Decisions

### KTD1. No new JSON schema field. The renderer computes emptiness; the agent narrates it in `headline`.

Rejected: `quiet_week: true`. Three independent reasons converge:

1. *Helper computes, agent narrates.* Whether sections are empty is mechanically checkable. An
   authored boolean can contradict the data (flag says quiet, sections are full) — a hallucination
   surface the pattern exists to eliminate.
2. *Lockstep cost.* The schema block is byte-identical across both skills. `quiet_week` is
   semantically wrong in an ad_hoc report over an arbitrary date range, yet the test would force it there.
3. *Egress cost.* A free-text quiet-week note would be a new user-controlled input reaching disk,
   requiring enumeration in the secret scanner. `headline` is already scanned.

The agent's job is prose ("A quiet week: no code shipped; the vendor SLA risk carries forward").
The renderer's job is to label the empty sections and to not lie about the diff.

### KTD2. "Quiet week" is **not** "all sections empty." Fix per-section, not globally.

This is the trap. Skill guidance tells the agent to **carry still-true risks and asks forward**, so a
*correctly authored* quiet report has non-empty `risks_blockers` and `asks_decisions`. An
all-sections-empty precondition would therefore rarely fire on the reports it is meant to serve —
and would fire on reports where the agent simply forgot.

So there is no global "quiet mode" and no quiet-week branch in the renderer. Each section stands on
its own: if it is empty, it says so. A quiet week is just the case where several of them are.

### KTD3. Required schema keys always render. Optional keys may vanish.

The clean, statable line — and it happens to match `validate_ceo_report`'s own required-key list:

- **Always render** (required keys): `progress`, `risks_blockers`, `asks_decisions`, `next`, `sources`.
- **May vanish** (optional / derived): `metrics` (the only optional key), and *Follow-up signals*
  (a derived triage card that self-suppresses by design).

`sources` is included deliberately. The guardrail "never state work that cannot be traced to actual
repo evidence" makes a silently-absent evidence list the exact ambiguity this feature exists to kill.

### KTD4. `empty_note` is opt-in per call site — for **both** shared helpers.

`render_list_section` has **18 call sites across 6 report kinds**, and `render_sources` has **7**.
Making either emit placeholders unconditionally would regress tech-stack ("Onboarding Notes: none"),
engineering-risk, weekly-review, and codebase-accountability reports — and would leak KTD5's
`ceo-updates`-specific "this window" wording into kinds where it is meaningless.

Both signatures gain a defaulted note: `render_list_section(title, items, empty_note=None)` and
`render_sources(data, empty_note=None)`. `None` preserves today's exact vanish behavior for every
existing positional caller. **Only `render_ceo_update` passes a note.** Regression tests must guard
both helpers, not just the list one.

### KTD5. Placeholder wording is cadence-neutral and states absence, not failure to record.

Both `weekly` and `ad_hoc` share `kind == "ceo-updates"`, so wording cannot say "week." And
"None recorded" reads as a process miss ("we failed to record") rather than a fact ("there were
none"). Use "this window" and phrase the absence positively. Wording below is directional.

### KTD6. The validator warning is a plain empty-report tripwire — nothing more.

It is tempting to claim the all-empty warn "distinguishes an intentional quiet week from an agent
that forgot." **It cannot**, and the plan must not pretend otherwise: the two produce byte-identical
JSON, and the only distinguisher is `headline` prose, which KTD1 deliberately leaves un-checkable.
Per KTD2 it also misses the common carried-forward quiet week entirely.

It is still worth having as a cheap, warn-only nudge toward narrating the window. It ships with an
honest justification, not an inflated one.

---

## High-Level Technical Design

> *Directional guidance for review, not implementation specification. The implementing agent should
> treat this as context, not code to reproduce.*

The diff-phrasing fix (U1) — the third case the current logic collapses into the second:

```
for each change group (Progress, Risks/Blockers, Asks/Decisions, Next):

    prior lacks the section entirely   -> "Not comparable — prior report lacked this section."   (unchanged, still wins)
    current == []  and  prior != []    -> "No items this window."          <-- NEW. today: "No longer listed: <every prior item>"
    current == []  and  prior == []    -> emit nothing                                            (unchanged)
    otherwise                          -> "Added: …" / "No longer listed: …" set-difference       (unchanged)
```

Note the counter: the new branch must still increment `group_changes`, or the
`No material structured changes` fallback (`:1962-1968`) fires *alongside* it and the section
contradicts itself.

Section rendering (U2), required keys only:

```
render_list_section(title, items, empty_note=None)      # 18 call sites; only render_ceo_update passes a note
render_sources(data, empty_note=None)                   #  7 call sites; only render_ceo_update passes a note

    rows empty and empty_note is None  -> ""                                    (today; every other call site)
    rows empty and empty_note given    -> <h2>title</h2> + <p class="empty-item">empty_note</p>
```

What a quiet week looks like before and after:

| Section | Today | After |
| --- | --- | --- |
| Week over week | `Progress: No longer listed: Login shipped` | `Progress: No items this window.` |
| Progress | *(absent)* | `No progress to report for this window.` |
| Risks / Blockers | carried-forward risk renders | *(unchanged)* |
| Asks / Decisions | *(absent)* | `No asks or decisions this window.` |
| Next | *(absent)* | `Nothing queued for the next window.` |
| Metrics | *(absent when key dropped)* | *(absent — optional key; skill tells agent to emit `0`s)* |
| Follow-up signals | absent if ≤3 carried items, present if ≥4 | *(unchanged — not touched)* |
| Sources | *(absent)* | `No evidence sources recorded for this window.` |

Only the `ceo-updates` path changes. Every other report kind renders byte-identically to today —
that is what the defaulted `empty_note` on both shared helpers buys.

---

## Files

- Modify: `scripts/dzcto_artifact.py` — `report_changes_html` (U1); `render_list_section` and
  `render_sources` (both gain a defaulted `empty_note`) plus `render_ceo_update` (U2);
  `validate_ceo_report` (U4)
- Modify: `skills/dzcto-ceo-report-weekly/SKILL.md` (U3)
- Modify: `skills/dzcto-ceo-report/SKILL.md` (U6 — scope addition, see Open Questions)
- Modify: `docs/ceo-report-template.md` (U5)
- Test: `tests/test_dzcto_artifact.py` (U1, U2, U3, U4, U6)

No new files. No new dependencies (stdlib only). No CSS changes — `.empty-item` already exists at
`scripts/dzcto_artifact.py:4951`.

---

## Plan

### U1. Stop the week-over-week diff from reporting a quiet window as a reversal

**Goal:** An empty current group against a populated prior renders "No items this window," not
"No longer listed: <every prior item>."

**Dependencies:** None. **This lands first** — it is the blocker, and U2 is cosmetic without it.

**This is a general diff-phrasing change, not a quiet-week-gated one.** It fires on *any*
`ceo-updates` report whose group empties out — including a busy week that resolves every ask. So the
replacement must not lose information the old phrasing carried: prefer
`Asks / Decisions: No items this window (prior listed: Approve budget).` over a bare
`No items this window.` The old text's sin was the false *reversal* reading of "No longer listed," not
the item names. Keep the names; drop the implication.

**Files:** Modify `scripts/dzcto_artifact.py` (`report_changes_html`, ~`:1930-1949`);
Test `tests/test_dzcto_artifact.py` (`TestReportChangesHtml`)

**Approach:**
- Add the wholesale-empty-current-group branch shown in the design sketch, ordered *after* the
  existing `not_comparable` check so "prior lacked this section" still wins.
- Distinguish *empty* (`current == []`) from *shrunk* (`current == ["A"]`, prior `["A","B"]`). Only
  the former gets the new phrasing; a genuinely dropped item must still read "No longer listed."
- Increment `group_changes` in the new branch. Otherwise the `group_changes == 0` guard at `:1962`
  lets the "No material structured changes" fallback render underneath a section that just listed
  four groups of changes.
- `per_group` is `True` only for `ceo-updates`; leave the legacy capped path for other kinds alone.

**Patterns to follow:** the existing per-group branch structure at `:1941-1950`; the labeled-placeholder
voice of `"Not comparable — prior report lacked this section."` (`:1932`).

**Test scenarios:**
- Happy path: quiet current (`progress=[]`, `next=[]`) vs populated prior → HTML contains
  `No items this window` for both groups and **does not** contain `No longer listed`.
- Edge case: prior `["A","B"]`, current `["A"]` → still renders `No longer listed: B`. The fix must
  not swallow real removals.
- Edge case: prior `[]`, current `[]` → that group emits no line at all.
- Edge case: a report where *every* group is empty-vs-populated → each group renders its "No items"
  line, and `No material structured changes` is **absent** (the `group_changes` counter regression).
- Edge case: prior report lacking the `progress` key entirely → `Not comparable` still wins over the
  new branch.
- Integration: `render_structured_report("ceo-updates", quiet, previous_data=busy)` — the composed
  body carries the new phrasing.
- Regression: existing `TestReportChangesHtml` (15 methods) stays green untouched.

**Verification:** A quiet report diffed against a busy prior no longer implies work was reverted.

---

### U2. Required-key sections always render; optional keys may vanish

**Goal:** Progress, Risks / Blockers, Asks / Decisions, Next, and Sources always render their heading,
with a muted `.empty-item` placeholder when empty. Everything else keeps today's behavior.

**Dependencies:** None (independent of U1, but lands after it so the quiet-week fixture tests one
coherent output).

**Files:** Modify `scripts/dzcto_artifact.py` (`render_list_section:1284`, `render_sources:1476`,
`render_ceo_update:1604`); Test `tests/test_dzcto_artifact.py`

**Approach:**
- `render_list_section(title, items, empty_note=None)`. When rows are empty and `empty_note` is
  falsy → return `""` exactly as today (KTD4: 14 other call sites depend on this).
- `render_ceo_update` passes a note for its four required list sections only. Directional wording:
  - Progress — `No progress to report for this window.`
  - Risks / Blockers — `No risks or blockers this window.`
  - Asks / Decisions — `No asks or decisions this window.`
  - Next — `Nothing queued for the next window.`
- `render_sources(data, empty_note=None)` gains the **same opt-in** (KTD4 — it has 7 call sites across
  every report kind; an unconditional empty state would regress four of them). Only `render_ceo_update`
  passes `No evidence sources recorded for this window.` It is a `<details>` element, so the placeholder
  goes in the body and the `<summary>` count reads `0 sources`. Keep it collapsible for shape consistency.
- **Do not** touch `render_metrics` — `metrics` is the only optional schema key (`validate_ceo_report`
  omits it from the required list). It legitimately vanishes. U3 handles the honest-zeros instruction.
- **Do not** touch `render_action_summary` — its self-suppression is deliberate.
- Reuse `.empty-item` (`:4951`, `color: var(--faint)`). No new CSS. Muted paragraph, not a card
  (`AGENTS.md:39`).

**Execution note:** Per the numeric-gotchas lesson, verify the empty variants by execution rather
than reasoning: `None`, `[]`, `[""]`, `[{}]`, and whitespace-only strings all collapse to `[]` via
`array_value`'s `present` filter — confirm each renders the placeholder and none raises.

**Patterns to follow:** `.empty-item` usage at `:2011` and `:5473`; the spine-invariant placeholder
precedent in `report_changes_html:1910-1915`.

**Test scenarios:**
- Happy path: **sparse** quiet fixture (`progress/asks/next = []`, exactly **one** carried risk,
  `metrics={}`, `sources=[]`) → `<h2>Progress</h2>` present with its placeholder; same for
  Asks / Decisions, Next, Sources; the carried risk renders normally in Risks / Blockers.
- Happy path: quiet fixture → the four required headings appear in **spine order**, and Masthead /
  Lede / Week-over-week / Footer are present.
- Edge case: sparse quiet fixture → Metrics is **absent** (optional key) and Follow-up signals is
  **absent**. Pin the fixture to one carried item: with `total_items >= 4` the strip *renders*
  (verified). Comment the fixture so a later author does not "make it realistic" and break the test.
- Edge case: `progress=[""]` and `progress=[{}]` → placeholder renders (the `present` filter empties them).
- Regression: populated `v1_report()` fixture → **no** `empty-item` string anywhere in the body.
- Regression (blast radius, `render_list_section`): `render_engineering_risk` with `mitigations=[]` →
  Mitigations section still vanishes. Same for `render_tech_stack` with `onboarding_notes=[]`.
- Regression (blast radius, `render_sources`): `render_engineering_risk` and `render_tech_stack` with
  `sources=[]` → Sources section still **vanishes**, with no `this window` wording anywhere. Without
  this test the `render_sources` regression ships green — it is the guard KTD4 exists for.
- Regression: `TestReportSectionSpine` (both methods) stays green — no section added or reordered.

**Verification:** A reader can tell "no risks this week" from "the tool dropped the section," and no
other report kind changed shape.

---

### U3. Quiet-week authoring guidance in the weekly skill

**Goal:** The weekly skill tells the agent how to recognize and write a quiet week honestly.

**Dependencies:** U1, U2 (guidance should describe behavior that exists).

**Files:** Modify `skills/dzcto-ceo-report-weekly/SKILL.md`; Test `tests/test_dzcto_artifact.py`

**Approach:** Split the instruction by workflow stage, mirroring how DAYZEROCTO-2 placed the bad-news
guidance (gather in step 4, write in step 6 / Standards). All of it lands **outside** the
`## Report JSON schema (v1)` block, so the lockstep test is untouched.

- **Step 4 (gather)** — recognize a low-activity window: few or no commits, PRs, or merges in the
  selected week.
- **Step 6 (write)** — the quiet-week contract:
  - State it plainly in `headline`. A quiet week is the report's most important truth.
  - **Never pad.** Do not manufacture progress, inflate minor work, or restate old wins as new.
  - Carry still-true risks, asks, **and next items** forward *verbatim*. (Verbatim matters: drifted
    wording renders as *both* `Added: <new>` and `No longer listed: <old>` — phantom churn in the very
    section meant to signal continuity.)
  - **Report zeros explicitly.** Keep the `metrics` key with `prs_merged: 0` rather than dropping it —
    dropping it hides the honest `8 → 0` delta, because `metric_delta_items` needs metrics in both
    reports. Omitting a zero is padding by omission.
  - Leave genuinely empty sections empty. The renderer labels them; that is the honest output.
- **Standards** — one bullet: prefer an honest quiet-week report over skipping the week.
- **Must not imply the streak.** Per the North Star exclusion, a window with no actual work does not
  count toward the three-week streak. Say nothing that licenses counting it. The quiet-week report is
  about honesty and ritual continuity, not the metric.
- Preserve the three phrases `TestSkillBadNewsInstructions` asserts: `reverts or reverted commits`,
  `failing or red ci`, `slipped or descoped work`.
- Keep it concise and agent-neutral (`AGENTS.md:12`, `:26`).

**Patterns to follow:** the step-4 / step-6 split from `plans/dayzerocto-2-…`;
`TestSkillBadNewsInstructions` (`tests/test_dzcto_artifact.py:410`) as the literal-substring precedent.

**Test scenarios:**
- Happy path: new `TestSkillQuietWeekInstructions` asserts the weekly SKILL.md (lowercased) contains
  the load-bearing phrases — `quiet week`, a never-pad phrase, a carry-forward-verbatim phrase, and a
  zeros/`metrics` phrase. Pick the literals from the final prose; assert the *behavior words*, not
  whole sentences, so copy-editing does not break the test.
- Edge case: assert the weekly SKILL.md does **not** contain `streak` (guards the North Star exclusion).
- Regression: `TestSkillSchemaLockstep` stays green — proof the guidance landed outside the schema block.
- Regression: `TestSkillBadNewsInstructions` stays green — the three bad-news phrases survive the edit.

**Verification:** An agent reading only the weekly SKILL.md produces an honest quiet-week report
without inventing progress, and without believing it protects a streak.

---

### U4. Warn-only empty-report tripwire

**Goal:** When every required list section is empty, `validate_ceo_report` nudges the author to
narrate the window in `headline`.

**Dependencies:** None.

**Files:** Modify `scripts/dzcto_artifact.py` (`validate_ceo_report:2435`);
Test `tests/test_dzcto_artifact.py` (`TestValidateCeoReport`)

**Approach:**
- If `progress`, `risks_blockers`, `asks_decisions`, and `next` are all empty (post-`array_value`),
  append one warning: the report has no structured content — if the window was quiet, say so in `headline`.
- **Warn-only.** Same contract as every other check here: printed to stderr at `:6259`, never blocks
  the write. This is inherited from the numeric-gotchas lesson (degrade, never raise).
- Scope the claim honestly (KTD6). This is an *empty-report tripwire*. It does **not** distinguish an
  intentional quiet week from a forgetful agent — those are byte-identical JSON — and per KTD2 it will
  not fire on the common carried-forward quiet week. Write that limitation into the code comment so
  the next reader does not over-trust it.

**Patterns to follow:** the existing warn-append style in `validate_ceo_report:2437-2472`.

**Test scenarios:**
- Happy path: all four empty → exactly one new warning, containing `headline`.
- Edge case: one carried-forward risk present, rest empty → **no** warning (documents KTD2's limitation
  as intended behavior, not a bug).
- Edge case: `metrics` and `sources` empty but the four list sections populated → no warning
  (optional/evidence keys do not trigger it).
- Edge case: keys absent entirely vs present-but-empty → both paths produce the missing-field warnings
  they already produce, plus this one; no crash on absent keys.
- Regression: a fully populated `v1_report()` → `validate_ceo_report` returns `[]` (existing
  `test_valid_v1_report_has_no_warnings`).
- Integration: the CLI write path still succeeds and writes the artifact when the warning fires.

**Verification:** A structurally empty report warns on stderr and still writes.

---

### U5. Canonize the quiet-week state in the template

**Goal:** `docs/ceo-report-template.md` documents the new rendering contract, so doc and renderer do
not disagree (`docs/ceo-report-template.md:7`).

**Dependencies:** U1, U2, U4 (document what shipped).

**Files:** Modify `docs/ceo-report-template.md`

**Approach:**
- Add a **`## Quiet windows`** section: what a quiet week is, that required sections render a labeled
  placeholder rather than vanishing, that the agent narrates quietness in `headline` and never pads,
  and — explicitly — that a quiet-week report **does not count toward the North Star streak**.
- Under *Week-over-week semantics*, document the third diff case: an empty current group renders
  "No items this window," because the mechanical diff cannot call it *completed*, *dropped*, **or**
  *nothing happened* — and the first two would be a lie.
- State the **required-renders / optional-vanishes** rule from KTD3, naming `metrics` and Follow-up
  signals as the conditional sections. The spine table currently reads as if all 11 always render;
  that is already only true for chrome.
- Under *Conformance tiers*: the empty-section labeling and the tripwire warning are **Verifiable**;
  "state the quiet week honestly, never pad" is **Aspirational** (prompted, not machine-checked).
- **Do not** add, remove, or rename a spine-table row. Placeholders render inside existing sections.
  (If a future change *does* add a row, note that `documented_sections()` reads `cells[1]` and
  tolerates extra columns but not new numbered rows without a matching `SPINE` entry.)

**Test scenarios:** `Test expectation: none — documentation only.` The existing
`test_spine_constant_matches_template_sections` already guards the table against drift and must stay
green, which is the real assertion here.

**Verification:** `python3 -m unittest discover -s tests` green; the doc describes what the renderer does.

---

### U6. Ad-hoc skill parity — *scope addition, see Open Questions*

**Goal:** `skills/dzcto-ceo-report/SKILL.md` gets window-neutral quiet-window guidance matching U3.

**Dependencies:** U3. **Isolated by design** — drop this unit and U1–U5 still ship coherently.

**Files:** Modify `skills/dzcto-ceo-report/SKILL.md`; Test `tests/test_dzcto_artifact.py`

**Approach:** U1, U2, and U4 all land on the shared `kind == "ceo-updates"` path, so an ad_hoc report
over a low-activity range already gets the placeholders and the tripwire — while no skill tells that
agent to narrate the quiet window. Guidance-only asymmetry, no code difference.

- Same substance as U3, worded for an arbitrary range: "low-activity window" / "this window", never "week."
- Lands in Workflow step 4 / step 6 and Standards — **outside** the locked schema block.
- Omit the streak sentence entirely; the North Star is a *weekly* metric.

**Patterns to follow:** U3; the way `TestSkillBadNewsInstructions` asserts across both skills.

**Test scenarios:**
- Happy path: extend the quiet-week substring assertions to both skills (mirroring
  `TestSkillBadNewsInstructions.SKILLS`), with the cadence-specific literals excluded.
- Edge case: the ad_hoc skill contains no `week`-scoped quiet phrasing (it reports arbitrary ranges).
- Regression: `TestSkillSchemaLockstep` green.

**Verification:** Both cadences that share the renderer also share the authoring contract.

---

## Risks

| Risk | Mitigation |
| --- | --- |
| The two **shared** helpers regress — placeholders leak into tech-stack / engineering-risk / weekly-review / codebase-accountability. `render_list_section` has 18 call sites, `render_sources` has 7 | `empty_note=None` default on **both** preserves exact current behavior; U2 carries regression tests on two other report kinds for **each** helper. `render_sources` is the easy one to forget — it takes only `data` today |
| U1's new branch swallows a *genuine* removal, hiding real dropped work — inverting the fix | Branch on `current == []` only, never on "current is smaller"; U1 test asserts prior `[A,B]` → current `[A]` still reads "No longer listed: B" |
| U1 forgets to increment `group_changes`, so "No material structured changes" renders alongside the per-group lines | Named in the design sketch and covered by a dedicated U1 test |
| The tripwire (U4) gets over-trusted as a quiet-week detector and something later depends on it | KTD6 states the limitation; it is repeated in the code comment and asserted by the "carried risk → no warning" test |
| Carry-forward wording drift produces phantom `Added` + `No longer listed` churn in the section meant to show continuity | Pre-existing hazard; U3 calls out *verbatim* explicitly. Not newly introduced here |
| Guidance implies a quiet report protects the streak, contradicting the North Star exclusion | U3 forbids it; a test asserts `streak` is absent from the weekly skill |
| Doc and renderer drift (`docs/ceo-report-template.md:7`) | U5 lands in the same change; the spine golden test guards the table |

---

## Scope Boundaries

- No new JSON schema field, and no edit to the `## Report JSON schema (v1)` block in either skill.
- No change to `render_metrics` (`metrics` is optional and may legitimately vanish) or to
  `render_action_summary`'s self-suppression.
- No streak computation. Nothing in this repo computes the North Star streak today; that is
  DAYZEROCTO-5. This plan only avoids writing anything that would later license counting a no-work window.
- No new CSS, no new files, no new dependencies.
- Out (per the issue): auto-creating issues from future audits; scheduling recurring audits.

---

## Open Questions

### Resolved during planning

- **Explicit `quiet_week` field, renderer inference, or hybrid?** → Neither pure option. See KTD1/KTD2:
  no schema field; per-section labeling; the agent narrates in `headline`. The framing assumed
  "quiet week ⇒ all sections empty," which the carry-forward requirement makes false.
- **Does the schema lockstep force quiet-week guidance into both skills?** → No. The test covers only
  the `## Report JSON schema (v1)` block; Workflow and Standards prose is free to differ. This removed
  the stated reason for scoping guidance to the weekly skill alone (hence U6).
- **Does `0` silently vanish from metrics?** → No. `present(0) is True`, verified by execution. The real
  hazard is dropping the `metrics` key; U3 addresses it.
- **Does the golden spine test need updating?** → No. Placeholders render inside existing sections; no
  section is added, removed, or reordered.
- **What does "no empty-section artifacts" mean, given sections currently vanish?** → Required-key
  sections render a labeled `.empty-item` placeholder (KTD3); the artifact to eliminate is the *missing*
  section, not an empty one.

### Deferred / needs a call

- **U6 (ad_hoc parity) is a scope addition.** The issue scopes skill guidance to the weekly skill, but
  U1/U2/U4 change ad_hoc rendering too. Recorded as a comment on DAYZEROCTO-3. U6 is isolated — ship
  U1–U5 and drop it if the scope line should hold.
- **U1 changes an existing rendered section's phrasing**, which is inside the issue's stated renderer
  scope but is a behavior change beyond "add a quiet state." Also recorded on DAYZEROCTO-3.
- **Should *Follow-up signals* surface on a sparse quiet week?** The strip suppresses at
  `total_items <= 3`, so a quiet week carrying one or two items forward loses its top-of-report triage
  cue, while one carrying four or more keeps it. That threshold was tuned for busy reports and nobody
  has asked whether it is right for quiet ones. Left unchanged — `render_action_summary` is out of
  scope — but the discontinuity is real and worth a look if review disagrees.
- **Exact placeholder and diff wording.** Directional in this plan. Settle at implementation against
  rendered output — the surrounding sections' voice is the arbiter.

---

## Verification Contract

1. `python3 -m py_compile scripts/dzcto_artifact.py` (`AGENTS.md:47`)
2. `python3 -m unittest discover -s tests` — 65 existing tests green, plus the new ones (`AGENTS.md:48`)
3. Smoke-test the real write path against a temp folder with a **quiet** `--data-file`
   (`AGENTS.md:49`): `dzcto artifact --artifacts-dir <tmp> --kind ceo-updates --data-file <quiet.json>`
   — confirm the artifact writes, the tripwire warning appears on stderr, and the write is not blocked.
4. Render a quiet report against a **populated prior** and read the HTML top-to-bottom. The report must
   not imply that prior work was reverted or dropped. This is the acceptance check U1 exists for, and it
   is a human read, not an assertion.

## Definition of Done

- A quiet week renders as a quiet week: labeled empty sections, an honest week-over-week diff, and a
  `headline` that says so.
- **No other report kind changed shape** — guarded by regression tests on *both* shared helpers
  (`render_list_section` and `render_sources`), not just the list one.
- The template, the renderer, and the golden spine test agree.
- Nothing in the skills implies a quiet-week report advances the North Star streak.

## Decisions

### Ship ad-hoc parity with window-neutral wording — 2026-07-09

U6 shipped with U1-U5 because the renderer path already changes all `ceo-updates` reports. The
alternative was weekly-only prompt guidance, but that would leave ad-hoc reports with the new
empty-section behavior and no matching authoring contract.

### Keep prior item names in the empty-group diff — 2026-07-09

The implemented wording is `No items this window (prior listed: ...)`. A bare empty-state line was
rejected because it would hide useful prior context; the old `No longer listed` wording was rejected
because it reads like a reversal when the current group is wholly empty.

### Leave Follow-up signals suppression unchanged — 2026-07-09

`render_action_summary` still self-suppresses for sparse reports. Changing that threshold was
rejected for this issue because the quiet-window fix only needed honest body rendering and diff
phrasing; triage-card behavior remains a separate product call.

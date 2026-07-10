---
title: "DAYZEROCTO-6: Validate evidence sources at render time"
status: planned
priority: p2
created: 2026-07-09
effort: small
tags: [ceo-report, artifact, traceability, evidence, render-time, guardrail]
linear_id: DAYZEROCTO-6
artifact_contract: ce-unified-plan/v1
artifact_readiness: implementation-ready
execution: code
---

# DAYZEROCTO-6: Validate evidence sources at render time

## Goal

Turn the "claims must trace to repo evidence" guardrail from a docs convention into something the renderer upholds: when a report ships with zero cited evidence, warn on the CLI and stamp a visible thin-evidence banner into the artifact — warn-and-annotate, never hard-fail. The business contract lives on DAYZEROCTO-6; this plan owns only the engineering response.

---

## Problem Frame

Every structured report schema carries a `sources` array meant to record the evidence behind its claims, but the renderer accepts an empty or missing array silently. `render_sources` (`scripts/dzcto_artifact.py:1483`) returns `""` when there is nothing to render, and the artifact write path (`scripts/dzcto_artifact.py:6348-6407`) never warns when a report has zero cited evidence. A report full of untraceable claims renders indistinguishably from a well-evidenced one — the exact failure the product-strategy guardrail exists to prevent.

The constraint is **warn-and-annotate, not hard-fail**: an honest quiet-week report may legitimately cite thin evidence, and blocking generation would conflict with the "ritual over highlights" principle. This mirrors the warn-level posture already established by the DAYZEROCTO-4 secret scan (`print_secret_redactions`, `scripts/dzcto_artifact.py:6171`) and the schema warnings (`validate_ceo_report`, `scripts/dzcto_artifact.py:2454`), neither of which raises for warn-level findings.

---

## Context

### The three seams (resolved by code reading, not assumption)

**Seam 1 — Annotation placement is safe to centralize; `render_sources` must not change behavior.**
All eight `render_sources(...)` call sites pass the **top-level report `data`** dict, never a section or sub-dict:

| Renderer | Line | Call |
|---|---|---|
| `render_weekly_review` | 1612 | `render_sources(data)` |
| `render_ceo_update` | 1626 | `render_sources(data, "No evidence sources recorded for this window.")` |
| `render_engineering_risk` | 1639 | `render_sources(data)` |
| `render_tech_stack` | 1656 | `render_sources(data)` |
| `render_codebase_accountability` | 1675 | `render_sources(data)` |
| `render_snapshot_report` | 1780 | `render_sources(data)` |
| `render_generic_report` | 1795 | `render_sources(data)` |

Because every site is top-level, the thin-evidence signal can be centralized without per-section ripple. **Decision:** leave `render_sources`' empty branch untouched (it keeps rendering its subtle collapsed-`<details>` empty note, e.g. ceo-updates' "No evidence sources recorded for this window.") and add a **distinct, prominent top-level banner** at the single dispatch point `render_structured_report` (`scripts/dzcto_artifact.py:1998-2029`). The collapsed empty note is not "visible" enough to satisfy the AC on its own — it lives inside a closed disclosure widget — so the banner is the load-bearing annotation. An empty-sources ceo-update will show both; that overlap is acceptable (see Open Questions).

**Seam 2 — Which reports get checked: all structured reports; body-only excluded.**
Every structured kind flows through `render_structured_report`, and the body-only path (no `structured_data`, `scripts/dzcto_artifact.py:6369-6370`) never reaches it and has no `sources` array. **Decision:** the check applies to all structured reports — *not* gated on `args.kind == "ceo-updates"` the way the schema warnings at `6357` are. The CLI warning is gated on `structured_data is not None`, which structurally excludes body-only reports (they would otherwise all warn spuriously).

**Seam 3 — One source of truth for "empty".**
The CLI warning and the render banner must agree on what counts as cited evidence. `render_sources` (`1484-1485`) extracts via `array_value(value_at(data, "sources", "source_list", "evidence_sources"))` and then drops entries whose `source_entry_html` renders blank (a source with no resolvable title, `1466-1467`). **Decision:** factor **one** helper both paths call, filtering by the same `source_entry_html`-non-empty rule, so warn-but-shows / shows-but-warns skew is impossible.

### Relevant code and patterns

- `scripts/dzcto_artifact.py:1455` `source_entry_html` — the blank-row filter the helper must match.
- `scripts/dzcto_artifact.py:1483` `render_sources` — extraction + count; refactor its count to reuse the new helper.
- `scripts/dzcto_artifact.py:1998` `render_structured_report` — single dispatch point; banner injection site.
- `scripts/dzcto_artifact.py:6348-6407` — write path; CLI warning site (inside `if structured_data is not None:`).
- `scripts/dzcto_artifact.py:6171` `print_secret_redactions` / `2454` `validate_ceo_report` — warn-level, stderr, `dzcto: ` prefix, never raises. Mirror this voice.
- `tests/test_dzcto_artifact.py` — `unittest` + `subprocess`; `v1_report(**overrides)` fixture at the top.

### Institutional learnings

- `docs/solutions/` exists; no entry is specific to sources rendering. No prior-art constraint beyond the in-repo warn precedents above.

---

## Key Technical Decisions

- **Warn-and-annotate, never raise.** The CLI warning prints to `sys.stderr` with a `dzcto: ` prefix and continues; no `SystemExit`. Honors the issue's constraint and matches the redaction-warning precedent.
- **Centralized banner over per-site edits.** Inject one top-level banner in `render_structured_report` rather than changing `render_sources`' empty branch at eight call sites — safer, and keeps the happy path byte-identical.
- **Single shared helper.** Both the warning and the banner gate call `cited_evidence_sources(data)` (returns the list of sources that render non-empty). No second extraction path.
- **All structured kinds, not ceo-updates only.** `sources` is universal across the structured renderers; scoping to one kind would leave the guardrail half-enforced.

---

## Files

- Modify: `scripts/dzcto_artifact.py`
  - Add helper `cited_evidence_sources(data)` (near `render_sources`, ~1483).
  - Add `render_thin_evidence_banner()` and inject it in `render_structured_report` (~2024).
  - Refactor `render_sources` count to reuse the helper.
  - Add the CLI stderr warning in the write path inside `if structured_data is not None:` (~6356).
- Test: `tests/test_dzcto_artifact.py`
  - Unit tests for `cited_evidence_sources` (empty / missing / blank-only / populated / alias keys).
  - Unit test for banner presence/absence via `render_structured_report`.
  - Subprocess test: render an empty-sources report → assert stderr warning + banner HTML in the written file; render a populated report → assert no warning and no banner.

---

## Open Questions

### Resolved During Planning

- **Change `render_sources` or add a banner?** → Add a top-level banner; leave `render_sources` behavior intact (Seam 1).
- **Which kinds?** → All structured reports; body-only excluded structurally (Seam 2).
- **How to avoid warn/show skew?** → One shared helper (Seam 3).
- **Warning severity?** → Warn-level to stderr, never raise (issue constraint + DAYZEROCTO-4 precedent).

### Deferred to Implementation

- **Exact banner copy and CSS class name.** Directional: an `<aside class="report-thin-evidence">` above the body with text like "No cited evidence — claims in this report are not yet traceable to repo sources." Final wording/class chosen against the existing artifact stylesheet at implementation time.
- **Exact warning string.** Directional: `dzcto: no cited evidence sources — report ships with thin evidence (add sources[] to make claims traceable)`. Match the phrasing register of the existing `dzcto:` warnings.
- **Minor double-signal on empty-sources ceo-updates** (top banner + the existing collapsed "No evidence sources recorded" note). Accepted as harmless; revisit only if it reads as noise in a rendered artifact.

---

## Implementation Units

- U1. **Shared cited-evidence helper**

**Goal:** One function that decides whether a report has cited evidence, matching the renderer's blank-row filter exactly.

**Requirements:** Advances the traceability guardrail by giving both the warning and the banner a single source of truth (Seam 3).

**Dependencies:** None.

**Files:**
- Modify: `scripts/dzcto_artifact.py` (add `cited_evidence_sources`; refactor `render_sources` count to reuse it)
- Test: `tests/test_dzcto_artifact.py`

**Approach:**
- `cited_evidence_sources(data)` returns `[s for s in array_value(value_at(data, "sources", "source_list", "evidence_sources")) if source_entry_html(s)]` — reusing `source_entry_html` so the "counts as cited" rule is defined once.
- Refactor `render_sources` to derive its `rows`/count from the same helper (or a shared inner) so the collapsed-section count and the guardrail can never disagree. Keep `render_sources`' rendered output unchanged.

**Patterns to follow:** `render_sources` (`1483`), `source_entry_html` (`1455`).

**Test scenarios:**
- Happy path: `sources: ["git log"]` → helper returns 1 entry.
- Edge case: `sources: []` → returns `[]`.
- Edge case: `sources` key absent entirely → returns `[]`.
- Edge case: blank-only sources (e.g. `[{}]` or `[{"detail": "x"}]` with no title) → returns `[]` (matches `source_entry_html` dropping titleless entries).
- Edge case: alias keys `source_list` / `evidence_sources` populated → returns the entries.

**Verification:** Helper unit tests pass; existing `render_sources`-dependent output tests (if any) still pass unchanged.

---

- U2. **Visible thin-evidence banner in the artifact**

**Goal:** Stamp a prominent top-level banner into every structured report that has no cited evidence.

**Requirements:** Provides the "visible annotation in the rendered artifact" half of the guardrail.

**Dependencies:** U1.

**Files:**
- Modify: `scripts/dzcto_artifact.py` (add `render_thin_evidence_banner()`; inject in `render_structured_report` ~2024)
- Test: `tests/test_dzcto_artifact.py`

**Approach:**
- Add `render_thin_evidence_banner()` returning a small static HTML block (an `<aside>`/`<section>` with a stable class the test can assert on).
- In `render_structured_report`, when `not cited_evidence_sources(data)`, prepend the banner to the assembled body. Prepend so it reads before the sections regardless of kind; leave the `snapshot` special-casing and the "No content yet." fallback (`2027-2028`) intact.
- Do not touch `render_sources` or any per-kind renderer — the injection is entirely at the dispatch layer, so the happy path (has sources) is byte-identical.

**Technical design:** *(directional, not implementation spec)*
```
render_structured_report(kind, data, ...):
    body = <existing dispatch>
    rendered = <existing assembly>
    if not cited_evidence_sources(data):
        rendered = thin_evidence_banner() + rendered
    return rendered
```

**Patterns to follow:** existing section-render helpers that return static HTML strings (e.g. `render_snapshot_appendix`, `1740`).

**Test scenarios:**
- Happy path: `render_structured_report("ceo-updates", v1_report())` (has `sources`) → banner class **absent**.
- Edge case: `render_structured_report("ceo-updates", v1_report(sources=[]))` → banner class **present**.
- Edge case: a non-ceo kind (e.g. `weekly-reviews`) with empty sources → banner **present** (confirms it is not ceo-only).
- Integration: banner appears once, above the body, and does not suppress existing sections.

**Verification:** Rendered HTML contains the banner class exactly when `cited_evidence_sources` is empty and never otherwise.

---

- U3. **CLI warning on the write path + end-to-end coverage**

**Goal:** Emit a stderr warning when a structured report is written with no cited evidence, and prove the whole path end-to-end.

**Requirements:** Provides the "clear warning on the CLI" half of the guardrail and the "verifiable without internal details" AC.

**Dependencies:** U1 (warning gate), U2 (banner asserted by the subprocess test).

**Files:**
- Modify: `scripts/dzcto_artifact.py` (write path, inside `if structured_data is not None:` ~6356)
- Test: `tests/test_dzcto_artifact.py`

**Approach:**
- After `sanitize_current_report_data` and independent of `args.kind == "ceo-updates"`, add: `if not cited_evidence_sources(structured_data): print("dzcto: ...", file=sys.stderr)`.
- Place it inside the `if structured_data is not None:` block so the body-only path (`6369-6370`) is structurally excluded.
- Never raise — this is warn-level, matching `print_secret_redactions`.

**Execution note:** Add the subprocess characterization test first — it pins the externally observable contract (stderr line + banner in the written file) the AC cares about.

**Patterns to follow:** the schema-warning print at `6357-6359`; the stderr/`dzcto: ` voice of `print_secret_redactions` (`6171`); the existing `subprocess`-based tests in `tests/test_dzcto_artifact.py`.

**Test scenarios:**
- Integration (subprocess): render a report with `sources: []` via the artifact CLI → assert the `dzcto:` thin-evidence warning is on stderr **and** the banner class is in the written `.html`.
- Integration (subprocess): render a report with populated `sources` → assert **no** thin-evidence warning on stderr and **no** banner class in the output (happy-path silence).
- Edge case (subprocess): a body-only report (no structured data) → assert **no** thin-evidence warning (body-only path excluded).

**Verification:** `python -m unittest` (or the repo's test entrypoint) is green; the warning and banner fire together on empty sources and are both absent on populated sources.

---

## System-Wide Impact

- **Interaction graph:** One new gate at `render_structured_report` and one at the write path; both read-only over `data`. No change to prior-report location, manifest, or provenance.
- **API surface parity:** All structured kinds get the check uniformly via the shared dispatch — no per-kind drift. Body-only reports intentionally unaffected.
- **Unchanged invariants:** `render_sources` rendered output, every per-kind renderer, the happy-path artifact (reports with sources render byte-identically), and the no-hard-fail exit behavior of the write path.
- **Error propagation:** Warn-only; a thin-evidence report still writes and exits 0.

---

## Risks & Dependencies

| Risk | Mitigation |
|------|------------|
| Banner leaks onto the happy path and creates "new noise" (AC violation) | Injection gated on the shared helper; happy-path (has sources) is byte-identical because nothing on that branch changes. Subprocess test asserts absence on populated sources. |
| Warning fires on body-only reports that legitimately have no `sources` array | Warning lives inside `if structured_data is not None:`, structurally excluding the body-only path; covered by an explicit subprocess test. |
| Warn/show skew (warns but no banner, or vice versa) | Single `cited_evidence_sources` helper gates both; U1 lands first. |
| Over-scoping into claim-level traceability | Explicitly out of scope per the issue; this only checks presence of ≥1 cited source. |

---

## Sources & References

- Backlog issue: DAYZEROCTO-6 (owns the acceptance criteria and business contract)
- Related plan/precedent: `plans/dayzerocto-4-feature-scan-the-shareable-report-artifact-for-s.md` (warn-level artifact-write-path pattern)
- Related code: `scripts/dzcto_artifact.py` (`render_sources` 1483, `render_structured_report` 1998, write path 6348-6407)
- Schema doc: `docs/ceo-report-template.md`

## Decisions

### Keep the thin-evidence signal prominent but lightweight — 2026-07-09

Used a top-level `report-thin-evidence` aside with the existing medium-warning color tokens and matching `dzcto: no cited evidence sources` CLI copy. Rejected a card-style treatment or a new warning palette because the signal should be immediately visible without competing with report content or expanding the design system.

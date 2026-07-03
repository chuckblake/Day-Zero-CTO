---
title: "DAYZEROCTO-1: Standardize CEO report template with week-over-week highlights"
type: feat
status: active
priority: p2
created: 2026-07-03
effort: medium
tags: [ceo-report, template, week-over-week, skills, artifact-renderer]
linear_id: DAYZEROCTO-1
---

# DAYZEROCTO-1: Standardize CEO report template with week-over-week highlights

## Goal

Lock the CEO report format into one canonical, documented template enforced by the artifact renderer, and light up the week-over-week delta section — whose rendering machinery already exists in `scripts/dzcto_artifact.py` but is never invoked on the live write path.

The business contract (acceptance criteria) is owned by backlog issue `DAYZEROCTO-1`; this plan carries only the engineering response. Units cite the issue's criteria as AC1–AC5 by pointer.

---

## Context & Research

### What the audit of generated reports found (7 reports, 4 companies)

- The HTML section spine is **already identical everywhere**: masthead → headline lede → attention strip → metrics tiles → Progress → Risks / Blockers → Asks / Decisions → Next → Sources → footer. The canonical template should bless this, not invent a new one.
- All 7 JSONs share the same 8 top-level keys (`headline, window, metrics, progress, risks_blockers, asks_decisions, next, sources`) but the sub-shapes drift hard: `progress` has 3 variants, `risks_blockers` 4, `asks_decisions` 3 (richest forms in the GetMusic reports; flattest are bare string lists).
- Filename date-range segments use three incompatible formats (`jun-20-to-jun-26-2026`, `june-26-to-july-2-2026`, `2026-06-26-to-2026-07-02`); the ISO form is the plurality and sorts correctly.
- Missing metadata: no company/profile identity in the JSON, no true generated-at timestamp, `window` shape undefined (sometimes `{start,end}`, sometimes plus a free-text `label`).
- **No report has a week-over-week section today**, but the shared page CSS already defines the `.report-changes` block — the slot exists, unpopulated.

### What repo research found

- The de-facto template lives in code: `render_ceo_update` (`scripts/dzcto_artifact.py:1596`) fixes the section list and order; `render_report_page` / `page_shell` own the chrome; skills only author the JSON and shell out to `dzcto artifact --kind ceo-updates`.
- **The WoW machinery exists but is dead code**: `report_changes_html` (`scripts/dzcto_artifact.py:1845`) diffs added/removed items per `REPORT_CHANGE_GROUPS["ceo-updates"]` (line 1791) with graceful no-prior degradation; `previous_report_json_path` (line 2331) locates the prior sibling JSON. Their only caller, `refresh_structured_report_pages` (line 5344), has no call sites. The live write path (`main`, ~line 5954) calls `render_structured_report(args.kind, data)` with no previous-report args.
- `previous_report_json_path` uses reverse-lexicographic filename sort — wrong for legacy non-date-prefixed files (they sort as newest) and blind to windows/cadence.
- The two SKILL.md files are ~80% duplicated text; the JSON schema prose is triplicated (both SKILL.md files + `README.md` field table) and has already drifted in wording.
- `AGENTS.md` constraints: skill bodies concise/procedural, no per-skill READMEs, shared behavior belongs in `scripts/`, generated HTML must embed provenance and update the `.dzcto/` sidecar, README must be updated when behavior changes, and plugin-facing changes bump the version in `.claude-plugin/plugin.json`, `.codex-plugin/plugin.json`, and `scripts/dzcto_common.py::TOOL_VERSION` together.
- Repo has **no test suite**; the documented validation recipe is `python3 -m py_compile scripts/*.py` plus smoke-testing `dzcto init` / `dzcto artifact` against a temp artifacts dir.

### Institutional learnings

- No `docs/solutions/` corpus exists in this repo (skipped).

---

## Key Technical Decisions

- **Delta ownership: the helper computes, the agent narrates.** The WoW section is rendered deterministically by `dzcto_artifact.py` from the prior report's JSON (existing `report_changes_html` string-diff, extended with metric deltas). Skills instruct the agent to *read* the prior JSON for narrative continuity in Progress/Risks prose, but the dedicated WoW section is never agent-authored. Rationale: mechanical diffs can be noisy but cannot hallucinate; the agent-authored path has the opposite failure mode and is unverifiable.
- **Cadence-scoped prior selection.** New `report_type: weekly | ad_hoc` JSON field. A weekly report diffs against the most recent prior `weekly`; an ad-hoc report diffs against the most recent report of any type whose window ends before the current window starts. Rationale: a Tuesday ad-hoc must not rebase Friday's weekly onto a 3-day window ("everything since Tuesday" is not a week-over-week signal). **Fallback:** when no weekly-typed prior exists — true for every existing workspace on the first v1 run, since legacy reports carry no `report_type` — the weekly falls back to the most recent any-type prior with a rendered note ("prior report predates cadence tagging"); the no-prior placeholder fires only when no usable prior exists at all, so it never claims "first report" in a folder full of reports.
- **Date-based prior locator, not filename sort.** Candidate priors are sibling `*.json` (excluding `data.json` and self) ranked by `window.end` (fallback: ISO filename prefix), keeping only candidates strictly before the current window's start; tiebreak by `generated_at`. Candidates with no resolvable date are skipped with a stderr note. Rationale: legacy non-prefixed filenames sort as newest under the current lexicographic rule (edge case found in the IndieCrates folder).
- **No-prior renders a labeled placeholder, not an omitted section.** "First report — no prior baseline." Rationale: a fixed, invariant section list is what makes template conformance checkable (AC5); silently omitted sections reintroduce drift.
- **Schema v1 pins the richest observed sub-shapes.** `progress[]: {area, status, summary, items[]}`, `risks_blockers[]: {risk, detail, severity}`, `asks_decisions[]: {ask, context, owner}`, `metrics` as a flat `{label: scalar}` dict (diffability), plus new metadata: `schema_version`, `report_type`, `company`, `generated_at`, `window: {start, end}` (ISO), and `prior_report` (path or null, recorded at write time so the diff chain is auditable and frozen). Existing alias tolerance (`value_at`) stays — validation **warns, never fails**, so legacy JSON still renders.
- **ISO dates everywhere.** Filenames, `<title>`, and `window` use `YYYY-MM-DD`; the free-text `window.label` is dropped from the canonical schema (renderer may still tolerate it). Skills omit `--date`; the helper derives it from `window.end`. Mechanics: `--date`'s argparse default becomes a `None` sentinel (today's default makes omission undetectable), precedence is `window.end` > explicit `--date` (warn on disagreement — a filename/window mismatch is exactly the drift being killed) > today. This removes agent discretion over the date entirely.
- **Template doc home: `docs/ceo-report-template.md`.** Human-facing canon documenting sections, JSON schema v1, naming, and WoW semantics, with the renderer named as the enforcement point. Both SKILL.md files carry a byte-identical "Report JSON schema" block (agents need it at runtime and skill dirs must stay self-contained per the installers) and point to the doc as canon. Rationale: AGENTS.md forbids per-skill READMEs; a cross-skill `references/` pointer would break the per-skill installers.

---

## Files

- Create: `docs/ceo-report-template.md`
- Create: `tests/test_dzcto_artifact.py`
- Modify: `scripts/dzcto_artifact.py`
- Modify: `skills/dzcto-ceo-report/SKILL.md`
- Modify: `skills/dzcto-ceo-report-weekly/SKILL.md`
- Modify: `README.md`
- Modify: `.claude-plugin/plugin.json`, `.codex-plugin/plugin.json`, `.claude-plugin/marketplace.json` (both version fields), `scripts/dzcto_common.py` (version bump, release unit)

External (read-only context, not repo files): generated reports under `~/Documents/Code/chuck-vault/dzcto/<Company>/reports/ceo-updates/` — the audited corpus; existing reports are **not** retrofitted.

---

## High-Level Technical Design

> *This illustrates the intended approach and is directional guidance for review, not implementation specification. The implementing agent should treat it as context, not code to reproduce.*

```
skill (agent)                      dzcto artifact --kind ceo-updates
  authors report JSON  ──────────▶   validate_ceo_report(data)        # warn-only
  (schema v1, report_type,           locate_prior_report(dir, data)   # date+cadence rule
   window {start,end})               data["prior_report"] = path|null
                                     render_structured_report(kind, data,
                                        previous_data, previous_date) # WoW section live
                                     write HTML + JSON + data.json, provenance, manifest
```

WoW section placement: the existing prepend slot — after the masthead/lede, before the attention strip and metrics (`render_structured_report` already concatenates `change_summary` ahead of the body; no reordering code needed). Content, in order: heading naming the actual prior window/date ("since the 2026-06-26 report"), metric deltas (keys numeric in both, with direction), then added / no-longer-listed items per existing change groups (Progress, Risks / Blockers, Asks / Decisions, Next). "No longer listed" phrasing is kept verbatim — the mechanical diff cannot distinguish *completed* from *dropped*.

---

## Implementation Units

- U1. **Canonical template doc + README schema table**

**Goal:** One documented source of truth for the report template (AC2), blessing the observed de-facto standard rather than inventing a new format.

**Requirements:** AC1, AC2; feeds AC3/AC4 (see `linear_id`).

**Dependencies:** None.

**Files:**
- Create: `docs/ceo-report-template.md`
- Modify: `README.md` (field table, lines ~101–113)

**Approach:**
- Document: fixed section list and order (as rendered by `render_ceo_update` + `render_structured_report` + page chrome, with the WoW section in the existing prepend slot: after the masthead/lede, before the attention strip), JSON schema v1 with pinned sub-shapes and new metadata fields, filename/date discipline (ISO; date derived from `window.end`), WoW section semantics (prior-selection rule, cadence scoping + fallback note, no-prior placeholder, "no longer listed" phrasing), and the two-tier conformance model — *verifiable* (sections, keys, types, naming — enforced/warned by the renderer) vs. *aspirational* (tone, editorial judgment — prompted in SKILL.md only).
- Name `scripts/dzcto_artifact.py::render_ceo_update` as the enforcement point so doc and code cannot silently diverge without a reviewer noticing.
- Record the audit's drift catalogue as a short appendix (sub-shape variants, filename formats seen) — this satisfies AC1's "differences catalogued" in a durable place.

**Test scenarios:**
- Test expectation: none — documentation unit; conformance is exercised by U2–U4 tests.

**Verification:**
- Doc exists, README table matches schema v1 exactly, and every section name in the doc maps to its actual renderer — the list sections to `render_ceo_update`, the WoW section to `render_structured_report`'s prepend, masthead/lede/attention strip to the page chrome.

---

- U2. **Schema v1 metadata + warn-only validation in the renderer**

**Goal:** Reports carry the metadata the locator and diff need (`report_type`, `window {start,end}`, `company`, `generated_at`, `schema_version`), and malformed JSON warns loudly instead of silently rendering drift.

**Requirements:** AC2, AC3; prerequisite for AC4.

**Dependencies:** U1 (schema is defined there).

**Files:**
- Modify: `scripts/dzcto_artifact.py` (artifact write path `main` ~5835–5997; new `validate_ceo_report` helper near the other ceo-update helpers)
- Test: `tests/test_dzcto_artifact.py`

**Approach:**
- Validate on write: required keys present, `window.start`/`window.end` ISO-parseable and ordered, `report_type` in the enum, sub-shapes matching schema v1. Emit stderr warnings listing each violation; never abort (legacy `data.json` auto-load must keep working).
- Stamp `generated_at` (UTC ISO) and `schema_version` into the emitted JSON if absent. Date resolution: change `--date`'s argparse default to a `None` sentinel (the current default of *today* makes omission indistinguishable from an explicit flag) and resolve `window.end` > explicit `--date` (warn on disagreement) > today.
- Fill `company` from the resolved profile when absent.
- Follow the existing graceful-degradation idiom (`value_at`, alias tuples) — no behavior change for fields the renderer already tolerates.

**Test scenarios:**
- Happy path: schema-v1 JSON → no warnings; emitted JSON contains `generated_at`, `schema_version`; filename prefix equals `window.end`.
- Edge case: legacy JSON (bare-string `progress`, no `window`) → renders successfully with warnings naming each violation.
- Edge case: `--date` omitted but `window.end` present → filename uses `window.end`, not today.
- Edge case: explicit `--date` disagreeing with `window.end` → warning emitted; filename uses `window.end`.
- Error path: `window.end < window.start` → warning, report still written.

**Verification:**
- `python3 -m py_compile scripts/*.py` clean; smoke run `dzcto artifact --kind ceo-updates --data-file <v1 sample>` against a temp dir produces a dated HTML+JSON pair with the new metadata.

---

- U3. **Date/cadence-aware prior-report locator**

**Goal:** Deterministically find the correct prior report despite legacy filenames, ad-hoc/weekly interleaving, gap weeks, reruns, and corrupt files.

**Requirements:** AC4.

**Dependencies:** U2 (needs `report_type` and pinned `window`).

**Files:**
- Modify: `scripts/dzcto_artifact.py` (new `locate_prior_report`; `previous_report_json_path` at line 2331 is absorbed and deleted — no second locator survives)
- Test: `tests/test_dzcto_artifact.py`

**Approach:**
- Candidates: sibling `*.json` excluding `data.json` and the report being written (self/same-window exclusion). Effective date per candidate: `window.end`, else ISO filename prefix, else skip with a stderr note (legacy non-prefixed IndieCrates-style files must never win by lexicographic accident).
- Filter: for same-cadence weekly-vs-weekly comparison, `window.end` strictly before the current `window.end` with **no** caveat — rolling-lookback weekly profiles (`weeklyReportDefaults.lookbackDays`, `last_7_days`) overlap by design, and a permanent caveat would train readers to ignore it. Otherwise: effective date strictly before the current `window.start`; if that empties the pool (overlapping ad-hoc windows), fall back to `window.end < current window.end` and let the renderer add an "overlapping windows — deltas may double-count" caveat line (cross-cadence overlap only).
- Cadence scope: weekly → most recent prior `weekly`; when no weekly-typed prior exists (every pre-v1 workspace), fall back to the most recent any-type prior with a "prior report predates cadence tagging" note. `ad_hoc` → most recent of any type. Reports without `report_type` (legacy) are treated as `ad_hoc`.
- Tiebreak equal dates by `generated_at`. Corrupt/unparseable JSON → skip and continue (existing `read_json_file(..., {})` idiom).
- Record the chosen path (or null) as `prior_report` in the emitted JSON, stored **relative to the reports directory** (absolute paths break the audit chain when the artifacts dir moves or syncs across machines) — freezes the diff chain at write time so any future refresh re-renders but never re-selects.

**Test scenarios:**
- Happy path: two dated weeklies → newer diffs against older; `prior_report` recorded.
- Edge case: first report in a workspace → locator returns null, no error.
- Edge case: legacy non-date-prefixed JSON alongside dated ones → never selected as newest; selected as prior only if its `window` parses and qualifies.
- Edge case: gap week (prior is 3 weeks old) → still selected; heading names its actual date.
- Edge case: weekly with an interleaved ad-hoc report → weekly skips the ad-hoc, diffs against prior weekly; the ad-hoc diffs against the weekly.
- Edge case: legacy corpus, first v1 weekly (no weekly-typed priors exist) → falls back to the most recent legacy report with the cadence-tagging note; the first-report placeholder does NOT fire.
- Edge case: two weeklies from a rolling-lookback profile with overlapping windows → prior selected normally, no double-count caveat.
- Edge case: rerun of the same window → does not select itself or the file it overwrites.
- Error path: corrupt prior JSON → skipped, next candidate used, generation completes.

**Verification:**
- Unit tests above pass via `python3 -m unittest`; smoke run in a temp dir with three seeded priors (weekly, ad-hoc, legacy-name) picks the right one.

---

- U4. **Wire the week-over-week section into the live write path**

**Goal:** Every newly generated report renders the dedicated WoW section (AC4) — populated when a prior exists, labeled placeholder when not.

**Requirements:** AC4, AC5.

**Dependencies:** U3.

**Files:**
- Modify: `scripts/dzcto_artifact.py` (`main` write path ~5954; `report_changes_html` at 1845; `render_structured_report` at 1882; delete dead `refresh_structured_report_pages` at 5344 or wire it — deleting is preferred, see Scope Boundaries)
- Test: `tests/test_dzcto_artifact.py`

**Approach:**
- Wire validation (U2), prior location (U3), and the extended render call **once, after the report data is resolved** — covering *both* `render_structured_report` call sites in `main` (the `--data-file` path at ~5954 and the `data.json` auto-load path at ~5969), e.g. by hoisting a single validate/locate/render step below the data-source branching. Otherwise auto-load-path reports silently ship without the WoW section.
- Extend `report_changes_html` for ceo-updates with: metric deltas (keys numeric in both reports, rendered with direction, e.g. `prs_merged 5 → 8`), the no-prior placeholder ("First report — no prior baseline"), the cadence-tagging fallback note, and the overlapping-window caveat line when U3 flagged it.
- Lift the existing output cap for ceo-updates: `report_changes_html` currently hard-caps the whole section at 4 change lines, suppresses removed items near the cap, and truncates removals to a 1-item summary (~lines 1856–1862) — incompatible with per-group add/remove coverage. Make the bound per-group for ceo-updates and render metric deltas as their own block outside the capped list; other report kinds keep current behavior.
- Diff only groups present in both reports; a group absent from the prior renders "not comparable — prior report lacked this section" rather than "everything is new."
- Keep the existing "no material structured changes" and "no longer listed" phrasings.

**Test scenarios:**
- Happy path: prior exists, items added/removed, metric changed → section shows heading with prior date, metric delta with direction, added and no-longer-listed items per group. (Covers the issue's delta AC.)
- Happy path: no prior (first report) → placeholder section present, generation succeeds. (Covers the issue's graceful-degradation constraint.)
- Edge case: identical prior and current → "No material structured changes."
- Edge case: prior lacks `risks_blockers` → that group says "not comparable," other groups diff normally.
- Edge case: metrics keys disjoint between reports → metric delta block omitted, list diffs still render.
- Edge case: changes in all four groups plus a metric delta → every group renders; no silent truncation of later groups.
- Integration: full `dzcto artifact` run against a temp dir with a seeded prior → emitted HTML contains the `.report-changes` block and JSON contains `prior_report`.
- Integration: run with `--data-file` omitted (the `data.json` auto-load path) → WoW section and validation fire identically to the `--data-file` path.

**Verification:**
- A newly generated report in a temp workspace visibly matches the template including the WoW section (per-AC5 smoke check); rerunning with no prior yields the placeholder.

---

- U5. **Align both skills with the template + release chores**

**Goal:** Both SKILL.md files instruct agents to produce schema-v1 JSON and use the standardized invocation (AC3), and the plugin version is bumped per AGENTS.md.

**Requirements:** AC3, AC5.

**Dependencies:** U1–U4.

**Files:**
- Modify: `skills/dzcto-ceo-report/SKILL.md`
- Modify: `skills/dzcto-ceo-report-weekly/SKILL.md`
- Modify: `.claude-plugin/plugin.json`, `.codex-plugin/plugin.json`, `.claude-plugin/marketplace.json` (both version fields), `scripts/dzcto_common.py` (`TOOL_VERSION`)
- Test: `tests/test_dzcto_artifact.py` (schema-block lockstep test)

**Approach:**
- Replace each skill's step-6 JSON prose with a byte-identical "Report JSON schema (v1)" block: pinned sub-shapes, `report_type` (`weekly` in the weekly skill, `ad_hoc` in the date-range skill), ISO `window {start,end}`, `company`, and a pointer to `docs/ceo-report-template.md` as canon.
- Standardize step 7: title format `CEO Report <start> to <end>` with ISO dates only; skills omit `--date` — the helper derives it from `window.end` (U2).
- Add one instruction: read the prior report's JSON (when present) for narrative continuity — carry still-true items forward **verbatim** (stable wording is what keeps the mechanical diff clean) and express continuity color in the headline/lede prose; never author the WoW section, which the renderer computes.
- Keep bodies concise/procedural per AGENTS.md; the shared block is duplicated verbatim by design (skill dirs must stay self-contained for the installers) — note in each that the other copy must be edited in lockstep.
- Enforce lockstep durably: add a unit test that extracts the "Report JSON schema (v1)" block from both SKILL.md files and asserts byte equality (modulo each skill's pinned `report_type` value), so drift fails `python3 -m unittest` instead of relying on reviewer memory.
- Bump the version in all four locations together (both plugin manifests, both version fields in `.claude-plugin/marketplace.json`, and `TOOL_VERSION`), per AGENTS.md.

**Test scenarios:**
- Test expectation: none — prompt/manifest text; conformance of the *output* is enforced by U2 validation and exercised by U2–U4 tests.

**Verification:**
- The lockstep unit test passes; all three manifests parse (`python3 -m json.tool`) and carry the same new version as `TOOL_VERSION`; a fresh end-to-end run of each skill's documented command sequence against a temp workspace produces a conforming report (AC5 visual check).

---

## System-Wide Impact

- **Interaction graph:** the artifact write path additionally reads sibling JSONs (locator). `render_index` and manifest/provenance flows are untouched except for new JSON fields passing through.
- **Error propagation:** all new failure modes (missing prior, corrupt prior, schema violations) degrade to warnings + graceful rendering — report generation must never fail because of the WoW feature.
- **State lifecycle:** `data.json` remains the rolling latest-pointer; the locator ignores it. `prior_report` freezes diff selection at write time, eliminating refresh-time re-selection drift.
- **API surface parity:** `--kind ceo-updates` is the only active report kind; other (legacy, inactive) kinds keep their current behavior — `REPORT_CHANGE_GROUPS` changes are scoped to ceo-updates.
- **Unchanged invariants:** existing generated reports are not rewritten (issue constraint); legacy JSON keeps rendering via alias tolerance; the `dzcto` CLI surface gains no new required flags.

---

## Risks & Dependencies

| Risk | Mitigation |
|------|------------|
| Mechanical string-diff reads as noise when the agent rephrases items week to week | Keep "no longer listed" phrasing; skills instruct stable item wording; accepted v1 tradeoff (deterministic > semantic) |
| Warn-only validation lets nonconforming reports ship | Deliberate: legacy compatibility first; warnings + template doc create pressure; hard-fail can be a follow-up |
| Two SKILL.md schema blocks drift again | Byte-identical block + lockstep note + unit test asserting block equality on every test run |
| First test suite in a zero-test repo sets a convention | stdlib `unittest` only (repo is stdlib-only by design); no new dependencies |
| `dzcto_artifact.py` is a 6k-line single file | Changes cluster at known seams (write path, changes renderer, locator); no restructuring in this plan |

---

## Scope Boundaries

- No retrofitting of existing generated reports (issue constraint) — they participate as *priors* when their date is resolvable, else they're skipped with a note.
- No hard-fail schema enforcement in v1 (warn-only).
- No semantic/agent-authored delta computation; no "carried over N weeks" tracking (requires >1 prior) — both are explicit non-goals for v1.
- The `data.json` stdin auto-load footgun (stale data republished under a new date when `--data-file` is omitted) is pre-existing behavior, out of scope; flagged to the backlog (see Open Questions).
- Dead `refresh_structured_report_pages` is deleted rather than wired — resurrecting refresh is follow-up work if ever needed.
- Legacy inactive report kinds (`snapshot`, etc.) are untouched.

---

## Open Questions

### Resolved During Planning

- Delta ownership (helper vs agent): **helper computes, agent narrates** — see Key Technical Decisions.
- Does an ad-hoc report become the weekly's prior? **No — cadence-scoped via `report_type`.**
- `window` shape: **pinned `{start, end}` ISO; free-text `label` dropped from canon.**
- No-prior rendering: **labeled placeholder, section always present.**
- Template doc home: **`docs/ceo-report-template.md`** (AGENTS.md forbids per-skill READMEs; cross-skill `references/` breaks per-skill installers).

### Deferred to Implementation

- Exact warning wording and whether validation output belongs on stderr only or also in the `.dzcto` diagnostics sidecar — decide at the seam.
- Whether `render_index`'s latest-report card should surface the WoW headline — cheap if it falls out of the data, not required by the issue.

### Flagged to the backlog (comment on DAYZEROCTO-1)

- New metadata fields (`report_type`, `company`, `generated_at`, `schema_version`, `prior_report`) are scope the issue didn't enumerate but AC4 requires.
- The `data.json` auto-load footgun deserves its own issue.

---

## Decisions

### Schema block made fully byte-identical — 2026-07-03
Picked: the `report_type` value is pinned in each skill's workflow step 6, outside the shared
"Report JSON schema (v1)" block, so the blocks are 100% byte-identical and the lockstep test is
an exact string equality. Rejected: "identical modulo the report_type token" (the plan's
minimum), which would have needed a normalizing comparison — strictly weaker for no benefit.

### prior_report stored workspace-relative — 2026-07-03
Picked: `reports/ceo-updates/<file>.json` (relative to the artifacts dir), matching the
manifest's `relativePath` convention. Rejected: relative to the reports folder (bare filename)
— unambiguous today since priors are always siblings, but workspace-relative survives any
future multi-kind diffing and matches existing provenance paths.

### Version bumped to 0.9.0 — 2026-07-03
Minor bump (new feature: WoW section + schema v1), not patch; the plan left the number open.

---

## Sources & References

- Backlog issue: `DAYZEROCTO-1` (markdown backend)
- Renderer seams: `scripts/dzcto_artifact.py` — `render_ceo_update` (1596), `REPORT_CHANGE_GROUPS` (1791), `report_changes_html` (1845), `render_structured_report` (1882), `previous_report_json_path` (2331), dead `refresh_structured_report_pages` (5344), write path in `main` (~5835–5997)
- Skills: `skills/dzcto-ceo-report/SKILL.md`, `skills/dzcto-ceo-report-weekly/SKILL.md`, `skills/dzcto-init/SKILL.md`
- Conventions: `AGENTS.md` (validation recipe, version-bump rule, skill-body rules), `README.md` field table
- Audited corpus (external): `~/Documents/Code/chuck-vault/dzcto/{Glance,GetMusic,Arwen,IndieCrates}/reports/ceo-updates/`

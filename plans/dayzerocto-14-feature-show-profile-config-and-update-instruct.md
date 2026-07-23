---
title: "DAYZEROCTO-14: Show profile config and update instructions on the report index page"
type: feat
status: active
priority: p2
created: 2026-07-23
date: 2026-07-23
effort: medium
tags: [artifact-renderer, index, config, documentation, shareable-artifact]
issue_id: DAYZEROCTO-14
---

# DAYZEROCTO-14: Show profile config and update instructions on the report index page

## Goal

Surface the active profile's report-shaping configuration on the report artifact's index page, and
ship a browser-viewable settings page next to it that documents how to change each value through
`dzcto init`. Read-only display; the update path stays the CLI.

---

## Problem Frame

The values that shape every CEO report — weekly range mode, tone, evidence repos, default profile —
are resolved from `.dzcto/config.json` (workspace sidecar) and `~/.dzcto/config.json` (global
profiles) and are invisible at the one place a CTO actually looks: `index.html`. Discovering the
active weekly range currently requires reading `scripts/dzcto_artifact.py`; changing it requires
knowing that `dzcto init` is non-interactive, flag-driven, and merges over the existing profile.

No origin requirements document exists — this plan works from the backlog issue directly. The
business contract (acceptance criteria, scope, constraints) lives in DAYZEROCTO-14.

---

## Requirements Trace

Trace anchors only — DAYZEROCTO-14 owns the business contract. These R-IDs are shorthand labels the
implementation units cite; read the issue for the authoritative acceptance criteria.

- R1. The index renders the active profile's key config values.
- R2. The index links to browser-viewable documentation for changing those values via `dzcto init`.
- R3. That documentation states the merge-over semantics and the `defaultProfile` switch side effect.
- R4. Regenerating the artifact refreshes both the displayed values and the docs page.
- R5. Nothing rendered crosses the shareable-artifact trust boundary as a secret or credential.

---

## Scope Boundaries

- No editing UI, form, or write path on any rendered page — configuration changes stay in `dzcto init`.
- No new `dzcto` CLI flag. The settings page is a byproduct of the existing `init` / `artifact`
  render path, so nothing needs threading through the three-site wrapper wiring.
- No refactor of `main()` in `scripts/dzcto.py` or `scripts/dzcto_artifact.py` to expose a reusable
  `build_parser()`. See Alternative Approaches Considered.
- No change to how configuration is *resolved* (`project_config`, `profile_from_global`,
  `save_global_preferences` are read-only inputs here).

---

## Context & Research

### Relevant Code and Patterns

- `scripts/dzcto_artifact.py` — `render_index` resolves config at the top of the function
  (`repos`, `weekly_defaults`/`weekly_label`, `tone`, `artifact_dir`, `profile_name`) and renders the
  `.kpis` tile block plus a `<details class="section" id="sec-settings">` "Defaults" section holding
  two `<article class="report">` cards. That section is the sibling precedent for this work.
- `scripts/dzcto_artifact.py` — `write_html_page(...)` immediately followed by `update_manifest(...)`
  is the only precedent for writing an HTML page into the artifact root; `render_index` is currently
  its sole caller. `page_shell(...)` supplies the chrome (sticky nav, masthead, footer).
- `scripts/dzcto_common.py` — `project_config` reads the **workspace sidecar** `.dzcto/config.json`;
  `read_global_config` reads `GLOBAL_CONFIG_FILE`, a module-level constant bound to
  `Path.home() / ".dzcto" / "config.json"`. `TOOL_VERSION` is defined here.
- `scripts/dzcto_common.py` — `LOCAL_PATH_KEYS = {"projectFolder", "wikiRoot", "artifactDirectory"}`
  is the existing declaration of which config values are local-path-shaped. It is enforced by
  `sanitize_report_value` on *report data*; `render_index` does not run that sanitizer.
- `scripts/dzcto.py` — the `init` subparser declares the full operator-facing flag surface
  (`--artifacts-dir`, `--profile`, `--company-name`, `--company-description`, `--company-url`,
  `--report-prompt-context`, `--weekly-range`, `--weekly-start-day`, `--weekly-end-day`,
  `--weekly-lookback-days`, `--ceo-report-tone`, `--no-save-preferences`, `--no-switch-default`,
  `--repo`). Its `epilog` already documents the persist-to-`.dzcto/config.json` behavior.
- `skills/dzcto-init/SKILL.md` — existing prose describing the save-preferences behavior and the
  `--no-switch-default` side effect.
- `tests/test_dzcto_artifact.py` — `TestRenderIndexWeeklyStreak` and
  `TestRenderIndexWeeklyDefaultTile` are the existing `render_index` harnesses; both build a temp
  workspace and read back `index.html`.

### Institutional Learnings

- `docs/solutions/conventions/absence-proxy-assertions-break-on-additive-rendering-2026-07-23.md` —
  three live traps confirmed by reading the tests, not inferred:
  1. `TestRenderIndexWeeklyDefaultTile.weekly_tile()` slices `html[start : start + 400]` from the
     "Weekly default" KPI label. That is a fixed-width window, not a bounded element, so it already
     spills past the `.kpis` block. `test_cursor_mode_does_not_render_a_weekday_range` asserts
     `assertNotIn(" to ", tile)` over that window — `" to "` is near-inevitable in settings prose.
  2. `test_cursor_mode_suppresses_stale_start_and_end_days` asserts `"Friday"`, `"Thursday"`,
     `"Fri to Thu"`, `"7 days"` are all absent from the same 400-char window.
  3. `test_copyable_weekly_prompt_inherits_the_corrected_label` asserts
     `assertNotIn("since_last_report; Friday to Thursday", html)` over the **entire** page — any
     new surface that naively joins range + startDay + endDay reproduces that exact string.
  Additionally `TestRenderIndexWeeklyStreak.streak_tile()` slices between the "Weekly streak" and
  "Weekly default" KPI labels, so inserting a KPI tile between them breaks it.
- `docs/solutions/conventions/dzcto-engine-flag-three-site-wiring-2026-07-10.md` — `scripts/dzcto.py`
  is a whitelist wrapper, not a passthrough. This plan deliberately introduces no new flag, so the
  three-site trap does not apply; that is a design constraint, not an accident.
- `docs/solutions/architecture-patterns/helper-computes-agent-narrates-2026-07-03.md` — deterministic
  computation belongs in the Python helper. The settings page's flag list is generated from one
  in-code table rather than hand-written prose that can drift.
- `CONCEPTS.md` — the index is a **report artifact** and therefore an egress point: any newly
  rendered value crosses a trust boundary the moment the tree is shared.

### External References

None — no new technology layer; the redaction guardrail already exists in-repo.

---

## Key Technical Decisions

- **The documentation is a generated HTML page in the artifact tree (`settings.html`), not a repo
  doc.** AC#2 requires it be viewable in the browser from the index. A shared artifact tree travels
  without a repo checkout, so a `docs/*.md` link would be dead for the exact reader the feature
  targets. The cost — a second `write_html_page` + `update_manifest` site — is one function following
  an existing pair.
- **Content drift is prevented structurally, not by discipline.** A single module-level table of
  `(flag, config key, what it sets)` is the source of truth for the settings page. `skills/dzcto-init/SKILL.md`
  and the `init` epilog stay prose; the generated page is derived. A parity test pins the table's
  flags against the real `scripts/dzcto.py` `init` surface so an invented or renamed flag fails CI.
- **`defaultProfile` requires reading the global config from `render_index`, which is a new coupling
  and a test-hermeticity hazard.** `project_config(wiki_root)` reads only the workspace sidecar;
  `defaultProfile` lives in `~/.dzcto/config.json` via `read_global_config()`, whose path is the
  module-level constant `dzcto_common.GLOBAL_CONFIG_FILE`. Today no `render_index` test touches the
  developer's home directory. Adding an unseamed read would make every existing index test depend on
  the machine's real profile. The config-view helper must therefore be independently callable with
  an injected global config, and tests must patch `dzcto_common.GLOBAL_CONFIG_FILE` (resolved at call
  time inside `read_global_config`, so patching the module attribute works) rather than the real home.
- **Evidence repo paths render as basenames plus a count, not absolute paths.** Repo paths are local
  absolute paths that leak usernames and directory layout. `LOCAL_PATH_KEYS` already declares this
  class of value local-path-shaped. The index does emit `artifact_dir` verbatim in the existing
  "Serve Index" command card, but that is a card the operator must run — extending that precedent to
  a always-visible panel widens the egress surface for no operator benefit. Basenames answer "which
  repos feed this report" without the path.
- **The config panel goes inside the existing `sec-settings` "Defaults" `<details>` section, and adds
  no KPI tile.** The `.kpis` block already carries "Weekly default" and "Evidence repos"; duplicating
  them there would both clutter the CEO-facing top of the page (issue Constraint) and break the two
  KPI-slicing test helpers.
- **`toolVersion` is already rendered.** `page_shell` emits `Day Zero CTO skills v{TOOL_VERSION}` in
  every page footer. The panel surfaces it explicitly per AC#1, but this is a relocation for
  discoverability, not a new disclosure.

---

## Open Questions

### Resolved During Planning

- Generated page vs. repo doc: generated page. See Key Technical Decisions.
- Where does `defaultProfile` come from? `read_global_config()["defaultProfile"]`, not the workspace
  sidecar. Confirmed by reading `save_global_preferences`.
- Does a new page risk manifest pruning? No. `prune_manifest_report_artifacts` only drops entries
  whose `relativePath` starts with `reports/`; a root-level `settings.html` is untouched.
- Does this need a new CLI flag? No. Both `dzcto init` and `dzcto artifact` already call
  `render_index`, so regenerating the artifact refreshes the page (R4) with no wrapper changes.

### Deferred to Implementation

- Exact helper name and return shape for the config view (a dataclass vs. a plain dict) — decide when
  writing it; the plan only requires that it be callable and assertable without rendering HTML.
- Whether the parity test reads `scripts/dzcto.py` source text or introspects an argparse object.
  Source-text matching is the assumed default because the parser is built inline in `main()`; if
  implementation finds a clean introspection seam that does not require refactoring `main()`, prefer it.
- Final copy for the settings page sections. The constraint (must not reproduce the trap strings
  verbatim in the index; the settings page is a separate document and is not covered by the index
  assertions) is settled; the wording is not.

---

## Completeness / Wiring Surfaces

Derived from the sibling precedent — the existing `weeklyReportDefaults` / `ceoReportTone` "Defaults"
panel in `render_index`. Each bullet names a concrete file/pattern an implementer can open and check.

- [ ] `scripts/dzcto_artifact.py` — config value resolution at the top of `render_index` (where
      `repos`, `weekly_defaults`, `weekly_label`, `tone`, `artifact_dir`, `profile_name` are already
      computed): the new view helper is called here, not inline-expanded.
- [ ] `scripts/dzcto_artifact.py` — the `<details class="section" id="sec-settings">` "Defaults"
      block: the config panel cards and the settings-page link render here.
- [ ] `scripts/dzcto_artifact.py` — the `.kpis` tile block: verify unchanged. No tile added, removed,
      or reordered (two test helpers slice against these labels).
- [ ] `esc(...)` applied to every newly interpolated value on both the index panel and the settings
      page, matching every existing value in that section.
- [ ] `scripts/dzcto_artifact.py` — a `write_html_page(...)` + `update_manifest(...)` pair for
      `settings.html`, mirroring the existing pair at the end of `render_index`, with its own
      `provenance_payload(...)` (distinct `artifact_id` / `artifact_kind` / `relative_path`).
- [ ] `scripts/dzcto_artifact.py` — `page_shell(...)` used for the settings page chrome so the sticky
      nav links back to `index.html` and the footer carries `TOOL_VERSION`.
- [ ] `scripts/dzcto_common.py` — `TOOL_VERSION` is the single source for the displayed version;
      not re-declared or hardcoded.
- [ ] `scripts/dzcto_common.py` — `read_global_config` / `GLOBAL_CONFIG_FILE`: the `defaultProfile`
      read goes through the existing helper, and the view helper accepts an injected global config so
      tests never touch the real home directory.
- [ ] `scripts/dzcto_common.py` — `LOCAL_PATH_KEYS`: the repo-path rendering policy is consistent with
      this declaration (basenames + count, no absolute paths).
- [ ] `scripts/dzcto.py` — the `init` subparser flag surface: every flag documented on the settings
      page exists there. No flag added to the subparser, the arg-list rebuild, or the engine argparse.
- [ ] `skills/dzcto-init/SKILL.md` — existing merge-over / `--no-switch-default` prose: verified
      consistent with the generated page; a pointer to the generated page added rather than a
      duplicated flag list.
- [ ] `tests/test_dzcto_artifact.py` — `TestRenderIndexWeeklyStreak.streak_tile` and
      `TestRenderIndexWeeklyDefaultTile.weekly_tile` still pass unmodified, or a proxy assertion is
      deliberately tightened with a comment explaining why (never relaxed to accommodate new output).

---

## Implementation Units

- U1. **Profile config view helper**

**Goal:** One helper that resolves every value the index panel and settings page display, applies the
shareable-artifact rendering policy, and is testable without rendering HTML.

**Requirements:** R1, R5

**Dependencies:** None

**Files:**
- Modify: `scripts/dzcto_artifact.py`
- Test: `tests/test_dzcto_artifact.py`

**Approach:**
- Add a module-level helper near the other config resolvers (`project_config`,
  `profile_name_for_config`) that takes the already-loaded workspace config plus the wiki root and
  returns a display-ready view: profile name, `defaultProfile`, weekly range label, tone, evidence
  repo basenames + count, artifact directory presence, and `TOOL_VERSION`.
- Accept the global config as an optional injected argument defaulting to `read_global_config()`.
  This is the test seam and the reason the unit exists separately from rendering.
- Apply the repo-path policy inside the helper (basenames + count), so the policy is one testable
  decision rather than a rendering detail repeated at two call sites.
- Reuse `render_index`'s existing `weekly_label` composition rather than recomputing it — the
  cursor-mode suppression logic there is load-bearing and already pinned by tests. Extract it if
  needed, but do not fork it; two independent formatters is the exact drift
  `test_copyable_weekly_prompt_inherits_the_corrected_label` exists to prevent.
- Handle every value missing: a fresh workspace with no sidecar and no global config must produce a
  complete view with honest "not set" placeholders, never a `KeyError` or the string `None`.

**Execution note:** Write the missing-config and redaction tests before the happy path — this helper's
failure modes (leaking a path, crashing a fresh install) matter more than its success path.

**Patterns to follow:**
- `profile_name_for_config` in `scripts/dzcto_artifact.py` — same shape: takes config, returns a
  resolved display value with fallbacks.
- `docs/solutions/architecture-patterns/helper-computes-agent-narrates-2026-07-03.md`.

**Test scenarios:**
- Happy path: a workspace config with `weeklyReportDefaults`, `ceoReportTone`, and `codeRepos`, plus
  an injected global config with `defaultProfile`, returns all six AC#1 values populated.
- Edge case: empty workspace config and empty injected global config returns a complete view with
  placeholder text for every field and no exception.
- Edge case: `codeRepos` present but empty list renders a zero count and an empty repo list, not a
  stray separator or "None".
- Error path: a `codeRepos` entry that is not a string (or is whitespace) is skipped rather than
  crashing, matching the existing `repos` filter in `render_index`.
- Integration: the helper reads `defaultProfile` through `read_global_config` such that patching
  `dzcto_common.GLOBAL_CONFIG_FILE` to a temp path changes the result — proving no test can be
  contaminated by the developer's real `~/.dzcto/config.json`.
- Happy path (R5): absolute repo paths in `codeRepos` produce basenames only; the returned view
  contains no `/` -prefixed path and no home-directory segment.
- Edge case: `toolVersion` in the view equals `dzcto_common.TOOL_VERSION` rather than a literal.

**Verification:**
- The helper can be called directly in a test with an injected global config and returns every AC#1
  field; no existing `render_index` test reads the real home directory.

---

- U2. **Config panel and settings link on the index**

**Goal:** Render the config view inside the existing "Defaults" section and link to the settings page,
without disturbing the KPI block or tripping the index's absence-proxy assertions.

**Requirements:** R1, R2, R4

**Dependencies:** U1

**Files:**
- Modify: `scripts/dzcto_artifact.py`
- Test: `tests/test_dzcto_artifact.py`

**Approach:**
- Call the U1 helper in `render_index` alongside the existing config resolution, and render its values
  as additional `<article class="report">` cards inside the `sec-settings` `<details>` block, matching
  the two cards already there.
- Add the settings-page link as a card or footer link within the same section — not in the masthead or
  KPI row. The issue's constraint is that a CEO-facing share must not be cluttered with operator
  settings; consider rendering the section collapsed (drop `open`) if the added cards make it heavy.
- **Before writing any string into this section, grep `tests/test_dzcto_artifact.py` for `assertNotIn`
  and read each match.** Three assertions are live traps (see Institutional Learnings). Concretely:
  the panel must not emit `" to "`, `"Friday"`, `"Thursday"`, `"Fri to Thu"`, or `"7 days"` within
  400 characters after the `<div class="k-label">Weekly default</div>` marker, and must never emit the
  literal `since_last_report; Friday to Thursday` anywhere on the page. Rendering the panel inside
  `sec-settings` — which sits after `sec-reports` and therefore far past the 400-char window —
  satisfies the first constraint by placement; do not undo that by adding a KPI tile.
- If a proxy assertion genuinely blocks correct output, tighten it to name what it means (per the
  learning) and add a comment. Never relax it to make new output pass.
- Every value goes through `esc(...)`.

**Patterns to follow:**
- The existing Weekly range / Tone `<article class="report">` cards in the `sec-settings` block.
- `docs/solutions/conventions/absence-proxy-assertions-break-on-additive-rendering-2026-07-23.md`.

**Test scenarios:**
- Happy path: a rendered index contains the profile name, weekly range mode, tone, evidence repo
  count, `defaultProfile`, and tool version, each within the `sec-settings` section.
- Happy path (R2): the index contains a link whose href resolves to the generated settings page.
- Integration (regression guard): the whole existing `TestRenderIndexWeeklyDefaultTile` and
  `TestRenderIndexWeeklyStreak` suites pass unmodified. If any assertion had to be tightened, a test
  documents the new, narrower meaning.
- Edge case: rendering with an empty workspace and empty global config still produces a valid index
  with placeholder config values and a working settings link.
- Edge case (pins the trap): the 400-character window following the "Weekly default" KPI label
  contains none of `" to "`, `"Friday"`, `"Thursday"`, `"7 days"` when the profile is in
  `since_last_report` mode and the config panel is present — i.e. the panel did not migrate into the
  KPI region.
- Integration (R4): rendering twice with a changed `weeklyReportDefaults.range` between runs produces
  a changed panel value, proving the panel reflects current config rather than a cached first render.

**Verification:**
- `index.html` shows all six values in the Defaults section and links to the settings page; the full
  existing artifact test suite passes.

---

- U3. **Generated settings page**

**Goal:** Write a browser-viewable `settings.html` into the artifact root that documents how to change
each config value via `dzcto init`, generated from one in-code flag table.

**Requirements:** R2, R3, R4, R5

**Dependencies:** U1

**Files:**
- Modify: `scripts/dzcto_artifact.py`
- Test: `tests/test_dzcto_artifact.py`

**Approach:**
- Add a module-level table of `(flag, config key, what it sets)` covering the `dzcto init` flags that
  shape reports. This table is the single source of truth for the page and the subject of U4's
  parity test.
- Add a render function that builds the page body from that table plus the U1 config view (so the page
  shows both "here is your current value" and "here is the flag that changes it"), wraps it in
  `page_shell(...)`, and writes it with `write_html_page(...)` immediately followed by
  `update_manifest(...)` — the same pair `render_index` already uses, with its own
  `provenance_payload(...)` (distinct `artifact_id`, `artifact_kind`, and `relative_path`).
- Call it from `render_index` so both `dzcto init` and `dzcto artifact` refresh it (R4). Do not add a
  CLI flag: the three-site wrapper wiring is the trap this design avoids.
- The page must state, in prose, the two non-obvious semantics from R3: re-running `dzcto init` with
  partial flags merges over the existing profile rather than resetting it, and saving switches
  `defaultProfile` to the named profile unless `--no-switch-default` is passed.
- Same egress rules as the index: `esc(...)` everywhere, repo basenames not paths, no credential-shaped
  value rendered.

**Patterns to follow:**
- `render_index`'s closing `write_html_page` → `update_manifest` sequence in `scripts/dzcto_artifact.py`.
- `page_shell(...)` for chrome; `copy_card(...)` if example commands are worth making copyable.

**Test scenarios:**
- Happy path: rendering the index also writes `settings.html` to the artifact root.
- Happy path (R3): the page text states the merge-over behavior and names `--no-switch-default`.
- Happy path: every flag in the in-code table appears on the rendered page.
- Integration: the manifest gains an entry for `settings.html` after render, and
  `prune_manifest_report_artifacts` does not remove it on a subsequent render (its `relativePath`
  does not start with `reports/`).
- Integration (R4): changing a config value and re-rendering updates the value shown on the settings
  page.
- Edge case: rendering into a workspace with no sidecar config still writes a valid settings page
  documenting the flags, with placeholders for unset current values.
- Error path (R5): a workspace config containing a credential-shaped value (e.g. an API-key-like
  string in a documented field) does not render that value verbatim on the page.
- Edge case: the page's sticky-nav home link resolves to `index.html` from the artifact root, so the
  two pages are navigable in both directions.

**Verification:**
- Opening `settings.html` from a generated artifact tree, with no repo checkout, explains every
  displayed config value and the flag that changes it.

---

- U4. **Flag-surface parity guard and docs sync**

**Goal:** Make the settings page structurally unable to document a flag that does not exist, and point
the existing skill prose at the generated page instead of growing a second flag list.

**Requirements:** R3

**Dependencies:** U3

**Files:**
- Modify: `skills/dzcto-init/SKILL.md`
- Test: `tests/test_dzcto_artifact.py`

**Approach:**
- Add a test asserting every flag in U3's table exists in the real `dzcto init` surface. The parser is
  built inline in `main()` in `scripts/dzcto.py`, so the assumed approach is matching against the
  `init` subparser region of the source text; prefer argparse introspection if a seam exists that does
  not require refactoring `main()`.
- Add the reverse-direction assertion deliberately as a *documented* subset check, not equality:
  operator-only flags (`--no-save-preferences`, install/plumbing flags) need not appear on a
  CTO-facing settings page. The test should name which flags are intentionally undocumented so the
  omission is a decision, not a gap.
- Update `skills/dzcto-init/SKILL.md` to point at the generated settings page as the reference for
  per-flag detail, keeping its existing behavioral prose. Do not duplicate the flag table into
  SKILL.md — that is the drift this unit exists to prevent.

**Patterns to follow:**
- `docs/solutions/conventions/skill-md-schema-lockstep-test-2026-07-03.md` — same shape of guard:
  a test pins documentation against the real surface.
- `docs/solutions/conventions/dzcto-engine-flag-three-site-wiring-2026-07-10.md` — the reason a flag
  list can silently drift from reality in this repo.

**Test scenarios:**
- Happy path: every flag string in the settings-page table appears in the `dzcto init` surface in
  `scripts/dzcto.py`.
- Error path: the test fails when the table names a flag that does not exist (verify by asserting the
  check is real — e.g. the matcher rejects a deliberately bogus flag name).
- Edge case: flags intentionally omitted from the settings page are enumerated in the test, so the
  subset relationship is explicit rather than accidental.

**Verification:**
- Renaming or removing a `dzcto init` flag without updating the settings table fails the suite.

---

## System-Wide Impact

- **Interaction graph:** `render_index` is called by both the `init` and `artifact` paths in
  `scripts/dzcto_artifact.py`'s `main()`. Adding a second page write inside it means every artifact
  refresh now writes two pages and two manifest entries.
- **Error propagation:** the settings-page write must not be able to break report rendering. It runs
  inside `render_index`, so a failure there fails the whole render — acceptable only because the write
  is deterministic and input-driven. If any part of it can raise on malformed config, U1's fallback
  handling is what prevents it.
- **State lifecycle risks:** the manifest gains a new artifact entry. Existing workspaces regenerate it
  on next render; no migration needed. `prune_manifest_report_artifacts` is confirmed not to touch
  root-level entries.
- **API surface parity:** none — no CLI flag, no config key, no JSON schema change. The `dzcto init`
  and `dzcto artifact` contracts are unchanged, which is why the three-site wrapper wiring is not in
  play.
- **Integration coverage:** the hermeticity seam (U1) is the scenario unit tests alone would miss —
  without it, tests pass on the author's machine and behave differently on a machine with a different
  `~/.dzcto/config.json`, or in CI where the file is absent.
- **Unchanged invariants:** the `.kpis` tile set and ordering, the `sec-reports` section, the single-line
  STDOUT path contract from `main()`, and the report-data sanitization path (`sanitize_report_value`)
  are all explicitly untouched.

---

## Alternative Approaches Considered

- **Link a repo doc (`docs/dzcto-settings.md`) instead of generating a page.** Cheapest option and no
  new render site. Rejected: AC#2 requires the documentation be viewable in the browser *from the
  index*, and the artifact tree is shared without a repo checkout — the link would be dead for the
  reader the feature exists to serve.
- **Ship a static `settings.html` copied into the tree at init time.** Avoids a second render function.
  Rejected: a static file cannot show the reader their *current* values, which is half of AC#1's value,
  and it re-introduces the drift problem the in-code flag table solves.
- **Refactor `build_parser()` out of `main()` in `scripts/dzcto.py` so the parity test can introspect
  argparse directly.** Cleaner test. Rejected as scope creep: `main()` is long and its parser
  construction is entangled with dispatch; a source-text parity check catches the same regression at a
  fraction of the blast radius. Revisit if a future change needs the parser independently.
- **Put the config values in the `.kpis` tile row for prominence.** Rejected on two counts: the issue's
  constraint is that a CEO-facing share must stay uncluttered by operator settings, and both existing
  KPI test helpers slice the page by tile label, so inserting tiles breaks them for no user gain.

---

## Risks & Dependencies

| Risk | Mitigation |
|------|------------|
| New index output trips `assertNotIn` proxy assertions in unrelated-looking tests | Placement inside `sec-settings` keeps output out of the 400-char KPI window; U2 carries the exact forbidden strings and a regression scenario. Tighten a proxy rather than relax it. |
| Reading the global config makes `render_index` tests machine-dependent | U1 injects the global config and tests patch `dzcto_common.GLOBAL_CONFIG_FILE`; a dedicated scenario proves the seam works. |
| Absolute repo paths leak usernames into a shared artifact | Basenames + count policy applied in the helper, with an explicit R5 test asserting no path separators in the view. |
| The settings page's flag list drifts from the real CLI | U4's parity test fails the suite on drift; SKILL.md points at the page rather than duplicating it. |
| Config panel clutters a CEO-facing share | Panel lives in a collapsible section, adds no KPI tile; collapsing `sec-settings` by default is available if the section grows heavy. |
| A second `write_html_page` site diverges from the index's provenance/manifest conventions | U3 mirrors the existing pair explicitly and asserts the manifest entry in a test. |

---

## Documentation / Operational Notes

- `skills/dzcto-init/SKILL.md` gains a pointer to the generated settings page (U4).
- No README change is required — the init flag surface is not currently documented there, and this
  plan does not create that obligation.
- Existing artifact trees pick up `settings.html` on their next `dzcto init` or `dzcto artifact` run;
  no backfill or migration step.

---

## Sources & References

- Origin: backlog issue DAYZEROCTO-14 (no upstream requirements document).
- Related code: `scripts/dzcto_artifact.py` (`render_index`, `write_html_page`, `page_shell`),
  `scripts/dzcto_common.py` (`read_global_config`, `TOOL_VERSION`, `LOCAL_PATH_KEYS`),
  `scripts/dzcto.py` (`init` subparser).
- Related learnings: `docs/solutions/conventions/absence-proxy-assertions-break-on-additive-rendering-2026-07-23.md`,
  `docs/solutions/conventions/dzcto-engine-flag-three-site-wiring-2026-07-10.md`,
  `docs/solutions/architecture-patterns/helper-computes-agent-narrates-2026-07-03.md`.

---

## Decisions

### Tone card renders the effective tone, not the raw configured value — 2026-07-23

`profile_config_view` returns `"Not set"` for an unconfigured `ceoReportTone`, and U2's first pass
rendered that in the Defaults panel. Rejected: `render_index` falls back to a built-in default tone
(`"direct, concise, business-facing, calm about risk, explicit about asks"`) that the copyable prompt
cards actually use, so the panel would have advertised a voice the reports do not have. The card now
renders the same effective `tone` variable the prompts do, pinned by
`test_displayed_tone_matches_the_tone_the_prompt_card_uses`. The view's raw value is still the right
thing for the settings page, where "Not set" is the honest answer to "what have you configured?".

### Pre-existing `render_index` tests were made hermetic — 2026-07-23

Adding the `defaultProfile` read means `render_index` now transitively calls `read_global_config()`,
so `TestRenderIndexWeeklyStreak` and `TestRenderIndexWeeklyDefaultTile` silently began depending on
the developer's real `~/.dzcto/config.json`. Both now patch `artifact.read_global_config` in `setUp`.
Rejected: leaving them alone because they happen to pass today — they pass only because no existing
assertion touches a global-config-derived value, which is luck, not design. Confirmed live during the
smoke test, which rendered `Global defaultProfile: arwen` from the real machine config.

### Flag parity is checked against source text, not an argparse object — 2026-07-23

`scripts/dzcto.py` builds its parser inline in `main()`, so there is no importable parser to
introspect. Rejected: refactoring a `build_parser()` out of `main()` — real scope creep for a test
convenience, and explicitly a non-goal in Scope Boundaries. The test slices the `init` subparser
region and regex-matches `init.add_argument("--flag"`, which catches a renamed, removed, or invented
flag; `test_the_parity_check_actually_rejects_an_unknown_flag` guards the guard.

### Absolute repo paths already on the index were left alone — 2026-07-23

The smoke test found `index.html` still emits absolute repo paths twice, via the pre-existing
copyable prompt cards (`exact_prompt` passes `repos` verbatim) and the "Serve Index" command card.
This predates DAYZEROCTO-14, and its acceptance criteria explicitly allow it ("config paths are
fine"). The new panel and settings page are deliberately stricter (basenames only). Flagged rather
than silently fixed, per the stay-in-scope working principle. If the shareable-artifact guardrail
should tighten here, that is its own issue.

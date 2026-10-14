# DAYZEROCTO-21 — State facts in CEO report headlines

## Scope and outcome

Implement the selected issue's Observable contract and all ten acceptance criteria. Both report skills direct authors to state counts and what shipped or changed. `validate_ceo_report` adds at most one advisory mood-label warning, and the artifact CLI still returns success and writes HTML. Preserve the JSON schema shape, existing reports, streak eligibility, explicit zero metrics, empty-section behavior, bad-news instructions, and honest quiet-report instructions. Do not check other prose fields or extend the settled mood-word list.

Use the selected light lane: this changes advisory wording and detection, with no authentication, payment, security, persistence, migration, or infrastructure change. The supervisor owns test execution, independent review, publication, merge, and closeout. Planning is complete when this artifact establishes the sequence; later execution evidence remains required.

## Source evidence and guidance

The checkout HEAD was read as `f991fc9861029539156a756921e5e0d30268241d`, matching the supplied revision for repository `chuckblake-day-zero-cto`. Supervisor research receipt `initial-repository` is consulted/current at that revision; its `AGENTS.md` provenance has SHA-256 `426b422258118bc019306c30cf9a97056a1424c7b30d37eba4a981afec0ee616`. Its manifest contents establish version 0.9.5. Direct local source reads below supplement that receipt; they are source evidence, not supervisor verification receipts.

Current anchors: `scripts/dzcto_artifact.py:1552-1596` implements warn-only validation; `:4010-4011` prints warnings and continues to the ordinary write path; `:1611-1624` excludes quiet evidence from the streak. `tests/test_dzcto_artifact.py:70-126`, `:1324-1350`, `:1510-1567`, and `:1662-1672` supply validator, schema-lockstep, skill, CLI, and quiet-streak test seams. `tests/test_dzcto_profiles.py:399-412`, `:438-445`, and `:447-508` cover init/artifact smoke, parsed manifest/version consistency, package creation, and execution of extracted helpers. `scripts/dzcto_common.py:19` pins `TOOL_VERSION` at 0.9.5. `.cb/config.yml` is the active runner configuration: checks are `lint` and `suite`, CI provider is `none`, and no UI/custom gate is configured. Do not substitute the legacy `.claude/cb.yml` CI setting from the initial receipt.

No planning-learning index was supplied. The following full entries were read directly from permitted `docs/solutions/` paths; no index summary or unavailable corpus is represented as consulted. Their old line numbers and historical test counts are stale; the current anchors above establish applicability.

| Full entry consulted | Effect on this plan; current-source check |
| --- | --- |
| `docs/solutions/architecture-patterns/helper-computes-agent-narrates-2026-07-03.md` | Put the finite, checkable word rule in the warn-only validator and the broader factual-writing rule in both skills. Current validator and CLI preserve this split; the lesson's trajectory narration does not override the settled factual-headline requirement. |
| `docs/solutions/conventions/skill-md-schema-lockstep-test-2026-07-03.md` | Change the identical headline line in both schema blocks together; retain the heading extractor and byte-equality test at `tests/test_dzcto_artifact.py:1324-1337`. No templating or new dependencies. |
| `docs/solutions/best-practices/characterize-what-already-holds-before-building-it-2026-08-01.md` | Retain existing quiet-streak exclusion and prove it with its current regression tests, rather than change streak code. CLI warning transport already exists and needs integration coverage, not new dispatch. |
| `docs/solutions/conventions/absence-proxy-assertions-break-on-additive-rendering-2026-07-23.md` | `tests/test_dzcto_artifact.py:1531-1534` forbids `quiet week` across the entire ad hoc skill, conflicting with the newly mandated schema example. Restrict that assertion to workflow instructions, preserving its window-neutral intent, and separately assert the exact schema guidance. |
| `docs/solutions/conventions/rendering-a-home-dir-config-value-breaks-test-hermeticity-2026-07-23.md` | Use `hermetic_cli` (`tests/test_dzcto_artifact.py:51-67`) and `ProfileFixture.env` (`tests/test_dzcto_profiles.py:71-79`) for CLI/package tests: temporary HOME, isolated cwd/Git discovery, no browser opening or operator-config writes. No new ambient-state reader is needed. |

The supplied `docs/pitfalls/shaping-pitfalls.md` rule applies to packaged behavior: execute the extracted helper and assert stderr, success, and generated HTML; do not inspect bundled application source to claim correctness. `PRODUCT_STRATEGY.md:20-26` and `CONCEPTS.md:22-23` support preserving honest reporting and evidence-based streak exclusion.

Local SHA-256 provenance at the pinned checkout:

| Path | SHA-256 |
| --- | --- |
| `.cb/config.yml` | `4bcb867bb3f32ced124b81ca0eb648f52ef03e420e280cbc7f662508847d689a` |
| `scripts/dzcto_artifact.py` | `4dc91ccd180f2e8fce1a4ea8f367222ddd0ad0358b0e0c2f9aabe2488ba6a35d` |
| `tests/test_dzcto_artifact.py` | `9ca4af967d309c1bff397fdac4a5d600908abb8ddee9e2d18dc4550399303e37` |
| `tests/test_dzcto_profiles.py` | `a7a24ae5a0654256c63cad758ad7afe1f369debec0373c6070a408bed69a1c48` |
| `skills/dzcto-ceo-report/SKILL.md` | `caab23c2cb5e4e9be819bff5222402db7161dbb59bb5a8d99676ab2cfbfd98f9` |
| `skills/dzcto-ceo-report-weekly/SKILL.md` | `11f5025ee45e4d743f4a7e55a4cdb4659677662f4d33eaa10cb26a196f484d04` |
| `docs/ceo-report-template.md` | `783a933094a6cc1fcd400dbbb55c934f8f367505d0e7bbdf5e402e5ff071a68e` |
| `docs/solutions/architecture-patterns/helper-computes-agent-narrates-2026-07-03.md` | `3a02942e66fb007da202527d582f3e7e1789cf5a5a0d9486aeab743eaa069d96` |
| `docs/solutions/conventions/skill-md-schema-lockstep-test-2026-07-03.md` | `53d780cc091a19fbf62317800ac191027a0fbe561c72f8a7facf4916ec2b8e79` |
| `docs/solutions/best-practices/characterize-what-already-holds-before-building-it-2026-08-01.md` | `4aff1e0ee48ce206f599a1ec141d024e5484aac914874c9d1e3a448d69056f1a` |
| `docs/solutions/conventions/absence-proxy-assertions-break-on-additive-rendering-2026-07-23.md` | `990fa95a95a5c3d8f7974d56f3afe69d919cc3ce03d2c7e5422871065e7f555d` |
| `docs/solutions/conventions/rendering-a-home-dir-config-value-breaks-test-hermeticity-2026-07-23.md` | `894a80d08ae764caac7563069fbc43cae57d9f34dd74b1ec5a3549499bf06b87` |

## Acceptance test interfaces

- Python: `dzcto_artifact.validate_ceo_report(data: dict[str, Any]) -> list[str]`. Input uses the existing v1 report shape. It returns ordinary warning strings without mutating report data. Mood warnings use exactly `headline characterizes the window ("<matched phrase>"); state counts and what shipped instead`.
- CLI: `bin/dzcto artifact --artifacts-dir <temporary workspace> --kind ceo-updates --title <title> --data-file <report.json>`, optionally `--evidence-file <snapshot.json>`. Expect exit 0, the generated HTML path on stdout, and `dzcto: ceo-report schema warning: headline characterizes the window` on stderr for a matching headline. Read that HTML and its sibling JSON; omit `--open`.
- Packaging: `bin/dzcto package-claude-desktop --output <temporary bundle.zip>`; extract and run `<bundle>/day-zero-cto/scripts/dzcto.py artifact` with the same report flags using the existing isolated package fixture. Assert observable warning/render behavior.
- Existing streak seams: `counts_toward_weekly_streak(data) -> tuple[bool, str | None]` and `weekly_report_dates(reports_dir: Path) -> list[date]`. Quiet facts come from the existing window-matched evidence snapshot (`window`, nonempty `repos`, `totals` with repos/commits/merges, and boolean `quiet`), not an authored eligibility field.

## Design decisions

Use a module-level immutable mood-word collection beside the existing CEO report constants: `quiet`, `slow`, `light`, `busy`, `heavy`, `heaviest`, `high-output`, `stalled`, `focused`, `smaller`, `big`, `strong`, `productive`. Accept only string headlines; missing, empty, or non-string values never create a mood warning. Match case-insensitively, preserve original text, and leave all existing validation behavior in place.

Use standard-library token spans so the check counts whole words rather than substrings. A suitable tokenizer is `\b\w+(?:-\w+)*\b`: keep `high-output` as one word, treat punctuation/whitespace as separators, and use original character offsets. Scan mood tokens in textual order; a subsequent whole token `week`, `window`, or `period` at distance 1, 2, or 3 matches (zero through two intervening words). Select the first qualifying phrase and stop. Slice the original headline from the mood token's start through the target token's end, preserving case, spacing, and intervening punctuation. Add only one mood warning even when several phrases qualify. No mood-after-window inference, adjective expansion, synonym classifier, or headline rewrite.

Replace only the existing empty-report warning text with `report has no structured content; if the window was quiet, state the zero counts in headline`. Its existing section-emptiness condition remains unchanged.

Both step-6 instructions must say ``state the zero counts plainly in `headline`, for example `No commits, PRs, or releases landed between <start> and <end>.` ``. Both schema lines must be exactly ``- `headline`: one sentence of facts — counts and what shipped or changed; never a characterization of the window such as 'a quiet week' or 'a heavy week'.`` Keep every other rule listed in the issue's Current behaviour word for word, including zero metrics, empty sections, never-pad, bad-news, and the distinct honest quiet-report standards.

## File map and implementation units

Every path below was compared with the current checkout and exists in this repository. All are existing-file edits or knowledge assessment targets; no new implementation, test, or knowledge file is proposed. This plan is the only file this planning role may edit.

| Unit | Paths | Concrete deliverable |
| --- | --- | --- |
| U1 | `scripts/dzcto_artifact.py`; `tests/test_dzcto_artifact.py` | Mood constants and bounded detection in `validate_ceo_report`; exact empty-warning replacement; validator cases and boundary fixtures. No write-path or streak changes. |
| U2 | `skills/dzcto-ceo-report/SKILL.md`; `skills/dzcto-ceo-report-weekly/SKILL.md`; `tests/test_dzcto_artifact.py` | Exact quiet-count and headline guidance, preserved rules, lockstep schema blocks, and precise skill assertions; repair the whole-skill negative assertion as described above. |
| U3 | `tests/test_dzcto_artifact.py`; `tests/test_dzcto_profiles.py` | CLI warning-plus-success/HTML test and extracted-package behavioral test using existing fixtures. Retain init/artifact smoke, package generation, and factual-headline quiet-streak coverage. |
| U4 | `docs/ceo-report-template.md`; `.codex-plugin/plugin.json`; `.claude-plugin/plugin.json`; `.claude-plugin/marketplace.json`; `scripts/dzcto_common.py`; `AGENTS.md` (assessment) | Align canonical headline/quiet-window/conformance prose; bump all five version fields to 0.9.6, including both marketplace fields and `TOOL_VERSION`; complete required knowledge assessment. |

Implement U1, then U2, then U3, then U4; the supervisor may allocate test authoring separately. Each unit requires the supervisor's grant for its exact paths before editing. U3 depends on U1/U2 interfaces, and U4 must finish before final verification and first normal publication. Later unit prerequisites are completed code and tests on the run tree, not evidence that this planning stage already executed them.

The canonical document currently repeats the old advice at `docs/ceo-report-template.md:47` and `:84-87`. Its own introductory consistency rule requires the narrow U4 prose update; this does not change schema fields or types. Update its conformance tiers to name the advisory word rule without promising detection of mood words after the period noun. Plugin version synchronization follows AGENTS.md's release rule and the existing version-lockstep test. Install behavior is unchanged, so no README/install-handoff edit is needed.

## Required verification and inputs

The supervisor runs every configured check on the final relevant tree. `lint` is `python3 -m compileall -q scripts tests`; it byte-compiles changed scripts/tests, supplying the required Python syntax validation. `suite` is `python3 -m unittest discover -s tests`; all functional proofs below belong in that configured suite. No additional supervisor command, temporary offense edit, retained failing run, external report folder, or live plugin refresh is a proof requirement.

| Issue acceptance criterion, in order | Required suite proof |
| --- | --- |
| 1: `A quiet week: no commits landed.` | Exact mood warning contains `headline characterizes the window ("quiet week")`. |
| 2: `A heavy hardening week: four gates shipped.` | Exact matched phrase `heavy hardening week`. |
| 3: `This two-week window was mostly quiet` | No mood warning; keep the operator's settled positional rule. |
| 4: `15 PRs merged: weekly featured and popular pipelines automated.` | No mood warning; other validator behavior stays intact. |
| 5: `HEAVIEST SHIPPING WEEK YET` | Exactly one mood warning, preserving `HEAVIEST SHIPPING WEEK`. |
| 6: artifact warning never blocks rendering | Actual wrapper invocation with a mood headline: exit 0, required stderr prefix, existing output HTML containing the headline, and unchanged headline in sibling JSON. Repeat the behavioral assertion using an extracted packaged helper. |
| 7: report with no structured content | Exact new empty-report warning; retain carried-forward-risk and nonempty-report negative cases. |
| 8: both skills have exact replacement instructions | Assert both exact instruction/schema strings and absence of ``state that plainly in `headline` ``; retain byte-identical schema test. Scope the existing ad hoc `quiet week` absence assertion to workflow prose. |
| 9: both skills preserve honesty rules | Assert the unchanged complete clauses for zero metrics (`prs_merged: 0`), empty sections, never-padding, bad news, and each skill's honest quiet-report standard. Keep existing bad-news and evidence tests. |
| 10: quiet reports stay excluded from streak | Existing predicate/date-pool regressions plus the evidence-file render regression using a factual zero-count headline; stamped `{quiet: true, commits: 0, merges: 0}` remains excluded. Do not infer quietness from headline text. |

Additional bounded cases: all thirteen words against each target noun; `Mostly quiet week`; mood distances 1/2/3 versus distance 4; hyphenated `high-output`; whole-word negative controls such as `quietly week` and `quiet weekend`; missing/empty/null headline; exact source slice across mixed case, spacing and punctuation; multiple matching phrases still produce one warning. Fixtures construct the offending input and assert detection in every suite run. Filter mood warnings by their stable prefix so unrelated schema warnings do not corrupt counts.

AGENTS.md's other required checks are carried by `suite`: existing parsed manifest/version tests validate JSON; the temporary `test_init_then_artifact_smoke` exercises init plus artifact; package tests generate the archive and U3 executes its helper. No configured check is waived because guidance files are Markdown. No remote CI or manual/UI gate is configured here; final review still requires supervisor-produced current-tree check receipts.

## Required knowledge, risks, and prerequisites

Required knowledge target is `AGENTS.md`. The later docs action must inspect the final diff and return a structured knowledge assessment before final verification/publication. Its current rules already cover advisory helpers, skill brevity, lockstep packaging and releases; an explicit `no_change` decision is appropriate if no new repository-wide rule emerges. Existing full learning entries already cover this change's reusable patterns; avoid duplicating them under `docs/learnings/`. Any genuinely new knowledge output needs a specific supervisor write grant. No manual target or planning index was supplied.

Risks are word-distance off-by-one errors, matching substrings, losing original phrase case, duplicate mood warnings, violating the warn-only contract, weakening the existing ad hoc workflow test, forgetting a version field, or accidentally changing quiet-streak eligibility. The boundary, exact-string, wrapper/package, lockstep/version, and evidence-based streak cases above address these risks. The broader editorial rule intentionally remains skill guidance for phrases outside the settled word rule.

No external prerequisite prevents this plan. Live operator vault reports, provider caches, and network services were not supplied or consulted and are unnecessary to design or verify this bounded change. No carried review findings or nonblocking review notes were supplied. Later tests, release, merge, and closeout remain supervisor obligations; this artifact claims none of their receipts.

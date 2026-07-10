---
title: Match a new command's config-resolution model to its consumers
date: 2026-07-09
category: architecture-patterns
module: dzcto-cli
problem_type: architecture_pattern
component: tooling
severity: high
applies_when:
  - Adding a CLI subcommand that reuses existing config/repo-resolution helpers
  - The codebase has more than one config-resolution model reading the same keys
  - A new command must read the same configured resources its downstream consumers already use
  - Reusing a date-window or range primitive whose bound semantics you have not checked
related_components:
  - development_workflow
  - documentation
tags:
  - config-resolution
  - profile-vs-wiki
  - cli-subcommand
  - helper-reuse
  - silent-failure
  - git-evidence
---

# Match a new command's config-resolution model to its consumers

## Context

DAYZEROCTO-7 added a read-only `dzcto evidence` subcommand to the Day Zero CTO CLI (`scripts/dzcto.py`). For an explicit start/end date window it walks every configured code repository and collects the commits, merge commits, and PR-subject issue refs that fall inside that window, emitting JSON. Both CEO report skills (`skills/dzcto-ceo-report/SKILL.md`, `skills/dzcto-ceo-report-weekly/SKILL.md`) were rewired so their evidence-gathering step now *leads* with this command and treats its JSON as the primary grounding source before falling back to conversation notes or prior reports.

The feature is small (+181 lines in `dzcto.py`, 8 real-git-fixture tests, 119 tests green) but it sits on top of two pre-existing, easy-to-confuse subsystems: the CLI's config-resolution helpers and its date-window helper. The reusable lesson is almost entirely about *which* existing helper to reuse, and how a reused primitive's semantics differ from the adjacent one it resembles.

Key identifiers: handler `run_evidence` (`dzcto.py:1320`); config/repo resolution `evidence_folder_and_repos` (`:194`); git query builder `evidence_log_args` (`:221`); data assembler `build_evidence_data` (`:262`); subparser registered at `:2306` with `help=argparse.SUPPRESS`.

## Guidance

**Before reusing config helpers, identify which config-resolution *model* your consumers already use — the two models look identical and the wrong choice fails silently.** This codebase has two distinct `.dzcto/config.json` locations, both keyed by `codeRepos`:

- **Project-wiki model.** `project_code_repos(project, extra_repos)` (`dzcto.py:148`) resolves `wiki_root_for_project(project)` → `<project>/knowledge/wiki`, then reads `<project>/knowledge/wiki/.dzcto/config.json`. Used by `snapshot` and `codebase-accountability`.
- **Artifact-folder / profile model.** `evidence_folder_and_repos` (`dzcto.py:194`) resolves the folder from `--artifacts-dir`, else `--profile` via `default_artifacts_dir_for_profile`, else `default_artifacts_dir_from_global`, then reads `<artifacts-dir>/.dzcto/config.json` via `project_repos(wiki_root)`. It also unions in `profile.get("codeRepos")` from the global profile and any `--repo` flags.

Both CEO report skills are profile-based and store config in the artifact folder, so `evidence` was deliberately built on the second model, mirroring `dzcto artifact`. Had it reused `project_code_repos` instead, `config.get("codeRepos", [])` would have read the wrong (typically absent) file, returned `[]`, and produced valid-but-empty evidence with **no error**. The rule: trace what your *consumer* already reads, not what looks like the nearest helper.

**Reuse the window primitive, but know its bound semantics.** `evidence` reuses `snapshot_window(args)`, which returns a validated `(start, end)` tuple — defaulting `end` to today, deriving `start` from `--days`, and hard-failing when `start > end`. The older `build_codebase_accountability_data` (`:348`) is driven by `accountability_since`, which is `--since`-only and open-ended: a lower bound but no upper bound, so it cannot honor an explicit report *end* date. `evidence_log_args` closes that gap by emitting **both** `--since=<start> 00:00:00` and `--until=<end> 23:59:59`, bounding the window on both ends.

**Document the git author-vs-commit-date subtlety instead of assuming they're equal.** `git log --since/--until` filters on *commit* date, but the format string `%ad` prints *author* date (`--pretty=format:%H%x09%h%x09%ad%x09%an%x09%s`). For rebased or cherry-picked commits these differ. The code calls this out inline (`dzcto.py:276`) rather than silently conflating them.

**Derive "PR subjects" from git alone when you have no GitHub API.** Merges are collected by re-running the log with `--merges`, and each merge subject is parsed by `MERGE_PR_PATTERN` (`\bMerge pull request (?P<pr>#\d+) from (?P<branch>\S+)`) to lift a `pr` number and `source_branch`. Issue refs come from `ISSUE_REF_PATTERN` (matches `ABC-123`, `#123`, `GH-123`) applied to commit subjects. No network, no token — purely local git.

**Shape internal, agent-facing commands as suppressed, read-only, JSON-only subparsers.** The `evidence` subparser is hidden from top-level `--help` via `argparse.SUPPRESS`, performs only non-mutating git reads, and emits machine-readable JSON. This keeps a skill-facing internal tool off the human-facing surface while remaining fully scriptable.

**Normalize resolved paths in test assertions on macOS.** The command resolves every repo path with `Path(value).expanduser().resolve()`. Because macOS `tempfile` dirs live under `/var/...` which symlink-resolves to `/private/var/...`, the skipped-repo test asserts against `str(missing.resolve())` (`tests/test_dzcto_evidence.py:179`) rather than the raw temp path — otherwise expected and actual diverge only on the `/private` prefix.

## Why This Matters

The dangerous failure here is not a crash — it is a *silent* one. If `evidence` had bound to the project-wiki config model, every CEO report would still generate, still render, and still read plausibly, while quietly omitting all Git evidence. A report whose entire premise is "grounded in real commit activity" would instead be grounded in nothing, and no test or exit code would flag it. Silent-empty is the worst failure mode for an evidence tool because the consumer (a report-writing agent) cannot distinguish "the week was genuinely quiet" from "I read the wrong file."

The bound-semantics point matters for report correctness. A CEO weekly report is defined by an exact week; an open-ended `--since` primitive would include everything after the start date, silently pulling next week's commits into this week's report. Reusing `snapshot_window` plus adding `--until` is what makes the window match the report's declared period.

The author-vs-commit-date and no-API-PR-parsing notes matter because they are subtleties that, undocumented, get "cleaned up" by a later well-meaning change (swapping `%ad` for `%cd`, or reaching for a GitHub API that isn't available in the target environment) that quietly shifts which commits land in which window.

## When to Apply

- **Adding a CLI command that reuses config/repo-resolution helpers.** Trace the exact file path each candidate helper reads and confirm it matches where your actual consumer stores config. When two helpers read the same key from same-named files at different roots, assume they are not interchangeable until proven otherwise.
- **Reusing a "window" or "range" primitive.** Check whether it is bounded on both ends or open-ended, and whether an adjacent command uses a different one. Match the primitive to the semantics the caller needs.
- **Formatting git output.** Whenever a date filter and a date field appear together, verify they refer to the same date kind (author vs commit) and document it if they don't.
- **Needing PR/issue provenance without API access.** Parse `git log --merges` subjects and commit subjects with explicit regexes; treat it as a first-class pattern for offline or token-less environments.
- **Building an internal, agent/skill-facing command.** Prefer a suppressed subparser, read-only operations, and JSON output.
- **Asserting on resolved paths in tests on macOS.** Resolve the expected path the same way the code does before comparing.

## Examples

**Choosing the right config model (the crux).** The evidence path reuses the artifact-folder model, unioning three repo sources:

```python
# dzcto.py:194  evidence_folder_and_repos
values = project_repos(wiki_root)                       # <artifacts-dir>/.dzcto/config.json codeRepos
values.extend(str(item) for item in (profile.get("codeRepos", []) or []) if str(item).strip())
values.extend(args.repo or [])                          # explicit --repo flags
```

Contrast the sibling command, which reads a *different* file at a *different* root:

```python
# dzcto.py:148  project_code_repos  (used by snapshot / codebase-accountability)
wiki_root = wiki_root_for_project(project)              # <project>/knowledge/wiki
config = read_json(sidecar_dir(wiki_root) / "config.json", {})   # .../knowledge/wiki/.dzcto/config.json
values = [... config.get("codeRepos", []) ...]
```

Same key (`codeRepos`), same filename (`.dzcto/config.json`), different location — pick by consumer. A profile test proves the intended path works with zero `--repo` flags: a global profile supplying both `artifactsDir` and `codeRepos` yields `totals.commits == 3`.

**Bounded window via reused primitive + added upper bound.**

```python
# dzcto.py:221  evidence_log_args
args.extend([
    f"--since={start.isoformat()} 00:00:00",
    f"--until={end.isoformat()} 23:59:59",   # the upper bound accountability lacks
    "--date=short",
    "--pretty=format:%H%x09%h%x09%ad%x09%an%x09%s",
])
```

Fixture commits span 2026-06-09…06-13; a `--start 2026-06-10 --end 2026-06-12` query returns exactly the three in-window subjects and excludes "Before the window" / "After the window."

**Offline PR-subject parsing.** A `--no-ff` merge with subject `Merge pull request #16 from feature/x` is parsed into `{"pr": "#16", "source_branch": "feature/x"}`, and `issue_refs` aggregates to `["#15", "#16", "DAYZEROCTO-7"]` purely from subject-line regexes — no GitHub call.

**Graceful degradation, not errors.** Unreadable repos are collected into `skipped_repos` and skipped; an all-empty result sets `quiet: true` and a `note` telling the consumer to fall back to conversation notes. The skills honor this: "If the collector reports no configured repositories, continue with the secondary evidence sources instead of treating that as an error." The hidden-command contract is locked by `test_evidence_command_is_hidden_from_top_level_help`.

## Related

- `../architecture-patterns/helper-computes-agent-narrates-2026-07-03.md` — `evidence` is a clean instance of the "helper computes, agent narrates" split: a deterministic, read-only, JSON-only helper with no LLM narration.
- `../design-patterns/today-anchored-cadence-period-streak-2026-07-09.md` — Closest prior art: its config-path testing trap ("a rarely-populated config path silently yields no rule while appearing to test the configured path") is the direct sibling of the wrong-config-model trap here; also shares today-anchored date-window handling and warn-never-fail read paths.
- `../design-patterns/cadence-scoped-prior-report-selection-2026-07-03.md` — Adjacent on date-window boundary handling (`window.end` resolution, deliberate `<` vs `<=` choice), parallel to bounded `snapshot_window + --until` vs open-ended `--since`.
- `../architecture-patterns/secret-scanning-shape-detection-and-split-fail-policy.md` — Downstream consumer boundary: git-evidence output is full of 40-char SHAs, which that scanner's `is_benign_secret_shape` must exclude if evidence ever reaches an egress artifact.
- `../best-practices/audit-for-dead-but-complete-machinery-2026-07-03.md` — Same reflex: "grep for existing machinery and check which caller is actually wired" is what drove identifying which of two config-resolution helpers the consumers use.

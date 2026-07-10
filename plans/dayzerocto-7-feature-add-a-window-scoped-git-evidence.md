---
title: "DAYZEROCTO-7: Add a window-scoped git evidence collector for report skills"
status: planned
priority: p2
created: 2026-07-09
effort: medium
tags: [ceo-report, evidence, git, cli, skill-workflow, dzcto-py]
linear_id: DAYZEROCTO-7
---

# DAYZEROCTO-7: Add a window-scoped git evidence collector for report skills

## Goal

Add a read-only `dzcto evidence` subcommand that mechanically collects commits, merges, and
PR-subject references from the configured `codeRepos` for an exact start/end date window, and rewire
both CEO report skills to consume it as their **primary** evidence source ahead of conversation
notes — so a grounded report needs zero manual git archaeology.

---

## Problem Frame

The two CEO report skills gather evidence in a manual-first order: user notes in conversation
first, prior report files second, freeform read-only git commands third
(`skills/dzcto-ceo-report-weekly/SKILL.md:17-24`, `skills/dzcto-ceo-report/SKILL.md:17-24`). Report
grounding therefore depends on what the CTO remembers to type, and every run reinvents its own git
archaeology from scratch.

Proven per-repo git machinery already exists in `scripts/dzcto.py` behind the suppressed
`codebase-accountability` command (`build_codebase_accountability_data:208-438`), but it is not
exposed as a clean, window-scoped, skill-consumable collector, and it has a window defect (below)
that makes it unsuitable as-is for an *explicit* report window.

This work exposes a small, focused collector that the skills call first, and reorders the skills'
evidence steps to lead with it. The business contract (what the collector must satisfy) lives in the
backlog issue `DAYZEROCTO-7`; this plan owns only the engineering response.

---

## Context & Research

### Relevant Code and Patterns

Everything below is in `scripts/dzcto.py` unless noted (verified against source this session):

- **Reusable read-only git helpers** — `repo_git(repo, args):132`, `repo_git_text(repo, args):139`
  (per-repo `git -C <repo>`, never mutating), `commit_files(repo, commit):190`,
  `parse_commit_rows(output):179` (tab-splits `%H\t%h\t%ad\t%an\t%s` into
  `full/short/date/author/subject`). **Do NOT reuse `run_git:77`** — it hardcodes `git -C REPO_ROOT`
  (the dzcto source repo, for self-update), not the project's evidence repos.
- **The commit-listing `git log`** is currently *inline* in `build_codebase_accountability_data:268-278`
  with format `%H%x09%h%x09%ad%x09%an%x09%s`, `--date=short`, `--max-count=200`, and — critically —
  **`--since` only** via `accountability_since:173`. There is **no upper bound**, so this machinery
  cannot honor an explicit report *end* date. This is the central defect to design around.
- **Window model to mirror** — `snapshot_window(args):486` already resolves `--start`/`--end`/`--days`
  into a validated `(start, end)` `datetime.date` tuple (defaults end=today, start=end-(days-1)) and
  raises `SystemExit` when `start > end`. `parse_snapshot_date(value, label):479` parses `YYYY-MM-DD`.
  Reuse `snapshot_window` verbatim.
- **Output conventions to mirror** — `run_snapshot:1140` is the closest model: write structured JSON
  to `generated_dir = sidecar_dir(wiki_root)/"generated"` (`mkdir(parents=True, exist_ok=True)`),
  default filename embeds the window (`snapshot-{start}-{end}.json`), `--output-json` overrides the
  path, `--json` also prints to stdout, `json.dumps(data, indent=2, sort_keys=True)+"\n"`, and the
  `--no-artifact` return path prints the data path and returns `0`.
- **codeRepos resolution (the crux)** — the two report skills operate on an **artifact folder /
  profile** model, *not* the `--project` wiki model that snapshot/accountability use:
  - The skills call `dzcto artifact --profile <name> --artifacts-dir <folder> …`. The artifact folder
    *is* the wiki_root and directly stores `.dzcto/config.json` (`dzcto.py:2149-2157`,
    README config example).
  - `codeRepos` is stored in `profiles.<name>.codeRepos` in `~/.dzcto/config.json` (README:70-88) and
    mirrored into the artifact folder's `.dzcto/config.json` by `dzcto init --repo`
    (`dzcto_artifact.py:388-393`).
  - `project_repos(wiki_root):1419` reads `codeRepos` from any wiki_root's sidecar
    (`sidecar_dir(wiki_root)/config.json`) — this is the right reuse for the artifact-folder model.
  - `default_artifacts_dir_for_profile(profile_name)` (`dzcto_artifact.py:472`),
    `default_artifacts_dir_from_global()` (`dzcto_artifact.py:397`), and `profile_from_global(name)`
    (`dzcto_artifact.py:459`) resolve a `--profile`/default into an artifacts dir and profile dict.
    `dzcto.py` already imports freely from `dzcto_artifact`, so these are importable.
  - **Do NOT reuse `project_code_repos(project):144`** — it assumes `project/knowledge/wiki` and would
    look in the wrong place for the CEO-report artifact-folder config.
- **Subcommand wiring** — subparsers at `:2032`; suppressed parsers use `help=argparse.SUPPRESS`
  and are stripped from help at `:2177`; dispatch is an inline `if args.command == …` chain near
  `:2181-2362`. `run_snapshot`/`run_codebase_accountability` establish the `run_<command>` naming.
- **Ref parsing** — `ISSUE_REF_PATTERN:120` (`[A-Z][A-Z0-9]+-\d+|#\d+|GH-\d+`) already matches both
  Linear-style IDs and GitHub `#NN` in commit subjects.

### Institutional Learnings

- No `docs/solutions/` entry covers git-evidence collection (checked). The sibling plan
  `plans/dayzerocto-3-…-quiet-week-report-path.md` establishes this repo's plan depth, its
  source-verification norm, and the honest-quiet-window and bad-news guardrails the report skills
  must keep honoring.

### External References

- None. Read-only local git only; no GitHub API in this repo; not a high-risk domain. External
  research gate did not fire.

---

## Key Technical Decisions

- **KTD1 — Config model: artifact-folder/profile, not `--project` wiki.** `run_evidence` resolves the
  evidence-repo set the *same way the CEO report skills already resolve their artifact folder*:
  `--artifacts-dir` (explicit) → else `--profile` → `default_artifacts_dir_for_profile` → else
  `default_artifacts_dir_from_global()`. codeRepos = union of `project_repos(<resolved folder>)`,
  the resolved profile's `codeRepos` (`profile_from_global`), and any `--repo` extras. This is what
  makes AC "zero manual notes when codeRepos are configured" hold end-to-end, because the skills
  already know their profile/folder. Mirror the `artifact` subparser's `--artifacts-dir`/`--profile`
  args (`dzcto.py:2150-2152`), not snapshot's positional `project`.

- **KTD2 — Explicit window with an upper bound.** Reuse `snapshot_window(args)` for the `(start, end)`
  tuple (gets `--start`/`--end`/`--days` + `start>end` validation for free). Build the `git log`
  bounds as an inclusive day window: `--since="<start> 00:00:00"` and `--until="<end> 23:59:59"`
  (plus `--date=short`). This is the fix for the `--since`-only defect. Note the git subtlety in a
  code comment: `--since`/`--until` filter on **commit** date while `%ad` displays **author** date;
  the collector filters on commit date (git default) and surfaces the short author date — acceptable
  and documented, not silently assumed.

- **KTD3 — "Merges / PR subjects" = merge-commit subjects + `#NN` refs, no API.** There is no GitHub
  API. Collect merges with `git log --merges` over the same window and parse
  `Merge pull request (#\d+) from (\S+)` out of the subject to get the PR number and source branch.
  Because squash-merge workflows put `(#NN)` in the *ordinary* commit subject (not a merge commit),
  also harvest `#NN` refs from **all** commit subjects via `ISSUE_REF_PATTERN`. Together these cover
  both merge-commit and squash-merge repos. Make `--merges` (not `--first-parent`) the choice and
  say why in a comment.

- **KTD4 — JSON-only, no HTML artifact.** The collector is consumed programmatically by the skills,
  so `dzcto evidence` writes structured JSON to `generated_dir/evidence-{start}-{end}.json`, honors
  `--output-json`, and prints to stdout under `--json` — mirroring `run_snapshot`'s `--no-artifact`
  path exactly. It does **not** shell to `dzcto_artifact.py`. Register the subparser
  **suppressed** (`help=argparse.SUPPRESS`), consistent with snapshot/accountability.

- **KTD5 — Graceful zero-repo path, never a hard failure.** If the folder resolves but no codeRepos
  are configured (and no `--repo` given), still write a valid evidence JSON with empty repo data and
  a `"note"`/`"quiet": true` marker and return `0`, so the skill can fall back to notes cleanly
  (mirrors the accountability "No code repositories configured" handling at `:395-400`). Only error
  (clear stderr message, non-zero) when no artifact folder can be resolved at all.

- **KTD6 — Evidence JSON shape carries ready-to-cite provenance.** Emit a shape the skills can drop
  straight into a report's `sources[]` and use for quiet-week detection (directional — final keys may
  shift in implementation):
  ```
  {
    "window": {"start": "YYYY-MM-DD", "end": "YYYY-MM-DD"},
    "repos": [{
      "repo": "<path/label>", "branch": "...", "head": "<short>",
      "commits": [{"short","date","author","subject","refs":["#12","ABC-3"]}],
      "merges":  [{"short","date","subject","pr":"#16","source_branch":"..."}],
      "counts":  {"commits": N, "merges": M, "authors": K}
    }],
    "totals": {"repos": R, "commits": N, "merges": M, "authors": K},
    "issue_refs": ["#12","ABC-3"],
    "sources": ["git log <repo> --since=<start> --until=<end> — N commits, M merges"],
    "quiet": <bool>,          // true when totals.commits == 0 across all repos
    "generated_at": "<iso>"
  }
  ```
  *(Directional guidance for review, not implementation specification.)*

---

## Files

- **Modify** `scripts/dzcto.py` — add `run_evidence` + evidence helpers (window bounds builder,
  artifact-folder/codeRepos resolution, commit+merge collection, PR/issue-ref parsing, evidence-data
  builder); register a suppressed `evidence` subparser (~`:2137`); add inline dispatch (~`:2325`).
- **Modify** `skills/dzcto-ceo-report-weekly/SKILL.md` — reorder step-4 evidence list to lead with
  the collector; add a `dzcto evidence` invocation block. Preserve the bad-news bullet substrings and
  the byte-identical `## Report JSON schema (v1)` block.
- **Modify** `skills/dzcto-ceo-report/SKILL.md` — same reorder + invocation block (lockstep with the
  weekly skill; "requested range" wording).
- **Modify** `README.md` — document the `dzcto evidence` command in the command/config surface
  (~`:145-160`).
- **Create** `tests/test_dzcto_evidence.py` — end-to-end tests driving `dzcto evidence` over a real
  temp git repo fixture (window boundaries, merge/PR parsing, codeRepos discovery, output/quiet).
- **Modify** `tests/test_dzcto_artifact.py` — add `TestSkillEvidencePrimary` locking AC #2 (both
  skills reference the collector as primary, ahead of conversation notes).

---

## Implementation Units

- U1. **Evidence collector core in `scripts/dzcto.py`**

**Goal:** Add the pure-ish building blocks: resolve the artifact folder + codeRepos the CEO-report
way, list window-scoped commits and merges per repo (read-only), parse PR/issue refs, and assemble
the evidence-data dict (KTD6).

**Requirements:** Backlog AC "collect commits/merges/PR subjects for an explicit start/end window,
read-only"; Constraint "code repos remain read-only".

**Dependencies:** None.

**Files:**
- Modify: `scripts/dzcto.py`

**Approach:**
- New helper to resolve the evidence folder from `--artifacts-dir`/`--profile`/default and gather
  codeRepos = `project_repos(folder)` ∪ profile `codeRepos` ∪ `--repo` extras, deduped/resolved
  (mirror the dedup in `project_code_repos:152-159`). Reuse `default_artifacts_dir_for_profile` /
  `default_artifacts_dir_from_global` / `profile_from_global` imported from `dzcto_artifact`.
  **These three names are not yet in the `from dzcto_artifact import (…)` block at `dzcto.py:21-47`
  — add them.** (They are module-level in `dzcto_artifact.py`; `default_artifacts_dir_from_global`
  internally falls back to `profile_from_global()`, so the `--profile`→default chain works.)
- New window-bounds helper: from `snapshot_window`'s `(start, end)` build `--since`/`--until`
  strings per KTD2. Reuse `repo_git_text` + `parse_commit_rows` for the commit list
  (format `%H%x09%h%x09%ad%x09%an%x09%s`, `--date=short`); a second `--merges` pass for merges.
- Parse `#NN`/issue refs from subjects via `ISSUE_REF_PATTERN`; parse
  `Merge pull request (#\d+) from (\S+)` for merge PR number + source branch (KTD3).
- Assemble the KTD6 dict, including per-repo branch/HEAD (via `repo_git_text(repo,["rev-parse",…])`)
  and the human-readable `sources[]` provenance strings.

**Patterns to follow:** `build_snapshot_data`/`build_codebase_accountability_data:208-438` for
per-repo iteration and provenance strings; `parse_commit_rows:179`; `project_repos:1419`.

**Test scenarios:** covered end-to-end in U4 (this unit is exercised through the CLI).
- Happy path: a repo with 3 commits + 1 merge in-window yields 3 commit rows, 1 merge row with the
  parsed `#NN`, and correct counts.
- Edge case: commits dated **before start** and **after end** are excluded (proves the `--until`
  bound — the defect this fixes).
- Edge case: window with zero in-window commits → empty repo data, `quiet: true`.
- Error path: a configured codeRepos path that is not a git repo is skipped without raising (mirror
  accountability's tolerant handling).

**Verification:** invoking the collector over a fixture repo returns the KTD6 shape with only
in-window commits and correctly parsed merge/issue refs.

- U2. **Wire the `evidence` subcommand (subparser + dispatch + output)**

**Goal:** Expose `run_evidence(args)` as a suppressed `dzcto evidence` subcommand with snapshot-style
output conventions.

**Requirements:** Backlog AC "a `dzcto evidence` (or equivalent) command …".

**Dependencies:** U1.

**Files:**
- Modify: `scripts/dzcto.py`

**Approach:**
- Register a suppressed parser near `:2137`: `--artifacts-dir`, `--profile`, `--repo` (append),
  `--start`, `--end`, `--days` (type int, default 7), `--output-json`, `--json`. No positional
  `project` (KTD1). `--repo` is a manual/test convenience (the skills rely on config discovery, not
  this flag — U4 proves the no-`--repo` path); it also gives U4 a clean handle to point the command
  at a fixture repo, and mirrors the `--repo` flag `codebase-accountability` already exposes.
- Add inline dispatch near `:2325`: `if args.command == "evidence": return run_evidence(args)`.
- `run_evidence`: resolve folder → `wiki_root`; `start, end = snapshot_window(args)`; build data via
  U1; write to `sidecar_dir(wiki_root)/"generated"/f"evidence-{start}-{end}.json"` unless
  `--output-json`; `--json` prints to stdout; otherwise print the data path. Return `0` on success;
  clear stderr + non-zero only when no folder resolves (KTD5). Follow `run_snapshot:1140-1161`.

**Patterns to follow:** `run_snapshot:1140`; snapshot subparser `:2127-2136`; help-suppression
filter `:2177`.

**Test scenarios:** (end-to-end in U4)
- Happy path: `dzcto evidence --artifacts-dir <tmp> --start … --end … --json` prints the JSON and
  writes `evidence-<start>-<end>.json` into the folder's `.dzcto/generated/`.
- Edge case: `--output-json <path>` writes to that path instead.
- Edge case: `--start` after `--end` exits non-zero (inherited from `snapshot_window`).
- Error path: no `--artifacts-dir`, no resolvable profile → clear stderr message, non-zero exit.

**Verification:** `dzcto evidence` appears in neither `dzcto --help` nor top-level help (suppressed),
runs read-only, and emits JSON to the generated dir.

- U3. **Rewire both report skills to lead with the collector**

**Goal:** Make the collector the primary evidence source in step 4 of both skills, ahead of
conversation notes, with an invocation block — satisfying AC #2 without breaking the three guard
tests.

**Requirements:** Backlog AC "Both CEO report skills reference the collector as the primary evidence
source, ahead of conversation notes"; Constraint "keep the two schema blocks byte-identical".

**Dependencies:** U2 (the invocation contract — args and output path).

**Files:**
- Modify: `skills/dzcto-ceo-report-weekly/SKILL.md`
- Modify: `skills/dzcto-ceo-report/SKILL.md`

**Approach:**
- Reorder each skill's step-4 list so the **first** bullet runs `dzcto evidence` for the window and
  names its JSON as the grounding source that report `sources[]` must trace to; keep "User notes"
  and "Existing report JSON/HTML" as **secondary** bullets after it.
- Add a `dzcto evidence` invocation block (with the `python3 scripts/dzcto.py evidence …` PATH
  fallback), mirroring the existing `dzcto artifact` block, passing the already-resolved
  `--profile`/`--artifacts-dir` from steps 1–2 plus `--start`/`--end` and `--json`.
- **Preserve verbatim** the bad-news bullet substrings `reverts or reverted commits`,
  `failing or red CI`, `slipped or descoped work` (guarded by `TestSkillBadNewsInstructions:762`).
- **Do not touch** steps 5–6 (they hold the quiet-window substrings guarded by
  `TestSkillQuietWindowInstructions:777`) or the `## Report JSON schema (v1)` block (guarded
  byte-identical by `TestSkillSchemaLockstep:745`). **The lockstep test slices the schema section by
  splitting on `"\n## "` (`test_dzcto_artifact.py:751`), so the new invocation block must not
  introduce another `## ` H2 heading inside/after the schema section — put it in step 4 above the
  schema header, as a `###`/fenced block.**

**Patterns to follow:** the existing `dzcto artifact` code-fence block in both SKILLs (`:27-45`);
current step-4 wording (`:17-24`).

**Test scenarios:** locked by U4's `TestSkillEvidencePrimary`; the three existing skill guard tests
must stay green.

**Verification:** `python -m unittest` skill tests pass; both skills lead step 4 with `dzcto
evidence`; the two schema blocks remain byte-identical.

- U4. **Tests: evidence command + AC-2 skill lock**

**Goal:** First test coverage for the per-repo git collector, and a lock on the primary-source
ordering.

**Requirements:** Backlog AC "a weekly report can be generated with zero manual notes when codeRepos
are configured, and its sources trace to the collected evidence" (proven via the collector output +
config-discovery test); AC #2 (ordering lock).

**Dependencies:** U1, U2, U3.

**Files:**
- Create: `tests/test_dzcto_evidence.py`
- Modify: `tests/test_dzcto_artifact.py`

**Approach:**
- `unittest`, subprocess-driven end-to-end (model on `test_dzcto_artifact.py`'s `run_cli` +
  `tempfile.TemporaryDirectory` setUp, ~`:806`), with the `sys.path.insert(scripts)` shim if any
  in-process import is needed.
- Build a **real temp git repo fixture**: `git init`, set `user.name`/`user.email`, create commits
  on controlled dates by setting `GIT_AUTHOR_DATE`/`GIT_COMMITTER_DATE` env (commit date is what
  `--since`/`--until` filter on — KTD2), including at least one commit before the window, one after,
  several inside, and one merge commit whose subject is `Merge pull request #16 from feature/x`.
- Create a temp artifact folder with `.dzcto/config.json` containing `codeRepos: [<fixture repo>]`
  to prove config-discovery with **no `--repo`** (the "zero manual notes" path).

**Test scenarios:**
- Happy path: evidence over the fixture returns only in-window commits; `totals.commits` matches.
- Edge case (the defect): the pre-window and post-window commits are **excluded** — asserts the
  upper bound works.
- Happy path: the merge commit is parsed into `merges[]` with `pr == "#16"` and the source branch;
  `#16` also appears in `issue_refs`.
- Happy path: codeRepos read from the artifact-folder `.dzcto/config.json` with no `--repo` flag.
- Edge case: empty window → `quiet: true`, exit `0`, valid JSON.
- Edge case: `--output-json` writes to the given path; `--json` prints parseable JSON to stdout.
- Error path: unresolvable folder (no `--artifacts-dir`/profile) → non-zero exit, message on stderr.
- `TestSkillEvidencePrimary` (in `test_dzcto_artifact.py`): for both skills, `dzcto evidence` appears
  in step 4 and its first occurrence precedes the first `User notes` occurrence (primary ordering).

**Verification:** `python -m unittest` (full suite) green, including the three pre-existing skill
guard tests.

- U5. **Document the `evidence` command in the README**

**Goal:** Give the collector a one-line home in the user-facing command/config surface.

**Requirements:** Constraint context ("existing guardrail in skills and README"); keeps README honest
about how codeRepos are consumed.

**Dependencies:** U2.

**Files:**
- Modify: `README.md`

**Approach:** Add a short entry near the config/command surface (~`:145-160`) describing
`dzcto evidence --profile <name> --start <date> --end <date>` as the read-only, window-scoped
collector that feeds the CEO report skills from `codeRepos`.

**Test scenarios:** `Test expectation: none — documentation-only, no behavioral change.`

**Verification:** README describes the command; no code paths changed.

---

## Risks & Dependencies

| Risk | Mitigation |
|------|------------|
| Reordering step 4 accidentally deletes a guarded substring, reddening `TestSkillBadNews`/`TestSkillQuietWindow`/`TestSkillSchemaLockstep`. | U3 calls out all three tests explicitly; keep the bad-news bullet verbatim, leave steps 5–6 and the schema block untouched; run `python -m unittest` before commit. |
| `--since`/`--until` commit-vs-author-date subtlety yields off-by-one at window edges. | KTD2 pins commit-date filtering with explicit `00:00:00`/`23:59:59` bounds; U4 asserts pre/post-window exclusion with dates set via `GIT_COMMITTER_DATE`. |
| codeRepos live in a different place than assumed (project wiki vs artifact folder). | KTD1 resolves via the artifact-folder/profile model the skills actually use (`project_repos`/`profile_from_global`), verified against source; U4 proves discovery from `.dzcto/config.json`. |
| Squash-merge repos produce no merge commits, so `--merges` finds nothing. | KTD3 also harvests `#NN` from all commit subjects, covering squash-merge workflows. |
| A configured codeRepos path is missing or not a git repo. | KTD5 tolerant handling: skip and continue; never crash the report. |

---

## Open Questions

### Resolved During Planning

- **Which config model does the evidence command use?** The artifact-folder/profile model the CEO
  report skills use (KTD1), not the `--project` wiki model — otherwise "zero manual notes" cannot
  hold for the skills.
- **How are "PR subjects" obtained without a GitHub API?** From `git log --merges` subjects plus
  `#NN` refs in all commit subjects (KTD3).
- **JSON-only or also HTML artifact?** JSON-only (KTD4).
- **Does the window need an upper bound?** Yes — the existing machinery is `--since`-only; add
  `--until` (KTD2).

### Deferred to Implementation

- Exact final JSON key names / whether merges are nested per-repo or also flattened at top level —
  settle when wiring the skills' consumption in U3 against the real U1 output. **Note:** the keys U4
  asserts (`window`, `totals.commits`, `repos[].merges[].pr`, `issue_refs`, `quiet`) are the stable
  contract; the deferral applies to *additional* keys/nesting, not these — don't rename them in a way
  that reddens U4.
- Whether to cap commits per repo (accountability uses `--max-count=200`/`[:80]`); pick a sane cap
  during U1 once real report windows are exercised.
- Exact README wording and placement — trivial, settle in U5.

---

## Verification Contract

- `python -m unittest` passes, including the new `tests/test_dzcto_evidence.py` and the three
  pre-existing skill guard tests.
- `dzcto evidence --artifacts-dir <folder-with-codeRepos> --start <s> --end <e> --json` emits valid
  JSON containing only in-window commits, parsed merges/PR refs, and a `sources[]` that traces to the
  git commands run — with **no `--repo`** flag needed when codeRepos are configured.
- The collector performs only read-only git operations (`log`, `show`, `rev-parse`); no mutating git
  command is ever issued.
- Both report skills lead step 4 with the collector; the two `## Report JSON schema (v1)` blocks are
  byte-identical.

---

## Definition of Done

- `dzcto evidence` exists, is suppressed from help, read-only, artifact-folder/profile-scoped, and
  honors an explicit start/end window with an upper bound.
- Both CEO report skills reference the collector as the primary evidence source ahead of conversation
  notes, with an invocation block, and all skill guard tests stay green.
- New evidence tests prove window boundaries, merge/PR parsing, config discovery, and the quiet/empty
  path.
- README documents the command.

## Decisions

### Keep explicit evidence windows uncapped — 2026-07-09

The collector returns every commit reachable in the requested bounded window. A fixed per-repo cap
was rejected because it could make an exact report window silently incomplete; callers control cost
by selecting the report dates, and invalid repositories remain isolated through tolerant skipping.

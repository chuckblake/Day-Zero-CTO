---
name: codebase-accountability
description: "Generate a Day Zero CTO codebase accountability report. Use for agent-fleet oversight, repo movement, management exceptions, provenance gaps, guardrail drift, accountability of codebase work, or understanding what many coding agents changed."
---

# Codebase Accountability

Create a management-by-exception view of repo movement so one CTO can oversee many agents without reading every diff.

## Workflow

1. Resolve the project folder. Durable outputs live under `<project>/knowledge/wiki/`.
2. Treat configured code repos as read-only evidence unless the user explicitly asks for code changes.
3. Prefer the deterministic helper:

```bash
dzcto codebase-accountability "<project folder>"
```

Use `--repo <path>` for extra repos, `--since "<git date>"` for a specific review window, or `--days N` for the first run lookback.

4. Review the generated report for management exceptions first, then provenance, guardrails, changed subsystems, actor activity, risk signals, decision signals, and open questions.
5. If deeper judgment is needed, inspect only the flagged commits, files, or subsystems. Keep evidence concise and cite concrete repos, commits, files, or report links.
6. Promote durable exposure into `core/RISKS.md`, durable choices into `core/DECISIONS.md`, and durable invariants into `core/ENGINEERING_GUARDRAILS.md`.
7. Do not edit generated HTML. Refresh with `dzcto refresh "<project folder>"`.

## Report Contract

The helper writes structured JSON and renders the HTML artifact under `reports/codebase-accountability/`.

Expected JSON fields:

- `executive_read`
- `review_window`
- `metrics`
- `management_exceptions`
- `changed_subsystems`
- `provenance`
- `guardrail_checks`
- `agent_activity`
- `change_units`
- `risks`
- `decisions`
- `questions`
- `sources`

Use `risks` only for exposures that may need owner, mitigation, source, and dated next review. Use `decisions` only for formal choices needed or choices already made.

## Standards

- This is an oversight brief, not a full code review.
- Surface exceptions and uncertainty instead of summarizing every routine commit.
- Prefer queryable provenance: repo, branch/head, commit, issue ref, actor, source file, or generated report link.
- Flag missing issue refs, dirty worktrees, high-attention files, dependency changes, and source changes without visible test/eval evidence.
- If a risk review creates a formal choice, log that choice in `core/DECISIONS.md`.

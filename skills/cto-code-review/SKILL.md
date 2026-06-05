---
name: cto-code-review
description: "Review code from a startup CTO perspective and optionally create a durable HTML code review artifact in the project knowledge wiki. Use when the user asks for CTO code review, PR review, architecture review of a diff, startup-risk review of code, merge readiness, or help deciding whether code is safe enough to ship given product goals, customer trust, delivery speed, reliability, security, and maintainability."
---

# CTO Code Review

Review code for the risks and leverage a startup CTO should care about.

## Workflow

1. Resolve the code repo or diff under review.
2. Resolve the project folder separately when company context or durable output matters. If unknown and the user wants durable output, ask for it and recommend `~/Documents/<Company>/`. Durable outputs live under `<project>/knowledge/wiki/`.
3. Treat the code repo as read-only during review unless the user explicitly asks you to fix code.
4. Inspect the diff, touched files, tests, and surrounding code before forming findings.
5. Load company context when it changes the review: `core/STRATEGY.md`, `core/RISKS.md`, launch plans, incidents, customer commitments, or architecture notes from `<project>/knowledge/wiki/`.
6. Prioritize issues that affect correctness, customer trust, security, reliability, operability, product speed, or future team load.
7. Separate blocking findings from follow-up improvements.
8. Give a merge recommendation with residual risk.
9. When the user wants a durable review artifact, write it as HTML under `<project>/knowledge/wiki/reports/code-reviews/` and regenerate `<project>/knowledge/wiki/index.html`.

## Findings Format

Lead with findings, ordered by severity. Include tight file and line references when possible.

- `Blocking`: must fix before merge.
- `FYI`: worth considering, not a merge blocker.
- `Question`: a real uncertainty that changes the review outcome.

After findings, include:

- `Merge recommendation`
- `Tests / verification`
- `Startup risk note` when the code affects launch, sales, support, compliance, or runway.

## Durable Artifact

Write structured JSON report data, then use the helper from this plugin. Prefer the wrapper when it is on `PATH`; otherwise run the Python script from the plugin repo:

Required JSON fields: `merge_recommendation`, `blocking`, `fyi`, `questions`, `tests_verification`, `startup_risk_note`, and `sources`.

```bash
dzcto-artifact --project "<project folder>" --kind code-reviews --title "CTO Code Review" --data-file "<json report data file>"

# Fallback when dzcto-artifact is not on PATH:
python3 scripts/dzcto_artifact.py --project "<project folder>" --kind code-reviews --title "CTO Code Review" --data-file "<json report data file>"
```

The helper owns the HTML template; the agent owns the judgment and structured content. Keep the chat response focused on findings and the merge recommendation.

## Standards

- Do not spend review budget on style nits unless they hide real risk.
- Do not approve large changes just because they compile.
- Mention missing tests when the changed behavior is risky.
- When the right answer depends on product urgency, say what you would ship now and what you would follow up on.
- Do not write code review artifacts into the code repo by default.

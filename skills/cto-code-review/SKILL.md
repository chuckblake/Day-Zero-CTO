---
name: cto-code-review
description: "Review code from a startup CTO perspective. Use when the user asks for CTO code review, PR review, architecture review of a diff, startup-risk review of code, merge readiness, or help deciding whether code is safe enough to ship given product goals, customer trust, delivery speed, reliability, security, and maintainability."
---

# CTO Code Review

Review code for the risks and leverage a startup CTO should care about.

## Workflow

1. Inspect the diff, touched files, tests, and surrounding code before forming findings.
2. Load company context when it changes the review: `STRATEGY.md`, `RISKS.md`, launch plans, incidents, customer commitments, or architecture notes.
3. Prioritize issues that affect correctness, customer trust, security, reliability, operability, product speed, or future team load.
4. Separate blocking findings from follow-up improvements.
5. Give a merge recommendation with residual risk.

## Findings Format

Lead with findings, ordered by severity. Include tight file and line references when possible.

- `Blocking`: must fix before merge.
- `FYI`: worth considering, not a merge blocker.
- `Question`: a real uncertainty that changes the review outcome.

After findings, include:

- `Merge recommendation`
- `Tests / verification`
- `Startup risk note` when the code affects launch, sales, support, compliance, or runway.

## Standards

- Do not spend review budget on style nits unless they hide real risk.
- Do not approve large changes just because they compile.
- Mention missing tests when the changed behavior is risky.
- When the right answer depends on product urgency, say what you would ship now and what you would follow up on.

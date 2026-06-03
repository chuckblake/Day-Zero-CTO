---
name: review-engineering-risk
description: "Review engineering risk for an early-stage startup. Use when the user asks for a risk review, tech debt assessment, launch readiness check, fundraise readiness check, architecture risk review, security/reliability concern, scaling concern, or a CTO view of what could threaten product, customers, delivery, trust, or runway."
---

# Review Engineering Risk

Find the engineering risks that could realistically hurt the startup's current goals.

## Workflow

1. Load company context: `STRATEGY.md`, `RISKS.md`, `DECISIONS.md`, planning docs, incident notes, and relevant code/docs.
2. Define the review horizon: launch, next week, next month, fundraise, enterprise sale, major migration, or ongoing operations.
3. Inspect evidence before asserting risk. Use code, docs, incidents, tests, CI, architecture notes, and user-provided context.
4. Group risks by business impact rather than by technical subsystem.
5. Recommend mitigations sized to the company's stage and runway.
6. Update `RISKS.md` only when the user asks or when the workflow is explicitly maintaining the risk register.

## Risk Categories

- Product delivery risk
- Reliability and operability risk
- Security, privacy, and compliance risk
- Data and integration risk
- Maintainability and architecture risk
- Team, process, and ownership risk
- Vendor, cost, and runway risk

## Output Shape

Lead with the highest risks:

- `Risk`
- `Evidence`
- `Business impact`
- `Likelihood`
- `Severity`
- `Mitigation`
- `Owner / horizon` when known

## Standards

- Findings must be evidence-backed or labeled as assumptions.
- Do not confuse code ugliness with startup risk.
- Prefer mitigations that reduce risk without freezing product learning.
- Call out when the cheapest mitigation is a manual process, monitoring habit, or sharper owner assignment.

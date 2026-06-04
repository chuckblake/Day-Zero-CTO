---
name: review-engineering-risk
description: "Review engineering risk for an early-stage startup and create a durable HTML risk review in the Day Zero CTO home folder. Use when the user asks for a risk review, tech debt assessment, launch readiness check, fundraise readiness check, architecture risk review, security/reliability concern, scaling concern, or a CTO view of what could threaten product, customers, delivery, trust, or runway."
---

# Review Engineering Risk

Find the engineering risks that could realistically hurt the startup's current goals.

## Workflow

1. Resolve the Day Zero CTO home folder. If unknown, ask for it and recommend `~/Documents/<Company>/Day Zero CTO/`.
2. Resolve an optional code repo pointer separately. Treat the code repo as read-only evidence unless the user explicitly asks for code changes.
3. Load company context from the Day Zero CTO home: `core/STRATEGY.md`, `core/RISKS.md`, `core/DECISIONS.md`, planning docs, incident notes, and relevant reports.
4. Define the review horizon: launch, next week, next month, fundraise, enterprise sale, major migration, or ongoing operations.
5. Inspect evidence before asserting risk. Use code, docs, incidents, tests, CI, architecture notes, and user-provided context.
6. Group risks by business impact rather than by technical subsystem.
7. Recommend mitigations sized to the company's stage and runway.
8. Write the canonical review as an HTML artifact under `<Day Zero CTO home>/reports/engineering-risk/` and regenerate `<Day Zero CTO home>/index.html`.
9. Update `core/RISKS.md` only when the user asks or when the workflow is explicitly maintaining the risk register.
10. Summarize the top risks in chat and link to the generated artifact.

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

## Durable Artifact

Use the helper script from this plugin:

```bash
scripts/dzcto-artifact.rb --home "<Day Zero CTO home>" --kind engineering-risk --title "Engineering Risk Review" --body-file "<html body file>"
```

The report body should be HTML. Keep the chat response brief; the HTML file is the durable record.

## Standards

- Findings must be evidence-backed or labeled as assumptions.
- Do not confuse code ugliness with startup risk.
- Prefer mitigations that reduce risk without freezing product learning.
- Call out when the cheapest mitigation is a manual process, monitoring habit, or sharper owner assignment.
- Do not write risk reviews or Day Zero CTO context files into the code repo by default.

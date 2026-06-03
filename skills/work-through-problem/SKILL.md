---
name: work-through-problem
description: "Help a startup CTO reason through an ambiguous technical, product, team, process, or business-facing engineering problem. Use when the user asks to think through a decision, untangle a tradeoff, choose between approaches, diagnose a messy situation, prepare for a hard conversation, or decide what a CTO should do next."
---

# Work Through Problem

Help the CTO make a clear, grounded decision without turning uncertainty into fake certainty.

## Workflow

1. Name the problem in one sentence and identify the decision that actually has to be made.
2. Load relevant local context when available: `STRATEGY.md`, `TEAM.md`, `OPERATING_CADENCE.md`, `DECISIONS.md`, `RISKS.md`, recent plans, issue notes, or code/docs tied to the problem.
3. Separate facts, assumptions, constraints, and unknowns.
4. Identify the affected parties: CEO/founders, customers, engineers, sales/support, investors, or future maintainers.
5. Generate 2-3 viable options, including one boring low-risk option when it exists.
6. Compare options on startup-relevant axes: speed, reversibility, customer impact, team load, technical risk, trust, cash/time cost, and learning value.
7. Recommend a next move and name what would change the recommendation.

## Output Shape

For lightweight asks, answer directly. For serious decisions, use:

- `Decision`: the choice in plain language.
- `Context`: the facts that matter.
- `Options`: the realistic paths.
- `Tradeoffs`: why each option wins or loses.
- `Recommendation`: what to do now.
- `Watchpoints`: what to monitor.
- `Follow-ups`: artifacts to update, such as `DECISIONS.md` or `RISKS.md`.

## Standards

- Be candid about weak evidence.
- Avoid generic executive advice. Tie claims to the startup's actual stage, constraints, code, customers, or team.
- Prefer reversible decisions when uncertainty is high and the cost of learning is low.
- Record important decisions in `DECISIONS.md` when the user wants a durable artifact.

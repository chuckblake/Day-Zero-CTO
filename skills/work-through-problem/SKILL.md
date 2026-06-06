---
name: work-through-problem
description: "Help a startup CTO reason through an ambiguous technical, product, team, process, or business-facing engineering problem and optionally create a durable HTML decision artifact in the project knowledge wiki. Use when the user asks to think through a decision, untangle a tradeoff, choose between approaches, diagnose a messy situation, prepare for a hard conversation, write a decision memo, or decide what a CTO should do next."
---

# Work Through Problem

Help the CTO make a clear, grounded decision without turning uncertainty into fake certainty.

## Workflow

1. Name the problem in one sentence and identify the decision that actually has to be made.
2. Resolve the project folder. If it is unknown and the user wants durable output, ask for it and recommend `~/Documents/<Company>/`. Durable outputs live under `<project>/knowledge/wiki/`.
3. Resolve one or more optional code repo pointers separately. Treat code repos as read-only evidence unless the user explicitly asks for code changes.
4. Load relevant Day Zero CTO context when available: `core/STRATEGY.md`, `core/TEAM.md`, `core/OPERATING_CADENCE.md`, `core/DECISIONS.md`, `core/RISKS.md`, recent reports, issue notes, or code/docs tied to the problem from `<project>/knowledge/wiki/`.
5. Separate facts, assumptions, constraints, and unknowns.
6. Identify the affected parties: CEO/founders, customers, engineers, sales/support, investors, or future maintainers.
7. Generate 2-3 viable options, including one boring low-risk option when it exists.
8. Compare options on startup-relevant axes: speed, reversibility, customer impact, team load, technical risk, trust, cash/time cost, and learning value.
9. Recommend a next move and name what would change the recommendation.

## Output Shape

For lightweight asks, answer directly. For serious decisions, use:

- `Decision`: the choice in plain language.
- `Context`: the facts that matter.
- `Options`: the realistic paths.
- `Tradeoffs`: why each option wins or loses.
- `Recommendation`: what to do now.
- `Watchpoints`: what to monitor.
- `Follow-ups`: artifacts to update, such as `core/DECISIONS.md` or `core/RISKS.md`.

## Durable Artifacts

When the user wants the decision captured, write structured JSON data and render the canonical HTML artifact under `<project>/knowledge/wiki/reports/decisions/`, then regenerate `<project>/knowledge/wiki/index.html`.

Use a structured JSON payload when the user wants the decision captured. Required JSON fields: `decision`, `context`, `options`, `tradeoffs`, `recommendation`, `watchpoints`, `follow_ups`, and `sources`.

Use the helper from this plugin. Prefer the `dzcto` wrapper when it is on `PATH`; otherwise run the Python command from the plugin repo:

```bash
dzcto artifact --project "<project folder>" --kind decisions --title "<decision title>" --data-file "<json report data file>"

# Fallback when dzcto is not on PATH:
python3 scripts/dzcto.py artifact --project "<project folder>" --kind decisions --title "<decision title>" --data-file "<json report data file>"
```

The chat response should summarize the recommendation and link to the generated artifact.

## Standards

- Be candid about weak evidence.
- Avoid generic executive advice. Tie claims to the startup's actual stage, constraints, code, customers, or team.
- Prefer reversible decisions when uncertainty is high and the cost of learning is low.
- Record important decisions in the project knowledge wiki, not code repos, when the user wants a durable artifact.

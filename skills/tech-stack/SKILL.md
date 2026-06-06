---
name: tech-stack
description: "Review a startup codebase or technical workspace and create a durable HTML Tech Stack report in the project knowledge wiki. Use when the user asks what stack is being used, wants codebase onboarding, needs a technology inventory, wants architecture/system context, or asks for a stack review across frameworks, languages, infrastructure, data stores, integrations, tooling, and operational risks."
---

# Tech Stack

Create a grounded technology inventory and system map from the codebase without assuming a framework or language.

## Workflow

1. Resolve the project folder. If unknown, ask for it and recommend `~/Documents/<Company>/`. Durable outputs live under `<project>/knowledge/wiki/`.
2. Resolve the codebase location separately. A Tech Stack report normally needs a codebase; if none is available, clearly label the report as docs-only.
3. Treat the codebase as read-only unless the user explicitly asks for code changes.
4. Load relevant context from `<project>/knowledge/wiki/`: `core/STRATEGY.md`, recent reports, `core/RISKS.md`, `core/DECISIONS.md`, and any existing Tech Stack report.
5. Inspect stack evidence across the repo, choosing files by ecosystem instead of assuming one:
   - Package manifests and lockfiles.
   - Framework configuration and app entrypoints.
   - Database schemas, migrations, ORM config, seeds, and data access layers.
   - CI, deployment, container, infrastructure, hosting, and process manager config.
   - Runtime service docs, environment examples, queue/cache/search/storage integrations, and API clients.
   - Test, lint, formatting, observability, error reporting, analytics, and security tooling.
6. Separate facts from inferences. Use `Assumption:` where evidence is partial.
7. Write structured JSON report data and render the canonical HTML artifact under `<project>/knowledge/wiki/reports/tech-stack/`.
8. Summarize the stack shape, biggest onboarding clues, and any stack risks in chat.

## Output Shape

- `Stack components`: layer, technology, evidence, and notes.
- `Architecture shape`: how the major pieces fit together.
- `Data and storage`: databases, caches, queues, object stores, search, analytics, and ownership.
- `Integrations`: third-party APIs, auth, payments, messaging, AI, email, monitoring, and customer-facing dependencies.
- `Infrastructure and operations`: hosting, deploy path, CI, background jobs, observability, secrets, and environments.
- `Development tooling`: local setup, tests, linting, formatting, code generation, and developer workflow.
- `Risks and watchpoints`: stack risks that matter to delivery, reliability, trust, or onboarding.
- `Onboarding notes`: what a new technical leader or agent should read first.

## Durable Artifact

Required JSON fields: `executive_read`, `stack_components`, `architecture_shape`, `data_storage`, `integrations`, `infrastructure_operations`, `development_tooling`, `risks_watchpoints`, `onboarding_notes`, and `sources`.

```bash
dzcto artifact --project "<project folder>" --kind tech-stack --title "Tech Stack" --data-file "<json report data file>"

# Fallback when dzcto is not on PATH:
python3 scripts/dzcto.py artifact --project "<project folder>" --kind tech-stack --title "Tech Stack" --data-file "<json report data file>"
```

The helper owns the HTML template; the agent owns the evidence and structured content.

## Standards

- Do not assume Rails, Node, Python, mobile, or any specific stack.
- Cite concrete files or directories as evidence.
- Do not expose secrets; mention only the existence or pattern of secret management.
- Prioritize technologies that affect onboarding, product delivery, reliability, security, cost, or vendor risk.
- Treat generated report content as a map for future agents, not a comprehensive API reference.

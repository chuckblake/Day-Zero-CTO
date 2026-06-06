---
name: tech-stack
description: "Review one or more startup codebases or technical workspaces and create a durable HTML Tech Stack report in the project knowledge wiki. Use when the user asks what stack is being used, wants codebase onboarding, needs a technology inventory, wants architecture/system context, or asks for a stack review across frameworks, languages, infrastructure, data stores, integrations, tooling, and operational risks."
---

# Tech Stack

Create a grounded technology inventory and system map from one or more codebases without assuming a framework or language.

## Workflow

1. Resolve the project folder. If unknown, ask for it and recommend `~/Documents/<Company>/`. Durable outputs live under `<project>/knowledge/wiki/`.
2. Resolve one or more codebase locations separately. A Tech Stack report normally needs codebase evidence; if none is available, clearly label the report as docs-only.
3. Treat codebases as read-only unless the user explicitly asks for code changes.
4. Load relevant context from `<project>/knowledge/wiki/`: `core/STRATEGY.md`, recent reports, `core/RISKS.md`, `core/DECISIONS.md`, and any existing Tech Stack report.
5. Inspect stack evidence across each repo, choosing files by ecosystem instead of assuming one:
   - Package manifests and lockfiles.
   - Framework configuration and app entrypoints.
   - Database schemas, migrations, ORM config, seeds, and data access layers.
   - CI, deployment, container, infrastructure, hosting, and process manager config.
   - Runtime service docs, environment examples, queue/cache/search/storage integrations, and API clients.
   - Test, lint, formatting, observability, error reporting, analytics, and security tooling.
6. Separate facts from inferences. Use `Assumption:` where evidence is partial. When multiple repos are involved, make the source repo clear in evidence and sources.
7. Write structured JSON report data and render the canonical HTML artifact under `<project>/knowledge/wiki/reports/tech-stack/`.
8. Summarize the stack shape, biggest onboarding clues, and any stack risks in chat.

## Output Shape

- `Stack components`: layer, technology, evidence, and notes.
- `Architecture shape`: how the major pieces fit together.
- `Data and storage`: databases, caches, queues, object stores, search, analytics, and ownership.
- `Integrations`: third-party APIs, auth, payments, messaging, AI, email, monitoring, and customer-facing dependencies.
- `Infrastructure and operations`: hosting, deploy path, CI, background jobs, observability, secrets, and environments.
- `Development tooling`: local setup, tests, linting, formatting, code generation, and developer workflow.
- `Risks and watchpoints`: candidate stack risk signals that matter to delivery, reliability, trust, or onboarding. These are not the operating risk register until promoted into `core/RISKS.md`; after refresh they appear on `core/risks.html#risk-signals` with a link back to the Tech Stack report so they can be promoted, merged, or dismissed from the canonical risk page.
- `Onboarding notes`: what a new technical leader or agent should read first.

## Durable Artifact

Required JSON fields: `executive_read`, `stack_components`, `architecture_shape`, `data_storage`, `integrations`, `infrastructure_operations`, `development_tooling`, `risks_watchpoints`, `onboarding_notes`, and `sources`. For each `risks_watchpoints` row, include concrete `evidence`, `severity`, `mitigation`, and `source` when known; use a source such as `Tech Stack report <date>` or the specific file/report that produced the signal.

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
- Treat Tech Stack risks as candidate signals. If the user wants them tracked operationally, promote them into `<project>/knowledge/wiki/core/RISKS.md` with owner, mitigation, source, and calendar next review date.
- Treat generated report content as a map for future agents, not a comprehensive API reference.

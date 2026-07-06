# Product Strategy

## Goals

- Goal: a first-time CTO — an IC newly carrying the technical-leadership responsibilities of a small startup — achieves instant comprehension of a sprint of AI-accelerated work plus a CEO-ready shareable report, so the business can build open-source credibility that generates consulting leads.
- Target user: a first-time CTO — an individual contributor newly responsible for the technical side of a small startup, not an engineering manager at scale.
- User outcome: in minutes, understand all work done in the past ~7 days and hold a document ready to share and discuss with a CEO — replacing hours of manual assembly.
- Business outcome: DZCTO is free and open source; it demonstrates the maintainer's expertise on real and client projects, helps the community, and generates inbound consulting leads.

## North Star

- North Star: the three-week streak measures a user generating the weekly CEO report three consecutive weeks.
- North Star exclusion: test or debug runs whose artifact is discarded do not count.
- North Star exclusion: automated runs whose report nobody opens do not count.
- North Star exclusion: runs over a window with no actual work do not count.
- North Star exclusion: the maintainer's own usage on his own projects does not count.

## Principles

- Principle: Ritual over highlights means choose generating an honest "quiet week" report over skipping or padding the report to look impressive.
- Principle: One altitude per report means choose business/customer framing over technical completeness; technical depth belongs in separate future reports, never blended into this one.

## Guardrails

- Guardrail: never state work, progress, or metrics that cannot be traced to actual repo evidence (commits, PRs, issues).
- Guardrail: never omit or soften bad news — reverted work, red CI, slipped scope, a quiet week — to make a report read better.
- Guardrail: never include secrets, credentials, or client-identifying data in the shareable artifact.
- Guardrail: never let report generation depend on manual data assembly or hours of setup.

## Anti-Goals

- Anti-Goal: this is not a project tracker — no issue management, no Jira or Linear replacement.
- Anti-Goal: this is not a rebuild of anything already covered by a widely used existing tool; DZCTO only builds where the human is most needed in an agentic development project.
- Anti-Goal: this is not a tool for engineering organizations at scale — small startups, not 200-person companies.

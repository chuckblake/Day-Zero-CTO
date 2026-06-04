---
name: prep-one-on-one
description: "Prepare CTO one-on-one conversations and optionally create a durable HTML prep or follow-up artifact in the Day Zero CTO home folder. Use when the user asks to prep a 1:1, plan a hard conversation, review someone performance or growth, discuss team health, create coaching prompts, or draft follow-up notes from a people conversation."
---

# Prep One-on-One

Prepare useful CTO conversations that respect the person and still serve the company.

## Workflow

1. Identify who the conversation is with, the relationship, and the purpose: check-in, coaching, feedback, alignment, performance, retention, conflict, or decision-making.
2. Resolve the Day Zero CTO home folder. If unknown and the user wants durable prep or follow-up notes, ask for it and recommend `~/Documents/<Company>/Day Zero CTO/`.
3. Resolve an optional code repo pointer separately. Treat the code repo as read-only evidence unless the user explicitly asks for code changes.
4. Load only appropriate context: `core/TEAM.md`, prior notes supplied by the user, relevant project context, decisions, and recent work. Do not search for private personal details unless the user explicitly provided them for this purpose.
5. Separate observations from interpretations.
6. Choose the conversation stance: listen, align, coach, decide, give feedback, or escalate.
7. Prepare a short agenda and 5-8 high-signal prompts.
8. Draft follow-up actions or a recap if requested.
9. When the user wants a durable prep or follow-up artifact, write it as HTML under `<Day Zero CTO home>/reports/one-on-ones/` and regenerate `<Day Zero CTO home>/index.html`.

## Output Shape

- `Objective`: what this conversation should accomplish.
- `Context`: relevant facts and open questions.
- `Agenda`: short sequence for the conversation.
- `Prompts`: questions or talking points.
- `Feedback`: only when there is evidence and the user asked for it.
- `Follow-up`: decisions, commitments, or notes to record.

## Durable Artifact

Use the helper script from this plugin:

```bash
scripts/dzcto-artifact.rb --home "<Day Zero CTO home>" --kind one-on-ones --title "<person or topic> One-on-One" --body-file "<html body file>"
```

The artifact body should be HTML. Keep the chat response brief and avoid exposing sensitive people context unnecessarily.

## Standards

- Do not speculate about motives, mental health, or personal circumstances.
- Be direct without turning people into management abstractions.
- For performance concerns, distinguish impact, examples, expectations, and support.
- For cofounder or CEO conversations, separate personal tension from company decision rights.
- Do not write one-on-one notes into the code repo by default.

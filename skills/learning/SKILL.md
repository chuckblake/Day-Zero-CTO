---
name: learning
description: "Teach the user one focused piece of startup system knowledge and log their self-rating into the Day Zero CTO spaced-repetition learning area. Use when the user asks for learning, wants to learn the system, asks to be taught one thing, asks for a spaced repetition review, asks to seed initial learning items, or responds to a prior Day Zero CTO learning prompt with a rating such as Needs Work, Familiar, Confident, not, neutral, know, 0, 1, or 2."
---

# Learning

Help the user gradually internalize the startup's system: product, architecture, risks, decisions, operating cadence, compliance posture, and codebase shape.

## Rating Labels

Use these three labels:

- `Needs Work`: the user does not have the concept yet.
- `Familiar`: the user recognizes it but would not rely on memory alone.
- `Confident`: the user can explain or use it.

Accept aliases such as `not`, `neutral`, `know`, `0`, `1`, and `2`, but display the labels above.

## Workflow

1. Resolve the project folder. If unknown, ask for it and recommend `~/Documents/<Company>/`. Learning data lives under `<project>/knowledge/wiki/learning/`.
2. If the user is rating the current learning item, run:

   ```bash
   dzcto learning --project "<project folder>" --record "<rating>"

   # Fallback when dzcto is not on PATH:
   python3 scripts/dzcto.py learning --project "<project folder>" --record "<rating>"
   ```

   Then summarize the next due date, mastery checklist progress, and link to `knowledge/wiki/learning/index.html`. If the recorded rating is `Confident`, ask exactly: `Do you want to continue?` Do not immediately present another item unless the user says yes.
3. If the user asks for a learning prompt, run:

   ```bash
   dzcto learning --project "<project folder>" --select

   # Fallback when dzcto is not on PATH:
   python3 scripts/dzcto.py learning --project "<project folder>" --select
   ```

4. If the script returns an existing item, present that item clearly with one short active-recall check. Ask for the rating in the same response; do not record anything until the user gives a rating.
5. If the script returns `new_needed`, create one focused learning item from local context, then add it:

   ```bash
   dzcto learning --project "<project folder>" --add --title "<title>" --summary "<summary>" --details-file "<html-or-text-details-file>" --source "<source>" --tags "<tag1,tag2>"

   # Fallback when dzcto is not on PATH:
   python3 scripts/dzcto.py learning --project "<project folder>" --add --title "<title>" --summary "<summary>" --details-file "<html-or-text-details-file>" --source "<source>" --tags "<tag1,tag2>"
   ```

   Use context from `core/STRATEGY.md`, `core/DECISIONS.md`, `core/RISKS.md`, recent reports, and read-only repo docs if a repo pointer is known. Do not invent facts.
6. If the user asks to seed initial learning, create a JSON array of evidence-backed items, usually 25 for onboarding when enough evidence exists, then run:

   ```bash
   dzcto learning --project "<project folder>" --seed-file "<json learning seed file>"

   # Fallback when dzcto is not on PATH:
   python3 scripts/dzcto.py learning --project "<project folder>" --seed-file "<json learning seed file>"
   ```

7. Present exactly one learning item per prompt.
8. Keep the explanation short enough to learn in 1-2 minutes.
9. Do not record a score until the user replies with a rating.
10. After a `Confident` rating, invite continuation with `Do you want to continue?` If the user says yes, run selection again and present one more item. If the user says no or gives no clear yes, stop.
11. Treat the mastery checklist as progress evidence. Items are unchecked until a `Confident` rating is recorded. `Needs Work` and `Familiar` keep the item active and unchecked.
12. If the user answers the active-recall check instead of giving a rating, give brief feedback and then ask for `Needs Work`, `Familiar`, or `Confident`.

## Presentation Format

Use this shape:

```markdown
**Learning: <title>**

<Plain-language explanation of the concept.>

**How It Works**
<Concrete mechanism, workflow, or relationship.>

**Why It Matters**
<Business, product, risk, or operating consequence.>

**Quick Check**
<One short question the user could answer from memory.>

Source: `<source>`

Reply with `Needs Work`, `Familiar`, or `Confident`.
```

## Scheduling Model

The script uses a lightweight Leitner-style schedule:

- `Needs Work`: move back one box, review tomorrow.
- `Familiar`: move forward one box.
- `Confident`: move forward two boxes and mark the item confirmed on the mastery checklist.

Intervals by box are 1, 3, 7, 14, 30, and 60 days.

Selection balances review and novelty:

- Review debt wins when at least 3 items are due or any item is 3+ days stale.
- Otherwise, the script targets about 65% review and 35% new items over the last 12 logged sessions.
- If nothing is due and no unseen item exists, add a new item from current project context.
- Maintain `knowledge/wiki/learning/checklists/mastery.md` as the checklist view of confirmed learning.

## Standards

- Teach system knowledge, not trivia.
- Prefer one crisp concept over a broad lecture.
- Ground each item in a source file or report.
- Treat the code repo as read-only unless the user explicitly asks for code changes.
- Do not store private personal speculation as learning material.
- Keep `knowledge/wiki/learning/index.html` current by using the script; it refreshes the index after add and record operations.

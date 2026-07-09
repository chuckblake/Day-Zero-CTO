---
title: "DAYZEROCTO-2: Instruct report skills to surface bad news explicitly"
status: planned
priority: p1
created: 2026-07-09
effort: small
tags: [skills, ceo-report, prompt-design, guardrail]
linear_id: DAYZEROCTO-2
---

# DAYZEROCTO-2: Instruct report skills to surface bad news explicitly

## Goal
Add an explicit bad-news evidence-and-writing instruction to both CEO-report skills, and name
where bad news lands in the template's section spine, so an honest report is what the
instructions produce rather than what the agent happens to choose.

## Prior Solutions
- `docs/solutions/conventions/skill-md-schema-lockstep-test-2026-07-03.md` — only the
  `## Report JSON schema (v1)` block is under the byte-identical lockstep test; it is extracted
  by heading and compared, so edits elsewhere in the two SKILL.md files are free.
- `docs/solutions/architecture-patterns/helper-computes-agent-narrates-2026-07-03.md` — anything
  checkable belongs in the renderer; prose judgment stays in the prompt. Bad-news *detection* is
  judgment over evidence, so it stays prompt-side (the template's "aspirational" conformance
  tier) rather than becoming renderer validation.

## Files
- Modify: `skills/dzcto-ceo-report-weekly/SKILL.md`
- Modify: `skills/dzcto-ceo-report/SKILL.md`
- Modify: `docs/ceo-report-template.md`
- Test: `tests/test_dzcto_artifact.py`

## Approach
The acceptance criterion has two halves — *gather* the bad news, and *report it plainly*. Put
each half where it belongs in the workflow rather than as one blob:

- **Gather** goes in step 4 ("Gather evidence for only the selected week / requested range") of
  each skill, as a fourth bullet: check the available evidence for reverted commits, failing or
  red CI, and slipped or descoped work.
- **Report plainly** goes in the writing step (step 6) or `## Standards` of each skill: when the
  window contains bad news, state it in `headline` / `progress.status` / `risks_blockers`
  without softening.

The two files' `## Workflow` and `## Standards` sections are already *not* identical (weekly says
"selected week," ad-hoc says "requested range"; the Standards lists differ entirely). Both files
get the instruction; neither is forced to match the other's wording.

Word the gather bullet as **"check the available evidence for…"**. Reverts are reachable today via
the read-only `codeRepos` git log; CI status is not collected by anything yet — a window-scoped
git evidence collector is DAYZEROCTO-7's job. An instruction that assumes a CI source exists would
over-promise.

## Plan
- [ ] Add the bad-news evidence bullet to step 4 of `skills/dzcto-ceo-report-weekly/SKILL.md`,
      scoped to the selected week and worded against *available* evidence.
- [ ] Add the equivalent bullet to step 4 of `skills/dzcto-ceo-report/SKILL.md`, scoped to the
      requested range.
- [ ] Add the "report it plainly, do not soften" directive to the writing step / `## Standards`
      of both skills.
- [ ] Confirm no edit lands inside the `## Report JSON schema (v1)` block in either file.
- [ ] Update `docs/ceo-report-template.md` to name where bad news lands in the section spine
      (`headline`, `progress.status`, `risks_blockers`) and record the instruction under the
      **Aspirational** conformance tier — it is prompted, not machine-checked.
- [ ] Add a presence-based test to `tests/test_dzcto_artifact.py`: assert each SKILL.md mentions
      reverts, CI, and slipped/descoped work. **Not** a byte-identity assertion — the surrounding
      prose legitimately differs between the two files.
- [ ] Run `python3 -m pytest tests/test_dzcto_artifact.py` (or `python3 -m unittest`) and confirm
      the existing schema-lockstep test still passes.

## Open Questions
- CI signal has no collector today. The gather instruction is deliberately worded against
  *available* evidence; DAYZEROCTO-7 (window-scoped git evidence collector) is the issue that
  makes red-CI evidence actually reachable. No blocker here — noting the seam.

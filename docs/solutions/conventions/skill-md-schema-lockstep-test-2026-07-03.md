---
title: Enforce byte-identical duplicated SKILL.md blocks with a lockstep unit test
date: 2026-07-03
category: conventions
module: skills
problem_type: convention
component: testing_framework
related_components: [documentation]
severity: medium
applies_when:
  - "The same contract text (schema, spec, instructions) must be duplicated across self-contained skill or doc directories"
  - "Installers or packagers require each directory to stand alone, ruling out includes or a single shared source"
  - "Reviewer memory is the only thing keeping duplicated blocks in sync"
tags: [skill-md, duplication, lockstep, unit-test, schema, plugin-packaging]
---

# Enforce byte-identical duplicated SKILL.md blocks with a lockstep unit test

## Context

`skills/dzcto-ceo-report/SKILL.md` and `skills/dzcto-ceo-report-weekly/SKILL.md` both carry the "Report JSON schema (v1)" block. Skill installers copy each skill directory as a self-contained unit, so the block cannot be factored into one shared file — it must be duplicated. Duplicated contract text drifts unless something mechanical stops it.

## Guidance

Duplicate deliberately, then enforce the duplication with a unit test that extracts each copy by its heading and asserts byte equality (`tests/test_dzcto_artifact.py:315-329`):

```python
class TestSkillSchemaLockstep(unittest.TestCase):
    HEADER = "## Report JSON schema (v1)"

    def schema_block(self, skill: str) -> str:
        text = (REPO / "skills" / skill / "SKILL.md").read_text(encoding="utf-8")
        self.assertIn(self.HEADER, text, f"{skill} lost its schema block")
        block = text.split(self.HEADER, 1)[1]
        return block.split("\n## ", 1)[0]

    def test_schema_blocks_are_byte_identical(self):
        self.assertEqual(
            self.schema_block("dzcto-ceo-report"),
            self.schema_block("dzcto-ceo-report-weekly"),
            "Report JSON schema (v1) blocks in the two SKILL.md files must stay byte-identical",
        )
```

Pair the test with an in-source guard comment at the top of the duplicated block (both SKILL.md files, lines 47-49): "Keep this section byte-identical in dzcto-ceo-report/SKILL.md and dzcto-ceo-report-weekly/SKILL.md; a unit test enforces the lockstep." The comment tells the editor what to do; the test catches them when they don't.

Two properties worth copying:

- The extractor also asserts the block *exists* (`assertIn`), so deleting the section fails loudly rather than comparing two empty strings.
- Byte equality (not normalized/semantic comparison) keeps the test trivial and the fix obvious: copy one block over the other.

## Why This Matters

- Divergent schema blocks would give the two skills different data contracts against the same renderer — a bug that surfaces as confusing agent output, not a crash.
- Lockstep-by-test is durable; lockstep-by-reviewer-memory decays with every contributor who doesn't know the rule.
- The alternative (single source + build-time templating) adds packaging machinery to a plugin whose value is being dependency-free.

## When to Apply

- Any time packaging constraints force duplicating normative text across directories
- Prompt blocks, schema prose, or config fragments repeated across agent skill files
- When a review comment says "remember to also update the copy in X" — that sentence is the test asking to be written

## Examples

Run: `python3 -m unittest discover -s tests` (the repo's standard validation; suite is 40 tests).

## Related

- docs/solutions/architecture-patterns/helper-computes-agent-narrates-2026-07-03.md — the schema contract this block documents
- AGENTS.md — repo rule that skill instructions stay agent-neutral, and warning that installers may scan all `SKILL.md` files

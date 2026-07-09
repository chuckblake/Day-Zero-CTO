---
title: "Secret scanning at an egress boundary: match shape, split the fail policy"
date: 2026-07-09
category: architecture-patterns
module: ceo-report
problem_type: architecture_pattern
component: tooling
related_components: [documentation, assistant]
severity: high
applies_when:
  - "Adding a secret/credential scan before writing or sharing an artifact"
  - "One detector is consumed by both an egress path (must block) and a resilience path (must keep working)"
  - "Reviewing a redaction or masking function before trusting it as a security control"
  - "A regex looks for a keyword near a value to find secrets"
tags: [secret-scanning, redaction, egress-boundary, security, detector-design, fail-policy, false-confidence]
---

# Secret scanning at an egress boundary: match shape, split the fail policy

## Context

DAYZEROCTO-4 asked to "scan the shareable report artifact for secrets before writing" — and it named the mechanism: reuse the existing `redact()` in `scripts/dzcto_common.py`. Running that function against representative input before building on it falsified the entire premise in minutes:

```python
redact("authorization: Bearer ghp_ABC123def456")
# -> "authorization: <redacted> ghp_ABC123def456"
```

The old value pattern — `(?i)(token|secret|password|api[_-]?key|authorization)(['"\s:=]+)([^'"\s,}]+)` — has a value group that stops at the first whitespace. So it redacted the *scheme word* ("Bearer") and shipped the credential verbatim. It also mangled ordinary prose (`"The secret to our success"` -> `"The secret <redacted> our success"`) and blanked legitimate metric keys via an unanchored dict-key substring match (`tokens_processed` -> `<redacted>`). Wiring this in as-asked would have produced an artifact that *looks* sanitized and isn't — strictly worse than no scan, because it manufactures false confidence at an egress boundary where a leak is unrecoverable. The same silent Bearer leak already existed in production at `scripts/dzcto.py:1807` (`collect_issue_bundle` on log text); it was fixed as a side effect of hardening the shared detector.

The rebuild (`scripts/dzcto_common.py`, `scripts/dzcto_artifact.py`, `tests/test_dzcto_secrets.py`, `tests/test_dzcto_artifact.py`) settled on two reusable patterns.

## Guidance

### Pattern 1 — Match the *shape* of the secret, not the English word next to it

"Keyword near a value" is the wrong primitive. Every mature scanner (gitleaks, detect-secrets, trufflehog, GitHub secret scanning) abandoned it. Match the shape of the credential — provider prefixes, length, charset — via `PROVIDER_RULES` (`dzcto_common.py:227`): `gh[pousr]_`, `github_pat_`, `AKIA`/`ASIA`, `sk-`/`sk-proj-`, `xox[baprs]-`, `AIza`, `sk_live`/`rk_live`, `SG.`, PEM blocks, JWTs. These are HIGH confidence and fire on shape alone, independent of any surrounding key.

- **Entropy is a secondary gate on an already-extracted candidate, never a primary trigger.** The generic assignment rule (`ASSIGNMENT_RULE`, `dzcto_common.py:239`) first isolates a `key: value` / `key = value` candidate, then `assignment_value_is_secret` (`:331`) applies a length/charset/entropy floor. Entropy never scans free text on its own.
- **Scope benign-shape exclusions to the generic rule only.** A git-evidence-derived report is full of 40-char SHAs, which clear a 3.0 hex entropy floor. `is_benign_secret_shape` (`:320`) excludes SHAs and UUIDs — but it gates *only* `assignment_value_is_secret`, never a provider-prefix hit. `test_benign_exclusion_never_suppresses_provider_prefix` locks this: a hex-shaped exclusion must never suppress a real credential.
- **HIGH wins overlap resolution.** When a provider hit and a generic hit cover the same span, `_selected_findings` (`:352`) keeps the HIGH finding.
- **Deterministic, idempotent placeholders.** Redaction writes a constant `[REDACTED:<rule>]` (`:210`), not a value-derived or random marker — a random marker would make every week's artifact differ and destroy week-over-week diffs. The placeholder is itself excluded from re-matching (`REDACTION_PLACEHOLDER_PATTERN`), so redaction is idempotent (`test_idempotence_and_determinism`).

### Pattern 2 — One shared detector, two consumers, opposite fail policies — put the policy at the caller

Two consumers need opposite behavior on a high-confidence hit:

- The **artifact write path** is an egress boundary — a leaked credential in a shared HTML report is unrecoverable, so it must **BLOCK**.
- The **troubleshooting-bundle path** (`dzcto.py:collect_issue_bundle`) must **REDACT and keep working** — crashing a debug bundle helps no one.

Resolution: **the shared detector never decides policy.** `redact()` / `redact_text()` in `dzcto_common.py` are detect-and-redact only and never raise `SystemExit`, so any consumer can call them safely (`test_redact_never_blocks_on_high_confidence_hit`). Blocking lives *exclusively* in the `dzcto_artifact.py` callers: `print_secret_blocks(..., block_all=...)` (`:6058`) raises `SystemExit(1)`; `sanitize_current_report_data` (`:6085`) blocks on HIGH; `sanitize_prior_report_data` (`:6100`) redacts and warns but has no block call at all.

Two corollaries the rebuild had to get right:

- **Sanitizing "the data" is not sanitizing "the artifact."** Three separate user-controlled inputs reach disk: `structured_data`, the raw `--body-file` body, and `args.title` — and the title reaches the filename slug, the page header, *and* the provenance `<script>` block via `provenance_payload(title=...)`. `html.escape()` does **not** strip credentials (there is no markup to escape). Enumerate every input that reaches disk. `enforce_safe_report_title(args.title)` (`:6080`, `block_all=True` internally) runs at `:6189` — *before* slug derivation — so a secret in the title blocks rather than silently renaming the file (`test_high_confidence_secret_in_title_blocks_before_slug_write`).
- **Derived/historical data is its own leak source with its own correct policy.** `report_changes_html()` renders values *from the prior report* (removed items, previous summary, metric deltas) into the new report. A report written before this feature landed could carry a raw secret into a freshly "sanitized" artifact. Fresh input **blocks** (the author can fix it); prior-report-on-disk **redacts but never blocks** (no user action could clear it, and blocking would wedge the weekly cadence permanently). `sanitize_prior_report_data` runs at `:6285`, after `locate_prior_report`, and only warns (`test_secret_bearing_prior_report_is_redacted_without_blocking`).

## Why This Matters

- A redaction that silently fails is **worse than no redaction** — it manufactures false confidence at the one boundary where a leak can't be recalled. The cheapest guard against this class of bug is empirical: run the control against real inputs before trusting it. That took minutes here and overturned the issue.
- Shape-based detection catches the credential wherever it appears (in prose, after "Bearer", inside JSON), instead of depending on an adjacent English word the attacker/author doesn't control.
- Putting the fail policy at the caller, not in the detector, is what lets one hardened detector serve an egress boundary and a resilience path without either compromising the other. Baking "block" into the shared function would crash the debug bundle; baking "never block" in would silently ship the report.

## When to Apply

- Any time you add a pre-write or pre-share secret scan — start from provider-shape rules, not keyword-near-value.
- Whenever a single detector/validator is consumed by both a fail-closed boundary and a fail-open resilience path: keep the detector policy-free and locate blocking at each caller.
- Before trusting *any* inherited masking/redaction/sanitizer as a security control: feed it a `Bearer <token>` line and a prose sentence containing "secret" and read the output.
- When redacted output is diffed or compared over time: use a constant, idempotent placeholder.

## Examples

Accepted tradeoffs (documented as tradeoffs, not defects):

- **Entropy floor 3.0 for both charsets**, where research suggests ~4.5 for base64. Deliberately more sensitive — it over-redacts only in the LOW redact-and-warn tier (never blocks on it), which is the fail-safe direction for a report generator.
- **Provider lookarounds `(?<![\w-])` / `(?![\w-])`** mean a token glued to a word char (`aghp_TOKEN`) is not matched. A deliberate precision tradeoff, tested, that prevents false positives on identifiers that merely contain a prefix substring.

Regression coverage that pins the behavior:

- `tests/test_dzcto_secrets.py::TestRedaction::test_bearer_token_is_redacted_without_mangling_scheme` — the exact failure that falsified the issue: `"authorization: Bearer [REDACTED:github_pat]"`, scheme word intact.
- `test_prose_survives_byte_intact` and `test_anchored_key_matching` (`tokens_processed` stays `1234`) — the prose-mangling and unanchored-key bugs.
- `test_redact_never_blocks_on_high_confidence_hit` — the shared detector never raises `SystemExit` (the split-fail-policy contract).
- `tests/test_dzcto_artifact.py` — `test_high_confidence_secret_in_title_blocks_before_slug_write`, `test_high_confidence_secret_in_raw_body_blocks`, `test_high_confidence_secret_in_metric_value_blocks`, `test_low_confidence_secret_is_redacted_and_warned`, `test_secret_bearing_prior_report_is_redacted_without_blocking`, `test_redaction_is_stable_across_week_over_week_reports`.

## Related

- docs/solutions/architecture-patterns/helper-computes-agent-narrates-2026-07-03.md — the sibling "where does each responsibility live" split (deterministic helper vs. LLM prose); here it's policy-free detector vs. policy-owning caller.
- docs/solutions/design-patterns/cadence-scoped-prior-report-selection-2026-07-03.md — how the prior report (the derived-data leak source above) is selected.
- docs/solutions/best-practices/audit-for-dead-but-complete-machinery-2026-07-03.md — the same `report_changes_html` prior-report path, wired up in DAYZEROCTO-1, that made historical data a live egress source here.

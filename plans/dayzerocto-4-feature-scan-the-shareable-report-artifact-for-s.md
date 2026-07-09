---
title: "DAYZEROCTO-4: Scan the shareable report artifact for secrets before writing"
status: planned
priority: p1
created: 2026-07-09
effort: medium
tags: [security, secret-scanning, ceo-report, artifact, redaction]
linear_id: DAYZEROCTO-4
artifact_contract: ce-unified-plan/v1
artifact_readiness: implementation-ready
execution: code
product_contract_source: ce-plan-bootstrap
---

# DAYZEROCTO-4: Scan the shareable report artifact for secrets before writing

## Goal

Stop credentials from reaching the one artifact designed to leave the company: scan CEO report content for secret-shaped values at render time, blocking the write on high-confidence hits and redacting lower-confidence ones. The business contract lives on DAYZEROCTO-4; this plan owns only the engineering response.

---

## Problem Frame

The issue frames this as "wire the existing `redact()` into the report path." **That framing is wrong, and building it would ship a regression.** Running the current `redact()` (`scripts/dzcto_common.py:212`) against representative report content produces two disqualifying behaviors, both verified by execution:

**1. It leaks the credential it claims to redact.**

```
redact("authorization: Bearer ghp_ABC123def456")
  -> "authorization: <redacted> ghp_ABC123def456"
```

`SECRET_VALUE_PATTERN`'s value group `[^'"\s,}]+` halts at the first space, so it consumes the scheme word `Bearer` and emits the token verbatim. An artifact processed this way *looks* sanitized. That is strictly worse than no scan at all, because it manufactures false confidence at exactly the boundary where a leak is unrecoverable.

**2. It mangles ordinary English.**

| Input | Current output |
|---|---|
| `The secret to our success was focus.` | `The secret <redacted> our success was focus.` |
| `Password reset flow is now live.` | `Password <redacted> flow is now live.` |
| `The authorization model was simplified.` | `The authorization <redacted> was simplified.` |

Separately, `SECRET_KEY_PATTERN` is an unanchored substring match on dict keys, so a legitimate metric label is blanked: `{"tokens_processed": 1234}` -> `{"tokens_processed": "<redacted>"}`. `metrics` is a user-controlled `label -> scalar` namespace (`validate_ceo_report`), so this is a live false-positive surface, not a hypothetical.

The engineering task is therefore **harden the detector, then wire it** — not wire what exists. The issue's own constraint ("treat the existing redaction code as unvetted on this path") anticipates this.

---

## Context

**There are three user-controlled inputs, not one chokepoint.** In `scripts/dzcto_artifact.py` `main()` (~6108–6193):

- `structured_data: dict` — from `--data-file`, or auto-loaded `reports/<kind>/data.json`
- `body: str` — from `--body-file` (raw HTML) or stdin
- **`args.title: str`** — free text, and **part of neither of the above**

The HTML body is *derived from* `structured_data` (`render_structured_report`, ~6169), and the same dict is written to both `<slug>.json` (~6190) and `data.json` (~6191). So sanitizing `structured_data` once, before `render_structured_report`, covers those three writes together. The raw `body` string is a second, independent path.

**`--title` is a third egress path, and provenance is a risk surface after all.** `args.title` reaches disk in four places: the filename slug (`slugify(f"{report_date} {args.title}")`, ~6157); the rendered page header (`render_report_page(args.title, …)`, ~6188); and — via `provenance_payload(…, title=args.title, …)` (~6184) — `payload["title"]`, `relativePath`, and `artifactId`, which `provenance_block()` embeds verbatim as a `<script type="application/json">` tag in the HTML (`dzcto_common.py:179`). Crucially, `html.escape()` does **not** strip a credential: `html.escape("ghp_ABC123def456")` returns it unchanged, because there is no markup character to escape. A token pasted into `--title` therefore lands in the shareable artifact in three places plus the filename, and no amount of scanning `structured_data` catches it.

**Ordering is load-bearing.** `locate_prior_report()` (~6165) reads the previous report's JSON off disk to build the week-over-week diff. Sanitization must run *before* it, so comparison is redacted-vs-redacted. The placeholder must be deterministic — a value-derived or random marker would make every week's artifact differ from the last even when content is unchanged, destroying the diff (see `docs/solutions/design-patterns/cadence-scoped-prior-report-selection-2026-07-03.md`).

**Prior reports are a second, independent leak source.** `report_changes_html()` (~1891) renders content *from the prior report* into the new HTML: `removed` items are drawn from `previous_data`, `previous_summary` comes from `report_lead_summary(previous_data)`, and `metric_delta_items(data, previous_data)` renders the old metric values (the `5 → 8` deltas). A report written **before** this feature lands can therefore carry a raw credential into a **new** report's week-over-week section, even when the new report's own data is perfectly clean. Sanitizing only `structured_data` does not close this. See KTD7.

**The block path writes no artifact — state it precisely.** `SystemExit(1)` propagates cleanly: `main()` is reached only via `raise SystemExit(main(...))`, and `dzcto.py` shells out through `run_script` -> `subprocess.call`, which returns the exit code. All four artifact writes (~6188, ~6190, ~6191, ~6192) and `render_index` (~6195) sit after the block point, so none of them fire. It is *not* true that the run "writes nothing," though: `ensure_sidecar` (~6085) and `apply_init_metadata` (~6086) persist `company_description` / `report_prompt_context` into sidecar config beforehand, unscanned. Those are local config, not the shareable artifact — the guarantee that matters holds, but claim only that guarantee.

**Nothing consumes `data.json` expecting raw values.** Verified by grep: it is re-read only by the renderer's own auto-load path (~6127) and is explicitly excluded from every prior-report glob (`:2498`, `:3236`, `:3250`, `:3350`, `dzcto.py:165`, `dzcto.py:518`).

**Reports are built from git evidence**, so the content legitimately contains commit SHAs. A naive entropy detector flags every 40-char hex SHA (entropy ~3.8–4.0, clearing the conventional 3.0 hex floor). SHA and UUID exclusions are mandatory, not polish.

**`redact()` has a second consumer.** `collect_issue_bundle` (`scripts/dzcto.py:1816`, `:1840`) calls it on config and log text and carries the identical `Bearer` leak today. No test in `tests/` locks `redact()`'s behavior.

### Research grounding

External research (best-practices + framework docs) was run by the `cb-plan` wrapper before this plan. The load-bearing findings:

- Every mature scanner (gitleaks, detect-secrets, trufflehog, GitHub secret scanning) **abandoned "keyword near a value"** regex — precisely the broken primitive here. Match the *shape of the secret*, not the neighboring English word.
- **Literal provider prefixes are ~80% of the practical win** and have near-zero false-positive rate: prose never looks like `AKIAIOSFODNN7EXAMPLE`. Safe to fail closed on.
- **Entropy is a secondary gate, never a primary trigger** — applied only to an already-extracted, length-gated candidate value.
- **GitHub push protection is the reference model** for an egress boundary: hard-block on high confidence, because a published credential cannot be un-published.
- Pitfalls: entropy false-positives on SHAs/UUIDs; double-redaction; non-deterministic placeholders breaking diffs; redacting the wrong span (the bug here); over-redaction eroding trust until users route around the scanner.

---

## Key Technical Decisions

### KTD1. Harden `redact()` in `dzcto_common.py` rather than adding a report-scoped scanner

**Decision:** fix the shared detector in place.

**Rationale:** the `Bearer` leak is a real defect on the *existing* consumer too — `collect_issue_bundle` ships credentials in troubleshooting bundles today. No test locks the current behavior, so the blast radius is behavioral-only and strictly corrective. A parallel report-scoped scanner would leave that leak standing and create two near-duplicate pattern sets that drift. The issue's "reusing `redact()`/patterns" permits either; blast radius is the discriminator and it points one way.

**Consequence:** `scripts/dzcto.py` changes behavior without changing code. U4 verifies it improves (catches the token it used to leak) and does not regress.

**Load-bearing boundary — the shared detector NEVER blocks.** `dzcto_common.py` provides *detection and redaction only*. It must never call `sys.exit` / `raise SystemExit`, and must never decide policy. The block decision (KTD2) lives **exclusively in the `dzcto_artifact.py` caller** (U3), which inspects the returned findings and chooses to exit.

This is not a style preference. The two consumers want **opposite** high-confidence behavior:

| Consumer | High-confidence hit | Why |
|---|---|---|
| `dzcto_artifact.py` (shareable artifact) | **Block** | Egress boundary; a published credential is unrecoverable |
| `dzcto.py` `collect_issue_bundle` | **Redact** | A troubleshooting bundle must still be produced; crashing on a token in `latest.log` breaks `dzcto doctor --bundle` |

If an implementer reads "harden the shared detector" (KTD1) together with "block on high confidence" (KTD2) and puts the exit inside `redact()`, then any config value or log line containing a `ghp_`-shaped token makes `dzcto doctor --bundle` crash — the exact regression U4 claims is impossible. Naming the boundary here is what makes U4's "strictly corrective" guarantee true rather than accidental.

### KTD2. Two-tier fail policy: block on high confidence, redact-and-warn on low

| Detection | Confidence | Action |
|---|---|---|
| Provider-prefix rule (`ghp_`, `AKIA`, `sk-`, `xox…`, `AIza`, PEM block, JWT triple) | High | **Block the write**, exit non-zero, name the rule and location on stderr |
| Narrow assignment rule + entropy gate | Low | Redact in place, warn on stderr |
| Local filesystem path | Low | Redact in place, warn on stderr |

**Rationale:** the egress boundary is asymmetric. A false block costs one regenerate of a weekly report; a false pass publishes a credential permanently. Provider prefixes essentially never fire on prose, so blocking on them is safe. Entropy-gated generic hits are where false positives live, so those degrade to redact-and-warn — a stray git SHA must never wedge the weekly report. Every action is logged; nothing is redacted silently.

### KTD3. Retire the bare-keyword `SECRET_VALUE_PATTERN`

It is the single root cause of *both* verified defects — the prose false positive and the `Bearer` false negative. Replace it with:

- a **rule table** of provider-prefix patterns, bounded by explicit `(?<![\w-])` / `(?![\w-])` lookarounds (not `\b`, which is unreliable adjacent to `_` and `-`);
- a **narrow assignment rule** that fires only on `key = "value"` / `key: value` shapes where the value clears a length floor *and* an entropy floor.

Bare `secret` / `password` / `authorization` as prose words must never trigger anything.

### KTD4. Anchored key matching

Replace the unanchored `SECRET_KEY_PATTERN.search(key)` with exact-name matching plus a suffix rule (`*_token`, `*_secret`, `*api_key`, `*password`, `*credential`). `tokens_processed` survives; `github_token` and `openai_api_key` still redact. Preserves the issue-bundle's real coverage while freeing the metrics namespace.

### KTD5. Deterministic, idempotent, HTML-safe placeholder

Format: `[REDACTED:<rule-name>]` (e.g. `[REDACTED:github_pat]`).

- **Deterministic** — same input, same output, every week; the week-over-week diff stays clean.
- **Idempotent** — the placeholder must not match any detection rule, so re-scanning redacted content is a no-op.
- **HTML-safe** — `--body-file` is raw HTML; square brackets need no escaping and cannot break markup.

It carries the rule name so a reader can tell *what* was removed without seeing the value.

### KTD6. Stdlib only; no new dependency

`re`, `math`, `collections.Counter`. No maintained package exposes just the prefix constants as data; `detect-secrets` (importable, offline) and `gitleaks` (Go binary) are both heavier than scanning one generated artifact in-process. Vendor a small hand-picked rule table derived from gitleaks' default config. This holds the "Functional" altitude the issue asks for — **do not build a general entropy scanning engine.**

### KTD7. Sanitize `previous_data` too — but never block on it

**Decision:** after `locate_prior_report()` returns, run `previous_data` through the **redact-only** path, regardless of confidence tier. A HIGH finding in a prior report redacts and warns; it does **not** block.

**Rationale:** the two inputs have different provenance and therefore different correct policies.

- `structured_data` is *this run's* input. The author can fix it by removing the credential, so blocking is actionable and correct.
- `previous_data` is an *already-written artifact on disk*, possibly authored before this feature existed. Blocking on it would wedge every future report permanently, with no action the user can take short of hand-editing history. That is a denial-of-service on the weekly cadence, and it fails closed in the wrong direction — the *new* artifact is the thing leaving the company, and redacting the diff section fully protects it.

**Consequence:** the old report on disk still contains the secret. That is pre-existing exposure, out of scope for this issue, and worth a follow-up sweep (see Scope Boundaries). What this plan guarantees is that **no newly written artifact contains it.**

---

## High-Level Technical Design

```mermaid
flowchart TD
    T["--title (free text)"] --> F
    A["--data-file / data.json"] --> C{structured_data?}
    B["--body-file / stdin<br/>(raw HTML)"] --> C
    C -->|dict| D["sanitize_report_data()"]
    C -->|str| E["sanitize_report_text()"]

    D --> F{high-confidence hit?}
    E --> F
    F -->|yes| G["stderr: rule + location<br/>exit non-zero<br/>NO ARTIFACT WRITTEN"]
    F -->|no| H["redact low-confidence<br/>warn on stderr"]
    F -.->|title also feeds| P["slug + page header<br/>+ provenance script tag"]
    P --> K

    H --> I["locate_prior_report()<br/>redacted vs redacted"]
    I --> M["prior .json from disk<br/>(may predate this feature)"]
    M --> N["sanitize_prior()<br/>REDACT ONLY — never block"]
    N --> J["render_structured_report()"]
    I --> J
    J --> K["write .html"]
    H --> L["write &lt;slug&gt;.json + data.json"]

    style G fill:#c0392b,color:#fff
    style D fill:#2980b9,color:#fff
    style E fill:#2980b9,color:#fff
    style N fill:#8e44ad,color:#fff
```

Three inputs, two policies. `args.title`, `structured_data`, and `body` are all *this run's* input — a high-confidence hit blocks, and the block path writes no artifact. `previous_data` is an artifact already on disk — it is redacted but never blocks, because no user action could clear it (KTD7). The dotted edge is the path the "single chokepoint" premise originally missed: `--title` reaches the HTML without passing through `structured_data` at all.

**Detection pipeline (directional, not implementation spec):**

```
scan(text):
  for rule in PROVIDER_RULES:                 # high confidence — NEVER suppressed
      for m in rule.regex.finditer(text):     # prefix + length + lookarounds
          yield Finding(rule, HIGH, m.span())

  for m in ASSIGNMENT_RULE.finditer(text):    # low confidence
      v = m.group("value")
      if len(v) >= MIN_LEN and shannon_entropy(v) >= MIN_ENTROPY:
          if not is_benign_shape(v):          # SHA / UUID / data: URI / placeholder
              yield Finding(ASSIGNMENT_RULE, LOW, m.span("value"))
```

Two properties are load-bearing:

- **`finditer`, not blind `sub`.** The entropy gate must consult the matched value before deciding, and every finding needs a location for the stderr report.
- **`is_benign_shape` gates only the generic rule.** A provider-prefix hit is never suppressed by the SHA/UUID exclusion. Otherwise a hex-shaped exclusion could silently swallow a real credential — reintroducing a false negative of exactly the kind this plan exists to eliminate.

---

## Files

- **Modify:** `scripts/dzcto_common.py` — detector primitives, hardened `redact()`, anchored key matching, retire `SECRET_VALUE_PATTERN`
- **Modify:** `scripts/dzcto_artifact.py` — sanitize both input paths at the chokepoint; block/warn policy; stderr reporting
- **Create:** `tests/test_dzcto_secrets.py` — detector unit tests (regression + false-positive corpus)
- **Modify:** `tests/test_dzcto_artifact.py` — end-to-end acceptance tests through the CLI
- **Verify (no change expected):** `scripts/dzcto.py` — inherits the hardened `redact()`

---

## Plan

### U1. Detector primitives in `dzcto_common.py`

**Goal:** add shape-based detection alongside the existing code. Purely additive — no caller behavior changes yet, so this unit is independently safe to land.

**Dependencies:** none.

**Files:** `scripts/dzcto_common.py`, `tests/test_dzcto_secrets.py`

**Approach:**
- `shannon_entropy(s) -> float` via `math.log2` + `collections.Counter`.
- `PROVIDER_RULES`: ordered table of `(name, compiled_regex)` for GitHub (`ghp_`/`gho_`/`ghs_`/`ghr_`/`github_pat_`), AWS (`AKIA`/`ASIA` + 16 upper-alnum), OpenAI (`sk-`, `sk-proj-`), Slack (`xox[baprs]-`), Google (`AIza` + 35), Stripe (`sk_live_`/`rk_live_`), SendGrid (`SG.`), PEM private-key header, JWT three-segment shape. Bound each with `(?<![\w-])` / `(?![\w-])`.
- `ASSIGNMENT_RULE`: `key` in a small keyword set, followed by `[:=]` and a **quoted or whitespace-free** value captured as a named group, with a length floor (>=20 base64-ish, >=16 hex). Must not match `The secret to our success`.
- `BENIGN_SHAPES`: git SHA (`[0-9a-f]{7,64}`), UUID, `data:` URI prefix, and the redaction placeholder itself. **Consulted only by the generic assignment rule** — never allowed to suppress a provider-prefix hit.
- `scan_secrets(text) -> list[Finding]` using `finditer`; `Finding` carries rule name, confidence, span, and a masked preview (never the raw value).
- `REDACTION_PLACEHOLDER = "[REDACTED:{rule}]"`.

**Patterns to follow:** module-level compiled `re` constants, matching the existing `SECRET_KEY_PATTERN` / `LOCAL_PATH_PATTERN` style.

**Test scenarios** (`tests/test_dzcto_secrets.py`):
- *Happy path:* `ghp_` + 36 chars detected as HIGH with rule `github_pat`; `AKIA` + 16 detected as HIGH.
- *The regression that motivates this plan:* `"authorization: Bearer ghp_ABC123def456"` — assert the token substring is detected, and (after U2) absent from the redacted output. This is the single most important assertion in the suite.
- *False positives — must yield zero findings:* `The secret to our success was focus.` · `Password reset flow is now live.` · `The authorization model was simplified.` · `Revenue grew 12% after the secret sauce shipped.`
- *Benign high-entropy shapes — zero findings:* a 40-char git SHA; a 7-char short SHA; a UUID; a `data:image/png;base64,…` prefix.
- *Entropy gate:* `api_key = "aaaaaaaaaaaaaaaaaaaaaa"` (low entropy, repeated char) → no finding; `api_key = "<random 32-char base64>"` → LOW finding.
- *Edge:* empty string, single char, and a string that is only the placeholder → zero findings (idempotence precondition).
- *Boundary:* `ghp_` embedded inside a longer identifier (`xghp_abc…`) → no match, proving the lookarounds work.
- *Exclusion cannot suppress a provider hit:* a provider-prefixed token whose body happens to be all lowercase hex (e.g. `ghp_` + 36 hex chars) → still HIGH. Guards the failure mode where the SHA exclusion swallows a real credential.

**Verification:** the detector fires on every planted credential in the corpus and on none of the prose or benign-shape cases.

---

### U2. Rewrite `redact()` on the hardened primitives

**Goal:** make `redact()` correct — redact the *whole* secret span, leave prose alone, anchor key matching. Retire `SECRET_VALUE_PATTERN`.

**Dependencies:** U1.

**Files:** `scripts/dzcto_common.py`, `tests/test_dzcto_secrets.py`

**Approach:**
- `redact_text(s) -> (str, list[Finding])` — `re.sub` with a **callable** replacement so the entropy gate runs inside the callback; replaces the full matched span with `[REDACTED:<rule>]`. Retain `LOCAL_PATH_PATTERN` handling as a LOW finding.
- Replace `SECRET_KEY_PATTERN.search(key)` with `is_secret_key(key)`: exact-name set plus suffix rule (`*_token`, `*_secret`, `*api_key`, `*password`, `*credential`). Keep `LOCAL_PATH_KEYS` as-is.
- `redact()` keeps its current recursive dict/list/str signature and return shape so `dzcto.py` needs no edit; internally it now delegates to `redact_text` and `is_secret_key`.
- **Delete `SECRET_VALUE_PATTERN`.** Leaving it in place invites a future caller to reintroduce the bug.

**Execution note:** characterization-first. Before changing `redact()`, land the U1 test corpus asserting today's *broken* outputs, then flip each assertion as the fix lands. The function has one existing consumer and zero test coverage; capturing current behavior first is how the `dzcto.py` blast radius stays visible rather than inferred.

**Test scenarios:**
- *Whole-span redaction:* `"authorization: Bearer ghp_ABC…"` → output contains neither `ghp_ABC…` nor the bare word `Bearer` mangled mid-sentence; the token span is replaced entirely.
- *Prose survives byte-intact:* each of the four false-positive sentences round-trips unchanged through `redact()`.
- *Anchored keys:* `{"tokens_processed": 1234}` → unchanged. `{"github_token": "x"}` and `{"openai_api_key": "y"}` → redacted. `{"credential_rotation_note": "we rotated keys"}` → key matches suffix rule → redacted (documented, intentional).
- *Idempotence:* `redact(redact(x)) == redact(x)` for every corpus entry.
- *Determinism:* two calls on the same input produce byte-identical output.
- *Nested structures:* secret inside a list inside a dict is found; `LOCAL_PATH_KEYS` still redact.
- *Error path:* `None`, `int`, `bool` values pass through untouched (existing contract).

**Verification:** the U1 corpus passes with the fixed assertions; `redact()`'s signature and return shape are unchanged.

---

### U3. Wire the report write path

**Goal:** sanitize both input shapes at the chokepoint, and enforce the two-tier policy.

**Dependencies:** U1, U2.

**Files:** `scripts/dzcto_artifact.py`, `tests/test_dzcto_artifact.py`

**Approach:**
- Import the scanner from `dzcto_common` (extend the existing `from dzcto_common import (...)` block, ~line 19). **All block/exit policy lives here in the caller** — the shared detector only reports findings (KTD1 boundary).
- **Scan `args.title` first**, before `slug` is computed (~6157). It is the earliest egress point: a HIGH finding must abort before the filename is derived, since the slug itself would carry the token. Title is scanned in **block-or-pass** mode only — silently redacting a user's report title would produce a confusingly-renamed artifact; the right answer is to make them fix it.
- Insert sanitization of `structured_data` **after** it is loaded and schema-stamped, and **before** `locate_prior_report()` (~6160). Sanitize `body` on the raw-text path at the same point.
- **Separately**, sanitize `previous_data` immediately after `locate_prior_report()` returns it (~6165), in **redact-only** mode per KTD7 — before it is handed to `render_structured_report()`.
- `structured_data["prior_report"]` is assigned at ~6168, *after* sanitization. This is safe: the value is a code-generated repo-relative path, not user content, and `LOCAL_PATH_PATTERN` only matches absolute `/Users`/`/home` paths. Do not re-sanitize after this assignment.
- On any HIGH finding in `structured_data` or `body`: print each finding to stderr as `dzcto: secret detected in <location>: rule=<name> (value masked)`, then `raise SystemExit(1)`. Write nothing — not the HTML, not the JSON, not `data.json`, not the manifest.
- On LOW findings (and on **any** finding in `previous_data`): replace in place, print `dzcto: redacted <n> value(s): <rule names>` to stderr, continue.
- Location for structured data is the JSON key path (e.g. `progress[0].summary`, `metrics.api_key`); for raw text it is a character offset. Never print the matched value.

**Patterns to follow:** the existing `print(f"dzcto: ceo-report schema warning: …", file=sys.stderr)` convention at ~6146; `raise SystemExit(...)` as used at ~6117.

**Test scenarios** (in `tests/test_dzcto_artifact.py`, `TestArtifactWritePath` style):
- *Blocks and writes no artifact:* a `ghp_`-shaped token planted in `headline` → CLI exits non-zero, stderr names the rule and `headline`, and the target `.html` / `.json` / `data.json` **do not exist** on disk. Requires a `check=False` variant of `run_cli` — the existing helper hardcodes `check=True` (`test_dzcto_artifact.py:346`) and would raise before the assertion.
- *Token in `--title` (the path the chokepoint premise missed):* `--title "CEO Report ghp_ABC…"` with clean data → exits non-zero, and **no file matching the slug exists**. Then assert the negative case explicitly: generate a clean report and confirm the token appears nowhere in the rendered HTML, including inside the `<script id="dzcto-provenance">` block. Guards all four title egress points (slug, page header, `provenance.title`, `artifactId`).
- *Token in a metric value:* `metrics: {"deploy_key": "ghp_…"}` → same block, location reported as `metrics.deploy_key`.
- *Raw-body path:* `--body-file` containing `<p>AKIA…</p>` → blocked; asserts the second input shape is covered.
- *Low-confidence redact-and-warn:* an entropy-clearing generic assignment in `risks_blockers[0].detail` → exit 0, artifact written, token absent from HTML and JSON, stderr carries the redaction warning.
- *Prose survives end-to-end:* `headline: "The secret to our success was focus."` → exit 0, sentence present byte-intact in the rendered HTML.
- *Git SHA survives:* `progress[0].summary` containing a 40-char SHA → exit 0, SHA present verbatim in the HTML. Guards the dominant entropy false positive on a git-evidence-derived report.
- *Integration — diff stability:* generate two consecutive weekly reports whose data contains an identical redacted low-confidence value; assert the week-over-week section renders and the placeholder is byte-identical across both artifacts. Mocks cannot prove this; it exercises `locate_prior_report()` against a real prior file.
- *Ordering:* a report with a LOW finding still produces a correct `prior_report` pointer, proving sanitization runs before prior-report location.
- *Legacy prior report (KTD7) — the leak this plan almost missed:* hand-write a prior-week `.json` on disk containing a raw `ghp_` token in `progress[0].items` and in `metrics`, bypassing the CLI. Generate a **clean** current-week report. Assert: exit 0 (the prior report must not wedge the cadence), the new HTML renders the week-over-week section, and the token is **absent** from the new `.html`. Covers both the `removed`-items and `metric_delta_items` render paths.
- *Prior-report redaction does not block:* the same fixture asserts a non-empty stderr warning and a written artifact — proving HIGH-in-prior redacts rather than exits non-zero.

**Verification:** a secret-bearing report never produces an artifact; a clean report is byte-identical to today's output.

---

### U4. Confirm the second consumer

**Goal:** verify `collect_issue_bundle` improves and does not regress. No production code change expected.

**Dependencies:** U2.

**Files:** `scripts/dzcto.py` (verify only), `tests/test_dzcto_secrets.py`

**Approach:** `dzcto.py` calls `redact()` / `redacted_json_text()` and is untouched by U2's internal rewrite. Confirm the call sites at `:1816`, `:1831`, `:1836`, `:1840` still typecheck against the unchanged signature, and that log text now redacts the `Bearer` token it previously leaked.

**Test scenarios:**
- *The inherited fix:* `redacted_json_text({"log": "authorization: Bearer ghp_…"})` → token absent from the serialized output. This is the pre-existing leak, closed as a side effect.
- *The shared detector never blocks (enforces the KTD1 boundary):* `redact("authorization: Bearer ghp_…")` — a HIGH-confidence hit — **returns a redacted string and does not raise `SystemExit`**. Assert with `try/except SystemExit: self.fail(...)`. This is the guard that keeps `dzcto doctor --bundle` alive; without it the boundary is documentation, not a constraint.
- *No regression:* a config dict with `github_token` still redacts; a log line of ordinary prose passes through unchanged.
- *Contract:* `redacted_json_text` still returns sorted-key, 2-space-indented JSON with a trailing newline (`dzcto.py` writes it straight into a zip).

**Verification:** existing `dzcto doctor --bundle` behavior is unchanged except that credentials no longer appear — and in particular it still *succeeds* on a bundle containing a credential.

---

## Assumptions

Recorded here rather than as decisions, because the scoping confirmation was skipped (headless run). Each is a bet worth challenging in review:

1. **Blocking is acceptable UX for the weekly report.** A high-confidence hit fails the run. The remedy is always "remove the credential from the report data," which is correct in every case — so no override flag is proposed. If a false block ever occurs in practice, that is the signal to add an allowlist (see Open Questions).
2. **Local-path redaction should apply to reports too.** `LOCAL_PATH_PATTERN` currently only runs for issue bundles. Extending it to the shareable artifact is consistent with the strategy guardrail's "client-identifying data" clause, and is treated as a LOW (redact-and-warn) finding.
3. **A key named `credential_rotation_note` redacting its value is acceptable.** The suffix rule is deliberately conservative. Over-redacting a note is recoverable; under-redacting a credential is not.
4. **Recall in prose is intentionally lower than in structured fields.** Per the research, free-text scanning uses only high-specificity provider patterns. A hand-typed password with no provider prefix and no assignment syntax will not be caught in prose. This is the accepted trade for never mangling the report.
5. **The git-SHA exclusion knowingly whitelists lowercase-hex secrets in the LOW tier.** `is_benign_shape` drops any `[0-9a-f]{7,64}` value, so an MD5-shaped or 64-hex API token (`api_key = "d41d8cd98f00b204e9800998ecf8427e"`) is excluded rather than redacted. The hole is bounded: it applies **only** to the generic assignment/text tier — provider-prefix rules are never suppressed (see KTD3's pseudocode note), and the structured-dict path still catches it by *key name* via `is_secret_key` regardless of value shape. The exclusion is not free, and this plan does not pretend it is; it is the price of not redacting every commit SHA in a git-evidence-derived report.

---

## Risks

| Risk | Mitigation |
|---|---|
| **Implementer puts the block inside the shared `redact()`, crashing `dzcto doctor --bundle`** | KTD1's explicit boundary: `dzcto_common.py` is detect-and-redact only, never exits. U4 asserts `redact()` on a HIGH hit does not raise `SystemExit`. |
| **A secret in `--title` bypasses the scan entirely** | U3 scans `args.title` before the slug is derived. U3 asserts the token is absent from the `dzcto-provenance` script block, not just the page body. |
| A false block wedges the weekly report | Provider-prefix rules only; near-zero FP rate. Entropy hits never block. SHA/UUID exclusions are tested explicitly. |
| Changing `redact()` silently alters issue-bundle output | U2's characterization-first execution note; U4 asserts the contract. No test locks the old behavior, so nothing breaks — but the change is made visible rather than accidental. |
| Redaction destabilizes week-over-week diffing | Deterministic placeholder (KTD5); sanitize before `locate_prior_report()`; U3 has an explicit two-report diff-stability test. |
| Scope creep into a general scanning engine | KTD6 caps the design at a vendored rule table + entropy gate. Explicitly out: verification-by-API-call, baseline files, plugin architecture. |
| Placeholder re-matches a rule, causing double-redaction | `BENIGN_SHAPES` includes the placeholder; idempotence is asserted in U2. |
| Sanitizing only `structured_data` leaves the week-over-week section leaking from legacy prior reports | KTD7 adds a second, redact-only sanitization point on `previous_data`. U3 tests it with a hand-written secret-bearing prior file. |
| The git-SHA exclusion (`[0-9a-f]{7,64}`) whitelists a genuine lowercase-hex secret | Real risk, accepted. The exclusion applies **only** to the generic entropy rule — provider-prefix rules are never suppressed by it. A hex-shaped secret with no prefix and no assignment syntax is out of reach by design (Assumption 4). |

---

## Scope Boundaries

**In scope:** the report artifact write path; hardening the shared detector both consumers use; tests.

**Deferred to Follow-Up Work:**
- **A sweep of already-written reports on disk.** KTD7 guarantees no *new* artifact leaks, but a pre-existing report that already contains a credential stays on disk. A `dzcto artifact --rescan` that redacts historical reports in place is the natural follow-up. (The credential should be rotated regardless — redaction is not remediation.)
- An allowlist / `--allow-secret` override, if a real false block is ever observed.
- Client-identifying-data heuristics beyond the existing pattern set (names, emails, client org names) — the issue explicitly defers these.
- A CI-side `gitleaks` or `detect-secrets` gate over committed artifacts, as defense in depth.

**Out of scope (per the issue):** auto-creating issues from audits; scheduling recurring audits.

---

## Open Questions

- **Should the redaction placeholder name the rule?** `[REDACTED:github_pat]` tells a reader what class of value was removed, which aids trust and debugging, but discloses that a GitHub token was present. For an artifact leaving the company, a bare `[REDACTED]` may be preferable. Resolve at implementation; the rule name is available either way for the stderr log. *(Leaning: bare `[REDACTED]` in the artifact, rule name on stderr only.)*
- ~~**Does any consumer parse `data.json` expecting unredacted values?**~~ **Resolved during planning:** no. `data.json` is re-read only by the renderer's own auto-load path (`dzcto_artifact.py:6127`) and is explicitly excluded from every prior-report glob (`:2498`, `:3236`, `:3250`, `:3350`, `dzcto.py:165`, `dzcto.py:518`).
- Planning surfaced four constraints the issue did not capture — the `Bearer` false-negative, the prose false positives, the `dzcto.py` second-consumer blast radius, and the diff-stability requirement. All four are recorded as a comment on DAYZEROCTO-4 and are load-bearing on KTD1–KTD5 above.

---

## Verification Contract

- `python3 -m unittest discover tests` passes, including the new `tests/test_dzcto_secrets.py`.
- A report whose JSON carries a `ghp_`-shaped token produces **no artifact on disk** and a non-zero exit.
- A report whose **`--title`** carries a `ghp_`-shaped token produces no artifact and a non-zero exit; a clean report has no token anywhere in its HTML, including the `dzcto-provenance` script block.
- `redact()` on a high-confidence hit **returns** — it never raises `SystemExit`. `dzcto doctor --bundle` still succeeds on a credential-bearing bundle.
- A report whose prose contains `The secret to our success was focus.` and a 40-char git SHA renders both byte-intact.
- Two consecutive weekly reports containing the same redacted value produce a stable week-over-week diff.
- A **clean** report generated against a **secret-bearing prior report** exits 0 and emits an artifact containing no trace of the prior secret.

## Definition of Done

All four units land, the Verification Contract passes, and every acceptance criterion on DAYZEROCTO-4 is demonstrably met through the CLI without reference to internal implementation details. The issue owns that contract; this plan does not restate it.

## Decisions

### Keep rule-named placeholders in emitted artifacts — 2026-07-09

Picked `[REDACTED:<rule>]` consistently for text, structured data, and prior-report redaction. Rejected a bare `[REDACTED]` artifact placeholder because the existing technical design depends on deterministic, idempotent replacements and the rule name gives reviewers enough context without exposing the matched value.

### Treat dictionary keys as artifact egress text — 2026-07-09

Picked recursive scanning/redaction of JSON object keys in addition to values, and moved structured-data sanitization before schema validation. Rejected value-only sanitization because user-controlled labels such as metrics keys can render into HTML or validation warnings, which would leave a leak path outside the original value scanner.

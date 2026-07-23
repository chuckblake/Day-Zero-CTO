---
title: "Rendering one home-directory config value silently un-hermetics every test of that renderer"
date: 2026-07-23
category: conventions
module: dzcto-renderer
problem_type: convention
component: testing
severity: medium
applies_when:
  - "Adding a value sourced from ~/.dzcto/config.json (or any home-dir file) to a rendered artifact"
  - "A renderer's tests pass locally but the rendered output depends on machine state"
  - "Introducing a call to read_global_config() into a code path that tests already cover"
symptoms:
  - "A render test passes on one machine and would render different HTML on another"
  - "A test suite that never touched $HOME suddenly reads the developer's real config"
  - "Output differs between the test suite and a real run for reasons the test cannot see"
related_components: [development_workflow, documentation]
tags: [testing, hermeticity, global-config, renderer, module-constant, injection-seam]
---

# Rendering one home-directory config value silently un-hermetics every test of that renderer

## Context

DAYZEROCTO-14 added the active profile's config to the CEO report index. Five of the six displayed
values come from `project_config(wiki_root)` — the **workspace sidecar** `.dzcto/config.json`, which
every test already builds inside a `TemporaryDirectory`. Those are hermetic by construction.

The sixth, `defaultProfile`, does not live there. It lives in the **global** config:

```python
# scripts/dzcto_common.py
GLOBAL_CONFIG_DIR  = Path.home() / ".dzcto"
GLOBAL_CONFIG_FILE = GLOBAL_CONFIG_DIR / "config.json"

def read_global_config() -> dict[str, Any]:
    return read_json(GLOBAL_CONFIG_FILE, {}) or {}
```

`GLOBAL_CONFIG_FILE` is a **module-level constant bound at import time**, and there is no environment
seam (no `DZCTO_HOME`). So the moment `render_index` calls `read_global_config()`, every existing test
of `render_index` starts reading the developer's real `~/.dzcto/config.json` — without any test
changing, any assertion failing, or any warning appearing.

The full suite stayed green through the change. That is the trap: it stayed green **only because no
existing assertion happened to read a global-derived value**. That is luck, not design. The next test
that asserts on rendered profile text would pass on the author's machine and fail in CI, or vice
versa, for reasons invisible in the test file.

The hazard was confirmed empirically, not theorized. An end-to-end smoke run — deliberately unpatched,
because a smoke test *should* use the real environment — rendered:

```
Global defaultProfile   arwen
```

`arwen` is a profile on the developer's laptop. Nothing in the repo mentions it.

## Guidance

**Treat "this render path now reads a home-dir file" as a test-infrastructure change, not a feature
detail.** The feature diff looks like one added dictionary key. The blast radius is every test of that
renderer.

**Give the reader an injection seam at the point of computation.** Do not make callers patch a
module constant they cannot see from the call site:

```python
def profile_config_view(
    config: dict[str, Any] | None,
    wiki_root: Path,
    global_config: dict[str, Any] | None = None,   # <- the seam
) -> dict[str, Any]:
    resolved_global_config = read_global_config() if global_config is None else global_config
```

Production callers pass nothing and get the real read. Tests pass a literal dict and are hermetic with
no patching at all. The default argument keeps the production call site unchanged, so the seam costs
nothing to the code that does not need it.

**Retrofit the seam into the tests that existed *before* your change.** The new tests are easy — you
are already thinking about it. The dangerous ones are the suites that predate the change and now read
`$HOME` without their author's knowledge:

```python
def setUp(self):
    ...
    # render_index reads the global config for defaultProfile (DAYZEROCTO-14); pin it so
    # these tests never depend on the developer's real ~/.dzcto/config.json.
    patcher = mock.patch.object(artifact, "read_global_config", dict)
    patcher.start()
    self.addCleanup(patcher.stop)
```

Patching `artifact.read_global_config` (the name as imported into the consuming module) works because
`dzcto_artifact.py` does `from dzcto_common import read_global_config`. Patching
`dzcto_common.GLOBAL_CONFIG_FILE` also works — `read_json(GLOBAL_CONFIG_FILE, ...)` resolves the module
global at call time, not at import — but it is the more indirect lever; prefer patching the function
the consumer actually calls.

**Write one test that proves the seam is load-bearing.** Otherwise a later refactor can quietly delete
the parameter and nothing notices:

```python
def test_default_profile_reads_the_global_config_through_the_injection_seam(self):
    with mock.patch.object(artifact, "read_global_config", lambda: {"defaultProfile": "injected-profile"}):
        view = artifact.profile_config_view({}, self.workspace)
    self.assertEqual(view["defaultProfile"], "injected-profile")
```

**Leave the smoke test unpatched.** Its whole job is to exercise the real environment. The divergence
between "patched suite renders `test-default`" and "smoke run renders `arwen`" is the signal that the
seam is doing real work.

## Why This Matters

A green suite is normally evidence. Here it is the *absence* of evidence: the tests did not fail
because they never looked at the value that became machine-dependent. The failure mode is deferred and
misattributed — it surfaces later, in someone else's test, on someone else's machine, as a mysterious
environment difference rather than as a consequence of the commit that introduced it.

It is also asymmetric in cost. Adding the seam while writing the feature is a default argument and two
`setUp` lines. Diagnosing it six months later means noticing that a module-level `Path.home()` constant
three files away is reachable from the renderer under test — which is exactly the kind of thing nobody
greps for, because nothing in the renderer says so.

## When to Apply

- Adding any value read from `$HOME`, a machine-global path, an env var, or the system clock to a
  function that already has test coverage.
- Reviewing a diff that introduces a call to `read_global_config()`, `Path.home()`, or a similar
  ambient-state reader into a previously pure-ish code path.
- Triaging a test that passes locally and fails in CI (or vice versa) with no relevant code difference
  — look for an ambient read added by an unrelated-looking feature commit.
- Any time a test suite's hermeticity depends on "no assertion currently reads that value" rather than
  on a structural guarantee.

## Related

- `absence-proxy-assertions-break-on-additive-rendering-2026-07-23.md` — the sibling trap from the same
  renderer and the same day: there, an existing test's *shorthand* silently constrains new output; here,
  an existing test's *environment* silently widens. Both are invisible from the production code, and
  both are found only by reading the tests before writing the feature.
- `../architecture-patterns/helper-computes-agent-narrates-2026-07-03.md` — the pattern that put the
  computation in a helper in the first place, which is what made a clean injection seam available.

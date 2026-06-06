---
name: Stale artifact report
about: Report an index, cadence, provenance, or stale-check issue.
title: "[Stale artifact]: "
labels: stale-artifact
assignees: ""
---

## What looks stale or wrong?

Describe the artifact, report folder, or cadence alert that seems incorrect.

## Check output

Run:

```bash
dzcto check-stale "<project folder>"
```

Paste the output here.

## Issue bundle

Run:

```bash
dzcto collect-issue-bundle "<project folder>"
```

Attach the generated zip if it does not contain private information you cannot share.

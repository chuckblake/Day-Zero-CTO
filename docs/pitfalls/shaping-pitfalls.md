---
title: Issue shaping pitfalls — repeated repair causes
domain: shaping
status: active
---

# Issue shaping pitfalls — repeated repair causes

## What it is

One-line rules for issue gaps that already cost a cb terminal run a repair or operator question; each names the run it came from. Read them before shaping an issue.

## Rules

- Acceptance tests for packaged behavior must execute the packaged artifact and assert observable results, never inspect bundled application source text. — origin: DAYZEROCTO-20, run 2edf1882

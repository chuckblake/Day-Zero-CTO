---
name: snapshot-report
description: "Generate the Day Zero CTO Snapshot Report. Use when the CTO needs one consumable report summarizing the current application state, what to communicate up, what to communicate down, priorities, risks, decisions, cadence, and recent report signals."
---

# Snapshot Report

Create the one report a CTO can read to understand what is going on and what must be communicated or prioritized.

## Workflow

1. Resolve the project folder. Durable outputs live under `<project>/knowledge/wiki/`.
2. Prefer the deterministic helper:

```bash
dzcto snapshot "<project folder>"
```

Use `--start YYYY-MM-DD --end YYYY-MM-DD` for an explicit window, or `--days N` for a rolling window ending today.

3. Review the generated snapshot for:
   - `Communicate Up`: CEO, founder, board, investor, or executive-facing points.
   - `Communicate Down`: team-facing expectations, decisions, focus, and process signals.
   - `Priorities`: the next operating actions for the CTO.
   - `Application State`: distillation of current reports.
   - `Risks`, `Decisions / Asks`, and `Operating Signals`.
4. If the snapshot exposes stale or incorrect facts, update the canonical source: `core/RISKS.md`, `core/DECISIONS.md`, `core/OPERATING_CADENCE.md`, learning state, or the source report JSON. Do not edit generated HTML.
5. Refresh with `dzcto refresh "<project folder>"` after source changes.

## Report Contract

The helper writes structured JSON and renders HTML under `reports/snapshot/`.

Expected JSON fields:

- `executive_read`
- `window`
- `metrics`
- `communicate_up`
- `communicate_down`
- `priorities`
- `application_state`
- `risks`
- `decisions`
- `operating_signals`
- `report_rollup`
- `sources`

## Standards

- This is a synthesis layer, not a new source of truth.
- Keep it short enough to read before a leadership meeting.
- Prefer sharp operating judgment over exhaustive coverage.
- Separate what should be communicated up from what should be communicated down.
- Make priorities actionable, with owners or next actions when known.

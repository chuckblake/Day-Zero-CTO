# Concepts

Shared domain vocabulary for this project — entities, named processes, and status concepts with project-specific meaning. Seeded with core domain vocabulary, then accretes as ce-compound and ce-compound-refresh process learnings; direct edits are fine. Glossary only, not a spec or catch-all.

## Reports

### Report artifact
The generated, shareable HTML page for a single report — the self-contained product written to disk and handed to a reader. Because it crosses the trust boundary the moment it is shared, it is an egress point: the inputs that flow into it are the last place a leaked credential can still be stopped.

### CEO report
A report artifact addressed to a company's CEO, summarizing progress, risks, asks, and metrics in executive framing, rendered deterministically from structured report data rather than authored freehand. The two flavors are the recurring weekly report and the ad-hoc report.

### Sample report
The single illustrative report artifact `dzcto init` seeds into a new workspace so a first-time reader can open real generated output before any evidence is wired. It is a report artifact in every rendering sense and deliberately not one in every accounting sense: an explicit `sample` marker on its report JSON excludes it from report counts, the weekly streak, prior-report selection, and the since-last-report window, so illustrative content can never be mistaken for, or counted as, traceable engineering evidence.

### Prior report
The previous report in the same cadence, selected as the comparison baseline so a new report can render an automatic week-over-week section. Its data is historical and outside the author's current control: it may predate current sanitization rules, so values carried forward from it are redacted if needed but are never allowed to block a new report.

### Since-last-report window
The weekly coverage span from the prior weekly report artifact's `window.end` (exclusive) through the run date (inclusive), so every calendar day lands in exactly one report. Its coverage cursor is weekly-scoped, while the prior-report diff baseline is not; these rules deliberately differ because the cursor is a coverage ledger and the diff baseline is a narrative comparison baseline.

### Weekly streak
The count of consecutive configured weekly cadence periods, ending at today, that contain a `weekly` CEO report. It is a best-effort local signal derived from report JSON on the index, not the canonical North Star metric with exclusions such as test runs or unopened reports.

### Provenance
The embedded machine-readable record identifying which skill version generated an artifact and from what inputs, carried inside the artifact so a regenerated page is self-describing. Because it echoes user-supplied fields such as the report title, it is one of the inputs that must be sanitized before the artifact is written.

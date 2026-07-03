#!/usr/bin/env bash
# Stop hook: if cb.yml worklog.enabled and the session left uncommitted changes,
# emit a reminder to run /cb:work-log. Never blocks (always exit 0).
set -euo pipefail

# Resolve the repo root so a drifted CWD doesn't silently disable the check.
root="$(git rev-parse --show-toplevel 2>/dev/null || echo "")"
[ -z "$root" ] && exit 0

enabled="$(ruby -ryaml -e '
  c = (YAML.safe_load(File.read(File.join(ARGV[0], ".claude", "cb.yml"))) rescue nil)
  c = {} unless c.is_a?(Hash)
  puts((c.dig("worklog", "enabled") == true && c.dig("hooks", "worklog_stop") != false).to_s)
' "$root" 2>/dev/null || echo false)"

# status --porcelain sees staged-only and untracked changes; diff --quiet misses both.
if [ "$enabled" = "true" ] && [ -n "$(git -C "$root" status --porcelain 2>/dev/null)" ]; then
  echo "cb: significant changes detected — consider /cb:work-log."
fi
exit 0

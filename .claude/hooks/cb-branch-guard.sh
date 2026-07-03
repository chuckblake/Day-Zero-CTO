#!/usr/bin/env bash
# PreToolUse hook for Write|Edit|MultiEdit.
# Blocks edits to files INSIDE THIS REPO while on the base branch (use a worktree
# instead). Edits to paths OUTSIDE the repo root — global ~/.claude config, an
# external notes/worklog vault, /tmp — are not this repo's concern and pass through.
#
# Hot path: this runs on every file edit, so everything beyond the two git
# lookups happens in ONE Ruby spawn (config read + payload parse + path check).
set -euo pipefail

# Not in a git repo → nothing to guard.
root="$(git rev-parse --show-toplevel 2>/dev/null || echo "")"
[ -z "$root" ] && exit 0
cur="$(git -C "$root" rev-parse --abbrev-ref HEAD 2>/dev/null || echo "")"

# PreToolUse delivers the tool call as JSON on stdin (tool_input.file_path);
# exec passes our stdin straight through to Ruby.
exec ruby -ryaml -rjson -e '
  root, cur = ARGV
  cfg = (YAML.safe_load(File.read(File.join(root, ".claude", "cb.yml"))) rescue nil)
  cfg = {} unless cfg.is_a?(Hash)  # a scalar-YAML cb.yml must fail open, not crash .dig
  exit 0 if cfg.dig("hooks", "branch_guard") == false   # cb.yml kill switch
  base = cfg.dig("worktree", "base") || "main"
  exit 0 unless cur == base                             # only the base branch is guarded

  d = (JSON.parse(STDIN.read) rescue {})
  ti = d["tool_input"] || {}
  target = ti["file_path"] || ti["path"] || ""
  exit 0 if target.empty?  # unknown payload shape → fail open, never block blindly

  # Compare CANONICAL paths so symlinks (/var → /private/var, symlinked checkouts)
  # and not-yet-created files resolve correctly — realpath the repo root and the
  # target path via its nearest existing ancestor.
  rp = (File.realpath(root) rescue File.expand_path(root))
  t  = File.expand_path(target, root)
  rest = []
  node = t
  until File.exist?(node)
    rest.unshift(File.basename(node))
    parent = File.dirname(node)
    break if parent == node
    node = parent
  end
  base_real = (File.realpath(node) rescue node)
  tp = rest.empty? ? base_real : File.join(base_real, *rest)

  if tp == rp || tp.start_with?(rp + File::SEPARATOR)
    warn "cb: refusing to edit #{target.inspect} on base branch #{base.inspect}. Create a worktree with /cb:start or /cb:worktree."
    exit 2
  end
' "$root" "$cur"

#!/usr/bin/env bash
# capture_prod_state.sh
# ---------------------------------------------------------------------------
# Read-only.  Runs INSIDE the prod container.  No PATs.  No network calls.
#
# For every app installed in this bench, records:
#   - app name
#   - git remote URL  (origin)
#   - current branch  (or "DETACHED")
#   - current HEAD SHA (full and short)
#   - latest tag reachable from HEAD  (empty if none)
#   - tag distance from HEAD (number of commits ahead of the tag)
#   - working-tree dirty marker (so you know if prod has uncommitted hacks)
#
# Output: a JSON document on stdout AND a copy at /tmp/prod_state.<timestamp>.json
#
# Usage:
#   docker exec -it -u frappe erpnext-backend-1 bash
#   cd ~/frappe-bench/apps/raven_ai_agent
#   bash scripts/capture_prod_state.sh
#
# Then on your laptop / sandbox:
#   docker cp erpnext-backend-1:/tmp/prod_state.<timestamp>.json ./prod_state.json
# ---------------------------------------------------------------------------
set -euo pipefail

BENCH_DIR="${BENCH_DIR:-$HOME/frappe-bench}"
APPS_DIR="$BENCH_DIR/apps"
OUTPUT="/tmp/prod_state.$(date +%Y%m%d-%H%M%S).json"

if [ ! -d "$APPS_DIR" ]; then
  echo "ERR: $APPS_DIR not found.  Set BENCH_DIR or run inside a bench container." >&2
  exit 2
fi

# Hostname helps you tell prod / test / sandbox snapshots apart later.
HOSTNAME_VAL=$(hostname 2>/dev/null || echo "unknown")
TIMESTAMP=$(date -u +"%Y-%m-%dT%H:%M:%SZ")

# Build a JSON array of {app: ...} objects, one per app.
echo "{" > "$OUTPUT"
{
  printf '  "captured_at": "%s",\n'   "$TIMESTAMP"
  printf '  "captured_on": "%s",\n'   "$HOSTNAME_VAL"
  printf '  "bench_dir":   "%s",\n'   "$BENCH_DIR"
  printf '  "apps": [\n'
} >> "$OUTPUT"

FIRST=1
for app_path in "$APPS_DIR"/*/; do
  app=$(basename "$app_path")
  [ -d "$app_path/.git" ] || continue   # skip non-git dirs

  pushd "$app_path" >/dev/null

  # Pick a remote in priority order:
  #   1. origin             (default Frappe convention)
  #   2. upstream           (some bench transport flows use this)
  #   3. first listed       (anything else)
  # We also record the remote name we used so the syncer can ignore apps with
  # NO remote at all (no upstream owner can be inferred).
  remote=""
  remote_name=""
  for candidate in origin upstream; do
    url=$(git config --get "remote.$candidate.url" 2>/dev/null || echo "")
    if [ -n "$url" ]; then
      remote="$url"
      remote_name="$candidate"
      break
    fi
  done
  if [ -z "$remote" ]; then
    first=$(git remote 2>/dev/null | head -n 1)
    if [ -n "$first" ]; then
      remote=$(git config --get "remote.$first.url" 2>/dev/null || echo "")
      remote_name="$first"
    fi
  fi

  branch=$(git rev-parse --abbrev-ref HEAD 2>/dev/null || echo "DETACHED")
  sha=$(git rev-parse HEAD 2>/dev/null || echo "")
  short_sha=$(git rev-parse --short=8 HEAD 2>/dev/null || echo "")

  # Latest tag reachable from HEAD (semver or any).  Empty if none.
  latest_tag=$(git describe --tags --abbrev=0 HEAD 2>/dev/null || echo "")
  tag_distance=""
  if [ -n "$latest_tag" ]; then
    tag_distance=$(git rev-list --count "$latest_tag..HEAD" 2>/dev/null || echo "")
  fi

  dirty="false"
  if ! git diff-index --quiet HEAD -- 2>/dev/null; then
    dirty="true"
  fi

  # Detect upstream owner from origin URL (best-effort).  Helps the syncer
  # decide whether it's an app we own (fork target) or an upstream we just
  # vendor (frappe, erpnext, ...).
  upstream_owner=""
  upstream_repo=""
  if [[ "$remote" =~ ^(https://|git@)github.com[:/]([^/]+)/([^/.]+)(\.git)?$ ]]; then
    upstream_owner="${BASH_REMATCH[2]}"
    upstream_repo="${BASH_REMATCH[3]}"
  fi

  if [ "$FIRST" -eq 0 ]; then
    printf ',\n' >> "$OUTPUT"
  fi
  FIRST=0

  cat >> "$OUTPUT" <<JSON
    {
      "app": "$app",
      "remote": "$remote",
      "remote_name": "$remote_name",
      "upstream_owner": "$upstream_owner",
      "upstream_repo": "$upstream_repo",
      "branch": "$branch",
      "sha": "$sha",
      "short_sha": "$short_sha",
      "latest_tag": "$latest_tag",
      "tag_distance": "$tag_distance",
      "dirty": $dirty
    }
JSON

  popd >/dev/null
done

{
  printf '\n  ]\n'
  printf '}\n'
} >> "$OUTPUT"

# Validate JSON before announcing success (best-effort).
if command -v python3 >/dev/null 2>&1; then
  python3 -m json.tool "$OUTPUT" >/dev/null
fi

echo "----------------------------------------------------------------"
echo "Wrote $OUTPUT"
echo "Apps captured: $(grep -c '"app":' "$OUTPUT")"
echo
echo "Copy to your sandbox with:"
echo "  docker cp <container>:$OUTPUT ./prod_state.json"
echo "Then on the sandbox run:"
echo "  bench --site \$SITE execute \\"
echo "    raven_ai_agent.bug_reporter.setup.sync_forks_from_prod_state \\"
echo "    --kwargs '{\"state_path\": \"/abs/path/to/prod_state.json\"}'"
echo "----------------------------------------------------------------"

# Echo the JSON so you can also pipe-paste.
cat "$OUTPUT"

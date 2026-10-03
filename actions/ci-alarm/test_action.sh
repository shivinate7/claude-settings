#!/usr/bin/env bash
# Red proof with a fake `gh`: a red latest run opens the issue; red-then-fixed and self-red do not.
set -u
here="$(cd "$(dirname "$0")" && pwd)"
tmp="$(mktemp -d)"; mkdir "$tmp/bin"
cat > "$tmp/bin/gh" <<'SH'
#!/usr/bin/env bash
case "$1 $2" in
  "run list") cat "$RUNS" ;;
  "issue list") echo "${OPEN:-}" ;;
  "issue create") echo "ISSUE $*" >> "$LOG" ;;
  "issue comment") echo "COMMENT $*" >> "$LOG" ;;
esac
SH
chmod +x "$tmp/bin/gh"
bad=0
t() { # want label
  : > "$tmp/log"
  out="$(PATH="$tmp/bin:$PATH" RUNS="$tmp/runs" LOG="$tmp/log" GITHUB_REPOSITORY=o/r SELF=alarm bash "$here/alarm.sh" 2>&1)"
  if [ "$1" = green ] && [ "$out" = green ] && [ ! -s "$tmp/log" ]; then echo "ok   $2"
  elif [ "$1" = red ] && [ "$out" = red ] && grep -q ISSUE "$tmp/log"; then echo "ok   $2"
  else echo "FAIL $2 (got: $out)"; bad=1; fi
}
echo '[{"workflowName":"ci","conclusion":"failure","createdAt":"2026-01-02","url":"u1"},{"workflowName":"ci","conclusion":"success","createdAt":"2026-01-01","url":"u0"}]' > "$tmp/runs"
t red latest-red-opens-issue
echo '[{"workflowName":"ci","conclusion":"success","createdAt":"2026-01-02","url":"u1"},{"workflowName":"ci","conclusion":"failure","createdAt":"2026-01-01","url":"u0"}]' > "$tmp/runs"
t green red-then-fixed-is-quiet
echo '[{"workflowName":"alarm","conclusion":"failure","createdAt":"2026-01-02","url":"u1"}]' > "$tmp/runs"
t green own-workflow-is-ignored
echo '[{"workflowName":"ci","conclusion":"success","createdAt":"2026-01-02","url":"u1"},{"workflowName":"deploy","conclusion":"timed_out","createdAt":"2026-01-01","url":"u2"}]' > "$tmp/runs"
t red one-red-workflow-among-green
echo '[{"workflowName":"ci","conclusion":"failure","createdAt":"2026-01-02","url":"u1"}]' > "$tmp/runs"
: > "$tmp/log"
OPEN=42 PATH="$tmp/bin:$PATH" RUNS="$tmp/runs" LOG="$tmp/log" GITHUB_REPOSITORY=o/r SELF=alarm bash "$here/alarm.sh" >/dev/null 2>&1
if grep -q "COMMENT issue comment 42" "$tmp/log" && ! grep -q ISSUE "$tmp/log"; then echo "ok   open-issue-gets-a-comment-not-a-duplicate"
else echo "FAIL open-issue-gets-a-comment-not-a-duplicate"; bad=1; fi
rm -rf "$tmp"; exit $bad

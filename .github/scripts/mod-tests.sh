#!/usr/bin/env bash
# The one home of the mod tests and the plain-english-map skill tests. Three CI jobs run it.
# Argument: none (both phases), mods or skill. No argument runs both phases. Any other argument exits 2.
# Bash 3.2 and Git Bash safe: no mapfile, no associative arrays, no ${x,,}.
set -u
case "${1:-}" in
  ""|mods|skill) ;;
  *) echo "usage: mod-tests.sh, argument mods or skill" >&2; exit 2 ;;
esac
cd "$(dirname "$0")/../.." || exit 1
want=${1:-}
rc=0

phase_mods() {
  local list f n=0 fail=0
  # A pipe would hide find's exit code, so find runs alone and the loop reads its output.
  list=$(find mods -name node_modules -prune -o \( -name '*.test.mjs' -o -name '*.test.js' \) -print) || { echo "find failed"; return 1; }
  [ -n "$list" ] || { echo "no mod test file found"; return 1; }
  while IFS= read -r f; do n=$((n + 1)); done <<< "$list"
  echo "mod tests: $n files"
  # Each exit code lands in fail, so a failing first or last file fails the phase.
  while IFS= read -r f; do
    node "$f" || fail=1
  done <<< "$list"
  return "$fail"
}

# The skill's tests load typescript from this checkout's node_modules, as an install does.
phase_skill() {
  npm ci --ignore-scripts --no-audit --no-fund || return 1
  (cd skills/plain-english-map/tests && node --test)
}

if [ -z "$want" ] || [ "$want" = mods ]; then
  phase_mods || rc=1
fi
if [ -z "$want" ] || [ "$want" = skill ]; then
  phase_skill || rc=1
fi
exit "$rc"

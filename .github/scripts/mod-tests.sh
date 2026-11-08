#!/usr/bin/env bash
# The one home of the mod tests and the plain-english-map skill tests. Three CI jobs run it.
# Argument: none (both phases), mods, skill or list. No argument runs both phases. Any other argument exits 2.
# list prints each file the two phases run, one repo-relative path per line, and runs nothing.
# Bash 3.2 and Git Bash safe: no mapfile, no associative arrays, no ${x,,}.
set -u
case "${1:-}" in
  ""|mods|skill|list) ;;
  *) echo "usage: mod-tests.sh, argument mods, skill or list" >&2; exit 2 ;;
esac
cd "$(dirname "$0")/../.." || exit 1
want=${1:-}
rc=0
skill_dir=skills/plain-english-map/tests

# The two finders are the one home of what each phase runs. The phases and list read them, so list cannot drift.
# A pipe would hide find's exit code, so find runs alone and its output is checked before it is printed.
mod_files() {
  local list
  list=$(find mods -name node_modules -prune -o \( -name '*.test.mjs' -o -name '*.test.js' \) -print) || { echo "find failed" >&2; return 1; }
  [ -n "$list" ] || { echo "no mod test file found" >&2; return 1; }
  printf '%s\n' "$list"
}

skill_files() {
  local list
  list=$(find "$skill_dir" -name node_modules -prune -o -name '*.test.mjs' -print) || { echo "find failed" >&2; return 1; }
  [ -n "$list" ] || { echo "no skill test file found" >&2; return 1; }
  printf '%s\n' "$list"
}

phase_mods() {
  local list f n=0 fail=0
  list=$(mod_files) || return 1
  while IFS= read -r f; do n=$((n + 1)); done <<< "$list"
  echo "mod tests: $n files"
  # Each exit code lands in fail, so a failing first or last file fails the phase.
  while IFS= read -r f; do
    node "$f" || fail=1
  done <<< "$list"
  return "$fail"
}

# The skill's tests load typescript from this checkout's node_modules, as an install does.
# node --test gets the listed files by name, from the tests folder, as the bare run had it.
phase_skill() {
  local list f
  npm ci --ignore-scripts --no-audit --no-fund || return 1
  list=$(skill_files) || return 1
  set --
  while IFS= read -r f; do set -- "$@" "${f#"$skill_dir"/}"; done <<< "$list"
  (cd "$skill_dir" && node --test "$@")
}

phase_list() {
  mod_files || return 1
  skill_files
}

if [ "$want" = list ]; then
  phase_list || rc=1
  exit "$rc"
fi
if [ -z "$want" ] || [ "$want" = mods ]; then
  phase_mods || rc=1
fi
if [ -z "$want" ] || [ "$want" = skill ]; then
  phase_skill || rc=1
fi
exit "$rc"

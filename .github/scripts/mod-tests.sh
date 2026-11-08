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
# check.mjs files are checks, not tests by name, and a red one must fail the phase too.
mod_files() {
  local list
  list=$(find mods -name node_modules -prune -o \( -name '*.test.mjs' -o -name '*.test.js' -o -name check.mjs \) -print) || { echo "find failed" >&2; return 1; }
  [ -n "$list" ] || { echo "no mod test file found" >&2; return 1; }
  printf '%s\n' "$list"
}

# Bare node --test collects these names recursively and skips node_modules (nodejs.org/api/test.html, "Test runner execution model"), so the phase runs all of them.
skill_files() {
  local list stem ext
  set -- -path '*/test/*.cjs' -o -path '*/test/*.mjs' -o -path '*/test/*.js'
  for stem in '*.test' '*-test' '*_test' 'test-*' 'test'; do
    for ext in cjs mjs js; do set -- "$@" -o -name "$stem.$ext"; done
  done
  list=$(find "$skill_dir" -name node_modules -prune -o -type f \( "$@" \) -print) || { echo "find failed" >&2; return 1; }
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
    # node reads its own stdin from /dev/null, so a test that reads stdin cannot swallow the rest of the list.
    node "$f" < /dev/null || fail=1
  done <<< "$list"
  return "$fail"
}

# The skill's tests load typescript from this checkout's node_modules, as an install does.
# node --test gets the listed files by name, from the tests folder: the files a bare run there would collect.
phase_skill() {
  local list f
  npm ci --ignore-scripts --no-audit --no-fund || return 1
  list=$(skill_files) || return 1
  set --
  while IFS= read -r f; do set -- ${1+"$@"} "${f#"$skill_dir"/}"; done <<< "$list"
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

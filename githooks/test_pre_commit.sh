#!/usr/bin/env bash
# Fixture suite for the shared pre-commit hook (githooks/pre-commit). Refused: a staged env file
# (by name, in a subfolder, by a wildcard stage, or among many files), a symlink that is absolute
# or leaves the repo, and a commit when guard_env cannot be imported. Allowed: an ordinary file,
# the example env file, a symlink that stays inside, a staged deletion, an empty commit, and the
# escape hatch. Red until the hook and its installer exist: each refused case then reads "landed".
set -u
here="$(cd "$(dirname "$0")" && pwd)"
repo="$(cd "$here/.." && pwd)"
hook="$here/pre-commit/pre-commit"
install="$here/pre-commit/install.sh"
. "$repo/lint/_test_git.sh"  # test-run signing opt-out (lint/_test_git.sh)
export GIT_CONFIG_GLOBAL=/dev/null GIT_AUTHOR_NAME=t GIT_AUTHOR_EMAIL=t@t GIT_COMMITTER_NAME=t GIT_COMMITTER_EMAIL=t@t
export CLAUDE_HOOKS_DIR="$repo/hooks"

# One run folder per run, from the one home of the test-temp standard (lint/_test_temp.py).
run="$(python3 -c 'import sys; sys.path.insert(0, sys.argv[1]); import _test_temp; print(_test_temp.run_folder())' "$repo/lint")" || { echo "FAIL setup: no run folder"; exit 1; }
trap 'rm -rf "$run"' EXIT
mkdir "$run/empty"

# Built from parts, so this file never holds an env file name whole.
E=".""env"
EX="$E"".example"
RC="$E""rc"

bad=0
[ -f "$hook" ] || { bad=1; echo "FAIL hook absent: githooks/pre-commit/pre-commit"; }

fresh() { # name: a repo of its own under the run folder, with one commit and no hook
  cd "$run" && mkdir "$1" && cd "$1" && git init -q -b main . && git commit -q --allow-empty -m init
}

arm() { # the installer copies the hook into this repo; with no installer there is no hook
  [ -f "$install" ] || return 0
  if ! bash "$install" >"$run/arm.out" 2>&1; then bad=1; echo "FAIL setup: installer failed to arm $(pwd)"; fi
}

must_run() { # label cmd...: a precondition; its failure is a setup failure, never a hook verdict
  label="$1"; shift
  "$@" >"$run/setup.out" 2>&1 && return 0
  bad=1; echo "FAIL setup: $label"; return 1
}

must_staged() { # path: the path is in the index
  git diff --cached --name-only | grep -qxF -- "$1" && return 0
  bad=1; echo "FAIL setup: $1 is not staged"; return 1
}

must_deleted() { # path: the staged change removes the path
  git diff --cached --name-only --diff-filter=D | grep -qxF -- "$1" && return 0
  bad=1; echo "FAIL setup: $1 is not a staged deletion"; return 1
}

must_link() { # path: the index holds a symlink (mode 120000) at the path
  git ls-files -s -- "$1" | grep -q '^120000 ' && return 0
  bad=1; echo "FAIL setup: the index holds no symlink (mode 120000) at $1"; return 1
}

t() { # want label cmd...: refused = the commit does not land, and the hook did not crash; ok = it lands
  want="$1"; label="$2"; shift 2
  before="$(git rev-parse -q --verify HEAD)"
  "$@" >"$run/last.out" 2>&1; got=$?
  landed=no
  [ "$(git rev-parse -q --verify HEAD)" = "$before" ] || landed=yes
  crashed=no
  grep -q Traceback "$run/last.out" && crashed=yes
  if [ "$want" = ok ] && [ "$landed" = yes ]; then echo "ok   $label"; return 0; fi
  if [ "$want" = refused ] && [ "$landed" = yes ]; then bad=1; echo "FAIL $label: the commit landed, wanted refused"; return 1; fi
  if [ "$want" = refused ] && [ "$crashed" = yes ]; then bad=1; echo "FAIL $label: the hook crashed, which is not a refusal"; return 1; fi
  if [ "$want" = refused ]; then echo "ok   $label"; return 0; fi
  bad=1; echo "FAIL $label: the commit did not land (exit $got), wanted allowed"
  sed 's/^/     | /' "$run/last.out" | head -n 3
  return 1
}

# refused
fresh r-add-all; arm
printf 'KEY=1\n' >"$E"; git add -A
must_staged "$E" && t refused "refused: $E staged by git add -A" git commit -q -m c

fresh r-subdir; arm
mkdir sub; printf 'KEY=1\n' >"sub/$E"; git add .
must_staged "sub/$E" && t refused "refused: sub/$E staged by git add ." git commit -q -m c

fresh r-rc; arm
printf 'export K=1\n' >"$RC"; git add -- "$RC"
must_staged "$RC" && t refused "refused: $RC staged by name" git commit -q -m c

fresh r-abs-link; arm
ln -s /outside/mirror abs; git add -- abs
must_staged abs && must_link abs && t refused "refused: absolute symlink abs -> /outside/mirror" git commit -q -m c

fresh r-up-link; arm
ln -s ../outside up; git add -- up
must_staged up && must_link up && t refused "refused: symlink up -> ../outside leaves the repo" git commit -q -m c

fresh r-climb-link; arm
ln -s a/../../x climb; git add -- climb
must_staged climb && must_link climb && t refused "refused: symlink climb -> a/../../x leaves the repo" git commit -q -m c

fresh r-many; arm
for i in $(seq 0 199); do printf '%s\n' "$i" >"f$i.txt"; done
printf 'KEY=1\n' >"$E"; git add -A
must_staged "$E" && t refused "refused: $E among 200 other staged files" git commit -q -m c

fresh r-no-import; arm
printf 'plain\n' >plain.txt; git add -- plain.txt
if must_staged plain.txt && t refused "refused: guard_env cannot be imported (CLAUDE_HOOKS_DIR empty)" env CLAUDE_HOOKS_DIR="$run/empty" git commit -q -m c; then
  grep -q PRE_COMMIT_GUARD "$run/last.out" || { bad=1; echo "FAIL the fail-closed refusal does not name the escape hatch PRE_COMMIT_GUARD"; }
fi

# allowed
fresh o-plain; arm
printf 'hi\n' >plain.txt; git add -- plain.txt
must_staged plain.txt && t ok "ok: ordinary file plain.txt" git commit -q -m c

fresh o-example; arm
printf 'KEY=\n' >"$EX"; git add -- "$EX"
must_staged "$EX" && t ok "ok: $EX staged" git commit -q -m c

fresh o-rel-link; arm
printf 'x\n' >x; ln -s x link; git add -- x link
must_staged link && must_link link && t ok "ok: symlink link -> x inside the repo" git commit -q -m c

fresh o-dots-link; arm
mkdir sub; printf 'x\n' >x; ln -s sub/../x link; git add -- x link
must_staged link && must_link link && t ok "ok: symlink link -> sub/../x inside the repo" git commit -q -m c

fresh o-subdir-link; arm
mkdir sub; printf 'x\n' >x; ln -s ../x sub/l; git add -- x sub/l
must_staged sub/l && must_link sub/l && t ok "ok: sub/l -> ../x, resolved from the link's own folder" git commit -q -m c

fresh o-delete; arm
printf 'KEY=1\n' >"$E"; git add -- "$E"
must_staged "$E" && must_run "$E was not committed under the hatch" env PRE_COMMIT_GUARD=off git commit -q -m setup && must_run "$E was not removed" git rm -q -- "$E" && must_deleted "$E" && t ok "ok: staged deletion of $E committed earlier under the hatch" git commit -q -m c

fresh o-hatch; arm
printf 'KEY=1\n' >"$E"; git add -- "$E"
must_staged "$E" && t ok "ok: escape hatch lets $E through" env PRE_COMMIT_GUARD=off git commit -q -m c

fresh o-hatch-no-import; arm
printf 'plain\n' >plain.txt; git add -- plain.txt
must_staged plain.txt && t ok "ok: escape hatch works when guard_env cannot be imported" env CLAUDE_HOOKS_DIR="$run/empty" PRE_COMMIT_GUARD=off git commit -q -m c

fresh o-empty; arm
t ok "ok: empty commit, nothing staged" git commit -q --allow-empty -m c

# installer
fresh i-different
printf '#!/bin/sh\necho mine\n' >.git/hooks/pre-commit; chmod +x .git/hooks/pre-commit
cp .git/hooks/pre-commit "$run/prior.hook"
if [ -f "$install" ]; then
  bash "$install" >"$run/inst.out" 2>&1; got=$?
  if [ "$got" -eq 0 ]; then bad=1; echo "FAIL installer replaces a different existing pre-commit (exit 0), wanted refused"
  elif ! cmp -s "$run/prior.hook" .git/hooks/pre-commit; then bad=1; echo "FAIL installer changes the different pre-commit it refused"
  else echo "ok   installer refuses a different existing pre-commit"; fi
else
  bad=1; echo "FAIL installer refuses a different existing pre-commit: no installer at githooks/pre-commit/install.sh"
fi

fresh i-none
if [ -f "$install" ]; then
  bash "$install" >"$run/inst.out" 2>&1; got=$?
  if [ "$got" -ne 0 ]; then bad=1; echo "FAIL installer refuses over no existing pre-commit (exit $got), wanted ok"
  elif ! cmp -s "$hook" .git/hooks/pre-commit || [ ! -x .git/hooks/pre-commit ]; then bad=1; echo "FAIL installer leaves no executable copy of githooks/pre-commit/pre-commit"
  else echo "ok   installer installs over no existing pre-commit"; fi
else
  bad=1; echo "FAIL installer installs over no existing pre-commit: no installer at githooks/pre-commit/install.sh"
fi

exit "$bad"

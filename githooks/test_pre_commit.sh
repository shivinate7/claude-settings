#!/usr/bin/env bash
# Fixture suite for the shared pre-commit hook (githooks/pre-commit). Each refused case names the
# rule that must fire: env-file (a staged env file), symlink-absolute, symlink-outside (a staged
# symlink that is absolute or leaves the repo, also when it replaces a tracked file), and
# env-file-check (guard_env cannot be imported). Allowed: an ordinary file, the example env file, a
# symlink that stays inside, a staged deletion, an empty commit, and the escape hatch. The
# installer replaces an earlier copy of the hook (it carries the marker line) and refuses a foreign
# pre-commit.
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
MARKER="# claude-settings githooks/pre-commit"

bad=0
[ -f "$hook" ] || { bad=1; echo "FAIL hook absent: githooks/pre-commit/pre-commit"; }
if [ -f "$hook" ]; then
  head -n 5 "$hook" >"$run/shipped5"
  grep -qxF -- "$MARKER" "$run/shipped5" || { bad=1; echo "FAIL shipped hook has no marker line in its first five lines: githooks/pre-commit/pre-commit"; }
fi

fresh() { # name: a repo of its own under the run folder, with one commit and no hook
  cd "$run" && mkdir "$1" && cd "$1" && git init -q -b main . && git commit -q --allow-empty -m init
}

arm() { # the installer copies the hook into this repo; with no installer there is no hook
  [ -f "$install" ] || return 0
  if ! bash "$install" >"$run/arm.out" 2>&1; then bad=1; echo "FAIL setup: installer failed to arm $(pwd)"; fi
}

run_installer() { # runs the installer in this repo; sets got; returns 1 when there is no installer
  [ -f "$install" ] || return 1
  bash "$install" >"$run/inst.out" 2>&1; got=$?
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

must_typechange() { # path: the staged change replaces the path's type (git's T)
  git diff --cached --name-status -- "$1" | grep -q '^T' && return 0
  bad=1; echo "FAIL setup: $1 is not a staged type change"; return 1
}

must_link() { # path: the index holds a symlink (mode 120000) at the path
  git ls-files -s -- "$1" | grep -q '^120000 ' && return 0
  bad=1; echo "FAIL setup: the index holds no symlink (mode 120000) at $1"; return 1
}

lands() { # label cmd...: the commit lands
  label="$1"; shift
  before="$(git rev-parse -q --verify HEAD)"
  "$@" >"$run/last.out" 2>&1; got=$?
  if [ "$(git rev-parse -q --verify HEAD)" != "$before" ]; then echo "ok   $label"; return 0; fi
  bad=1; echo "FAIL $label: the commit did not land (exit $got), wanted allowed"
  sed 's/^/     | /' "$run/last.out" | head -n 3
  return 1
}

refused_by() { # rule label cmd...: the commit does not land, the hook does not crash, and its output names rule <rule>
  rule="$1"; label="$2"; shift 2
  before="$(git rev-parse -q --verify HEAD)"
  "$@" >"$run/last.out" 2>&1
  if [ "$(git rev-parse -q --verify HEAD)" != "$before" ]; then bad=1; echo "FAIL $label: the commit landed, wanted refused"; return 1; fi
  if grep -q Traceback "$run/last.out"; then bad=1; echo "FAIL $label: the hook crashed, which is not a refusal"; return 1; fi
  if ! grep -Eq "rule $rule([^A-Za-z0-9_-]|\$)" "$run/last.out"; then
    bad=1; echo "FAIL $label: the refusal does not name rule $rule"
    sed 's/^/     | /' "$run/last.out" | head -n 3
    return 1
  fi
  echo "ok   $label"; return 0
}

# refused, each by the rule it must name
fresh r-add-all; arm
printf 'KEY=1\n' >"$E"; git add -A
must_staged "$E" && refused_by env-file "refused: $E staged by git add -A" git commit -q -m c

fresh r-subdir; arm
mkdir sub; printf 'KEY=1\n' >"sub/$E"; git add .
must_staged "sub/$E" && refused_by env-file "refused: sub/$E staged by git add ." git commit -q -m c

fresh r-rc; arm
printf 'export K=1\n' >"$RC"; git add -- "$RC"
must_staged "$RC" && refused_by env-file "refused: $RC staged by name" git commit -q -m c

fresh r-abs-link; arm
ln -s /outside/mirror abs; git add -- abs
must_staged abs && must_link abs && refused_by symlink-absolute "refused: absolute symlink abs -> /outside/mirror" git commit -q -m c

fresh r-up-link; arm
ln -s ../outside up; git add -- up
must_staged up && must_link up && refused_by symlink-outside "refused: symlink up -> ../outside leaves the repo" git commit -q -m c

fresh r-climb-link; arm
ln -s a/../../x climb; git add -- climb
must_staged climb && must_link climb && refused_by symlink-outside "refused: symlink climb -> a/../../x leaves the repo" git commit -q -m c

fresh r-many; arm
for i in $(seq 0 199); do printf '%s\n' "$i" >"f$i.txt"; done
printf 'KEY=1\n' >"$E"; git add -A
must_staged "$E" && refused_by env-file "refused: $E among 200 other staged files" git commit -q -m c

fresh r-typechange-abs; printf 'plain\n' >f; git add -- f; git commit -q -m base; arm
ln -sf /outside/mirror f; git add -- f
must_typechange f && must_link f && refused_by symlink-absolute "refused: tracked f replaced by an absolute symlink" git commit -q -m c

fresh r-typechange-out; printf 'plain\n' >f; git add -- f; git commit -q -m base; arm
ln -sf ../outside f; git add -- f
must_typechange f && must_link f && refused_by symlink-outside "refused: tracked f replaced by a symlink that leaves the repo" git commit -q -m c

fresh r-no-import; arm
printf 'plain\n' >plain.txt; git add -- plain.txt
if must_staged plain.txt && refused_by env-file-check "refused: guard_env cannot be imported (CLAUDE_HOOKS_DIR empty)" env CLAUDE_HOOKS_DIR="$run/empty" git commit -q -m c; then
  grep -q PRE_COMMIT_GUARD "$run/last.out" || { bad=1; echo "FAIL the fail-closed refusal does not name the escape hatch PRE_COMMIT_GUARD"; }
fi

# allowed
fresh o-plain; arm
printf 'hi\n' >plain.txt; git add -- plain.txt
must_staged plain.txt && lands "ok: ordinary file plain.txt" git commit -q -m c

fresh o-example; arm
printf 'KEY=\n' >"$EX"; git add -- "$EX"
must_staged "$EX" && lands "ok: $EX staged" git commit -q -m c

fresh o-rel-link; arm
printf 'x\n' >x; ln -s x link; git add -- x link
must_staged link && must_link link && lands "ok: symlink link -> x inside the repo" git commit -q -m c

fresh o-dots-link; arm
mkdir sub; printf 'x\n' >x; ln -s sub/../x link; git add -- x link
must_staged link && must_link link && lands "ok: symlink link -> sub/../x inside the repo" git commit -q -m c

fresh o-subdir-link; arm
mkdir sub; printf 'x\n' >x; ln -s ../x sub/l; git add -- x sub/l
must_staged sub/l && must_link sub/l && lands "ok: sub/l -> ../x, resolved from the link's own folder" git commit -q -m c

fresh o-delete; arm
printf 'KEY=1\n' >"$E"; git add -- "$E"
must_staged "$E" && must_run "$E was not committed under the hatch" env PRE_COMMIT_GUARD=off git commit -q -m setup && must_run "$E was not removed" git rm -q -- "$E" && must_deleted "$E" && lands "ok: staged deletion of $E committed earlier under the hatch" git commit -q -m c

fresh o-hatch; arm
printf 'KEY=1\n' >"$E"; git add -- "$E"
must_staged "$E" && lands "ok: escape hatch lets $E through" env PRE_COMMIT_GUARD=off git commit -q -m c

fresh o-hatch-no-import; arm
printf 'plain\n' >plain.txt; git add -- plain.txt
must_staged plain.txt && lands "ok: escape hatch works when guard_env cannot be imported" env CLAUDE_HOOKS_DIR="$run/empty" PRE_COMMIT_GUARD=off git commit -q -m c

fresh o-empty; arm
lands "ok: empty commit, nothing staged" git commit -q --allow-empty -m c

# installer
fresh i-upgrade
sed '$ s/$/ # an earlier copy/' "$hook" >.git/hooks/pre-commit
chmod +x .git/hooks/pre-commit
if run_installer; then
  if [ "$got" -ne 0 ]; then bad=1; echo "FAIL installer does not replace an earlier copy of our hook (exit $got), wanted ok"
  elif ! cmp -s "$hook" .git/hooks/pre-commit || [ ! -x .git/hooks/pre-commit ]; then bad=1; echo "FAIL installer leaves the earlier copy of our hook in place"
  else echo "ok   installer replaces an earlier copy of our hook"; fi
else
  bad=1; echo "FAIL installer replaces an earlier copy of our hook: no installer at githooks/pre-commit/install.sh"
fi

fresh i-different
printf '#!/bin/sh\necho mine\n' >.git/hooks/pre-commit; chmod +x .git/hooks/pre-commit
cp .git/hooks/pre-commit "$run/prior.hook"
if run_installer; then
  if [ "$got" -eq 0 ]; then bad=1; echo "FAIL installer replaces a foreign pre-commit with no marker (exit 0), wanted refused"
  elif ! cmp -s "$run/prior.hook" .git/hooks/pre-commit; then bad=1; echo "FAIL installer changes the foreign pre-commit it refused"
  else echo "ok   installer refuses a foreign pre-commit with no marker"; fi
else
  bad=1; echo "FAIL installer refuses a foreign pre-commit with no marker: no installer at githooks/pre-commit/install.sh"
fi

fresh i-none
if run_installer; then
  if [ "$got" -ne 0 ]; then bad=1; echo "FAIL installer refuses over no existing pre-commit (exit $got), wanted ok"
  elif ! cmp -s "$hook" .git/hooks/pre-commit || [ ! -x .git/hooks/pre-commit ]; then bad=1; echo "FAIL installer leaves no executable copy of githooks/pre-commit/pre-commit"
  else echo "ok   installer installs over no existing pre-commit"; fi
else
  bad=1; echo "FAIL installer installs over no existing pre-commit: no installer at githooks/pre-commit/install.sh"
fi

# --check through the shared pre-commit: a repo that holds githooks/main-ref/install.sh is held to main.
# Each fixture commits a copy of that installer and hook on main before any hook is armed, then commits
# on feat. The armed reference-transaction is a neutral copy that exits 0, except in the current case.
neutral="$run/neutral-hook"; printf '#!/bin/sh\n# an older copy\nexit 0\n' >"$neutral"; chmod +x "$neutral"
fresh_mr() { # name branch [installer]: a repo on branch that holds githooks/main-ref, then a feature branch to commit on
  cd "$run" && mkdir "$1" && cd "$1" && git init -q -b "$2" . || { bad=1; echo "FAIL setup: cannot make $1"; return 1; }
  mkdir -p githooks/main-ref && cp "${3:-$repo/githooks/main-ref/install.sh}" githooks/main-ref/install.sh && cp "$repo/githooks/main-ref/reference-transaction" githooks/main-ref/
  git add -A && git commit -q -m "main-ref fixture" && git switch -q -c feat
}
arm_hook() { # file: the armed reference-transaction for the repo in the working directory
  mkdir -p .git/hooks && cp "$1" .git/hooks/reference-transaction && chmod +x .git/hooks/reference-transaction
}
commit_err() { # cmd...: runs cmd; landed is 1 when HEAD moved; stdout to last.out, stderr to last.err
  before="$(git rev-parse -q --verify HEAD)"
  "$@" >"$run/last.out" 2>"$run/last.err"; got=$?
  if [ "$(git rev-parse -q --verify HEAD)" != "$before" ]; then landed=1; else landed=0; fi
}
refused_naming() { # pattern label cmd...: the commit does not land, the hook does not crash, stderr names pattern
  pat="$1"; label="$2"; shift 2
  commit_err "$@"
  if [ "$landed" -eq 1 ]; then bad=1; echo "FAIL $label: the commit landed, wanted refused"; return 1; fi
  if grep -q Traceback "$run/last.err"; then bad=1; echo "FAIL $label: the hook crashed, which is not a refusal"; return 1; fi
  if ! grep -qF -- "$pat" "$run/last.err"; then bad=1; echo "FAIL $label: stderr lacks '$pat'"; return 1; fi
  echo "ok   $label"
}
lands_with() { # pattern label cmd...: the commit lands and stderr names pattern
  pat="$1"; label="$2"; shift 2
  commit_err "$@"
  if [ "$landed" -ne 1 ]; then bad=1; echo "FAIL $label: the commit did not land (exit $got), wanted allowed"; return 1; fi
  if ! grep -qF -- "$pat" "$run/last.err"; then bad=1; echo "FAIL $label: stderr lacks '$pat'"; return 1; fi
  echo "ok   $label"
}
lands_without() { # pattern label cmd...: the commit lands and no output names pattern
  pat="$1"; label="$2"; shift 2
  commit_err "$@"
  if [ "$landed" -ne 1 ]; then bad=1; echo "FAIL $label: the commit did not land (exit $got), wanted allowed"; return 1; fi
  if grep -qF -- "$pat" "$run/last.out" "$run/last.err"; then bad=1; echo "FAIL $label: output names '$pat'"; return 1; fi
  echo "ok   $label"
}

# stale: the armed copy is behind main, so the commit is refused and the refusal names the re-arm command
fresh_mr mr-stale main; arm_hook "$neutral"; arm
printf 'x\n' >f.txt; git add -- f.txt
must_staged f.txt && refused_naming "sh githooks/main-ref/install.sh" "refused: armed copy behind main names the re-arm command" git commit -q -m c

# current: the armed copy equals main, so the commit lands
fresh_mr mr-current main; arm_hook "$repo/githooks/main-ref/reference-transaction"; arm
printf 'x\n' >f.txt; git add -- f.txt
must_staged f.txt && lands "ok: armed copy equal to main, the commit lands" git commit -q -m c

# no githooks/main-ref in the repo: the commit lands and no main-ref output appears
fresh mr-none; git switch -q -c feat; arm
printf 'x\n' >f.txt; git add -- f.txt
must_staged f.txt && lands_without "main-ref" "ok: no githooks/main-ref, the commit lands with no main-ref output" git commit -q -m c

# unknown: the repo has no main ref. The commit is allowed, because unknown is never clear and never broken, and stderr says so
fresh_mr mr-unknown trunk; arm_hook "$neutral"; arm
printf 'x\n' >f.txt; git add -- f.txt
must_staged f.txt && lands_with "unknown" "ok: no main ref, the commit lands and stderr says unknown" git commit -q -m c

# the escape hatch lets a stale copy through
fresh_mr mr-hatch main; arm_hook "$neutral"; arm
printf 'x\n' >f.txt; git add -- f.txt
must_staged f.txt && lands "ok: PRE_COMMIT_GUARD=off lets a stale copy through" env PRE_COMMIT_GUARD=off git commit -q -m c

# The check reads HEAD, not the working tree: an uncommitted edit to the hook excuses nothing.
fresh_mr mr-uncommitted main; arm_hook "$neutral"; arm
printf '# an uncommitted edit\n' >>githooks/main-ref/reference-transaction
printf 'x\n' >f.txt; git add -- f.txt
must_staged f.txt && refused_naming "sh githooks/main-ref/install.sh" "refused: uncommitted edit does not excuse a stale armed copy" git commit -q -m c

# A repo that vendors the installer from before --check: the pre-commit must not re-arm the copy
# through it. The copy stays byte-identical, the verdict is unknown, and unknown lets the commit land.
fresh_mr mr-old-install main "$repo/githooks/test_fixtures/main-ref-install-no-check.sh"; arm_hook "$neutral"; arm
printf 'x\n' >f.txt; git add -- f.txt
must_staged f.txt
armed_before="$(cksum <.git/hooks/reference-transaction)"
lands_with "unknown" "ok: vendored installer with no --check, the commit lands and stderr says unknown" git commit -q -m c
armed_after="$(cksum <.git/hooks/reference-transaction)"
if [ "$armed_before" = "$armed_after" ]; then echo "ok   pre-commit leaves the armed copy alone when the vendored installer has no --check"; else bad=1; echo "FAIL pre-commit re-armed the copy through a vendored installer that has no --check"; fi

# git rev-parse --show-toplevel fails inside the hook: the verdict is unknown and the commit is allowed.
# git prepends its exec path (/usr/lib/git-core) to PATH, so a PATH shim alone never runs. GIT_EXEC_PATH at a
# dir with no git binary puts the shim first. The shim logs each failing call: the case checks that the
# failure happened before it judges the verdict.
fresh_mr mr-toplevel main; arm_hook "$repo/githooks/main-ref/reference-transaction"; arm
shim="$run/shim-toplevel"; noexec="$run/shim-noexec"; mkdir "$shim" "$noexec"; real="$(command -v git)"
printf '#!/bin/sh\nif [ "$1" = rev-parse ] && [ "$2" = --show-toplevel ]; then echo hit >>"%s"; echo "fatal: simulated failure" >&2; exit 128; fi\nexec "%s" "$@"\n' "$run/toplevel.hits" "$real" >"$shim/git"
chmod +x "$shim/git"
printf 'x\n' >f.txt; git add -- f.txt
must_staged f.txt
commit_err env PATH="$shim:$PATH" GIT_EXEC_PATH="$noexec" "$shim/git" commit -q -m c
if [ ! -s "$run/toplevel.hits" ]; then bad=1; echo "FAIL setup: the shim never failed rev-parse --show-toplevel, so the case proves nothing"
elif [ "$landed" -ne 1 ]; then bad=1; echo "FAIL ok: rev-parse --show-toplevel fails: the commit did not land, wanted allowed"
elif grep -qF "unknown" "$run/last.err"; then echo "ok   ok: rev-parse --show-toplevel fails, the commit lands and stderr says unknown"
else bad=1; echo "FAIL ok: rev-parse --show-toplevel fails: stderr lacks 'unknown'"; fi

exit "$bad"

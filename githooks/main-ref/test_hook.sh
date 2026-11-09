#!/usr/bin/env bash
# Red run in a scratch clone: each way to move main locally is refused; a pull of an origin
# commit, a feature-branch commit and the escape hatch are allowed.
set -u
here="$(cd "$(dirname "$0")" && pwd)"
. "$here/../../lint/_test_git.sh"  # test-run signing opt-out (lint/_test_git.sh)
# One run folder per run, from the one home of the test-temp standard (lint/_test_temp.py).
repo="$(cd "$here/../.." && pwd)"
tmp="$(python3 -c 'import sys; sys.path.insert(0, sys.argv[1]); import _test_temp; print(_test_temp.run_folder())' "$repo/lint")" || { echo "FAIL setup: no run folder"; exit 1; }
trap 'rm -rf "$tmp"' EXIT
errf="$tmp/stderr"
cd "$tmp" || exit 1
export GIT_CONFIG_GLOBAL=/dev/null GIT_AUTHOR_NAME=t GIT_AUTHOR_EMAIL=t@t GIT_COMMITTER_NAME=t GIT_COMMITTER_EMAIL=t@t
git init -q --bare -b main origin.git
git clone -q origin.git w 2>/dev/null; cd w || exit 1
git commit -q --allow-empty -m one && git push -q origin main 2>/dev/null
bash "$here/install.sh"
bad=0
t() { # want label cmd...: ok is exit 0, refused any non-zero, stale exit 1, unknown exit 2; stderr to $errf
  want="$1"; label="$2"; shift 2
  "$@" >/dev/null 2>"$errf"; got=$?
  if { [ "$want" = ok ] && [ $got -eq 0 ]; } || { [ "$want" = refused ] && [ $got -ne 0 ]; } \
    || { [ "$want" = stale ] && [ $got -eq 1 ]; } || { [ "$want" = unknown ] && [ $got -eq 2 ]; }; then echo "ok   $label"
  else echo "FAIL $label (exit $got, wanted $want)"; bad=1; fi
}
git switch -q -c feat && git commit -q --allow-empty -m two
t ok      "commit on a feature branch"      git commit -q --allow-empty -m three
t refused "branch -f main to local commit"  git branch -f main feat
t refused "update-ref main to local commit" git update-ref refs/heads/main feat
git switch -q main
t refused "ff-merge into main"              git merge -q --ff-only feat
t refused "reset --hard main to local"      git reset -q --hard feat
t refused "commit while on main"            git commit -q --allow-empty -m direct
git switch -q feat
t refused "delete main"                     git branch -D main
t ok      "escape hatch"                    env MAIN_REF_GUARD=off git branch -f main feat
env MAIN_REF_GUARD=off git branch -f main origin/main
# a PR merges on GitHub: push feat there from a second clone, then pull here
cd "$tmp" && git clone -q origin.git w2 2>/dev/null && cd w2 && git commit -q --allow-empty -m remote && git push -q origin main 2>/dev/null
cd "$tmp/w" && git switch -q main && git fetch -q origin
t ok      "pull of a commit origin has"     git merge -q --ff-only origin/main
t ok      "gc leaves main alone"            git gc -q
# stale origin/main: a second clone pushes, this clone has not fetched, then fetch into main directly
git switch -q feat
cd "$tmp/w2" && git commit -q --allow-empty -m remote2 && git push -q origin main 2>/dev/null
cd "$tmp/w" || exit 1
t ok      "fetch origin main:main, origin/main stale" git fetch -q origin main:main
# a different remote branch whose name starts with "main" must not pass as origin/main
git switch -q feat
cd "$tmp/w2" && git switch -q -c main-x && git commit -q --allow-empty -m other && git push -q origin main-x 2>/dev/null
cd "$tmp/w" || exit 1
t refused "fetch origin main-x:main"             git fetch -q origin main-x:main
# another remote's main is not origin's, even one fast-forward of local main
git switch -q -c o main && git commit -q --allow-empty -m o && git switch -q feat
git init -q --bare -b main "$tmp/other.git" && git push -q "$tmp/other.git" o:main 2>/dev/null
git remote add other "$tmp/other.git"
t refused "fetch other main:main"                git fetch -q other main:main
# git 2.43 splits `fetch origin main:main` into two transactions, main's first; newer git batches
# them. Replay the split on any git: FETCH_HEAD written, origin/main stale, then main moves alone.
cd "$tmp/w2" && git switch -q main && git commit -q --allow-empty -m remote3 && git push -q origin main 2>/dev/null
cd "$tmp/w" || exit 1
stale="$(git rev-parse origin/main)"; git fetch -q origin; tip="$(git rev-parse origin/main)"
git update-ref refs/remotes/origin/main "$stale"
fh() { printf '%s\t\t%s\n' "$tip" "$1" >"$(git rev-parse --git-path FETCH_HEAD)"; }
fh "branch 'main-x' of $tmp/origin"
t refused "split fetch, FETCH_HEAD names main-x" git update-ref refs/heads/main "$tip"
fh "branch 'main' of $tmp/other"
t refused "split fetch, FETCH_HEAD names other"  git update-ref refs/heads/main "$tip"
fh "branch 'main' of $tmp/origin"
t refused "split fetch, FETCH_HEAD at another commit" git update-ref refs/heads/main feat
t ok      "split fetch, FETCH_HEAD names origin main" git update-ref refs/heads/main "$tip"
# install.sh placement: each case a fresh clone with a local commit on feat, then a guarded move
mk() { # name [hooksPath]: fresh clone at $tmp/name on feat
  cd "$tmp" && git clone -q origin.git "$1" 2>/dev/null && cd "$1" || exit 1
  [ -z "${2:-}" ] || git config core.hooksPath "$2"
  git switch -q -c feat && git commit -q --allow-empty -m local
}
mk rel .hooks; mkdir -p sub/deep
(cd sub/deep && bash "$here/install.sh")
t refused "relative hooksPath, installed from a subdir"  git branch -f main feat
mk relwt .hooks; git worktree add -q -b wtb "$tmp/relwt-2" 2>/dev/null
bash "$here/install.sh"
cd "$tmp/relwt-2" && git commit -q --allow-empty -m wt
t refused "relative hooksPath, move from a second worktree" git branch -f main wtb
mkdir -p "$tmp/home"
# SC2088: the config value must hold a literal "~/"; the installer, not the shell, expands it.
# shellcheck disable=SC2088
mk tilde '~/hk'
HOME="$tmp/home" bash "$here/install.sh"
t refused "~ hooksPath expands to HOME"          env HOME="$tmp/home" git branch -f main feat
mk dash
sh "$here/install.sh"
t refused "installer run under sh"               git branch -f main feat
# outside any repo: the installer fails and writes nothing (it once wrote /hooks)
mkdir "$tmp/norepo"; snap() { cksum /hooks/reference-transaction 2>/dev/null; }; before="$(snap)"
# SC2016: the inner sh expands $1 and $2, which carry the paths.
# shellcheck disable=SC2016
t refused "installer outside a repo"             env GIT_CEILING_DIRECTORIES="$tmp" sh -c 'cd "$1" && sh "$2"' _ "$tmp/norepo" "$here/install.sh"
# shellcheck disable=SC2016
t ok      "outside a repo writes nothing"        sh -c '[ -z "$(ls -A "$1")" ] && [ "$(cksum /hooks/reference-transaction 2>/dev/null)" = "$2" ]' _ "$tmp/norepo" "$before"
# --check: the armed copy against main. Each case clones a scratch source repo that holds a copy of
# this installer at githooks/main-ref/ on main, then runs that clone's copy with --check. Each case
# gets a fresh clone: an installer without --check re-arms, so state must not carry between cases.
says() { # label pattern: stderr of the last case contains pattern
  if grep -qF -- "$2" "$errf"; then echo "ok   $1"; else echo "FAIL $1: stderr lacks '$2'"; bad=1; fi
}
lacks() { # label pattern: stderr of the last case does not contain pattern
  if grep -qF -- "$2" "$errf"; then echo "FAIL $1: stderr contains '$2'"; bad=1; else echo "ok   $1"; fi
}
silent() { # label: stderr of the last case is empty
  if [ -s "$errf" ]; then echo "FAIL $1: stderr is not empty"; bad=1; else echo "ok   $1"; fi
}
chk="$tmp/chk"; mkdir "$chk"
src="$chk/src"; mkdir -p "$src/githooks/main-ref"
cp "$here/install.sh" "$here/reference-transaction" "$src/githooks/main-ref/"
git init -q -b main "$src" && git -C "$src" add -A && git -C "$src" commit -q -m "main: installer and hook"
nomain="$chk/nomain-src"; mkdir -p "$nomain/githooks/main-ref"
cp "$here/install.sh" "$here/reference-transaction" "$nomain/githooks/main-ref/"
git init -q -b trunk "$nomain" && git -C "$nomain" add -A && git -C "$nomain" commit -q -m "trunk only, no main"
neutral="$chk/neutral"; printf '#!/bin/sh\n# an older copy\nexit 0\n' >"$neutral"; chmod +x "$neutral"
main_hook="$src/githooks/main-ref/reference-transaction"
fresh_clone() { # source name: a clone of source in $chk/name; prints its path
  git clone -q "$1" "$chk/$2" 2>/dev/null && echo "$chk/$2"
}
arm_copy() { # dir file: put file where git reads the armed copy (the common .git hooks dir)
  mkdir -p "$1/.git/hooks" && cp "$2" "$1/.git/hooks/reference-transaction" && chmod +x "$1/.git/hooks/reference-transaction"
}
ckdir() { ( cd "$1" && sh githooks/main-ref/install.sh --check ); }

# current: the armed copy equals main. The old installer passes this too, so it is the green control.
c="$(fresh_clone "$src" chk-current)"; arm_copy "$c" "$main_hook"
t ok "--check: armed copy equal to main exits 0" ckdir "$c"
silent "--check: armed copy equal to main prints nothing on stderr"

# stale: the armed copy differs from main, and the source file is main
c="$(fresh_clone "$src" chk-stale)"; arm_copy "$c" "$neutral"
t stale "--check: armed copy behind main exits 1" ckdir "$c"
says "--check: stale copy names the re-arm command" "sh githooks/main-ref/install.sh"

# missing: no armed copy at all is stale too
c="$(fresh_clone "$src" chk-missing)"
[ ! -e "$c/.git/hooks/reference-transaction" ] || { bad=1; echo "FAIL setup: an armed copy exists in chk-missing"; }
t stale "--check: missing armed copy exits 1" ckdir "$c"
says "--check: missing copy names the re-arm command" "sh githooks/main-ref/install.sh"

# unknown: the source repo has no main ref, so nothing can be compared. Exit 2, never 0.
c="$(fresh_clone "$nomain" chk-nomain)"; arm_copy "$c" "$neutral"
t unknown "--check: no main ref exits 2" ckdir "$c"
says "--check: no main ref says unknown" "unknown"

# unknown: the armed path is a directory, so no copy can be read as a file
c="$(fresh_clone "$src" chk-unreadable)"; mkdir -p "$c/.git/hooks/reference-transaction"
t unknown "--check: armed copy that cannot be read as a file exits 2" ckdir "$c"
says "--check: unreadable armed copy says unknown" "unknown"

# branch editing the hook: the source differs from main, the armed copy differs too. Allowed, with a NOTE
# that does not tell the reader to rerun the installer, because that would arm unmerged work everywhere.
c="$(fresh_clone "$src" chk-editing)"; arm_copy "$c" "$neutral"
git -C "$c" switch -q -c edit-hook && printf '# a branch edit\n' >>"$c/githooks/main-ref/reference-transaction" && git -C "$c" commit -q -am "edit the hook on a branch"
t ok "--check: branch editing the hook exits 0" ckdir "$c"
says "--check: branch editing the hook prints a NOTE" "NOTE"
lacks "--check: branch editing the hook does not tell to rerun install.sh" "install.sh"

# relative core.hooksPath with two worktrees: one copy current, the other behind main. Exit 1.
c="$(fresh_clone "$src" chk-two-wt)"; git -C "$c" config core.hooksPath .hooks
git -C "$c" worktree add -q -b wt2 "$chk/chk-two-wt-2" main
mkdir -p "$c/.hooks" "$chk/chk-two-wt-2/.hooks"
cp "$main_hook" "$c/.hooks/reference-transaction"; cp "$neutral" "$chk/chk-two-wt-2/.hooks/reference-transaction"
t stale "--check: one of two worktrees behind main exits 1" ckdir "$c"
says "--check: stale worktree copy names the re-arm command" "sh githooks/main-ref/install.sh"

# --check writes nothing: the armed copy is byte-identical before and after a stale run
c="$(fresh_clone "$src" chk-nowrite)"; arm_copy "$c" "$neutral"
before="$(cksum <"$c/.git/hooks/reference-transaction")"
ckdir "$c" >/dev/null 2>&1
after="$(cksum <"$c/.git/hooks/reference-transaction")"
if [ "$before" = "$after" ]; then echo "ok   --check leaves the armed copy unchanged"; else echo "FAIL --check changed the armed copy"; bad=1; fi

# The check reads HEAD, not the working tree: an uncommitted edit to the hook excuses nothing.
c="$(fresh_clone "$src" chk-uncommitted)"; arm_copy "$c" "$neutral"
printf '# an uncommitted edit\n' >>"$c/githooks/main-ref/reference-transaction"
t stale "--check: uncommitted edit does not excuse a stale copy, exits 1" ckdir "$c"
says "--check: uncommitted edit, stale copy names the re-arm command" "sh githooks/main-ref/install.sh"

# A hooksPath in drive-letter form is absolute, so its copy is not read under the worktree.
# Linux has no drive letters; the message is the testable part: no worktree prefix in front of C:/.
c="$(fresh_clone "$src" chk-drive)"; git -C "$c" config core.hooksPath 'C:/x/hooks'
t stale "--check: drive-letter hooksPath with no copy exits 1" ckdir "$c"
lacks "--check: drive-letter hooksPath is not read under the worktree" "/C:/x/hooks"

# A hooks path under a regular file is a stat error: unknown (exit 2), never a stale copy (exit 1).
c="$(fresh_clone "$src" chk-stat)"; : >"$c/afile"; git -C "$c" config core.hooksPath "$c/afile/hooks"
t unknown "--check: hooks path under a regular file exits 2" ckdir "$c"
says "--check: hooks path under a regular file says unknown" "unknown"

# No local main but origin/main present: the verdict comes from origin/main.
c="$(fresh_clone "$src" chk-origin-stale)"; git -C "$c" switch -q -c away; git -C "$c" branch -q -D main
arm_copy "$c" "$neutral"
t stale "--check: no local main, stale copy exits 1 against origin/main" ckdir "$c"
says "--check: no local main, stale copy names the re-arm command" "sh githooks/main-ref/install.sh"
c="$(fresh_clone "$src" chk-origin-current)"; git -C "$c" switch -q -c away; git -C "$c" branch -q -D main
arm_copy "$c" "$main_hook"
t ok "--check: no local main, current copy exits 0 against origin/main" ckdir "$c"

rm -rf "$tmp"; exit $bad

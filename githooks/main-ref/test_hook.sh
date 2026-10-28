#!/usr/bin/env bash
# Red run in a scratch clone: each way to move main locally is refused; a pull of an origin
# commit, a feature-branch commit and the escape hatch are allowed.
set -u
here="$(cd "$(dirname "$0")" && pwd)"
tmp="$(mktemp -d)"; cd "$tmp" || exit 1
export GIT_CONFIG_GLOBAL=/dev/null GIT_AUTHOR_NAME=t GIT_AUTHOR_EMAIL=t@t GIT_COMMITTER_NAME=t GIT_COMMITTER_EMAIL=t@t
git init -q --bare -b main origin.git
git clone -q origin.git w 2>/dev/null; cd w || exit 1
git commit -q --allow-empty -m one && git push -q origin main 2>/dev/null
bash "$here/install.sh"
bad=0
t() { # want label cmd...
  want="$1"; label="$2"; shift 2
  "$@" >/dev/null 2>&1; got=$?
  if { [ "$want" = ok ] && [ $got -eq 0 ]; } || { [ "$want" = refused ] && [ $got -ne 0 ]; }; then echo "ok   $label"
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
rm -rf "$tmp"; exit $bad

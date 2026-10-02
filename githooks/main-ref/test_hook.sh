#!/usr/bin/env bash
# Red proof in a scratch clone: each way to move main locally is refused; a pull of an origin
# commit, a feature-branch commit and the escape hatch are allowed.
set -u
here="$(cd "$(dirname "$0")" && pwd)"
tmp="$(mktemp -d)"; cd "$tmp" || exit 1
export GIT_CONFIG_GLOBAL=/dev/null GIT_AUTHOR_NAME=t GIT_AUTHOR_EMAIL=t@t GIT_COMMITTER_NAME=t GIT_COMMITTER_EMAIL=t@t
git init -q --bare -b main origin.git
git clone -q origin.git w 2>/dev/null; cd w || exit 1
git commit -q --allow-empty -m one && git push -q origin main 2>/dev/null
bash "$here/install.sh" >/dev/null
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
rm -rf "$tmp"; exit $bad

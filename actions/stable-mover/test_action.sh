#!/usr/bin/env bash
# The stable mover (actions/stable-mover/run.sh) moves stable to a green main head, fast-forward only. It leaves
# stable alone on a failed run, on a head that does not descend from stable, on a head that origin's main lacks,
# and on a head behind stable (exit 0). It creates stable when origin has none, and exits 2 (UNKNOWN) when origin
# cannot be read. Run in a checkout whose origin is the fixture, with HEAD_SHA and RUN_CONCLUSION set.
set -u
here="$(cd "$(dirname "$0")" && pwd)"
root="$(cd "$here/../.." && pwd)"
mover="$here/run.sh"
fails=0
ok() { echo "ok   $1"; }
fail() { echo "FAIL $1"; fails=$((fails + 1)); }

# One run folder per test run (test-temp-standard): lint/_test_temp.py makes it under the repo's one temp root.
work=$(python3 -I -c 'import sys; sys.path.insert(0, sys.argv[1]); import _test_temp; print(_test_temp.run_folder())' "$root/lint") || work=""
[ -n "$work" ] || { echo "FAIL - run folder: lint/_test_temp.py made no run folder"; exit 1; }
trap 'rm -rf "$work"' EXIT

export GIT_CONFIG_GLOBAL=/dev/null GIT_CONFIG_NOSYSTEM=1
export GIT_AUTHOR_NAME=test GIT_AUTHOR_EMAIL=test@example.invalid
export GIT_COMMITTER_NAME=test GIT_COMMITTER_EMAIL=test@example.invalid

# Seed: base, then green (main's head, a child of base), then diverged (a child of base that green does not contain).
seed="$work/seed"
git init -q -b main "$seed" || { echo "FAIL - fixture: git init of the seed failed"; exit 1; }
commit() { # commit <file> <text>: one commit on the seed's checked-out branch, prints its sha
  printf '%s\n' "$2" > "$seed/$1"
  git -C "$seed" add "$1" && git -C "$seed" commit -q -m "$2" && git -C "$seed" rev-parse HEAD
}
base=$(commit f base) || { echo "FAIL - fixture: seed commit failed"; exit 1; }
green=$(commit f green) || { echo "FAIL - fixture: seed commit failed"; exit 1; }
git -C "$seed" checkout -q -b side "$base" || { echo "FAIL - fixture: seed branch failed"; exit 1; }
diverged=$(commit g diverged) || { echo "FAIL - fixture: seed commit failed"; exit 1; }
git -C "$seed" checkout -q -b ahead "$green" || { echo "FAIL - fixture: seed branch failed"; exit 1; }
ahead=$(commit f ahead) || { echo "FAIL - fixture: seed commit failed"; exit 1; }

origin_sha() { # origin_sha <origin dir> <branch>: the sha the fixture origin holds for the branch, or none
  git --git-dir="$1" rev-parse -q --verify "refs/heads/$2" 2>/dev/null || echo none
}
control() { # control <label> <got> <want>: the fixture is set up as the case says before the mover runs
  if [ "$2" = "$3" ]; then ok "control: $1"; else fail "control: $1 (fixture holds $2, wanted $3)"; fi
}
# scenario <name> <stable commit | none> [<side commit>]: sets origin and ws. The origin's main is the green head; its
# stable is the given commit, or absent for none. A side commit becomes a branch of its own, so a checkout can hold a
# head that main lacks. The checkout ws is a clone of that origin, so its origin is the fixture.
scenario() {
  origin="$work/$1.git"
  ws="$work/$1.ws"
  git init -q --bare -b main "$origin" || { echo "FAIL - fixture $1: init of the origin failed"; exit 1; }
  refs=("$green:refs/heads/main")
  [ "$2" = none ] || refs+=("$2:refs/heads/stable")
  [ -z "${3:-}" ] || refs+=("$3:refs/heads/side")
  git -C "$seed" push -q "$origin" "${refs[@]}" \
    || { echo "FAIL - fixture $1: push to the origin failed"; exit 1; }
  git clone -q "$origin" "$ws" || { echo "FAIL - fixture $1: clone of the origin failed"; exit 1; }
}
# run_mover <checkout> <head> <conclusion>: runs the mover as the workflow does. Only the stable ref is read after it.
# It leaves the mover's exit code in mover_rc.
run_mover() {
  (cd "$1" && HEAD_SHA="$2" RUN_CONCLUSION="$3" bash "$mover") >"$work/mover.log" 2>&1
  mover_rc=$?
}

scenario success "$base"
control "a green run: the fixture stable is the old base" "$(origin_sha "$origin" stable)" "$base"
control "a green run: the fixture main is the green head" "$(origin_sha "$origin" main)" "$green"
run_mover "$ws" "$green" success
got=$(origin_sha "$origin" stable)
if [ "$got" = "$green" ]; then ok "a green run fast-forwards stable to the green head"
else fail "green run: stable did not move to the green head (stable at $got, wanted $green)"; fi

scenario failed "$base"
control "a failed run: the fixture stable is the old base" "$(origin_sha "$origin" stable)" "$base"
control "a failed run: the fixture main is the green head" "$(origin_sha "$origin" main)" "$green"
run_mover "$ws" "$green" failure
got=$(origin_sha "$origin" stable)
if [ "$got" = "$base" ]; then ok "a failed run leaves stable where it was"
else fail "failed run: stable moved on a failed run (stable at $got, wanted $base)"; fi

scenario diverged "$diverged"
control "a non-descendant: the fixture stable is the diverged commit" "$(origin_sha "$origin" stable)" "$diverged"
control "a non-descendant: the fixture main is the green head" "$(origin_sha "$origin" main)" "$green"
run_mover "$ws" "$green" success
got=$(origin_sha "$origin" stable)
if [ "$got" = "$diverged" ]; then ok "a head that does not descend from stable is refused"
else fail "non-descendant: stable moved to a head that does not descend from it (stable at $got, wanted $diverged)"; fi

# A green head behind stable (an out-of-order green run): stable stays where it is, and the mover exits 0.
scenario behind "$ahead"
control "a green run behind stable: the fixture stable is the ahead commit" "$(origin_sha "$origin" stable)" "$ahead"
control "a green run behind stable: the fixture main is the green head" "$(origin_sha "$origin" main)" "$green"
run_mover "$ws" "$green" success
got=$(origin_sha "$origin" stable)
if [ "$got" = "$ahead" ]; then ok "a green run behind stable leaves stable where it is"
else fail "behind stable: stable moved backwards on a green run (stable at $got, wanted $ahead)"; fi
if [ "$mover_rc" -eq 0 ]; then ok "a green run behind stable exits 0"
else fail "behind stable: the mover exited $mover_rc, wanted 0"; fi

# No stable yet (the first live run): the mover creates stable at the green head.
scenario absent none
control "a green run with no stable: the fixture has no stable" "$(origin_sha "$origin" stable)" none
control "a green run with no stable: the fixture main is the green head" "$(origin_sha "$origin" main)" "$green"
run_mover "$ws" "$green" success
got=$(origin_sha "$origin" stable)
if [ "$got" = "$green" ]; then ok "a green run with no stable creates stable at the green head"
else fail "absent stable: stable was not created at the green head (stable at $got, wanted $green)"; fi

# A green head that main lacks. It descends from stable, so only the main check refuses it.
scenario offmain "$base" "$diverged"
control "a head off main: the fixture stable is the old base" "$(origin_sha "$origin" stable)" "$base"
control "a head off main: the fixture main is the green head" "$(origin_sha "$origin" main)" "$green"
if git --git-dir="$origin" merge-base --is-ancestor "$diverged" refs/heads/main; then on_main=yes; else on_main=no; fi
control "a head off main: origin's main does not hold the head" "$on_main" no
run_mover "$ws" "$diverged" success
got=$(origin_sha "$origin" stable)
if [ "$got" = "$base" ]; then ok "a green run whose head main lacks leaves stable alone"
else fail "head off main: stable moved to a head that origin's main does not hold (stable at $got, wanted $base)"; fi

# An origin that cannot be read: the mover fails closed with exit 2, and does not read stable as absent.
scenario unreadable "$base"
git -C "$ws" remote set-url origin "$work/gone.git"
control "an unreadable origin: the origin path is missing" "$(test -e "$work/gone.git" && echo present || echo missing)" missing
run_mover "$ws" "$green" success
if [ "$mover_rc" -eq 2 ]; then ok "an unreadable origin exits 2 (UNKNOWN)"
else fail "unreadable origin: the mover exited $mover_rc, wanted 2 (UNKNOWN)"; fi

if [ "$fails" -eq 0 ]; then echo "stable-mover: all cases pass"; exit 0; fi
echo "stable-mover: $fails failed"
exit 1

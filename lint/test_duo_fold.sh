#!/usr/bin/env bash
# Tests for bin/duo-fold: the iPhone Duo fold through hinge, and the angle read-back that checks the fold. Ported from the
# script cases of home's Node test for the fold script; its screen-check and comment-scanner cases stay in home.
# It is meant to run under /bin/bash (3.2) and under bash on PATH.
# DUO_FOLD=PATH picks the tool; the default is bin/duo-fold in this repo. A red run points it at a stub.
# The tool runs under this suite's own shell ("$BASH"), so /bin/bash 3.2 runs the tool under 3.2.
# No real hinge, simctl, xcrun or git is touched. uname prints $STUB_ARCH for -m. git logs its calls, and a clone makes
# the tree a fetch needs. The hinge stub logs its calls, prints $STUB_MOVE_OUT on a move and $STUB_ANGLE on get.
# Temp files live in one run folder from lint/_test_temp.py (decision test-temp-standard). Its sweep is proved once, in
# lint/test_check_agent_models.py.
# The tool's contract, as these cases hold it:
#  - `duo-fold <udid> <folded|open>`: folded runs hinge close (target 0), open runs hinge open (target 180). Then hinge get
#    reads the angle back. A reading within 0.5 of the target passes. Exit 0 passes, 1 refuses, 64 is wrong arguments.
#  - A refusal writes a line that starts `duo-fold:` on stderr. The usage line names `duo-fold <udid> <folded|open>`.
#  - A move that exits non-zero is noted on stderr, the angle is read anyway, and nothing is retried.
#  - A Mac that is not arm64 is refused before hinge is fetched or run.
#  - With HINGE unset, the tool clones hinge at DUO_FOLD_HINGE_SHA into DUO_FOLD_WORK, checks that sha out, and uses
#    that tool. A failed clone or checkout is refused before any hinge call.
#  - DUO_FOLD_LOG takes hinge's output. Unset, hinge's output goes to stderr.
#  - Sourced, the tool defines duo_fold, duo_fold_fetch_hinge and the DUO_FOLD_* constants, and runs nothing.
# The one deliberate change from the pinned script: the usage line names `duo-fold`, the shared command's name.
# The last line is the tally: passed and failed counts, then the failing case names.
set -uo pipefail
root=$(cd "$(dirname "$0")/.." && pwd)
DUO_FOLD=${DUO_FOLD:-$root/bin/duo-fold}
UDID=7F6A2C1E-3B4D-4E5F-8A9B-0C1D2E3F4A5B
# Inherited settings never reach a case. Each case sets what it needs, and these names start unset.
unset HINGE DUO_FOLD_LOG DUO_FOLD_WORK DUO_FOLD_HINGE_REPO DUO_FOLD_HINGE_SHA
base_path=$PATH
pass_n=0; fail_n=0; failed=; why=
rc=0; out=; err=; cdir=; pin_repo=; pin_sha=

# The run folder: one per run, under the one temp root (lint/_test_temp.py). Teardown removes it.
work=$(python3 -I -c 'import sys; sys.path.insert(0, sys.argv[1]); import _test_temp; print(_test_temp.run_folder())' "$root/lint") || exit 1
[ -n "$work" ] || exit 1
trap 'rm -rf "$work"' EXIT
stubs=$work/stubs
mkdir -p "$stubs" || exit 1

# The stubs. uname answers -m with $STUB_ARCH. git logs its call. A clone makes the folder a fetch looks for: a .git
# folder and the hinge tool, a copy of hinge-stub. STUB_GIT_RC and STUB_GIT_CHECKOUT_RC make the clone or checkout fail.
cat > "$stubs/uname" <<'SH'
#!/bin/sh
if [ "$1" = -m ]; then printf '%s\n' "$STUB_ARCH"; else printf 'Linux\n'; fi
SH
cat > "$stubs/git" <<'SH'
#!/bin/sh
printf '%s\n' "$*" >> "$STUB_GIT_LOG"
case " $* " in
  *" clone "*)
    [ "${STUB_GIT_RC:-0}" = 0 ] || exit "$STUB_GIT_RC"
    for dest; do :; done
    mkdir -p "$dest/.git" "$dest/skills/hinge/scripts" || exit 1
    cp "$STUB_HINGE_SRC" "$dest/skills/hinge/scripts/hinge" || exit 1
    chmod +x "$dest/skills/hinge/scripts/hinge" || exit 1 ;;
  *" checkout "*) exit "${STUB_GIT_CHECKOUT_RC:-0}" ;;
esac
exit 0
SH
# The hinge stub: logs its arguments. A move prints $STUB_MOVE_OUT and exits $STUB_MOVE_EXIT. A get prints
# $STUB_GET_ERR on stderr, prints $STUB_ANGLE on stdout and exits $STUB_GET_EXIT.
cat > "$stubs/hinge-stub" <<'SH'
#!/bin/sh
printf '%s\n' "$*" >> "$STUB_LOG"
case "$3" in
  get)
    if [ -n "${STUB_GET_ERR:-}" ]; then echo "$STUB_GET_ERR" >&2; fi
    if [ -n "${STUB_ANGLE:-}" ]; then printf '%b\n' "$STUB_ANGLE"; fi
    exit "${STUB_GET_EXIT:-0}" ;;
  close|open)
    if [ -n "${STUB_MOVE_OUT:-}" ]; then echo "$STUB_MOVE_OUT"; fi
    exit "${STUB_MOVE_EXIT:-0}" ;;
esac
exit 0
SH
chmod +x "$stubs/uname" "$stubs/git" "$stubs/hinge-stub" || exit 1

# ---- harness: a case runs its checks in order. The first failed check names the case's failure. ----
case_pass() { printf 'PASS %s\n' "$1"; pass_n=$((pass_n + 1)); }
case_fail() { printf 'FAIL %s: %s\n' "$1" "$2"; fail_n=$((fail_n + 1)); failed=${failed:+$failed, }$1; }
end_case() { if [ -z "$why" ]; then case_pass "$1"; else case_fail "$1" "$why"; fi; why=; }
# need MSG CMD...: when no earlier check failed, runs CMD. A failure sets the case's failure to MSG.
need() { local msg=$1; shift; [ -n "$why" ] && return 0; "$@" || why=$msg; }

# setup: a fresh case folder, and the environment every case starts from. The stubs come first on PATH, HINGE is the
# hinge stub, uname says arm64, the fetch folder is in the case folder, and no fault is set. A case sets only what it tests.
setup() {
  cdir=$work/case
  rm -rf "$cdir"
  mkdir -p "$cdir/home" "$cdir/work" || exit 1
  : > "$cdir/hinge.log"
  : > "$cdir/git.log"
  why=
  PATH="$stubs:$base_path"; export PATH
  export HOME="$cdir/home" STUB_LOG="$cdir/hinge.log" STUB_GIT_LOG="$cdir/git.log" STUB_ARCH=arm64
  export STUB_HINGE_SRC="$stubs/hinge-stub" HINGE="$stubs/hinge-stub" DUO_FOLD_WORK="$cdir/work"
  unset STUB_ANGLE STUB_GET_EXIT STUB_MOVE_EXIT STUB_MOVE_OUT STUB_GET_ERR STUB_GIT_RC STUB_GIT_CHECKOUT_RC DUO_FOLD_LOG
}
# tool_present: the first check of every case. With no tool file, each case fails on this line and nothing else.
tool_present() { need "no tool file at $DUO_FOLD" test -f "$DUO_FOLD"; }
# run_tool ARGS...: runs the tool under the case's environment. rc is its exit code, out its stdout, err its stderr.
run_tool() {
  out=$cdir/out
  err=$cdir/err
  "$BASH" "$DUO_FOLD" "$@" < /dev/null > "$out" 2> "$err"
  rc=$?
}
# calls_are LINE...: the hinge calls logged, in order, are exactly these lines. With no line, there are no calls.
calls_are() { [ "$(cat "$cdir/hinge.log")" = "$(printf '%s\n' "$@")" ]; }
no_hinge_call() { [ ! -s "$cdir/hinge.log" ]; }
no_git_call() { [ ! -s "$cdir/git.log" ]; }
# first_refusal: the first stderr line starts with duo-fold:.
first_refusal() { case $(sed -n 1p "$err") in duo-fold:*) return 0 ;; esac; return 1; }
# refusal_names TEXT: a duo-fold: line on stderr holds TEXT.
refusal_names() { sed -n '/^duo-fold:/p' "$err" > "$cdir/refusals"; grep -Fq -- "$1" "$cdir/refusals"; }
err_has() { grep -Fq -- "$1" "$err"; }
err_lacks() { ! grep -Fq -- "$1" "$err"; }
# read_pin: sets pin_repo and pin_sha from the pin the tool names, read by sourcing the tool. No case copies the pin.
read_pin() {
  local line
  line=$("$BASH" -c 'source "$1" && printf "%s %s" "$DUO_FOLD_HINGE_REPO" "$DUO_FOLD_HINGE_SHA"' bash "$DUO_FOLD" 2>/dev/null) || return 1
  pin_repo=${line% *}
  pin_sha=${line##* }
  [ -n "$pin_repo" ] && [ -n "$pin_sha" ]
}
sha_ok() { [ "${#1}" -eq 40 ] || return 1; case $1 in *[!0-9a-f]*) return 1 ;; esac; return 0; }
repo_ok() { case $1 in https://github.com/*/hinge) return 0 ;; esac; return 1; }
# git_count_is_two: the tool ran git twice, the clone and then the checkout, and no more.
git_count_is_two() { [ "$(wc -l < "$cdir/git.log" | tr -d ' ')" -eq 2 ]; }
# first_git_is_clone: the first git call clones the pinned repo into the fetch folder.
first_git_is_clone() {
  case $(sed -n 1p "$cdir/git.log") in clone\ *"$pin_repo"*"$DUO_FOLD_WORK/hinge"*) return 0 ;; esac
  return 1
}
# second_git_is_checkout: the second git call checks out the pinned sha.
second_git_is_checkout() {
  case $(sed -n 2p "$cdir/git.log") in *checkout*"$pin_sha"*) return 0 ;; esac
  return 1
}

# pass_case NAME POSTURE ANGLE: the fold moves, reads ANGLE back and passes, with the hinge calls it makes.
pass_case() {
  local move=open
  if [ "$2" = folded ]; then move=close; fi
  setup; tool_present
  export STUB_ANGLE="$3"
  run_tool "$UDID" "$2"
  need "hinge calls are not the move then the read-back" calls_are "-d $UDID $move" "-d $UDID get"
  need "exit is $rc, not 0" test "$rc" -eq 0
  end_case "$1"
}
# refuse_case NAME POSTURE ANGLE TEXT: the fold moves, reads ANGLE back and is refused. The refusal names the udid and
# TEXT. An empty TEXT names no reading.
refuse_case() {
  local move=open
  if [ "$2" = folded ]; then move=close; fi
  setup; tool_present
  export STUB_ANGLE="$3"
  run_tool "$UDID" "$2"
  need "hinge calls are not the move then the read-back" calls_are "-d $UDID $move" "-d $UDID get"
  need "exit is $rc, not 1" test "$rc" -eq 1
  need "the refusal line does not start duo-fold:" first_refusal
  need "the refusal does not name the udid" err_has "$UDID"
  if [ -n "$4" ]; then need "the refusal does not name the reading $4" err_has "$4"; fi
  end_case "$1"
}
# args_case NAME ARGS...: the tool exits 64, and hinge is not called.
args_case() {
  local name=$1
  shift
  setup; tool_present
  run_tool "$@"
  need "exit is $rc, not 64" test "$rc" -eq 64
  need "hinge was called on wrong arguments" no_hinge_call
  end_case "$name"
}

# ---- the tool is a command: it is executable, as bin/ holds it ----
setup; tool_present
need "the tool is not executable" test -x "$DUO_FOLD"
end_case "the tool is executable as a command"

# ---- angle: a reading within 0.5 of the target passes ----
pass_case "folded reads 0.0 and passes" folded 0.0
pass_case "folded reads 0 and passes" folded 0
pass_case "folded reads -0.0 and passes" folded -0.0
pass_case "folded reads 0.4 and passes" folded 0.4
pass_case "folded reads 0.5 and passes at the tolerance" folded 0.5
pass_case "open reads 180.0 and passes" open 180.0
pass_case "open reads 179.6 and passes" open 179.6
pass_case "open reads 179.5 and passes at the tolerance" open 179.5
pass_case "open reads a blank-padded 180.0 and passes" open '  180.0  '

# ---- angle: a reading off the target, or not one number, is refused ----
refuse_case "folded reads 180.0 and is refused" folded 180.0 180.0
refuse_case "folded reads 90.0 and is refused" folded 90.0 90.0
refuse_case "folded reads 0.6 and is refused" folded 0.6 0.6
refuse_case "folded reads two lines and is refused" folded '0.0\n0.0' ''
refuse_case "folded reads a blank first line and is refused" folded '\n0.0' ''
refuse_case "folded reads text and is refused" folded udid-0 udid-0
refuse_case "folded reads nothing and is refused" folded '' ''
refuse_case "open reads 0.0 and is refused" open 0.0 0.0
refuse_case "open reads 179.4 and is refused" open 179.4 179.4

# ---- get and move faults: a get that fails is refused; a move that fails is noted, read back, and not retried ----
setup; tool_present
export STUB_ANGLE=0.0 STUB_GET_EXIT=1
run_tool "$UDID" folded
need "hinge calls are not close then get" calls_are "-d $UDID close" "-d $UDID get"
need "exit is $rc, not 1" test "$rc" -eq 1
need "the refusal line does not start duo-fold:" first_refusal
need "the refusal does not name the udid" err_has "$UDID"
end_case "a get that exits 1 is refused"

setup; tool_present
export STUB_ANGLE=0.0 STUB_MOVE_EXIT=1
run_tool "$UDID" folded
need "hinge calls are not close then get, with no retry" calls_are "-d $UDID close" "-d $UDID get"
need "exit is $rc, not 0" test "$rc" -eq 0
end_case "a close that exits 1 and reads 0.0 back passes with no retry"

setup; tool_present
export STUB_ANGLE=180.0 STUB_MOVE_EXIT=1
run_tool "$UDID" open
need "hinge calls are not open then get, with no retry" calls_are "-d $UDID open" "-d $UDID get"
need "exit is $rc, not 0" test "$rc" -eq 0
end_case "an open that exits 1 and reads 180.0 back passes with no retry"

setup; tool_present
export STUB_ANGLE=180.0 STUB_MOVE_EXIT=1
run_tool "$UDID" folded
need "hinge calls are not close then get, with no retry" calls_are "-d $UDID close" "-d $UDID get"
need "exit is $rc, not 1" test "$rc" -eq 1
need "no duo-fold: line names the reading 180.0" refusal_names 180.0
need "the refusal does not name the udid" err_has "$UDID"
end_case "a close that exits 1 and reads 180.0 back is refused, naming the reading"

# ---- a Mac that is not arm64 is refused before hinge is fetched or run ----
setup; tool_present
unset HINGE
export STUB_ARCH=x86_64
run_tool "$UDID" folded
need "exit is $rc, not 1" test "$rc" -eq 1
need "the refusal line does not start duo-fold:" first_refusal
need "hinge was fetched on a Mac that is not arm64" no_git_call
need "hinge was called on a Mac that is not arm64" no_hinge_call
end_case "a Mac that is not arm64 is refused before hinge is fetched or run"

# ---- wrong arguments exit 64 before hinge runs ----
args_case "no arguments exit 64"
args_case "one argument exits 64" "$UDID"
args_case "a posture that is not folded or open exits 64" "$UDID" half
args_case "three arguments exit 64" "$UDID" folded extra

setup; tool_present
run_tool
need "exit is $rc, not 64" test "$rc" -eq 64
need "the usage line does not name duo-fold <udid> <folded|open>" grep -Fq 'usage: duo-fold <udid> <folded|open>' "$err"
end_case "the usage line names duo-fold <udid> <folded|open>"

# ---- sourcing: the tool defines its functions and constants and runs nothing ----
setup; tool_present
out=$cdir/out; err=$cdir/err
"$BASH" -c 'source "$1"; type duo_fold >/dev/null 2>&1 && type duo_fold_fetch_hinge >/dev/null 2>&1' bash "$DUO_FOLD" < /dev/null > "$out" 2> "$err"
rc=$?
need "sourcing did not define duo_fold and duo_fold_fetch_hinge (exit $rc)" test "$rc" -eq 0
need "sourcing printed to stdout" test ! -s "$out"
need "sourcing called hinge" no_hinge_call
need "sourcing fetched hinge" no_git_call
end_case "sourcing defines duo_fold and runs nothing"

setup; tool_present
need "the tool does not name a hinge repo and sha when sourced" read_pin
need "the pinned sha is not 40 lowercase hex digits" sha_ok "$pin_sha"
need "the pinned repo is not a github.com URL ending in /hinge" repo_ok "$pin_repo"
end_case "the hinge pin is a github repo and a 40-hex sha"

setup; tool_present
out=$cdir/out; err=$cdir/err
export STUB_ANGLE=180.0
"$BASH" -c 'source "$1"; duo_fold "$2" folded; echo "after=$?"' bash "$DUO_FOLD" "$UDID" < /dev/null > "$out" 2> "$err"
need "duo_fold did not reach hinge close then get" calls_are "-d $UDID close" "-d $UDID get"
need "duo_fold did not return 1 to its caller" grep -Fxq 'after=1' "$out"
end_case "a refused duo_fold returns 1 to its caller, which goes on"

# ---- the fetch: with HINGE unset, the pinned hinge is cloned into DUO_FOLD_WORK, checked out and used ----
setup; tool_present
need "the tool does not name a hinge repo and sha when sourced" read_pin
unset HINGE
export STUB_ANGLE=0.0
run_tool "$UDID" folded
need "exit is $rc, not 0" test "$rc" -eq 0
need "git was not called twice, clone then checkout" git_count_is_two
need "the first git call is not the clone of the pinned repo into DUO_FOLD_WORK" first_git_is_clone
need "the second git call is not the checkout of the pinned sha" second_git_is_checkout
need "hinge calls are not close then get on the fetched hinge" calls_are "-d $UDID close" "-d $UDID get"
end_case "with HINGE unset the pinned hinge is fetched, checked out and used"

setup; tool_present
need "the tool does not name a hinge repo and sha when sourced" read_pin
unset HINGE
export STUB_GIT_RC=1
run_tool "$UDID" folded
need "exit is $rc, not 1" test "$rc" -eq 1
need "the refusal line does not start duo-fold:" first_refusal
need "the refusal does not name the udid" err_has "$UDID"
need "the clone was not the first git call" first_git_is_clone
need "hinge was called after a failed clone" no_hinge_call
end_case "a failed clone is refused with exit 1 and no hinge call"

setup; tool_present
need "the tool does not name a hinge repo and sha when sourced" read_pin
unset HINGE
export STUB_GIT_CHECKOUT_RC=1 STUB_ANGLE=0.0
run_tool "$UDID" folded
need "exit is $rc, not 1" test "$rc" -eq 1
need "the refusal line does not start duo-fold:" first_refusal
need "the clone was not the first git call" first_git_is_clone
need "the checkout was not the second git call" second_git_is_checkout
need "hinge was called after a failed checkout" no_hinge_call
end_case "a failed checkout is refused with exit 1 and no hinge call"

setup; tool_present
export STUB_ANGLE=0.0
run_tool "$UDID" folded
need "hinge calls are not close then get" calls_are "-d $UDID close" "-d $UDID get"
need "exit is $rc, not 0" test "$rc" -eq 0
need "git was called although HINGE is set" no_git_call
end_case "a HINGE that is set is used as given, with no fetch"

# ---- DUO_FOLD_LOG: hinge's output goes to the file when it is set, and to stderr when it is unset ----
setup; tool_present
export STUB_ANGLE=0.0 STUB_MOVE_OUT=moved-marker STUB_GET_ERR=get-marker
export DUO_FOLD_LOG="$cdir/hinge-out.log"
: > "$DUO_FOLD_LOG"
run_tool "$UDID" folded
need "exit is $rc, not 0" test "$rc" -eq 0
need "the log file does not hold hinge's move output" grep -Fq moved-marker "$DUO_FOLD_LOG"
need "the log file does not hold hinge's get output" grep -Fq get-marker "$DUO_FOLD_LOG"
need "hinge move output reached stderr" err_lacks moved-marker
need "hinge get output reached stderr" err_lacks get-marker
need "hinge output reached stdout" test ! -s "$out"
end_case "DUO_FOLD_LOG takes hinge's output"

setup; tool_present
export STUB_ANGLE=0.0 STUB_MOVE_OUT=moved-marker STUB_GET_ERR=get-marker
run_tool "$UDID" folded
need "exit is $rc, not 0" test "$rc" -eq 0
need "hinge move output did not reach stderr" err_has moved-marker
need "hinge get output did not reach stderr" err_has get-marker
need "hinge output reached stdout" test ! -s "$out"
end_case "with DUO_FOLD_LOG unset, hinge's output goes to stderr"

echo "duo-fold suite: $pass_n passed, $fail_n failed${failed:+: $failed}"
if [ "$fail_n" -eq 0 ]; then exit 0; fi
exit 1

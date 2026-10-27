#!/usr/bin/env bash
# Tests for bin/sim-test. CI runs this under /bin/bash (3.2) and under bash on PATH (shell-macos job).
# SIM_TEST=PATH picks the script under test; the default is bin/sim-test in this repo. A red proof points it at a stub.
# No real simulator or xcodebuild is touched. xcrun, xcodebuild, top and mkdir are PATH shims, and the tool runs under
# a temp HOME. Temp files follow decisions/test-temp-standard.md: one run folder <pid>-<UUID> under one temp root,
# and the first request of a run sweeps siblings older than a day.
# The tool's contract:
#  - One booted iPhone is reused by UDID: no boot, no shutdown. An iPad is not an iPhone. With two, the first is used.
#  - None booted: boot the shared iPhone 18 Pro, test, then shut down that simulator, also on failure, INT and TERM.
#  - A failed boot exits non-zero and runs no xcodebuild.
#  - The exit code is xcodebuild's. The tool takes no lock and runs no top.
# The last line is the tally: passed and failed counts, then the failing case names.
set -uo pipefail
root=$(cd "$(dirname "$0")/.." && pwd)
script=${SIM_TEST:-$root/bin/sim-test}
fail=0; pass_n=0; fail_n=0; failed=
why=
case_pass() { echo "PASS $1"; pass_n=$((pass_n + 1)); }
case_fail() { echo "FAIL $1: $2"; fail=1; fail_n=$((fail_n + 1)); failed=${failed:+$failed, }$1; }
end_case() { if [[ -z $why ]]; then case_pass "$1"; else case_fail "$1" "$why"; fi; why=; }
# need MSG CMD...: the first failed need names the case's failure.
need() { local msg=$1; shift; [[ -n $why ]] && return 0; "$@" || why=$msg; }

# ---- run folder (decisions/test-temp-standard.md) ----
tmp_root=${TMPDIR:-/tmp}/claude-settings-tests
# sweep_runs ROOT: remove sibling run folders named <pid>-<UUID> that are older than a day. Newer ones stay: a parallel run owns them.
sweep_runs() {
  local d n
  for d in "$1"/*-*; do
    [[ -d $d && ! -L $d ]] || continue
    n=${d##*/}
    [[ $n =~ ^[0-9]+-[0-9a-f-]+$ ]] || continue
    [[ -z $(find "$d" -prune -mmin +1440) ]] || rm -rf "$d"
  done
}
mkdir -p "$tmp_root" || exit 1
sweep_runs "$tmp_root"
uuid=$( (uuidgen 2>/dev/null || cat /proc/sys/kernel/random/uuid) | tr 'A-Z' 'a-z'); [[ -n $uuid ]] || exit 1
work=$tmp_root/$$-$uuid
mkdir "$work" || exit 1
trap 'rm -rf "$work"' EXIT

stubs=$work/stubs; mkdir -p "$stubs" "$work/home"
calls=$work/calls; booted_file=$work/booted
export RUN=$work PATH="$stubs:$PATH"
SHARED=8787FE1C-48CC-4213-9B5C-8605AFE7F9B3
OTHER=AAAAAAAA-0000-4000-8000-000000000001
THIRD=BBBBBBBB-0000-4000-8000-000000000002
DEST="xcodebuild test -scheme X -destination platform=iOS Simulator,id="

# xcodebuild: logs its call, then exits $STUB_RC. With STUB_HANG set, it marks a start file and waits for a signal.
cat > "$stubs/xcodebuild" <<'SH'
#!/bin/sh
echo "xcodebuild $*" >> "$RUN/calls"
if [ -n "${STUB_HANG:-}" ]; then : > "$RUN/started"; sleep 30; fi
exit ${STUB_RC:-0}
SH
# xcrun: simctl only. $RUN/booted holds the "Booted" lines of `simctl list devices booted`.
cat > "$stubs/xcrun" <<'SH'
#!/bin/sh
[ "$1" = simctl ] || exit 99
shift
echo "simctl $*" >> "$RUN/calls"
case "$1" in
  list) echo "== Devices =="; echo "-- iOS 27.0 --"; cat "$RUN/booted" ;;
  boot) [ -n "${STUB_BOOT_RC:-}" ] && exit "$STUB_BOOT_RC"; echo "    iPhone 18 Pro ($2) (Booted) " > "$RUN/booted" ;;
  shutdown) : > "$RUN/booted" ;;
esac
exit 0
SH
# mkdir and top: log their calls. mkdir runs for real; top prints an idle CPU sample.
cat > "$stubs/mkdir" <<'SH'
#!/bin/sh
echo "mkdir $*" >> "$RUN/mkdir_calls"
exec /bin/mkdir "$@"
SH
cat > "$stubs/top" <<'SH'
#!/bin/sh
echo "top $*" >> "$RUN/topcalls"
echo "CPU usage: 30.00% user, 5.00% sys, 90.00% idle"
SH
chmod +x "$stubs"/*

booted() { printf '    %s (%s) (Booted) \n' "$1" "$2" >> "$booted_file"; }
fresh() { : > "$calls"; : > "$booted_file"; rm -f "$work/topcalls" "$work/mkdir_calls" "$work/started"; }
# run [VAR=value...]: the tool runs with a temp HOME and its own PATH; out and rc are the result.
rc=0
run() { env HOME="$work/home" "$@" "$script" -scheme X > "$work/run.out" 2>&1; rc=$?; }
steps() { grep -E '^(simctl (boot|shutdown) |xcodebuild)' "$calls" | awk '{print ($1=="xcodebuild") ? "run" : $2}' | tr '\n' ' '; }
has_call() { grep -Fxq "$1" "$calls"; }
rc_is() { [[ $rc -eq $1 ]]; }
steps_are() { [[ "$(steps)" == "$1" ]]; }

fresh; booted "iPhone 18 Pro" $SHARED; run
need "exit code" rc_is 0
need "destination is the booted UDID" has_call "$DEST$SHARED"
need "steps are run only" steps_are "run "
end_case "1 booted iPhone is reused by UDID: no boot, no shutdown"

fresh; booted "iPhone 17 Pro" $OTHER; run
need "exit code" rc_is 0
need "destination is the other UDID" has_call "$DEST$OTHER"
need "steps are run only" steps_are "run "
end_case "3 another single booted iPhone is used, not booted twice"

fresh; run
need "exit code" rc_is 0
need "boot of the shared iPhone" has_call "simctl boot $SHARED"
need "destination is the shared UDID" has_call "$DEST$SHARED"
need "shutdown of the shared iPhone" has_call "simctl shutdown $SHARED"
need "steps are boot run shutdown" steps_are "boot run shutdown "
end_case "4 none booted: boots the shared iPhone, tests, shuts it down"

fresh; booted "iPad Pro 13-inch" $OTHER; run
need "steps are boot run shutdown" steps_are "boot run shutdown "
need "destination is the shared UDID" has_call "$DEST$SHARED"
end_case "5 only an iPad booted: it is not the phone sim"

fresh; run STUB_RC=65
need "exit 65 passes through" rc_is 65
need "steps are boot run shutdown" steps_are "boot run shutdown "
end_case "6 test exit 65 passes through; booted sim still shut down"

fresh; booted "iPhone 18 Pro" $SHARED; run STUB_RC=75
need "exit 75 passes through" rc_is 75
need "one xcodebuild call" test "$(grep -c ^xcodebuild "$calls")" -eq 1
end_case "7 test exit 75 is a result"

fresh; booted "iPhone 18 Pro" $SHARED; run
need "exit code" rc_is 0
need "no top call" test ! -e "$work/topcalls"
need "no lock dir made" test ! -e "$work/home/.claude/locks"
need "no mkdir call at all" test ! -e "$work/mkdir_calls"
end_case "16 no lock dir under HOME/.claude/locks; top never called"

fresh; booted "iPhone 17 Pro" $OTHER; booted "iPhone 18 Pro" $THIRD; run
need "destination is the first booted iPhone" has_call "$DEST$OTHER"
need "steps are run only" steps_are "run "
end_case "17 two booted iPhones: the first is used"

fresh; run STUB_BOOT_RC=1
need "exit is non-zero" test $rc -ne 0
need "boot was tried" has_call "simctl boot $SHARED"
need "no xcodebuild call" test "$(grep -c ^xcodebuild "$calls")" -eq 0
end_case "18 failed boot exits non-zero and runs no xcodebuild"

# sig_case SIGNAL: the tool boots its own simulator and waits in xcodebuild. A signal to the whole process group
# (as a terminal sends it) must still shut that simulator down.
sig_case() {
  local sig=$1 pid
  fresh
  set -m
  env HOME="$work/home" STUB_HANG=1 "$script" -scheme X > "$work/sig.out" 2>&1 &
  pid=$!
  set +m
  for _ in $(seq 1 20); do
    [[ -e $work/started ]] && break
    "$REAL_SLEEP" 0.5
  done
  need "xcodebuild did not start" test -e "$work/started"
  kill "-$sig" -- "-$pid" 2>/dev/null
  wait "$pid" 2>/dev/null; rc=$?
  kill -KILL -- "-$pid" 2>/dev/null
  need "exit is non-zero" test $rc -ne 0
  need "simulator shut down once" test "$(grep -c "^simctl shutdown $SHARED\$" "$calls")" -eq 1
}
REAL_SLEEP=$(command -v sleep)
sig_case INT; end_case "19 INT after its own boot still shuts the simulator down"
sig_case TERM; end_case "20 TERM after its own boot still shuts the simulator down"

echo "sim-test suite: $pass_n passed, $fail_n failed${failed:+: $failed}"
exit $fail

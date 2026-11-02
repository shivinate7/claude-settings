#!/usr/bin/env bash
# Tests for bin/sim-test. CI runs this under /bin/bash (3.2) and under bash on PATH (shell-macos job).
# SIM_TEST=PATH picks the script under test; the default is bin/sim-test in this repo. A red run points it at a stub.
# No real simulator or xcodebuild is touched. xcrun, xcodebuild, top and mkdir are PATH shims, and the tool runs under
# a temp HOME with no CLAUDE_CONFIG_DIR. Temp files follow decisions/test-temp-standard.md: one run folder <pid>-<UUID>
# under one temp root, and the first request of a run sweeps siblings older than a day.
# The tool's contract:
#  - One booted iPhone is reused by UDID: no boot, no shutdown. An iPad is not an iPhone. With two, the first is used.
#  - None booted: boot the shared iPhone 18 Pro, test, then shut down that simulator, also on failure, INT and TERM.
#  - A failed boot exits non-zero and runs no xcodebuild.
#  - At the cap (2 booted devices of any kind, no iPhone among them): no boot, no xcodebuild, exit non-zero, and
#    the booted devices and the remedy are printed. Under the cap it boots.
#  - The exit code is otherwise xcodebuild's. The tool runs no top.
#  - One Mac-wide lock, state/sim-test.lock under the config dir, held for the whole run and freed on every exit,
#    SIGHUP too. A live holder is waited for (SIM_TEST_LOCK_WAIT seconds, then refused). A dead holder is taken over.
#    A lock folder with no pid file counts as held for 60 s, then it is taken over.
#  - Every xcodebuild call carries `-collect-test-diagnostics never`, so a failed UI test starts no simctl diagnose
#    (up to 10 minutes). A caller's own `-collect-test-diagnostics VALUE` wins: its value stays, with no second copy.
#  - A SpringBoard crash loop (3 new SpringBoard-*.ips reports during the run that name this run's UDID, or no device
#    folder) stops xcodebuild and exits non-zero. The stop line says "shut down" if it booted the simulator, else "left".
# The last line is the tally: passed and failed counts, then the failing case names.
set -uo pipefail
root=$(cd "$(dirname "$0")/.." && pwd)
script=${SIM_TEST:-$root/bin/sim-test}
REAL_SLEEP=$(command -v sleep)
LIMIT=20 # hard timeout per run, in seconds: a red case cannot hang the suite
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
DEST="xcodebuild test -scheme X -collect-test-diagnostics never -destination platform=iOS Simulator,id="
crashdir=$work/crash
lockdir=$work/home/.claude/state/sim-test.lock

# xcodebuild: logs its call. When the lock folder exists it records the lock (lock_during, lock_alive, lock_pid_seen).
# With STUB_CRASH=N it waits 1 s, then writes N <STUB_CRASH_PREFIX or SpringBoard>-<i>.ips reports into SIM_TEST_CRASH_DIR,
# each naming the device folder of STUB_CRASH_UDID (see mkreport).
# With STUB_HANG or STUB_CRASH it marks a start file and sleeps STUB_HANG_SECS (default 30). It writes xc_finished only
# when it is not killed, so a stop shows as no xc_finished. Then it exits with STUB_RC.
cat > "$stubs/xcodebuild" <<'SH'
#!/bin/sh
echo "xcodebuild $*" >> "$RUN/calls"
lock="${CLAUDE_CONFIG_DIR:-$HOME/.claude}/state/sim-test.lock"
if [ -d "$lock" ]; then
  : > "$RUN/lock_during"
  cat "$lock/pid" > "$RUN/lock_pid_seen" 2>/dev/null
  p=$(cat "$lock/pid" 2>/dev/null)
  if [ -n "$p" ] && kill -0 "$p" 2>/dev/null; then : > "$RUN/lock_alive"; fi
fi
n=${STUB_CRASH:-0}
if [ "$n" -gt 0 ]; then
  sleep 1
  i=0
  while [ "$i" -lt "$n" ]; do
    mkreport "$SIM_TEST_CRASH_DIR/${STUB_CRASH_PREFIX:-SpringBoard}-$i.ips" "$STUB_CRASH_UDID"
    i=$((i + 1))
  done
fi
if [ -n "${STUB_HANG:-}" ] || [ "$n" -gt 0 ]; then : > "$RUN/started"; sleep "${STUB_HANG_SECS:-30}"; fi
: > "$RUN/xc_finished"
exit ${STUB_RC:-0}
SH
# xcrun: simctl only. $RUN/booted holds the "Booted" lines of `simctl list devices booted`. Each simctl call logs its
# verb and whether the lock folder exists (lock_simctl), so a case can check the lock across list, boot and shutdown.
cat > "$stubs/xcrun" <<'SH'
#!/bin/sh
[ "$1" = simctl ] || exit 99
shift
echo "simctl $*" >> "$RUN/calls"
lock="${CLAUDE_CONFIG_DIR:-$HOME/.claude}/state/sim-test.lock"
held=no; [ -d "$lock" ] && held=yes
echo "$1 $held" >> "$RUN/lock_simctl"
case "$1" in
  list) echo "== Devices =="; echo "-- iOS 27.0 --"; cat "$RUN/booted" ;;
  boot) [ -n "${STUB_BOOT_RC:-}" ] && exit "$STUB_BOOT_RC"; echo "    iPhone 18 Pro ($2) (Booted) " > "$RUN/booted" ;;
  shutdown) : > "$RUN/booted" ;;
esac
exit 0
SH
# mkdir and top: log their calls. The mkdir log is the call log, so the lock's mkdir can be ordered against simctl.
# mkdir runs for real; top prints an idle CPU sample.
cat > "$stubs/mkdir" <<'SH'
#!/bin/sh
echo "mkdir $*" >> "$RUN/calls"
exec /bin/mkdir "$@"
SH
cat > "$stubs/top" <<'SH'
#!/bin/sh
echo "top $*" >> "$RUN/topcalls"
echo "CPU usage: 30.00% user, 5.00% sys, 90.00% idle"
SH
# mkreport FILE UDID: writes a SpringBoard report whose text names the device folder of UDID. UDID - names no device.
cat > "$stubs/mkreport" <<'SH'
#!/bin/sh
if [ "$2" = - ]; then
  printf '%s\n' '"procPath" : "/System/Library/CoreServices/SpringBoard.app/SpringBoard"' > "$1"
else
  printf '%s\n' "\"procPath\" : \"/Users/x/Library/Developer/CoreSimulator/Devices/$2/data/Containers/Bundle\"" > "$1"
fi
SH
chmod +x "$stubs"/*

booted() { printf '    %s (%s) (Booted) \n' "$1" "$2" >> "$booted_file"; }
# fresh: a clean fixture. It removes the lock folder, the crash dir and every observation file, so no lock or report
# leaks into the next case.
fresh() {
  : > "$calls"; : > "$booted_file"
  rm -f "$work/topcalls" "$work/started" "$work/xc_finished" "$work/watchdog_fired" "$work/lock_during" \
    "$work/lock_alive" "$work/lock_pid_seen" "$work/lock_simctl"
  rm -rf "$work/home/.claude" "$crashdir" "$work/sweep_root"
  /bin/mkdir -p "$crashdir" "$work/home"
}
# start_tool [VAR=value...]: starts the tool in its own process group, behind a hard timeout. Its stdout and stderr go
# to run.std and run.err. Defaults: a temp HOME, no CLAUDE_CONFIG_DIR, the crash dir in the run folder, a 1 s poll and
# a 2 s lock wait, and reports that name SHARED. Sets tool_pid and wd_pid. ARGS holds the tool's own arguments.
start_tool() {
  set -m
  env -u CLAUDE_CONFIG_DIR HOME="$work/home" SIM_TEST_CRASH_DIR="$crashdir" SIM_TEST_POLL=1 SIM_TEST_LOCK_WAIT=2 \
    STUB_CRASH_UDID="$SHARED" "$@" \
    "$script" "${ARGS[@]}" > "$work/run.std" 2> "$work/run.err" &
  tool_pid=$!
  set +m
  ( "$REAL_SLEEP" "$LIMIT"; : > "$work/watchdog_fired"; kill -KILL -- "-$tool_pid" 2>/dev/null ) > /dev/null 2>&1 &
  wd_pid=$!
}
# finish_tool: waits for the tool (rc is its exit code), kills what is left in its group, stops the watchdog, and joins
# the two streams into run.out. A run that reached the hard timeout fails the case.
finish_tool() {
  wait "$tool_pid" 2>/dev/null; rc=$?
  kill -KILL -- "-$tool_pid" 2>/dev/null
  kill "$wd_pid" 2>/dev/null; wait "$wd_pid" 2>/dev/null
  cat "$work/run.std" "$work/run.err" > "$work/run.out" 2>/dev/null
  if [[ -e $work/watchdog_fired ]]; then why=${why:-"ran past the ${LIMIT}s hard timeout"}; fi
}
# run [VAR=value...]: the tool runs with a temp HOME and its own PATH; out and rc are the result.
# ARGS holds the tool's own arguments. A case that needs more sets it before run and puts it back after.
rc=0
ARGS=(-scheme X)
run() { start_tool "$@"; finish_tool; }
steps() { grep -E '^(simctl (boot|shutdown) |xcodebuild)' "$calls" | awk '{print ($1=="xcodebuild") ? "run" : $2}' | tr '\n' ' '; }
has_call() { grep -Fxq "$1" "$calls"; }
rc_is() { [[ $rc -eq $1 ]]; }
steps_are() { [[ "$(steps)" == "$1" ]]; }

# diag_count: how many times the logged xcodebuild call names -collect-test-diagnostics.
diag_count() { grep '^xcodebuild' "$calls" | grep -o -e '-collect-test-diagnostics' | wc -l | tr -d ' '; }
# dead_pid: the pid of a process that has exited and been reaped.
dead_pid() { bash -c 'exit 0' & local p=$!; wait "$p"; echo "$p"; }
# hold_lock PID: a lock folder whose pid file names PID, as an earlier holder left it.
hold_lock() { /bin/mkdir -p "$lockdir" && printf '%s\n' "$1" > "$lockdir/pid"; }
# holder_ends_after SECS: sets holder_pid to a process alive now that exits in SECS. It is double-forked, so its parent
# exits at once and no zombie is left for the tool to see as alive.
holder_ends_after() { holder_pid=$(sh -c "sleep $1 > /dev/null 2>&1 & echo \$!"); }
# lock checks: the stub records the lock at each xcodebuild call, and at each simctl call with yes or no.
lock_seen() { test -e "$work/lock_during"; }
lock_alive() { test -e "$work/lock_alive"; }
lock_gone() { test ! -e "$lockdir"; }
lock_at() { grep -Fxq "$1 yes" "$work/lock_simctl"; }
lock_at_every_simctl() { [[ -s $work/lock_simctl ]] && ! grep -Eq ' no$' "$work/lock_simctl"; }
lock_pid_is_tool() { [[ "$(cat "$work/lock_pid_seen" 2>/dev/null)" == "$tool_pid" ]]; }
# mkdir_lock_first: one mkdir of the lock folder (no -p) is in the call log, before the first simctl call.
mkdir_lock_first() {
  local m s
  m=$(grep -nFx "mkdir $lockdir" "$calls" | head -n 1 | cut -d: -f1)
  s=$(grep -n '^simctl ' "$calls" | head -n 1 | cut -d: -f1)
  [[ -n $m && -n $s && $m -lt $s ]]
}
# crash checks: the tool's stop message goes to stderr, so they read run.err.
# stop_line: the stop line is the stderr line with crash; it is copied to crash_line.
stop_line() { grep -F crash "$work/run.err" > "$work/crash_line"; }
crash_msg() { grep -Fq crash "$work/run.err"; }
no_crash_msg() { ! grep -Fq crash "$work/run.err"; }
crash_msg_count3() { stop_line && grep -Ewq 3 "$work/crash_line"; }
crash_line_has() { stop_line && grep -Fq "$1" "$work/crash_line"; }
no_shutdown() { [[ "$(grep -c '^simctl shutdown' "$calls")" -eq 0 ]]; }
# old_reports: three reports that exist before the run. They are made 1 s before it, so they are old, not just pre-run.
old_reports() {
  local n
  for n in 0 1 2; do mkreport "$crashdir/SpringBoard-old-$n.ips" "$SHARED"; done
  "$REAL_SLEEP" 1
}

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

# Lock: step sim-machine-lock (roadmap record 55264090, 2026-11-02).
# 16 is re-pointed to the lock contract: the reuse path takes the lock with one mkdir, and holds it for the run.
fresh; booted "iPhone 18 Pro" $SHARED; run
need "exit code" rc_is 0
need "no top call" test ! -e "$work/topcalls"
need "lock mkdir (no -p) before the first simctl call" mkdir_lock_first
need "lock held during xcodebuild" lock_seen
need "lock gone after the pass" lock_gone
end_case "16 reuse path: no top; takes the lock first, holds it, frees it"

fresh; booted "iPhone 17 Pro" $OTHER; booted "iPhone 18 Pro" $THIRD; run
need "destination is the first booted iPhone" has_call "$DEST$OTHER"
need "steps are run only" steps_are "run "
end_case "17 two booted iPhones: the first is used"

fresh; run STUB_BOOT_RC=1
need "exit is non-zero" test $rc -ne 0
need "boot was tried" has_call "simctl boot $SHARED"
need "no xcodebuild call" test "$(grep -c ^xcodebuild "$calls")" -eq 0
end_case "18 failed boot exits non-zero and runs no xcodebuild"

fresh; booted "iPad Pro 13-inch" $OTHER; booted "Apple Watch Ultra 3" $THIRD; run
need "exit is non-zero" test $rc -ne 0
need "no boot" test "$(grep -c '^simctl boot' "$calls")" -eq 0
need "no xcodebuild call" test "$(grep -c ^xcodebuild "$calls")" -eq 0
need "names the first booted device" grep -Fq "iPad Pro 13-inch ($OTHER)" "$work/run.out"
need "names the second booted device" grep -Fq "Apple Watch Ultra 3 ($THIRD)" "$work/run.out"
need "prints the remedy" grep -Fq "use one, or ask the owner to stop one" "$work/run.out"
end_case "21 two non-iPhones booted: at the cap, boots nothing and runs no xcodebuild"

fresh; booted "Apple Watch Ultra 3" $THIRD; run
need "exit code" rc_is 0
need "steps are boot run shutdown" steps_are "boot run shutdown "
end_case "22 one non-iPhone booted: under the cap, boots the shared iPhone"

fresh; booted "iPad Pro 13-inch" $OTHER; booted "iPhone 18 Pro" $SHARED; run
need "exit code" rc_is 0
need "destination is the booted iPhone" has_call "$DEST$SHARED"
need "steps are run only" steps_are "run "
end_case "23 an iPhone and an iPad booted: the iPhone is reused, which is not a boot"

fresh; booted "iPhone 18 Pro" $SHARED; ARGS=(-scheme X -collect-test-diagnostics on-failure); run; ARGS=(-scheme X)
need "exit code" rc_is 0
need "the caller's value is kept, once" has_call "xcodebuild test -scheme X -collect-test-diagnostics on-failure -destination platform=iOS Simulator,id=$SHARED"
need "exactly one -collect-test-diagnostics in the call" test "$(diag_count)" = 1
end_case "24 a caller's -collect-test-diagnostics value is kept, with no second copy"

# sig_case SIGNAL: the tool boots its own simulator and waits in xcodebuild. A signal to the whole process group
# (as a terminal sends it) must still shut that simulator down.
sig_case() {
  local sig=$1
  fresh
  start_tool STUB_HANG=1 STUB_HANG_SECS=5
  for _ in $(seq 1 20); do
    [[ -e $work/started ]] && break
    "$REAL_SLEEP" 0.5
  done
  need "xcodebuild did not start" test -e "$work/started"
  kill "-$sig" -- "-$tool_pid" 2>/dev/null
  finish_tool
  need "exit is non-zero" test $rc -ne 0
  need "simulator shut down once" test "$(grep -c "^simctl shutdown $SHARED\$" "$calls")" -eq 1
}
sig_case INT; end_case "19 INT after its own boot still shuts the simulator down"
sig_case TERM; end_case "20 TERM after its own boot still shuts the simulator down"

# Lock: step sim-machine-lock (roadmap record 55264090, 2026-11-02).
fresh; hold_lock $$; run SIM_TEST_LOCK_WAIT=1
need "exit is non-zero" test $rc -ne 0
need "no simctl boot" test "$(grep -c '^simctl boot' "$calls")" -eq 0
need "no xcodebuild call" test "$(grep -c ^xcodebuild "$calls")" -eq 0
need "stderr names the holder's pid" grep -Fq "$$" "$work/run.err"
need "lock folder kept" test -d "$lockdir"
need "holder's pid file unchanged" test "$(cat "$lockdir/pid")" = "$$"
end_case "25 live holder that never ends: refused at the wait bound, no boot, no xcodebuild, lock kept"

fresh; run
need "exit code" rc_is 0
need "lock held at every simctl call" lock_at_every_simctl
need "lock held during xcodebuild" lock_seen
need "lock mkdir (no -p) before the first simctl call" mkdir_lock_first
need "pid in the lock is the tool's pid" lock_pid_is_tool
end_case "26 booted by me: one mkdir takes the lock before any simctl call; held through list, boot, xcodebuild, shutdown"

fresh; run
need "exit code" rc_is 0
need "lock held during xcodebuild" lock_seen
need "lock gone after a pass" lock_gone
end_case "27 lock gone after a pass"

fresh; run STUB_RC=65
need "exit 65 passes through" rc_is 65
need "lock held during xcodebuild" lock_seen
need "lock gone after an xcodebuild failure" lock_gone
end_case "28 lock gone after an xcodebuild failure"

sig_case INT
need "lock held during xcodebuild" lock_seen
need "lock gone after INT" lock_gone
end_case "29 lock gone after INT"

sig_case TERM
need "lock held during xcodebuild" lock_seen
need "lock gone after TERM" lock_gone
end_case "30 lock gone after TERM"

fresh; run STUB_BOOT_RC=1
need "exit is non-zero" test $rc -ne 0
need "boot was tried" has_call "simctl boot $SHARED"
need "lock held at boot" lock_at boot
need "no xcodebuild call" test "$(grep -c ^xcodebuild "$calls")" -eq 0
need "lock gone after a failed boot" lock_gone
end_case "31 lock gone after a failed boot"

fresh; booted "iPad Pro 13-inch" $OTHER; booted "Apple Watch Ultra 3" $THIRD; run
need "exit is non-zero" test $rc -ne 0
need "lock held at the device list" lock_at list
need "no xcodebuild call" test "$(grep -c ^xcodebuild "$calls")" -eq 0
need "lock gone after the cap refusal" lock_gone
end_case "32 lock gone after the cap refusal"

dead=$(dead_pid)
fresh; hold_lock "$dead"; run
need "exit code" rc_is 0
need "steps are boot run shutdown" steps_are "boot run shutdown "
need "lock held during xcodebuild" lock_seen
need "lock taken over: its holder is alive during xcodebuild" lock_alive
need "pid in the lock is the tool's pid" lock_pid_is_tool
need "lock gone after the run" lock_gone
end_case "33 stale lock (dead pid) is taken over, rewritten to the tool's pid, freed after"

fresh; holder_ends_after 1; hold_lock "$holder_pid"; run SIM_TEST_LOCK_WAIT=10
need "exit code" rc_is 0
need "waited: stderr names the holder's pid" grep -Fq "$holder_pid" "$work/run.err"
need "steps are boot run shutdown" steps_are "boot run shutdown "
need "lock held during xcodebuild" lock_seen
need "pid in the lock is the tool's pid" lock_pid_is_tool
need "lock gone after the run" lock_gone
end_case "34 live holder that ends in about 1 s: the run waits, then runs normally"

# Crash loop: step sim-crash-loop-stop (roadmap record 55264090, 2026-11-02). Named incident: 7-minute simulator
# crash loop, home repo, 2026-11-01.
fresh; run STUB_CRASH=3 STUB_HANG_SECS=4
need "exit is non-zero" test $rc -ne 0
need "xcodebuild was stopped: no xc_finished" test ! -e "$work/xc_finished"
need "shutdown of the simulator it booted" has_call "simctl shutdown $SHARED"
need "stderr has crash" crash_msg
need "stderr has crash and the count 3" crash_msg_count3
need "stop line says it shut down the simulator it booted" crash_line_has "shut down"
end_case "35 crash loop on a simulator it booted: stops xcodebuild, shuts it down, exits non-zero, names crash and 3"

fresh; run STUB_CRASH=3 STUB_HANG_SECS=4
need "exit is non-zero" test $rc -ne 0
need "lock held during xcodebuild" lock_seen
need "lock gone after the crash stop" lock_gone
end_case "36 lock gone after the crash-loop stop"

fresh; run STUB_CRASH=2 STUB_RC=65 STUB_HANG_SECS=2
need "exit code is xcodebuild's" rc_is 65
need "xcodebuild finished, not stopped" test -e "$work/xc_finished"
need "steps are boot run shutdown" steps_are "boot run shutdown "
need "no crash on stderr" no_crash_msg
end_case "37 control: 2 new SpringBoard reports do not stop the run"

fresh; old_reports; run STUB_HANG=1 STUB_HANG_SECS=2
need "exit code" rc_is 0
need "xcodebuild finished, not stopped" test -e "$work/xc_finished"
need "steps are boot run shutdown" steps_are "boot run shutdown "
need "no crash on stderr" no_crash_msg
end_case "38 control: 3 SpringBoard reports that exist before the run do not stop it"

fresh; run STUB_CRASH=3 STUB_CRASH_PREFIX=Safari STUB_HANG_SECS=2
need "exit code" rc_is 0
need "xcodebuild finished, not stopped" test -e "$work/xc_finished"
need "steps are boot run shutdown" steps_are "boot run shutdown "
need "no crash on stderr" no_crash_msg
end_case "39 control: 3 new reports not named SpringBoard do not stop the run"

fresh; booted "iPhone 18 Pro" $SHARED; run STUB_CRASH=3 STUB_HANG_SECS=4
need "exit is non-zero" test $rc -ne 0
need "xcodebuild was stopped: no xc_finished" test ! -e "$work/xc_finished"
need "no simctl boot" test "$(grep -c '^simctl boot' "$calls")" -eq 0
need "no shutdown" no_shutdown
need "stop line says it was left running" crash_line_has "left"
need "stderr has crash" crash_msg
end_case "40 crash loop on a reused iPhone: exits non-zero, no shutdown"

# Lock age: a lock folder with no pid file counts as held for 60 s, then it is stale.
fresh; /bin/mkdir -p "$lockdir"; touch -t 202001010000 "$lockdir"; run
need "exit code" rc_is 0
need "lock taken over: held during xcodebuild" lock_seen
need "lock taken over: pid in the lock is the tool's pid" lock_pid_is_tool
need "lock gone after the run" lock_gone
end_case "42 lock folder with no pid, older than 60 s: taken over"

fresh; /bin/mkdir -p "$lockdir"; run SIM_TEST_LOCK_WAIT=1
need "exit is non-zero" test $rc -ne 0
need "no simctl boot" test "$(grep -c '^simctl boot' "$calls")" -eq 0
need "no xcodebuild call" test "$(grep -c ^xcodebuild "$calls")" -eq 0
need "lock folder kept" test -d "$lockdir"
end_case "43 lock folder with no pid, younger than 60 s: still held, refused"

# SIGHUP: like TERM, it frees the lock and shuts down the simulator the tool booted.
sig_case HUP
need "lock held during xcodebuild" lock_seen
need "lock gone after SIGHUP" lock_gone
end_case "44 SIGHUP during xcodebuild: lock gone, booted simulator shut down, like TERM"

# Crash count by UDID: a report that names another simulator does not count.
fresh; run STUB_CRASH=3 STUB_CRASH_UDID=$OTHER STUB_HANG_SECS=4
need "exit code" rc_is 0
need "xcodebuild finished, not stopped" test -e "$work/xc_finished"
need "steps are boot run shutdown" steps_are "boot run shutdown "
need "no crash on stderr" no_crash_msg
end_case "45 control: 3 new reports naming another simulator's UDID do not stop the run"

# A report that names no device folder counts toward the crash loop.
fresh; run STUB_CRASH=3 STUB_CRASH_UDID=- STUB_HANG_SECS=4
need "exit is non-zero" test $rc -ne 0
need "xcodebuild was stopped: no xc_finished" test ! -e "$work/xc_finished"
need "shutdown of the simulator it booted" has_call "simctl shutdown $SHARED"
need "stderr has crash and the count 3" crash_msg_count3
end_case "46 3 new reports naming no device folder: stop"

# sweep: the run-folder sweep (decisions/test-temp-standard.md). The case reads the real sweep_runs from this file and
# runs it on a private root under the run folder.
sweep_case() {
  local sroot=$work/sweep_root old new
  sroot=$work/sweep_root
  old=$sroot/4242-0000-4000-8000-00000000000a
  new=$sroot/4243-0000-4000-8000-00000000000b
  /bin/mkdir -p "$old" "$new"
  touch -t 202001010000 "$old"
  eval "$(sed -n '/^sweep_runs() {/,/^}/p' "$0")"
  sweep_runs "$sroot"
  need "old run folder removed" test ! -e "$old"
  need "new run folder kept" test -d "$new"
}
sweep_case; end_case "41 sweep: a run folder older than a day goes, a newer one stays"

echo "sim-test suite: $pass_n passed, $fail_n failed${failed:+: $failed}"
exit $fail

#!/usr/bin/env bash
# Tests for bin/sim-test. CI runs this under /bin/bash (3.2) and under bash on PATH (shell-macos job).
# SIM_TEST=PATH picks the script under test; the default is bin/sim-test in this repo. A red run points it at a stub.
# No real simulator or xcodebuild is touched. xcrun, xcodebuild, top and mkdir are PATH shims, and the tool runs under
# a temp HOME with no CLAUDE_CONFIG_DIR. Temp files follow decisions/test-temp-standard.md: one run folder <pid>-<UUID>
# under one temp root, and the first request of a run sweeps siblings older than a day.
# The tool's contract:
#  - Flags first, all double-dash: --device duo|pro (default duo), --hold, --for S. The first argument it does not know
#    starts xcodebuild's own arguments, which pass through unchanged. Any other --device value: one usage line on stderr,
#    exit 2, no lock, no boot.
#  - A booted Duo (its name contains "iPhone Duo") is reused by UDID: no boot, no shutdown. With two, the first
#    is used. An iPad is not an iPhone. pro reuses the first booted iPhone whose name does not contain "Duo".
#  - Cross-role: a duo run with a non-Duo iPhone booted, or a pro run with a Duo booted, boots nothing, runs nothing,
#    prints one stderr line naming the booted device, and exits 1. It shuts down no device it did not boot.
#  - None booted, its own boot: the lease (bin/sim-lease, beside the script) grants the UDID for the role, duo slot 1 or
#    2 or the pro UDID. The tool boots that UDID, tests, and shuts that same UDID down. The UDIDs are read from SLOT_UDID
#    in bin/sim-lease, the one home of the device IDs.
#  - A failed boot exits non-zero, runs no xcodebuild, and shuts nothing down.
#  - At the cap (2 booted devices of any kind, no iPhone among them): no boot, no xcodebuild, exit non-zero, and
#    the booted devices and the remedy are printed. Under the cap it boots.
#  - A no-op lease (sim-lease prints none: CI or GITHUB_ACTIONS true, or not Darwin): it boots nothing, runs nothing,
#    prints one stderr line saying no lease, and exits 1.
#  - --hold: no xcodebuild. It takes the lock and a device as above, prints `sim-test: holding <UDID> as pid <PID> for <S>s`
#    on stdout, and exports SIM_TEST_UDID. With `-- CMD ARGS`, CMD runs as its child and the exit code is CMD's. With no
#    CMD, it waits until S passes (exit 0) or INT, TERM or HUP arrives (exit 130). Then it cleans up as a test run does:
#    it shuts down what it booted, gives the lease, and frees the lock.
#  - --for S: only with --hold. Default 300, max 900. Out of range or not an integer: exit 2, no lock, no boot.
#  - The exit code is otherwise xcodebuild's. The tool runs no top.
#  - One Mac-wide lock, state/sim-test.lock under the config dir, held for the whole run, a hold included, and freed on
#    every exit, SIGHUP too. A live holder is waited for (SIM_TEST_LOCK_WAIT seconds, then refused). A dead holder is taken
#    over. A lock folder with no pid file counts as held for 60 s, then it is taken over.
#  - Its own boot takes the lease for its role (`sim-lease take --device duo|pro --udid`) before simctl boot. At a 5-minute
#    load of 100 or a 1-minute load of 60 it waits, then exits 1 with no boot. The lease is released on every exit, INT and
#    TERM too.
#  - A reused device holds the lease of its own slot for the whole run or hold: `sim-lease take --device <role>
#    --for-udid <its UDID> --pid $$`. It gives that lease back on every exit, INT and TERM too. A run that granted a lease
#    and then reuses a device gives the granted lease back first. A reused device in no slot prints one stderr line and
#    runs with no lease.
#  - Every xcodebuild call carries `-collect-test-diagnostics never`, so a failed UI test starts no simctl diagnose
#    (up to 10 minutes). A caller's own `-collect-test-diagnostics VALUE` wins: its value stays, with no second copy.
#  - A SpringBoard crash loop (3 new SpringBoard-*.ips reports during the run that name this run's UDID, or no device
#    folder) stops xcodebuild and exits non-zero. The stop line says "shut down" if it booted the simulator, else "left".
#  - A `simctl list` that fails (non-zero): exit 1, no boot, no xcodebuild. The booted list is never read as empty.
#  - A duo run that queued behind a pro holder re-reads the booted list after its grant: an 18 Pro booted by then is
#    refused (exit 1, no boot), as the one-phone-kind rule says.
#  - `--hold --for S -- CMD` with CMD still running at S: exit 124, then cleanup. A crash loop stops a hold, with or
#    without CMD.
#  - TERM to the tool during the lease wait: it ends at once, not after the wait, with no boot, its queue place and the
#    lock freed. TERM during a simctl boot: the device still comes up, so it is shut down and recorded.
# The last line is the tally: passed and failed counts, then the failing case names.
set -uo pipefail
root=$(cd "$(dirname "$0")/.." && pwd)
script=${SIM_TEST:-$root/bin/sim-test}
sim_lease=$(dirname "$script")/sim-lease
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
OTHER=AAAAAAAA-0000-4000-8000-000000000001
THIRD=BBBBBBBB-0000-4000-8000-000000000002
# The device UDIDs are read from SLOT_UDID in bin/sim-lease, the one home. This suite copies none of them.
UDID_READ='import importlib.machinery, importlib.util, sys
loader = importlib.machinery.SourceFileLoader("sim_lease", sys.argv[1])
mod = importlib.util.module_from_spec(importlib.util.spec_from_loader("sim_lease", loader))
loader.exec_module(mod)
print(mod.SLOT_UDID["1"], mod.SLOT_UDID["2"], mod.SLOT_UDID["pro"])'
read -r DUO1 DUO2 PRO <<UDIDS
$(python3 -I -c "$UDID_READ" "$sim_lease" 2>/dev/null)
UDIDS
[[ -n $DUO1 && -n $DUO2 && -n $PRO ]] || { echo "sim-test suite: cannot read SLOT_UDID from $sim_lease" >&2; exit 1; }
export STUB_PRO_UDID=$PRO # the boot stub names the 18 Pro by this UDID, and a Duo by any other
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
lease="${CLAUDE_CONFIG_DIR:-$HOME/.claude}/state/sim-lease/leases.json"
[ -f "$lease" ] && cp "$lease" "$RUN/lease_at_xc"
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
# xcrun: simctl only. $RUN/booted holds the "Booted" lines of `simctl list devices booted`, and $RUN/devices.json answers
# `simctl list devices --json` (the record mode's read). Each simctl call logs its
# verb and whether the lock folder exists (lock_simctl), so a case can check the lock across list, boot and shutdown.
# STUB_LIST_RC makes every simctl list exit with that code. STUB_BOOT_HOLD holds a boot open: it writes $RUN/boot_started,
# then waits (at most 20 s) for $RUN/boot_release, so a case can send a signal while the boot is in flight.
cat > "$stubs/xcrun" <<'SH'
#!/bin/sh
[ "$1" = simctl ] || exit 99
shift
echo "simctl $*" >> "$RUN/calls"
lock="${CLAUDE_CONFIG_DIR:-$HOME/.claude}/state/sim-test.lock"
lease="${CLAUDE_CONFIG_DIR:-$HOME/.claude}/state/sim-lease/leases.json"
held=no; [ -d "$lock" ] && held=yes
echo "$1 $held" >> "$RUN/lock_simctl"
case "$1" in
  list) [ -n "${STUB_LIST_RC:-}" ] && exit "$STUB_LIST_RC"; case "$*" in
    *--json*) cat "$RUN/devices.json" ;;
    *) echo "== Devices =="; echo "-- iOS 27.0 --"; cat "$RUN/booted" ;;
  esac ;;
  boot) cp -f "$lease" "$RUN/lease_at_boot" 2>/dev/null; [ -n "${STUB_BOOT_RC:-}" ] && exit "$STUB_BOOT_RC"
    if [ -n "${STUB_BOOT_HOLD:-}" ]; then : > "$RUN/boot_started"; n=0; while [ ! -e "$RUN/boot_release" ] && [ "$n" -lt 40 ]; do sleep 0.5; n=$((n + 1)); done; fi
    case $2 in "$STUB_PRO_UDID") name="iPhone 18 Pro" ;; *) name="iPhone Duo" ;; esac; echo "    $name ($2) (Booted) " > "$RUN/booted" ;;
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
# sysctl: the load line sim-lease reads (`sysctl -n vm.loadavg`). A case writes $RUN/loadavg; with none the load is idle.
# Each read is logged to $RUN/load_reads, so a case can count the polls of a waiting take.
cat > "$stubs/sysctl" <<'SH'
#!/bin/sh
echo read >> "$RUN/load_reads"
if [ -f "$RUN/loadavg" ]; then cat "$RUN/loadavg"; else echo "{ 0.50 0.50 0.50 }"; fi
SH
# uname: sim-lease reads `uname -s` and does nothing unless it is Darwin, so the suite runs on any host.
cat > "$stubs/uname" <<'SH'
#!/bin/sh
echo Darwin
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

# hold_cmd: the child of a `--hold -- CMD` case. It records SIM_TEST_UDID, its arguments and the lock it sees, then exits 7.
hold_cmd=$work/hold_cmd.sh
cat > "$hold_cmd" <<'SH'
#!/bin/sh
echo "$SIM_TEST_UDID" > "$RUN/cmd_udid"
echo "$*" > "$RUN/cmd_args"
if [ -d "$HOME/.claude/state/sim-test.lock" ]; then
  cat "$HOME/.claude/state/sim-test.lock/pid" > "$RUN/cmd_lock_pid" 2>/dev/null
  : > "$RUN/cmd_lock_seen"
fi
lease="$HOME/.claude/state/sim-lease/leases.json"
[ -f "$lease" ] && cp "$lease" "$RUN/cmd_lease"
exit 7
SH
chmod +x "$hold_cmd"

booted() { printf '    %s (%s) (Booted) \n' "$1" "$2" >> "$booted_file"; }
# fresh: a clean fixture. It removes the lock folder, the crash dir and every observation file, so no lock or report
# leaks into the next case.
fresh() {
  : > "$calls"; : > "$booted_file"
  rm -f "$work/topcalls" "$work/started" "$work/xc_finished" "$work/watchdog_fired" "$work/lock_during" \
    "$work/lock_alive" "$work/lock_pid_seen" "$work/lock_simctl" "$work/devices.json" \
    "$work/cmd_udid" "$work/cmd_args" "$work/cmd_lock_seen" "$work/cmd_lock_pid" "$work/cmd_lease"
  rm -rf "$work/home/.claude" "$crashdir" "$work/sweep_root"
  rm -f "$work/lease_at_boot" "$work/lease_at_xc" "$work/loadavg" "$work/load_reads" "$work/boot_started" "$work/boot_release"
  /bin/mkdir -p "$crashdir" "$work/home"
}
# start_tool [VAR=value...]: starts the tool in its own process group, behind a hard timeout. Its stdout and stderr go
# to run.std and run.err. Defaults: a temp HOME, no CLAUDE_CONFIG_DIR, the crash dir in the run folder, a 1 s poll and
# a 2 s lock wait, a 1 s lease poll, CI and GITHUB_ACTIONS unset (sim-lease does nothing under them), and reports that
# name DUO1, the Duo of slot 1. Sets tool_pid and wd_pid. ARGS holds the tool's own arguments.
start_tool() {
  set -m
  env -u CLAUDE_CONFIG_DIR -u CI -u GITHUB_ACTIONS HOME="$work/home" SIM_TEST_CRASH_DIR="$crashdir" SIM_TEST_POLL=1 \
    SIM_TEST_LOCK_WAIT=2 SIM_LEASE_POLL=1 \
    STUB_CRASH_UDID="$DUO1" "$@" \
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
# dest_is UDID: a logged xcodebuild call names this destination. Its other arguments are not checked.
dest_is() { grep -Fq -- "-destination platform=iOS Simulator,id=$1" "$calls"; }
no_boot() { [[ "$(grep -c '^simctl boot' "$calls")" -eq 0 ]]; }
no_simctl() { [[ "$(grep -c '^simctl ' "$calls")" -eq 0 ]]; }
no_xcodebuild() { [[ "$(grep -c '^xcodebuild' "$calls")" -eq 0 ]]; }
# no_device_in_xcodebuild: no logged xcodebuild call carries --device. The role flag is sim-test's, not xcodebuild's.
no_device_in_xcodebuild() { [[ "$(grep '^xcodebuild' "$calls" | grep -c -- --device)" -eq 0 ]]; }
# no_lock_taken: the lock folder was never made (one mkdir of it is in the call log).
no_lock_taken() { ! has_call "mkdir $lockdir"; }

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
# lock_pid_file_is_tool: the lock folder is held now, and its pid file names this tool.
lock_pid_file_is_tool() { [[ "$(cat "$lockdir/pid" 2>/dev/null)" == "$tool_pid" ]]; }
# lease checks: sim-lease keeps its state under this run's HOME. lease_holds FILE PID exits 0 when the JSON in FILE holds PID
# as a value anywhere (no field name is assumed), 1 when it does not or FILE is missing, 2 when FILE is not JSON. The
# compare is on the whole value, so pid 12 does not match 123.
lease_file=$work/home/.claude/state/sim-lease/leases.json
LEASE_CHECK='import json, sys
try:
    with open(sys.argv[1]) as f:
        state = json.load(f)
except FileNotFoundError:
    sys.exit(1)
except ValueError:
    sys.exit(2)
def holds(v):
    if isinstance(v, dict):
        return any(holds(x) for x in v.values())
    if isinstance(v, list):
        return any(holds(x) for x in v)
    return str(v) == sys.argv[2]
sys.exit(0 if holds(state) else 1)'
lease_holds() { python3 -I -c "$LEASE_CHECK" "$1" "$2"; }
# lease_slot FILE PID SLOT exits 0 when FILE holds a lease whose pid is PID and whose slot is SLOT (1, 2 or pro).
SLOT_CHECK='import json, sys
try:
    with open(sys.argv[1]) as f:
        state = json.load(f)
except (FileNotFoundError, ValueError):
    sys.exit(1)
held = [e for e in state.get("leases", []) if isinstance(e, dict)]
sys.exit(0 if any(str(e.get("pid")) == sys.argv[2] and str(e.get("slot")) == sys.argv[3] for e in held) else 1)'
lease_slot() { python3 -I -c "$SLOT_CHECK" "$1" "$2" "$3"; }
lease_at_boot_holds() { lease_holds "$work/lease_at_boot" "$tool_pid"; }
lease_at_boot_slot() { lease_slot "$work/lease_at_boot" "$tool_pid" "$1"; }
lease_at_xc_holds() { lease_holds "$work/lease_at_xc" "$tool_pid"; }
lease_at_xc_slot() { lease_slot "$work/lease_at_xc" "$tool_pid" "$1"; }
lease_at_xc_lacks_slot() { ! lease_slot "$work/lease_at_xc" "$tool_pid" "$1"; }
lease_at_cmd_slot() { lease_slot "$work/cmd_lease" "$tool_pid" "$1"; }
lease_not_held_at_xc() { ! lease_at_xc_holds; }
# lease_released: the state after the run holds no lease of this tool. Exit 1 is the only pass, so a broken file fails.
lease_released() { lease_holds "$lease_file" "$tool_pid"; [ $? -eq 1 ]; }
no_lease_file() { [ ! -e "$lease_file" ]; }
# set_load LINE: the load line the sysctl stub prints, as `sysctl -n vm.loadavg` prints it.
set_load() { printf '%s\n' "$1" > "$work/loadavg"; }
# load_polls_at_least N: the sysctl stub logs each read, so a take that waits reads the load at least N times.
load_polls_at_least() { [ "$(cat "$work/load_reads" 2>/dev/null | wc -l | tr -d ' ')" -ge "$1" ]; }
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
  for n in 0 1 2; do mkreport "$crashdir/SpringBoard-old-$n.ips" "$DUO1"; done
  "$REAL_SLEEP" 1
}
# hold_slot1: a live holder takes Duo slot 1 through the real sim-lease, so the next take is granted slot 2.
# release_slot1 stops the holder; a later take then reaps it.
slot_holder=
hold_slot1() {
  sleep 600 > /dev/null 2>&1 &
  slot_holder=$!
  need "the holder is granted Duo slot 1" test "$(env -u CLAUDE_CONFIG_DIR -u CI -u GITHUB_ACTIONS HOME="$work/home" \
    "$sim_lease" take --device duo --pid "$slot_holder" --wait 1 2>/dev/null)" = 1
}
release_slot1() {
  if [[ -n $slot_holder ]]; then kill "$slot_holder" 2>/dev/null; wait "$slot_holder" 2>/dev/null; fi
  slot_holder=
}
# hold_then_term ARG...: runs the tool with ARG... (a --hold run with no CMD). It waits for the holding line, records
# whether the lock folder is held by this tool's pid (lock_hold_ok), then sends TERM to its group. The wait is for the
# line or for the tool to end, never a fixed delay.
lock_hold_ok=
hold_then_term() {
  fresh
  ARGS=("$@"); start_tool; ARGS=(-scheme X)
  for _ in $(seq 1 20); do
    grep -Fq "sim-test: holding" "$work/run.std" && break
    kill -0 "$tool_pid" 2>/dev/null || break
    "$REAL_SLEEP" 0.5
  done
  lock_hold_ok=; lock_pid_file_is_tool && lock_hold_ok=1
  kill -TERM -- "-$tool_pid" 2>/dev/null
  finish_tool
}
# for_case_ok VALUE: `--hold --for VALUE` exits 2 before any lock, simctl or xcodebuild call.
for_case_ok() {
  fresh; ARGS=(--hold --for "$1"); run; ARGS=(-scheme X)
  rc_is 2 && no_lock_taken && no_simctl && no_xcodebuild
}

fresh; booted "iPhone Duo" $DUO1; run
need "exit code" rc_is 0
need "destination is the booted Duo" dest_is "$DUO1"
need "steps are run only" steps_are "run "
need "the lease held during xcodebuild is slot 1" lease_at_xc_slot 1
need "lease released after the run" lease_released
end_case "1 booted Duo is reused by UDID: no boot, no shutdown, slot 1's lease held during the run and released after"

fresh; booted "iPhone Duo" $DUO2; run
need "exit code" rc_is 0
need "destination is the other Duo's UDID" dest_is "$DUO2"
need "steps are run only" steps_are "run "
end_case "3 another booted Duo is used, not booted twice"

fresh; run
need "boot of the Duo the lease grants (slot 1)" has_call "simctl boot $DUO1"
need "destination is that UDID" has_call "$DEST$DUO1"
need "shutdown of that UDID" has_call "simctl shutdown $DUO1"
need "steps are boot run shutdown" steps_are "boot run shutdown "
need "exit code" rc_is 0
end_case "4 none booted: boots the Duo the lease grants, tests, shuts that same Duo down"

fresh; booted "iPad Pro 13-inch" $OTHER; run
need "steps are boot run shutdown" steps_are "boot run shutdown "
need "destination is the Duo's UDID, not the iPad's" has_call "$DEST$DUO1"
end_case "5 only an iPad booted: it is not the phone sim, so the Duo is booted"

fresh; run STUB_RC=65
need "exit 65 passes through" rc_is 65
need "steps are boot run shutdown" steps_are "boot run shutdown "
end_case "6 test exit 65 passes through; booted sim still shut down"

fresh; booted "iPhone Duo" $DUO1; run STUB_RC=75
need "exit 75 passes through" rc_is 75
need "one xcodebuild call" test "$(grep -c ^xcodebuild "$calls")" -eq 1
end_case "7 test exit 75 is a result"

# Lock: step sim-machine-lock (roadmap record 55264090, 2026-11-02).
# 16 is re-pointed to a booted Duo: the reuse path takes the lock with one mkdir, and holds it for the run.
fresh; booted "iPhone Duo" $DUO1; run
need "exit code" rc_is 0
need "no top call" test ! -e "$work/topcalls"
need "lock mkdir (no -p) before the first simctl call" mkdir_lock_first
need "lock held during xcodebuild" lock_seen
need "lock gone after the pass" lock_gone
end_case "16 reuse path: no top; takes the lock first, holds it, frees it"

fresh; booted "iPhone Duo" $DUO2; booted "iPhone Duo" $DUO1; run
need "destination is the first booted Duo" dest_is "$DUO2"
need "steps are run only" steps_are "run "
end_case "17 two booted Duos: the first is used"

fresh; run STUB_BOOT_RC=1
need "exit is non-zero" test $rc -ne 0
need "boot was tried on the Duo's UDID" has_call "simctl boot $DUO1"
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
need "destination is the Duo's UDID" has_call "$DEST$DUO1"
end_case "22 one non-iPhone booted: under the cap, boots the Duo"

fresh; booted "iPad Pro 13-inch" $OTHER; booted "iPhone Duo" $DUO1; run
need "exit code" rc_is 0
need "destination is the booted Duo" dest_is "$DUO1"
need "steps are run only" steps_are "run "
end_case "23 a Duo and an iPad booted: the Duo is reused, which is not a boot"

fresh; booted "iPhone Duo" $DUO1; ARGS=(-scheme X -collect-test-diagnostics on-failure); run; ARGS=(-scheme X)
need "exit code" rc_is 0
need "the caller's value is kept, once" has_call "xcodebuild test -scheme X -collect-test-diagnostics on-failure -destination platform=iOS Simulator,id=$DUO1"
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
  need "simulator shut down once" test "$(grep -c "^simctl shutdown $DUO1\$" "$calls")" -eq 1
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
need "boot was tried on the Duo's UDID" has_call "simctl boot $DUO1"
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
need "shutdown of the Duo it booted" has_call "simctl shutdown $DUO1"
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

fresh; booted "iPhone Duo" $DUO1; run STUB_CRASH=3 STUB_HANG_SECS=4
need "exit is non-zero" test $rc -ne 0
need "xcodebuild was stopped: no xc_finished" test ! -e "$work/xc_finished"
need "no simctl boot" test "$(grep -c '^simctl boot' "$calls")" -eq 0
need "no shutdown" no_shutdown
need "stop line says it was left running" crash_line_has "left"
need "stderr has crash" crash_msg
end_case "40 crash loop on a reused Duo: exits non-zero, no shutdown"

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
need "shutdown of the Duo it booted" has_call "simctl shutdown $DUO1"
need "stderr has crash and the count 3" crash_msg_count3
end_case "46 3 new reports naming no device folder: stop"

# Record: after its own boot, the tool calls the hook's record mode, which appends one sim-boots.jsonl line for the
# simulator it booted. A reuse writes none. The stub ps names a launchd_sim for DUO1 (pid 4242), DUO2 (pid 4343) and the
# pro UDID (pid 4444), so a line has a real launchd_sim to name. The record call is silent, and its failure is ignored.
LSTART="Sat Oct 10 07:00:00 2026"
LAUNCHD=/Library/Developer/PrivateFrameworks/CoreSimulator.framework/Versions/A/Resources/launchd_sim
records=$work/home/.claude/state/sim-boots.jsonl
# ps_stub: a `ps` that answers the process table with a launchd_sim row for each of the three device UDIDs, and the start
# time of each pid for a `-o lstart= -p PID` call; any other pid goes to the real ps (sim-lease reads its holder's start).
# The case that needs it puts it first on PATH.
ps_stub() {
  local real_ps
  real_ps=$(command -v ps)
  /bin/mkdir -p "$work/psbin"
  cat > "$work/psbin/ps" <<SH
#!/bin/sh
case "\$*" in
  *lstart*) case "\$*" in
    *"-p 4242") echo "4242 $LSTART" ;; *"-p 4343") echo "4343 $LSTART" ;; *"-p 4444") echo "4444 $LSTART" ;;
    *) exec $real_ps "\$@" ;; esac ;;
  *) printf '%s\n' "4242 1 501 $LAUNCHD $DUO1" "4343 1 501 $LAUNCHD $DUO2" "4444 1 501 $LAUNCHD $PRO" ;;
esac
SH
  chmod +x "$work/psbin/ps"
}
# devices_json UDID [NAME]: the device list after a boot of UDID, one Booted device on one runtime. NAME defaults to a Duo.
devices_json() {
  local name=${2:-iPhone Duo}
  cat > "$work/devices.json" <<JSON
{"devices":{"com.apple.CoreSimulator.SimRuntime.iOS-27-0":[{"udid":"$1","name":"$name","state":"Booted","deviceTypeIdentifier":"com.apple.CoreSimulator.SimDeviceType.iPhone-Duo","isAvailable":true}]}}
JSON
}
# record_lines: how many sim-boots.jsonl lines the run wrote, 0 when it wrote no file.
record_lines() { if [[ -e $records ]]; then wc -l < "$records" | tr -d ' '; else echo 0; fi; }
record_names() { grep -Fq "\"udid\": \"$1\"" "$records" 2>/dev/null; }
no_hook_message() { ! grep -Fq sim_boot_record "$work/run.err"; }

fresh; ps_stub; devices_json "$DUO1"; run PATH="$work/psbin:$PATH"
need "exit code" rc_is 0
need "steps are boot run shutdown" steps_are "boot run shutdown "
need "one record line" test "$(record_lines)" -eq 1
need "the line names the Duo's UDID" record_names "$DUO1"
end_case "51 boot path: the Duo it boots gets one sim-boots.jsonl line"

fresh; ps_stub; devices_json "$DUO2"; booted "iPhone Duo" $DUO2; run PATH="$work/psbin:$PATH"
need "exit code" rc_is 0
need "steps are run only" steps_are "run "
need "no record line" test "$(record_lines)" -eq 0
end_case "52 reuse path: the Duo it reuses gets no sim-boots.jsonl line"

# A copy of the tool and its sim-lease, with a hooks folder that holds only what sim-lease imports: the record call finds no hook. It must print nothing, and the
# run must still boot, test and shut down with xcodebuild's exit code.
fresh; ps_stub; devices_json "$DUO1"
/bin/mkdir -p "$work/nohooks/bin"; cp "$script" "$work/nohooks/bin/sim-test"; cp "$sim_lease" "$work/nohooks/bin/sim-lease"; chmod +x "$work/nohooks/bin/sim-test" "$work/nohooks/bin/sim-lease"
/bin/mkdir -p "$work/nohooks/hooks"; cp "$root/hooks/_nowindow.py" "$work/nohooks/hooks/"
saved_script=$script; script=$work/nohooks/bin/sim-test
run PATH="$work/psbin:$PATH"
script=$saved_script
need "exit code is xcodebuild's" rc_is 0
need "steps are boot run shutdown" steps_are "boot run shutdown "
need "no hook message on stderr" no_hook_message
end_case "53 the record call is silent, and its failure does not change the exit code"

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

# Lease: the own-boot path takes the Duo lease from bin/sim-lease, the sibling of the script under test.
fresh; run
need "exit code" rc_is 0
need "lease held at the boot" lease_at_boot_holds
need "lease released after the run" lease_released
end_case "47 own boot: the lease is held while simctl boot runs, and released after the run"

fresh; set_load "{ 0.50 100.00 0.50 }"; run SIM_LEASE_WAIT=2
need "no boot" test "$(grep -c '^simctl boot' "$calls")" -eq 0
need "no xcodebuild call" test "$(grep -c ^xcodebuild "$calls")" -eq 0
need "waited: the load was read at least twice" load_polls_at_least 2
need "exit code is 1" rc_is 1
need "stderr names the load" grep -Fq "5-min 100.00" "$work/run.err"
end_case "48 own boot over a 5-minute load of 100: waits, exits 1, no boot, no xcodebuild"

sig_case TERM
need "lease held during xcodebuild" lease_at_xc_holds
need "lease released after TERM" lease_released
end_case "49 TERM during an own-boot run: the lease is held during xcodebuild, and released after"

fresh; booted "iPhone Duo" $DUO1; run
need "exit code" rc_is 0
need "steps are run only" steps_are "run "
need "the lease held during xcodebuild is slot 1" lease_at_xc_slot 1
need "lease released after the run" lease_released
end_case "50 reuse path: holds the Duo's slot lease during xcodebuild, and gives it back after"

# Duo slot 2: a live holder has slot 1, so the real sim-lease grants this take slot 2. Its UDID is booted, tested and shut
# down. The take waits 2 s at most, so a take refused on the old code fails fast.
fresh; hold_slot1; run SIM_LEASE_WAIT=2
need "boot of slot 2's UDID" has_call "simctl boot $DUO2"
need "destination is slot 2's UDID" dest_is "$DUO2"
need "shutdown of slot 2's UDID" has_call "simctl shutdown $DUO2"
need "steps are boot run shutdown" steps_are "boot run shutdown "
need "the lease at boot is slot 2" lease_at_boot_slot 2
need "exit code" rc_is 0
release_slot1
end_case "54 Duo slot 1 held by another: slot 2 is granted, and its UDID is booted, tested and shut down"

fresh; ARGS=(--device pro -scheme X); run; ARGS=(-scheme X)
need "boot of the pro UDID" has_call "simctl boot $PRO"
need "destination is the pro UDID" dest_is "$PRO"
need "shutdown of the pro UDID" has_call "simctl shutdown $PRO"
need "steps are boot run shutdown" steps_are "boot run shutdown "
need "the lease at boot is the pro lease" lease_at_boot_slot pro
need "--device is not passed to xcodebuild" no_device_in_xcodebuild
need "exit code" rc_is 0
end_case "55 --device pro: boots the pro UDID under the pro lease, and xcodebuild gets no --device"

fresh; ARGS=(--device nope -scheme X); run; ARGS=(-scheme X)
need "exit 2" rc_is 2
need "one usage line on stderr" test "$(grep -c . "$work/run.err")" -eq 1
need "the usage line names --device" grep -Fq -- --device "$work/run.err"
need "no lock taken" no_lock_taken
need "no simctl call" no_simctl
need "no xcodebuild call" no_xcodebuild
end_case "56 bad --device: exit 2 with one usage line, no lock, no boot, no xcodebuild"

# Control: xcodebuild's arguments pass through in order, and the flags and destination follow them.
fresh; booted "iPhone Duo" $DUO1; ARGS=(-scheme X -only-testing:AppUITests/Login); run; ARGS=(-scheme X)
need "exit code" rc_is 0
need "xcodebuild gets its arguments in order, then the flags and destination" has_call "xcodebuild test -scheme X -only-testing:AppUITests/Login -collect-test-diagnostics never -destination platform=iOS Simulator,id=$DUO1"
end_case "57 control: xcodebuild arguments pass through in order"

# Control: the first argument sim-test does not know ends its flags, so a later --device is xcodebuild's own.
fresh; booted "iPhone Duo" $DUO1; ARGS=(-scheme X --device pro -only-testing:AppUITests/Login); run; ARGS=(-scheme X)
need "exit code" rc_is 0
need "the Duo is reused: the role is not read after -scheme" dest_is "$DUO1"
need "--device and its value reach xcodebuild unchanged" has_call "xcodebuild test -scheme X --device pro -only-testing:AppUITests/Login -collect-test-diagnostics never -destination platform=iOS Simulator,id=$DUO1"
end_case "58 control: a flag after the first xcodebuild argument is xcodebuild's own"

fresh; booted "iPhone 18 Pro" $PRO; run
need "exit 1" rc_is 1
need "boots nothing" no_boot
need "runs nothing" no_xcodebuild
need "shuts down nothing" no_shutdown
need "stderr names the booted 18 Pro" grep -Fq "iPhone 18 Pro" "$work/run.err"
end_case "59 duo run with an 18 Pro booted: refused, boots and runs nothing, exit 1"

fresh; booted "iPhone Duo" $DUO1; ARGS=(--device pro -scheme X); run; ARGS=(-scheme X)
need "exit 1" rc_is 1
need "boots nothing" no_boot
need "runs nothing" no_xcodebuild
need "shuts down nothing" no_shutdown
need "stderr names the booted Duo" grep -Fq "iPhone Duo" "$work/run.err"
end_case "60 pro run with a Duo booted: refused, boots and runs nothing, exit 1"

# The pro role reuses the booted 18 Pro, as it did before the role flag existed, and holds the pro lease for the run.
fresh; booted "iPhone 18 Pro" $PRO; ARGS=(--device pro -scheme X); run; ARGS=(-scheme X)
need "exit code" rc_is 0
need "steps are run only" steps_are "run "
need "the lease held during xcodebuild is the pro slot" lease_at_xc_slot pro
need "lease released after the run" lease_released
end_case "61 pro run with the 18 Pro booted reuses it, with no boot, and holds the pro lease during the run"

fresh; run CI=true
need "exit 1" rc_is 1
need "boots nothing" no_boot
need "runs nothing" no_xcodebuild
need "writes no lease file" no_lease_file
need "stderr says no lease" grep -Fqi "no lease" "$work/run.err"
end_case "62 no-op lease (CI=true): exit 1, boots and runs nothing, writes no lease"

fresh; ARGS=(--hold -- "$hold_cmd" alpha beta); run; ARGS=(-scheme X)
need "exit code is the child's, 7" rc_is 7
need "the child got SIM_TEST_UDID for the Duo the lease granted" test "$(cat "$work/cmd_udid" 2>/dev/null)" = "$DUO1"
need "the child got its arguments" test "$(cat "$work/cmd_args" 2>/dev/null)" = "alpha beta"
need "holding line names the Duo, this pid and 300s" grep -Fq "sim-test: holding $DUO1 as pid $tool_pid for 300s" "$work/run.std"
need "boot, then shutdown of the Duo: no xcodebuild" steps_are "boot shutdown "
need "shutdown of the Duo after the child ends" has_call "simctl shutdown $DUO1"
need "lease given" lease_released
need "lock freed" lock_gone
end_case "63 --hold -- CMD: the child gets SIM_TEST_UDID and its arguments; its exit code is returned; then cleanup"

fresh; ARGS=(--hold --for 1); run; ARGS=(-scheme X)
need "exit 0 on timeout" rc_is 0
need "holding line names the Duo, this pid and 1s" grep -Fq "sim-test: holding $DUO1 as pid $tool_pid for 1s" "$work/run.std"
need "boot, then shutdown of the Duo: no xcodebuild" steps_are "boot shutdown "
need "shutdown of the Duo" has_call "simctl shutdown $DUO1"
need "lease given" lease_released
need "lock freed" lock_gone
end_case "64 --hold --for 1 with no CMD: exit 0 on timeout, shuts the Duo down, gives the lease"

hold_then_term --hold
need "holding line names the Duo, this pid and 300s" grep -Fq "sim-test: holding $DUO1 as pid $tool_pid for 300s" "$work/run.std"
need "lock held during the hold, by this tool's pid" test "$lock_hold_ok" = 1
need "exit 130 on TERM" rc_is 130
need "boot, then shutdown of the Duo" steps_are "boot shutdown "
need "shutdown of the Duo" has_call "simctl shutdown $DUO1"
need "lease given" lease_released
need "lock freed" lock_gone
end_case "65 --hold with no CMD, then TERM: exit 130, shuts the Duo down, gives the lease, frees the lock"

hold_then_term --hold --for 900
need "--for 900 is accepted: the holding line says 900s" grep -Fq "for 900s" "$work/run.std"
need "exit 130 on TERM" rc_is 130
need "shutdown of the Duo" has_call "simctl shutdown $DUO1"
end_case "66 --for 900 is the longest hold, and it is accepted"

for v in 0 901 x; do
  need "--for $v: exit 2 before any lock, simctl or xcodebuild call" for_case_ok "$v"
done
end_case "67 --for out of range or not an integer: exit 2, no lock, no boot, no xcodebuild"

fresh; ARGS=(--hold -- "$hold_cmd"); run; ARGS=(-scheme X)
need "the child saw the lock folder" test -e "$work/cmd_lock_seen"
need "the lock's pid is this tool's pid while the child runs" test "$(cat "$work/cmd_lock_pid" 2>/dev/null)" = "$tool_pid"
need "lock freed after the hold" lock_gone
end_case "68 lock held through a --hold run: the child sees the lock with this tool's pid, and it is freed after"

# ---- Cases 69 to 77: the queued duo run, simctl list failing, a hold past its time, a crash loop in a hold, and TERM
# during the lease wait and during a boot.
# poll_for TRIES CMD...: runs CMD now and then every 0.5 s, up to TRIES runs, and returns at the first success. It waits for
# a step the tool or the test has made, never for a fixed time: TRIES is a ceiling only.
poll_for() { local n=$1; shift; while [ "$n" -gt 0 ]; do "$@" && return 0; n=$((n - 1)); "$REAL_SLEEP" 0.5; done; "$@"; }
# in_lease_file: this tool's pid is in leases.json, as a lease or as a place in the queue.
in_lease_file() { lease_holds "$lease_file" "$tool_pid"; }
# tool_ended: the tool has exited. A zombie counts as exited: finish_tool reaps it.
tool_ended() { local st; st=$(ps -o stat= -p "$tool_pid" 2>/dev/null); [[ -z $st || $st == Z* ]]; }
# lease_freed_after_reap: a `sim-lease status` call drops the dead holders and places, as a later take does. Then the tool
# holds neither a lease nor a place.
lease_freed_after_reap() { env -u CLAUDE_CONFIG_DIR -u CI -u GITHUB_ACTIONS HOME="$work/home" "$sim_lease" status > /dev/null 2>&1; lease_released; }

# pro_dies_during_duo_wait BOOTED: a pro holder takes the pro lease, a duo run queues behind it, and the holder dies. With
# BOOTED yes the 18 Pro is still booted when the holder dies, as a pro run that never shut it down leaves it. With BOOTED
# duo, a Duo of slot 2 is booted during the wait, so the queued run reuses that Duo after its grant.
pro_dies_during_duo_wait() {
  fresh
  sleep 600 > /dev/null 2>&1 &
  local holder=$!
  need "the pro holder is granted the pro lease" test "$(env -u CLAUDE_CONFIG_DIR -u CI -u GITHUB_ACTIONS HOME="$work/home" \
    "$sim_lease" take --device pro --pid "$holder" --wait 1 2>/dev/null)" = pro
  ARGS=(-scheme X); start_tool SIM_LEASE_WAIT=60
  need "the duo run is queued behind the pro lease" poll_for 20 in_lease_file
  if [[ $1 = yes ]]; then
    booted "iPhone 18 Pro" $PRO
    need "the 18 Pro is booted when the holder dies" grep -Fq "iPhone 18 Pro" "$booted_file"
  elif [[ $1 = duo ]]; then
    booted "iPhone Duo" $DUO2
  fi
  kill "$holder" 2>/dev/null; wait "$holder" 2>/dev/null
  finish_tool
  ARGS=(-scheme X)
}
pro_dies_during_duo_wait yes
need "exit 1" rc_is 1
need "boots nothing" no_boot
need "runs nothing" no_xcodebuild
need "stderr names the booted 18 Pro" grep -Fq "iPhone 18 Pro" "$work/run.err"
need "lease given back" lease_released
end_case "69 a pro holder dies with the 18 Pro still booted, during a queued duo run's wait: refused, no boot, exit 1"

pro_dies_during_duo_wait no
need "exit code" rc_is 0
need "steps are boot run shutdown" steps_are "boot run shutdown "
need "destination is the Duo's UDID" dest_is "$DUO1"
end_case "70 control: a pro holder dies with nothing booted, and the queued duo run boots its Duo"

fresh; run STUB_LIST_RC=1
need "exit 1" rc_is 1
need "boots nothing" no_boot
need "runs nothing" no_xcodebuild
end_case "71 simctl list fails: exit 1, boots and runs nothing"

fresh; ARGS=(--hold --for 1 -- sleep 15); run; ARGS=(-scheme X)
need "exit 124 when CMD runs past --for" rc_is 124
need "steps are boot shutdown" steps_are "boot shutdown "
need "shutdown of the Duo it booted" has_call "simctl shutdown $DUO1"
need "lease given" lease_released
need "lock freed" lock_gone
end_case "72 --hold --for 1 -- CMD still running at 1 s: exit 124, shuts the Duo down, gives the lease, frees the lock"

# The CMD of case 73 writes three SpringBoard reports that name its Duo, then sleeps on until the hold stops it.
crash_cmd=$work/crash_cmd.sh
cat > "$crash_cmd" <<'SH'
#!/bin/sh
sleep 1
for i in 0 1 2; do mkreport "$SIM_TEST_CRASH_DIR/SpringBoard-hold-$i.ips" "$STUB_CRASH_UDID"; done
sleep 30
SH
chmod +x "$crash_cmd"
fresh; ARGS=(--hold -- "$crash_cmd"); run; ARGS=(-scheme X)
need "exit 1 on the crash loop" rc_is 1
need "stderr names the crash loop and the count 3" crash_msg_count3
need "the stop line says it shut down the Duo it booted" crash_line_has "shut down"
need "shutdown of the Duo it booted" has_call "simctl shutdown $DUO1"
end_case "73 crash loop during a hold with CMD: stops CMD, shuts the Duo down, exits 1"

fresh; ARGS=(--hold --for 60); start_tool; ARGS=(-scheme X)
need "the hold is up" poll_for 20 grep -Fq "sim-test: holding" "$work/run.std"
for i in 0 1 2; do mkreport "$crashdir/SpringBoard-hold-$i.ips" "$DUO1"; done
finish_tool
need "exit 1 on the crash loop" rc_is 1
need "stderr names the crash loop and the count 3" crash_msg_count3
need "the stop line says it shut down the Duo it booted" crash_line_has "shut down"
need "shutdown of the Duo it booted" has_call "simctl shutdown $DUO1"
end_case "74 crash loop during a hold with no CMD: exits 1, shuts the Duo down"

# lease_wait_term TARGET: a duo run queues behind a 5-minute load of 100, then TERM arrives. TARGET tool sends it to the
# tool's pid alone, as a caller's own kill does; TARGET group sends it to the whole process group, as a terminal does.
lease_wait_term() {
  fresh; set_load "{ 0.50 100.00 0.50 }"
  ARGS=(-scheme X); start_tool SIM_LEASE_WAIT=60
  need "the duo run is queued behind the load" poll_for 20 in_lease_file
  if [[ $1 = group ]]; then kill -TERM -- "-$tool_pid" 2>/dev/null; else kill -TERM "$tool_pid" 2>/dev/null; fi
  need "the tool ends within 5 s of TERM (a ceiling of 10 polls, 0.5 s apart)" poll_for 10 tool_ended
  finish_tool
  ARGS=(-scheme X)
  need "no boot" no_boot
  need "queue place and lease freed" lease_freed_after_reap
  need "lock freed" lock_gone
}
lease_wait_term tool
end_case "75 TERM to the tool alone during the lease wait: ends within 5 s, no boot, queue place and lock freed"
lease_wait_term group
end_case "76 control: TERM to the whole group during the lease wait ends within 5 s, with the same cleanup"

# Case 77: the boot is held open, TERM reaches the tool alone, and then the boot is let finish. The Duo it booted is shut
# down and recorded.
fresh; ps_stub; devices_json "$DUO1"
ARGS=(-scheme X); start_tool PATH="$work/psbin:$PATH" STUB_BOOT_HOLD=1
need "the boot is in flight" poll_for 20 test -e "$work/boot_started"
kill -TERM "$tool_pid" 2>/dev/null
: > "$work/boot_release"
finish_tool
need "shutdown of the Duo it booted, after the boot" has_call "simctl shutdown $DUO1"
need "the Duo's boot is recorded" record_names "$DUO1"
end_case "77 TERM to the tool during a slow simctl boot: the Duo still comes up, and is shut down and recorded"

# Case 78: a Duo booted during the wait, then the pro holder dies: the queued duo run is granted slot 1, then reuses the
# Duo of slot 2, so it gives slot 1 back and holds slot 2 during xcodebuild.
pro_dies_during_duo_wait duo
need "exit code" rc_is 0
need "steps are run only" steps_are "run "
need "destination is the booted Duo" dest_is "$DUO2"
need "the lease held during xcodebuild is slot 2" lease_at_xc_slot 2
need "the granted slot 1 is given back before xcodebuild" lease_at_xc_lacks_slot 1
need "lease released after the run" lease_released
need "no shutdown" no_shutdown
end_case "78 a Duo booted during the wait, then the pro holder dies: the queued run gives back slot 1, holds slot 2 during xcodebuild, and releases it after"

# Case 79: a failed own boot shuts nothing down. The boot fails, so the tool clears its boot mark before it exits, and its
# cleanup has no simulator of its own to shut down.
fresh; run STUB_BOOT_RC=1
need "boot was tried on the Duo's UDID" has_call "simctl boot $DUO1"
need "exit is non-zero" test $rc -ne 0
need "no shutdown of a device it did not boot" no_shutdown
end_case "79 failed own boot shuts nothing down"

# Case 80: a dead holder's lock folder that also holds take.out, the file a holder leaves when it dies during its lease
# take. The take over moves the whole folder, so no part of it may be left beside the lock.
# no_dead_folder: no sim-test.lock.dead.* folder is left beside the lock folder.
no_dead_folder() { [ -z "$(ls -d "$lockdir".dead.* 2>/dev/null)" ]; }
# no_rmdir_error: the tool wrote no rmdir error to stderr.
no_rmdir_error() { ! grep -Fq rmdir "$work/run.err"; }
dead=$(dead_pid)
fresh; hold_lock "$dead"; : > "$lockdir/take.out"; run
need "exit code" rc_is 0
need "steps are boot run shutdown" steps_are "boot run shutdown "
need "no sim-test.lock.dead.* folder is left" no_dead_folder
need "no rmdir error on stderr" no_rmdir_error
end_case "80 dead holder's lock folder with take.out: taken over, no dead folder left, no rmdir error"

# Reuse holds the lease of the reused device's slot. The real sim-lease runs beside the script, so the lease file shows the
# slot while the run goes on, and the run gives it back on every exit.
fresh; booted "iPhone Duo" $DUO2; run
need "exit code" rc_is 0
need "destination is the reused Duo of slot 2" dest_is "$DUO2"
need "no boot of the reused Duo" no_boot
need "the lease held during xcodebuild is slot 2" lease_at_xc_slot 2
need "lease released after the run" lease_released
end_case "81 reuse of the booted Duo of slot 2: no boot, and slot 2's lease is held during xcodebuild and released after"

# --hold -- CMD on a reused Duo: the child reads the lease file, so it sees slot 1's lease held for the whole hold.
fresh; booted "iPhone Duo" $DUO1; ARGS=(--hold -- "$hold_cmd" alpha beta); run; ARGS=(-scheme X)
need "exit code is the child's, 7" rc_is 7
need "the child got SIM_TEST_UDID for the reused Duo" test "$(cat "$work/cmd_udid" 2>/dev/null)" = "$DUO1"
need "the child sees slot 1's lease held" lease_at_cmd_slot 1
need "no boot" no_boot
need "lease released after the child ends" lease_released
end_case "82 --hold -- CMD on a reused Duo: the child runs under slot 1's lease, which is released after"

# A failed xcodebuild on a reused Duo: the run exits with xcodebuild's code, and the lease is still given back.
fresh; booted "iPhone Duo" $DUO1; run STUB_RC=5
need "exit code is xcodebuild's, 5" rc_is 5
need "the lease held during xcodebuild is slot 1" lease_at_xc_slot 1
need "lease released after the failed run" lease_released
end_case "83 reuse of the Duo of slot 1, xcodebuild exits 5: the exit code is kept, and the lease is held and given back"

# TERM during a reused run: the lease is held while xcodebuild runs and given back on TERM. A device it did not boot is
# never shut down.
fresh; booted "iPhone Duo" $DUO1
start_tool STUB_HANG=1 STUB_HANG_SECS=5
for _ in $(seq 1 20); do
  [[ -e $work/started ]] && break
  "$REAL_SLEEP" 0.5
done
need "xcodebuild started" test -e "$work/started"
kill -TERM -- "-$tool_pid" 2>/dev/null
finish_tool
need "exit is non-zero" test $rc -ne 0
need "the lease held during xcodebuild is slot 1" lease_at_xc_slot 1
need "lease released after TERM" lease_released
need "no shutdown of a device it did not boot" no_shutdown
end_case "84 TERM during a reused run: the lease is held during xcodebuild and given back, and nothing is shut down"

# A Duo that is booted but in no slot: the run names it on stderr with exactly one line.
UNSLOTTED_UDID=11111111-2222-4333-8444-555555555555
fresh; booted "iPhone Duo" $UNSLOTTED_UDID; run
need "exit code" rc_is 0
need "one stderr line" test "$(wc -l < "$work/run.err" | tr -d ' ')" -eq 1
end_case "85 reuse of a Duo in no slot: one stderr line"

fresh; booted "iPhone Duo" $UNSLOTTED_UDID; run
need "exit code" rc_is 0
need "destination is that UDID" dest_is "$UNSLOTTED_UDID"
need "steps are run only" steps_are "run "
need "no lease held during xcodebuild" lease_not_held_at_xc
end_case "86 control: a reused Duo in no slot runs with no lease"

echo "sim-test suite: $pass_n passed, $fail_n failed${failed:+: $failed}"
exit $fail

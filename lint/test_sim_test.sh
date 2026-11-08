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
#  - A booted Duo (its name contains "iPhone Duo") is reused by UDID: no boot, no shutdown. It takes the lease of its slot
#    for the run (see the lease line below). With two, the first
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
#  - One Mac-wide lock, state/sim-test.lock under the config dir, held while a run (a hold too) picks and boots its
#    device, then freed; the slot's lease holds the device until shutdown. It is freed on every exit, SIGHUP too. A live holder is waited for (SIM_TEST_LOCK_WAIT seconds, then refused). A dead holder is taken
#    over. A lock folder with no pid file counts as held for 60 s, then it is taken over.
#    A cleanup removes the lock only while its pid file names this run, so a take-over that wrote another pid is left
#    alone. A take-over whose put-back finds the lock re-created nests nothing inside it. A live holder that kill -0 cannot
#    signal (EPERM) is waited for, never taken over.
#  - Its own boot takes the lease for its role (`sim-lease take --device duo|pro --udid`) before simctl boot. At a 5-minute
#    load of 100 or a 1-minute load of 60 it waits, then exits 1 with no boot. The lease is released on every exit, INT and
#    TERM too. A reuse takes the lease of the slot that boots its UDID, held for the run; it skips the load bars, and a
#    booted device whose UDID is not in SLOT_UDID is leased as slot `other`. So `sim-lease status` names every user.
#  - A live run renews its lease every SIM_TEST_RENEW s. A renew that finds the lease gone (`sim-lease renew` exits 1) is
#    named once on stderr, however many renews fail, and the run goes on with its child's exit code.
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
#  - Before xcodebuild, every run reads the appearance (`simctl ui <udid> appearance`) and sets it to light when it reads
#    dark. A Duo whose fold reads open (`hinge -d <udid> get`) is closed (`hinge -d <udid> close`). Each change is one
#    stderr line that names it. With hinge not on PATH the run goes on, with one stderr line saying the fold was not
#    checked. No run calls simctl uninstall or erase.
# The last line is the tally: passed and failed counts, then the failing case names.
set -uo pipefail
root=$(cd "$(dirname "$0")/.." && pwd)
script=${SIM_TEST:-$root/bin/sim-test}
sim_lease=$(dirname "$script")/sim-lease
export SIM_LEASE_BIN=$sim_lease # the xcodebuild stub reads `sim-lease status` through it during a run
REAL_SLEEP=$(command -v sleep)
TEST_REAL_MV=$(command -v mv) # the mv stub below calls the real one through this
export TEST_REAL_MV
LIMIT=20 # hard timeout per run, in seconds: a red case cannot hang the suite
fail=0; pass_n=0; fail_n=0; failed=
why=
case_pass() { echo "PASS $1"; pass_n=$((pass_n + 1)); }
case_fail() { echo "FAIL $1: $2"; fail=1; fail_n=$((fail_n + 1)); failed=${failed:+$failed, }$1; }
end_case() { if [[ -z $why ]]; then case_pass "$1"; else case_fail "$1" "$why"; fi; why=; }
# need MSG CMD...: the first failed need names the case's failure.
need() { local msg=$1; shift; [[ -n $why ]] && return 0; "$@" || why=$msg; }
# skip_case NAME REASON: a case that cannot run on this host. It prints one SKIP line, and is neither a pass nor a fail.
skip_case() { echo "SKIP $1: $2"; }

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
base_path=$PATH
hingebin=$work/hingebin; mkdir -p "$hingebin" # hinge stands here, first on PATH, so no case runs a real hinge
export RUN=$work PATH="$stubs:$hingebin:$base_path"
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

# xcodebuild: logs its call. When the lock folder exists it records the lock (lock_during).
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
fi
lease="${CLAUDE_CONFIG_DIR:-$HOME/.claude}/state/sim-lease/leases.json"
[ -f "$lease" ] && cp "$lease" "$RUN/lease_at_xc"
[ -n "${SIM_LEASE_BIN:-}" ] && "$SIM_LEASE_BIN" status > "$RUN/status_at_xc" 2>&1
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
  boot) cp -f "$lease" "$RUN/lease_at_boot" 2>/dev/null; cat "$lock/pid" > "$RUN/lock_pid_at_boot" 2>/dev/null; [ -n "${STUB_BOOT_RC:-}" ] && exit "$STUB_BOOT_RC"
    if [ -n "${STUB_BOOT_HOLD:-}" ]; then : > "$RUN/boot_started"; n=0; while [ ! -e "$RUN/boot_release" ] && [ "$n" -lt 40 ]; do sleep 0.5; n=$((n + 1)); done; fi
    case $2 in "$STUB_PRO_UDID") name="iPhone 18 Pro" ;; *) name="iPhone Duo" ;; esac; echo "    $name ($2) (Booted) " > "$RUN/booted" ;;
  shutdown) cp -f "$lease" "$RUN/lease_at_shutdown" 2>/dev/null; : > "$RUN/booted" ;;
  ui) case "$*" in
    *" appearance light") echo light > "$RUN/appearance" ;;
    *appearance) if [ -f "$RUN/appearance" ]; then cat "$RUN/appearance"; else echo "${STUB_APPEARANCE:-light}"; fi ;;
  esac ;;
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
# mv: a stand-in only for the take-over window, when MV_HOOK is takeover, and only once per run (the marker mv_hooked).
# The first move of the lock folder is a dead holder's move. Before it, the lock's pid file names MV_PID_SEEN, a live pid
# that took the lock after the take-over's check. After it, another run re-creates the lock with MV_PID_NEW: the window
# the put-back must survive. Every other move is the real mv.
cat > "$stubs/mv" <<'SH'
#!/bin/sh
lock="$HOME/.claude/state/sim-test.lock"
if [ "${MV_HOOK:-}" = takeover ] && [ "$1" = "$lock" ] && [ ! -e "$RUN/mv_hooked" ]; then
  : > "$RUN/mv_hooked"
  printf '%s\n' "$MV_PID_SEEN" > "$lock/pid"
  "$TEST_REAL_MV" "$@" || exit $?
  /bin/mkdir "$lock" && printf '%s\n' "$MV_PID_NEW" > "$lock/pid"
  exit 0
fi
exec "$TEST_REAL_MV" "$@"
SH
# hinge: the Duo's fold, the command skills/ios-apps/SKILL.md names (`hinge -d <udid> open|close|half|<degrees>|get|posture`).
# The skill gives the verbs, not the text `get` prints. The shim prints the posture word, `open` or `closed`: the word the
# case expects, from the brief. The posture is $RUN/posture once a close or an open has run, else STUB_POSTURE (default closed).
cat > "$hingebin/hinge" <<'SH'
#!/bin/sh
echo "hinge $*" >> "$RUN/calls"
case "$*" in
  "-d "*" get") if [ -f "$RUN/posture" ]; then cat "$RUN/posture"; else echo "${STUB_POSTURE:-closed}"; fi ;;
  "-d "*" close") echo closed > "$RUN/posture" ;;
  "-d "*" open") echo open > "$RUN/posture" ;;
  *) exit 99 ;;
esac
SH
chmod +x "$hingebin/hinge"
# path_without_hinge: base_path without each directory that holds a hinge, so a missing-hinge case runs no real hinge.
path_without_hinge() {
  local IFS=: d out=
  for d in $base_path; do [ -x "$d/hinge" ] && continue; out=${out:+$out:}$d; done
  printf '%s' "$out"
}
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
cp -f "$HOME/.claude/state/sim-lease/leases.json" "$RUN/cmd_lease" 2>/dev/null
exit 7
SH
chmod +x "$hold_cmd"

booted() { printf '    %s (%s) (Booted) \n' "$1" "$2" >> "$booted_file"; }
# fresh: a clean fixture. It removes the lock folder, the crash dir and every observation file, so no lock or report
# leaks into the next case.
fresh() {
  : > "$calls"; : > "$booted_file"
  rm -f "$work/topcalls" "$work/started" "$work/xc_finished" "$work/watchdog_fired" "$work/lock_during" \
    "$work/lock_simctl" "$work/devices.json" \
    "$work/cmd_udid" "$work/cmd_args" "$work/cmd_lease"
  rm -rf "$work/home/.claude" "$crashdir" "$work/sweep_root"
  rm -f "$work/lease_at_boot" "$work/lease_at_xc" "$work/lease_at_shutdown" "$work/lock_pid_at_boot" "$work/status_at_xc" "$work/loadavg" "$work/load_reads" "$work/boot_started" "$work/boot_release" "$work/mv_hooked" "$work/posture" "$work/appearance"
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
# first_line TEXT: the number of the first call-log line that is exactly TEXT, or nothing. The sentinel xcodebuild stands
# for the first xcodebuild call. in_order TEXT...: each TEXT's first line comes after the one before it, and each occurs.
first_line() {
  if [[ $1 == xcodebuild ]]; then grep -n '^xcodebuild' "$calls" | head -n 1 | cut -d: -f1
  else grep -nFx -- "$1" "$calls" | head -n 1 | cut -d: -f1; fi
}
in_order() {
  local prev=0 pat n
  for pat in "$@"; do
    n=$(first_line "$pat")
    [[ -n $n && $n -gt $prev ]] || return 1
    prev=$n
  done
}
no_call() { ! has_call "$1"; }
# names_once TEXT: exactly one stderr line of the run has TEXT.
names_once() { [[ "$(grep -Fc -- "$1" "$work/run.err")" -eq 1 ]]; }
# fold_unchecked_once: exactly one stderr line says the fold was not checked.
fold_unchecked_once() { names_once "not checked" && grep -F -- "not checked" "$work/run.err" | grep -Fq fold; }
# no_reset_stderr: the run wrote no appearance or fold line.
no_reset_stderr() { ! grep -Eq 'appearance|fold' "$work/run.err"; }
no_uninstall_or_erase() { ! grep -Eq '^simctl (uninstall|erase)( |$)' "$calls"; }
# hinge_missing: the PATH a missing-hinge case gets has no hinge the tool could run.
hinge_missing() { ! PATH="$stubs:$(path_without_hinge)" command -v hinge >/dev/null 2>&1; }

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
lock_gone() { test ! -e "$lockdir"; }
lock_at() { grep -Fxq "$1 yes" "$work/lock_simctl"; }
# lock_pid_at_boot_is_tool: the lock names this tool's pid when the device boots. The lock is held there, not at xcodebuild.
lock_pid_at_boot_is_tool() { [[ "$(cat "$work/lock_pid_at_boot" 2>/dev/null)" == "$tool_pid" ]]; }
# lock_at_pick_and_boot: the lock is held at the list and the boot, and free at the shutdown (gap-5 contract).
lock_at_pick_and_boot() { grep -Eq '^list yes$' "$work/lock_simctl" && grep -Eq '^boot yes$' "$work/lock_simctl" && ! grep -Eq '^shutdown yes$' "$work/lock_simctl"; }
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
lease_at_shutdown_holds() { lease_holds "$work/lease_at_shutdown" "$tool_pid"; }
cmd_lease_holds() { lease_holds "$work/cmd_lease" "$tool_pid"; }
lease_at_xc_slot() { lease_slot "$work/lease_at_xc" "$tool_pid" "$1"; }
# status_at_xc_has SLOT PID: the status the xcodebuild stub read during the run has a lease line for SLOT and PID. The
# pid is a whole word: the space after it ends the number. status_at_xc_udid also names the UDID on that line.
status_at_xc_has() { grep -Eq "^lease slot $1 pid $2 " "$work/status_at_xc" 2>/dev/null; }
status_at_xc_udid() { grep -E "^lease slot $1 pid $2 " "$work/status_at_xc" 2>/dev/null | grep -Fq "udid $3"; }
# lease_released: the state after the run holds no lease of this tool. Exit 1 is the only pass, so a broken file fails.
lease_released() { lease_holds "$lease_file" "$tool_pid"; [ $? -eq 1 ]; }
no_lease_file() { [ ! -e "$lease_file" ]; }
# drop_lease: leases.json holds no lease, as a holder finds it once its lease is gone. The next renew of the run exits 1.
drop_lease() { printf '%s\n' '{"leases": [], "queue": []}' > "$lease_file"; }
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
# hold_slot2: a second live holder, taken while slot 1 is held, is granted Duo slot 2. release_slot2 stops it.
slot2_holder=
hold_slot2() {
  sleep 600 > /dev/null 2>&1 &
  slot2_holder=$!
  need "the second holder is granted Duo slot 2" test "$(env -u CLAUDE_CONFIG_DIR -u CI -u GITHUB_ACTIONS HOME="$work/home" \
    "$sim_lease" take --device duo --pid "$slot2_holder" --wait 1 2>/dev/null)" = 2
}
release_slot2() {
  if [[ -n $slot2_holder ]]; then kill "$slot2_holder" 2>/dev/null; wait "$slot2_holder" 2>/dev/null; fi
  slot2_holder=
}
# hold_then_term ARG...: runs the tool with ARG... (a --hold run with no CMD). It waits for the holding line, records
# whether this tool's pid holds the slot's lease (lease_hold_ok), then sends TERM to its group. The wait is for the
# line or for the tool to end, never a fixed delay.
lease_hold_ok=
hold_then_term() {
  fresh
  ARGS=("$@"); start_tool; ARGS=(-scheme X)
  for _ in $(seq 1 20); do
    grep -Fq "sim-test: holding" "$work/run.std" && break
    kill -0 "$tool_pid" 2>/dev/null || break
    "$REAL_SLEEP" 0.5
  done
  lease_hold_ok=; lease_holds "$lease_file" "$tool_pid" && lease_hold_ok=1
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
need "takes slot 1's lease" lease_at_xc_slot 1
end_case "1 booted Duo is reused by UDID: no boot, no shutdown; takes slot 1's lease"

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
need "the slot's lease is held through xcodebuild" lease_at_xc_holds
need "lock gone after the pass" lock_gone
end_case "16 reuse path: no top; takes the lock first, holds the slot's lease through xcodebuild, frees the lock"

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

# Case 26 (gap-5 contract, owner 2026-11-02 14:23 CST, applied 2026-11-07 13:41 CST): the lease, not the lock, is held through
# xcodebuild and to the shutdown. The lock covers the list and the boot only. The lease checks come first, so a mutant that
# gives the lease back early fails on the lease, not on the lock.
fresh; run
need "the slot's lease is held through xcodebuild" lease_at_xc_holds
need "the slot's lease is still held at the shutdown" lease_at_shutdown_holds
need "the lock is not held during xcodebuild" test ! -e "$work/lock_during"
need "the lock is held at the list and the boot, and free at the shutdown" lock_at_pick_and_boot
need "the lock is made by one mkdir (no -p) before the first simctl call" mkdir_lock_first
need "the slot's lease is given back after the run" lease_released
end_case "26 booted by me: the lease, not the lock, is held through xcodebuild and to the shutdown; the lock covers list and boot only"

fresh; run
need "exit code" rc_is 0
need "the slot's lease is held through xcodebuild" lease_at_xc_holds
need "lock gone after a pass" lock_gone
end_case "27 lock gone after a pass, with the slot's lease held through xcodebuild"

fresh; run STUB_RC=65
need "exit 65 passes through" rc_is 65
need "the slot's lease is held through xcodebuild" lease_at_xc_holds
need "lock gone after an xcodebuild failure" lock_gone
end_case "28 lock gone after an xcodebuild failure"

sig_case INT
need "the slot's lease is held through xcodebuild" lease_at_xc_holds
need "lock gone after INT" lock_gone
end_case "29 lock gone after INT"

sig_case TERM
need "the slot's lease is held through xcodebuild" lease_at_xc_holds
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
need "the slot's lease is held through xcodebuild" lease_at_xc_holds
need "pid in the lock is the tool's pid at boot" lock_pid_at_boot_is_tool
need "lock gone after the run" lock_gone
end_case "33 stale lock (dead pid) is taken over, rewritten to the tool's pid at boot, freed after; the slot's lease held through xcodebuild"

fresh; holder_ends_after 1; hold_lock "$holder_pid"; run SIM_TEST_LOCK_WAIT=10
need "exit code" rc_is 0
need "waited: stderr names the holder's pid" grep -Fq "$holder_pid" "$work/run.err"
need "steps are boot run shutdown" steps_are "boot run shutdown "
need "the slot's lease is held through xcodebuild" lease_at_xc_holds
need "pid in the lock is the tool's pid at boot" lock_pid_at_boot_is_tool
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
need "the slot's lease is held through xcodebuild" lease_at_xc_holds
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
need "lock taken over: the slot's lease is held through xcodebuild" lease_at_xc_holds
need "lock taken over: pid in the lock is the tool's pid at boot" lock_pid_at_boot_is_tool
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
need "the slot's lease is held through xcodebuild" lease_at_xc_holds
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
need "slot 1's lease is held during xcodebuild" lease_at_xc_slot 1
need "the lease is released after the run" lease_released
end_case "50 reuse path: takes slot 1's lease, held during xcodebuild and released after"

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

# Control: the pro role reuses the booted 18 Pro, as it did before the role flag existed. The reuse takes the pro lease
# (owner, 2026-11-07 12:31 CST, page item 336).
fresh; booted "iPhone 18 Pro" $PRO; ARGS=(--device pro -scheme X); run; ARGS=(-scheme X)
need "exit code" rc_is 0
need "steps are run only" steps_are "run "
need "takes the pro lease" lease_at_xc_slot pro
end_case "61 control: pro run with the 18 Pro booted reuses it, with no boot"

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
need "the slot's lease is held during the hold, by this tool's pid" test "$lease_hold_ok" = 1
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
need "the slot's lease is held while the child runs, by this tool's pid" cmd_lease_holds
need "lock freed after the hold" lock_gone
end_case "68 the slot's lease held through a --hold run: the child sees the lease with this tool's pid, and the lock is freed after"

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

# Case 78: a Duo booted during the wait, then the pro holder dies: the queued duo run reuses that Duo after its grant, and
# holds the lease of its slot during xcodebuild (owner, 2026-11-07 12:31 CST, page item 336).
pro_dies_during_duo_wait duo
need "exit code" rc_is 0
need "steps are run only" steps_are "run "
need "destination is the booted Duo" dest_is "$DUO2"
need "lease held during xcodebuild" lease_at_xc_holds
need "no shutdown" no_shutdown
end_case "78 a Duo booted during the wait, then the pro holder dies: the queued run reuses it and holds its lease through xcodebuild"

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

# Cases 81 to 84: a reuse takes the lease of the slot that boots its UDID, as an own boot does. Each run's status is read
# by the xcodebuild stub, so the lease is checked while the run holds it.
fresh; booted "iPhone Duo" $DUO1; run
need "destination is the booted Duo" dest_is "$DUO1"
need "steps are run only" steps_are "run "
need "status during the run names slot 1 for this pid" status_at_xc_has 1 "$tool_pid"
need "status during the run names the UDID" status_at_xc_udid 1 "$tool_pid" "$DUO1"
need "exit code" rc_is 0
need "no lease after the run" lease_released
end_case "81 reuse: sim-lease status shows slot 1 for the sim-test pid, with its UDID, during the run; gone after"

fresh; booted "iPhone Duo" $DUO1; set_load "{ 60.00 0.50 0.50 }"; run
need "destination is the booted Duo" dest_is "$DUO1"
need "exit code: the reuse is not refused at a 1-minute load of 60" rc_is 0
need "slot 1's lease is held during the run at a 1-minute load of 60" lease_at_xc_slot 1
end_case "82 reuse at a 1-minute load of 60: takes slot 1's lease and runs"

# mentions_err PID: the pid is a whole word on stderr.
mentions_err() { grep -Ewq -- "$1" "$work/run.err"; }
fresh; booted "iPhone Duo" $OTHER; run
need "destination is the other Duo's UDID" dest_is "$OTHER"
need "steps are run only" steps_are "run "
need "exit code" rc_is 0
need "status during the run names slot other for this pid" status_at_xc_has other "$tool_pid"
need "status during the run names that Duo's UDID" status_at_xc_udid other "$tool_pid" "$OTHER"
end_case "84 reuse of a booted Duo not in SLOT_UDID: leased as slot other, its UDID shown in status"

# Cases 85 to 87: the lock. live_pid prints the pid of a sleep that outlives this subshell; the case kills it.
live_pid() { sh -c 'sleep 600 > /dev/null 2>&1 & echo $!'; }
# no_nested_dead: no dead-holder folder sits inside the lock folder.
no_nested_dead() { [ -z "$(ls -d "$lockdir"/*.dead.* 2>/dev/null)" ]; }

# Case 85 (gap-5 contract): the lock is held while the run picks and boots, so this case ends the run during its boot. The
# run's cleanup takes only its own lock: a pid file that names another live pid is left, with its folder.
fresh; ARGS=(-scheme X); start_tool STUB_BOOT_HOLD=1
need "the boot is in flight" poll_for 20 test -e "$work/boot_started"
need "the run holds the lock during its boot" test "$(cat "$lockdir/pid" 2>/dev/null)" = "$tool_pid"
new_holder=$(live_pid)
printf '%s\n' "$new_holder" > "$lockdir/pid"
need "scope: the pid file names the other pid before the run ends" test "$(cat "$lockdir/pid")" = "$new_holder"
kill -TERM -- "-$tool_pid" 2>/dev/null
finish_tool
ARGS=(-scheme X)
need "the lock folder is still there after the run's cleanup" test -d "$lockdir"
need "the pid file still names the other pid" test "$(cat "$lockdir/pid" 2>/dev/null)" = "$new_holder"
kill "$new_holder" 2>/dev/null
end_case "85 cleanup takes only its own lock: ended during its boot, a pid file that names another live pid is left, with its folder"

# The take-over window: the lock is taken by a dead holder's move, a live pid takes it before the put-back, and another
# run re-creates it in between. The put-back must not nest the moved folder inside the new lock.
dead=$(dead_pid); seen_pid=$(live_pid); new_pid=$(live_pid)
fresh; hold_lock "$dead"; run MV_HOOK=takeover MV_PID_SEEN=$seen_pid MV_PID_NEW=$new_pid
need "the take-over window opened: the mv hook ran" test -e "$work/mv_hooked"
need "no dead-holder folder is nested in the lock" no_nested_dead
need "the lock's pid file names the live holder" test "$(cat "$lockdir/pid" 2>/dev/null)" = "$new_pid"
need "exit 1: the live holder keeps the lock" rc_is 1
kill "$seen_pid" "$new_pid" 2>/dev/null
end_case "86 take-over put-back: a lock re-created in the window is not nested, and its live holder keeps it"

# EPERM: a live holder that kill -0 cannot signal is waited for, not taken over. As root, the holder is a root process and
# the tool runs as nobody. Otherwise the holder is pid 1, which belongs to root, and the tool runs as this user.
eperm_user='' eperm_holder='' eperm_reason=''
if [[ $(id -u) -eq 0 ]]; then
  eperm_user=nobody
  if id nobody >/dev/null 2>&1 && command -v setpriv >/dev/null 2>&1; then eperm_holder=$(live_pid)
  else eperm_reason="this is root, with no nobody user or no setpriv to run the tool as"; fi
else
  eperm_holder=1
fi
# as_eperm_user CMD...: runs CMD as the user that cannot signal the holder.
as_eperm_user() { if [[ -n $eperm_user ]]; then setpriv --reuid="$eperm_user" --regid=nogroup --clear-groups "$@"; else "$@"; fi; }
if [[ -z $eperm_reason ]]; then
  probe=$(as_eperm_user sh -c 'kill -0 "$1" 2>&1' sh "$eperm_holder")
  [[ $probe == *"not permitted"* ]] || eperm_reason="kill -0 from this user does not give EPERM on pid $eperm_holder"
fi
if [[ -n $eperm_reason ]]; then
  skip_case "87 EPERM from kill -0: a live holder this user cannot signal is waited for" "$eperm_reason"
else
  fresh
  eperm_tree=$work/eperm
  /bin/mkdir -p "$eperm_tree/bin" "$eperm_tree/hooks"
  cp "$script" "$eperm_tree/bin/sim-test"; cp "$sim_lease" "$eperm_tree/bin/sim-lease"; cp "$root/hooks/_nowindow.py" "$eperm_tree/hooks/"
  chmod +x "$eperm_tree/bin/sim-test" "$eperm_tree/bin/sim-lease"
  /bin/mkdir -p "$lockdir"; printf '%s\n' "$eperm_holder" > "$lockdir/pid"
  saved_script=$script
  if [[ -n $eperm_user ]]; then
    chown -R "$eperm_user" "$work/home"
    printf '#!/bin/sh\nexec setpriv --reuid=%s --regid=nogroup --clear-groups "%s" "$@"\n' "$eperm_user" \
      "$eperm_tree/bin/sim-test" > "$eperm_tree/as_user"
    chmod +x "$eperm_tree/as_user"; script=$eperm_tree/as_user
  else
    script=$eperm_tree/bin/sim-test
  fi
  ARGS=(-scheme X); run; ARGS=(-scheme X)
  script=$saved_script
  need "the lock folder is still there: the run waited for the holder" test -d "$lockdir"
  need "the pid file still names the holder" test "$(cat "$lockdir/pid" 2>/dev/null)" = "$eperm_holder"
  need "no dead-holder folder is left beside the lock" no_dead_folder
  need "exit 1 at the lock wait limit" rc_is 1
  need "stderr names the holder's pid" mentions_err "$eperm_holder"
  [[ -n $eperm_user ]] && chown -R root "$work/home"
  end_case "87 EPERM from kill -0: a live holder this user cannot signal is waited for, not taken over"
fi
[[ -n $eperm_user && -n $eperm_holder ]] && kill "$eperm_holder" 2>/dev/null

# Cases 88 to 94: before xcodebuild a run sets the appearance to light and a Duo's fold to closed, and names each change on
# stderr once. The defaults are light and closed, so the cases above see no change.
fresh; booted "iPhone Duo" $DUO1; run STUB_APPEARANCE=dark
need "destination is the booted Duo" dest_is "$DUO1"
need "exit code" rc_is 0
need "appearance is read, then set to light, before xcodebuild" in_order "simctl ui $DUO1 appearance" "simctl ui $DUO1 appearance light" xcodebuild
need "one stderr line names appearance dark -> light" names_once "appearance dark -> light"
need "no simctl uninstall or erase" no_uninstall_or_erase
end_case "88 reuse: appearance dark is set to light before xcodebuild, and one stderr line names the change"

fresh; run STUB_APPEARANCE=dark
need "steps are boot run shutdown" steps_are "boot run shutdown "
need "destination is slot 1's UDID" dest_is "$DUO1"
need "exit code" rc_is 0
need "appearance is set to light after the boot and before xcodebuild" in_order "simctl boot $DUO1" "simctl ui $DUO1 appearance light" xcodebuild
need "one stderr line names appearance dark -> light" names_once "appearance dark -> light"
need "no simctl uninstall or erase" no_uninstall_or_erase
end_case "89 own boot: appearance dark is set to light after the boot and before xcodebuild, one stderr line names it"

fresh; booted "iPhone Duo" $DUO1; run STUB_POSTURE=open
need "destination is the booted Duo" dest_is "$DUO1"
need "exit code" rc_is 0
need "the fold is read, then closed, before xcodebuild" in_order "hinge -d $DUO1 get" "hinge -d $DUO1 close" xcodebuild
need "one stderr line names open -> closed" names_once "open -> closed"
need "no simctl uninstall or erase" no_uninstall_or_erase
end_case "90 reuse of a Duo: an open fold is closed before xcodebuild, and one stderr line names the change"

fresh; run STUB_POSTURE=open
need "steps are boot run shutdown" steps_are "boot run shutdown "
need "destination is slot 1's UDID" dest_is "$DUO1"
need "exit code" rc_is 0
need "the fold is closed after the boot and before xcodebuild" in_order "simctl boot $DUO1" "hinge -d $DUO1 close" xcodebuild
need "one stderr line names open -> closed" names_once "open -> closed"
end_case "91 own boot of a Duo: an open fold is closed after the boot and before xcodebuild, one stderr line names it"

fresh; booted "iPhone Duo" $DUO1; run PATH="$stubs:$(path_without_hinge)"
need "hinge is not on the tool's PATH" hinge_missing
need "destination is the booted Duo" dest_is "$DUO1"
need "exit code: the run goes on" rc_is 0
need "steps are run only" steps_are "run "
need "one stderr line says the fold was not checked" fold_unchecked_once
end_case "92 hinge not on PATH: the run goes on, and one stderr line says the fold was not checked"

fresh; booted "iPhone Duo" $DUO1; run
need "exit code" rc_is 0
need "appearance is not set" no_call "simctl ui $DUO1 appearance light"
need "the fold is not closed" no_call "hinge -d $DUO1 close"
need "stderr has no reset line" no_reset_stderr
end_case "93 control: a closed fold and light appearance: nothing is set, and no line prints"

fresh; run STUB_APPEARANCE=dark STUB_POSTURE=open
need "exit code" rc_is 0
need "no simctl uninstall or erase in a run that resets" no_uninstall_or_erase
end_case "94 control: a run that resets appearance and fold calls no simctl uninstall or erase"

# Case 95: the duo run's own boot is granted slot 1, then the rescan finds Duo 2 booted and free, so the run reuses Duo 2. The
# lease the run holds during xcodebuild is Duo 2's slot, 2: status names slot 2 with Duo 2's UDID, and not slot 1.
no_status_slot1() { ! status_at_xc_has 1 "$tool_pid"; }
pro_dies_during_duo_wait duo
need "exit code" rc_is 0
need "steps are run only" steps_are "run "
need "destination is Duo 2" dest_is "$DUO2"
need "status during the run names slot 2 for this pid, with Duo 2's UDID" status_at_xc_udid 2 "$tool_pid" "$DUO2"
need "status during the run does not name slot 1 for this pid" no_status_slot1
end_case "95 duo run granted slot 1, then Duo 2 found booted by the rescan: holds slot 2 during the run, named in status with Duo 2's UDID"

# Cases 96 and 97: hinge get prints an angle. 0.0 is a closed fold, so the run runs no close. 180.0 is open, so the run closes
# it before xcodebuild, and one stderr line names the change. The closed word is case 93.
no_fold_line() { ! grep -Fq fold "$work/run.err"; }
fresh; booted "iPhone Duo" $DUO1; run STUB_POSTURE=0.0
need "destination is the booted Duo" dest_is "$DUO1"
need "exit code" rc_is 0
need "the fold is not closed: no hinge close" no_call "hinge -d $DUO1 close"
need "stderr has no fold line" no_fold_line
end_case "96 hinge get prints 0.0: a closed fold, so no close and no fold line"

fresh; booted "iPhone Duo" $DUO1; run STUB_POSTURE=180.0
need "destination is the booted Duo" dest_is "$DUO1"
need "exit code" rc_is 0
need "the fold is closed before xcodebuild" in_order "hinge -d $DUO1 close" xcodebuild
need "one stderr line names fold 180.0 -> closed" names_once "fold 180.0 -> closed"
end_case "97 hinge get prints 180.0: close runs before xcodebuild, and one stderr line names fold 180.0 -> closed"

# Cases 98 to 100: two duo runs at once, and a booted Duo whose slot is leased (decision sim-lease-tool). A duo run reuses
# a booted Duo only when that Duo's slot has no live lease. Otherwise it takes a fresh lease (slot 2 under the bars) and
# boots that slot. A reuse queues with a `reuse` field in leases.json, so queue_state reads a pid's queue entry while it waits.
queue_state() { python3 -I -c 'import json, sys
try:
    data = json.load(open(sys.argv[1]))
except (OSError, ValueError):
    print("absent"); sys.exit(0)
for e in data.get("queue", []):
    if str(e.get("pid")) == sys.argv[2]:
        print("reuse:" + e["reuse"] if e.get("reuse") else "queued"); sys.exit(0)
print("absent")' "$lease_file" "$1"; }
tool_settled() { [[ $(queue_state "$tool_pid") != absent ]] || tool_ended; }
b_pid=
# start_second [VAR=value...]: a second run with its own run folder, the same HOME, and Duo 1 listed as booted in its folder.
start_second() {
  rm -rf "$work/runB"; /bin/mkdir -p "$work/runB"
  printf '    iPhone Duo (%s) (Booted) \n' "$DUO1" > "$work/runB/booted"
  env -u CLAUDE_CONFIG_DIR -u CI -u GITHUB_ACTIONS HOME="$work/home" RUN="$work/runB" SIM_TEST_CRASH_DIR="$crashdir" \
    SIM_TEST_POLL=1 SIM_TEST_LOCK_WAIT=2 SIM_LEASE_POLL=1 "$@" "$script" "${ARGS[@]}" > "$work/b.std" 2> "$work/b.err" &
  b_pid=$!
}
b_calls_has() { grep -Fq -- "$1" "$work/runB/calls" 2>/dev/null; }
b_has_line() { grep -Fxq -- "$1" "$work/runB/calls" 2>/dev/null; }
b_no_duo1() { ! b_calls_has "-destination platform=iOS Simulator,id=$DUO1"; }
b_holds_slot2() { grep -E "^lease slot 2 pid $b_pid " "$work/runB/status_at_xc" 2>/dev/null | grep -Fq "udid $DUO2"; }
both_alive() { kill -0 "$tool_pid" 2>/dev/null && kill -0 "$b_pid" 2>/dev/null; }
b_ended() { local st; st=$(ps -o stat= -p "$b_pid" 2>/dev/null); [[ -z $st || $st == Z* ]]; }
b_settled() { [[ -e "$work/runB/started" ]] || [[ $(queue_state "$b_pid") != absent ]] || b_ended; }

fresh; ARGS=(-scheme X); start_tool STUB_HANG=1 STUB_HANG_SECS=12
need "run A is in xcodebuild on Duo 1" poll_for 20 test -e "$work/started"
need "the Mac lock is free while A is up and leased" test ! -e "$work/lock_during"
need "run A's status names slot 1 for its pid" status_at_xc_has 1 "$tool_pid"
start_second STUB_HANG=1 STUB_HANG_SECS=12 SIM_LEASE_WAIT=4
poll_for 20 b_settled
need "run B does not queue a reuse of Duo 1 while A's lease is live" test "$(queue_state "$b_pid")" != "reuse:$DUO1"
need "run B does not run its xcodebuild on Duo 1" b_no_duo1
need "run B boots Duo 2 beside A's slot 1" b_has_line "simctl boot $DUO2"
need "run B runs its xcodebuild on Duo 2" b_calls_has "-destination platform=iOS Simulator,id=$DUO2"
need "run B holds slot 2 with Duo 2's UDID in status" b_holds_slot2
need "both runs are running at once" both_alive
kill -TERM "$b_pid" 2>/dev/null; wait "$b_pid" 2>/dev/null
kill -TERM -- "-$tool_pid" 2>/dev/null; finish_tool
ARGS=(-scheme X)
end_case "98 two duo runs at once: B boots Duo 2 beside A's slot 1, holds slot 2 in status, never queues or runs on Duo 1"

fresh; booted "iPhone Duo" $DUO1; hold_slot1
ARGS=(-scheme X); start_tool SIM_LEASE_WAIT=4
poll_for 20 tool_settled
need "run B does not queue a reuse of Duo 1 while slot 1 is leased" test "$(queue_state "$tool_pid")" != "reuse:$DUO1"
finish_tool
need "run B boots Duo 2, the slot-2 device" has_call "simctl boot $DUO2"
need "run B runs its xcodebuild on Duo 2" dest_is "$DUO2"
need "run B holds slot 2 with Duo 2's UDID in status" status_at_xc_udid 2 "$tool_pid" "$DUO2"
need "run B ends with exit 0" rc_is 0
release_slot1
ARGS=(-scheme X)
end_case "99 a booted Duo whose slot is leased, at 5-minute load under 60: B takes slot 2 and boots Duo 2, no reuse of Duo 1"

fresh; booted "iPhone Duo" $DUO1; hold_slot1; set_load "{ 0.50 60.00 0.50 }"
ARGS=(-scheme X); start_tool SIM_LEASE_WAIT=4
poll_for 20 tool_settled
need "run B queues for a lease with no reuse of Duo 1 at 5-minute load 60" test "$(queue_state "$tool_pid")" = queued
finish_tool
need "run B is refused at the lease wait limit: exit 1" rc_is 1
need "run B's refusal names the 5-minute load" grep -Fq "5-min 60.00" "$work/run.err"
need "run B's refusal names the pid that holds slot 1" mentions_err "$slot_holder"
need "run B boots nothing" no_boot
need "run B runs no xcodebuild" no_xcodebuild
release_slot1
ARGS=(-scheme X)
end_case "100 a booted Duo whose slot is leased, at 5-minute load 60: B waits in queue with no reuse, refused at the lease wait limit"

# Cases 101 and 102: the time limit of a run (SIM_TEST_MAX_RUN, default 1800 s, unmeasured). A run whose xcodebuild child is
# still running after the limit stops it, exits 124, and cleans up as a hold does: it shuts down the Duo it booted, gives its
# lease back and frees the lock. The limit is small here, and the xcodebuild stub hangs longer than it.
fresh; ARGS=(-scheme X); run SIM_TEST_MAX_RUN=1 STUB_HANG=1 STUB_HANG_SECS=8
need "the run exits 124 when xcodebuild is still running after SIM_TEST_MAX_RUN" rc_is 124
need "xcodebuild is stopped, so it never finishes" test ! -e "$work/xc_finished"
need "the Duo the run booted is shut down" has_call "simctl shutdown $DUO1"
need "the lease is given back" lease_released
need "the lock folder is gone" test ! -d "$lockdir"
ARGS=(-scheme X)
end_case "101 a run past SIM_TEST_MAX_RUN: xcodebuild is stopped, exit 124, the booted Duo shut down, lease and lock released"

# Control: a run inside its limit is not stopped. Its xcodebuild returns in 2 s, under a 6 s limit.
fresh; ARGS=(-scheme X); run SIM_TEST_MAX_RUN=6 STUB_HANG=1 STUB_HANG_SECS=2
need "a run inside its limit exits 0" rc_is 0
need "xcodebuild finished on its own" test -e "$work/xc_finished"
need "one xcodebuild call" test "$(grep -c ^xcodebuild "$calls")" -eq 1
ARGS=(-scheme X)
end_case "102 a run inside SIM_TEST_MAX_RUN is not stopped: exit 0, xcodebuild finishes"

# Cases 103 and 104: both Duos are booted and each is leased by another live pid. A duo run must wait in the queue for a
# lease, not exit at the cap check. It reuses whichever Duo frees first, or exits 1 at the lease wait limit.
fresh; booted "iPhone Duo" $DUO1; booted "iPhone Duo" $DUO2; hold_slot1; hold_slot2
ARGS=(-scheme X); start_tool SIM_LEASE_WAIT=20
poll_for 20 tool_settled
need "both Duos leased by other live pids: the run queues for a lease, not exit at the cap check" test "$(queue_state "$tool_pid")" != absent
release_slot2
poll_for 30 tool_ended
finish_tool
need "run reuses Duo 2, the Duo whose holder ended first" dest_is "$DUO2"
need "run boots nothing" no_boot
need "exit code" rc_is 0
release_slot1
ARGS=(-scheme X)
end_case "103 both Duos booted, each leased by another live pid: the run queues, then reuses Duo 2 when its holder ends; exit 0"

fresh; booted "iPhone Duo" $DUO1; booted "iPhone Duo" $DUO2; hold_slot1; hold_slot2
ARGS=(-scheme X); start_tool SIM_LEASE_WAIT=4
poll_for 20 tool_settled
need "both Duos leased by other live pids: the run queues for a lease" test "$(queue_state "$tool_pid")" != absent
finish_tool
need "exit 1 at the lease wait limit" rc_is 1
need "no xcodebuild call" no_xcodebuild
need "no boot" no_boot
release_slot1
release_slot2
ARGS=(-scheme X)
end_case "104 both Duos booted, each leased by another live pid: the run queues, then exits 1 at the lease wait limit, with no xcodebuild and no boot"

# Case 105: a run whose xcodebuild outlives SIM_LEASE_MAX keeps its slot-1 lease. The run renews it every SIM_TEST_RENEW
# seconds (owner, 2026-11-07 13:00: a holder that stops answering loses its turn). Here SIM_LEASE_MAX=3, renew every 1 s,
# and xcodebuild runs 6 s. At second 5 a take for Duo 1's slot is not granted while the run lives. The 5 s is the
# stimulus's timing; the assert is the take's outcome.
fresh; start_tool SIM_LEASE_MAX=3 SIM_TEST_RENEW=1 STUB_HANG=1 STUB_HANG_SECS=6
need "run A is in xcodebuild" poll_for 20 test -e "$work/started"
"$REAL_SLEEP" 5
need "run A is still in xcodebuild at second 5" test ! -e "$work/xc_finished"
sleep 600 > /dev/null 2>&1 &
second_pid=$!
second_rc=0
env -u CLAUDE_CONFIG_DIR -u CI -u GITHUB_ACTIONS HOME="$work/home" SIM_LEASE_MAX=3 "$sim_lease" take --device duo \
  --reuse "$DUO1" --pid "$second_pid" --wait 0 > /dev/null 2>&1 || second_rc=$?
need "a take for Duo 1 at second 5 is not granted while run A lives" test "$second_rc" -eq 1
finish_tool
need "run A exits 0" rc_is 0
kill "$second_pid" 2>/dev/null; wait "$second_pid" 2>/dev/null
end_case "105 SIM_TEST_RENEW keeps run A's slot-1 lease past SIM_LEASE_MAX while its xcodebuild runs: a take for Duo 1 at second 5 is not granted"

# Case 106: a renew that finds its lease gone (sim-lease renew exits 1) is named once on stderr, however many renews fail,
# and the run exits with its child's code. The lease is dropped from leases.json once xcodebuild runs. The child then runs
# 5 s more, about five renew periods at SIM_TEST_RENEW=1, so several renews fail. STUB_RC=7 is the child's exit code.
fresh; ARGS=(-scheme X); start_tool SIM_TEST_RENEW=1 STUB_HANG=1 STUB_HANG_SECS=5 STUB_RC=7
need "run is in xcodebuild" poll_for 20 test -e "$work/started"
need "the run holds its lease when xcodebuild starts" lease_at_xc_holds
drop_lease
finish_tool
need "the run exits with its child's exit code, 7" rc_is 7
need "xcodebuild ran to its end while the renews failed" test -e "$work/xc_finished"
need "the lost lease is named on exactly one stderr line" names_once "lease lost"
ARGS=(-scheme X)
end_case "106 a renew that finds its lease gone names the loss once, however many renews fail; the run exits with its child's code"

echo "sim-test suite: $pass_n passed, $fail_n failed${failed:+: $failed}"
exit $fail

#!/usr/bin/env bash
# Tests for bin/ios-ship, both jobs. CI runs this under /bin/bash (3.2) and under bash on PATH (shell-macos job).
# IOS_SHIP=PATH picks the script under test; the default is bin/ios-ship in this repo. A red run points it at a mutant.
# Every case builds a throwaway world in one run folder: a bare origin, a clone, a config, and stubs on PATH for
# xcodebuild, xcodegen, xcrun, osascript, date, cp and git. The tool runs from its own clean repo, away from the fixture.
# Temp files follow decisions/test-temp-standard.md: one run folder <pid>-<UUID> under one temp root, and the first
# request of a run sweeps siblings older than a day. All IDs here are fake.
# The last line is the tally: passed and failed counts, then the failing case names.
set -uo pipefail
root=$(cd "$(dirname "$0")/.." && pwd)
script=${IOS_SHIP:-$root/bin/ios-ship}
fail=0; pass_n=0; fail_n=0; failed=
why=
case_pass() { echo "PASS $1"; pass_n=$((pass_n + 1)); }
case_fail() { echo "FAIL $1: $2"; fail=1; fail_n=$((fail_n + 1)); failed=${failed:+$failed, }$1; }
end_case() { if [[ -z $why ]]; then case_pass "$1"; else case_fail "$1" "$why"; fi; why=; }
# need MSG CMD...: the first failed need names the case's failure.
need() { local msg=$1; shift; [[ -n $why ]] && return 0; "$@" || why=$msg; }
not() { ! "$@"; }

REAL_GIT=$(command -v git); REAL_DATE=$(command -v date); REAL_CP=$(command -v cp); REAL_SLEEP=$(command -v sleep); export REAL_GIT REAL_DATE REAL_CP REAL_SLEEP
# The owner's shell may export these. Unset here, so only a case's own prefix assignment reaches the tool.
unset TEAM_ID DEVICE_UDID ASC_KEY_PATH ASC_KEY_ID ASC_ISSUER_ID PHONE_APPS_JSON

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
uuid=$(uuidgen | tr 'A-Z' 'a-z'); [[ -n $uuid ]] || exit 1
work=$tmp_root/$$-$uuid
mkdir "$work" || exit 1
trap 'chmod -R u+rwx "$work" 2>/dev/null; rm -rf "$work"' EXIT
# IOS_SHIP_TEST_PROBE=1: print this run's folder and exit, so a case can check that teardown removed it.
if [[ -n ${IOS_SHIP_TEST_PROBE:-} ]]; then echo "run folder: $work"; exit 0; fi

stubs=$work/stubs; mkdir -p "$stubs" "$work/tmp" "$work/elsewhere" "$work/secrets" "$work/home"
out=$work/out; calls=$work/calls; rc=0
g() { "$REAL_GIT" -C "$1" -c user.name=t -c user.email=t@t "${@:2}" >> "$work/git.log" 2>&1; }

# ---- stubs ----
# git: logs clone, fetch and reset (the call-order cases read them), then runs real git.
printf '#!/usr/bin/env bash\ncase ${1:-} in clone|fetch|reset) echo "$1" >> "${CALL_LOG:-/dev/null}" ;; esac\nexec "$REAL_GIT" "$@"\n' > "$stubs/git"
# date: each `date -u +%Y%m%d%H%M` returns a new value, so a build number taken twice differs.
cat > "$stubs/date" <<'SH'
#!/usr/bin/env bash
if [[ ${1:-} == -u && ${2:-} == +%Y%m%d%H%M ]]; then
  n=$(cat "$DATE_COUNTER" 2>/dev/null || echo 0); n=$((n + 1)); echo "$n" > "$DATE_COUNTER"; echo $((202601010000 + n)); exit 0
fi
exec "$REAL_DATE" "$@"
SH
# xcodegen: XCODEGEN_TOUCH=FILE appends to FILE, as a generator that edits a tracked file does.
printf '#!/usr/bin/env bash\necho xcodegen >> "$CALL_LOG"\necho "xcodegen $*" >> "$CALL_LOG.args"\n[[ -z ${XCODEGEN_TOUCH:-} ]] || echo x >> "$XCODEGEN_TOUCH"\n' > "$stubs/xcodegen"
# cp: CP_PARTIAL=1 writes the target, then fails, as a copy that dies half-made does.
cat > "$stubs/cp" <<SH
#!/usr/bin/env bash
if [[ -n \${CP_PARTIAL:-} ]]; then for last; do :; done; printf partial > "\$last"; exit 1; fi
exec "$REAL_CP" "\$@"
SH
# xcodebuild: logs the call and its args; notes whether COPY_PROBE exists at call time; makes the archive and a fake .ipa.
# XCODEBUILD_FAIL_KIND (archive, export or build) and XCODEBUILD_FAIL_SCHEME fail just those calls; XCODEBUILD_RC, _OUT,
# _SLEEP (seconds, in the foreground) and _HANG as before. XCODEBUILD_LOCK_EXPORT=1 makes the export folder read-only.
# XCODEBUILD_PID_FILE with _SLEEP: the sleep is the step's own process, and its pid goes to that file.
cat > "$stubs/xcodebuild" <<'SH'
#!/usr/bin/env bash
echo xcodebuild >> "$CALL_LOG"
echo "xcodebuild $*" >> "$CALL_LOG.args"
kind=build; case " $* " in *" archive "*) kind=archive ;; *" -exportArchive "*) kind=export ;; esac
if [[ -n ${COPY_PROBE:-} ]]; then if [[ -e $COPY_PROBE ]]; then echo "$kind present"; else echo "$kind absent"; fi >> "$CALL_LOG.probe"; fi
prev=
for a in "$@"; do
  [[ $prev == -archivePath && $kind == archive ]] && mkdir -p "$a"
  if [[ $prev == -exportPath ]]; then mkdir -p "$a"; : > "$a/App.ipa"; [[ -z ${XCODEBUILD_LOCK_EXPORT:-} ]] || chmod 555 "$a"; fi
  [[ $prev == -exportOptionsPlist ]] && cat "$a" >> "$CALL_LOG.plist"
  prev=$a
done
[[ -n ${XCODEBUILD_OUT:-} ]] && echo "$XCODEBUILD_OUT"
[[ -z ${XCODEBUILD_PID_FILE:-} || -z ${XCODEBUILD_SLEEP:-} ]] || { echo $$ > "$XCODEBUILD_PID_FILE"; exec sleep "$XCODEBUILD_SLEEP"; }
[[ -n ${XCODEBUILD_SLEEP:-} ]] && sleep "$XCODEBUILD_SLEEP"
[[ -n ${XCODEBUILD_FAIL_KIND:-} && $kind == "$XCODEBUILD_FAIL_KIND" ]] && exit 1
if [[ -n ${XCODEBUILD_FAIL_SCHEME:-} && "$*" == *"-scheme $XCODEBUILD_FAIL_SCHEME "* ]]; then exit 1; fi
if [[ -n ${XCODEBUILD_HANG:-} ]]; then
  perl -MPOSIX -e 'POSIX::setsid(); sleep 20' &
  sleep 8
fi
exit "${XCODEBUILD_RC:-0}"
SH
# XCRUN_FAIL / LAUNCH_FAIL: the devicectl install or launch prints that text and exits 1.
cat > "$stubs/xcrun" <<'SH'
#!/usr/bin/env bash
case "$*" in
  "devicectl device install"*)
    echo install >> "$CALL_LOG"
    echo "xcrun $*" >> "$CALL_LOG.args"
    if [[ -n ${XCRUN_FAIL:-} ]]; then echo "$XCRUN_FAIL"; exit 1; fi
    if [[ -n ${XCRUN_OUT:-} ]]; then echo "$XCRUN_OUT"; fi ;;
  "devicectl device process launch"*)
    echo launch >> "$CALL_LOG"
    if [[ -n ${LAUNCH_FAIL:-} ]]; then echo "$LAUNCH_FAIL"; exit 1; fi ;;
  "xctrace record"*)
    # XCTRACE_PLAN: one word per call. ok exits 0; boot prints the boot wait and exits 13; hang hangs in the save until
    # the tool's timeout; any other word fails with exit 7.
    echo xctrace >> "$CALL_LOG"
    echo "xcrun $*" >> "$CALL_LOG.args"
    o=; prev=; for a in "$@"; do [[ $prev == --output ]] && o=$a; prev=$a; done
    # Real xctrace will not write over a trace.
    if [[ -n $o && -e $o ]]; then echo "Recording failed: output exists"; exit 9; fi
    n=$(cat "$CALL_LOG.xctn" 2>/dev/null || echo 0); n=$((n + 1)); echo "$n" > "$CALL_LOG.xctn"
    set -- ${XCTRACE_PLAN:-ok}; shift $((n - 1)); w=${1:-ok}
    case $w in
      ok) exit 0 ;;
      # XCTRACE_MAKE_OUTPUT=1: a boot failure leaves a partial trace at --output, which the retry must remove.
      boot) [[ -z ${XCTRACE_MAKE_OUTPUT:-} ]] || [[ -z $o ]] || mkdir -p "$o"
        echo "Waiting for device to boot..."; echo "Timed out waiting for device to boot"; exit 13 ;;
      hang) echo "Recording completed. Saving output file..."; exec "$REAL_SLEEP" 30 ;;
      *) echo "Recording failed: $w"; exit 7 ;;
    esac ;;
  *) echo "xcrun $*" >> "$CALL_LOG" ;;
esac
SH
# sleep: SLEEP_FAKE=1 logs the call and returns at once. Unset, it is the real sleep, so the other stubs still wait.
printf '#!/usr/bin/env bash\nif [[ -n ${SLEEP_FAKE:-} ]]; then echo "sleep $*" >> "$CALL_LOG"; exit 0; fi\nexec "$REAL_SLEEP" "$@"\n' > "$stubs/sleep"
# OSASCRIPT_HANG makes every notification sleep past the notify timeout.
printf '#!/usr/bin/env bash\necho "osascript $*" >> "$CALL_LOG"\nif [[ -n ${OSASCRIPT_HANG:-} ]]; then sleep 60; fi\n' > "$stubs/osascript"
chmod +x "$stubs"/*

# ---- the tool, in its own clean repo with nothing to do with the fixture repo ----
mkdir -p "$work/toolrepo/bin"
cp "$script" "$work/toolrepo/bin/ios-ship"; chmod +x "$work/toolrepo/bin/ios-ship"
tool=$work/toolrepo/bin/ios-ship
"$REAL_GIT" init -q -b main "$work/toolrepo" >> "$work/git.log" 2>&1
"$REAL_GIT" init -q --bare -b main "$work/tool.git" >> "$work/git.log" 2>&1
g "$work/toolrepo" remote add origin "$work/tool.git"; g "$work/toolrepo" add -A; g "$work/toolrepo" commit -q -m tool
g "$work/toolrepo" push -q origin HEAD:main; g "$work/toolrepo" fetch -q origin

# ---- config builders. Fake IDs only. ----
app() { # NAME [EXTRA_JSON_OBJECT]: one app entry
  local x=${2:-}; [[ -n $x ]] || x='{}'
  jq -cn --arg n "$1" --argjson x "$x" \
    '{name:$n,scheme:$n,bundle_id:("dev.example."+$n),project_dir:"ios",project_yml:"project.yml",prebuild:["tools/build-rules"]} + $x'
}
apps() { printf '%s\n' "$@" | jq -cs .; }   # APP_JSON... -> a JSON list
cfg() { # APPS_LIST [JQ_FILTER]: the whole config, with the filter applied last
  jq -n --argjson apps "$1" --arg key "$work/key.p8" --arg url "$work/origin-x.git" \
    '{team_id:"TEAMFAKE01",device_udid:"FAKE-DEVICE-0001",asc_key_path:$key,asc_key_id:"KEYFAKE001",asc_issuer_id:"00000000-0000-0000-0000-00000000FAKE",repo_url:$url,apps:$apps}' | jq "${2:-.}"
}
copy_in() { jq -cn --arg f "$1" --arg t "$2" '{copy_in:[{from:$f,to:$t}]}'; }   # an EXTRA object for app
acct() { # HOME [JQ_FILTER]: the account file under HOME, with fake values. The filter is applied last.
  mkdir -p "$1/.config/ios-ship"
  jq -n --arg key "$work/key.p8" \
    '{team_id:"TEAMACCT01",device_udid:"FAKE-DEVICE-ACCT",asc_key_path:$key,asc_key_id:"KEYACCT001",asc_issuer_id:"11111111-1111-1111-1111-11111111FAKE"}' \
    | jq "${2:-.}" > "$1/.config/ios-ship/account.json"
}

# tool_exec HOME JOB [CONFIG] ARGS...: the tool in place of this subshell, so $! is the tool's own PID. Clean environment.
# It runs from run_dir when a case sets it (a subshell), else from elsewhere/.
# SIGINT and SIGTERM are reset to the default, so a signal a case sends reaches the tool when the case started it in the background.
tool_exec() {
  local home=$1; shift
  # HOME is unset when a case sets no_home (the case passes an empty HOME with it). PHONE_APPS_JSON reaches the tool
  # only when the case sets it, even to empty: the tool tells set from unset.
  local homevar phone
  homevar=(HOME="$home"); phone=()
  [[ -z ${no_home:-} ]] || homevar=()
  [[ -z ${PHONE_APPS_JSON+x} ]] || phone=(PHONE_APPS_JSON="$PHONE_APPS_JSON")
  cd "${run_dir:-$work/elsewhere}" && exec env -i ${homevar[@]+"${homevar[@]}"} PATH="$stubs:$PATH" CALL_LOG="$calls" TMPDIR="$work/tmp" REAL_GIT="$REAL_GIT" REAL_DATE="$REAL_DATE" REAL_CP="$REAL_CP" REAL_SLEEP="$REAL_SLEEP" \
    DATE_COUNTER="$work/datecount" COPY_PROBE="${COPY_PROBE:-}" XCODEGEN_TOUCH="${XCODEGEN_TOUCH:-}" CP_PARTIAL="${CP_PARTIAL:-}" \
    XCODEBUILD_RC="${XCODEBUILD_RC:-0}" XCODEBUILD_OUT="${XCODEBUILD_OUT:-}" XCODEBUILD_SLEEP="${XCODEBUILD_SLEEP:-}" \
    XCODEBUILD_FAIL_KIND="${XCODEBUILD_FAIL_KIND:-}" XCODEBUILD_FAIL_SCHEME="${XCODEBUILD_FAIL_SCHEME:-}" XCODEBUILD_HANG="${XCODEBUILD_HANG:-}" \
    XCODEBUILD_LOCK_EXPORT="${XCODEBUILD_LOCK_EXPORT:-}" XCODEBUILD_PID_FILE="${XCODEBUILD_PID_FILE:-}" \
    XCRUN_FAIL="${XCRUN_FAIL:-}" XCRUN_OUT="${XCRUN_OUT:-}" LAUNCH_FAIL="${LAUNCH_FAIL:-}" OSASCRIPT_HANG="${OSASCRIPT_HANG:-}" XCTRACE_PLAN="${XCTRACE_PLAN:-}" XCTRACE_MAKE_OUTPUT="${XCTRACE_MAKE_OUTPUT:-}" SLEEP_FAKE="${SLEEP_FAKE:-}" \
    STEP_TIMEOUT="${STEP_TIMEOUT:-}" REINSTALL_HOME="${REINSTALL_HOME:-}" TEAM_ID="${TEAM_ID:-}" DEVICE_UDID="${DEVICE_UDID:-}" \
    ASC_KEY_PATH="${ASC_KEY_PATH:-}" ASC_KEY_ID="${ASC_KEY_ID:-}" ASC_ISSUER_ID="${ASC_ISSUER_ID:-}" ${phone[@]+"${phone[@]}"} \
    perl -e '$SIG{INT} = $SIG{TERM} = "DEFAULT"; alarm shift; exec @ARGV' "${LIMIT:-60}" "$tool" "$@"
}
# run JOB CONFIG HOME ARGS...: the tool, from elsewhere/. Sets rc and fills $out. BG=1 starts it in the background and sets RUN_PID.
# LIMIT (seconds, default 60) kills a hung run: rc 142.
run() {
  local job=$1 conf=$2 home=$3; shift 3
  rm -rf "$work/tmp"; [[ -z $home ]] || mkdir -p "$home"; mkdir -p "$work/tmp"; : > "$calls"; : > "$calls.args"; : > "$calls.probe"; : > "$calls.plist"; rm -f "$work/datecount" "$calls.xctn"
  if [[ -n ${BG:-} ]]; then
    ( tool_exec "$home" "$job" "$conf" "$@" ) > "$out" 2>&1 &
    RUN_PID=$!; return 0
  fi
  ( tool_exec "$home" "$job" "$conf" "$@" ) > "$out" 2>&1
  rc=$?
}
built() { grep -q '^xcodebuild' "$calls"; }
args_have() { grep -q -- "$1" "$calls.args"; }
# run_in DIR JOB HOME ARGS...: the tool with no CONFIG argument, run from DIR. Stdout goes to $work/stdout, stderr to $out.
run_in() {
  local dir=$1 job=$2 home=$3; shift 3
  rm -rf "$work/tmp"; mkdir -p "$home" "$work/tmp"; : > "$calls"; : > "$calls.args"; : > "$calls.probe"; : > "$calls.plist"; rm -f "$work/datecount"
  ( run_dir=$dir tool_exec "$home" "$job" "$@" ) > "$work/stdout" 2> "$out"; rc=$?
}
# trace FILE: the last run's call order and args, with the random scratch and export folder names made fixed, so two runs compare.
trace() { { cat "$calls"; sed -E 's/ios-ship-(scratch|export)\.[A-Za-z0-9]+/ios-ship-\1.X/g' "$calls.args"; } > "$1"; }
outside_repo() { ! "$REAL_GIT" -C "$1" rev-parse --show-toplevel >/dev/null 2>&1; }

# ---- testflight world: a bare origin plus a clone that holds the config and the secrets' .gitignore ----
tfconf=$work/repo/tools/ios-ship.json
mk_tf() { # APPS_LIST [JQ_FILTER]: a clean clone at origin/main
  rm -rf "$work/origin.git" "$work/repo" "$work/other"
  "$REAL_GIT" init -q --bare -b main "$work/origin.git" >> "$work/git.log" 2>&1
  "$REAL_GIT" clone -q "$work/origin.git" "$work/repo" >> "$work/git.log" 2>&1
  mkdir -p "$work/repo/tools" "$work/repo/ios"
  printf '#!/usr/bin/env bash\necho build-rules >> "$CALL_LOG"\n' > "$work/repo/tools/build-rules"; chmod +x "$work/repo/tools/build-rules"
  printf 'ios/Secret.xcconfig\nios/Other.xcconfig\n' > "$work/repo/.gitignore"
  touch "$work/repo/ios/.keep"
  cfg "$1" "${2:-.}" > "$tfconf"
  g "$work/repo" add -A; g "$work/repo" commit -q -m init; g "$work/repo" push -q origin HEAD:main; g "$work/repo" fetch -q origin
  rm -f "$work/key.p8"; printf x > "$work/key.p8"; chmod 000 "$work/key.p8"   # unreadable: a read of the key would fail the run
  printf 'SECRET' > "$work/secrets/Secret.xcconfig"
  COPY_PROBE=$work/repo/ios/Secret.xcconfig
}
tf() { run testflight "$tfconf" "$work/home" "$@"; }
one_app() { mk_tf "$(apps "$(app A "${1:-}")")" "${2:-.}"; }
# signal_mid_build SIG: start a testflight run, send SIG to the tool alone once xcodebuild runs. Records in sig_gone
# whether the copy_in file left the tree within 3 s, and in sig_step_gone whether the archive step's own process
# (sig_pid, from $xcb_pid) died within 3 s. The tool must not wait for the build to end to clean up.
signal_mid_build() {
  local xcb_pid=$work/xcodebuild.pid XCODEBUILD_PID_FILE
  rm -f "$xcb_pid"; XCODEBUILD_PID_FILE=$xcb_pid
  BG=1 tf
  for _ in $(seq 1 100); do grep -q '^xcodebuild' "$calls" && [[ -s $xcb_pid ]] && break; sleep 0.1; done
  sig_pid=$(cat "$xcb_pid" 2>/dev/null)
  kill -"$1" "$RUN_PID"
  sig_gone=no; sig_step_gone=no
  for _ in $(seq 1 30); do
    [[ -e $COPY_PROBE ]] || sig_gone=yes
    if [[ -n $sig_pid ]] && ! kill -0 "$sig_pid" 2>/dev/null; then sig_step_gone=yes; fi
    [[ $sig_gone = yes && $sig_step_gone = yes ]] && break
    sleep 0.1
  done
  [[ $sig_step_gone = yes || -z $sig_pid ]] || kill "$sig_pid" 2>/dev/null   # a step still alive is stopped here, not left for the next case
  wait "$RUN_PID"; rc=$?
}

# ===================== testflight =====================

one_app; tf
need "rc=$rc: $(tail -2 "$out" | tr '\n' ' ')" test "$rc" -eq 0
need "no archive" grep -q '^xcodebuild archive ' "$calls.args"
need "no export" grep -q '^xcodebuild -exportArchive ' "$calls.args"
end_case "tf: clean main archives and exports"
one_app; tf
need "build-rules not run in the repo root" grep -q '^build-rules' "$calls"
end_case "tf: prebuild runs"
one_app; tf
n=$(grep -c -- "-authenticationKeyPath $work/key.p8 -authenticationKeyID KEYFAKE001 -authenticationKeyIssuerID 00000000-0000-0000-0000-00000000FAKE" "$calls.args")
need "auth flags on $n of 2 xcodebuild calls" test "$n" -eq 2
end_case "tf: both xcodebuild calls get the key flags"
one_app; tf
need "success line: $(tail -1 "$out")" grep -qE "^TESTFLIGHT OK: build [0-9]+ uploaded \(A\) from main [0-9a-f]{7}$" "$out"
need "destination is not upload" grep -q '<key>destination</key><string>upload</string>' "$calls.plist"
need "team ID missing from the export plist" grep -q '<string>TEAMFAKE01</string>' "$calls.plist"
end_case "tf: success prints build, branch, short SHA; export options upload"
one_app; XCODEBUILD_OUT=buildmarker tf
need "scratch dir left behind" test -z "$(find "$work/tmp" -name '*scratch*')"
log_file=$(sed -n 's/.*log \(.*\)$/\1/p' "$out" | head -1)
need "log file missing: $log_file" test -f "$log_file"
need "xcodebuild output not in the log" grep -q buildmarker "$log_file"
need "xcodebuild output on stdout" not grep -q buildmarker "$out"
end_case "tf: scratch deleted, log kept"

one_app; echo x > "$work/repo/dirty"; tf
need "rc=$rc" test "$rc" -ne 0
need "build ran" not built
need "refusal text: $(tail -1 "$out")" grep -q 'TESTFLIGHT FAIL: the tree is not clean' "$out"
end_case "tf: dirty tree refused before any build, tool repo clean"
one_app; g "$work/repo" commit -q --allow-empty -m ahead; tf
need "rc=$rc" test "$rc" -ne 0
need "build ran" not built
need "refusal text: $(tail -1 "$out")" grep -q 'TESTFLIGHT FAIL: HEAD is not origin/main' "$out"
end_case "tf: HEAD ahead of origin/main refused"
one_app
"$REAL_GIT" clone -q "$work/origin.git" "$work/other" >> "$work/git.log" 2>&1
g "$work/other" commit -q --allow-empty -m moved; g "$work/other" push -q origin HEAD:main
tf   # origin moved after the clone's last fetch: the tool must fetch first, so HEAD is behind
need "rc=$rc" test "$rc" -ne 0
need "build ran" not built
need "refusal text: $(tail -1 "$out")" grep -q 'TESTFLIGHT FAIL: HEAD is not origin/main' "$out"
end_case "tf: HEAD behind a freshly fetched origin/main refused"
one_app; g "$work/repo" remote set-url origin "$work/missing.git"; tf
need "rc=$rc" test "$rc" -ne 0
need "build ran" not built
need "refusal text: $(tail -1 "$out")" grep -q 'TESTFLIGHT FAIL: git fetch origin main failed' "$out"
end_case "tf: failed fetch refused (a stale origin/main proves nothing)"
one_app; rm -f "$work/key.p8"; tf
need "rc=$rc" test "$rc" -ne 0
need "build ran" not built
need "refusal text: $(tail -1 "$out")" grep -q 'TESTFLIGHT FAIL: no App Store Connect key at' "$out"
end_case "tf: missing key file refused"
one_app; echo x > "$work/toolrepo/dirty"; tf; rm -f "$work/toolrepo/dirty"
need "rc=$rc: the tool's own repo was judged" test "$rc" -eq 0
end_case "tf: the root comes from CONFIG, not from the tool's path"

# New: the status check and the fetch must see what they should.
one_app; "$REAL_GIT" -C "$work/repo" config status.showUntrackedFiles no; echo x > "$work/repo/dirty"; tf
need "rc=$rc, want non-zero" test "$rc" -ne 0
need "build ran" not built
need "refusal text: $(tail -1 "$out")" grep -q 'TESTFLIGHT FAIL: the tree is not clean' "$out"
end_case "tf: an untracked file refuses the run even when status hides untracked files"
one_app; "$REAL_GIT" -C "$work/repo" config remote.origin.fetch '+refs/heads/feature:refs/remotes/origin/feature'
"$REAL_GIT" clone -q "$work/origin.git" "$work/other" >> "$work/git.log" 2>&1
g "$work/other" commit -q --allow-empty -m moved; g "$work/other" push -q origin HEAD:main
tf
need "rc=$rc, want non-zero" test "$rc" -ne 0
need "build ran" not built
need "refusal text: $(tail -1 "$out")" grep -q 'TESTFLIGHT FAIL: HEAD is not origin/main' "$out"
end_case "tf: a narrowed fetch refspec still updates origin/main, so a moved main is refused"

# IDs: the config or the env must hold each one. The device ID is not needed to upload.
for k in team_id asc_key_path asc_key_id asc_issuer_id; do
  one_app "" "del(.$k)"; tf
  need "$k: rc=$rc, want non-zero" test "$rc" -ne 0
  need "$k: build ran" not built
  need "$k: notice does not name it" grep -q "$k" "$out"
  end_case "tf: missing $k refused"
done
one_app "" "del(.device_udid)"; tf
need "tf must not need device_udid: rc=$rc" test "$rc" -eq 0
end_case "tf: no device ID needed"
one_app "" "del(.team_id)"; TEAM_ID=TEAMENV001 tf
need "env TEAM_ID not used: rc=$rc" test "$rc" -eq 0
need "team from env missing" args_have 'DEVELOPMENT_TEAM=TEAMENV001'
end_case "tf: env fills an ID the config lacks"
one_app; TEAM_ID=TEAMENV002 tf
need "env did not win" args_have 'DEVELOPMENT_TEAM=TEAMENV002'
need "config team used" not args_have 'DEVELOPMENT_TEAM=TEAMFAKE01'
end_case "tf: env wins over the config"
one_app "" ".asc_key_path = \"~/k.p8\""; mkdir -p "$work/home"; printf x > "$work/home/k.p8"; tf
need "tilde not expanded to HOME: rc=$rc" test "$rc" -eq 0
need "key flag not the HOME path" args_have "-authenticationKeyPath $work/home/k.p8 "
end_case "tf: ~/ in the key path expands to HOME"

# copy_in
one_app "$(copy_in "$work/secrets/Secret.xcconfig" ios/Secret.xcconfig)"; tf
need "rc=$rc" test "$rc" -eq 0
need "copy missing during the archive" grep -qx 'archive present' "$calls.probe"
need "copy still there at export" grep -qx 'export absent' "$calls.probe"
need "copy left in the tree" not test -e "$work/repo/ios/Secret.xcconfig"
need "source touched" test -f "$work/secrets/Secret.xcconfig"
end_case "tf: copy_in is copied for the archive and removed after it"
one_app "$(copy_in "$work/secrets/Secret.xcconfig" ios/Secret.xcconfig)"; XCODEBUILD_FAIL_KIND=archive tf
need "rc=$rc, want non-zero" test "$rc" -ne 0
need "copy not there during the archive" grep -qx 'archive present' "$calls.probe"
need "copy left after a failed archive" not test -e "$work/repo/ios/Secret.xcconfig"
need "verdict: $(tail -1 "$out")" grep -q '^TESTFLIGHT FAIL: A archive, see ' "$out"
end_case "tf: copy_in removed after a failed archive"
one_app "$(copy_in "$work/secrets/Secret.xcconfig" ios/Secret.xcconfig)"; XCODEBUILD_FAIL_KIND="export" tf
need "rc=$rc, want non-zero" test "$rc" -ne 0
need "copy left after a failed export" not test -e "$work/repo/ios/Secret.xcconfig"
end_case "tf: copy_in removed after a failed export"
one_app "$(copy_in "$work/secrets/Secret.xcconfig" ios/Secret.xcconfig | jq -c '. + {prebuild:["exit 3"]}')"; tf
need "rc=$rc, want non-zero" test "$rc" -ne 0
need "verdict: $(tail -1 "$out")" grep -q '^TESTFLIGHT FAIL: A prebuild: exit 3, see ' "$out"
need "build ran after a failed prebuild" not built
need "copy left" not test -e "$work/repo/ios/Secret.xcconfig"
end_case "tf: a failed prebuild stops the app"
one_app "$(copy_in "$work/secrets/Secret.xcconfig" ios/NotIgnored.xcconfig)"; tf
need "rc=$rc, want non-zero" test "$rc" -ne 0
need "build ran" not built
need "refusal text: $(tail -1 "$out")" grep -q 'FAIL: A: ios/NotIgnored.xcconfig is not git-ignored' "$out"
need "copy made anyway" not test -e "$work/repo/ios/NotIgnored.xcconfig"
end_case "tf: copy_in to a path that is not git-ignored refused"
one_app "$(copy_in "$work/secrets/Secret.xcconfig" ios/Secret.xcconfig)"; printf mine > "$work/repo/ios/Secret.xcconfig"; tf
need "rc=$rc, want non-zero" test "$rc" -ne 0
need "build ran" not built
need "refusal text: $(tail -1 "$out")" grep -q 'already exists in the tree' "$out"
need "a file this run did not make was removed" test "$(cat "$work/repo/ios/Secret.xcconfig")" = mine
end_case "tf: copy_in onto an existing file refused and the file kept"
one_app "$(copy_in "$work/secrets/Missing.xcconfig" ios/Secret.xcconfig)"; tf
need "rc=$rc, want non-zero" test "$rc" -ne 0
need "build ran" not built
need "refusal text: $(tail -1 "$out")" grep -q 'copy_in source missing' "$out"
end_case "tf: copy_in with a missing source refused"
one_app "$(copy_in "$work/repo/ios/Secret.xcconfig" ios/Secret.xcconfig)"; printf same > "$work/repo/ios/Secret.xcconfig"; tf
need "rc=$rc" test "$rc" -eq 0
need "the file that was already in place was removed" test "$(cat "$work/repo/ios/Secret.xcconfig")" = same
end_case "tf: copy_in whose source is the target copies nothing and removes nothing"
one_app "$(copy_in ../x ios/Secret.xcconfig | jq -c '.copy_in[0].to = "../escape"')"; tf
need "rc=$rc, want non-zero" test "$rc" -ne 0
need "build ran" not built
need "refusal text: $(tail -1 "$out")" grep -q 'copy_in.to must stay inside the tree' "$out"
end_case "tf: copy_in to outside the tree refused"
one_app "$(copy_in rel/Secret.xcconfig ios/Secret.xcconfig)"; mkdir -p "$work/repo/rel"; printf s > "$work/repo/rel/Secret.xcconfig"
printf 'rel/\n' >> "$work/repo/.gitignore"; g "$work/repo" add -A; g "$work/repo" commit -q -m ignore; g "$work/repo" push -q origin HEAD:main; tf
need "relative from not resolved against the repo root: rc=$rc" test "$rc" -eq 0
need "copy not made" grep -qx 'archive present' "$calls.probe"
end_case "tf: a relative copy_in.from resolves against the config's repo root"

# New: a copy that a prebuild or a failed copy leaves behind is never this run's to keep.
one_app "$(copy_in "$work/secrets/Secret.xcconfig" ios/Secret.xcconfig | jq -c '. + {prebuild:["echo mine > ios/Secret.xcconfig"]}')"; tf
need "rc=$rc, want non-zero" test "$rc" -ne 0
need "build ran" not built
need "refusal text: $(tail -1 "$out")" grep -q 'already exists in the tree' "$out"
need "the file the prebuild made was overwritten" test "$(cat "$work/repo/ios/Secret.xcconfig")" = mine
end_case "tf: copy_in is checked after the prebuild, so a file the prebuild makes is refused"
one_app "$(copy_in "$work/secrets/Secret.xcconfig" ios/Secret.xcconfig)"; CP_PARTIAL=1 tf
need "rc=$rc, want non-zero" test "$rc" -ne 0
need "build ran" not built
need "a half-made copy was left in the tree" not test -e "$work/repo/ios/Secret.xcconfig"
end_case "tf: a copy that dies half-made is removed"
for sig in TERM INT; do
  one_app "$(copy_in "$work/secrets/Secret.xcconfig" ios/Secret.xcconfig)"
  XCODEBUILD_SLEEP=6 signal_mid_build "$sig"
  need "$sig: no xcodebuild call, so the signal tested nothing" built
  need "$sig: the copy was still in the tree 3 s after the signal" test "$sig_gone" = yes
  need "$sig: the copy was left in the tree after the tool exited" not test -e "$COPY_PROBE"
  end_case "tf: $sig during the archive removes the copy at once"
  need "$sig: the archive step wrote no pid, so it could not be checked" test -n "$sig_pid"
  need "$sig: the archive step (pid $sig_pid) was alive 3 s after the signal" test "$sig_step_gone" = yes
  end_case "tf: $sig during the archive stops the archive step within 3 s"
done

# New: a step that reads stdin must not eat the steps after it, and a checked step must not be skipped.
one_app '{"prebuild":["cat >/dev/null","echo later >> \"$CALL_LOG\""]}'; tf
need "rc=$rc: $(tail -1 "$out")" test "$rc" -eq 0
need "the command after the stdin reader did not run" grep -qx later "$calls"
end_case "tf: a prebuild that reads stdin does not skip the next prebuild"
one_app '{"prebuild":["cat >/dev/null","exit 3"]}'; tf
need "rc=$rc, want non-zero" test "$rc" -ne 0
need "verdict: $(tail -1 "$out")" grep -q '^TESTFLIGHT FAIL: A prebuild: exit 3, see ' "$out"
need "build ran after a failed prebuild" not built
end_case "tf: a prebuild that reads stdin does not hide a failing prebuild"
one_app '{"after_archive":["cat >/dev/null","false"]}'; tf
need "rc=$rc, want non-zero" test "$rc" -ne 0
need "verdict: $(tail -1 "$out")" grep -q '^TESTFLIGHT FAIL: A after_archive: false, see ' "$out"
need "export ran after a failed check" not grep -q '^xcodebuild -exportArchive' "$calls.args"
end_case "tf: an after_archive that reads stdin does not hide a failing check"

# New: a prebuild or xcodegen that changes a tracked file is refused before the archive, and the refusal names the file.
one_app '{"prebuild":["printf x >> ios/.keep"]}'; tf
need "rc=$rc, want non-zero" test "$rc" -ne 0
need "build ran" not built
need "refusal does not name the prebuild step: $(tail -1 "$out")" grep -qF 'a prebuild step changed tracked files: ios/.keep' "$out"
need "the upload was labelled from main" not grep -q 'from main' "$out"
end_case "tf: a prebuild that changes a tracked file is refused before any archive"
one_app; XCODEGEN_TOUCH=$work/repo/ios/.keep tf
need "rc=$rc, want non-zero" test "$rc" -ne 0
need "build ran" not built
need "refusal text: $(tail -1 "$out")" grep -q 'TESTFLIGHT FAIL: .*tracked.*ios/.keep' "$out"
end_case "tf: an xcodegen that changes a tracked file is refused before any archive"

# New: a failed delete of a copy_in app's .ipa in --export-only is a FAIL verdict, not OK.
one_app "$(copy_in "$work/secrets/Secret.xcconfig" ios/Secret.xcconfig)"; XCODEBUILD_LOCK_EXPORT=1 tf --export-only
chmod -R u+rwx "$work/tmp" 2>/dev/null
need "rc=$rc: $(tail -1 "$out")" test "$rc" -ne 0
need "printed OK with a .ipa it could not delete: $(tail -1 "$out")" not grep -q '^TESTFLIGHT OK' "$out"
end_case "tf: a .ipa of a copy_in app that cannot be deleted is a FAIL verdict"

# several apps
mk_tf "$(apps "$(app A)" "$(app B '{"scheme":"BScheme"}')")"; tf
need "rc=$rc" test "$rc" -eq 0
need "archives: $(grep -c '^xcodebuild archive ' "$calls.args"), want 2" test "$(grep -c '^xcodebuild archive ' "$calls.args")" -eq 2
need "build numbers differ across apps" test "$(sed -n 's/.*CURRENT_PROJECT_VERSION=\([0-9]*\).*/\1/p' "$calls.args" | sort -u | wc -l | tr -d ' ')" -eq 1
need "success line: $(tail -1 "$out")" grep -q '^TESTFLIGHT OK: build [0-9]* uploaded (A, B) from ' "$out"
need "scheme not used" args_have 'archive -scheme BScheme '
end_case "tf: one build number across apps"
mk_tf "$(apps "$(app A)" "$(app B)")"; tf --app B
need "rc=$rc" test "$rc" -eq 0
need "A was built" not args_have 'archive -scheme A '
need "B was not built" args_have 'archive -scheme B '
end_case "tf: --app limits the run"
mk_tf "$(apps "$(app A)" "$(app B)")"; tf --app Nope
need "rc=$rc, want 2" test "$rc" -eq 2
need "build ran" not built
need "refusal text: $(tail -1 "$out")" grep -q 'unknown app: Nope' "$out"
end_case "tf: --app with an unknown name exits 2"
mk_tf "$(apps "$(app A)" "$(app B)")"; XCODEBUILD_FAIL_SCHEME=A tf
need "rc=$rc, want non-zero" test "$rc" -ne 0
need "B built after A failed" not args_have 'archive -scheme B '
end_case "tf: the first failing app ends the run"
# B's copy_in is bad: A must not have been archived (checks come before the first archive)
mk_tf "$(apps "$(app A)" "$(app B "$(copy_in "$work/secrets/Missing.xcconfig" ios/Secret.xcconfig)")")"; tf
need "rc=$rc, want non-zero" test "$rc" -ne 0
need "A was archived although B would refuse" not built
end_case "tf: every app is checked before the first archive"
one_app '{"trust_package_plugins":true}'; tf
need "plugin flags missing" grep -q '^xcodebuild archive .*-skipPackagePluginValidation -skipMacroValidation' "$calls.args"
end_case "tf: trust_package_plugins adds both flags"
one_app; tf
need "plugin flags added without the opt-in" not args_have 'skipPackagePluginValidation'
end_case "tf: no plugin flags without the opt-in"
one_app; tf
need "xcodegen not run with the spec" grep -qx 'xcodegen generate --spec project.yml' "$calls.args"
end_case "tf: xcodegen runs with the project_yml"
one_app '{"project_yml":null}'; tf
need "xcodegen ran without a project_yml" not grep -qx xcodegen "$calls"
need "rc=$rc" test "$rc" -eq 0
end_case "tf: no project_yml means no xcodegen"
one_app; tf --no-install
need "rc=$rc, want 2" test "$rc" -eq 2
need "refusal text: $(tail -1 "$out")" grep -q '^usage: ios-ship testflight' "$out"
end_case "tf: an install flag is refused"

# --export-only
mk_tf "$(apps "$(app A "$(copy_in "$work/secrets/Secret.xcconfig" ios/Secret.xcconfig)")" "$(app B)")"
"$REAL_GIT" clone -q "$work/origin.git" "$work/other" >> "$work/git.log" 2>&1
g "$work/other" commit -q --allow-empty -m moved; g "$work/other" push -q origin HEAD:main
tf --export-only   # origin moved: an upload would refuse, an export must not
exp=$(sed -n 's/.*exported to \([^ ]*\) .*/\1/p' "$out")
need "rc=$rc: $(tail -2 "$out" | tr '\n' ' ')" test "$rc" -eq 0
need "destination is not export" grep -q '<key>destination</key><string>export</string>' "$calls.plist"
need "export folder not kept or not printed: '$exp'" test -d "$exp"
need "the copy_in app's .ipa was kept" not test -e "$exp/A/App.ipa"
need "the other app's .ipa was not kept" test -e "$exp/B/App.ipa"
need "success line: $(tail -1 "$out")" grep -q '^TESTFLIGHT OK: build [0-9]* exported to .* (not uploaded: A, B)$' "$out"
end_case "tf: --export-only skips the main check and deletes the .ipa of a copy_in app"
mk_tf "$(apps "$(app A "$(copy_in "$work/secrets/Secret.xcconfig" ios/Secret.xcconfig)")")"; XCODEBUILD_FAIL_KIND="export" tf --export-only
need "rc=$rc, want non-zero" test "$rc" -ne 0
need "an .ipa of a copy_in app survived a failed export" test -z "$(find "$work/tmp" -name '*.ipa')"
end_case "tf: no .ipa of a copy_in app outlives a failed export"
one_app; echo x > "$work/repo/dirty"; tf --export-only
need "rc=$rc, want non-zero" test "$rc" -ne 0
need "build ran" not built
need "refusal text: $(tail -1 "$out")" grep -q 'TESTFLIGHT FAIL: the tree is not clean' "$out"
end_case "tf: --export-only still refuses a dirty tree"

# ===================== install =====================

# A real origin that the tool clones: ios/, an executable tools/build-rules that logs its call, and a .gitignore for the secrets.
"$REAL_GIT" init -q --bare -b main "$work/origin-x.git" >> "$work/git.log" 2>&1
"$REAL_GIT" clone -q "$work/origin-x.git" "$work/seed" >> "$work/git.log" 2>&1
mkdir -p "$work/seed/tools" "$work/seed/ios"
printf '#!/usr/bin/env bash\necho build-rules >> "$CALL_LOG"\n' > "$work/seed/tools/build-rules"; chmod +x "$work/seed/tools/build-rules"
printf 'ios/Secret.xcconfig\n' > "$work/seed/.gitignore"; touch "$work/seed/ios/.keep"
g "$work/seed" add -A; g "$work/seed" commit -q -m init; g "$work/seed" push -q origin HEAD:main
# The config lives in a repo of its own, as in an app repo. It is not a clone of the origin.
"$REAL_GIT" init -q -b main "$work/cfgrepo" >> "$work/git.log" 2>&1; mkdir -p "$work/cfgrepo/tools"
iconf=$work/cfgrepo/tools/ios-ship.json
icfg() { cfg "$1" "${2:-.}" > "$iconf"; }   # APPS_LIST [JQ_FILTER]
install_run() { run install "$iconf" "$@"; }   # HOME ARGS...
chain="clone fetch reset build-rules xcodegen xcodebuild install launch"
stamp_of() { echo "$1/Library/Application Support/ios-adblock-reinstall/$2/last-success"; }
repo_of() { echo "$1/Library/Application Support/ios-adblock-reinstall/$2/repo"; }
non_notify() { grep -v '^osascript ' "$calls" | tr '\n' ' ' | sed 's/ $//'; }
icfg "$(apps "$(app AdBlock)")"

home=$work/a; mkdir -p "$(dirname "$(stamp_of "$home" AdBlock)")"; date +%s > "$(stamp_of "$home" AdBlock)"
install_run "$home"
need "exit $rc, want 0" test "$rc" -eq 0
need "calls: $(non_notify)" test "$(non_notify)" = "$chain"
end_case "install: recent-stamp-runs (a fresh stamp never skips)"
home=$work/a2; mkdir -p "$(dirname "$(stamp_of "$home" AdBlock)")"; printf '%s\n' $(( $(date +%s) - 4 * 86400 )) > "$(stamp_of "$home" AdBlock)"
install_run "$home"
need "exit $rc" test "$rc" -eq 0
need "overdue alert on a 4-day stamp" not grep -q '^osascript .*Reinstall overdue' "$calls"
end_case "install: no overdue alert at 4 days"
home=$work/a3; mkdir -p "$(dirname "$(stamp_of "$home" AdBlock)")"; printf '%s\n' $(( $(date +%s) - 299 * 86400 )) > "$(stamp_of "$home" AdBlock)"
install_run "$home" --no-install
need "overdue alert on a 299-day stamp" not grep -q '^osascript .*Reinstall overdue' "$calls"
end_case "install: no overdue alert at 299 days"
home=$work/f; mkdir -p "$(dirname "$(stamp_of "$home" AdBlock)")"; printf '%s\n' $(( $(date +%s) - 301 * 86400 )) > "$(stamp_of "$home" AdBlock)"
install_run "$home"
need "exit $rc" test "$rc" -eq 0
need "no overdue alert" grep -q '^osascript .*Reinstall overdue' "$calls"
need "calls: $(non_notify)" test "$(non_notify)" = "$chain"
end_case "install: overdue alert at 301 days, the run continues"
home=$work/b; XCODEBUILD_RC=1 install_run "$home"
need "exit 0, want non-zero" test "$rc" -ne 0
need "no notice naming the build step" grep -q '^osascript .*AdBlock failed at step: build\.' "$calls"
need "install or launch ran after a failed build" not grep -qE '^(install|launch)$' "$calls"
end_case "install: build-fail"
home=$work/c; install_run "$home" --force
need "exit $rc" test "$rc" -eq 0
need "calls: $(non_notify)" test "$(non_notify)" = "$chain"
end_case "install: --force is accepted and changes nothing"
home=$work/d; install_run "$home" --force --no-install
need "exit $rc" test "$rc" -eq 0
need "calls: $(non_notify)" test "$(non_notify)" = "clone fetch reset build-rules xcodegen xcodebuild"
end_case "install: --force --no-install stops after xcodebuild"
home=$work/g; install_run "$home" --no-install
need "exit $rc" test "$rc" -eq 0
need "stamp written on --no-install" not test -e "$(stamp_of "$home" AdBlock)"
need "build not aimed at generic iOS" args_have '^xcodebuild .*-destination generic/platform=iOS '
end_case "install: --no-install writes no stamp and needs no phone"
home=$work/h; XCRUN_FAIL="ERROR: the device is locked" install_run "$home"
need "exit $rc, want 75" test "$rc" -eq 75
need "stamp written after a failed install" not test -e "$(stamp_of "$home" AdBlock)"
need "no phone notice" grep -qi 'phone not on home Wi-Fi or asleep' "$out"
end_case "install: locked phone is exit 75"
home=$work/h2; XCRUN_FAIL="ERROR: The device is not able to fulfill the requested usage assertion requirements. (com.apple.dt.CoreDeviceError error 4016 (0xFB0))" install_run "$home"
need "exit $rc, want 75" test "$rc" -eq 75
need "stamp written" not test -e "$(stamp_of "$home" AdBlock)"
end_case "install: CoreDevice 4016 is exit 75"
home=$work/h3; XCRUN_FAIL="ERROR: something else (com.apple.dt.CoreDeviceError error 40160 (0x9CE0))" install_run "$home"
need "exit $rc, want a hard failure" test "$rc" -ne 75 -a "$rc" -ne 0
end_case "install: CoreDevice 40160 is a hard failure"
# STEP_TIMEOUT applies to every step the tool runs, so the clone exists already (no clone step) and the timeout is 3 s:
# clone is the only step that could be slow, and fetch and reset are local. The build is the step under test.
home=$work/i; mkdir -p "$(dirname "$(repo_of "$home" AdBlock)")"; "$REAL_GIT" clone -q "$work/origin-x.git" "$(repo_of "$home" AdBlock)" >> "$work/git.log" 2>&1
start=$SECONDS; STEP_TIMEOUT=3 XCODEBUILD_HANG=1 install_run "$home"; took=$((SECONDS - start))
need "exit 0, want non-zero" test "$rc" -ne 0
need "took ${took}s, want under 10s: a child held stdout open" test "$took" -lt 10
need "no notice naming the build step" grep -q '^osascript .*AdBlock failed at step: build\.' "$calls"
need "stamp written after a timed-out build" not test -e "$(stamp_of "$home" AdBlock)"
end_case "install: step-timeout"
home=$work/j; LAUNCH_FAIL="ERROR: launch failed" install_run "$home"
need "exit $rc, want 0" test "$rc" -eq 0
need "no stamp after a successful install" grep -qE '^[0-9]+$' "$(stamp_of "$home" AdBlock)"
need "calls: $(non_notify)" test "$(non_notify)" = "$chain"
end_case "install: launch failure is soft"
home=$work/k; mkdir -p "$(repo_of "$home" AdBlock)/.git"
"$REAL_GIT" init -q "$home" && "$REAL_GIT" -C "$home" remote add origin "$work/origin-x.git"
install_run "$home"
need "exit 0, want non-zero" test "$rc" -ne 0
need "no refusal notice naming the guard" grep -q '^osascript .*failed at step: guard' "$calls"
need "build steps ran past the guard" not grep -qE '^(fetch|reset|build-rules|xcodebuild)$' "$calls"
end_case "install: guard-empty-git"
home=$work/l; mkdir -p "$(repo_of "$home" AdBlock)"
"$REAL_GIT" init -q "$(repo_of "$home" AdBlock)" && "$REAL_GIT" -C "$(repo_of "$home" AdBlock)" remote add origin https://example.invalid/other.git
install_run "$home"
need "exit 0, want non-zero" test "$rc" -ne 0
need "no refusal notice naming the guard" grep -q '^osascript .*failed at step: guard' "$calls"
need "build steps ran past the guard" not grep -qE '^(fetch|reset|build-rules|xcodebuild)$' "$calls"
end_case "install: guard-origin"
home=$work/m; mkdir -p "$(dirname "$(stamp_of "$home" AdBlock)")"; printf '%s\n' $(( $(date +%s) + 10 * 86400 )) > "$(stamp_of "$home" AdBlock)"
install_run "$home"
need "exit $rc" test "$rc" -eq 0
need "no overdue alert for a future stamp" grep -q '^osascript .*Reinstall overdue' "$calls"
need "calls: $(non_notify)" test "$(non_notify)" = "$chain"
end_case "install: future-stamp"
home=$work/n; mkdir -p "$(dirname "$(stamp_of "$home" AdBlock)")"; date +%s > "$work/n-target"; ln -s "$work/n-target" "$(stamp_of "$home" AdBlock)"
install_run "$home"
need "exit $rc" test "$rc" -eq 0
need "no overdue alert for a symlink stamp" grep -q '^osascript .*Reinstall overdue' "$calls"
end_case "install: symlink-stamp"
home=$work/o
REINSTALL_HOME=rel-home install_run "$home"
stampval=$(cat "$work/elsewhere/rel-home/AdBlock/last-success" 2>/dev/null)
need "no stamp at the relative home under the tool's cwd: '$stampval'" test -n "$stampval"
end_case "install: relative REINSTALL_HOME resolves against the cwd, not the clone"
home=$work/p; XCRUN_OUT="ERROR: install reported a failure" install_run "$home"
need "exit 0, want non-zero" test "$rc" -ne 0
need "stamp written after install printed an error" not test -e "$(stamp_of "$home" AdBlock)"
end_case "install: devicectl error text fails the install"
home=$work/q; mkdir -p "$(repo_of "$home" AdBlock)" "$work/q-elsewhere"
"$REAL_GIT" init -q "$work/q-elsewhere" && "$REAL_GIT" -C "$work/q-elsewhere" remote add origin "$work/origin-x.git"
ln -s "$work/q-elsewhere/.git" "$(repo_of "$home" AdBlock)/.git"
install_run "$home"
need "exit 0, want non-zero" test "$rc" -ne 0
need "no refusal naming the guard" grep -q '^osascript .*guard' "$calls"
need "fetch or reset ran past the guard" not grep -qE '^(fetch|reset)$' "$calls"
end_case "install: guard-git-symlink"
home=$work/r; mkdir -p "$(dirname "$(stamp_of "$home" AdBlock)")"; mkfifo "$(stamp_of "$home" AdBlock)"
LIMIT=5 install_run "$home"
perl -e 'open(my $f, "+<", $ARGV[0]) and close $f' "$(stamp_of "$home" AdBlock)" 2>/dev/null
need "hung: killed at 5s reading the FIFO" test "$rc" -ne 142
need "exit $rc" test "$rc" -eq 0
need "no overdue alert for a FIFO stamp" grep -q '^osascript .*Reinstall overdue' "$calls"
end_case "install: stamp-fifo"
home=$work/s; mkdir -p "$(dirname "$(stamp_of "$home" AdBlock)")"; printf '1\n' > "$work/s-target"; ln -s "$work/s-target" "$(stamp_of "$home" AdBlock)"
install_run "$home"
need "exit $rc" test "$rc" -eq 0
need "stamp is still a symlink" not test -L "$(stamp_of "$home" AdBlock)"
need "symlink target changed" test "$(cat "$work/s-target")" = 1
end_case "install: stamp-symlink-run"
home=$work/t; start=$SECONDS; OSASCRIPT_HANG=1 LIMIT=40 XCODEBUILD_RC=1 install_run "$home"; took=$((SECONDS - start))
need "notify hang was not bounded" test "$rc" -ne 142
need "exit $rc, want 1" test "$rc" -eq 1
need "took ${took}s, want at most 20s" test "$took" -le 20
end_case "install: notify-hang"
home=$work/u; mkdir -p "$home"
printf '[url "%s"]\n\tinsteadOf = https://github.com/example/app.git\n' "$work/origin-x.git" > "$home/.gitconfig"
icfg "$(apps "$(app AdBlock)")" '.repo_url = "https://github.com/example/app.git"'
install_run "$home"
need "exit $rc" test "$rc" -eq 0
need "calls: $(non_notify)" test "$(non_notify)" = "$chain"
end_case "install: insteadof-origin (the guard reads the raw origin)"
icfg "$(apps "$(app AdBlock)")"
home=$work/w; icfg "$(apps "$(app AdBlock)" "$(app Other)")"
XCODEBUILD_FAIL_SCHEME=AdBlock install_run "$home"
need "exit 0, want non-zero" test "$rc" -ne 0
need "no notice naming AdBlock and the build step" grep -q '^osascript .*AdBlock failed at step: build\.' "$calls"
need "calls: $(non_notify)" test "$(non_notify)" = "clone fetch reset build-rules xcodegen xcodebuild clone fetch reset build-rules xcodegen xcodebuild install launch"
end_case "install: two-apps-first-fails"
printf '[{"name":' > "$work/bad.json"
home=$work/x1; run install "$work/cfgrepo/tools/none.json" "$home"; rc1=$rc; cp "$calls" "$work/x1.calls"
home=$work/x2; run install "$work/bad.json" "$home"; rc2=$rc
need "exit 0 on a bad config (missing $rc1, invalid $rc2)" test "$rc1" -ne 0 -a "$rc2" -ne 0
need "no notice naming the config" grep -q '^osascript .*config:' "$work/x1.calls"
need "a clone or build ran on a bad config" test -z "$(grep -v '^osascript ' "$work/x1.calls" "$calls")"
end_case "install: config-refused"
home=$work/y; mkdir -p "$(dirname "$(stamp_of "$home" AdBlock)")"; printf '%s\n' $(( $(date +%s) - 301 * 86400 )) > "$(stamp_of "$home" AdBlock)"
icfg "$(apps "$(app AdBlock)" "$(app Other)")"; install_run "$home"
need "exit $rc" test "$rc" -eq 0
need "no overdue alert for AdBlock" grep -q '^osascript .*Reinstall overdue for AdBlock' "$calls"
need "overdue alert for Other, which has no stamp" not grep -q '^osascript .*Reinstall overdue for Other' "$calls"
need "a stamp was not written fresh" test -f "$(stamp_of "$home" Other)"
end_case "install: per-app-stamp"
icfg "$(apps "$(app AdBlock)")"
home=$work/z1; install_run "$home"
need "not Release" grep -q '^xcodebuild .*-configuration Release ' "$calls.args"
need "install not from Release-iphoneos" grep -q '^xcrun .*/Release-iphoneos/AdBlock.app' "$calls.args"
end_case "install: Release by default"
home=$work/z2; install_run "$home" --debug
need "not Debug" grep -q '^xcodebuild .*-configuration Debug ' "$calls.args"
need "install not from Debug-iphoneos" grep -q '^xcrun .*/Debug-iphoneos/AdBlock.app' "$calls.args"
end_case "install: --debug forces Debug"
icfg "$(apps "$(app AdBlock '{"configuration":"Debug"}')")"; home=$work/z3; install_run "$home"
need "not Debug" grep -q '^xcodebuild .*-configuration Debug ' "$calls.args"
end_case "install: the configuration key"
icfg "$(apps "$(app AdBlock '{"configuration":"../x"}')")"; home=$work/z4; install_run "$home"
need "exit 0" test "$rc" -ne 0
need "no configuration notice" grep -q 'configuration must be Release or Debug' "$out"
need "build ran" not built
end_case "install: unknown configuration refused"
icfg "$(apps "$(app AdBlock)")"
home=$work/y1; install_run "$home"
need "exit $rc" test "$rc" -eq 0
need "build not aimed at the phone" grep -q '^xcodebuild .*-destination id=FAKE-DEVICE-0001 ' "$calls.args"
need "no device registration" grep -q '^xcodebuild .*-allowProvisioningDeviceRegistration' "$calls.args"
need "install not aimed at the phone" grep -q '^xcrun .*--device FAKE-DEVICE-0001 ' "$calls.args"
end_case "install: build aimed at the phone"
home=$work/y2; XCODEBUILD_OUT='xcodebuild: error: Unable to find a device matching the provided destination specifier:' XCODEBUILD_RC=70 install_run "$home"
need "exit $rc, want 75" test "$rc" -eq 75
need "install ran" not grep -q '^install$' "$calls"
end_case "install: phone absent at build is exit 75"
home=$work/y3; XCODEBUILD_OUT='error: file could not be found' XCODEBUILD_RC=65 install_run "$home"
need "exit $rc, want 65" test "$rc" -eq 65
end_case "install: a build error is not soft"
home=$work/k1; install_run "$home"
need "key flags missing" grep -q -- "^xcodebuild .*-authenticationKeyPath $work/key.p8 -authenticationKeyID KEYFAKE001 -authenticationKeyIssuerID 00000000-0000-0000-0000-00000000FAKE " "$calls.args"
end_case "install: key flags when the key file exists"
rm -f "$work/key.p8"; home=$work/k2; install_run "$home"
need "exit $rc" test "$rc" -eq 0
need "key flags without a key file" not args_have 'authenticationKey'
end_case "install: no key file, build without key flags"
printf x > "$work/key.p8"; chmod 000 "$work/key.p8"

# IDs and the other new install behaviour
for k in team_id device_udid asc_key_path asc_key_id asc_issuer_id; do
  icfg "$(apps "$(app AdBlock)")" "del(.$k)"; home=$work/id-$k; install_run "$home"
  need "$k: exit 0, want non-zero" test "$rc" -ne 0
  need "$k: clone or build ran" test -z "$(non_notify)"
  need "$k: notice does not name it" grep -q "$k" "$out"
  end_case "install: missing $k refused"
done
icfg "$(apps "$(app AdBlock)")" 'del(.repo_url)'; home=$work/id-url; install_run "$home"
need "exit $rc, want non-zero" test "$rc" -ne 0
need "clone ran" test -z "$(non_notify)"
end_case "install: missing repo_url refused"
icfg "$(apps "$(app AdBlock)")" 'del(.team_id)'; home=$work/env1; TEAM_ID=TEAMENV001 install_run "$home"
need "exit $rc" test "$rc" -eq 0
need "env team not used" args_have 'DEVELOPMENT_TEAM=TEAMENV001'
end_case "install: env fills an ID the config lacks"
icfg "$(apps "$(app AdBlock)")"; home=$work/env2; DEVICE_UDID=FAKE-DEVICE-ENV install_run "$home"
need "env device not used" grep -q '^xcodebuild .*-destination id=FAKE-DEVICE-ENV ' "$calls.args"
end_case "install: env wins over the config"
icfg "$(apps "$(app AdBlock '{"product_name":"Como TV"}')")"; home=$work/pn; install_run "$home"
need "exit $rc" test "$rc" -eq 0
need "install path does not use product_name" grep -q '/Release-iphoneos/Como TV.app' "$calls.args"
need "the scheme was used for the path" not grep -q '/Release-iphoneos/AdBlock.app' "$calls.args"
end_case "install: product_name names the .app"
icfg "$(apps "$(app AdBlock '{"trust_package_plugins":true}')")"; home=$work/tp; install_run "$home"
need "plugin flags missing" grep -q '^xcodebuild .*-skipPackagePluginValidation -skipMacroValidation' "$calls.args"
end_case "install: trust_package_plugins adds both flags"
icfg "$(apps "$(app AdBlock '{"project_yml":null}')")"; home=$work/ny; install_run "$home"
need "exit $rc" test "$rc" -eq 0
need "xcodegen ran" not grep -qx xcodegen "$calls"
end_case "install: no project_yml means no xcodegen"
icfg "$(apps "$(app A)" "$(app B)")"; home=$work/ap; install_run "$home" --app B
need "exit $rc" test "$rc" -eq 0
need "A was handled" not test -d "$(repo_of "$home" A)"
need "B was not handled" test -d "$(repo_of "$home" B)"
end_case "install: --app limits the run"
home=$work/ap2; install_run "$home" --app Nope
need "exit $rc, want 2" test "$rc" -eq 2
need "clone ran" test -z "$(non_notify)"
end_case "install: --app with an unknown name exits 2"

# install copy_in
ci_conf() { icfg "$(apps "$(app AdBlock "$1")")"; }
ci_conf "$(copy_in "$work/secrets/Secret.xcconfig" ios/Secret.xcconfig)"
home=$work/ci1; COPY_PROBE="$(repo_of "$home" AdBlock)/ios/Secret.xcconfig" install_run "$home"
need "exit $rc" test "$rc" -eq 0
need "copy missing during the build" grep -qx 'build present' "$calls.probe"
need "copy left in the clone" not test -e "$(repo_of "$home" AdBlock)/ios/Secret.xcconfig"
end_case "install: copy_in is copied for the build and removed after it"
home=$work/ci2; COPY_PROBE="$(repo_of "$home" AdBlock)/ios/Secret.xcconfig" XCODEBUILD_RC=1 install_run "$home"
need "exit 0, want non-zero" test "$rc" -ne 0
need "copy not there during the build" grep -qx 'build present' "$calls.probe"
need "copy left after a failed build" not test -e "$(repo_of "$home" AdBlock)/ios/Secret.xcconfig"
end_case "install: copy_in removed after a failed build"
ci_conf "$(copy_in "$work/secrets/Secret.xcconfig" ios/NotIgnored.xcconfig)"
home=$work/ci3; install_run "$home"
need "exit 0, want non-zero" test "$rc" -ne 0
need "build or prebuild ran" not grep -qE '^(xcodebuild|build-rules)$' "$calls"
need "copy made anyway" not test -e "$(repo_of "$home" AdBlock)/ios/NotIgnored.xcconfig"
end_case "install: copy_in to a path that is not git-ignored refused"
ci_conf "$(copy_in "$work/secrets/Missing.xcconfig" ios/Secret.xcconfig)"
home=$work/ci4; install_run "$home"
need "exit 0, want non-zero" test "$rc" -ne 0
need "build ran" not built
end_case "install: copy_in with a missing source refused"
mkdir -p "$work/cfgrepo/secrets"; printf s > "$work/cfgrepo/secrets/Secret.xcconfig"
ci_conf "$(copy_in secrets/Secret.xcconfig ios/Secret.xcconfig)"
home=$work/ci5; COPY_PROBE="$(repo_of "$home" AdBlock)/ios/Secret.xcconfig" install_run "$home"
need "exit $rc" test "$rc" -eq 0
need "relative from not resolved against the config's repo root" grep -qx 'build present' "$calls.probe"
end_case "install: a relative copy_in.from resolves against the config's repo root"
mkdir -p "$work/ci6home/s"; printf s > "$work/ci6home/s/S.xcconfig"
# shellcheck disable=SC2088  # the literal ~/ is the point: the tool expands it
ci_conf "$(copy_in '~/s/S.xcconfig' ios/Secret.xcconfig)"
home=$work/ci6home; COPY_PROBE="$(repo_of "$home" AdBlock)/ios/Secret.xcconfig" install_run "$home"
need "exit $rc" test "$rc" -eq 0
need "tilde not expanded to HOME" grep -qx 'build present' "$calls.probe"
end_case "install: ~/ in copy_in.from expands to HOME"

# ===================== account file and an optional CONFIG =====================
# The account values come from env first, then the repo config, then $HOME/.config/ios-ship/account.json.
# Each case that writes an account file uses its own fixture HOME, so no case reads another case's file.
one_app "" 'del(.team_id,.device_udid,.asc_key_path,.asc_key_id,.asc_issuer_id)'; acct "$work/acct1"
run testflight "$tfconf" "$work/acct1"
need "rc=$rc: $(tail -1 "$out")" test "$rc" -eq 0
need "account team not used" args_have 'DEVELOPMENT_TEAM=TEAMACCT01'
need "account key ID not used" args_have '-authenticationKeyID KEYACCT001 '
end_case "tf: the account file supplies every ID the config lacks"
one_app "" 'del(.device_udid,.asc_key_path,.asc_key_id,.asc_issuer_id)'; acct "$work/acct2"
run testflight "$tfconf" "$work/acct2"
need "rc=$rc: $(tail -1 "$out")" test "$rc" -eq 0
need "config team not used" args_have 'DEVELOPMENT_TEAM=TEAMFAKE01'
need "account team beat the config" not args_have 'DEVELOPMENT_TEAM=TEAMACCT01'
end_case "tf: the config's team ID wins over the account file"
one_app "" 'del(.device_udid,.asc_key_path,.asc_key_id,.asc_issuer_id)'; acct "$work/acct3"
TEAM_ID=TEAMENV003 run testflight "$tfconf" "$work/acct3"
need "rc=$rc: $(tail -1 "$out")" test "$rc" -eq 0
need "env team not used" args_have 'DEVELOPMENT_TEAM=TEAMENV003'
need "config team used" not args_have 'DEVELOPMENT_TEAM=TEAMFAKE01'
need "account team used" not args_have 'DEVELOPMENT_TEAM=TEAMACCT01'
end_case "tf: an env team ID wins over the config and the account file"
# A key unset in env, config and account file is refused. The notice names the config, the account file and the env var.
for pair in team_id:TEAM_ID asc_key_path:ASC_KEY_PATH asc_key_id:ASC_KEY_ID asc_issuer_id:ASC_ISSUER_ID; do
  k=${pair%%:*}; ev=${pair#*:}
  one_app "" "del(.$k)"; acct "$work/acct-$k" "del(.$k)"
  run testflight "$tfconf" "$work/acct-$k"
  need "$k: rc=$rc, want non-zero" test "$rc" -ne 0
  need "$k: build ran" not built
  need "$k: notice lacks the config path: $(tail -1 "$out")" grep -qF "$tfconf" "$out"
  need "$k: notice lacks the account file" grep -qF "$work/acct-$k/.config/ios-ship/account.json" "$out"
  need "$k: notice lacks $ev" grep -qF "$ev" "$out"
  end_case "tf: $k unset in env, config and account file is refused, and the notice names both files and $ev"
done
icfg "$(apps "$(app AdBlock)")" 'del(.team_id,.device_udid,.asc_key_path,.asc_key_id,.asc_issuer_id)'; acct "$work/acct-i1"
install_run "$work/acct-i1"
need "exit $rc" test "$rc" -eq 0
need "account team not used" args_have 'DEVELOPMENT_TEAM=TEAMACCT01'
need "account phone not used" args_have 'destination id=FAKE-DEVICE-ACCT '
end_case "install: the account file supplies the phone and the team"
icfg "$(apps "$(app AdBlock)")" 'del(.device_udid)'; acct "$work/acct-i2" 'del(.device_udid)'
install_run "$work/acct-i2"
need "exit $rc, want non-zero" test "$rc" -ne 0
need "a clone or build ran" test -z "$(non_notify)"
need "notice lacks the config path: $(tail -1 "$out")" grep -qF "$iconf" "$out"
need "notice lacks the account file" grep -qF "$work/acct-i2/.config/ios-ship/account.json" "$out"
need "notice lacks DEVICE_UDID" grep -qF DEVICE_UDID "$out"
end_case "install: device_udid unset in env, config and account file is refused, and the notice names both files and DEVICE_UDID"

# ===================== profile: one xctrace recording, retried once after the boot wait =====================
# xctrace on a network-paired phone can fail with "Waiting for device to boot" while the phone is fine. One retry after a
# fixed wait; any other failure is not retried. The sleep is stubbed, so no case waits.
icfg "$(apps "$(app AdBlock)" "$(app Other)")"
prof() { SLEEP_FAKE=1 run profile "$iconf" "$work/prof" "$@"; }   # ARGS...
pcalls() { tr '\n' ' ' < "$calls" | sed 's/ $//'; }
XCTRACE_PLAN=ok prof --app AdBlock
need "exit $rc, want 0: $(tail -1 "$out")" test "$rc" -eq 0
need "calls: $(pcalls)" test "$(pcalls)" = "xctrace"
end_case "profile: a first recording that passes is one call, no sleep, exit 0"
XCTRACE_PLAN="boot ok" prof --app AdBlock
need "exit $rc, want 0: $(tail -1 "$out")" test "$rc" -eq 0
need "calls: $(pcalls)" test "$(pcalls)" = "xctrace sleep 60 xctrace"
need "no line names the wait" grep -q 'Waiting for device to boot' "$out"
end_case "profile: the boot wait, then a pass, is two calls with one 60 s sleep between, exit 0"
XCTRACE_PLAN="boot boot" prof --app AdBlock
need "exit $rc, want 13 (xctrace's code)" test "$rc" -eq 13
need "calls: $(pcalls)" test "$(pcalls)" = "xctrace sleep 60 xctrace"
need "the last line names no log: $(tail -1 "$out")" grep -qE 'see .*ios-ship-profile' "$out"
need "no line says the phone may need unlocking or a cable" grep -qE 'unlock.*cable' "$out"
end_case "profile: two boot waits are two calls and exit with xctrace's code"
XCTRACE_PLAN="disk-full" prof --app AdBlock
need "exit $rc, want 7 (xctrace's code)" test "$rc" -eq 7
need "calls: $(pcalls)" test "$(pcalls)" = "xctrace"
end_case "profile: a failure without the boot wait is not retried and exits with xctrace's code"
XCTRACE_PLAN="boot ok" prof --app AdBlock --retry-wait 5 --template Allocations --time-limit 7 --output "$work/p.trace"
need "exit $rc, want 0: $(tail -1 "$out")" test "$rc" -eq 0
need "calls: $(pcalls)" test "$(pcalls)" = "xctrace sleep 5 xctrace"
need "xctrace not aimed at the phone's UDID" args_have '^xcrun xctrace record .*--device FAKE-DEVICE-0001 '
need "xctrace not launching the app's bundle id" args_have "--launch -- dev.example.AdBlock\$"
need "template, time limit or output not passed" args_have "--template Allocations --device FAKE-DEVICE-0001 --time-limit 7s --output $work/p.trace "
need "xctrace given a device name" not grep -qE -- '--device [^ ]*[^-A-Z0-9 ]' "$calls.args"
end_case "profile: records by UDID with the app's bundle id, and --retry-wait 5 sleeps 5"
XCTRACE_PLAN="boot boot" XCTRACE_MAKE_OUTPUT=1 prof --app AdBlock --output "$work/p3.trace"
need "exit $rc, want 13" test "$rc" -eq 13
need "calls: $(pcalls)" test "$(pcalls)" = "xctrace sleep 60 xctrace"
need "the partial trace of the first try was not removed before the retry" not grep -q 'output exists' "$out"
end_case "profile: a partial trace from a boot failure is removed before the retry"
XCTRACE_PLAN="boot other" prof --app AdBlock
need "exit $rc, want 7" test "$rc" -eq 7
need "calls: $(pcalls)" test "$(pcalls)" = "xctrace sleep 60 xctrace"
need "a line says the phone may need unlocking or a cable" not grep -qE 'unlock.*cable' "$out"
end_case "profile: a retry that fails another way exits with its code and names no cable"
XCTRACE_PLAN="boot hang" STEP_TIMEOUT=1 prof --app AdBlock
need "exit $rc, want 124" test "$rc" -eq 124
need "calls: $(pcalls)" test "$(pcalls)" = "xctrace sleep 60 xctrace"
need "no line names the step and its 1 s timeout" grep -q 'step xctrace record timed out after 1s' "$out"
need "a line says the phone may need unlocking or a cable" not grep -qE 'unlock.*cable' "$out"
end_case "profile: a retry that hangs in its save names the timeout and the step, and no cable"
XCTRACE_PLAN="hang" STEP_TIMEOUT=1 prof --app AdBlock
need "exit $rc, want 124" test "$rc" -eq 124
need "calls: $(pcalls)" test "$(pcalls)" = "xctrace"
need "no line names the step and its 1 s timeout" grep -q 'step xctrace record timed out after 1s' "$out"
need "a line says the phone may need unlocking or a cable" not grep -qE 'unlock.*cable' "$out"
end_case "profile: a first try that hangs is not retried, and names the timeout and the step"
XCTRACE_PLAN=ok DEVICE_UDID=FAKE-DEVICE-ENV1 prof --app Other
need "exit $rc, want 0" test "$rc" -eq 0
need "the env UDID or the named app was not used" args_have '--device FAKE-DEVICE-ENV1 .*--launch -- dev.example.Other$'
end_case "profile: the UDID comes from the env first, and --app picks the app"
for a in "" "--app AdBlock --app Other" "--app AdBlock --retry-wait x" "--app AdBlock --time-limit 0"; do
  # shellcheck disable=SC2086
  XCTRACE_PLAN=ok prof $a
  need "[$a] exit $rc, want 2" test "$rc" -eq 2
  need "[$a] xctrace ran" test ! -s "$calls"
done
end_case "profile: no --app, two --app, or a bad number exits 2 with no recording"
mkdir -p "$work/p2.trace"; XCTRACE_PLAN=ok prof --app AdBlock --output "$work/p2.trace"
need "exit $rc, want non-zero" test "$rc" -ne 0
need "xctrace ran over an existing output" test ! -s "$calls"
end_case "profile: an output path that exists is refused before any recording"
icfg "$(apps "$(app AdBlock)")"
install_run "$work/prof2" --retry-wait 5
need "install: exit $rc, want 2" test "$rc" -eq 2
end_case "install: --retry-wait is a profile option and exits 2"

# No CONFIG: the default is tools/ios-ship.json at the git toplevel of the current folder. It runs the calls that passing that path runs.
one_app; run testflight "$tfconf" "$work/home"
need "passed CONFIG: rc=$rc" test "$rc" -eq 0
trace "$work/explicit.trace"
run_in "$work/repo" testflight "$work/home"
need "no CONFIG: rc=$rc: $(cat "$work/stdout" "$out" | tail -1)" test "$rc" -eq 0
need "no CONFIG: no xcodebuild call" built
trace "$work/implicit.trace"
need "no CONFIG ran other calls than passing CONFIG" cmp -s "$work/implicit.trace" "$work/explicit.trace"
end_case "tf: no CONFIG in a repo with tools/ios-ship.json runs the same calls as passing it"
one_app; run testflight "$tfconf" "$work/home"
need "passed CONFIG: rc=$rc" test "$rc" -eq 0
trace "$work/explicit.trace"
run_in "$work/repo/ios" testflight "$work/home"
need "no CONFIG from a subfolder: rc=$rc: $(cat "$work/stdout" "$out" | tail -1)" test "$rc" -eq 0
trace "$work/implicit.trace"
need "no CONFIG from a subfolder ran other calls than passing CONFIG" cmp -s "$work/implicit.trace" "$work/explicit.trace"
end_case "tf: no CONFIG from a subfolder of the repo finds the repo's tools/ios-ship.json"
icfg "$(apps "$(app AdBlock)")"
install_run "$work/n1" --no-install
need "passed CONFIG: rc=$rc" test "$rc" -eq 0
trace "$work/explicit.trace"
run_in "$work/cfgrepo" install "$work/n2" --no-install
need "no CONFIG: rc=$rc: $(cat "$work/stdout" "$out" | tail -1)" test "$rc" -eq 0
trace "$work/implicit.trace"
need "no CONFIG ran other calls than passing CONFIG" cmp -s "$work/implicit.trace" "$work/explicit.trace"
end_case "install: no CONFIG in a repo, with --no-install right after the job, runs the same calls as passing it"

one_app; run testflight "$tfconf" "$work/home" --export-only
need "passed CONFIG: rc=$rc" test "$rc" -eq 0
trace "$work/explicit.trace"
run_in "$work/repo" testflight "$work/home" --export-only
need "no CONFIG: rc=$rc: $(cat "$work/stdout" "$out" | tail -1)" test "$rc" -eq 0
trace "$work/implicit.trace"
need "no CONFIG ran other calls than passing CONFIG" cmp -s "$work/implicit.trace" "$work/explicit.trace"
end_case "tf: no CONFIG with --export-only right after the job runs the same calls as passing it"

# No CONFIG and no repo config: exit 2 with one line on stderr, and nothing is built.
mkdir -p "$work/nowhere"
"$REAL_GIT" init -q -b main "$work/norepo" >> "$work/git.log" 2>&1
for job in testflight install; do
  run_in "$work/nowhere" "$job" "$work/n3"
  need "$job: the folder is inside a git repo" outside_repo "$work/nowhere"
  need "$job: rc=$rc, want 2" test "$rc" -eq 2
  need "$job: stdout is not empty" test ! -s "$work/stdout"
  need "$job: stderr is not one line" test "$(wc -l < "$out" | tr -d ' ')" -eq 1
  need "$job: the line does not name tools/ios-ship.json: $(cat "$out")" grep -qF 'tools/ios-ship.json' "$out"
  need "$job: xcodebuild ran" not built
  end_case "$job: no CONFIG outside a git repo exits 2 with one line and no xcodebuild"
done
for job in testflight install; do
  run_in "$work/norepo" "$job" "$work/n4"
  need "$job: rc=$rc, want 2" test "$rc" -eq 2
  need "$job: stdout is not empty" test ! -s "$work/stdout"
  need "$job: stderr is not one line" test "$(wc -l < "$out" | tr -d ' ')" -eq 1
  need "$job: the line does not name tools/ios-ship.json: $(cat "$out")" grep -qF 'tools/ios-ship.json' "$out"
  need "$job: xcodebuild ran" not built
  end_case "$job: no CONFIG in a repo without tools/ios-ship.json exits 2 with one line and no xcodebuild"
done

# PHONE_APPS_JSON is the old install variable: install refuses it and names the replacement.
icfg "$(apps "$(app AdBlock)")"
PHONE_APPS_JSON='[{"name":"AdBlock"}]' install_run "$work/pj"
need "exit $rc, want 2" test "$rc" -eq 2
need "notice lacks --app: $(tail -1 "$out")" grep -qF -- '--app' "$out"
need "notice lacks tools/ios-ship.json" grep -qF 'tools/ios-ship.json' "$out"
need "xcodebuild ran" not built
end_case "install: PHONE_APPS_JSON is refused with exit 2, and the notice names --app and tools/ios-ship.json"

# PHONE_APPS_JSON set to an empty value is still set, so install refuses it.
icfg "$(apps "$(app AdBlock)")"
PHONE_APPS_JSON='' install_run "$work/pj2"
need "exit $rc, want 2" test "$rc" -eq 2
need "notice lacks --app: $(tail -1 "$out")" grep -qF -- '--app' "$out"
need "xcodebuild ran" not built
end_case "install: PHONE_APPS_JSON set but empty is refused with exit 2 and no xcodebuild"

# An account file that is not JSON gives no values. The refusal names both files, and jq prints no error.
one_app "" 'del(.team_id)'; mkdir -p "$work/bad1/.config/ios-ship"; printf 'not json\n' > "$work/bad1/.config/ios-ship/account.json"
run testflight "$tfconf" "$work/bad1"
need "rc=$rc, want non-zero" test "$rc" -ne 0
need "build ran" not built
need "notice lacks the config path: $(tail -1 "$out")" grep -qF "$tfconf" "$out"
need "notice lacks the account file" grep -qF "$work/bad1/.config/ios-ship/account.json" "$out"
need "jq printed an error: $(tail -1 "$out")" not grep -qiE 'parse error|^jq' "$out"
end_case "tf: an account file that is not JSON gives no values: the refusal names both files, with no jq error"

# HOME empty or unset, and no key in env or config: no account file can be named, so the notice must not name /.config/ios-ship/account.json.
one_app "" 'del(.asc_key_path)'
run testflight "$tfconf" ""
need "rc=$rc, want non-zero" test "$rc" -ne 0
need "build ran" not built
need "notice names /.config/ios-ship/account.json: $(tail -1 "$out")" not grep -qF '/.config/ios-ship/account.json' "$out"
need "notice lacks ASC_KEY_PATH" grep -qF ASC_KEY_PATH "$out"
end_case "tf: HOME empty, no key in env or config: refused, and the notice does not name /.config/ios-ship/account.json"
one_app "" 'del(.asc_key_path)'
no_home=1 run testflight "$tfconf" ""
need "rc=$rc, want non-zero" test "$rc" -ne 0
need "build ran" not built
need "notice names /.config/ios-ship/account.json: $(tail -1 "$out")" not grep -qF '/.config/ios-ship/account.json' "$out"
need "notice lacks ASC_KEY_PATH" grep -qF ASC_KEY_PATH "$out"
end_case "tf: HOME unset, no key in env or config: refused, and the notice does not name /.config/ios-ship/account.json"

# No CONFIG outside a git repo: there is no toplevel, so the notice must not claim one or name /tools/ios-ship.json.
# No file is made at that root path: the test would have to write to / on the owner's Mac.
for job in testflight install; do
  run_in "$work/nowhere" "$job" "$work/n6"
  need "$job: rc=$rc, want 2" test "$rc" -eq 2
  need "$job: the notice claims a git toplevel: $(cat "$out")" not grep -qF toplevel "$out"
  need "$job: the notice names /tools/ios-ship.json" not grep -qF '/tools/ios-ship.json' "$out"
  end_case "$job: no CONFIG outside a git repo: the notice names no git toplevel and no /tools/ios-ship.json"
done

# ===================== run folder: sweep and teardown (decisions/test-temp-standard.md) =====================
# The probe child sweeps the same temp root on its first request, prints its folder, and exits.
old=$tmp_root/999991-$(uuidgen | tr 'A-Z' 'a-z'); new=$tmp_root/999992-$(uuidgen | tr 'A-Z' 'a-z'); keep=$tmp_root/keep-me
mkdir "$old" "$new" "$keep" || exit 1
perl -e 'utime(time()-172800, time()-172800, @ARGV)' "$old" "$keep"
probe=$(IOS_SHIP_TEST_PROBE=1 "$BASH" "$0" 2>&1)
child=$(printf '%s\n' "$probe" | sed -n 's/^run folder: //p')
need "the probe printed no run folder: $probe" test -n "$child"
need "the first request kept an old sibling run folder" not test -e "$old"
need "the first request removed a new sibling run folder" test -e "$new"
need "the first request removed a folder that is not a run folder" test -e "$keep"
end_case "run folder: the first request removes an old sibling and keeps a new one"
need "the probe printed no run folder: $probe" test -n "$child"
need "the run folder is still there after the run: $child" not test -e "$child"
end_case "run folder: teardown removes the run folder"
rm -rf "$old" "$new" "$keep"

echo "TALLY: $pass_n passed, $fail_n failed${failed:+: $failed}"
exit $fail

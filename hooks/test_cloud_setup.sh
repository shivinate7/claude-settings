#!/bin/sh
# Cases for cloud-setup.sh, the cloud environment's setup script. It fetches install.sh (the raw
# GitHub copy first, else the copy in a local checkout), runs that copy under a timeout, and exits 0
# with one verdict line whatever install.sh does. Named cases, each isolated, a pass/fail line per
# case, and a summary exit code, in the style of hooks/test_install_src.sh.
#
# Run it from the repository root:
#
#   sh hooks/test_cloud_setup.sh [case ...]   # names given: run only those cases
#
# CLOUD_SETUP_SH_UNDER_TEST points a run at another copy of the script.
#
# No case reaches the network. Every run starts from an empty environment (env -i) with a dead
# proxy and a dead raw URL. A fake curl stands in for the fetch, and a pipx stub keeps install.sh
# from running pip. Temp files live in one run folder (lint/_test_temp.py), removed at exit.
# The suite needs a GNU-style `timeout` on PATH.

set -u

HERE="$(cd "$(dirname "$0")" && pwd)"
REPO_ROOT="$(cd "$HERE/.." && pwd)"
SETUP_SH="${CLOUD_SETUP_SH_UNDER_TEST:-$REPO_ROOT/cloud-setup.sh}"
ORIGIN="https://github.com/shivinate7/claude-settings.git"
DEAD_RAW="http://127.0.0.1:9/raw"
DEAD_PROXY="http://127.0.0.1:9"
BASE_PATH="$PATH"
ONLY="$*"

PASS=0
FAIL=0

ok() { PASS=$((PASS + 1)); printf 'ok   - %s\n' "$1"; }
bad() { FAIL=$((FAIL + 1)); printf 'FAIL - %s: %s\n' "$1" "$2"; }

# One run folder per test run. The one home is lint/_test_temp.py. Its first request also sweeps
# old sibling run folders, and caseSweep proves that.
RUN=$(python3 -I -c 'import sys; sys.path.insert(0, sys.argv[1]); import _test_temp; print(_test_temp.run_folder())' "$REPO_ROOT/lint") || RUN=""
if [ -z "$RUN" ]; then
  echo "FAIL - run folder: lint/_test_temp.py made no run folder"
  exit 1
fi
trap 'rm -rf "$RUN"' EXIT

# shellcheck source=../testing/tracked_tree.sh
TRACKED_ROOT=$REPO_ROOT
. "$TRACKED_ROOT/testing/tracked_tree.sh"  # copies what git lists, so no fixture lists files

# The checkout every case copies: the repo's tracked files, with origin set to the GitHub URL.
MASTER="$RUN/master"
if ! copy_tracked "$MASTER" .; then
  echo "FAIL - fixture: tracked_tree.sh could not copy the repo"
  exit 1
fi
git -C "$MASTER" init -q -b master
git -C "$MASTER" remote add origin "$ORIGIN"
git -C "$MASTER" add -A
git -C "$MASTER" -c user.email=t@example.com -c user.name=t commit -q -m init

# A fresh case folder: HOME, config dir, a cwd outside any repo, search roots, a temp dir and a bin
# dir holding the pipx stub. Prints the folder.
new_case() {
  nc="$RUN/$1"
  rm -rf "$nc"
  mkdir -p "$nc/home" "$nc/cfg" "$nc/cwd" "$nc/roots" "$nc/tmp" "$nc/bin"
  printf '#!/bin/sh\nexit 0\n' > "$nc/bin/pipx"
  chmod +x "$nc/bin/pipx"
  printf '%s\n' "$nc"
}

# Put a copy of the fixture checkout at <case>/roots/claude-settings, the name the search finds.
add_checkout() {
  rm -rf "$1/roots/claude-settings"
  cp -R "$MASTER" "$1/roots/claude-settings"
}

# fake_curl <case> <mode> [body]: fail exits 7, as a refused connection does. hang exits 28 when
# --max-time is given, as curl does when that limit passes, and sleeps otherwise. serve writes the
# body to the -o file, or to stdout. Every call's argv is appended to <case>/curl.log.
fake_curl() {
  cat > "$1/bin/curl" <<EOF
#!/bin/sh
printf '%s\n' "\$*" >> "$1/curl.log"
case "$2" in
  fail) exit 7 ;;
  hang)
    for a in "\$@"; do [ "\$a" = --max-time ] && exit 28; done
    exec sleep 120 ;;
  serve)
    out=""; prev=""
    for a in "\$@"; do [ "\$prev" = -o ] && out="\$a"; prev="\$a"; done
    if [ -n "\$out" ]; then cp "${3:-/dev/null}" "\$out"; else cat "${3:-/dev/null}"; fi ;;
esac
EOF
  chmod +x "$1/bin/curl"
}

# run_setup <case> <name> [VAR=value ...]: runs the script in an empty environment from the case's
# cwd, with output in <case>/out-<name>.txt. Sets rc to its exit code and secs to its wall time.
# Output goes to a file, so a child left running cannot hold a pipe open.
run_setup() {
  rs_c=$1
  rs_n=$2
  rs_extra=${3:-}
  rs_t0=$(date +%s)
  ( cd "$rs_c/cwd" && env -i PATH="$rs_c/bin:$BASE_PATH" HOME="$rs_c/home" \
      CLAUDE_CONFIG_DIR="$rs_c/cfg" TMPDIR="$rs_c/tmp" GIT_CEILING_DIRECTORIES="$rs_c/cwd" \
      CLAUDE_SETTINGS_SEARCH_ROOTS="$rs_c/roots" CLAUDE_SETTINGS_RAW="$DEAD_RAW" \
      HTTPS_PROXY="$DEAD_PROXY" https_proxy="$DEAD_PROXY" $rs_extra \
      timeout 90 bash "$SETUP_SH" < /dev/null > "$rs_c/out-$rs_n.txt" 2>&1 )
  rc=$?
  secs=$(( $(date +%s) - rs_t0 ))
}

# The verdict lines of a run's output, and the first of them.
verdict_count() { grep -c '^claude-settings setup: ' "$1"; }
verdict_text() { grep '^claude-settings setup: ' "$1" | head -n 1; }

# The first 200 characters of a run's output on one line, for a FAIL line.
brief() { tr '\n' ' ' < "$1" | cut -c1-200; }

says_installed() {
  case "$1" in
    *"not installed"*) return 1 ;;
    *installed*) return 0 ;;
  esac
  return 1
}

# True when the case's curl log shows the raw install.sh fetch with curl's --max-time 20.
fetch_asked() {
  grep -qF -- '--max-time 20' "$1/curl.log" 2>/dev/null && grep -qF -- "$DEAD_RAW/install.sh" "$1/curl.log" 2>/dev/null
}

# The checksums of the install's agents and settings, in a stable order.
snapshot() {
  ( cd "$1/cfg" 2>/dev/null && find agents settings.json -type f 2>/dev/null | sort | while IFS= read -r f; do cksum "$f"; done )
}

# ---- a: checkout under a search root, no network: installs, one verdict line says installed ----
caseA() {
  name="a: checkout under a search root, no network: installs, exits 0, one verdict line says installed"
  c=$(new_case caseA)
  add_checkout "$c"
  fake_curl "$c" fail
  run_setup "$c" a
  v=$(verdict_text "$c/out-a.txt")
  if [ "$rc" -ne 0 ]; then
    bad "$name" "exit $rc: $(brief "$c/out-a.txt")"
  elif [ ! -f "$c/cfg/agents/builder.md" ]; then
    bad "$name" "agents/builder.md did not land"
  elif [ ! -f "$c/cfg/settings.json" ]; then
    bad "$name" "settings.json did not land"
  elif [ "$(verdict_count "$c/out-a.txt")" != 1 ]; then
    bad "$name" "expected one verdict line, got $(verdict_count "$c/out-a.txt")"
  elif ! says_installed "$v"; then
    bad "$name" "verdict does not say installed: $v"
  else
    case "$v" in
      *"no source"*|*"timed out"*|*exit*) bad "$name" "verdict names a failure: $v" ;;
      *) ok "$name" ;;
    esac
  fi
}

# ---- b: no checkout, no network: exits 0, one verdict line names no source, no builder.md ------
caseB() {
  name="b: no checkout, no network: exits 0, one verdict line names no source, no builder.md"
  c=$(new_case caseB)
  fake_curl "$c" fail
  run_setup "$c" b
  v=$(verdict_text "$c/out-b.txt")
  if [ "$rc" -ne 0 ]; then
    bad "$name" "exit $rc: $(brief "$c/out-b.txt")"
  elif [ "$(verdict_count "$c/out-b.txt")" != 1 ]; then
    bad "$name" "expected one verdict line, got $(verdict_count "$c/out-b.txt")"
  elif [ -e "$c/cfg/agents/builder.md" ]; then
    bad "$name" "agents/builder.md landed with no source"
  elif ! printf '%s\n' "$v" | grep -q 'no source'; then
    bad "$name" "verdict does not name no source: $v"
  elif ! fetch_asked "$c"; then
    bad "$name" "raw install.sh was not fetched with --max-time 20: $(brief "$c/curl.log")"
  else
    ok "$name"
  fi
}

# ---- c: fetch hangs until curl's --max-time: returns within 30 s, exit 0, one verdict line ------
caseC() {
  name="c: hung fetch: curl stops at --max-time, the script returns within 30 s, exit 0, one verdict line"
  c=$(new_case caseC)
  fake_curl "$c" hang
  run_setup "$c" c
  v=$(verdict_text "$c/out-c.txt")
  if [ "$rc" -ne 0 ]; then
    bad "$name" "exit $rc (124 means it hung past the 90 s bound): $(brief "$c/out-c.txt")"
  elif [ "$secs" -gt 30 ]; then
    bad "$name" "took $secs s, over the 30 s bound"
  elif [ "$(verdict_count "$c/out-c.txt")" != 1 ]; then
    bad "$name" "expected one verdict line, got $(verdict_count "$c/out-c.txt")"
  elif ! printf '%s\n' "$v" | grep -q 'no source'; then
    bad "$name" "verdict does not name no source: $v"
  else
    ok "$name"
  fi
}

# ---- c2: install run past CLAUDE_SETTINGS_SETUP_CAP: stopped, exit 0, verdict says timed out ---
caseC2() {
  name="c2: install run past CLAUDE_SETTINGS_SETUP_CAP: stopped, returns within 30 s, exit 0, verdict says timed out"
  c=$(new_case caseC2)
  printf '#!/bin/sh\nexec sleep 300\n' > "$c/served.sh"
  fake_curl "$c" serve "$c/served.sh"
  run_setup "$c" c2 "CLAUDE_SETTINGS_SETUP_CAP=2"
  v=$(verdict_text "$c/out-c2.txt")
  if [ "$rc" -ne 0 ]; then
    bad "$name" "exit $rc: $(brief "$c/out-c2.txt")"
  elif [ "$secs" -gt 30 ]; then
    bad "$name" "took $secs s, over the 30 s bound"
  elif [ "$(verdict_count "$c/out-c2.txt")" != 1 ]; then
    bad "$name" "expected one verdict line, got $(verdict_count "$c/out-c2.txt")"
  elif ! printf '%s\n' "$v" | grep -q 'timed out'; then
    bad "$name" "verdict does not say timed out: $v"
  elif [ -e "$c/cfg/agents/builder.md" ]; then
    bad "$name" "agents/builder.md landed from a run that was stopped"
  else
    ok "$name"
  fi
}

# ---- d: install.sh exits 1: exits 0, verdict names exit 1, the copy runs outside the checkout ---
caseD() {
  name="d: install.sh exits 1: exits 0, verdict names exit 1, install.sh runs from a temp copy"
  c=$(new_case caseD)
  add_checkout "$c"
  cat > "$c/roots/claude-settings/install.sh" <<EOF
#!/bin/sh
printf '%s\n' "\$0" > "$c/ran-path"
exit 1
EOF
  fake_curl "$c" fail
  run_setup "$c" d
  v=$(verdict_text "$c/out-d.txt")
  if [ "$rc" -ne 0 ]; then
    bad "$name" "exit $rc: $(brief "$c/out-d.txt")"
  elif [ "$(verdict_count "$c/out-d.txt")" != 1 ]; then
    bad "$name" "expected one verdict line, got $(verdict_count "$c/out-d.txt")"
  elif [ -e "$c/cfg/agents/builder.md" ]; then
    bad "$name" "agents/builder.md landed from a failed install"
  elif ! printf '%s\n' "$v" | grep -Eq 'exit[^0-9]*1([^0-9]|$)'; then
    bad "$name" "verdict does not name exit 1: $v"
  elif [ ! -f "$c/ran-path" ]; then
    bad "$name" "install.sh never ran"
  else
    ran=$(cat "$c/ran-path")
    case "$ran" in
      "$c/roots/claude-settings"/*) bad "$name" "install.sh ran in place inside the checkout: $ran" ;;
      *) ok "$name" ;;
    esac
  fi
}

# ---- e: two runs on one checkout: both exit 0, one verdict line each, the same install ---------
caseE() {
  name="e: two runs on one checkout: both exit 0, one verdict line each, the same install"
  c=$(new_case caseE)
  add_checkout "$c"
  fake_curl "$c" fail
  run_setup "$c" e1
  rc1=$rc
  n1=$(verdict_count "$c/out-e1.txt")
  snap1=$(snapshot "$c")
  run_setup "$c" e2
  rc2=$rc
  n2=$(verdict_count "$c/out-e2.txt")
  snap2=$(snapshot "$c")
  if [ "$rc1" -ne 0 ] || [ "$rc2" -ne 0 ]; then
    bad "$name" "exit codes $rc1 and $rc2"
  elif [ "$n1" != 1 ] || [ "$n2" != 1 ]; then
    bad "$name" "verdict lines $n1 and $n2, want 1 each"
  elif [ -z "$snap1" ]; then
    bad "$name" "nothing installed by the first run"
  elif [ "$snap1" != "$snap2" ]; then
    bad "$name" "the install changed between runs"
  elif [ ! -f "$c/cfg/agents/builder.md" ]; then
    bad "$name" "agents/builder.md is gone after the second run"
  else
    ok "$name"
  fi
}

# ---- h: the raw install.sh is fetched first and runs; the checkout's copy is not used ----------
caseH() {
  name="h: the raw install.sh is fetched first and runs; the checkout's copy is not used"
  c=$(new_case caseH)
  add_checkout "$c"
  printf '#!/bin/sh\nexit 1\n' > "$c/roots/claude-settings/install.sh"
  cp "$REPO_ROOT/install.sh" "$c/served.sh"
  fake_curl "$c" serve "$c/served.sh"
  run_setup "$c" h
  v=$(verdict_text "$c/out-h.txt")
  if [ "$rc" -ne 0 ]; then
    bad "$name" "exit $rc: $(brief "$c/out-h.txt")"
  elif [ "$(verdict_count "$c/out-h.txt")" != 1 ]; then
    bad "$name" "expected one verdict line, got $(verdict_count "$c/out-h.txt")"
  elif [ ! -f "$c/cfg/agents/builder.md" ]; then
    bad "$name" "agents/builder.md did not land: the checkout's copy ran instead? verdict: $v"
  elif ! says_installed "$v"; then
    bad "$name" "verdict does not say installed: $v"
  elif ! fetch_asked "$c"; then
    bad "$name" "raw install.sh was not fetched with --max-time 20: $(brief "$c/curl.log")"
  else
    ok "$name"
  fi
}

# ---- sweep: the first request of a run removes an old run folder and keeps a new one -----------
# The probe runs in its own process, as a first request does, on a root under this run's folder.
cat > "$RUN/sweep_probe.py" <<'PY'
import os, sys, time, uuid
sys.path.insert(0, sys.argv[1])
import _test_temp
root = sys.argv[2]
os.makedirs(root)
old = os.path.join(root, "1-" + uuid.uuid4().hex)
new = os.path.join(root, "2-" + uuid.uuid4().hex)
keep = os.path.join(root, "not-a-run")
for path in (old, new, keep):
    os.makedirs(path)
two_days_ago = time.time() - 2 * 24 * 60 * 60
for path in (old, keep):
    os.utime(path, (two_days_ago, two_days_ago))
print("OLD " + old)
print("NEW " + new)
print("KEEP " + keep)
print("OWN " + _test_temp.run_folder(root))
PY

caseSweep() {
  name="sweep: the first request of a run removes an old sibling run folder and keeps a new one"
  sroot="$RUN/sweep-root"
  out=$(python3 -I "$RUN/sweep_probe.py" "$REPO_ROOT/lint" "$sroot" 2>&1)
  prc=$?
  old=$(printf '%s\n' "$out" | sed -n 's/^OLD //p')
  new=$(printf '%s\n' "$out" | sed -n 's/^NEW //p')
  keep=$(printf '%s\n' "$out" | sed -n 's/^KEEP //p')
  own=$(printf '%s\n' "$out" | sed -n 's/^OWN //p')
  if [ "$prc" -ne 0 ]; then
    bad "$name" "probe exited $prc: $(printf '%s' "$out" | tr '\n' ' ' | cut -c1-200)"
  elif [ -z "$old" ] || [ -z "$new" ] || [ -z "$keep" ] || [ -z "$own" ]; then
    bad "$name" "probe printed no folder paths: $(printf '%s' "$out" | tr '\n' ' ' | cut -c1-200)"
  elif [ -e "$old" ]; then
    bad "$name" "old sibling run folder was kept"
  elif [ ! -d "$new" ]; then
    bad "$name" "new sibling run folder was removed"
  elif [ ! -d "$keep" ]; then
    bad "$name" "a folder that is not a run folder was removed"
  elif [ ! -d "$own" ]; then
    bad "$name" "the probe's own run folder is missing"
  else
    ok "$name"
  fi
}

run() {
  if [ -n "$ONLY" ]; then
    case " $ONLY " in *" $1 "*) ;; *) return 0 ;; esac
  fi
  "$1"
}

run caseA
run caseB
run caseC
run caseC2
run caseD
run caseE
run caseH
run caseSweep

printf '%s passed, %s failed\n' "$PASS" "$FAIL"
[ "$FAIL" -eq 0 ]

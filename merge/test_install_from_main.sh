#!/bin/sh
# Cases for merge/install_from_main.sh, the afterMerge helper. Owner ruling 2026-10-15 (record
# merge-reinstalls-from-main, "The ruling"): the links in ~/.claude point at one pinned checkout,
# a worktree of the clone on a detached HEAD at main's commit, at the sibling path <clone>-live.
# The helper moves that checkout to main, then runs its install from there (Windows: install.ps1).
# Shell script, following the layout of hooks/test_install_src.sh: named cases, each isolated, a
# pass/fail line per case, a SKIP line for a case this host cannot run, and a summary exit code.
#
# Run it from the repository root:
#
#   sh merge/test_install_from_main.sh [case ...]   # names given: run only those cases
#
# Every case builds its own temp git repos. The clone is $d/clone on branch main, the caller is a
# linked worktree at $d/linked, and the pinned checkout is $d/clone-live. The installers are marker
# stubs, except cases 8 and 9, which run the real install.sh. Each stub writes a marker file into
# its own folder, so a case can see which tree ran it. HOME and CLAUDE_CONFIG_DIR point into the
# temp dir, so the real ~/.claude is never touched. INSTALL_FROM_MAIN_UNDER_TEST lets a case point
# at another copy of the script.

set -u

# A git hook may export these. The fixtures must not inherit them.
unset GIT_DIR GIT_WORK_TREE GIT_INDEX_FILE

HERE="$(cd "$(dirname "$0")" && pwd)"
REPO_ROOT="$(cd "$HERE/.." && pwd)"
SCRIPT="${INSTALL_FROM_MAIN_UNDER_TEST:-$REPO_ROOT/merge/install_from_main.sh}"
case "$SCRIPT" in /*) ;; *) SCRIPT="$PWD/$SCRIPT" ;; esac

PASS=0
FAIL=0
SKIP=0

ok() { PASS=$((PASS + 1)); printf 'ok   - %s\n' "$1"; }
bad() { FAIL=$((FAIL + 1)); printf 'FAIL - %s: %s\n' "$1" "$2"; }
skip() { SKIP=$((SKIP + 1)); printf 'SKIP - %s: %s\n' "$1" "$2"; }

# Canonicalize: on macOS, mktemp -d returns /var/folders/..., where /var is a symlink to
# /private/var. git reports worktree paths in resolved form, so every path built here goes
# through pwd -P before a comparison.
realpwd() { ( cd "$1" 2>/dev/null && pwd -P ); }

work=$(mktemp -d); work=$(realpwd "$work")
cleanup() { rm -rf "$work"; }
trap cleanup EXIT

# Marker installers for a clone at $1. install.sh writes ran-sh.txt into its own folder, then
# exits with $STUB_EXIT (default 0). install.ps1 writes ran-ps1.txt into its own folder.
stub_installers() {
  cat > "$1/install.sh" <<'EOF'
#!/bin/sh
printf ran > "$(dirname "$0")/ran-sh.txt"
exit "${STUB_EXIT:-0}"
EOF
  cat > "$1/install.ps1" <<'EOF'
Set-Content -Path (Join-Path $PSScriptRoot 'ran-ps1.txt') -Value 'ran'
EOF
}

# The real install.sh with its landed-dirs.txt, plus a small CLAUDE.md and settings.json. The
# landed directories are created empty, as hooks/test_install_src.sh does: a full copy makes
# the install slow here, because each landed file gets its own link.
payload_files() {
  git -c core.autocrlf=false -C "$REPO_ROOT" archive HEAD install.sh landed-dirs.txt | tar -x -C "$1"
  printf '# fixture CLAUDE.md\n' > "$1/CLAUDE.md"
  printf '{}\n' > "$1/settings.json"
  while IFS= read -r sub || [ -n "$sub" ]; do
    sub=$(printf '%s' "$sub" | tr -d '\r' | sed 's/#.*//; s/^[[:space:]]*//; s/[[:space:]]*$//')
    if [ -n "$sub" ]; then mkdir -p "$1/$sub"; fi
  done < "$1/landed-dirs.txt"
}

# Fake clone at $1 on branch main, with one commit. $2 is stub (marker installers) or payload
# (the real install.sh and its manifest). autocrlf is off: this host sets it on, and that
# would turn the scripts into CRLF.
live_clone() {
  mkdir -p "$1"
  git -C "$1" init -q -b main
  git -C "$1" config core.autocrlf false
  git -C "$1" config user.email t@example.com
  git -C "$1" config user.name t
  if [ "$2" = payload ]; then
    payload_files "$1"
    git -C "$1" remote add origin https://github.com/shivinate7/claude-settings.git
  else
    stub_installers "$1"
  fi
  git -C "$1" add -A
  git -C "$1" commit -q -m init
}

# pin_at_main CLONE: a pinned checkout at CLONE-live, detached at main's commit.
pin_at_main() {
  git -C "$1" worktree add -q --detach "$1-live" "$(git -C "$1" rev-parse main)"
}

# A uname that reports Linux, in dir $1. The helper takes its POSIX path only on Linux.
make_shim() {
  mkdir -p "$1"
  printf '#!/bin/sh\necho Linux\n' > "$1/uname"
  chmod +x "$1/uname"
}

# Run the helper with cwd $1 and HOME $h. Sets rc, outs (stdout), errs (stderr), out (both).
# SHIM, when set, goes first on PATH. MSYS makes install.sh's ln create real links here.
run_live() {
  ( cd "$1" && env HOME="$h" CLAUDE_CONFIG_DIR="$h/.claude-cfg" MSYS=winsymlinks:nativestrict \
      PATH="${SHIM:+$SHIM:}$PATH" bash "$SCRIPT" ) > "$work/run.out" 2> "$work/run.err"
  rc=$?
  outs=$(cat "$work/run.out")
  errs=$(cat "$work/run.err")
  out=$(cat "$work/run.out" "$work/run.err")
}

# Probe for real symlinks once. install.sh links into CLAUDE_CONFIG_DIR, so case 8 needs them.
printf x > "$work/probe-src"
LINKS_OK=no
if MSYS=winsymlinks:nativestrict ln -s "$work/probe-src" "$work/probe-link" 2>/dev/null \
   && [ -L "$work/probe-link" ]; then LINKS_OK=yes; fi

# ---- Case 1: run from a linked worktree -> the pinned checkout's install runs ---------------
case1() {
  name="case1: run from a linked worktree runs the install from the pinned checkout, not the clone or the caller"
  d="$work/case1"; h="$d/home"; mkdir -p "$h"; SHIM="$d/shim"; make_shim "$SHIM"
  live_clone "$d/clone" stub
  pin_at_main "$d/clone"
  git -C "$d/clone" worktree add -q -b caller "$d/linked"
  run_live "$d/linked"

  if [ "$rc" -ne 0 ]; then
    bad "$name" "script exited $rc: $out"
  elif [ ! -f "$d/clone-live/ran-sh.txt" ]; then
    bad "$name" "install did not run from the pinned checkout: $out"
  elif [ -e "$d/clone/ran-sh.txt" ] || [ -e "$d/linked/ran-sh.txt" ]; then
    bad "$name" "install ran from the clone or from the calling worktree"
  else
    ok "$name"
  fi
}

# ---- Case 2: run from the clone itself -> the pinned checkout's install runs, not the clone's --
case2() {
  name="case2: run from the clone runs the install from the pinned checkout, not the clone itself"
  d="$work/case2"; h="$d/home"; mkdir -p "$h"; SHIM="$d/shim"; make_shim "$SHIM"
  live_clone "$d/clone" stub
  pin_at_main "$d/clone"
  run_live "$d/clone"

  if [ "$rc" -ne 0 ]; then
    bad "$name" "script exited $rc: $out"
  elif [ ! -f "$d/clone-live/ran-sh.txt" ]; then
    bad "$name" "install did not run from the pinned checkout: $out"
  elif [ -e "$d/clone/ran-sh.txt" ]; then
    bad "$name" "install ran from the clone"
  else
    ok "$name"
  fi
}

# ---- Case 3: no worktree holds main, but the branch exists -> pinned moves, install runs --
# The helper reads main's commit from the branch, so it does not need a worktree on main. The
# pinned checkout moves to the new main, and the install runs from it.
case3() {
  name="case3: no worktree holds main, the pinned checkout still moves to main's commit and the install runs"
  d="$work/case3"; h="$d/home"; mkdir -p "$h"; SHIM="$d/shim"; make_shim "$SHIM"
  live_clone "$d/clone" stub
  pin_at_main "$d/clone"
  git -C "$d/clone" worktree add -q -b feature "$d/linked"
  printf 'feature\n' > "$d/linked/feature.txt"
  git -C "$d/linked" add feature.txt
  git -C "$d/linked" commit -q -m feature
  c1=$(git -C "$d/linked" rev-parse HEAD)
  git -C "$d/clone" switch -q -c trunk
  git -C "$d/clone" branch -q -f main "$c1"
  run_live "$d/linked"

  if [ "$rc" -ne 0 ]; then
    bad "$name" "script exited $rc: $out"
  elif [ "$(git -C "$d/clone-live" rev-parse HEAD 2>/dev/null)" != "$c1" ]; then
    bad "$name" "pinned checkout is not at main's commit $c1: $out"
  elif [ ! -f "$d/clone-live/ran-sh.txt" ]; then
    bad "$name" "install did not run from the pinned checkout: $out"
  else
    ok "$name"
  fi
}

# ---- Case 4: no branch named main -> one stderr line naming the pinned path, exit non-zero ---
# The pinned checkout cannot move, so the helper fails loudly. The line must say the install did
# not run and name the pinned path. It must not name `git switch main`: that remedy is retired.
case4() {
  name="case4: no branch named main prints one stderr line naming the pinned path, exits non-zero, runs no install"
  d="$work/case4"; h="$d/home"; mkdir -p "$h"; SHIM="$d/shim"; make_shim "$SHIM"
  live_clone "$d/clone" stub
  git -C "$d/clone" switch -q -c trunk
  git -C "$d/clone" branch -q -D main
  git -C "$d/clone" worktree add -q -b caller "$d/linked"
  run_live "$d/linked"
  lines=$(printf '%s\n' "$errs" | grep -c .)

  if [ "$rc" -eq 0 ]; then
    bad "$name" "script exited 0, expected non-zero so the merge tool reports FAILED: $out"
  elif [ -n "$outs" ]; then
    bad "$name" "text went to stdout, expected stderr only: $outs"
  elif [ "$lines" -ne 1 ]; then
    bad "$name" "expected one stderr line, got $lines: $errs"
  else
    case "$errs" in
      *"git switch main"*) bad "$name" "stderr still names the retired remedy git switch main: $errs"; return ;;
      *"not run"*"clone-live"*) ;;
      *) bad "$name" "stderr line does not say the install did not run and name the pinned path: $errs"; return ;;
    esac
    if [ -e "$d/clone/ran-sh.txt" ] || [ -e "$d/linked/ran-sh.txt" ]; then
      bad "$name" "an install ran although no branch named main exists"
    else
      ok "$name"
    fi
  fi
}

# ---- Case 5: the pinned checkout's install exits non-zero -> script exits with that code ----
case5() {
  name="case5: a failing install from the pinned checkout makes the script exit with the same code"
  d="$work/case5"; h="$d/home"; mkdir -p "$h"; SHIM="$d/shim"; make_shim "$SHIM"
  live_clone "$d/clone" stub
  pin_at_main "$d/clone"
  git -C "$d/clone" worktree add -q -b caller "$d/linked"
  STUB_EXIT=7
  export STUB_EXIT
  run_live "$d/linked"
  unset STUB_EXIT

  if [ "$rc" -ne 7 ]; then
    bad "$name" "expected exit 7, got $rc: $out"
  elif [ ! -f "$d/clone-live/ran-sh.txt" ]; then
    bad "$name" "install did not run from the pinned checkout, so the code proves nothing: $out"
  elif [ -e "$d/clone/ran-sh.txt" ] || [ -e "$d/linked/ran-sh.txt" ]; then
    bad "$name" "install ran from the clone or from the calling worktree"
  else
    ok "$name"
  fi
}

# ---- Case 6: a clone path with a space -> the pinned checkout is found and its install runs --
case6() {
  name="case6: a clone path with a space: the pinned checkout is found and its install runs"
  d="$work/case6"; h="$d/home"; mkdir -p "$h"; SHIM="$d/shim"; make_shim "$SHIM"
  live_clone "$d/main tree" stub
  pin_at_main "$d/main tree"
  git -C "$d/main tree" worktree add -q -b caller "$d/linked"
  run_live "$d/linked"

  if [ "$rc" -ne 0 ]; then
    bad "$name" "script exited $rc: $out"
  elif [ ! -f "$d/main tree-live/ran-sh.txt" ]; then
    bad "$name" "install did not run from the pinned checkout: $out"
  elif [ -e "$d/main tree/ran-sh.txt" ] || [ -e "$d/linked/ran-sh.txt" ]; then
    bad "$name" "install ran from the clone or from the calling worktree"
  else
    ok "$name"
  fi
}

# ---- Case 7: a merge moves main -> the pinned checkout moves to main's commit, detached ----
case7() {
  name="case7: after a merge moves main, the pinned checkout moves to main's commit, detached"
  d="$work/case7"; h="$d/home"; mkdir -p "$h"; SHIM="$d/shim"; make_shim "$SHIM"
  live_clone "$d/clone" stub
  c0=$(git -C "$d/clone" rev-parse main)
  git -C "$d/clone" worktree add -q --detach "$d/clone-live" "$c0"
  git -C "$d/clone" switch -q -c lane
  printf 'lane\n' > "$d/clone/lane.txt"
  git -C "$d/clone" add lane.txt
  git -C "$d/clone" commit -q -m lane
  git -C "$d/clone" switch -q main
  git -C "$d/clone" merge -q --no-ff -m merge lane
  c1=$(git -C "$d/clone" rev-parse main)
  git -C "$d/clone" worktree add -q -b caller "$d/linked"
  run_live "$d/linked"

  if [ "$rc" -ne 0 ]; then
    bad "$name" "script exited $rc: $out"
  elif [ "$(git -C "$d/clone-live" rev-parse HEAD 2>/dev/null)" != "$c1" ]; then
    bad "$name" "pinned checkout is not at main's commit $c1: $out"
  elif git -C "$d/clone-live" symbolic-ref -q HEAD >/dev/null 2>&1; then
    bad "$name" "pinned checkout is on a branch, expected a detached HEAD"
  elif [ ! -f "$d/clone-live/ran-sh.txt" ]; then
    bad "$name" "install did not run from the pinned checkout: $out"
  elif [ -e "$d/clone/ran-sh.txt" ] || [ -e "$d/linked/ran-sh.txt" ]; then
    bad "$name" "install ran from the clone or from the calling worktree"
  else
    ok "$name"
  fi
}

# ---- Case 8: a branch switch in the clone does not change what the links point at ---------
case8() {
  name="case8: a branch switch in the clone does not change what the links point at"
  if [ "$LINKS_OK" != yes ]; then skip "$name" "no symlink rights here, so the link check cannot run"; return; fi
  d="$work/case8"; h="$d/home"; mkdir -p "$h"; SHIM="$d/shim"; make_shim "$SHIM"
  live_clone "$d/clone" payload
  c0=$(git -C "$d/clone" rev-parse main)
  git -C "$d/clone" worktree add -q --detach "$d/clone-live" "$c0"
  git -C "$d/clone" worktree add -q -b feature "$d/linked"
  git -C "$d/clone" switch -q -c lane
  printf 'lane\n' > "$d/clone/settings.json"
  git -C "$d/clone" commit -q -am lane
  printf 'main\n' > "$d/linked/settings.json"
  git -C "$d/linked" commit -q -am main
  c1=$(git -C "$d/linked" rev-parse HEAD)
  git -C "$d/clone" branch -f main "$c1"
  git -C "$d/clone" show "$c1:settings.json" > "$work/case8.want"
  run_live "$d/linked"
  cfg="$h/.claude-cfg"

  if [ "$rc" -ne 0 ]; then
    bad "$name" "script exited $rc: $out"
  elif [ "$(git -C "$d/clone-live" rev-parse HEAD 2>/dev/null)" != "$c1" ]; then
    bad "$name" "pinned checkout is not at main's commit $c1: $out"
  elif git -C "$d/clone-live" symbolic-ref -q HEAD >/dev/null 2>&1; then
    bad "$name" "pinned checkout is on a branch, expected a detached HEAD"
  elif [ "$(git -C "$d/clone" symbolic-ref -q HEAD)" != refs/heads/lane ]; then
    bad "$name" "the helper changed the clone's branch"
  elif [ ! -L "$cfg/settings.json" ]; then
    bad "$name" "settings.json in CLAUDE_CONFIG_DIR is not a link: $out"
  elif ! cmp -s "$cfg/settings.json" "$work/case8.want"; then
    bad "$name" "the link does not read main's settings.json, so it follows the clone's branch"
  else
    ok "$name"
  fi
}

# ---- Case 9: no pinned checkout -> the real install makes one at main's commit ------------
case9() {
  name="case9: with no pinned checkout, the install makes one at main's commit"
  d="$work/case9"; h="$d/home"; cfg="$h/.claude-cfg"; mkdir -p "$h"
  live_clone "$d/clone" payload
  c0=$(git -C "$d/clone" rev-parse main)
  out=$(cd "$d/clone" && env -i PATH="$PATH" HOME="$h" CLAUDE_CONFIG_DIR="$cfg" MSYS=winsymlinks:nativestrict bash ./install.sh 2>&1)
  rc=$?
  pointer=$(sed -n 's|^@\(.*\)/CLAUDE\.md$|\1|p' "$cfg/CLAUDE.md" 2>/dev/null | head -n 1)
  case "$pointer" in "~"/*) pointer="$h${pointer#\~}" ;; esac

  if [ "$rc" -ne 0 ]; then
    bad "$name" "install.sh exited $rc: $out"
  elif [ "$(git -C "$d/clone-live" rev-parse HEAD 2>/dev/null)" != "$c0" ]; then
    bad "$name" "no pinned checkout at main's commit $c0 after the install"
  elif git -C "$d/clone-live" symbolic-ref -q HEAD >/dev/null 2>&1; then
    bad "$name" "pinned checkout is on a branch, expected a detached HEAD"
  elif [ "$(realpwd "$pointer")" != "$(realpwd "$d/clone-live")" ]; then
    bad "$name" "CLAUDE.md pointer [$pointer] does not name the pinned checkout"
  else
    ok "$name"
  fi
}

# ---- Case 10: the pinned path cannot be moved -> one stderr line, non-zero, no install -----
# A plain directory sits at the pinned path, so no move can make it a worktree at main. The
# helper must not delete it. The line must say the install did not run and name the pinned path.
case10() {
  name="case10: a pinned path that cannot be moved prints one stderr line, exits non-zero, runs no install"
  d="$work/case10"; h="$d/home"; mkdir -p "$h"; SHIM="$d/shim"; make_shim "$SHIM"
  live_clone "$d/clone" stub
  mkdir -p "$d/clone-live"
  printf 'keep\n' > "$d/clone-live/keep.txt"
  git -C "$d/clone" worktree add -q -b caller "$d/linked"
  run_live "$d/linked"
  lines=$(printf '%s\n' "$errs" | grep -c .)

  if [ "$rc" -eq 0 ]; then
    bad "$name" "script exited 0, expected non-zero so the merge tool reports FAILED: $out"
  elif [ "$lines" -ne 1 ]; then
    bad "$name" "expected one stderr line, got $lines: $errs"
  else
    case "$errs" in
      *"not run"*"clone-live"*) ;;
      *) bad "$name" "stderr line does not say the install did not run and name the pinned path: $errs"; return ;;
    esac
    if [ -e "$d/clone/ran-sh.txt" ] || [ -e "$d/linked/ran-sh.txt" ] || [ -e "$d/clone-live/ran-sh.txt" ]; then
      bad "$name" "an install ran anyway"
    elif [ ! -f "$d/clone-live/keep.txt" ]; then
      bad "$name" "the file in the blocking directory was removed"
    else
      ok "$name"
    fi
  fi
}

# ---- Case 11: Windows -> the after-merge step runs install.ps1, not the pointer ----------
# No pinned checkout exists. The helper runs install.ps1, which makes the pinned checkout. A stub
# cannot make it, so this case checks only that install.ps1 ran, from the clone or the pinned
# checkout. install.test.ps1 (pinnedps1) checks that the real install.ps1 makes it.
case11() {
  name="case11: on Windows the after-merge step runs install.ps1, not the pointer"
  case "$(uname)" in
    MINGW*|MSYS*|CYGWIN*) ;;
    *) skip "$name" "not Windows"; return ;;
  esac
  d="$work/case11"; h="$d/home"; mkdir -p "$h"; SHIM=""
  live_clone "$d/clone" stub
  git -C "$d/clone" worktree add -q -b caller "$d/linked"
  run_live "$d/linked"

  if [ "$rc" -ne 0 ]; then
    bad "$name" "script exited $rc: $out"
  elif printf '%s\n' "$out" | grep -q 'by hand'; then
    bad "$name" "printed the pointer instead of running install.ps1: $out"
  elif [ ! -f "$d/clone-live/ran-ps1.txt" ] && [ ! -f "$d/clone/ran-ps1.txt" ]; then
    bad "$name" "install.ps1 did not run: $out"
  else
    ok "$name"
  fi
}

# ---- Case 12: link mode, the pinned checkout moves from A to B while the links are loaded -----
# Owner ruling 2026-10-15 (install-set). A link in ~/.claude points into <clone>-live, and the move
# is the git switch in this helper, which writes the files one at a time. Link mode carries the
# placeholder in every guard file, so guard.py's INSTALL_ID check cannot see a mix here: the case
# samples the loads itself. The fixture's guard_core.py and guard_sib.py carry a marker that differs
# between A and B. A smudge filter holds the switch on hooks/guard_pause.txt, which sorts between
# them. While it holds, guard_core.py is B and guard_sib.py is still A. Each load must read all-A or
# all-B. The stub guard retries a failed load for a few seconds, as guard.py does, so a load that
# falls between git's unlink and write of a file is not a crash.
guard_fixture() {  # $1 clone, $2 marker: the stub guard and its two modules at one commit
  mkdir -p "$1/hooks"
  printf '%s\n' 'import guard_core' 'import guard_sib' 'print(guard_core.MARK, guard_sib.MARK)' > "$1/hooks/guard.py"
  printf 'MARK = "%s"\n' "$2" > "$1/hooks/guard_core.py"
  printf 'MARK = "%s"\n' "$2" > "$1/hooks/guard_sib.py"
  printf 'marker %s\n' "$2" > "$1/hooks/guard_pause.txt"
  printf 'hooks/guard_pause.txt filter=pause\n' > "$1/.gitattributes"
}

# One guard load through the links, retried up to 3 s as guard.py retries a failed load. Prints the
# pair the stub prints, or nothing when no attempt loaded. $1 is the config dir; $h is the home.
link_probe() {
  i=0; got=""
  while [ "$i" -lt 15 ]; do
    got=$(env CLAUDE_CONFIG_DIR="$1" HOME="$h" PYTHONPATH= python3 -B "$1/hooks/guard.py" 2>/dev/null) \
      && [ -n "$got" ] && break
    got=""; i=$((i + 1)); sleep 0.2
  done
  printf '%s' "$got"
}

case12() {
  name="case12: a pinned-checkout move from A to B, sampled through the links, never loads a mix or a crash"
  if [ "$LINKS_OK" != yes ]; then skip "$name" "no symlink rights here, so the link check cannot run"; return; fi
  d="$work/case12"; h="$d/home"; mkdir -p "$h"; SHIM="$d/shim"; make_shim "$SHIM"
  live_clone "$d/clone" stub
  guard_fixture "$d/clone" A
  git -C "$d/clone" add -A
  git -C "$d/clone" commit -q -m A
  pin_at_main "$d/clone"
  git -C "$d/clone" switch -q -c trunk
  guard_fixture "$d/clone" B
  git -C "$d/clone" add -A
  git -C "$d/clone" commit -q -m B
  git -C "$d/clone" branch -q -f main trunk
  pause="$d/pause-smudge.sh"
  cat > "$pause" <<'EOF'
#!/bin/sh
# Smudge filter for hooks/guard_pause.txt. While $PAUSE_FLAG exists, it logs the call and sleeps
# $PAUSE_SECS before git writes the file. Otherwise it passes the content through.
if [ -e "$PAUSE_FLAG" ]; then printf '%s\n' "$1" >> "$PAUSE_LOG"; sleep "$PAUSE_SECS"; fi
cat
EOF
  git -C "$d/clone" config filter.pause.smudge "sh \"$pause\" %f"
  git -C "$d/clone" config checkout.workers 1
  cfg="$h/.claude-cfg"; mkdir -p "$cfg/hooks"
  for f in guard.py guard_core.py guard_sib.py; do
    MSYS=winsymlinks:nativestrict ln -s "$d/clone-live/hooks/$f" "$cfg/hooks/$f" \
      || { bad "$name" "could not link $f into $cfg/hooks"; return; }
  done

  PAUSE_FLAG="$d/pause.flag"; PAUSE_LOG="$d/pause.log"; : > "$PAUSE_FLAG"; : > "$PAUSE_LOG"
  ( cd "$d/clone" && env HOME="$h" CLAUDE_CONFIG_DIR="$cfg" PATH="$SHIM:$PATH" \
      PAUSE_FLAG="$PAUSE_FLAG" PAUSE_LOG="$PAUSE_LOG" PAUSE_SECS=2 bash "$SCRIPT" ) > "$d/helper.out" 2>&1 &
  hp=$!
  # Bounded sampler: it reads local files through the links while the move runs, and stops when the
  # move exits or after 400 loads.
  loads=0; mixed=0; crashes=0; seen=""; n=0
  while kill -0 "$hp" 2>/dev/null && [ "$n" -lt 400 ]; do
    n=$((n + 1))
    got=$(link_probe "$cfg")
    loads=$((loads + 1))
    case "$got" in
      "A A"|"B B") ;;
      "A B"|"B A") mixed=$((mixed + 1)); seen="$got" ;;
      *) crashes=$((crashes + 1)) ;;
    esac
  done
  wait "$hp"; hrc=$?
  paused=$(grep -c . "$PAUSE_LOG")
  final=$(link_probe "$cfg")
  pin_head=$(git -C "$d/clone-live" rev-parse HEAD 2>/dev/null)
  want_head=$(git -C "$d/clone" rev-parse main 2>/dev/null)

  if [ "$hrc" -ne 0 ]; then bad "$name" "the helper exited $hrc: $(cat "$d/helper.out")"
  elif [ "$pin_head" != "$want_head" ]; then bad "$name" "the pinned checkout is at [$pin_head], want main at [$want_head]"
  elif [ "$mixed" -gt 0 ]; then bad "$name" "$mixed of $loads loads read a mix ($seen) while the pinned checkout moved from A to B"
  elif [ "$crashes" -gt 0 ]; then bad "$name" "$crashes of $loads loads crashed, with no marker pair after retries"
  elif [ "$paused" -lt 1 ]; then bad "$name" "precondition: the switch never held, so no load was sampled inside it"
  elif [ "$loads" -lt 3 ]; then bad "$name" "precondition: only $loads loads ran during the switch"
  elif [ "$final" != "B B" ]; then bad "$name" "after the move a load read [$final], want [B B]"
  else ok "$name"
  fi
}

# ---- Case 13: <clone>-live deleted but still registered -> the line carries git's message --
# The folder is gone, but git still lists the worktree, so `worktree add` refuses the path. Freeing
# the path is the wrong remedy: the stale registration must be pruned. The helper must not discard
# git's stderr, so the line carries git's own message or names the stale registration. The line may
# be more than one stderr line, because git's message comes first.
case13() {
  name="case13: <clone>-live deleted but still registered: the stderr line carries git's message or names the stale registration"
  d="$work/case13"; h="$d/home"; mkdir -p "$h"; SHIM="$d/shim"; make_shim "$SHIM"
  live_clone "$d/clone" stub
  pin_at_main "$d/clone"
  git -C "$d/clone" worktree add -q -b caller "$d/linked"
  rm -rf "$d/clone-live"
  if ! git -C "$d/clone" worktree list --porcelain | grep -q 'clone-live$'; then
    bad "$name" "fixture: git no longer lists the stale pinned checkout"; return
  fi
  run_live "$d/linked"

  if [ "$rc" -eq 0 ]; then
    bad "$name" "script exited 0, expected non-zero so the merge tool reports FAILED: $out"
  elif [ -n "$outs" ]; then
    bad "$name" "text went to stdout, expected stderr only: $outs"
  else
    case "$errs" in
      *"not run"*"clone-live"*) ;;
      *) bad "$name" "stderr line does not say the install did not run and name the pinned path: $errs"; return ;;
    esac
    case "$errs" in
      *registered*|*prune*) ;;
      *) bad "$name" "stderr carries neither git's message nor the stale registration: $errs"; return ;;
    esac
    if [ -e "$d/clone/ran-sh.txt" ] || [ -e "$d/linked/ran-sh.txt" ]; then
      bad "$name" "an install ran although the pinned checkout could not be made"
    else
      ok "$name"
    fi
  fi
}

ALL="case1 case2 case3 case4 case5 case6 case7 case8 case9 case10 case11 case12 case13"
if [ $# -gt 0 ]; then WANT="$*"; else WANT="$ALL"; fi
for c in $WANT; do "$c"; done

printf '%s passed, %s failed, %s skipped\n' "$PASS" "$FAIL" "$SKIP"
[ "$FAIL" -eq 0 ]

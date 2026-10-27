#!/bin/sh
# Cases for merge/install_from_main.sh, the afterMerge helper (record
# merge-reinstalls-from-main): the links in ~/.claude point at one pinned checkout,
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
# at another copy of the script. Cases 22 to 31 run the SessionStart hook command that settings.json
# carries; HOOK_SETTINGS_UNDER_TEST lets a case point at another settings file.

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

# pin_behind_main CLONE: a locked pinned checkout at CLONE-live, as install.sh makes it, at main's
# commit c0; then main moves one commit on, so the pin is behind main. Sets c0.
pin_behind_main() {
  c0=$(git -C "$1" rev-parse main)
  git -C "$1" worktree add -q --detach --lock --reason "claude-settings live pin" "$1-live" "$c0"
  git -C "$1" commit -q --allow-empty -m next
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
  # The real install.sh takes the install lock too. A helper that holds the lock while it runs
  # install.sh makes install.sh wait on it and fail, so the short wait turns that into a visible red.
  export CLAUDE_SETTINGS_LOCK_WAIT=5
  run_live "$d/linked"
  unset CLAUDE_SETTINGS_LOCK_WAIT
  cfg="$h/.claude-cfg"

  if printf '%s' "$out" | grep -q 'holds the lock'; then
    bad "$name" "install.sh found the install lock held: the helper holds the lock across its install.sh call, so the install waits on itself: $out"
  elif grep -q 'exit=[1-9]' "$cfg/claude-settings-install.log" 2>/dev/null; then
    bad "$name" "an install log end line exited non-zero: $(cat "$cfg/claude-settings-install.log")"
  elif [ "$rc" -ne 0 ]; then
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
# A link in ~/.claude points into <clone>-live, and the move
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

# Prints the id of the first start line in the install log $1, or nothing. Each install-log line
# holds "id=<id> pid=<pid>", as install.sh writes them.
first_start_id() { grep -w start "$1" 2>/dev/null | sed -n 's/.* id=\([^ ]*\).*/\1/p' | head -n 1; }

# ---- Case 14: no symlink rights -> the pinned checkout stays usable; the run installs or refuses ----
# The pin is behind main. The first move renames the plain pin, then point_at needs a link. With no
# link rights the helper must not stop there: the pin path would be gone, no install would run, and the pointer
# in CLAUDE.md would dangle. Accepted: the pin moves in place and the install runs, or the run refuses
# before it moves anything. The shim ln fails on every call, so no real link is made.
case14() {
  name="case14: no symlink rights: the pinned checkout stays usable, and the run either installs or refuses before any move"
  d="$work/case14"; h="$d/home"; mkdir -p "$h"; SHIM="$d/shim"; make_shim "$SHIM"
  printf '#!/bin/sh\nexit 1\n' > "$SHIM/ln"; chmod +x "$SHIM/ln"
  live_clone "$d/clone" stub
  pin_behind_main "$d/clone"
  c1=$(git -C "$d/clone" rev-parse main)
  git -C "$d/clone" worktree add -q -b caller "$d/linked"
  short0=$(git -C "$d/clone" rev-parse --short=12 "$c0")
  if [ "$c0" = "$c1" ] || [ -L "$d/clone-live" ] || [ "$(git -C "$d/clone-live" rev-parse HEAD)" != "$c0" ]; then
    bad "$name" "precondition: clone-live is not a plain worktree at the old main"; return
  fi
  run_live "$d/linked"
  pin_head=$(git -C "$d/clone-live" rev-parse HEAD 2>/dev/null)

  if [ ! -e "$d/clone-live" ]; then
    bad "$name" "clone-live is gone after the run (rc $rc), so the links and the CLAUDE.md pointer dangle: $out"
  elif [ -e "$d/clone-live.tmp" ]; then
    bad "$name" "clone-live.tmp was left behind"
  elif [ "$rc" -eq 0 ]; then
    if [ "$pin_head" != "$c1" ]; then
      bad "$name" "exit 0, but clone-live is at [$pin_head], want main [$c1]"
    elif [ ! -f "$d/clone-live/ran-sh.txt" ]; then
      bad "$name" "exit 0, but the install did not run from clone-live: $out"
    elif [ "$(realpwd "$(git -C "$d/clone-live" rev-parse --path-format=absolute --git-common-dir)")" \
         != "$(realpwd "$(git -C "$d/clone" rev-parse --path-format=absolute --git-common-dir)")" ]; then
      bad "$name" "exit 0, but clone-live is not a worktree of the clone"
    else
      ok "$name"
    fi
  elif [ "$pin_head" != "$c0" ]; then
    bad "$name" "the run refused (rc $rc) but already moved clone-live to [$pin_head]; a refusal must move nothing"
  elif [ -e "$d/clone-live-$short0" ] || [ -e "$d/clone/ran-sh.txt" ] || [ -e "$d/clone-live/ran-sh.txt" ]; then
    bad "$name" "the run refused but moved the pin aside or ran an install"
  else
    ok "$name"
  fi
}

# ---- Case 15: another run holds the install lock -> the helper waits, refuses, moves nothing ----
# The pin move holds the lock the installers hold. A lock file
# with a fresh mtime is a live run's, so this run waits CLAUDE_SETTINGS_LOCK_WAIT seconds, then exits
# non-zero with nothing written. The lock is not this run's, so the run must leave it as it is.
case15() {
  name="case15: another run holds the install lock: the helper refuses after the wait, moves no pin, runs no install, keeps the lock"
  d="$work/case15"; h="$d/home"; mkdir -p "$h/.claude-cfg"; SHIM="$d/shim"; make_shim "$SHIM"
  live_clone "$d/clone" stub
  pin_behind_main "$d/clone"
  git -C "$d/clone" worktree add -q -b caller "$d/linked"
  lock="$h/.claude-cfg/.claude-settings-install.lock"
  printf '4242\n' > "$lock"
  export CLAUDE_SETTINGS_LOCK_WAIT=2
  run_live "$d/linked"
  unset CLAUDE_SETTINGS_LOCK_WAIT
  pin_head=$(git -C "$d/clone-live" rev-parse HEAD 2>/dev/null)

  if [ "$rc" -eq 0 ]; then
    bad "$name" "exit 0 while another run held the install lock: $out"
  elif [ "$pin_head" != "$c0" ]; then
    bad "$name" "the helper moved clone-live to [$pin_head] while another run held the lock; want [$c0]"
  elif [ -e "$d/clone/ran-sh.txt" ] || [ -e "$d/linked/ran-sh.txt" ] || [ -e "$d/clone-live/ran-sh.txt" ]; then
    bad "$name" "an install ran while another run held the lock"
  elif [ "$(cat "$lock" 2>/dev/null)" != 4242 ]; then
    bad "$name" "the helper removed or replaced a lock it did not take"
  else
    case "$errs" in
      *lock*) ok "$name" ;;
      *) bad "$name" "the refusal does not name the lock: $errs" ;;
    esac
  fi
}

# ---- Case 16: each helper run logs one start line and one end line, with its id and pid -------
# The install log is the one install.sh writes. A start line and an end line share an id= and a
# pid=, and a second run gets a new id. The wording around them is not pinned.
case16() {
  name="case16: each helper run writes one start and one end line, each with its id and pid; a second run gets a new id"
  d="$work/case16"; h="$d/home"; mkdir -p "$h"; SHIM="$d/shim"; make_shim "$SHIM"
  live_clone "$d/clone" stub
  pin_at_main "$d/clone"
  git -C "$d/clone" worktree add -q -b caller "$d/linked"
  log="$h/.claude-cfg/claude-settings-install.log"
  run_live "$d/linked"; rc1=$rc; out1=$out
  run_live "$d/linked"; rc2=$rc; out2=$out
  if [ "$rc1" -ne 0 ] || [ "$rc2" -ne 0 ]; then
    bad "$name" "a run exited non-zero ($rc1, $rc2): $out1 | $out2"; return
  fi
  starts=$(cat "$log" 2>/dev/null | grep -cw start)
  ends=$(cat "$log" 2>/dev/null | grep -cw end)
  if [ "$starts" -ne 2 ] || [ "$ends" -ne 2 ]; then
    bad "$name" "want one start and one end per run (2 each), got starts=$starts ends=$ends in the install log"; return
  fi
  ids=$(sed -n 's/.* id=\([^ ]*\).*/\1/p' "$log" | sort -u)
  if [ "$(printf '%s\n' "$ids" | grep -c .)" -ne 2 ]; then
    bad "$name" "two runs must log two different ids, got: [$ids]"; return
  fi
  for id in $ids; do
    sp=$(grep -w start "$log" | grep "id=$id " | sed -n 's/.* pid=\([^ ]*\).*/\1/p')
    ep=$(grep -w end "$log" | grep "id=$id " | sed -n 's/.* pid=\([^ ]*\).*/\1/p')
    case "$sp" in ''|*[!0-9]*) bad "$name" "start line for id=$id has no numeric pid: [$sp]"; return ;; esac
    if [ "$sp" != "$ep" ]; then bad "$name" "end line for id=$id has pid [$ep], start has [$sp]"; return; fi
  done
  ok "$name"
}

# ---- Case 17: a move that fails -> an end line, the folder in the way kept, no lock left behind ----
# The folder sits where the new pinned tree goes, so the move fails before it moves the pin. The
# run must still close its log pair and must not leave the install lock behind, or every later
# install waits out the 10-minute stale age.
case17() {
  name="case17: a move that fails ends with an end line, keeps the folder in the way, and leaves no lock behind"
  d="$work/case17"; h="$d/home"; mkdir -p "$h"; SHIM="$d/shim"; make_shim "$SHIM"
  live_clone "$d/clone" stub
  pin_behind_main "$d/clone"
  short1=$(git -C "$d/clone" rev-parse --short=12 main)
  mkdir -p "$d/clone-live-$short1"; printf 'keep\n' > "$d/clone-live-$short1/keep.txt"
  git -C "$d/clone" worktree add -q -b caller "$d/linked"
  run_live "$d/linked"
  log="$h/.claude-cfg/claude-settings-install.log"
  lock="$h/.claude-cfg/.claude-settings-install.lock"
  pin_head=$(git -C "$d/clone-live" rev-parse HEAD 2>/dev/null)
  sid=$(first_start_id "$log")

  if [ "$rc" -eq 0 ]; then
    bad "$name" "exit 0 with a folder in the way of the new pinned tree: $out"
  elif [ ! -f "$d/clone-live-$short1/keep.txt" ]; then
    bad "$name" "the folder in the way was removed"
  elif [ "$pin_head" != "$c0" ]; then
    bad "$name" "a failed move still moved clone-live to [$pin_head]; want [$c0]"
  elif [ -z "$sid" ]; then
    bad "$name" "no start line for the failed run: [$(cat "$log" 2>/dev/null)]"
  elif ! grep -w end "$log" 2>/dev/null | grep -q "id=$sid "; then
    bad "$name" "no end line for start id=$sid: the failed run left its log pair open"
  elif [ -e "$lock" ]; then
    bad "$name" "the failed run left the install lock behind; every later install waits out the 10-minute stale age"
  else
    ok "$name"
  fi
}

# ---- Case 18: two racing runs -> run B waits for run A's lock; the install log never interleaves ----
# Run A is held inside its move: the smudge filter pauses A's checkout of the new pinned tree for
# PAUSE_SECS. Run B starts during that pause. Under the install lock, B waits until A ends, so A ends
# first, and the install log reads start, end, start, end (as install.sh logs them, start after the
# lock is held). Without the lock, B moves the pin while A holds it. Waits are fixed sleeps, not a
# loop; a precondition fails the case when A has not reached its pause.
case18() {
  name="case18: two racing runs: run B waits for run A to end, the install-log pairs never interleave, the pin ends at main"
  if [ "$LINKS_OK" != yes ]; then skip "$name" "no symlink rights here; the race needs the links that the move makes"; return; fi
  d="$work/case18"; h="$d/home"; cfg="$h/.claude-cfg"; mkdir -p "$cfg"; SHIM="$d/shim"; make_shim "$SHIM"
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
  git -C "$d/clone" worktree add -q -b caller "$d/linked"
  PAUSE_FLAG="$d/pause.flag"; PAUSE_LOG="$d/pause.log"; ORDER="$d/order.txt"
  : > "$PAUSE_FLAG"; : > "$PAUSE_LOG"; : > "$ORDER"
  log="$cfg/claude-settings-install.log"

  # One helper run from the linked worktree. It appends "<letter> <exit code>" to ORDER when it ends.
  ( ( cd "$d/linked" && env HOME="$h" CLAUDE_CONFIG_DIR="$cfg" PATH="$SHIM:$PATH" \
        PAUSE_FLAG="$PAUSE_FLAG" PAUSE_LOG="$PAUSE_LOG" PAUSE_SECS=8 CLAUDE_SETTINGS_LOCK_WAIT=30 \
        bash "$SCRIPT" ) > "$d/A.out" 2>&1; printf 'A %s\n' "$?" >> "$ORDER" ) &
  ap=$!
  sleep 3
  pre=$(cat "$PAUSE_LOG" | grep -c .)
  if [ "$pre" -lt 1 ]; then
    rm -f "$PAUSE_FLAG"; wait "$ap"
    bad "$name" "precondition: run A had not reached its move within 3 s, so run B did not race it"; return
  fi
  ( ( cd "$d/linked" && env HOME="$h" CLAUDE_CONFIG_DIR="$cfg" PATH="$SHIM:$PATH" \
        PAUSE_FLAG="$PAUSE_FLAG" PAUSE_LOG="$PAUSE_LOG" PAUSE_SECS=8 CLAUDE_SETTINGS_LOCK_WAIT=30 \
        bash "$SCRIPT" ) > "$d/B.out" 2>&1; printf 'B %s\n' "$?" >> "$ORDER" ) &
  bp=$!
  rm -f "$PAUSE_FLAG"
  wait "$ap" "$bp"

  first=$(head -n 1 "$ORDER" | cut -c1)
  arc=$(grep '^A ' "$ORDER" | cut -d' ' -f2)
  brc=$(grep '^B ' "$ORDER" | cut -d' ' -f2)
  seq=$(grep -ow -e start -e end "$log" 2>/dev/null | paste -sd' ' -)
  ids_seq=$(sed -n 's/.* id=\([^ ]*\).*/\1/p' "$log" 2>/dev/null | paste -sd' ' -)
  pin_head=$(git -C "$d/clone-live" rev-parse HEAD 2>/dev/null)
  want=$(git -C "$d/clone" rev-parse main)

  if [ "$first" != A ]; then
    bad "$name" "B ended before A: the move takes no install lock, so run B moved the pinned checkout while run A held it (order: $(paste -sd' ' "$ORDER"))"
  elif [ "$arc" != 0 ] || [ "$brc" != 0 ]; then
    bad "$name" "a racing run exited non-zero (A=$arc, B=$brc): $(cat "$d/A.out") | $(cat "$d/B.out")"
  elif [ "$seq" != "start end start end" ]; then
    bad "$name" "install-log events interleave: [$seq]"
  else
    set -- $ids_seq
    if [ "$#" -ne 4 ] || [ "$1" != "$2" ] || [ "$3" != "$4" ] || [ "$1" = "$3" ]; then
      bad "$name" "install-log start and end lines do not pair by id: [$ids_seq]"
    elif [ "$pin_head" != "$want" ]; then
      bad "$name" "the pinned checkout is at [$pin_head] after the race, want main [$want]"
    elif [ -e "$d/clone-live.tmp" ]; then
      bad "$name" "clone-live.tmp was left behind by the race"
    else
      ok "$name"
    fi
  fi
}

# Prints the exit codes of the end lines for id $2 in install log $1, one per line, sorted and unique.
end_exits() { grep -w end "$1" 2>/dev/null | grep "id=$2 " | sed -n 's/.* exit=\([^ ]*\).*/\1/p' | sort -u; }

# ---- Case 19: run B waits on the lock, main moves X -> Y meanwhile; B must not move the pin back to X ----
# The helper reads main's commit before it takes the lock, so
# a run that waits on the lock can act on a commit that is no longer main when it gets the lock. The
# lock is a fake holder (case15's pattern), which keeps the race deterministic. The case plays run A's
# part: main moves to Y, the pin moves to Y, and the lock is let go. B is the real run, and it started
# when main was X. The pin must end at Y, never back at X.
case19() {
  name="case19: a run that waited on the lock works from main's commit after the wait, so it never moves the pin back to the older commit"
  d="$work/case19"; h="$d/home"; cfg="$h/.claude-cfg"; mkdir -p "$cfg"; SHIM="$d/shim"; make_shim "$SHIM"
  live_clone "$d/clone" stub
  pin_at_main "$d/clone"
  X=$(git -C "$d/clone" rev-parse main)
  git -C "$d/clone" worktree add -q -b caller "$d/linked"
  lock="$cfg/.claude-settings-install.lock"
  printf '4242\n' > "$lock"
  ( cd "$d/linked" && env HOME="$h" CLAUDE_CONFIG_DIR="$cfg" MSYS=winsymlinks:nativestrict \
      PATH="$SHIM:$PATH" CLAUDE_SETTINGS_LOCK_WAIT=30 bash "$SCRIPT" ) > "$d/B.out" 2>&1 &
  bp=$!
  sleep 3   # fixed wait: run B reads main (X) and then blocks on the fake lock
  if ! kill -0 "$bp" 2>/dev/null; then
    rm -f "$lock"; wait "$bp"
    bad "$name" "precondition: run B ended while the fake lock was held: $(cat "$d/B.out")"; return
  fi
  git -C "$d/clone" commit -q --allow-empty -m Y
  Y=$(git -C "$d/clone" rev-parse main)
  git -C "$d/clone-live" switch -q --detach "$Y"   # run A's move: the pin goes to Y
  pin_mid=$(git -C "$d/clone-live" rev-parse HEAD 2>/dev/null)
  rm -f "$lock"                                    # run A lets go; B takes the lock
  wait "$bp"; brc=$?
  pin_head=$(git -C "$d/clone-live" rev-parse HEAD 2>/dev/null)

  if [ "$X" = "$Y" ] || [ "$pin_mid" != "$Y" ]; then
    bad "$name" "precondition: the pin did not move to main's new commit [$Y] (pin at [$pin_mid])"
  elif [ "$pin_head" = "$X" ]; then
    bad "$name" "run B moved the pin back to the older commit [$X]; want main [$Y]. B read main before it waited on the lock: $(cat "$d/B.out")"
  elif [ "$pin_head" != "$Y" ]; then
    bad "$name" "the pin is at [$pin_head] after the lock wait, want main [$Y]: $(cat "$d/B.out")"
  elif [ "$brc" -ne 0 ]; then
    bad "$name" "run B exited $brc: $(cat "$d/B.out")"
  else
    ok "$name"
  fi
}

# ---- Case 20: the installer check fails (no install.sh) -> the end line carries the run's exit 1 ----
# release_lock logs the end line before the installer check, so a run that fails at that check logs
# exit=0 and then exits 1. The end line for the run's id must carry the real exit.
case20() {
  name="case20: a run that fails at the installer check logs an end line with its real non-zero exit"
  d="$work/case20"; h="$d/home"; mkdir -p "$h"; SHIM="$d/shim"; make_shim "$SHIM"
  live_clone "$d/clone" stub
  git -C "$d/clone" rm -q install.sh
  git -C "$d/clone" commit -q -m "no install.sh"
  pin_at_main "$d/clone"
  git -C "$d/clone" worktree add -q -b caller "$d/linked"
  run_live "$d/linked"
  log="$h/.claude-cfg/claude-settings-install.log"
  sid=$(first_start_id "$log")
  ends=$(end_exits "$log" "$sid")

  if [ "$rc" -eq 0 ]; then
    bad "$name" "exit 0 although the pinned checkout has no install.sh: $out"
  elif [ -z "$sid" ]; then
    bad "$name" "no start line for the run: [$(cat "$log" 2>/dev/null)]"
  elif [ "$ends" != "$rc" ]; then
    bad "$name" "the end line for id=$sid says exit=[$ends], the run exited $rc: $(cat "$log")"
  else
    ok "$name"
  fi
}

# ---- Case 21: the installer runs and exits 7 -> the end line carries exit=7, the run's real exit ----
case21() {
  name="case21: an installer that exits 7 leaves an end line with exit=7, the run's real exit"
  d="$work/case21"; h="$d/home"; mkdir -p "$h"; SHIM="$d/shim"; make_shim "$SHIM"
  live_clone "$d/clone" stub
  pin_at_main "$d/clone"
  git -C "$d/clone" worktree add -q -b caller "$d/linked"
  STUB_EXIT=7
  export STUB_EXIT
  run_live "$d/linked"
  unset STUB_EXIT
  log="$h/.claude-cfg/claude-settings-install.log"
  sid=$(first_start_id "$log")
  ends=$(end_exits "$log" "$sid")

  if [ "$rc" -ne 7 ]; then
    bad "$name" "expected exit 7, got $rc: $out"
  elif [ ! -f "$d/clone-live/ran-sh.txt" ]; then
    bad "$name" "install did not run from the pinned checkout, so the end line proves nothing: $out"
  elif [ -z "$sid" ]; then
    bad "$name" "no start line for the run: [$(cat "$log" 2>/dev/null)]"
  elif [ "$ends" != 7 ]; then
    bad "$name" "the end line for id=$sid says exit=[$ends], want exit=7: $(cat "$log")"
  else
    ok "$name"
  fi
}

# ---- SessionStart hook (settings.json): the pull that keeps the live pin at main ---------------
# The hook command as settings.json carries it: the one SessionStart command that reads CLAUDE.md.
# Printed with no trailing newline, so no carriage return rides along on Windows.
HOOK_SETTINGS="${HOOK_SETTINGS_UNDER_TEST:-$REPO_ROOT/settings.json}"
hook_command() {
  python3 -c '
import json, sys
hits = [h["command"] for e in json.load(sys.stdin)["hooks"]["SessionStart"]
        for h in e["hooks"] if "CLAUDE.md" in h.get("command", "")]
if len(hits) != 1:
    sys.exit("want one SessionStart command that reads CLAUDE.md, found %d" % len(hits))
sys.stdout.buffer.write(hits[0].encode("utf-8"))
' < "$HOOK_SETTINGS"
}

# A bare origin, and a clone holding one commit. The pinned checkout <clone>-live is detached and
# locked, as install.sh makes it, at c0. Then origin's main moves to c1, unless $3 is same (c1 is c0).
# $2 says where main is:
# trunk (the clone's checkout is on trunk, so main is free), main (the clone's own checkout is on
# main), or linked (a linked worktree <dir>/linked holds main). The clone holds the real merge/install_from_main.sh, a stub install.sh that appends the
# commit it ran from to $HOME/ran-install.txt, and a stub install.ps1. The config dir's CLAUDE.md
# points at the pin.
hook_fixture() {
  d="$1"
  make_shim "$d/shim"
  mkdir -p "$d/home/.claude-cfg"
  git init -q --bare -b main "$d/origin.git"
  git init -q -b main "$d/clone"
  git -C "$d/clone" config core.autocrlf false
  git -C "$d/clone" config user.email t@example.com
  git -C "$d/clone" config user.name t
  mkdir -p "$d/clone/merge"
  cp "$REPO_ROOT/merge/install_from_main.sh" "$d/clone/merge/install_from_main.sh"
  cat > "$d/clone/install.sh" <<'EOF'
#!/bin/sh
printf '%s\n' "$(git -C "$(dirname "$0")" rev-parse HEAD)" >> "$HOME/ran-install.txt"
EOF
  printf 'stub\n' > "$d/clone/install.ps1"
  printf 'notes\n' > "$d/clone/notes.txt"
  git -C "$d/clone" add -A
  git -C "$d/clone" commit -q -m init
  git -C "$d/clone" remote add origin "$d/origin.git"
  git -C "$d/clone" push -q origin main
  c0=$(git -C "$d/clone" rev-parse main)
  case "${2:-trunk}" in
    trunk) git -C "$d/clone" switch -q -c trunk ;;
    linked) git -C "$d/clone" switch -q -c trunk && git -C "$d/clone" worktree add -q "$d/linked" main ;;
  esac
  git -C "$d/clone" worktree add -q --detach --lock --reason "claude-settings live pin" "$d/clone-live" "$c0"
  printf '@%s/CLAUDE.md\n' "$d/clone-live" > "$d/home/.claude-cfg/CLAUDE.md"
  c1="$c0"
  if [ "${3:-ahead}" = ahead ]; then
    git clone -q "$d/origin.git" "$d/pusher"
    git -C "$d/pusher" config user.email t@example.com
    git -C "$d/pusher" config user.name t
    git -C "$d/pusher" commit -q --allow-empty -m next
    git -C "$d/pusher" push -q origin main
    c1=$(git -C "$d/pusher" rev-parse HEAD)
  fi
}

# Runs the hook command as the harness does: sh -c, in cwd $1, with HOME and CLAUDE_CONFIG_DIR in
# the fixture and its Linux uname first on PATH. $2 = remote sets CLAUDE_CODE_REMOTE. Sets cmd, hrc
# and hout. Returns 1 when settings.json has no such command.
# Clock in seconds with a fraction, from python. Times one hook run.
clock() { python3 -c 'import time; print("%.3f" % time.time())'; }

# The install-log lines a hook run wrote, without the helper's own start and end lines.
hook_log_lines() { grep -v 'install_from_main.sh:' "$1" 2>/dev/null; }

# Waits for detached work a hook may leave running: returns once the install log has stopped
# growing for 3 s, or after 30 s. A hook that writes nothing returns after about 3 s.
settle() {
  last=""; quiet=0; i=0
  while [ "$i" -lt 60 ]; do
    cur=$(cat "$1" 2>/dev/null | wc -c | tr -d ' ')
    if [ "$cur" = "$last" ]; then quiet=$((quiet + 1)); else quiet=0; last="$cur"; fi
    [ "$quiet" -lt 6 ] || break
    sleep 0.5; i=$((i + 1))
  done
}

# Runs the hook command as the harness does: sh -c, in cwd $1, with HOME and CLAUDE_CONFIG_DIR in
# the fixture and its Linux uname first on PATH. $2 = remote sets CLAUDE_CODE_REMOTE. Sets cmd, hrc,
# hout and hook_secs (the hook's own wall-clock time, before any detached work is waited for).
# Returns 1 when settings.json has no such command. $3 = nowait skips the settle wait, so a second
# run can start while the first is still detached.
run_hook() {
  cmd=$(hook_command) || cmd=""
  [ -n "$cmd" ] || return 1
  t0=$(clock)
  (
    cd "$1" || exit 1
    unset CLAUDE_CODE_REMOTE
    if [ "${2:-}" = remote ]; then CLAUDE_CODE_REMOTE=1; export CLAUDE_CODE_REMOTE; fi
    HOME="$1/home"; CLAUDE_CONFIG_DIR="$1/home/.claude-cfg"; PATH="$1/shim:$PATH"
    export HOME CLAUDE_CONFIG_DIR PATH
    sh -c "$cmd"
  ) > "$work/hook.out" 2> "$work/hook.err"
  hrc=$?
  t1=$(clock)
  hook_secs=$(python3 -c 'import sys; print("%.3f" % (float(sys.argv[2]) - float(sys.argv[1])))' "$t0" "$t1")
  hout=$(cat "$work/hook.out" "$work/hook.err")
  [ "${3:-}" = nowait ] || settle "$1/home/.claude-cfg/claude-settings-install.log"
  return 0
}

# ---- Case 22: origin ahead -> local main and the pin move to origin/main, then the install runs from the pin ----
case22() {
  name="case22: SessionStart hook with origin ahead moves local main and the pinned checkout to origin/main, then the installer runs from the pin"
  d="$work/case22"; hook_fixture "$d"
  run_hook "$d" || { bad "$name" "no SessionStart command reads CLAUDE.md in $HOOK_SETTINGS"; return; }
  why=""
  [ "$hrc" -eq 0 ] || why="$why; hook exited $hrc: $hout"
  [ "$(git -C "$d/clone" rev-parse main)" = "$c1" ] \
    || why="$why; local main is $(git -C "$d/clone" rev-parse main), want origin/main $c1"
  [ "$(git -C "$d/clone-live" rev-parse HEAD)" = "$c1" ] \
    || why="$why; the pinned checkout is at $(git -C "$d/clone-live" rev-parse HEAD), want $c1"
  [ "$(tail -n 1 "$d/home/ran-install.txt" 2>/dev/null)" = "$c1" ] \
    || why="$why; the installer did not run from the pin at $c1: [$(cat "$d/home/ran-install.txt" 2>/dev/null)]"
  if [ -z "$why" ]; then ok "$name"; else bad "$name" "${why#; }"; fi
}

# ---- Case 23: main checked out in the clone with a tracked change -> tree, change and pin stay; one skip line ----
case23() {
  name="case23: SessionStart hook with main checked out in the clone and a tracked change leaves the tree, the change and the pin alone, and logs one line"
  d="$work/case23"; hook_fixture "$d" main
  printf 'local edit\n' >> "$d/clone/notes.txt"
  run_hook "$d" || { bad "$name" "no SessionStart command reads CLAUDE.md in $HOOK_SETTINGS"; return; }
  why=""
  [ "$hrc" -eq 0 ] || why="$why; hook exited $hrc: $hout"
  [ "$(git -C "$d/clone" rev-parse HEAD)" = "$c0" ] \
    || why="$why; the clone's checkout moved to $(git -C "$d/clone" rev-parse HEAD)"
  [ "$(tail -n 1 "$d/clone/notes.txt")" = "local edit" ] \
    || why="$why; the tracked change is gone or changed"
  [ "$(git -C "$d/clone-live" rev-parse HEAD)" = "$c0" ] \
    || why="$why; the pinned checkout moved to $(git -C "$d/clone-live" rev-parse HEAD)"
  # The helper's own start and end lines do not count: only the skip line is the hook's to write.
  skip=$(grep -v 'install_from_main.sh:' "$d/home/.claude-cfg/claude-settings-install.log" 2>/dev/null)
  n=$(printf '%s\n' "$skip" | grep -c .)
  if [ "$n" -ne 1 ]; then
    why="$why; want one skip line in the install log, got $n: [$skip]"
  elif ! printf '%s\n' "$skip" | grep -q main; then
    why="$why; the skip line does not name main: [$skip]"
  fi
  if [ -z "$why" ]; then ok "$name"; else bad "$name" "${why#; }"; fi
}

# ---- Case 24: CLAUDE_CODE_REMOTE set -> exit 0 with no fetch, no move, no install, no log ----
case24() {
  name="case24: SessionStart hook with CLAUDE_CODE_REMOTE set exits 0 with no fetch, no move, no install and no log"
  d="$work/case24"; hook_fixture "$d"
  run_hook "$d" remote || { bad "$name" "no SessionStart command reads CLAUDE.md in $HOOK_SETTINGS"; return; }
  why=""
  [ "$hrc" -eq 0 ] || why="$why; hook exited $hrc: $hout"
  [ "$(git -C "$d/clone" rev-parse refs/remotes/origin/main)" = "$c0" ] || why="$why; origin/main was fetched"
  [ "$(git -C "$d/clone" rev-parse main)" = "$c0" ] || why="$why; main moved"
  [ "$(git -C "$d/clone-live" rev-parse HEAD)" = "$c0" ] || why="$why; the pinned checkout moved"
  [ ! -e "$d/home/ran-install.txt" ] || why="$why; the installer ran"
  [ ! -e "$d/home/.claude-cfg/claude-settings-install.log" ] || why="$why; the install log was written"
  if [ -z "$why" ]; then ok "$name"; else bad "$name" "${why#; }"; fi
}

# A Windows uname, and stubs for the two tools the helper's MINGW branch calls: powershell.exe
# records the commit of the install.ps1 it was given, and cygpath -w echoes the path it is given.
make_mingw_shim() {
  printf '#!/bin/sh\necho MINGW64_NT-10.0-26200\n' > "$1/uname"
  cat > "$1/powershell.exe" <<'EOF'
#!/bin/sh
for a; do last="$a"; done
printf '%s\n' "$(git -C "$(dirname "$last")" rev-parse HEAD)" >> "$HOME/ran-ps1.txt"
EOF
  cat > "$1/cygpath" <<'EOF'
#!/bin/sh
for a; do last="$a"; done
printf '%s\n' "$last"
EOF
  chmod +x "$1/uname" "$1/powershell.exe" "$1/cygpath"
}

# ---- Case 25: main checked out in the clone, no tracked change, an untracked file -> the clone and the pin move to origin/main; the file stays ----
case25() {
  name="case25: SessionStart hook with main checked out in the clone, no tracked change and an untracked file, moves the clone and the pin to origin/main and keeps the file"
  d="$work/case25"; hook_fixture "$d" main
  printf 'mine\n' > "$d/clone/scratch.txt"
  run_hook "$d" || { bad "$name" "no SessionStart command reads CLAUDE.md in $HOOK_SETTINGS"; return; }
  why=""
  [ "$hrc" -eq 0 ] || why="$why; hook exited $hrc: $hout"
  [ "$(git -C "$d/clone" rev-parse HEAD)" = "$c1" ] \
    || why="$why; the clone's checkout is at $(git -C "$d/clone" rev-parse HEAD), want origin/main $c1"
  [ "$(git -C "$d/clone-live" rev-parse HEAD)" = "$c1" ] \
    || why="$why; the pinned checkout is at $(git -C "$d/clone-live" rev-parse HEAD), want $c1"
  [ "$(cat "$d/clone/scratch.txt" 2>/dev/null)" = "mine" ] \
    || why="$why; the untracked file is gone or changed"
  [ "$(tail -n 1 "$d/home/ran-install.txt" 2>/dev/null)" = "$c1" ] \
    || why="$why; the installer did not run from the pin at $c1: [$(cat "$d/home/ran-install.txt" 2>/dev/null)]"
  if [ -z "$why" ]; then ok "$name"; else bad "$name" "${why#; }"; fi
}

# ---- Case 26: Windows uname -> the hook moves the clone and the pin to origin/main, then install.ps1 runs from the pin ----
case26() {
  name="case26: SessionStart hook under a Windows uname moves the clone and the pin to origin/main, then runs install.ps1 from the pin"
  d="$work/case26"; hook_fixture "$d" main
  make_mingw_shim "$d/shim"
  run_hook "$d" || { bad "$name" "no SessionStart command reads CLAUDE.md in $HOOK_SETTINGS"; return; }
  why=""
  [ "$hrc" -eq 0 ] || why="$why; hook exited $hrc: $hout"
  [ "$(git -C "$d/clone" rev-parse HEAD)" = "$c1" ] \
    || why="$why; the clone's checkout is at $(git -C "$d/clone" rev-parse HEAD), want origin/main $c1"
  [ "$(git -C "$d/clone-live" rev-parse HEAD)" = "$c1" ] \
    || why="$why; the pinned checkout is at $(git -C "$d/clone-live" rev-parse HEAD), want $c1"
  [ "$(tail -n 1 "$d/home/ran-ps1.txt" 2>/dev/null)" = "$c1" ] \
    || why="$why; install.ps1 did not run from the pin at $c1: [$(cat "$d/home/ran-ps1.txt" 2>/dev/null)]"
  if [ -z "$why" ]; then ok "$name"; else bad "$name" "${why#; }"; fi
}

# ---- Case 27: main checked out in a clean linked worktree -> that tree fast-forwards and the pin ends at origin/main ----
case27() {
  name="case27: SessionStart hook with main checked out in a clean linked worktree fast-forwards that worktree and moves the pin to origin/main"
  d="$work/case27"; hook_fixture "$d" linked
  run_hook "$d" || { bad "$name" "no SessionStart command reads CLAUDE.md in $HOOK_SETTINGS"; return; }
  why=""
  [ "$hrc" -eq 0 ] || why="$why; hook exited $hrc: $hout"
  [ "$(git -C "$d/linked" rev-parse HEAD)" = "$c1" ] \
    || why="$why; the linked worktree is at $(git -C "$d/linked" rev-parse HEAD), want origin/main $c1"
  [ "$(git -C "$d/clone-live" rev-parse HEAD)" = "$c1" ] \
    || why="$why; the pinned checkout is at $(git -C "$d/clone-live" rev-parse HEAD), want $c1"
  [ "$(tail -n 1 "$d/home/ran-install.txt" 2>/dev/null)" = "$c1" ] \
    || why="$why; the installer did not run from the pin at $c1: [$(cat "$d/home/ran-install.txt" 2>/dev/null)]"
  if [ -z "$why" ]; then ok "$name"; else bad "$name" "${why#; }"; fi
}

# ---- Case 28: a dirty pinned checkout -> the pin is not moved, its change stays, one log line names it ----
case28() {
  name="case28: SessionStart hook with a dirty pinned checkout leaves the pin unmoved with its change, and logs one line that names it"
  d="$work/case28"; hook_fixture "$d" trunk
  printf 'pin edit\n' >> "$d/clone-live/notes.txt"
  run_hook "$d" || { bad "$name" "no SessionStart command reads CLAUDE.md in $HOOK_SETTINGS"; return; }
  why=""
  [ "$hrc" -eq 0 ] || why="$why; hook exited $hrc: $hout"
  [ ! -L "$d/clone-live" ] || why="$why; the pin path is now a link"
  [ "$(git -C "$d/clone-live" rev-parse HEAD)" = "$c0" ] \
    || why="$why; the pinned checkout moved to $(git -C "$d/clone-live" rev-parse HEAD), want $c0"
  if git -C "$d/clone-live" symbolic-ref -q HEAD >/dev/null 2>&1; then why="$why; the pin was switched to a branch"; fi
  [ "$(tail -n 1 "$d/clone-live/notes.txt")" = "pin edit" ] \
    || why="$why; the pin's change is gone or changed"
  skip=$(hook_log_lines "$d/home/.claude-cfg/claude-settings-install.log")
  n=$(printf '%s\n' "$skip" | grep -c .)
  if [ "$n" -ne 1 ]; then
    why="$why; want one log line for the dirty pin, got $n: [$skip]"
  elif ! printf '%s\n' "$skip" | grep -q clone-live; then
    why="$why; the log line does not name the pin: [$skip]"
  fi
  if [ -z "$why" ]; then ok "$name"; else bad "$name" "${why#; }"; fi
}

# ---- Case 29: origin unreachable -> the hook returns within 2 s; the detached work logs git's fetch reason ----
case29() {
  name="case29: SessionStart hook with an unreachable origin returns within 2 s, and the detached work logs one line with git's fetch reason"
  d="$work/case29"; hook_fixture "$d" trunk
  git -C "$d/clone" remote set-url origin "$d/no-such.git"
  run_hook "$d" || { bad "$name" "no SessionStart command reads CLAUDE.md in $HOOK_SETTINGS"; return; }
  why=""
  [ "$hrc" -eq 0 ] || why="$why; hook exited $hrc: $hout"
  [ "$(python3 -c 'import sys; print(float(sys.argv[1]) <= 2.0)' "$hook_secs")" = True ] \
    || why="$why; the hook took $hook_secs s, want 2 s or less"
  skip=$(hook_log_lines "$d/home/.claude-cfg/claude-settings-install.log")
  n=$(printf '%s\n' "$skip" | grep -c .)
  if [ "$n" -ne 1 ]; then
    why="$why; want one log line for the fetch failure, got $n: [$skip]"
  elif ! printf '%s\n' "$skip" | grep -q "fatal:"; then
    why="$why; the log line has no git reason: [$skip]"
  fi
  if [ -z "$why" ]; then ok "$name"; else bad "$name" "${why#; }"; fi
}

# ---- Case 30: pin and local main already at origin/main -> the installer does not run ----
case30() {
  name="case30: SessionStart hook with the pin and local main already at origin/main does not run the installer"
  d="$work/case30"; hook_fixture "$d" trunk same
  run_hook "$d" || { bad "$name" "no SessionStart command reads CLAUDE.md in $HOOK_SETTINGS"; return; }
  why=""
  [ "$hrc" -eq 0 ] || why="$why; hook exited $hrc: $hout"
  [ "$(git -C "$d/clone" rev-parse main)" = "$c0" ] || why="$why; local main moved"
  [ "$(git -C "$d/clone-live" rev-parse HEAD)" = "$c0" ] || why="$why; the pinned checkout moved"
  [ ! -e "$d/home/ran-install.txt" ] || why="$why; the installer ran: [$(cat "$d/home/ran-install.txt")]"
  if [ -z "$why" ]; then ok "$name"; else bad "$name" "${why#; }"; fi
}

# ---- Case 31: local main diverged from origin, clean tree on main -> the tree stays; one log line with git's reason ----
case31() {
  name="case31: SessionStart hook with local main diverged from origin leaves the clean tree on main unchanged and logs one line with git's reason"
  d="$work/case31"; hook_fixture "$d" main
  git -C "$d/clone" commit -q --allow-empty -m local
  cl=$(git -C "$d/clone" rev-parse HEAD)
  run_hook "$d" || { bad "$name" "no SessionStart command reads CLAUDE.md in $HOOK_SETTINGS"; return; }
  why=""
  [ "$hrc" -eq 0 ] || why="$why; hook exited $hrc: $hout"
  [ "$(git -C "$d/clone" rev-parse HEAD)" = "$cl" ] \
    || why="$why; the clone's checkout moved to $(git -C "$d/clone" rev-parse HEAD), want $cl"
  skip=$(hook_log_lines "$d/home/.claude-cfg/claude-settings-install.log")
  n=$(printf '%s\n' "$skip" | grep -c .)
  if [ "$n" -ne 1 ]; then
    why="$why; want one log line for the refused fast-forward, got $n: [$skip]"
  elif ! printf '%s\n' "$skip" | grep -q "fatal:"; then
    why="$why; the log line has no git reason: [$skip]"
  fi
  if [ -z "$why" ]; then ok "$name"; else bad "$name" "${why#; }"; fi
}

# Waits, up to 30 s, until the checkout at $1 has HEAD $2: a detached child may still be moving it.
waitfor_head() {
  i=0
  while [ "$i" -lt 60 ]; do
    [ "$(git -C "$1" rev-parse HEAD 2>/dev/null)" = "$2" ] && return 0
    sleep 0.5; i=$((i + 1))
  done
  return 1
}

# ---- Case 32: two runs back to back; the second loses the ref-lock race -> no fetch failure logged ----
case32() {
  name="case32: two hook runs back to back, the second losing the ref-lock race, log no fetch failure, and pin and main end at origin/main with one install"
  d="$work/case32"; hook_fixture "$d" trunk ahead
  # The first fetch to reach its ref update holds the ref lock for 4 s (a reference-transaction hook).
  printf '#!/bin/sh\n[ "$1" = prepared ] || exit 0\ncat > /dev/null\n[ -f "$HOME/slow-refs" ] || exit 0\nrm -f "$HOME/slow-refs"\nsleep 4\n' \
    > "$d/clone/.git/hooks/reference-transaction"
  chmod +x "$d/clone/.git/hooks/reference-transaction"
  : > "$d/home/slow-refs"
  run_hook "$d" "" nowait || { bad "$name" "no SessionStart command reads CLAUDE.md in $HOOK_SETTINGS"; return; }
  first_hrc=$hrc
  run_hook "$d" "" nowait || { bad "$name" "no SessionStart command reads CLAUDE.md in $HOOK_SETTINGS"; return; }
  waitfor_head "$d/clone-live" "$c1"
  settle "$d/home/.claude-cfg/claude-settings-install.log"
  why=""
  [ "$first_hrc" -eq 0 ] && [ "$hrc" -eq 0 ] || why="$why; a hook exited non-zero: $first_hrc, $hrc"
  [ "$(git -C "$d/clone" rev-parse main)" = "$c1" ] || why="$why; local main is $(git -C "$d/clone" rev-parse main), want $c1"
  [ "$(git -C "$d/clone-live" rev-parse HEAD)" = "$c1" ] || why="$why; the pinned checkout is at $(git -C "$d/clone-live" rev-parse HEAD), want $c1"
  skip=$(hook_log_lines "$d/home/.claude-cfg/claude-settings-install.log")
  if printf '%s\n' "$skip" | grep -q "fetch of origin/main failed"; then
    why="$why; the log reports a fetch failure for a lost ref-lock race: [$skip]"
  fi
  installs=$(grep -c . "$d/home/ran-install.txt" 2>/dev/null)
  [ "${installs:-0}" -eq 1 ] || why="$why; want one install, got ${installs:-0}"
  if [ -z "$why" ]; then ok "$name"; else bad "$name" "${why#; }"; fi
}

# ---- Case 33: a half-populated tree at main's commit is not reused; the pin ends on a complete tree ----
case33() {
  name="case33: a half-populated <clone>-live-<sha> at main's commit is repaired or replaced, not reused; the pin ends on a complete tree at origin/main"
  d="$work/case33"; hook_fixture "$d" trunk ahead
  # The tree a kill leaves behind: at main's commit, with one tracked file missing.
  git -C "$d/clone" fetch -q origin main
  short=$(printf '%s' "$c1" | cut -c1-12)
  git -C "$d/clone" worktree add -q --detach --lock --reason "claude-settings live pin" "$d/clone-live-$short" "$c1"
  rm -f "$d/clone-live-$short/install.sh"
  run_hook "$d" || { bad "$name" "no SessionStart command reads CLAUDE.md in $HOOK_SETTINGS"; return; }
  waitfor_head "$d/clone-live" "$c1"
  settle "$d/home/.claude-cfg/claude-settings-install.log"
  why=""
  [ "$hrc" -eq 0 ] || why="$why; hook exited $hrc: $hout"
  [ "$(git -C "$d/clone-live" rev-parse HEAD)" = "$c1" ] || why="$why; the pinned checkout is at $(git -C "$d/clone-live" rev-parse HEAD), want $c1"
  incomplete=$(git -C "$d/clone-live" status --porcelain --untracked-files=no)
  [ -z "$incomplete" ] || why="$why; the pinned tree is incomplete: [$incomplete]"
  [ "$(tail -n 1 "$d/home/ran-install.txt" 2>/dev/null)" = "$c1" ] \
    || why="$why; the installer did not run from a complete pin at $c1: [$(cat "$d/home/ran-install.txt" 2>/dev/null)]"
  if [ -z "$why" ]; then ok "$name"; else bad "$name" "${why#; }"; fi
}

# ---- Case 34: nothing moves -> the install log is unchanged, no installer starts, at most one fetch ----
case34() {
  name="case34: when nothing moves the hook writes nothing to the install log, starts no installer, and runs at most one fetch"
  d="$work/case34"; hook_fixture "$d" main same
  # A git that counts its fetches and then runs the real git.
  real=$(command -v git)
  cat > "$d/shim/git" <<EOF
#!/bin/sh
case " \$* " in *" fetch "*) echo fetch >> "\$HOME/git-fetches.txt" ;; esac
exec "$real" "\$@"
EOF
  chmod +x "$d/shim/git"
  run_hook "$d" || { bad "$name" "no SessionStart command reads CLAUDE.md in $HOOK_SETTINGS"; return; }
  why=""
  [ "$hrc" -eq 0 ] || why="$why; hook exited $hrc: $hout"
  log="$d/home/.claude-cfg/claude-settings-install.log"
  [ ! -s "$log" ] || why="$why; the install log was written: [$(cat "$log")]"
  [ ! -e "$d/home/ran-install.txt" ] || why="$why; the installer ran"
  # Exactly one fetch: the count also shows the counting shim reached the hook at all.
  fetches=$(grep -c . "$d/home/git-fetches.txt" 2>/dev/null)
  [ "${fetches:-0}" -eq 1 ] || why="$why; the hook ran ${fetches:-0} fetches, want exactly 1"
  if [ -z "$why" ]; then ok "$name"; else bad "$name" "${why#; }"; fi
}

# ---- Case 35: a stale tree in the way makes the pin move fail -> one log line with the helper's reason ----
case35() {
  name="case35: a failed pin move logs one line with the helper's own reason, not only end exit=1"
  d="$work/case35"; hook_fixture "$d" trunk ahead
  short=$(printf '%s' "$c1" | cut -c1-12)
  mkdir -p "$d/clone-live-$short"
  printf 'stale\n' > "$d/clone-live-$short/junk.txt"
  run_hook "$d" || { bad "$name" "no SessionStart command reads CLAUDE.md in $HOOK_SETTINGS"; return; }
  why=""
  [ "$hrc" -eq 0 ] || why="$why; hook exited $hrc: $hout"
  [ "$(git -C "$d/clone-live" rev-parse HEAD)" = "$c0" ] || why="$why; the pinned checkout moved"
  [ "$(cat "$d/clone-live-$short/junk.txt" 2>/dev/null)" = "stale" ] || why="$why; the stale tree changed"
  skip=$(hook_log_lines "$d/home/.claude-cfg/claude-settings-install.log")
  n=$(printf '%s\n' "$skip" | grep -c .)
  if [ "$n" -ne 1 ]; then
    why="$why; want one log line for the failed move, got $n: [$skip]"
  elif ! printf '%s\n' "$skip" | grep -q "in the way"; then
    why="$why; the log line has no helper reason: [$skip]"
  fi
  if [ -z "$why" ]; then ok "$name"; else bad "$name" "${why#; }"; fi
}

# A clone whose settings.json and other.txt are tracked, with a pin behind main (pin_behind_main).
# settings.json holds two keys; reorder_settings rewrites a tree's copy with the keys swapped.
settings_fixture() {
  h="$1/home"; mkdir -p "$h"
  live_clone "$1/clone" stub
  printf '{"a": 1, "b": [1, 2]}\n' > "$1/clone/settings.json"
  printf 'x\n' > "$1/clone/other.txt"
  git -C "$1/clone" add -A; git -C "$1/clone" commit -q -m files
  pin_behind_main "$1/clone"
}
reorder_settings() { printf '{"b": [1, 2], "a": 1}\n' > "$1/settings.json"; }

# ---- Case 36: a pin whose settings.json only has its keys reordered moves to main, and the file equals main's ----
case36() {
  name="case36: a pin with only a reordered settings.json moves to main and its settings.json equals main's"
  command -v python3 >/dev/null 2>&1 || { skip "$name" "no python3"; return; }
  d="$work/case36"; settings_fixture "$d"
  reorder_settings "$d/clone-live"
  run_live "$d/clone"
  why=""
  [ "$rc" -eq 0 ] || why="$why; helper exited $rc: $out"
  [ "$(git -C "$d/clone-live" rev-parse HEAD 2>/dev/null)" = "$(git -C "$d/clone" rev-parse main)" ] || why="$why; the pin did not move to main"
  cmp -s "$d/clone-live/settings.json" "$d/clone/settings.json" || why="$why; the pin's settings.json differs from main's"
  if [ -z "$why" ]; then ok "$name"; else bad "$name" "${why#; }"; fi
}

# ---- Case 37: a pin whose settings.json changes one value is refused and not moved ----
case37() {
  name="case37: a pin whose settings.json changes a value is refused and not moved"
  d="$work/case37"; settings_fixture "$d"
  printf '{"b": [1, 2], "a": 2}\n' > "$d/clone-live/settings.json"
  run_live "$d/clone"
  why=""
  [ "$rc" -eq 1 ] || why="$why; helper exited $rc, want 1"
  printf '%s' "$errs" | grep -q "tracked changes" || why="$why; no tracked-changes line: $errs"
  [ "$(git -C "$d/clone-live" rev-parse HEAD)" = "$c0" ] || why="$why; the pin moved"
  grep -q '"a": 2' "$d/clone-live/settings.json" || why="$why; the changed value was lost"
  if [ -z "$why" ]; then ok "$name"; else bad "$name" "${why#; }"; fi
}

# ---- Case 38: a reordered settings.json plus a change to another tracked file is refused ----
case38() {
  name="case38: a reordered settings.json plus another tracked change is refused and nothing is touched"
  d="$work/case38"; settings_fixture "$d"
  reorder_settings "$d/clone-live"
  printf 'edited\n' > "$d/clone-live/other.txt"
  run_live "$d/clone"
  why=""
  [ "$rc" -eq 1 ] || why="$why; helper exited $rc, want 1"
  [ "$(git -C "$d/clone-live" rev-parse HEAD)" = "$c0" ] || why="$why; the pin moved"
  [ "$(cat "$d/clone-live/other.txt")" = "edited" ] || why="$why; the other change was lost"
  grep -q '^{"b"' "$d/clone-live/settings.json" || why="$why; settings.json was restored despite the refusal"
  if [ -z "$why" ]; then ok "$name"; else bad "$name" "${why#; }"; fi
}

# ---- Case 39: an old live tree holding only a reordered settings.json is swept ----
case39() {
  name="case39: an old -live-<hex> tree with only a reordered settings.json is swept"
  command -v python3 >/dev/null 2>&1 || { skip "$name" "no python3"; return; }
  d="$work/case39"; settings_fixture "$d"
  git -C "$d/clone" worktree add -q --detach "$d/clone-live-aaaaaaaaaaaa" "$c0"
  reorder_settings "$d/clone-live-aaaaaaaaaaaa"
  run_live "$d/clone"
  why=""
  [ "$rc" -eq 0 ] || why="$why; helper exited $rc: $out"
  [ ! -e "$d/clone-live-aaaaaaaaaaaa" ] || why="$why; the old tree is still there"
  if [ -z "$why" ]; then ok "$name"; else bad "$name" "${why#; }"; fi
}

ALL="case1 case2 case3 case4 case5 case6 case7 case8 case9 case10 case11 case12 case13 case14 case15 case16 case17 case18 case19 case20 case21 case22 case23 case24 case25 case26 case27 case28 case29 case30 case31 case32 case33 case34 case35 case36 case37 case38 case39"
if [ $# -gt 0 ]; then WANT="$*"; else WANT="$ALL"; fi
for c in $WANT; do "$c"; done

printf '%s passed, %s failed, %s skipped\n' "$PASS" "$FAIL" "$SKIP"
[ "$FAIL" -eq 0 ]

#!/bin/sh
# Cases for merge/install_from_main.sh, the afterMerge helper. It finds the worktree that
# holds refs/heads/main and runs that tree's install.sh. Shell script, following the layout
# of hooks/test_install_src.sh: named cases, each isolated, a pass/fail line per case, and a
# summary exit code.
#
# Run it from the repository root:
#
#   sh merge/test_install_from_main.sh [case ...]   # names given: run only those cases
#
# Every case builds its own temp git repos. The main tree is on branch main, and its
# install.sh is a stub. The linked worktree is on branch feature, and its install.sh is a
# different stub. Each stub writes its own directory to its own marker file, so a case can
# see which install.sh ran. HOME and CLAUDE_CONFIG_DIR point into the temp dir, so the real
# ~/.claude is never touched. INSTALL_FROM_MAIN_UNDER_TEST lets a case point at another copy
# of the script.

set -u

HERE="$(cd "$(dirname "$0")" && pwd)"
REPO_ROOT="$(cd "$HERE/.." && pwd)"
SCRIPT="${INSTALL_FROM_MAIN_UNDER_TEST:-$REPO_ROOT/merge/install_from_main.sh}"
case "$SCRIPT" in /*) ;; *) SCRIPT="$PWD/$SCRIPT" ;; esac

PASS=0
FAIL=0

ok() { PASS=$((PASS + 1)); printf 'ok   - %s\n' "$1"; }
bad() { FAIL=$((FAIL + 1)); printf 'FAIL - %s: %s\n' "$1" "$2"; }

# Canonicalize: on macOS, mktemp -d returns /var/folders/..., where /var is a symlink to
# /private/var. git reports worktree paths in resolved form, so every path built here goes
# through pwd -P before a comparison.
realpwd() { ( cd "$1" 2>/dev/null && pwd -P ); }

work=$(mktemp -d); work=$(realpwd "$work")
cleanup() { rm -rf "$work"; }
trap cleanup EXIT

# Write an install.sh stub to $1. It records its own directory in marker file $2, then exits
# with $STUB_EXIT (default 0). The directory comes from $0, so the marker names the tree the
# script really ran from, not the caller's working directory.
make_stub() {
  cat > "$1" <<EOF
#!/bin/sh
cd "\$(dirname "\$0")" && pwd -P > "$2"
exit "\${STUB_EXIT:-0}"
EOF
}

# Build a main tree at $1 whose first branch is $5 (default main), and a linked worktree at
# $2 on branch feature. Each tree commits its own stub. $3 is the main stub's marker, $4 the
# linked stub's marker.
make_pair() {
  main="$1"; linked="$2"; mark_main="$3"; mark_linked="$4"; first="${5:-main}"
  mkdir -p "$main"
  ( cd "$main" && git init -q -b "$first" && git config user.email t@example.com && git config user.name t )
  make_stub "$main/install.sh" "$mark_main"
  ( cd "$main" && git add install.sh && git commit -q -m init )
  ( cd "$main" && git worktree add -q -b feature "$linked" )
  make_stub "$linked/install.sh" "$mark_linked"
  ( cd "$linked" && git add install.sh && git commit -q -m stub )
}

# Run the script with cwd $1. Extra arguments $2... are KEY=VALUE pairs for env. Sets $out
# (stdout and stderr together) and $rc. HOME and CLAUDE_CONFIG_DIR come from $h.
run_from() {
  dir="$1"; shift
  ( cd "$dir" && env HOME="$h" CLAUDE_CONFIG_DIR="$h/.claude-cfg" "$@" bash "$SCRIPT" ) > "$work/run.out" 2> "$work/run.err"
  rc=$?
  outs=$(cat "$work/run.out")
  errs=$(cat "$work/run.err")
  out=$(cat "$work/run.out" "$work/run.err")
}

# ---- Case 1: run from a linked worktree -> main tree's install.sh runs, caller's does not --
case1() {
  name="case1: run from a linked worktree runs the main tree's install.sh, not the caller's"
  d="$work/case1"; h="$d/home"; mkdir -p "$h"
  make_pair "$d/main" "$d/linked" "$d/mark-main" "$d/mark-linked"
  run_from "$d/linked"

  if [ $rc -ne 0 ]; then
    bad "$name" "script exited $rc: $out"
  elif [ "$(cat "$d/mark-main" 2>/dev/null)" != "$(realpwd "$d/main")" ]; then
    bad "$name" "main tree install.sh did not run: $out"
  elif [ -e "$d/mark-linked" ]; then
    bad "$name" "the calling worktree's install.sh ran"
  else
    ok "$name"
  fi
}

# ---- Case 2: run from the main tree itself -> main tree's install.sh runs, once -----------
case2() {
  name="case2: run from the main tree runs the main tree's install.sh, not the linked one"
  d="$work/case2"; h="$d/home"; mkdir -p "$h"
  make_pair "$d/main" "$d/linked" "$d/mark-main" "$d/mark-linked"
  run_from "$d/main"

  if [ $rc -ne 0 ]; then
    bad "$name" "script exited $rc: $out"
  elif [ "$(cat "$d/mark-main" 2>/dev/null)" != "$(realpwd "$d/main")" ]; then
    bad "$name" "main tree install.sh did not run: $out"
  elif [ -e "$d/mark-linked" ]; then
    bad "$name" "the linked worktree's install.sh ran"
  else
    ok "$name"
  fi
}

# ---- Case 3: no worktree holds main (the branch exists, unchecked-out) -> one stderr line ----
# Owner ruling 2026-10-11: this fails loudly. One line on stderr says install.sh was not run and
# names `git switch main`. The exit is non-zero, so the merge tool reports FAILED. No install.sh
# runs. Nothing goes to stdout.
case3() {
  name="case3: no worktree holds main prints one stderr line naming git switch main, exits non-zero"
  d="$work/case3"; h="$d/home"; mkdir -p "$h"
  make_pair "$d/main" "$d/linked" "$d/mark-main" "$d/mark-linked"
  # Move the main tree off main. The branch main still exists, but no worktree holds it.
  ( cd "$d/main" && git checkout -q -b trunk )
  run_from "$d/linked"
  lines=$(printf '%s\n' "$errs" | grep -c .)

  if [ $rc -eq 0 ]; then
    bad "$name" "script exited 0, expected non-zero so the merge tool reports FAILED: $out"
  elif [ -n "$outs" ]; then
    bad "$name" "text went to stdout, expected stderr only: $outs"
  elif [ "$lines" -ne 1 ]; then
    bad "$name" "expected one stderr line, got $lines: $errs"
  else
    case "$errs" in
      *"install.sh"*"not run"*"git switch main"*) ;;
      *) bad "$name" "stderr does not say install.sh was not run and name git switch main: $errs"; return ;;
    esac
    if [ -e "$d/mark-main" ] || [ -e "$d/mark-linked" ]; then
      bad "$name" "an install.sh ran although no worktree holds main"
    else
      ok "$name"
    fi
  fi
}

# ---- Case 4: no branch named main anywhere -> one stderr line, exit non-zero ----------
# Same ruling as case 3: non-zero exit, one stderr line naming `git switch main`, no install.sh run.
case4() {
  name="case4: no branch named main at all prints one stderr line naming git switch main, exits non-zero"
  d="$work/case4"; h="$d/home"; mkdir -p "$h"
  make_pair "$d/main" "$d/linked" "$d/mark-main" "$d/mark-linked" trunk
  run_from "$d/linked"
  lines=$(printf '%s\n' "$errs" | grep -c .)

  if [ $rc -eq 0 ]; then
    bad "$name" "script exited 0, expected non-zero so the merge tool reports FAILED: $out"
  elif [ -n "$outs" ]; then
    bad "$name" "text went to stdout, expected stderr only: $outs"
  elif [ "$lines" -ne 1 ]; then
    bad "$name" "expected one stderr line, got $lines: $errs"
  else
    case "$errs" in
      *"install.sh"*"not run"*"git switch main"*) ;;
      *) bad "$name" "stderr does not say install.sh was not run and name git switch main: $errs"; return ;;
    esac
    if [ -e "$d/mark-main" ] || [ -e "$d/mark-linked" ]; then
      bad "$name" "an install.sh ran although no branch named main exists"
    else
      ok "$name"
    fi
  fi
}

# ---- Case 5: main tree's install.sh exits non-zero -> script exits with that code ---------
case5() {
  name="case5: a failing main install.sh makes the script exit with the same code"
  d="$work/case5"; h="$d/home"; mkdir -p "$h"
  make_pair "$d/main" "$d/linked" "$d/mark-main" "$d/mark-linked"
  run_from "$d/linked" STUB_EXIT=7

  if [ "$rc" -ne 7 ]; then
    bad "$name" "expected exit 7, got $rc: $out"
  elif [ "$(cat "$d/mark-main" 2>/dev/null)" != "$(realpwd "$d/main")" ]; then
    bad "$name" "main tree install.sh did not run, so the code proves nothing: $out"
  elif [ -e "$d/mark-linked" ]; then
    bad "$name" "the calling worktree's install.sh ran"
  else
    ok "$name"
  fi
}

# ---- Case 6: main tree path has a space -> still found and run ---------------------------
case6() {
  name="case6: a main tree path with a space is found and its install.sh runs"
  d="$work/case6"; h="$d/home"; mkdir -p "$h"
  make_pair "$d/main tree" "$d/linked" "$d/mark-main" "$d/mark-linked"
  run_from "$d/linked"

  if [ $rc -ne 0 ]; then
    bad "$name" "script exited $rc: $out"
  elif [ "$(cat "$d/mark-main" 2>/dev/null)" != "$(realpwd "$d/main tree")" ]; then
    bad "$name" "main tree install.sh did not run: $out"
  elif [ -e "$d/mark-linked" ]; then
    bad "$name" "the calling worktree's install.sh ran"
  else
    ok "$name"
  fi
}

# ---- Live pin: owner ruling 2026-10-15, record merge-reinstalls-from-main ("The ruling") ----
# The links in ~/.claude point at one pinned checkout: a worktree of the clone, on a detached
# HEAD at main's commit, at the sibling path <clone>-live. The helper moves that checkout to
# the new main, then runs the install from it. Cases 7-11 build a fake clone at $d/clone, a
# caller worktree at $d/linked, and the pinned checkout at $d/clone-live.
# Stub cases (7, 10, 11) commit marker installers, so no real install runs. Cases 8 and 9 run
# the real install.sh. Cases 7-10 shim uname to Linux, so the helper takes its POSIX path on
# Git Bash. Case 11 uses the real uname.

SKIP=0
skip() { SKIP=$((SKIP + 1)); printf 'SKIP - %s: %s\n' "$1" "$2"; }

# install.sh links into CLAUDE_CONFIG_DIR. Git Bash makes real links only with
# winsymlinks:nativestrict, and only when the account may create them. Probe once.
printf x > "$work/probe-src"
LINKS_OK=no
if MSYS=winsymlinks:nativestrict ln -s "$work/probe-src" "$work/probe-link" 2>/dev/null \
   && [ -L "$work/probe-link" ]; then LINKS_OK=yes; fi

# Marker installers for a clone at $1. Each writes a marker file into its own folder.
stub_installers() {
  cat > "$1/install.sh" <<'EOF'
#!/bin/sh
printf ran > "$(dirname "$0")/ran-sh.txt"
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

# A uname that reports Linux, in dir $1. The helper takes its POSIX path only on Linux.
make_shim() {
  mkdir -p "$1"
  printf '#!/bin/sh\necho Linux\n' > "$1/uname"
  chmod +x "$1/uname"
}

# Run the helper with cwd $1 and HOME $h. Sets rc, outs (stdout), errs (stderr), out (both).
# SHIM, when set, goes first on PATH.
run_live() {
  ( cd "$1" && env HOME="$h" CLAUDE_CONFIG_DIR="$h/.claude-cfg" MSYS=winsymlinks:nativestrict \
      PATH="${SHIM:+$SHIM:}$PATH" bash "$SCRIPT" ) > "$work/run.out" 2> "$work/run.err"
  rc=$?
  outs=$(cat "$work/run.out")
  errs=$(cat "$work/run.err")
  out=$(cat "$work/run.out" "$work/run.err")
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
  elif [ ! -f "$d/clone-live/ran-ps1.txt" ]; then
    bad "$name" "install.ps1 did not run from the pinned checkout: $out"
  else
    ok "$name"
  fi
}

ALL="case1 case2 case3 case4 case5 case6 case7 case8 case9 case10 case11"
if [ $# -gt 0 ]; then WANT="$*"; else WANT="$ALL"; fi
for c in $WANT; do "$c"; done

printf '%s passed, %s failed, %s skipped\n' "$PASS" "$FAIL" "$SKIP"
[ "$FAIL" -eq 0 ]

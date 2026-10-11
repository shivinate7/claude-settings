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
  out=$(cd "$dir" && env HOME="$h" CLAUDE_CONFIG_DIR="$h/.claude-cfg" "$@" bash "$SCRIPT" 2>&1)
  rc=$?
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

# ---- Case 3: no worktree holds main (the branch exists, unchecked-out) -> one line, exit 0 -
case3() {
  name="case3: no worktree holds main prints one line saying install.sh was not run, exits 0"
  d="$work/case3"; h="$d/home"; mkdir -p "$h"
  make_pair "$d/main" "$d/linked" "$d/mark-main" "$d/mark-linked"
  # Move the main tree off main. The branch main still exists, but no worktree holds it.
  ( cd "$d/main" && git checkout -q -b trunk )
  run_from "$d/linked"
  lines=$(printf '%s\n' "$out" | grep -c .)

  if [ $rc -ne 0 ]; then
    bad "$name" "script exited $rc: $out"
  elif [ "$lines" -ne 1 ]; then
    bad "$name" "expected one output line, got $lines: $out"
  else
    case "$out" in
      *"install.sh"*"not run"*) ;;
      *) bad "$name" "output does not say install.sh was not run: $out"; return ;;
    esac
    if [ -e "$d/mark-main" ] || [ -e "$d/mark-linked" ]; then
      bad "$name" "an install.sh ran although no worktree holds main"
    else
      ok "$name"
    fi
  fi
}

# ---- Case 4: no branch named main anywhere -> one line, exit 0 ---------------------------
case4() {
  name="case4: no branch named main at all prints one line saying install.sh was not run, exits 0"
  d="$work/case4"; h="$d/home"; mkdir -p "$h"
  make_pair "$d/main" "$d/linked" "$d/mark-main" "$d/mark-linked" trunk
  run_from "$d/linked"
  lines=$(printf '%s\n' "$out" | grep -c .)

  if [ $rc -ne 0 ]; then
    bad "$name" "script exited $rc: $out"
  elif [ "$lines" -ne 1 ]; then
    bad "$name" "expected one output line, got $lines: $out"
  else
    case "$out" in
      *"install.sh"*"not run"*) ;;
      *) bad "$name" "output does not say install.sh was not run: $out"; return ;;
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

ALL="case1 case2 case3 case4 case5 case6"
if [ $# -gt 0 ]; then WANT="$*"; else WANT="$ALL"; fi
for c in $WANT; do "$c"; done

printf '%s passed, %s failed\n' "$PASS" "$FAIL"
[ "$FAIL" -eq 0 ]

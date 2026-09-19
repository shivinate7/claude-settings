#!/bin/sh
# Cases for install.sh's checkout-detection (Task C) and session_start.sh's divergence
# check (Task E). Shell script, following the layout of hooks/test_guard.py: named cases,
# each isolated, a pass/fail line per case, and a summary exit code.
#
# Run it from the repository root:
#
#   sh hooks/test_install_src.sh
#
# Every case uses a temp HOME and a temp CLAUDE_CONFIG_DIR so the real /root/.claude is
# never touched. SESSION_START_SH lets a case point at a different (e.g. pre-fix) copy of
# the hook, the same way GUARD_UNDER_TEST works in hooks/test_guard.py.

set -u

HERE="$(cd "$(dirname "$0")" && pwd)"
REPO_ROOT="$(cd "$HERE/.." && pwd)"
INSTALL_SH="${INSTALL_SH_UNDER_TEST:-$REPO_ROOT/install.sh}"
SESSION_START_SH_DEFAULT="${SESSION_START_SH_UNDER_TEST:-$REPO_ROOT/hooks/session_start.sh}"

PASS=0
FAIL=0

ok() { PASS=$((PASS + 1)); printf 'ok   - %s\n' "$1"; }
bad() { FAIL=$((FAIL + 1)); printf 'FAIL - %s: %s\n' "$1" "$2"; }

work=$(mktemp -d)
cleanup() { rm -rf "$work"; }
trap cleanup EXIT

# Make a bare-bones fake checkout of the repo at $1, with a fake origin remote matching
# $REPO, and CLAUDE.md/settings.json content of our choosing.
make_checkout() {
  dir="$1"
  md_body="$2"
  mkdir -p "$dir/hooks" "$dir/agents" "$dir/lint"
  ( cd "$dir" && git init -q && git config user.email t@example.com && git config user.name t \
      && git remote add origin https://github.com/shivinate7/claude-settings.git )
  printf '%s\n' "$md_body" > "$dir/CLAUDE.md"
  printf '{}\n' > "$dir/settings.json"
  ( cd "$dir" && git add -A && git commit -q -m init )
}

# ---- Case 1: piped cloud install, checkout present -> SRC is the checkout ----------------
case1() {
  name="case1: piped cloud install with checkout present uses the checkout"
  h=$(mktemp -d); cfg="$h/.claude-cfg"; co="$work/case1-checkout"
  make_checkout "$co" "# repo CLAUDE.md case1"

  # Simulate `curl ... | bash -s -- --cloud`: bash reads the script off its own stdin
  # (BASH_SOURCE[0] is then "-", never a real file), exactly like the piped install.
  out=$(cd "$co" && env -i PATH="$PATH" HOME="$h" CLAUDE_CONFIG_DIR="$cfg" \
        bash -s -- --cloud < "$INSTALL_SH" 2>&1)
  rc=$?

  pointer=$(sed -n 's|^@\(.*\)/CLAUDE\.md$|\1|p' "$cfg/CLAUDE.md" 2>/dev/null | head -n1)
  case "$pointer" in "~"/*) pointer="$h${pointer#\~}";; esac

  if [ $rc -ne 0 ]; then
    bad "$name" "install.sh exited $rc: $out"
  elif [ "$pointer" != "$co" ]; then
    bad "$name" "pointer target [$pointer] != checkout [$co]"
  elif [ -d "$h/claude-settings" ]; then
    bad "$name" "$h/claude-settings was created; a mirror should not have been fetched"
  else
    ok "$name"
  fi
  rm -rf "$h"
}

# ---- Case 2: piped cloud install, no checkout anywhere -> old fallback mirror -------------
case2() {
  name="case2: piped cloud install with no checkout fetches the fallback mirror"
  h=$(mktemp -d); cfg="$h/.claude-cfg"; scratch="$work/case2-scratch"
  mkdir -p "$scratch"

  # Stub curl: instead of hitting GitHub, write minimal local fixtures.
  stub_bin="$work/case2-bin"; mkdir -p "$stub_bin"
  cat > "$stub_bin/curl" <<'EOF'
#!/bin/sh
# usage: curl -fsSL <url> -o <out>
out=""
prev=""
for a in "$@"; do
  if [ "$prev" = "-o" ]; then out="$a"; fi
  prev="$a"
done
[ -n "$out" ] || exit 1
case "$*" in
  *CLAUDE.md*) printf '# fallback mirror CLAUDE.md\n' > "$out" ;;
  *settings.json*) printf '{}\n' > "$out" ;;
  *) printf '# stub\n' > "$out" ;;
esac
exit 0
EOF
  chmod +x "$stub_bin/curl"

  out=$(cd "$scratch" && env -i PATH="$stub_bin:$PATH" HOME="$h" CLAUDE_CONFIG_DIR="$cfg" \
        GIT_CEILING_DIRECTORIES="$scratch" \
        bash -s -- --cloud < "$INSTALL_SH" 2>&1)
  rc=$?

  pointer=$(sed -n 's|^@\(.*\)/CLAUDE\.md$|\1|p' "$cfg/CLAUDE.md" 2>/dev/null | head -n1)
  case "$pointer" in "~"/*) pointer="$h${pointer#\~}";; esac
  expect="$h/claude-settings"

  if [ $rc -ne 0 ]; then
    bad "$name" "install.sh exited $rc: $out"
  elif [ "$pointer" != "$expect" ]; then
    bad "$name" "pointer target [$pointer] != fallback mirror [$expect]"
  elif [ ! -f "$expect/CLAUDE.md" ]; then
    bad "$name" "fallback mirror CLAUDE.md was not fetched"
  else
    ok "$name"
  fi
  rm -rf "$h"
}

# ---- Case 3: local ./install.sh from a clone -> unchanged, SRC is the clone --------------
case3() {
  name="case3: local install.sh from a clone uses the clone"
  h=$(mktemp -d); cfg="$h/.claude-cfg"; co="$work/case3-checkout"
  make_checkout "$co" "# repo CLAUDE.md case3"
  cp "$INSTALL_SH" "$co/install.sh"

  out=$(cd "$co" && env -i PATH="$PATH" HOME="$h" CLAUDE_CONFIG_DIR="$cfg" \
        bash ./install.sh 2>&1)
  rc=$?

  pointer=$(sed -n 's|^@\(.*\)/CLAUDE\.md$|\1|p' "$cfg/CLAUDE.md" 2>/dev/null | head -n1)
  case "$pointer" in "~"/*) pointer="$h${pointer#\~}";; esac

  if [ $rc -ne 0 ]; then
    bad "$name" "install.sh exited $rc: $out"
  elif [ "$pointer" != "$co" ]; then
    bad "$name" "pointer target [$pointer] != clone [$co]"
  else
    ok "$name"
  fi
  rm -rf "$h"
}

# ---- Case 4/5/6: session_start.sh divergence check ----------------------------------------
case4() {
  name="case4: session_start.sh with pointer == checkout prints no extra line"
  co="$work/case4-checkout"; cfg="$work/case4-cfg"
  make_checkout "$co" "# same content"
  mkdir -p "$cfg"
  printf '@%s/CLAUDE.md\n' "$co" > "$cfg/CLAUDE.md"

  out=$(cd "$co" && CLAUDE_CONFIG_DIR="$cfg" sh "$SESSION_START_SH_DEFAULT" < /dev/null 2>/tmp/c4err)
  rc=$?
  errsize=$(wc -c < /tmp/c4err | tr -d '[:space:]'); rm -f /tmp/c4err
  lines=$(printf '%s\n' "$out" | grep -c 'differ from this checkout')

  if [ $rc -ne 0 ]; then
    bad "$name" "exit $rc"
  elif [ "$errsize" != "0" ]; then
    bad "$name" "wrote to stderr"
  elif [ "$lines" != "0" ]; then
    bad "$name" "unexpected divergence line: $out"
  else
    ok "$name"
  fi
}

case5() {
  name="case5: session_start.sh with pointer != checkout prints exactly one line"
  co="$work/case5-checkout"; cfg="$work/case5-cfg"
  make_checkout "$co" "# checkout content, v1"
  mkdir -p "$cfg"
  printf '# global content, different\n' > "$cfg/CLAUDE.md.pointed"
  # Pointer names a separate file with different content than the checkout's CLAUDE.md.
  mkdir -p "$cfg/other"
  printf '# global content, different\n' > "$cfg/other/CLAUDE.md"
  printf '@%s/other/CLAUDE.md\n' "$cfg" > "$cfg/CLAUDE.md"

  out=$(cd "$co" && CLAUDE_CONFIG_DIR="$cfg" sh "$SESSION_START_SH_DEFAULT" < /dev/null 2>/tmp/c5err)
  rc=$?
  errsize=$(wc -c < /tmp/c5err | tr -d '[:space:]'); rm -f /tmp/c5err
  lines=$(printf '%s\n' "$out" | grep -c 'differ from this checkout')

  if [ $rc -ne 0 ]; then
    bad "$name" "exit $rc"
  elif [ "$errsize" != "0" ]; then
    bad "$name" "wrote to stderr"
  elif [ "$lines" != "1" ]; then
    bad "$name" "expected exactly 1 divergence line, got $lines: $out"
  else
    ok "$name"
  fi
}

case6() {
  name="case6: session_start.sh outside a git tree stays silent, exit 0"
  outside="$work/case6-not-a-repo"; cfg="$work/case6-cfg"
  mkdir -p "$outside" "$cfg"
  printf '@%s/CLAUDE.md\n' "$work/case6-checkout" > "$cfg/CLAUDE.md"

  out=$(cd "$outside" && CLAUDE_CONFIG_DIR="$cfg" GIT_CEILING_DIRECTORIES="$outside" \
        sh "$SESSION_START_SH_DEFAULT" < /dev/null 2>/tmp/c6err)
  rc=$?
  errsize=$(wc -c < /tmp/c6err | tr -d '[:space:]'); rm -f /tmp/c6err

  if [ $rc -ne 0 ]; then
    bad "$name" "exit $rc"
  elif [ "$errsize" != "0" ]; then
    bad "$name" "wrote to stderr"
  elif [ -n "$out" ]; then
    bad "$name" "unexpected output: $out"
  else
    ok "$name"
  fi
}

case1
case2
case3
case4
case5
case6

printf '%s passed, %s failed\n' "$PASS" "$FAIL"
[ "$FAIL" -eq 0 ]

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

# Canonicalize: on macOS, mktemp -d returns a /var/folders/... path where /var is itself
# a symlink to /private/var. install.sh's checkout detection goes through
# `git rev-parse --show-toplevel`, which resolves that symlink, so the pointer it writes
# names /private/var/folders/.... Resolving every temp dir to its physical path right
# after creating it means every path built from it already matches what install.sh will
# write, with no separate resolve step needed at each comparison.
realpwd() { ( cd "$1" 2>/dev/null && pwd -P ); }

work=$(mktemp -d); work=$(realpwd "$work")
cleanup() { rm -rf "$work"; }
trap cleanup EXIT

# Make a bare-bones fake checkout of the repo at $1, with CLAUDE.md/settings.json content
# of our choosing. $3, if given, is the origin URL (default: the legitimate https form);
# pass an adversarial or alternate-form origin to drive the origin-matching cases.
make_checkout() {
  dir="$1"
  md_body="$2"
  origin="${3:-https://github.com/shivinate7/claude-settings.git}"
  mkdir -p "$dir/hooks" "$dir/agents" "$dir/lint"
  ( cd "$dir" && git init -q && git config user.email t@example.com && git config user.name t \
      && git remote add origin "$origin" )
  printf '%s\n' "$md_body" > "$dir/CLAUDE.md"
  printf '{}\n' > "$dir/settings.json"
  ( cd "$dir" && git add -A && git commit -q -m init )
}

# A curl stub for the fetch-fallback path: writes minimal fixtures instead of hitting
# GitHub. Installed at $1/curl.
make_curl_stub() {
  stub_bin="$1"
  mkdir -p "$stub_bin"
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
}

# ---- Case 1: piped cloud install, checkout present -> SRC is the checkout ----------------
case1() {
  name="case1: piped cloud install with checkout present uses the checkout"
  h=$(mktemp -d); h=$(realpwd "$h"); cfg="$h/.claude-cfg"; co="$work/case1-checkout"
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
  h=$(mktemp -d); h=$(realpwd "$h"); cfg="$h/.claude-cfg"; scratch="$work/case2-scratch"
  mkdir -p "$scratch"

  # Stub curl: instead of hitting GitHub, write minimal local fixtures.
  stub_bin="$work/case2-bin"
  make_curl_stub "$stub_bin"

  # Disable the bounded root search for this case: this container's own /home/user is a
  # real matching checkout, and without this override the search would find it instead
  # of exercising the fallback this case is about.
  out=$(cd "$scratch" && env -i PATH="$stub_bin:$PATH" HOME="$h" CLAUDE_CONFIG_DIR="$cfg" \
        GIT_CEILING_DIRECTORIES="$scratch" CLAUDE_SETTINGS_SEARCH_ROOTS="$work/no-such-root" \
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
  h=$(mktemp -d); h=$(realpwd "$h"); cfg="$h/.claude-cfg"; co="$work/case3-checkout"
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

# ---- Origin-matching cases: exact owner/name, not substring ------------------------------
# Each drives a piped cloud install with a checkout at the given origin, and asserts
# whether that checkout is accepted (SRC = checkout, no fetch) or rejected (falls through
# to the fetch-fallback mirror, curl stubbed so nothing hits the network).
origin_case() {
  case_name="$1"; origin_url="$2"; should_match="$3"   # should_match: yes|no

  h=$(mktemp -d); h=$(realpwd "$h"); cfg="$h/.claude-cfg"
  co="$work/origin-$(printf '%s' "$case_name" | tr -c 'a-zA-Z0-9' '-')-checkout"
  make_checkout "$co" "# origin case content" "$origin_url"

  stub_bin="$work/origin-$(printf '%s' "$case_name" | tr -c 'a-zA-Z0-9' '-')-bin"
  make_curl_stub "$stub_bin"

  # Same reason as case2: keep this container's real /home/user checkout out of the
  # rejection cases, so a wrongly-permissive origin match can't be masked by the search.
  out=$(cd "$co" && env -i PATH="$stub_bin:$PATH" HOME="$h" CLAUDE_CONFIG_DIR="$cfg" \
        CLAUDE_SETTINGS_SEARCH_ROOTS="$work/no-such-root" \
        bash -s -- --cloud < "$INSTALL_SH" 2>&1)
  rc=$?

  pointer=$(sed -n 's|^@\(.*\)/CLAUDE\.md$|\1|p' "$cfg/CLAUDE.md" 2>/dev/null | head -n1)
  case "$pointer" in "~"/*) pointer="$h${pointer#\~}";; esac

  if [ $rc -ne 0 ]; then
    bad "$case_name" "install.sh exited $rc: $out"
  elif [ "$should_match" = "yes" ]; then
    if [ "$pointer" = "$co" ]; then ok "$case_name"; else
      bad "$case_name" "expected checkout accepted, pointer=[$pointer] checkout=[$co]"
    fi
  else
    if [ "$pointer" = "$co" ]; then
      bad "$case_name" "adversarial origin [$origin_url] was wrongly accepted as shivinate7/claude-settings"
    elif [ "$pointer" = "$h/claude-settings" ] && [ -f "$h/claude-settings/CLAUDE.md" ]; then
      ok "$case_name"
    else
      bad "$case_name" "expected fallback mirror, got pointer=[$pointer]"
    fi
  fi
  rm -rf "$h"
}

case_origins() {
  # REPO is shivinate7/claude-settings.
  origin_case "origin: https with .git matches"        "https://github.com/shivinate7/claude-settings.git" yes
  origin_case "origin: https without .git matches"      "https://github.com/shivinate7/claude-settings"     yes
  origin_case "origin: ssh with .git matches"           "git@github.com:shivinate7/claude-settings.git"     yes
  origin_case "origin: ssh without .git matches"        "git@github.com:shivinate7/claude-settings"         yes
  origin_case "origin: name-suffix-evil does not match" "https://github.com/shivinate7/claude-settings-evil.git" no
  origin_case "origin: owner-prefix-evil does not match" "https://github.com/evil-shivinate7/claude-settings.git" no
  origin_case "origin: owner-notshivinate7 does not match" "https://github.com/notshivinate7/claude-settings.git" no
  origin_case "origin: ssh with explicit port matches"      "ssh://git@github.com:22/shivinate7/claude-settings.git" yes
  origin_case "origin: wrong host (gitlab.com) does not match" "https://gitlab.com/shivinate7/claude-settings.git" no
  origin_case "origin: extra leading path segment does not match" "https://github.com/mirror/shivinate7/claude-settings.git" no
  origin_case "origin: bare path with no host does not match" "file:///local/shivinate7/claude-settings" no
}

# ---- Case 7: no $CLAUDE_PROJECT_DIR, cwd not the checkout -> bounded root search finds it --
case7() {
  name="case7: no CLAUDE_PROJECT_DIR, cwd elsewhere, checkout under \$HOME is still found"
  h=$(mktemp -d); h=$(realpwd "$h"); cfg="$h/.claude-cfg"
  co="$h/some-project-dir"     # one level under $HOME, as the bounded search expects
  make_checkout "$co" "# case7 content"
  notacheckout="$work/case7-elsewhere"; mkdir -p "$notacheckout"

  # Root list narrowed to the temp $h for this case, standing in for "$HOME": production
  # always includes $HOME itself, this just avoids also scanning the container's real
  # /home/user and /root (which would pass anyway, but would not prove this case's point).
  out=$(cd "$notacheckout" && env -i PATH="$PATH" HOME="$h" CLAUDE_CONFIG_DIR="$cfg" \
        GIT_CEILING_DIRECTORIES="$notacheckout" CLAUDE_SETTINGS_SEARCH_ROOTS="$h" \
        bash -s -- --cloud < "$INSTALL_SH" 2>&1)
  rc=$?

  pointer=$(sed -n 's|^@\(.*\)/CLAUDE\.md$|\1|p' "$cfg/CLAUDE.md" 2>/dev/null | head -n1)
  case "$pointer" in "~"/*) pointer="$h${pointer#\~}";; esac

  if [ $rc -ne 0 ]; then
    bad "$name" "install.sh exited $rc: $out"
  elif [ "$pointer" != "$co" ]; then
    bad "$name" "pointer target [$pointer] != checkout [$co] (cwd-only detection would miss this)"
  elif [ -d "$h/claude-settings" ]; then
    bad "$name" "$h/claude-settings was created; a mirror should not have been fetched"
  else
    ok "$name"
  fi
  rm -rf "$h"
}

# ---- Pointer-as-candidate cases: an existing ~/.claude/CLAUDE.md pointer is tried first --
# Each case pre-seeds $cfg/CLAUDE.md with a pointer line before running install.sh, with
# cwd elsewhere and no CLAUDE_PROJECT_DIR, and (unless the case is specifically about
# depth) a root-scan list that cannot reach the pointer's target either, so only the
# pointer candidate itself can produce a match.
seed_pointer() {
  # $1 = cfg dir, $2 = the "@<path>" line's path half (already ~-form or absolute)
  mkdir -p "$1"
  printf '@%s/CLAUDE.md\n' "$2" > "$1/CLAUDE.md"
}

pointer_case1() {
  name="pointer1: pointer names a checkout two levels under \$HOME, root scan can't reach it"
  h=$(mktemp -d); h=$(realpwd "$h"); cfg="$h/.claude-cfg"
  co="$h/Developer/claude-settings"     # two levels deep, mirrors the owner's layout
  make_checkout "$co" "# pointer1 content"
  seed_pointer "$cfg" "$co"
  elsewhere="$work/pointer1-elsewhere"; mkdir -p "$elsewhere"
  stub_bin="$work/pointer1-bin"; make_curl_stub "$stub_bin"

  # CLAUDE_SETTINGS_SEARCH_ROOTS=$h only scans one level under $h ("Developer"), which
  # is not itself a git toplevel, so the bounded scan cannot find $co on its own here.
  out=$(cd "$elsewhere" && env -i PATH="$stub_bin:$PATH" HOME="$h" CLAUDE_CONFIG_DIR="$cfg" \
        GIT_CEILING_DIRECTORIES="$elsewhere" CLAUDE_SETTINGS_SEARCH_ROOTS="$h" \
        bash -s -- --cloud < "$INSTALL_SH" 2>&1)
  rc=$?

  pointer=$(sed -n 's|^@\(.*\)/CLAUDE\.md$|\1|p' "$cfg/CLAUDE.md" 2>/dev/null | head -n1)
  case "$pointer" in "~"/*) pointer="$h${pointer#\~}";; esac

  if [ $rc -ne 0 ]; then
    bad "$name" "install.sh exited $rc: $out"
  elif [ "$pointer" != "$co" ]; then
    bad "$name" "pointer target [$pointer] != checkout [$co] (root scan alone would miss this)"
  elif [ -d "$h/claude-settings" ]; then
    bad "$name" "$h/claude-settings was created; a mirror should not have been fetched"
  else
    ok "$name"
  fi
  rm -rf "$h"
}

pointer_case2() {
  name="pointer2: pointer names a directory that does not exist, falls through to fallback"
  h=$(mktemp -d); h=$(realpwd "$h"); cfg="$h/.claude-cfg"
  seed_pointer "$cfg" "$h/no-such-checkout"
  elsewhere="$work/pointer2-elsewhere"; mkdir -p "$elsewhere"
  stub_bin="$work/pointer2-bin"; make_curl_stub "$stub_bin"

  out=$(cd "$elsewhere" && env -i PATH="$stub_bin:$PATH" HOME="$h" CLAUDE_CONFIG_DIR="$cfg" \
        GIT_CEILING_DIRECTORIES="$elsewhere" CLAUDE_SETTINGS_SEARCH_ROOTS="$work/no-such-root" \
        bash -s -- --cloud < "$INSTALL_SH" 2>&1)
  rc=$?

  pointer=$(sed -n 's|^@\(.*\)/CLAUDE\.md$|\1|p' "$cfg/CLAUDE.md" 2>/dev/null | head -n1)
  case "$pointer" in "~"/*) pointer="$h${pointer#\~}";; esac
  expect="$h/claude-settings"

  if [ $rc -ne 0 ]; then
    bad "$name" "install.sh exited $rc: $out"
  elif [ "$pointer" != "$expect" ]; then
    bad "$name" "pointer target [$pointer] != fallback mirror [$expect]"
  else
    ok "$name"
  fi
  rm -rf "$h"
}

pointer_case3() {
  name="pointer3: pointer names a directory that is not a git checkout, falls through"
  h=$(mktemp -d); h=$(realpwd "$h"); cfg="$h/.claude-cfg"
  notgit="$h/not-a-checkout"; mkdir -p "$notgit"
  seed_pointer "$cfg" "$notgit"
  elsewhere="$work/pointer3-elsewhere"; mkdir -p "$elsewhere"
  stub_bin="$work/pointer3-bin"; make_curl_stub "$stub_bin"

  out=$(cd "$elsewhere" && env -i PATH="$stub_bin:$PATH" HOME="$h" CLAUDE_CONFIG_DIR="$cfg" \
        GIT_CEILING_DIRECTORIES="$elsewhere" CLAUDE_SETTINGS_SEARCH_ROOTS="$work/no-such-root" \
        bash -s -- --cloud < "$INSTALL_SH" 2>&1)
  rc=$?

  pointer=$(sed -n 's|^@\(.*\)/CLAUDE\.md$|\1|p' "$cfg/CLAUDE.md" 2>/dev/null | head -n1)
  case "$pointer" in "~"/*) pointer="$h${pointer#\~}";; esac
  expect="$h/claude-settings"

  if [ $rc -ne 0 ]; then
    bad "$name" "install.sh exited $rc: $out"
  elif [ "$pointer" != "$expect" ]; then
    bad "$name" "pointer target [$pointer] != fallback mirror [$expect]"
  else
    ok "$name"
  fi
  rm -rf "$h"
}

pointer_case4() {
  name="pointer4: pointer names a checkout with a rejected origin, is not accepted"
  h=$(mktemp -d); h=$(realpwd "$h"); cfg="$h/.claude-cfg"
  co="$h/evil-checkout"
  make_checkout "$co" "# pointer4 content" "https://gitlab.com/shivinate7/claude-settings.git"
  seed_pointer "$cfg" "$co"
  elsewhere="$work/pointer4-elsewhere"; mkdir -p "$elsewhere"
  stub_bin="$work/pointer4-bin"; make_curl_stub "$stub_bin"

  out=$(cd "$elsewhere" && env -i PATH="$stub_bin:$PATH" HOME="$h" CLAUDE_CONFIG_DIR="$cfg" \
        GIT_CEILING_DIRECTORIES="$elsewhere" CLAUDE_SETTINGS_SEARCH_ROOTS="$work/no-such-root" \
        bash -s -- --cloud < "$INSTALL_SH" 2>&1)
  rc=$?

  pointer=$(sed -n 's|^@\(.*\)/CLAUDE\.md$|\1|p' "$cfg/CLAUDE.md" 2>/dev/null | head -n1)
  case "$pointer" in "~"/*) pointer="$h${pointer#\~}";; esac
  expect="$h/claude-settings"

  if [ $rc -ne 0 ]; then
    bad "$name" "install.sh exited $rc: $out"
  elif [ "$pointer" = "$co" ]; then
    bad "$name" "pointer to a rejected-origin checkout was wrongly accepted"
  elif [ "$pointer" != "$expect" ]; then
    bad "$name" "pointer target [$pointer] != fallback mirror [$expect]"
  else
    ok "$name"
  fi
  rm -rf "$h"
}

pointer_case5() {
  name="pointer5: no pointer file at all, cwd-based detection is unaffected"
  h=$(mktemp -d); h=$(realpwd "$h"); cfg="$h/.claude-cfg"
  co="$work/pointer5-checkout"
  make_checkout "$co" "# pointer5 content"
  # No seed_pointer call: $cfg does not exist yet, same as a first-ever install.

  out=$(cd "$co" && env -i PATH="$PATH" HOME="$h" CLAUDE_CONFIG_DIR="$cfg" \
        bash -s -- --cloud < "$INSTALL_SH" 2>&1)
  rc=$?

  pointer=$(sed -n 's|^@\(.*\)/CLAUDE\.md$|\1|p' "$cfg/CLAUDE.md" 2>/dev/null | head -n1)
  case "$pointer" in "~"/*) pointer="$h${pointer#\~}";; esac

  if [ $rc -ne 0 ]; then
    bad "$name" "install.sh exited $rc: $out"
  elif [ "$pointer" != "$co" ]; then
    bad "$name" "pointer target [$pointer] != checkout [$co]"
  else
    ok "$name"
  fi
  rm -rf "$h"
}

pointer_case6() {
  name="pointer6: pointer line uses the ~/ form, expands and matches"
  h=$(mktemp -d); h=$(realpwd "$h"); cfg="$h/.claude-cfg"
  co="$h/Developer/claude-settings"
  make_checkout "$co" "# pointer6 content"
  seed_pointer "$cfg" "~/Developer/claude-settings"
  elsewhere="$work/pointer6-elsewhere"; mkdir -p "$elsewhere"
  stub_bin="$work/pointer6-bin"; make_curl_stub "$stub_bin"

  out=$(cd "$elsewhere" && env -i PATH="$stub_bin:$PATH" HOME="$h" CLAUDE_CONFIG_DIR="$cfg" \
        GIT_CEILING_DIRECTORIES="$elsewhere" CLAUDE_SETTINGS_SEARCH_ROOTS="$work/no-such-root" \
        bash -s -- --cloud < "$INSTALL_SH" 2>&1)
  rc=$?

  pointer=$(sed -n 's|^@\(.*\)/CLAUDE\.md$|\1|p' "$cfg/CLAUDE.md" 2>/dev/null | head -n1)
  case "$pointer" in "~"/*) pointer="$h${pointer#\~}";; esac

  if [ $rc -ne 0 ]; then
    bad "$name" "install.sh exited $rc: $out"
  elif [ "$pointer" != "$co" ]; then
    bad "$name" "pointer target [$pointer] != checkout [$co]"
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
case_origins
case7
pointer_case1
pointer_case2
pointer_case3
pointer_case4
pointer_case5
pointer_case6
case4
case5
case6

printf '%s passed, %s failed\n' "$PASS" "$FAIL"
[ "$FAIL" -eq 0 ]

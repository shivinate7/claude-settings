#!/bin/sh
# Cases for install.sh's checkout-detection (Task C) and session_start.sh's divergence
# check (Task E). Shell script, following the layout of hooks/test_guard.py: named cases,
# each isolated, a pass/fail line per case, and a summary exit code.
#
# Run it from the repository root:
#
#   sh hooks/test_install_src.sh [case ...]   # names given: run only those cases
#
# Every case uses a temp HOME and a temp CLAUDE_CONFIG_DIR so the real /root/.claude is
# never touched. SESSION_START_SH lets a case point at a different copy of
# the hook, the same way GUARD_UNDER_TEST works in hooks/test_guard.py.
#
# Linux and macOS only. Under a Windows uname install.sh exits at its top, so a full run on Windows
# is red by design. On Windows CI it runs only cases that never start install.sh: caseF1 and caseG1
# (their own capped step), and caseF4 and caseF6 (through lint/check_unknown_reads_contract.py).
# Windows has its own test, under the real Git Bash uname: hooks/test_install_windows.sh.

set -u

HERE="$(cd "$(dirname "$0")" && pwd)"
. "$HERE/../lint/_test_git.sh"  # test-run signing opt-out
REPO_ROOT="$(cd "$HERE/.." && pwd)"
TRACKED_ROOT=$REPO_ROOT
# shellcheck source=../testing/tracked_tree.sh
. "$TRACKED_ROOT/testing/tracked_tree.sh"  # copies what git lists, so no fixture lists files
INSTALL_SH="${INSTALL_SH_UNDER_TEST:-$REPO_ROOT/install.sh}"
SESSION_START_SH_DEFAULT="${SESSION_START_SH_UNDER_TEST:-$REPO_ROOT/hooks/session_start.sh}"

PASS=0
FAIL=0
SKIP=0

ok() { PASS=$((PASS + 1)); printf 'ok   - %s\n' "$1"; }
bad() { FAIL=$((FAIL + 1)); printf 'FAIL - %s: %s\n' "$1" "$2"; }
# True when DIR holds an entry whose name has .bak. in it.
has_bak() { for e in "$1"/*.bak.*; do [ -e "$e" ] && return 0; done; return 1; }
skip() { SKIP=$((SKIP + 1)); printf 'SKIP - %s: %s\n' "$1" "$2"; }

# Canonicalize: on macOS, mktemp -d returns a /var/folders/... path where /var is itself
# a symlink to /private/var. install.sh's checkout detection goes through
# `git rev-parse --show-toplevel`, which resolves that symlink, so the pointer it writes
# names /private/var/folders/.... Resolving every temp dir to its physical path right
# after creating it means every path built from it already matches what install.sh will
# write, with no separate resolve step needed at each comparison.
realpwd() { ( cd "$1" 2>/dev/null && pwd -P ); }

# Normalize a Windows-style path (C:/Users/... or C:\Users\...) to the POSIX/MSYS form
# (/c/Users/...). install.sh, run under bash on Windows, can write either form into the
# pointer, depending on which tool built it. The values this script builds itself
# (mktemp, pwd -P) already come out in POSIX form. Routing BOTH sides of a comparison
# through this makes each case robust to either input form, instead of assuming the two
# already agree. A no-op on an already-POSIX path.
normalize_path() {
  p=$(printf '%s' "$1" | tr '\\' '/')
  case "$p" in
    [A-Za-z]:/*)
      drive=$(printf '%s' "${p%%:*}" | tr 'A-Z' 'a-z')
      rest=${p#*:}
      p="/$drive$rest"
      ;;
  esac
  printf '%s' "$p"
}

# The directories install.sh lands, read from the same manifest install.sh itself reads
# (landed-dirs.txt at the repo root), not a hand-kept list here. Keeps case8 honest about
# every landed directory, not just the two it happened to name by hand.
landed_dirs() {
  sed 's/#.*//; s/^[[:space:]]*//; s/[[:space:]]*$//' "$REPO_ROOT/landed-dirs.txt" | grep -v '^$'
}

# One run folder per test run (test-temp-standard): lint/_test_temp.py makes it under the repo's one temp
# root and sweeps sibling run folders older than a day. Every temp path in this file sits under it.
work=$(python3 -I -c 'import sys; sys.path.insert(0, sys.argv[1]); import _test_temp; print(_test_temp.run_folder())' "$REPO_ROOT/lint") || work=""
[ -n "$work" ] || { echo "FAIL - run folder: lint/_test_temp.py made no run folder"; exit 1; }
work=$(realpwd "$work")
cleanup() { rm -rf "$work"; }
trap cleanup EXIT

# Detect once whether this account can create a real symbolic link, and reuse the answer
# everywhere below. Windows needs SeCreateSymbolicLinkPrivilege for `ln -s`. Developer Mode,
# or an elevated account, grants it. Without that privilege, MSYS/git-bash's `ln -sfn` still
# exits 0. It copies the target's bytes into a plain file instead of linking it. A case that
# only checks the exit code never sees this. Checking `[ -L ]` on the result does. This is a
# capability probe, never an OS-name check. A Windows machine with Developer Mode on still
# runs every case below for real.
probe_dir=$(mktemp -d "$work/probe.XXXXXX")
printf 'probe\n' > "$probe_dir/target"
ln -sfn "$probe_dir/target" "$probe_dir/link" 2>/dev/null
if [ -L "$probe_dir/link" ]; then
  SYMLINK_CAPABLE=1
else
  SYMLINK_CAPABLE=0
fi
rm -rf "$probe_dir"
NO_SYMLINK_REASON="this account cannot create a real symlink (SeCreateSymbolicLinkPrivilege is not held, turn on Developer Mode or run elevated on Windows)"

# A stub uname for one answer: its dir goes first on PATH for the run that needs it.
make_uname_stub() {
  mkdir -p "$1"
  printf '#!/bin/sh\necho %s\n' "$2" > "$1/uname"
  chmod +x "$1/uname"
}

# Build the tarball once, from this repo's own tracked files, so the curl stub serves
# exactly what GitHub's archive/refs/heads/<ref>.tar.gz would serve: a top-level
# "claude-settings-main" directory holding every tracked file.
tarsrc="$work/tarsrc/claude-settings-main"; mkdir -p "$tarsrc"
( cd "$REPO_ROOT" && git ls-files -z | tar -cf - --null -T - ) | tar -xf - -C "$tarsrc"
tar -czf "$work/repo.tar.gz" -C "$work/tarsrc" claude-settings-main

# Make a bare-bones fake checkout of the repo at $1, with CLAUDE.md/settings.json content
# of our choosing. $3, if given, is the origin URL (default: the legitimate https form);
# pass an adversarial or alternate-form origin to drive the origin-matching cases.
make_checkout() {
  dir="$1"
  md_body="$2"
  origin="${3:-https://github.com/shivinate7/claude-settings.git}"
  mkdir -p "$dir"
  cp "$REPO_ROOT/landed-dirs.txt" "$dir/landed-dirs.txt"
  for sub in $(landed_dirs); do mkdir -p "$dir/$sub"; done
  # -b master: init.defaultBranch=main (Xcode's git) would start the clone on main, which install.sh pins.
  ( cd "$dir" && git init -q -b master && git config user.email t@example.com && git config user.name t \
      && git remote add origin "$origin" )
  printf '%s\n' "$md_body" > "$dir/CLAUDE.md"
  printf '{}\n' > "$dir/settings.json"
  ( cd "$dir" && git add -A && git commit -q -m init )
}

# A curl stub for the fetch-fallback path: writes minimal fixtures instead of hitting
# GitHub. Installed at $1/curl.
# $2 = fail-tarball: the tarball URL exits 1, so a case can prove a path never fetched it. Every fetch
# that carries an output file is logged to $stub_bin/calls.
make_curl_stub() {
  stub_bin="$1"
  mkdir -p "$stub_bin"
  if [ "${2:-}" = fail-tarball ]; then : > "$stub_bin/fail-tarball"; fi
  # $work is captured at generation time (unquoted heredoc marker); everything else is
  # escaped so it stays a literal to be evaluated when the stub itself runs.
  cat > "$stub_bin/curl" <<EOF
#!/bin/sh
# usage: curl -fsSL <url> -o <out>
out=""
prev=""
for a in "\$@"; do
  if [ "\$prev" = "-o" ]; then out="\$a"; fi
  prev="\$a"
done
[ -n "\$out" ] || exit 1
printf '%s\n' "\$*" >> "$stub_bin/calls"
case "\$*" in
  *.tar.gz*) [ -e "$stub_bin/fail-tarball" ] && exit 1; cp "$work/repo.tar.gz" "\$out" ;;
  *CLAUDE.md*) printf '# fallback mirror CLAUDE.md\n' > "\$out" ;;
  *settings.json*) printf '{}\n' > "\$out" ;;
  *) printf '# stub\n' > "\$out" ;;
esac
exit 0
EOF
  chmod +x "$stub_bin/curl"
}

# ---- Case 1: piped cloud install, checkout present -> SRC is the checkout ----------------
case1() {
  name="case1: piped cloud install with checkout present uses the checkout"
  h=$(new_home); cfg="$h/.claude-cfg"; co="$work/case1-checkout"
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
  elif [ "$(normalize_path "$pointer")" != "$(normalize_path "$co")" ]; then
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
  h=$(new_home); cfg="$h/.claude-cfg"; scratch="$work/case2-scratch"
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
  elif [ "$(normalize_path "$pointer")" != "$(normalize_path "$expect")" ]; then
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
  name="case3: local install.sh from a clone points the pointer at the pinned checkout <clone>-live"
  h=$(new_home); cfg="$h/.claude-cfg"; co="$work/case3-checkout"
  make_checkout "$co" "# repo CLAUDE.md case3"
  git -C "$co" branch -q -M main
  cp "$INSTALL_SH" "$co/install.sh"

  out=$(cd "$co" && env -i PATH="$PATH" HOME="$h" CLAUDE_CONFIG_DIR="$cfg" \
        bash ./install.sh 2>&1)
  rc=$?

  pointer=$(sed -n 's|^@\(.*\)/CLAUDE\.md$|\1|p' "$cfg/CLAUDE.md" 2>/dev/null | head -n1)
  case "$pointer" in "~"/*) pointer="$h${pointer#\~}";; esac

  if [ $rc -ne 0 ]; then
    bad "$name" "install.sh exited $rc: $out"
  elif [ "$(normalize_path "$pointer")" != "$(normalize_path "$co-live")" ]; then
    bad "$name" "pointer target [$pointer] != pinned checkout [$co-live]"
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

  h=$(new_home); cfg="$h/.claude-cfg"
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
    if [ "$(normalize_path "$pointer")" = "$(normalize_path "$co")" ]; then ok "$case_name"; else
      bad "$case_name" "expected checkout accepted, pointer=[$pointer] checkout=[$co]"
    fi
  else
    if [ "$(normalize_path "$pointer")" = "$(normalize_path "$co")" ]; then
      bad "$case_name" "adversarial origin [$origin_url] was wrongly accepted as shivinate7/claude-settings"
    elif [ "$(normalize_path "$pointer")" = "$(normalize_path "$h/claude-settings")" ] && [ -f "$h/claude-settings/CLAUDE.md" ]; then
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
  h=$(new_home); cfg="$h/.claude-cfg"
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
  elif [ "$(normalize_path "$pointer")" != "$(normalize_path "$co")" ]; then
    bad "$name" "pointer target [$pointer] != checkout [$co] (cwd-only detection would miss this)"
  elif [ -d "$h/claude-settings" ]; then
    bad "$name" "$h/claude-settings was created; a mirror should not have been fetched"
  else
    ok "$name"
  fi
  rm -rf "$h"
}

# ---- Case 8: fallback mirror lands every tracked file under every landed directory, no hand list
# Guards against a hand-maintained per-file fetch list drifting behind git: every file
# `git ls-files` reports under a directory landed-dirs.txt names must land both in the fetched
# mirror ($h/claude-settings/<path>) and in the config dir land_dir() copies it into for cloud
# installs ($cfg/<path>, since --cloud always copies rather than symlinks). The directory list
# itself comes from landed-dirs.txt (see landed_dirs() above), not a hand-kept "hooks lint"
# pair here, so this case cannot go blind to a directory the manifest adds.
case8() {
  name="case8: fallback mirror lands every tracked file under every landed directory"
  h=$(new_home); cfg="$h/.claude-cfg"; scratch="$work/case8-scratch"
  mkdir -p "$scratch"

  stub_bin="$work/case8-bin"
  make_curl_stub "$stub_bin"

  out=$(cd "$scratch" && env -i PATH="$stub_bin:$PATH" HOME="$h" CLAUDE_CONFIG_DIR="$cfg" \
        GIT_CEILING_DIRECTORIES="$scratch" CLAUDE_SETTINGS_SEARCH_ROOTS="$work/no-such-root" \
        bash -s -- --cloud < "$INSTALL_SH" 2>&1)
  rc=$?

  missing=""
  # landed_dirs prints one directory per line; each becomes its own ls-files argument, so the split is meant.
  # shellcheck disable=SC2046
  for path in $(git -C "$REPO_ROOT" ls-files $(landed_dirs)); do
    [ -f "$h/claude-settings/$path" ] || missing="$missing mirror:$path"
    [ -f "$cfg/$path" ] || missing="$missing landed:$path"
  done

  if [ $rc -ne 0 ]; then
    bad "$name" "install.sh exited $rc: $out"
  elif [ -n "$missing" ]; then
    bad "$name" "missing files:$missing"
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
  h=$(new_home); cfg="$h/.claude-cfg"
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
  elif [ "$(normalize_path "$pointer")" != "$(normalize_path "$co")" ]; then
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
  h=$(new_home); cfg="$h/.claude-cfg"
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
  elif [ "$(normalize_path "$pointer")" != "$(normalize_path "$expect")" ]; then
    bad "$name" "pointer target [$pointer] != fallback mirror [$expect]"
  else
    ok "$name"
  fi
  rm -rf "$h"
}

pointer_case3() {
  name="pointer3: pointer names a directory that is not a git checkout, falls through"
  h=$(new_home); cfg="$h/.claude-cfg"
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
  elif [ "$(normalize_path "$pointer")" != "$(normalize_path "$expect")" ]; then
    bad "$name" "pointer target [$pointer] != fallback mirror [$expect]"
  else
    ok "$name"
  fi
  rm -rf "$h"
}

pointer_case4() {
  name="pointer4: pointer names a checkout with a rejected origin, is not accepted"
  h=$(new_home); cfg="$h/.claude-cfg"
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
  elif [ "$(normalize_path "$pointer")" = "$(normalize_path "$co")" ]; then
    bad "$name" "pointer to a rejected-origin checkout was wrongly accepted"
  elif [ "$(normalize_path "$pointer")" != "$(normalize_path "$expect")" ]; then
    bad "$name" "pointer target [$pointer] != fallback mirror [$expect]"
  else
    ok "$name"
  fi
  rm -rf "$h"
}

pointer_case5() {
  name="pointer5: no pointer file at all, cwd-based detection is unaffected"
  h=$(new_home); cfg="$h/.claude-cfg"
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
  elif [ "$(normalize_path "$pointer")" != "$(normalize_path "$co")" ]; then
    bad "$name" "pointer target [$pointer] != checkout [$co]"
  else
    ok "$name"
  fi
  rm -rf "$h"
}

pointer_case6() {
  name="pointer6: pointer line uses the ~/ form, expands and matches"
  h=$(new_home); cfg="$h/.claude-cfg"
  co="$h/Developer/claude-settings"
  make_checkout "$co" "# pointer6 content"
  # The pointer line must hold a literal "~/", so install.sh expands it; $HOME would test another form.
  # shellcheck disable=SC2088
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
  elif [ "$(normalize_path "$pointer")" != "$(normalize_path "$co")" ]; then
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
  name="case5: two clones of one origin, differing CLAUDE.md, prints exactly one line"
  co="$work/case5-checkout"; other="$work/case5-other"; cfg="$work/case5-cfg"
  # Both trees are real clones of the same origin URL (make_checkout's default), so the
  # fix's same-repository check passes and the raw content differs, so the line must print.
  make_checkout "$co" "# checkout content, v1"
  make_checkout "$other" "# global content, different"
  mkdir -p "$cfg"
  printf '@%s/CLAUDE.md\n' "$other" > "$cfg/CLAUDE.md"

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

  # CLAUDE_CODE_REMOTE unset: a cloud session prints its session-tier line by design.
  out=$(cd "$outside" && CLAUDE_CONFIG_DIR="$cfg" GIT_CEILING_DIRECTORIES="$outside" \
        env -u CLAUDE_CODE_REMOTE sh "$SESSION_START_SH_DEFAULT" < /dev/null 2>/tmp/c6err)
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

case9() {
  name="case9: unrelated repo with its own CLAUDE.md stays silent (the banchi repro)"
  co="$work/case9-checkout"; pointer_co="$work/case9-pointer-checkout"; cfg="$work/case9-cfg"
  # $co is its own repo, a different origin than the pointer target, with its own,
  # differing CLAUDE.md. banchi is not a claude-settings clone.
  make_checkout "$co" "# unrelated repo content" "https://github.com/someone/banchi.git"
  make_checkout "$pointer_co" "# global content, different"
  mkdir -p "$cfg"
  printf '@%s/CLAUDE.md\n' "$pointer_co" > "$cfg/CLAUDE.md"

  out=$(cd "$co" && CLAUDE_CONFIG_DIR="$cfg" sh "$SESSION_START_SH_DEFAULT" < /dev/null 2>/tmp/c9err)
  rc=$?
  errsize=$(wc -c < /tmp/c9err | tr -d '[:space:]'); rm -f /tmp/c9err
  lines=$(printf '%s\n' "$out" | grep -c 'differ from this checkout')

  if [ $rc -ne 0 ]; then
    bad "$name" "exit $rc"
  elif [ "$errsize" != "0" ]; then
    bad "$name" "wrote to stderr"
  elif [ "$lines" != "0" ]; then
    bad "$name" "unrelated repo wrongly printed a divergence line: $out"
  else
    ok "$name"
  fi
}

case10() {
  name="case10: an unreadable pointer remote stays silent"
  co="$work/case10-checkout"; pointer_co="$work/case10-pointer-notgit"; cfg="$work/case10-cfg"
  make_checkout "$co" "# checkout content"
  # Pointer target exists and has a CLAUDE.md, but is not a git repo at all, so
  # `git remote get-url origin` fails there. The read failure must stay silent, never print.
  mkdir -p "$pointer_co"
  printf '# global content, different\n' > "$pointer_co/CLAUDE.md"
  mkdir -p "$cfg"
  printf '@%s/CLAUDE.md\n' "$pointer_co" > "$cfg/CLAUDE.md"

  out=$(cd "$co" && CLAUDE_CONFIG_DIR="$cfg" sh "$SESSION_START_SH_DEFAULT" < /dev/null 2>/tmp/c10err)
  rc=$?
  errsize=$(wc -c < /tmp/c10err | tr -d '[:space:]'); rm -f /tmp/c10err
  lines=$(printf '%s\n' "$out" | grep -c 'differ from this checkout')

  if [ $rc -ne 0 ]; then
    bad "$name" "exit $rc"
  elif [ "$errsize" != "0" ]; then
    bad "$name" "wrote to stderr"
  elif [ "$lines" != "0" ]; then
    bad "$name" "unreadable remote wrongly printed a divergence line: $out"
  else
    ok "$name"
  fi
}

# ---- land_dir prune cases: local mode removes an entry only for a file that is both ------
# a symlink land_dir made and points at a source file that is now gone. Each case runs
# install.sh (copied into the checkout, local mode, no --cloud) against a real checkout so
# git tracking is never a variable: local mode reads SCRIPT_DIR/CLAUDE.md and
# SCRIPT_DIR/settings.json directly, the same detection case3 exercises, with no git
# requirement on the files under hooks/.
run_local_install() {
  # $1 = checkout dir, $2 = HOME, $3 = CLAUDE_CONFIG_DIR
  ( cd "$1" && env -i PATH="$PATH" HOME="$2" CLAUDE_CONFIG_DIR="$3" bash ./install.sh 2>&1 )
}

prune_case1() {
  name="prune1: source file removed leaves no destination entry"
  if [ "$SYMLINK_CAPABLE" != 1 ]; then
    skip "$name" "$NO_SYMLINK_REASON"
    return
  fi
  h=$(new_home); cfg="$h/.claude-cfg"; co="$work/prune1-checkout"
  make_checkout "$co" "# prune1 content"
  cp "$INSTALL_SH" "$co/install.sh"
  printf '#!/bin/sh\necho hi\n' > "$co/hooks/temp_hook.sh"

  out1=$(run_local_install "$co" "$h" "$cfg"); rc1=$?
  rm -f "$co/hooks/temp_hook.sh"
  out2=$(run_local_install "$co" "$h" "$cfg"); rc2=$?

  if [ $rc1 -ne 0 ] || [ $rc2 -ne 0 ]; then
    bad "$name" "install.sh exited rc1=$rc1 rc2=$rc2: $out1 / $out2"
  elif [ -e "$cfg/hooks/temp_hook.sh" ] || [ -L "$cfg/hooks/temp_hook.sh" ]; then
    bad "$name" "stale entry $cfg/hooks/temp_hook.sh survived the second install"
  else
    ok "$name"
  fi
  rm -rf "$h"
}

prune_case2() {
  name="prune2: hand-placed regular file in config dir survives prune"
  h=$(new_home); cfg="$h/.claude-cfg"; co="$work/prune2-checkout"
  make_checkout "$co" "# prune2 content"
  cp "$INSTALL_SH" "$co/install.sh"
  mkdir -p "$cfg/hooks"
  printf 'a person wrote this by hand\n' > "$cfg/hooks/manual.sh"

  out=$(run_local_install "$co" "$h" "$cfg"); rc=$?
  content=$(cat "$cfg/hooks/manual.sh" 2>/dev/null)

  if [ $rc -ne 0 ]; then
    bad "$name" "install.sh exited $rc: $out"
  elif [ ! -f "$cfg/hooks/manual.sh" ] || [ -L "$cfg/hooks/manual.sh" ]; then
    bad "$name" "manual.sh is gone or was replaced by a symlink"
  elif [ "$content" != "a person wrote this by hand" ]; then
    bad "$name" "manual.sh content changed: $content"
  else
    ok "$name"
  fi
  rm -rf "$h"
}

prune_case3() {
  name="prune3: symlink pointing outside \$SRC/\$sub survives prune"
  if [ "$SYMLINK_CAPABLE" != 1 ]; then
    skip "$name" "$NO_SYMLINK_REASON"
    return
  fi
  h=$(new_home); cfg="$h/.claude-cfg"; co="$work/prune3-checkout"
  make_checkout "$co" "# prune3 content"
  cp "$INSTALL_SH" "$co/install.sh"
  mkdir -p "$cfg/hooks"
  outside_target="$work/prune3-outside-target.sh"
  printf 'not from this checkout\n' > "$outside_target"
  ln -sfn "$outside_target" "$cfg/hooks/external.sh"
  # The pointed-to file then disappears too, so the only thing distinguishing this link
  # from a stale one land_dir made is where it points, not whether that target exists.
  rm -f "$outside_target"

  out=$(run_local_install "$co" "$h" "$cfg"); rc=$?

  if [ $rc -ne 0 ]; then
    bad "$name" "install.sh exited $rc: $out"
  elif [ ! -L "$cfg/hooks/external.sh" ]; then
    bad "$name" "external.sh was removed or replaced"
  elif [ "$(readlink "$cfg/hooks/external.sh")" != "$outside_target" ]; then
    bad "$name" "external.sh target changed"
  else
    ok "$name"
  fi
  rm -rf "$h"
}

prune_case4() {
  name="prune4: a .bak.* file land_dir created survives prune"
  h=$(new_home); cfg="$h/.claude-cfg"; co="$work/prune4-checkout"
  make_checkout "$co" "# prune4 content"
  cp "$INSTALL_SH" "$co/install.sh"
  printf '#!/bin/sh\necho new\n' > "$co/hooks/foo.sh"
  mkdir -p "$cfg/hooks"
  printf 'old hand-placed content\n' > "$cfg/hooks/foo.sh"

  # First install: foo.sh in the config dir is a regular file, not land_dir's own symlink,
  # so land_dir backs it up to foo.sh.bak.<timestamp> before linking. That backup is the
  # thing this case protects.
  out1=$(run_local_install "$co" "$h" "$cfg"); rc1=$?
  bak=$(ls "$cfg/hooks/"foo.sh.bak.* 2>/dev/null | head -n1)

  rm -f "$co/hooks/foo.sh"
  out2=$(run_local_install "$co" "$h" "$cfg"); rc2=$?

  if [ $rc1 -ne 0 ] || [ $rc2 -ne 0 ]; then
    bad "$name" "install.sh exited rc1=$rc1 rc2=$rc2: $out1 / $out2"
  elif [ -z "$bak" ]; then
    bad "$name" "no .bak.* file was created by the first install"
  elif [ ! -f "$bak" ]; then
    bad "$name" "$bak was removed by the second install"
  else
    ok "$name"
  fi
  rm -rf "$h"
}

prune_case5() {
  name="prune5: source file still present keeps its link, and it still resolves"
  if [ "$SYMLINK_CAPABLE" != 1 ]; then
    skip "$name" "$NO_SYMLINK_REASON"
    return
  fi
  h=$(new_home); cfg="$h/.claude-cfg"; co="$work/prune5-checkout"
  make_checkout "$co" "# prune5 content"
  cp "$INSTALL_SH" "$co/install.sh"
  printf '#!/bin/sh\necho keep\n' > "$co/hooks/keep.sh"

  out1=$(run_local_install "$co" "$h" "$cfg"); rc1=$?
  out2=$(run_local_install "$co" "$h" "$cfg"); rc2=$?

  if [ $rc1 -ne 0 ] || [ $rc2 -ne 0 ]; then
    bad "$name" "install.sh exited rc1=$rc1 rc2=$rc2: $out1 / $out2"
  elif [ ! -L "$cfg/hooks/keep.sh" ]; then
    bad "$name" "keep.sh is not a symlink"
  elif [ "$(cat "$cfg/hooks/keep.sh" 2>/dev/null)" != "$(printf '#!/bin/sh\necho keep')" ]; then
    bad "$name" "keep.sh does not resolve to the source content"
  else
    ok "$name"
  fi
  rm -rf "$h"
}

prune_case6() {
  name="prune6: cloud mode does not prune a stale copy (documented, not fixed)"
  h=$(new_home); cfg="$h/.claude-cfg"; co="$work/prune6-checkout"
  make_checkout "$co" "# prune6 content"
  cp "$INSTALL_SH" "$co/install.sh"
  printf '#!/bin/sh\necho cloud\n' > "$co/hooks/cloud_hook.sh"

  out1=$(cd "$co" && env -i PATH="$PATH" HOME="$h" CLAUDE_CONFIG_DIR="$cfg" \
        bash ./install.sh --cloud 2>&1); rc1=$?
  rm -f "$co/hooks/cloud_hook.sh"
  out2=$(cd "$co" && env -i PATH="$PATH" HOME="$h" CLAUDE_CONFIG_DIR="$cfg" \
        bash ./install.sh --cloud 2>&1); rc2=$?

  if [ $rc1 -ne 0 ] || [ $rc2 -ne 0 ]; then
    bad "$name" "install.sh exited rc1=$rc1 rc2=$rc2: $out1 / $out2"
  elif [ ! -f "$cfg/hooks/cloud_hook.sh" ]; then
    bad "$name" "cloud_hook.sh was pruned; cloud mode is documented to leave stale copies in place"
  else
    ok "$name"
  fi
  rm -rf "$h"
}

# ---- Case F1-F5: session_start.sh origin-freshness check ---------------------------------
# These cases use a real local bare repo as "origin", so `git fetch` succeeds with no
# network and the behind-count is exact. They also confirm the fetch never runs, and
# never blocks, when it cannot help: wrong branch, no reachable remote, no git tree,
# no pointer file.

# Ensure a checkout's current branch is named "main", regardless of this machine's
# init.defaultBranch. Cases below depend on the branch name, not on ambient git config.
force_main_branch() {
  ( cd "$1" && git branch -m main >/dev/null 2>&1 )
}

# behind_fixture NAME MARKED: the pointer cases' state under $work/NAME-*. A checkout on main at
# $work/NAME-checkout, its origin a bare repo two commits ahead of it, and a pointer config at
# $work/NAME-cfg that names the checkout. MARKED=1 sets claude-settings.cloudMirror on the checkout,
# as install.sh's clone does. Sets co, cfg and fx_err: fx_err is empty when the fixture built the
# behind-by-2 state. That check compares the checkout and the bare repo directly, never the hook, so
# a fixture failure is never reported as a hook failure.
behind_fixture() {
  co="$work/$1-checkout"; cfg="$work/$1-cfg"; bare="$work/$1-origin.git"
  extra="$work/$1-extra"
  fx_err=""
  git init -q --bare "$bare"
  # A bare repo's HEAD follows init.defaultBranch, which this machine may set to main but a GitHub
  # runner leaves unset, defaulting to master. Force it, as force_main_branch does for checkouts.
  git -C "$bare" symbolic-ref HEAD refs/heads/main
  make_checkout "$co" "# $1 content" "$bare"
  force_main_branch "$co"
  ( cd "$co" && git push -q origin main )
  # Advance origin two commits past the checkout's own main, from a second clone. Captured, not
  # swallowed: a setup step whose exit status nobody reads can silently fail to build the state.
  extra_log=$( { git clone -q "$bare" "$extra" \
      && cd "$extra" && git config user.email t@example.com && git config user.name t \
      && echo a >> extra.txt && git add extra.txt && git commit -q -m extra1 \
      && echo b >> extra.txt && git add extra.txt && git commit -q -m extra2 \
      && git push -q origin main ; } 2>&1 )
  extra_rc=$?
  co_main=$(cd "$co" && git rev-parse main 2>/dev/null)
  bare_main=$(cd "$bare" && git rev-parse main 2>/dev/null)
  behind_built=$(cd "$bare" && git rev-list --count "$co_main..$bare_main" 2>/dev/null)
  if [ "$extra_rc" -ne 0 ]; then
    fx_err="FIXTURE failed to advance origin: $extra_log"
  elif [ "$behind_built" != "2" ]; then
    fx_err="FIXTURE did not build the behind-by-2 state (checkout vs origin main differ by [$behind_built])"
  fi
  if [ "$2" = 1 ]; then git -C "$co" config claude-settings.cloudMirror true; fi
  mkdir -p "$cfg"
  printf '@%s/CLAUDE.md\n' "$co" > "$cfg/CLAUDE.md"
}

# pointer_hook_run REMOTE: runs the hook in $co with the pointer config $cfg. REMOTE is the value of
# CLAUDE_CODE_REMOTE; empty leaves it unset. Sets out, rc and errsize (the stderr byte count).
pointer_hook_run() {
  if [ -n "$1" ]; then
    out=$(cd "$co" && env CLAUDE_CODE_REMOTE="$1" CLAUDE_CONFIG_DIR="$cfg" sh "$SESSION_START_SH_DEFAULT" < /dev/null 2>"$work/pointer-err")
  else
    out=$(cd "$co" && env -u CLAUDE_CODE_REMOTE CLAUDE_CONFIG_DIR="$cfg" sh "$SESSION_START_SH_DEFAULT" < /dev/null 2>"$work/pointer-err")
  fi
  rc=$?
  errsize=$(wc -c < "$work/pointer-err" | tr -d '[:space:]')
}

caseF1() {
  name="caseF1: pointer on main and behind origin/main prints the stale line"
  behind_fixture caseF1 0
  if [ -n "$fx_err" ]; then bad "$name" "$fx_err"; return; fi
  pointer_hook_run ""

  if [ "$rc" -ne 0 ]; then
    bad "$name" "exit $rc"
  elif [ "$errsize" != "0" ]; then
    bad "$name" "wrote to stderr"
  elif ! printf '%s\n' "$out" | grep -q "$co is 2 commits behind origin/main"; then
    bad "$name" "expected stale line naming 2 commits behind, got: $out"
  else
    ok "$name"
  fi
}

# ---- caseF7, caseF8: the freshness check in a cloud session, on a clone install.sh made ----
# A clone install.sh made carries the cloudMirror marker, and the resume refreshes it, so a behind
# count on it is not a warning. An unmarked clone behind origin still warns in a cloud session.
caseF7() {
  name="caseF7: a marked cloud clone behind origin prints no behind or freshness line in a cloud session"
  behind_fixture caseF7 1
  if [ -n "$fx_err" ]; then bad "$name" "$fx_err"; return; fi
  pointer_hook_run true

  if [ "$rc" -ne 0 ]; then
    bad "$name" "exit $rc"
  elif [ "$errsize" != "0" ]; then
    bad "$name" "wrote to stderr"
  elif ! printf '%s\n' "$out" | grep -qF "checkout $co on main,"; then
    bad "$name" "the hook did not run: no checkout line: $out"
  elif printf '%s\n' "$out" | grep -q 'commits behind origin/main\|freshness unknown'; then
    bad "$name" "a marked cloud clone printed a freshness line: $out"
  else
    ok "$name"
  fi
}

caseF8() {
  name="caseF8: an unmarked clone behind origin still warns in a cloud session"
  behind_fixture caseF8 0
  if [ -n "$fx_err" ]; then bad "$name" "$fx_err"; return; fi
  pointer_hook_run true

  if [ "$rc" -ne 0 ]; then
    bad "$name" "exit $rc"
  elif [ "$errsize" != "0" ]; then
    bad "$name" "wrote to stderr"
  elif ! printf '%s\n' "$out" | grep -qF "$co is 2 commits behind origin/main"; then
    bad "$name" "expected stale line naming 2 commits behind, got: $out"
  else
    ok "$name"
  fi
}

caseF2() {
  name="caseF2: pointer on main and up to date with origin/main prints no stale line"
  co="$work/caseF2-checkout"; cfg="$work/caseF2-cfg"; bare="$work/caseF2-origin.git"
  git init -q --bare "$bare"
  git -C "$bare" symbolic-ref HEAD refs/heads/main
  make_checkout "$co" "# caseF2 content" "$bare"
  force_main_branch "$co"
  ( cd "$co" && git push -q origin main )
  mkdir -p "$cfg"
  printf '@%s/CLAUDE.md\n' "$co" > "$cfg/CLAUDE.md"

  out=$(cd "$co" && CLAUDE_CONFIG_DIR="$cfg" sh "$SESSION_START_SH_DEFAULT" < /dev/null 2>/tmp/cF2err)
  rc=$?
  errsize=$(wc -c < /tmp/cF2err | tr -d '[:space:]'); rm -f /tmp/cF2err
  lines=$(printf '%s\n' "$out" | grep -c 'commits behind origin/main')

  if [ $rc -ne 0 ]; then
    bad "$name" "exit $rc"
  elif [ "$errsize" != "0" ]; then
    bad "$name" "wrote to stderr"
  elif [ "$lines" != "0" ]; then
    bad "$name" "unexpected stale line when up to date: $out"
  else
    ok "$name"
  fi
}

caseF3() {
  name="caseF3: pointer on a branch other than main still reports the branch, never fetches"
  co="$work/caseF3-checkout"; cfg="$work/caseF3-cfg"; bare="$work/caseF3-origin.git"
  git init -q --bare "$bare"
  git -C "$bare" symbolic-ref HEAD refs/heads/main
  make_checkout "$co" "# caseF3 content" "$bare"
  ( cd "$co" && git push -q origin HEAD:main && git checkout -q -b feature-branch )
  mkdir -p "$cfg"
  printf '@%s/CLAUDE.md\n' "$co" > "$cfg/CLAUDE.md"

  out=$(cd "$co" && CLAUDE_CONFIG_DIR="$cfg" sh "$SESSION_START_SH_DEFAULT" < /dev/null 2>/tmp/cF3err)
  rc=$?
  errsize=$(wc -c < /tmp/cF3err | tr -d '[:space:]'); rm -f /tmp/cF3err
  branch_lines=$(printf '%s\n' "$out" | grep -c 'is on feature-branch, not main')
  stale_lines=$(printf '%s\n' "$out" | grep -c 'commits behind origin/main')

  if [ $rc -ne 0 ]; then
    bad "$name" "exit $rc"
  elif [ "$errsize" != "0" ]; then
    bad "$name" "wrote to stderr"
  elif [ "$branch_lines" != "1" ]; then
    bad "$name" "expected the existing branch report, got: $out"
  elif [ "$stale_lines" != "0" ]; then
    bad "$name" "freshness check ran on a non-main branch: $out"
  else
    ok "$name"
  fi
}

caseF4() {
  # A failed fetch must never read as "up to date". It must say freshness is
  # unknown, per CLAUDE.md: "report a read that could not run as unknown,
  # never as clear or broken." Silence here would be indistinguishable from
  # a clean check.
  name="caseF4: no reachable origin reports freshness unknown, no error, exit 0"
  co="$work/caseF4-checkout"; cfg="$work/caseF4-cfg"
  # A local path that does not exist: fails the same way a dead network host would
  # (fetch cannot reach it), but fails immediately, so the case stays fast and offline.
  make_checkout "$co" "# caseF4 content" "$work/caseF4-no-such-remote"
  force_main_branch "$co"
  mkdir -p "$cfg"
  printf '@%s/CLAUDE.md\n' "$co" > "$cfg/CLAUDE.md"

  out=$(cd "$co" && CLAUDE_CONFIG_DIR="$cfg" sh "$SESSION_START_SH_DEFAULT" < /dev/null 2>/tmp/cF4err)
  rc=$?
  errsize=$(wc -c < /tmp/cF4err | tr -d '[:space:]'); rm -f /tmp/cF4err
  stale_lines=$(printf '%s\n' "$out" | grep -c 'commits behind origin/main')
  unknown_lines=$(printf '%s\n' "$out" | grep -c 'freshness unknown')

  if [ $rc -ne 0 ]; then
    bad "$name" "exit $rc"
  elif [ "$errsize" != "0" ]; then
    bad "$name" "wrote to stderr"
  elif [ "$stale_lines" != "0" ]; then
    bad "$name" "reported a commit count with no reachable origin: $out"
  elif [ "$unknown_lines" != "1" ]; then
    bad "$name" "expected exactly 1 freshness-unknown line, got $unknown_lines: $out"
  else
    ok "$name"
  fi
}

caseF6() {
  # Forces the other failure shape: the fetch is reachable but does not land
  # inside the timeout, so it gets killed. This must report unknown too, not
  # silence and not a stale count read off a ref the fetch never updated.
  # CLAUDE_SETTINGS_FETCH_TIMEOUT=0 makes the kill race the fetch instead of
  # waiting the full 2 seconds, and the origin's upload-pack is wrapped in a
  # real sleep so the fetch cannot win that race.
  name="caseF6: a fetch killed by the timeout reports freshness unknown, not silence"
  co="$work/caseF6-checkout"; cfg="$work/caseF6-cfg"; bare="$work/caseF6-origin.git"
  git init -q --bare "$bare"
  git -C "$bare" symbolic-ref HEAD refs/heads/main
  make_checkout "$co" "# caseF6 content" "$bare"
  force_main_branch "$co"
  ( cd "$co" && git push -q origin main )
  slow_helper="$work/caseF6-slow-upload.sh"
  cat > "$slow_helper" <<EOF
#!/bin/sh
sleep 5
exec git-upload-pack "\$1"
EOF
  chmod +x "$slow_helper"
  git config -f "$co/.git/config" remote.origin.url "ext::sh $slow_helper $bare"
  git config -f "$co/.git/config" protocol.ext.allow always
  mkdir -p "$cfg"
  printf '@%s/CLAUDE.md\n' "$co" > "$cfg/CLAUDE.md"

  out=$(cd "$co" && CLAUDE_CONFIG_DIR="$cfg" CLAUDE_SETTINGS_FETCH_TIMEOUT=0 \
        sh "$SESSION_START_SH_DEFAULT" < /dev/null 2>/tmp/cF6err)
  rc=$?
  errsize=$(wc -c < /tmp/cF6err | tr -d '[:space:]'); rm -f /tmp/cF6err
  stale_lines=$(printf '%s\n' "$out" | grep -c 'commits behind origin/main')
  unknown_lines=$(printf '%s\n' "$out" | grep -c 'freshness unknown')

  if [ $rc -ne 0 ]; then
    bad "$name" "exit $rc"
  elif [ "$errsize" != "0" ]; then
    bad "$name" "wrote to stderr"
  elif [ "$stale_lines" != "0" ]; then
    bad "$name" "reported a commit count off a fetch that was killed: $out"
  elif [ "$unknown_lines" != "1" ]; then
    bad "$name" "expected exactly 1 freshness-unknown line, got $unknown_lines: $out"
  else
    ok "$name"
  fi
}

# ---- skills case: a whole skill directory lands as one symlink, a pre-existing skill this
# repo does not ship is left alone. A per-file loop (`for f in .../skills/*; do [ -f "$f" ] ||
# continue`) skips every directory entry, so skills/fresh-prose/ never lands: this case pins
# that.
skills_case1() {
  name="skills1: a shipped skill lands as one whole-directory symlink, a person's own skill is untouched"
  if [ "$SYMLINK_CAPABLE" != 1 ]; then
    skip "$name" "$NO_SYMLINK_REASON"
    return
  fi
  h=$(new_home); cfg="$h/.claude-cfg"; co="$work/skills1-checkout"
  make_checkout "$co" "# skills1 content"
  cp "$INSTALL_SH" "$co/install.sh"
  mkdir -p "$co/skills/fresh-prose"
  printf '%s\n' "---" "name: fresh-prose" "---" "shipped skill" > "$co/skills/fresh-prose/SKILL.md"
  mkdir -p "$cfg/skills/my-own"
  printf 'a person wrote this skill by hand\n' > "$cfg/skills/my-own/SKILL.md"

  out=$(run_local_install "$co" "$h" "$cfg"); rc=$?
  own_content=$(cat "$cfg/skills/my-own/SKILL.md" 2>/dev/null)

  if [ $rc -ne 0 ]; then
    bad "$name" "install.sh exited $rc: $out"
  elif [ ! -f "$cfg/skills/fresh-prose/SKILL.md" ]; then
    bad "$name" "$cfg/skills/fresh-prose/SKILL.md does not exist after install"
  elif [ ! -L "$cfg/skills/fresh-prose" ]; then
    bad "$name" "$cfg/skills/fresh-prose is not a whole-directory symlink"
  elif [ "$(readlink "$cfg/skills/fresh-prose")" != "$co/skills/fresh-prose" ]; then
    bad "$name" "$cfg/skills/fresh-prose does not link to $co/skills/fresh-prose"
  elif [ ! -f "$cfg/skills/my-own/SKILL.md" ] || [ -L "$cfg/skills/my-own" ]; then
    bad "$name" "my-own (not shipped by this repo) was moved, linked, or removed"
  elif [ "$own_content" != "a person wrote this skill by hand" ]; then
    bad "$name" "my-own/SKILL.md content changed: $own_content"
  else
    ok "$name"
  fi
  rm -rf "$h"
}

# ---- skills case, cloud mode: an existing real directory is backed up, never rm -rf'd ------
skills_case2() {
  name="skills2: cloud mode backs up a pre-existing real skill directory before overwriting it"
  h=$(new_home); cfg="$h/.claude-cfg"; co="$work/skills2-checkout"
  make_checkout "$co" "# skills2 content"
  cp "$INSTALL_SH" "$co/install.sh"
  mkdir -p "$co/skills/fresh-prose"
  printf 'new content\n' > "$co/skills/fresh-prose/SKILL.md"
  mkdir -p "$cfg/skills/fresh-prose"
  printf 'old content a person may have edited\n' > "$cfg/skills/fresh-prose/SKILL.md"
  mkdir -p "$cfg/skills/my-own"
  printf 'a person wrote this skill by hand\n' > "$cfg/skills/my-own/SKILL.md"

  out=$(cd "$co" && env -i PATH="$PATH" HOME="$h" CLAUDE_CONFIG_DIR="$cfg" \
        bash ./install.sh --cloud 2>&1); rc=$?
  bak=$(ls -d "$cfg/backups/skills/"fresh-prose.* 2>/dev/null | head -n1)
  own_content=$(cat "$cfg/skills/my-own/SKILL.md" 2>/dev/null)

  if [ $rc -ne 0 ]; then
    bad "$name" "install.sh exited $rc: $out"
  elif [ -z "$bak" ]; then
    bad "$name" "no backup under backups/skills; the old content was dropped"
  elif [ "$(cat "$bak/SKILL.md" 2>/dev/null)" != "old content a person may have edited" ]; then
    bad "$name" "backed-up directory does not hold the pre-existing content"
  elif [ "$(cat "$cfg/skills/fresh-prose/SKILL.md" 2>/dev/null)" != "new content" ]; then
    bad "$name" "fresh-prose was not refreshed with the new content"
  elif [ ! -f "$cfg/skills/my-own/SKILL.md" ]; then
    bad "$name" "my-own (not shipped by this repo) was removed"
  elif [ "$own_content" != "a person wrote this skill by hand" ]; then
    bad "$name" "my-own/SKILL.md content changed: $own_content"
  else
    ok "$name"
  fi
  rm -rf "$h"
}

# ---- cloud settings: the refresh hook is added after the repo's own SessionStart hooks ------
# The expected list is read from the repo's settings.json, so a new SessionStart hook needs no edit here.
cloud_settings1() {
  name="cloud_settings1: cloud settings.json keeps every repo SessionStart hook, then adds the refresh hook"
  if ! command -v jq >/dev/null 2>&1; then skip "$name" "jq not found"; return; fi
  h=$(new_home); cfg="$h/.claude-cfg"; co="$work/cloud_settings1-checkout"
  make_checkout "$co" "# cloud_settings1 content"
  cp "$INSTALL_SH" "$co/install.sh"
  cp "$REPO_ROOT/settings.json" "$co/settings.json"
  ( cd "$co" && git add -A && git commit -q -m settings )

  out=$(cd "$co" && env -i PATH="$PATH" HOME="$h" CLAUDE_CONFIG_DIR="$cfg" \
        bash ./install.sh --cloud 2>&1); rc=$?
  want=$(jq -c '.hooks.SessionStart' "$REPO_ROOT/settings.json")
  n=$(jq '.hooks.SessionStart | length' "$REPO_ROOT/settings.json")
  got=$(jq -c --argjson n "$n" '.hooks.SessionStart[:$n]' "$cfg/settings.json" 2>/dev/null)
  tail_cmd=$(jq -r --argjson n "$n" '.hooks.SessionStart[$n:] | map(.hooks[].command) | join("\n")' \
        "$cfg/settings.json" 2>/dev/null)
  extra=$(jq --argjson n "$n" '.hooks.SessionStart | length - $n' "$cfg/settings.json" 2>/dev/null)

  if [ $rc -ne 0 ]; then
    bad "$name" "install.sh exited $rc: $out"
  elif [ "$got" != "$want" ]; then
    bad "$name" "the first $n SessionStart entries differ from the repo settings.json; the cloud install dropped or changed a repo hook"
  elif [ "$extra" != 1 ]; then
    bad "$name" "expected one entry after the repo hooks, found ${extra:-none}"
  else
    case "$tail_cmd" in
      "curl -fsSL "*"/install.sh | bash -s -- --cloud") ok "$name" ;;
      *) bad "$name" "the last SessionStart entry is not the refresh hook: $tail_cmd" ;;
    esac
  fi
  rm -rf "$h"
}

# ---- skills backups, cloud mode: a repeat run replaces its own copy, and a needed backup lands outside skills/ ----
# Each cloud run installs again, so a backup inside skills/ piled up and loaded as one more skill each.
skills_bak_setup() {
  h=$(new_home); cfg="$h/.claude-cfg"; co="$work/$1-checkout"
  make_checkout "$co" "# $1 content"
  cp "$INSTALL_SH" "$co/install.sh"
  mkdir -p "$co/skills/fresh-prose"
  printf 'v1\n' > "$co/skills/fresh-prose/SKILL.md"
}
skills_bak_run() {
  out=$(cd "$co" && env -i PATH="$PATH" HOME="$h" CLAUDE_CONFIG_DIR="$cfg" \
        bash ./install.sh --cloud 2>&1); rc=$?
}

skills_bak1() {
  name="skills_bak1: two cloud runs leave no backup anywhere"
  skills_bak_setup skills_bak1
  skills_bak_run; skills_bak_run
  stray=$(find "$cfg" -name '*.bak.*' ! -name 'settings.json.bak.*' ! -name 'CLAUDE.md.bak.*' 2>/dev/null | head -n3)
  if [ $rc -ne 0 ]; then bad "$name" "install.sh exited $rc: $out"
  elif has_bak "$cfg/skills"; then bad "$name" "skills/ holds a .bak.* entry: $(ls "$cfg/skills")"
  elif [ -n "$stray" ] || [ -n "$(ls "$cfg/backups/skills" 2>/dev/null)" ]; then bad "$name" "a backup was made: $stray $(ls "$cfg/backups/skills" 2>/dev/null)"
  elif [ "$(cat "$cfg/skills/fresh-prose/SKILL.md")" != "v1" ]; then bad "$name" "skill content wrong"
  else ok "$name"; fi
  rm -rf "$h"
}

skills_bak2() {
  name="skills_bak2: a hand-edited skill copy is backed up under backups/, not in skills/"
  skills_bak_setup skills_bak2
  skills_bak_run
  printf 'hand edit\n' > "$cfg/skills/fresh-prose/SKILL.md"
  skills_bak_run
  bak=$(ls -d "$cfg/backups/skills/"fresh-prose.* 2>/dev/null | head -n1)
  if [ $rc -ne 0 ]; then bad "$name" "install.sh exited $rc: $out"
  elif [ -z "$bak" ]; then bad "$name" "no backup under $cfg/backups/skills; skills/ holds: $(ls "$cfg/skills")"
  elif [ "$(cat "$bak/SKILL.md" 2>/dev/null)" != "hand edit" ]; then bad "$name" "backup lost the hand edit"
  elif has_bak "$cfg/skills"; then bad "$name" "skills/ holds a .bak.* entry"
  elif [ "$(cat "$cfg/skills/fresh-prose/SKILL.md")" != "v1" ]; then bad "$name" "skill was not refreshed"
  else ok "$name"; fi
  rm -rf "$h"
}

skills_bak3() {
  name="skills_bak3: a source change between cloud runs makes no backup"
  skills_bak_setup skills_bak3
  skills_bak_run
  printf 'v2\n' > "$co/skills/fresh-prose/SKILL.md"
  skills_bak_run
  if [ $rc -ne 0 ]; then bad "$name" "install.sh exited $rc: $out"
  elif has_bak "$cfg/skills"; then bad "$name" "skills/ holds a .bak.* entry: $(ls "$cfg/skills")"
  elif [ -n "$(ls "$cfg/backups/skills" 2>/dev/null)" ]; then bad "$name" "a backup was made: $(ls "$cfg/backups/skills")"
  elif [ "$(cat "$cfg/skills/fresh-prose/SKILL.md")" != "v2" ]; then bad "$name" "skill was not refreshed to v2"
  else ok "$name"; fi
  rm -rf "$h"
}

skills_bak4() {
  name="skills_bak4: an old skills/x.bak.* is moved to backups/skills, content kept"
  skills_bak_setup skills_bak4
  mkdir -p "$cfg/skills/fresh-prose.bak.20260101000000"
  printf 'old backup\n' > "$cfg/skills/fresh-prose.bak.20260101000000/SKILL.md"
  skills_bak_run
  moved=$(ls -d "$cfg/backups/skills/"fresh-prose.bak.20260101000000 2>/dev/null | head -n1)
  if [ $rc -ne 0 ]; then bad "$name" "install.sh exited $rc: $out"
  elif has_bak "$cfg/skills"; then bad "$name" "skills/ still holds a .bak.* entry: $(ls "$cfg/skills")"
  elif [ -z "$moved" ] || [ "$(cat "$moved/SKILL.md" 2>/dev/null)" != "old backup" ]; then bad "$name" "old backup not found intact under backups/skills"
  else ok "$name"; fi
  rm -rf "$h"
}

skills_bak5() {
  name="skills_bak5: a copy identical to the source, with no record, is replaced with no backup"
  skills_bak_setup skills_bak5
  mkdir -p "$cfg/skills/fresh-prose"
  printf 'v1\n' > "$cfg/skills/fresh-prose/SKILL.md"
  skills_bak_run
  if [ $rc -ne 0 ]; then bad "$name" "install.sh exited $rc: $out"
  elif has_bak "$cfg/skills"; then bad "$name" "skills/ holds a .bak.* entry"
  elif [ -n "$(ls "$cfg/backups/skills" 2>/dev/null)" ]; then bad "$name" "a backup was made: $(ls "$cfg/backups/skills")"
  else ok "$name"; fi
  rm -rf "$h"
}

skills_bak6() {
  name="skills_bak6: a skill folder named x.bak.v2 stays in skills/"
  skills_bak_setup skills_bak6
  mkdir -p "$cfg/skills/foo.bak.v2"
  printf 'mine\n' > "$cfg/skills/foo.bak.v2/SKILL.md"
  skills_bak_run
  if [ $rc -ne 0 ]; then bad "$name" "install.sh exited $rc: $out"
  elif [ "$(cat "$cfg/skills/foo.bak.v2/SKILL.md" 2>/dev/null)" != "mine" ]; then bad "$name" "foo.bak.v2 was moved out of skills/"
  else ok "$name"; fi
  rm -rf "$h"
}

# ---- copy-mode case: a fake `ln` that copies instead of linking must not pile up .bak entries
# across repeated runs. Git Bash's `ln -sfn` on a Windows account without symlink rights makes a
# real copy, so the next run sees a real file/dir where land_dir()/land_skills_dir() expect a
# symlink, and backs it up before copying again. A stub `ln` first on PATH that always copies
# reproduces this without a no-symlink-rights host.
# settings.json is the exception to D: copy-mode-overwrites-no-backup: a repeat run backs up a plain
# settings.json, and only the newest settings.json.bak.* stays. Skill and agent copies still leave
# no .bak entries.
make_fake_ln_bin() {
  stub_bin="$1"
  mkdir -p "$stub_bin"
  cat > "$stub_bin/ln" <<'EOF'
#!/bin/sh
# usage: ln -sfn <target> <linkname>  (flags ignored; copies instead of linking)
last1=""; last2=""
for a in "$@"; do
  case "$a" in
    -*) continue ;;
  esac
  last1="$last2"
  last2="$a"
done
target="$last1"; dest="$last2"
[ -n "$dest" ] || exit 1
rm -rf "$dest"
cp -R "$target" "$dest"
EOF
  chmod +x "$stub_bin/ln"
}

copymode_case1() {
  name="copymode1: two runs under a copying \`ln\` leave no skill/agent .bak, one settings.json.bak holding run 1, and land current content"
  h=$(new_home); cfg="$h/.claude-cfg"; co="$work/copymode1-checkout"
  make_checkout "$co" "# copymode1 content"
  cp "$INSTALL_SH" "$co/install.sh"
  mkdir -p "$co/skills/sample-skill"
  printf 'v1\n' > "$co/skills/sample-skill/SKILL.md"
  printf 'agent v1\n' > "$co/agents/sample.md"

  fake_bin="$work/copymode1-bin"
  make_fake_ln_bin "$fake_bin"
  run1=$(cd "$co" && env -i PATH="$fake_bin:$PATH" HOME="$h" CLAUDE_CONFIG_DIR="$cfg" \
         bash ./install.sh 2>&1); rc1=$?

  # Change a skill's source content, and the settings.json source, between runs, the way a
  # real `git pull` would. The settings.json copy run 1 made (content '{}') is what run 2 backs up.
  printf 'v2\n' > "$co/skills/sample-skill/SKILL.md"
  printf '{"v": 2}\n' > "$co/settings.json"

  run2=$(cd "$co" && env -i PATH="$fake_bin:$PATH" HOME="$h" CLAUDE_CONFIG_DIR="$cfg" \
         bash ./install.sh 2>&1); rc2=$?

  baks=$(find "$cfg" -name '*.bak.*' ! -name 'settings.json.bak.*' 2>/dev/null)
  sbak_count=$(ls "$cfg"/settings.json.bak.* 2>/dev/null | wc -l | tr -d ' ')
  sbak=$(ls "$cfg"/settings.json.bak.* 2>/dev/null | head -n1)
  sbak_got=$(cat "$sbak" 2>/dev/null)
  settings_got=$(cat "$cfg/settings.json" 2>/dev/null)
  skill_got=$(cat "$cfg/skills/sample-skill/SKILL.md" 2>/dev/null)
  agent_got=$(cat "$cfg/agents/sample.md" 2>/dev/null)
  agent_src=$(cat "$co/agents/sample.md" 2>/dev/null)

  if [ $rc1 -ne 0 ]; then
    bad "$name" "run 1 exited $rc1: $run1"
  elif [ $rc2 -ne 0 ]; then
    bad "$name" "run 2 exited $rc2: $run2"
  elif [ -n "$baks" ]; then
    bad "$name" "run 2 left skill/agent .bak entries under $cfg:$baks"
  elif [ "$sbak_count" != 1 ]; then
    bad "$name" "expected one settings.json.bak.* after run 2, found $sbak_count"
  elif [ "$sbak_got" != '{}' ]; then
    bad "$name" "settings.json.bak.* holds [$sbak_got], expected the run 1 content [{}]"
  elif [ "$settings_got" != '{"v": 2}' ]; then
    bad "$name" "settings.json holds [$settings_got] after run 2, source changed to {\"v\": 2}"
  elif [ ! -f "$cfg/skills/sample-skill/SKILL.md" ]; then
    bad "$name" "$cfg/skills/sample-skill/SKILL.md does not exist after run 2"
  elif [ "$skill_got" != "v2" ]; then
    bad "$name" "sample-skill/SKILL.md holds [$skill_got] after run 2, source changed to v2"
  elif [ "$agent_got" != "$agent_src" ]; then
    bad "$name" "agents/sample.md [$agent_got] does not match source [$agent_src] after run 2"
  else
    ok "$name"
  fi
  rm -rf "$h"
}

# ---- backup cases: a person's own CLAUDE.md or settings.json is never lost ------------------
backup_case1() {
  name="backup1: a pre-existing CLAUDE.md with its own content is backed up before the pointer replaces it"
  h=$(new_home); cfg="$h/.claude-cfg"; co="$work/backup1-checkout"
  make_checkout "$co" "# backup1 content"
  cp "$INSTALL_SH" "$co/install.sh"
  mkdir -p "$cfg"
  printf 'my own notes\n' > "$cfg/CLAUDE.md"

  out=$(run_local_install "$co" "$h" "$cfg"); rc=$?
  bak=$(ls "$cfg"/CLAUDE.md.bak.* 2>/dev/null | head -n1)

  if [ $rc -ne 0 ]; then
    bad "$name" "install.sh exited $rc: $out"
  elif [ -z "$bak" ]; then
    bad "$name" "no CLAUDE.md.bak.* file; the person's own CLAUDE.md was overwritten"
  elif [ "$(cat "$bak")" != "my own notes" ]; then
    bad "$name" "the backup does not hold the original content"
  elif grep -q "my own notes" "$cfg/CLAUDE.md"; then
    bad "$name" "CLAUDE.md still holds the old content, no pointer written"
  else
    ok "$name"
  fi
  rm -rf "$h"
}

backup_case2() {
  name="backup2: a pre-existing real settings.json is moved to settings.json.orig on the first install"
  if [ "$SYMLINK_CAPABLE" != 1 ]; then
    skip "$name" "$NO_SYMLINK_REASON"
    return
  fi
  h=$(new_home); cfg="$h/.claude-cfg"; co="$work/backup2-checkout"
  make_checkout "$co" "# backup2 content"
  cp "$INSTALL_SH" "$co/install.sh"
  mkdir -p "$cfg"
  printf '{"mine": true}\n' > "$cfg/settings.json"

  out=$(run_local_install "$co" "$h" "$cfg"); rc=$?
  orig=$(cat "$cfg/settings.json.orig" 2>/dev/null)
  bak_count=$(ls "$cfg"/settings.json.bak.* 2>/dev/null | wc -l | tr -d ' ')

  if [ $rc -ne 0 ]; then
    bad "$name" "install.sh exited $rc: $out"
  elif [ "$orig" != '{"mine": true}' ]; then
    bad "$name" "no settings.json.orig holding the person's own settings.json: [$orig]"
  elif [ "$bak_count" != 0 ]; then
    bad "$name" "the first install wrote a settings.json.bak.*; the first-ever settings.json belongs in settings.json.orig"
  elif [ ! -L "$cfg/settings.json" ]; then
    bad "$name" "settings.json is not a symlink after install"
  else
    ok "$name"
  fi
  rm -rf "$h"
}

# ---- settings.json repeat-run cases -------------------------------------------------------------
# On a repeat local install (the first-run marker exists), a plain settings.json is backed up
# before the link replaces it, and only the newest settings.json.bak.* is kept. Backups of
# other files are never touched. A settings.json that is already the link gets no backup.
settings_repeat_case1() {
  name="settings_repeat1: repeat run backs up a plain settings.json, then links it"
  if [ "$SYMLINK_CAPABLE" != 1 ]; then
    skip "$name" "$NO_SYMLINK_REASON"
    return
  fi
  h=$(new_home); cfg="$h/.claude-cfg"; co="$work/settings_repeat1-checkout"
  make_checkout "$co" "# settings_repeat1 content"
  cp "$INSTALL_SH" "$co/install.sh"

  out1=$(run_local_install "$co" "$h" "$cfg"); rc1=$?
  rm -f "$cfg/settings.json"
  printf '{"old": 1}\n' > "$cfg/settings.json"
  out2=$(run_local_install "$co" "$h" "$cfg"); rc2=$?
  bak=$(ls "$cfg"/settings.json.bak.* 2>/dev/null | head -n1)
  bak_count=$(ls "$cfg"/settings.json.bak.* 2>/dev/null | wc -l | tr -d ' ')

  if [ $rc1 -ne 0 ] || [ $rc2 -ne 0 ]; then
    bad "$name" "install.sh exited rc1=$rc1 rc2=$rc2: $out1 / $out2"
  elif [ ! -e "$cfg/.claude-settings-installed" ]; then
    bad "$name" "setup error: the first-run marker is missing, so run 2 was not a repeat run"
  elif [ "$bak_count" != 1 ]; then
    bad "$name" "expected one settings.json.bak.* after the repeat run, found $bak_count"
  elif [ "$(cat "$bak")" != '{"old": 1}' ]; then
    bad "$name" "the backup holds [$(cat "$bak")], expected the old settings.json content"
  elif [ ! -L "$cfg/settings.json" ]; then
    bad "$name" "settings.json is not a symlink after the repeat run"
  elif [ "$(cat "$cfg/settings.json")" != '{}' ]; then
    bad "$name" "settings.json does not resolve to the checkout's settings.json"
  else
    ok "$name"
  fi
  rm -rf "$h"
}

settings_repeat_case2() {
  name="settings_repeat2: repeat run keeps only the newest settings.json.bak.*"
  if [ "$SYMLINK_CAPABLE" != 1 ]; then
    skip "$name" "$NO_SYMLINK_REASON"
    return
  fi
  h=$(new_home); cfg="$h/.claude-cfg"; co="$work/settings_repeat2-checkout"
  make_checkout "$co" "# settings_repeat2 content"
  cp "$INSTALL_SH" "$co/install.sh"

  out1=$(run_local_install "$co" "$h" "$cfg"); rc1=$?
  printf '{"older": "first"}\n' > "$cfg/settings.json.bak.20260101000000.1001"
  printf '{"older": "second"}\n' > "$cfg/settings.json.bak.20260301000000.1002"
  rm -f "$cfg/settings.json"
  printf '{"old": 2}\n' > "$cfg/settings.json"
  out2=$(run_local_install "$co" "$h" "$cfg"); rc2=$?
  newest=$(ls "$cfg"/settings.json.bak.* 2>/dev/null | head -n1)
  bak_count=$(ls "$cfg"/settings.json.bak.* 2>/dev/null | wc -l | tr -d ' ')

  if [ $rc1 -ne 0 ] || [ $rc2 -ne 0 ]; then
    bad "$name" "install.sh exited rc1=$rc1 rc2=$rc2: $out1 / $out2"
  elif [ "$bak_count" != 1 ]; then
    bad "$name" "expected one settings.json.bak.* after the repeat run, found $bak_count"
  elif [ -e "$cfg/settings.json.bak.20260101000000.1001" ] || [ -e "$cfg/settings.json.bak.20260301000000.1002" ]; then
    bad "$name" "an older settings.json.bak.* survived the repeat run"
  elif [ "$(cat "$newest")" != '{"old": 2}' ]; then
    bad "$name" "the newest backup holds [$(cat "$newest")], expected the content run 2 replaced"
  else
    ok "$name"
  fi
  rm -rf "$h"
}

settings_repeat_case3() {
  name="settings_repeat3: the settings.json prune leaves CLAUDE.md.bak.* and other .bak files alone"
  if [ "$SYMLINK_CAPABLE" != 1 ]; then
    skip "$name" "$NO_SYMLINK_REASON"
    return
  fi
  h=$(new_home); cfg="$h/.claude-cfg"; co="$work/settings_repeat3-checkout"
  make_checkout "$co" "# settings_repeat3 content"
  cp "$INSTALL_SH" "$co/install.sh"

  out1=$(run_local_install "$co" "$h" "$cfg"); rc1=$?
  printf 'old claude backup\n' > "$cfg/CLAUDE.md.bak.20260101000000"
  mkdir -p "$cfg/hooks"
  printf 'old hook backup\n' > "$cfg/hooks/manual.sh.bak.20260101000000"
  rm -f "$cfg/settings.json"
  printf '{"plain": 3}\n' > "$cfg/settings.json"
  out2=$(run_local_install "$co" "$h" "$cfg"); rc2=$?
  claude_bak=$(cat "$cfg/CLAUDE.md.bak.20260101000000" 2>/dev/null)
  hook_bak=$(cat "$cfg/hooks/manual.sh.bak.20260101000000" 2>/dev/null)
  bak=$(ls "$cfg"/settings.json.bak.* 2>/dev/null | head -n1)
  bak_count=$(ls "$cfg"/settings.json.bak.* 2>/dev/null | wc -l | tr -d ' ')

  if [ $rc1 -ne 0 ] || [ $rc2 -ne 0 ]; then
    bad "$name" "install.sh exited rc1=$rc1 rc2=$rc2: $out1 / $out2"
  elif [ "$claude_bak" != 'old claude backup' ]; then
    bad "$name" "CLAUDE.md.bak.20260101000000 was removed or changed: [$claude_bak]"
  elif [ "$hook_bak" != 'old hook backup' ]; then
    bad "$name" "hooks/manual.sh.bak.20260101000000 was removed or changed: [$hook_bak]"
  elif [ "$bak_count" != 1 ]; then
    bad "$name" "expected one settings.json.bak.* after the repeat run, found $bak_count"
  elif [ "$(cat "$bak")" != '{"plain": 3}' ]; then
    bad "$name" "the settings.json backup holds [$(cat "$bak")], expected the plain settings.json"
  else
    ok "$name"
  fi
  rm -rf "$h"
}

settings_repeat_case4() {
  name="settings_repeat4: settings.json already linked gets no backup and old settings.json.bak.* stay"
  if [ "$SYMLINK_CAPABLE" != 1 ]; then
    skip "$name" "$NO_SYMLINK_REASON"
    return
  fi
  h=$(new_home); cfg="$h/.claude-cfg"; co="$work/settings_repeat4-checkout"
  make_checkout "$co" "# settings_repeat4 content"
  cp "$INSTALL_SH" "$co/install.sh"

  out1=$(run_local_install "$co" "$h" "$cfg"); rc1=$?
  printf '{"older": "first"}\n' > "$cfg/settings.json.bak.20260101000000.1001"
  printf '{"older": "second"}\n' > "$cfg/settings.json.bak.20260301000000.1002"
  before=$(ls "$cfg"/settings.json.bak.* 2>/dev/null | sort)
  out2=$(run_local_install "$co" "$h" "$cfg"); rc2=$?
  after=$(ls "$cfg"/settings.json.bak.* 2>/dev/null | sort)

  if [ $rc1 -ne 0 ] || [ $rc2 -ne 0 ]; then
    bad "$name" "install.sh exited rc1=$rc1 rc2=$rc2: $out1 / $out2"
  elif [ -z "$before" ] || [ "$after" != "$before" ]; then
    bad "$name" "settings.json.bak.* set changed on a run where settings.json was already linked: before [$before] after [$after]"
  elif [ "$(cat "$cfg/settings.json.bak.20260101000000.1001")" != '{"older": "first"}' ] || \
       [ "$(cat "$cfg/settings.json.bak.20260301000000.1002")" != '{"older": "second"}' ]; then
    bad "$name" "an old settings.json.bak.* changed content"
  elif [ ! -L "$cfg/settings.json" ]; then
    bad "$name" "settings.json is not a symlink after the repeat run"
  else
    ok "$name"
  fi
  rm -rf "$h"
}

# ---- settings.json first-ever, clock and move cases ---------------------------------------------
# The first local install moves a plain settings.json to settings.json.orig. Repeat installs back
# it up to settings.json.bak.<stamp> and keep only the newest. A later install never prunes or
# overwrites settings.json.orig. The stub bin below fixes the clock, so two runs share a stamp,
# logs each settings.json.bak.* move, and can make that move fail.
REAL_MV=$(command -v mv)
REAL_DATE=$(command -v date)

# $1 = stub bin dir, $2 = log file for settings.json.bak.* destinations, $3 = ok or fail.
# ln copies (copy mode: a repeat run finds a plain settings.json). date returns a fixed stamp.
# mv logs its last argument when the source is a settings.json.bak.* path, and exits 1 in fail
# mode. Every other mv call goes to the real mv.
make_settings_bin() {
  bin="$1"; log="$2"; mode="$3"
  make_fake_ln_bin "$bin"
  cat > "$bin/date" <<EOF
#!/bin/sh
case "\$*" in
  "+%Y%m%d%H%M%S") echo 20260301120000 ;;
  *) exec "$REAL_DATE" "\$@" ;;
esac
EOF
  cat > "$bin/mv" <<EOF
#!/bin/sh
case "\$*" in
  *settings.json.bak.*)
    for a in "\$@"; do d="\$a"; done
    printf '%s\n' "\$d" >> "$log"
    [ "$mode" = fail ] && exit 1
    ;;
esac
exec "$REAL_MV" "\$@"
EOF
  chmod +x "$bin/date" "$bin/mv"
}

# $1 = checkout, $2 = HOME, $3 = CLAUDE_CONFIG_DIR, $4 = stub bin dir placed first on PATH.
run_with_bin() {
  ( cd "$1" && env -i PATH="$4:$PATH" HOME="$2" CLAUDE_CONFIG_DIR="$3" bash ./install.sh 2>&1 )
}

orig_case1() {
  name="orig1: copy-mode runs 2 and 3 leave the user's first settings.json in .orig and one settings.json.bak.*"
  h=$(new_home); cfg="$h/.claude-cfg"; co="$work/orig1-checkout"
  make_checkout "$co" "# orig1 content"
  cp "$INSTALL_SH" "$co/install.sh"
  log="$work/orig1-mv.log"; : > "$log"
  make_settings_bin "$work/orig1-bin" "$log" ok
  mkdir -p "$cfg"
  printf '{"mine": 1}\n' > "$cfg/settings.json"

  out1=$(run_with_bin "$co" "$h" "$cfg" "$work/orig1-bin"); rc1=$?
  out2=$(run_with_bin "$co" "$h" "$cfg" "$work/orig1-bin"); rc2=$?
  out3=$(run_with_bin "$co" "$h" "$cfg" "$work/orig1-bin"); rc3=$?
  orig=$(cat "$cfg/settings.json.orig" 2>/dev/null)
  bak_count=$(ls "$cfg"/settings.json.bak.* 2>/dev/null | wc -l | tr -d ' ')

  if [ $rc1 -ne 0 ] || [ $rc2 -ne 0 ] || [ $rc3 -ne 0 ]; then
    bad "$name" "install.sh exited rc1=$rc1 rc2=$rc2 rc3=$rc3: $out1 / $out2 / $out3"
  elif [ "$orig" != '{"mine": 1}' ]; then
    bad "$name" "settings.json.orig holds [$orig], expected the user's own settings.json"
  elif [ "$bak_count" != 1 ]; then
    bad "$name" "expected one settings.json.bak.* after runs 2 and 3, found $bak_count"
  else
    ok "$name"
  fi
  rm -rf "$h"
}

orig_case2() {
  name="orig2: a repeat run never prunes or overwrites an existing settings.json.orig"
  h=$(new_home); cfg="$h/.claude-cfg"; co="$work/orig2-checkout"
  make_checkout "$co" "# orig2 content"
  cp "$INSTALL_SH" "$co/install.sh"
  log="$work/orig2-mv.log"; : > "$log"
  make_settings_bin "$work/orig2-bin" "$log" ok

  out1=$(run_with_bin "$co" "$h" "$cfg" "$work/orig2-bin"); rc1=$?
  printf '{"orig": "kept"}\n' > "$cfg/settings.json.orig"
  printf '{"older": "bak"}\n' > "$cfg/settings.json.bak.20260101000000.1001"
  printf '{"plain": 2}\n' > "$cfg/settings.json"
  out2=$(run_with_bin "$co" "$h" "$cfg" "$work/orig2-bin"); rc2=$?
  orig=$(cat "$cfg/settings.json.orig" 2>/dev/null)
  bak_count=$(ls "$cfg"/settings.json.bak.* 2>/dev/null | wc -l | tr -d ' ')

  if [ $rc1 -ne 0 ] || [ $rc2 -ne 0 ]; then
    bad "$name" "install.sh exited rc1=$rc1 rc2=$rc2: $out1 / $out2"
  elif [ "$orig" != '{"orig": "kept"}' ]; then
    bad "$name" "settings.json.orig changed to [$orig]"
  elif [ "$bak_count" != 1 ]; then
    bad "$name" "expected one settings.json.bak.* after the repeat run, found $bak_count"
  else
    ok "$name"
  fi
  rm -rf "$h"
}

bakname_case1() {
  name="bakname1: repeat runs 2 and 3 in the same second back up to distinct names"
  h=$(new_home); cfg="$h/.claude-cfg"; co="$work/bakname1-checkout"
  make_checkout "$co" "# bakname1 content"
  cp "$INSTALL_SH" "$co/install.sh"
  log="$work/bakname1-mv.log"; : > "$log"
  make_settings_bin "$work/bakname1-bin" "$log" ok
  mkdir -p "$cfg"
  printf '{"mine": 2}\n' > "$cfg/settings.json"

  out1=$(run_with_bin "$co" "$h" "$cfg" "$work/bakname1-bin"); rc1=$?
  : > "$log"  # run 1 is the first install: its move to .orig is not a settings.json.bak.* move
  printf '{"second": 2}\n' > "$cfg/settings.json"
  out2=$(run_with_bin "$co" "$h" "$cfg" "$work/bakname1-bin"); rc2=$?
  printf '{"third": 3}\n' > "$cfg/settings.json"
  out3=$(run_with_bin "$co" "$h" "$cfg" "$work/bakname1-bin"); rc3=$?
  moves=$(grep -c . "$log")
  distinct=$(sort -u "$log" | grep -c .)
  newest=$(cat "$(ls "$cfg"/settings.json.bak.* 2>/dev/null | head -n1)" 2>/dev/null)

  if [ $rc1 -ne 0 ] || [ $rc2 -ne 0 ] || [ $rc3 -ne 0 ]; then
    bad "$name" "install.sh exited rc1=$rc1 rc2=$rc2 rc3=$rc3: $out1 / $out2 / $out3"
  elif [ "$moves" != 2 ]; then
    bad "$name" "expected two settings.json.bak.* moves (runs 2 and 3), logged $moves"
  elif [ "$distinct" != 2 ]; then
    bad "$name" "runs 2 and 3 both backed up to the same name [$(tr '\n' ' ' < "$log")]; the second overwrote the first"
  elif [ "$newest" != '{"third": 3}' ]; then
    bad "$name" "the surviving backup holds [$newest], expected the run 3 content"
  else
    ok "$name"
  fi
  rm -rf "$h"
}

bakfail_case1() {
  name="bakfail1: a failed settings.json backup move exits non-zero, prunes nothing, leaves settings.json as it was"
  h=$(new_home); cfg="$h/.claude-cfg"; co="$work/bakfail1-checkout"
  make_checkout "$co" "# bakfail1 content"
  cp "$INSTALL_SH" "$co/install.sh"
  log="$work/bakfail1-mv.log"; : > "$log"
  make_settings_bin "$work/bakfail1-bin" "$log" fail

  out1=$(run_with_bin "$co" "$h" "$cfg" "$work/bakfail1-bin"); rc1=$?
  printf '{"older": "a"}\n' > "$cfg/settings.json.bak.20260101000000.1001"
  printf '{"older": "b"}\n' > "$cfg/settings.json.bak.20260301000000.1002"
  printf '{"keep": 3}\n' > "$cfg/settings.json"
  out2=$(run_with_bin "$co" "$h" "$cfg" "$work/bakfail1-bin"); rc2=$?
  older_a=$(cat "$cfg/settings.json.bak.20260101000000.1001" 2>/dev/null)
  older_b=$(cat "$cfg/settings.json.bak.20260301000000.1002" 2>/dev/null)
  current=$(cat "$cfg/settings.json" 2>/dev/null)

  if [ $rc1 -ne 0 ]; then
    bad "$name" "setup run 1 exited $rc1: $out1"
  elif [ $rc2 -eq 0 ]; then
    bad "$name" "install.sh exited 0 after the backup move failed, expected non-zero: $out2"
  elif [ "$older_a" != '{"older": "a"}' ] || [ "$older_b" != '{"older": "b"}' ]; then
    bad "$name" "an older settings.json.bak.* was pruned or changed after the failed move"
  elif [ "$current" != '{"keep": 3}' ]; then
    bad "$name" "settings.json was replaced after the failed move, now [$current]"
  else
    ok "$name"
  fi
  rm -rf "$h"
}

# Prints the settings.json.bak.<14 digits>.<pid> files under $1, one per line. A legacy
# settings.json.bak.<14 digits> (no pid, written by the older installer) is not printed.
fresh_baks() {
  for f in "$1"/settings.json.bak.*; do
    [ -e "$f" ] || continue
    case "$(basename "$f")" in
      settings.json.bak.[0-9][0-9][0-9][0-9][0-9][0-9][0-9][0-9][0-9][0-9][0-9][0-9][0-9][0-9].[0-9]*)
        printf '%s\n' "$f" ;;
    esac
  done
}

# A legacy settings.json.bak.<14 digits> from the older installer is the first-ever backup in
# the owner's real config. The prune must never delete it.
legacy_case1() {
  name="legacy1: a repeat run keeps a legacy settings.json.bak.<14 digits> and adds one .bak.<T>.<pid>"
  if [ "$SYMLINK_CAPABLE" != 1 ]; then
    skip "$name" "$NO_SYMLINK_REASON"
    return
  fi
  h=$(new_home); cfg="$h/.claude-cfg"; co="$work/legacy1-checkout"
  make_checkout "$co" "# legacy1 content"
  cp "$INSTALL_SH" "$co/install.sh"

  out1=$(run_local_install "$co" "$h" "$cfg"); rc1=$?
  printf '{"legacy": true}\n' > "$cfg/settings.json.bak.20260916213147"
  rm -f "$cfg/settings.json"
  printf '{"old": 1}\n' > "$cfg/settings.json"
  out2=$(run_local_install "$co" "$h" "$cfg"); rc2=$?
  legacy=$(cat "$cfg/settings.json.bak.20260916213147" 2>/dev/null)
  fresh=$(fresh_baks "$cfg")
  fresh_count=$(printf '%s\n' "$fresh" | grep -c .)
  total=$(ls "$cfg"/settings.json.bak.* 2>/dev/null | wc -l | tr -d ' ')

  if [ $rc1 -ne 0 ] || [ $rc2 -ne 0 ]; then
    bad "$name" "install.sh exited rc1=$rc1 rc2=$rc2: $out1 / $out2"
  elif [ "$legacy" != '{"legacy": true}' ]; then
    bad "$name" "the legacy settings.json.bak.20260916213147 was pruned or changed: [$legacy]"
  elif [ "$fresh_count" != 1 ]; then
    bad "$name" "expected one new settings.json.bak.<T>.<pid>, found $fresh_count"
  elif [ "$(cat "$fresh")" != '{"old": 1}' ]; then
    bad "$name" "the new backup holds [$(cat "$fresh")], expected the plain settings.json"
  elif [ "$total" != 2 ]; then
    bad "$name" "expected two settings.json.bak.* (legacy and new), found $total"
  else
    ok "$name"
  fi
  rm -rf "$h"
}

# First install with settings.json.orig already present: .orig is kept as it is, and the plain
# settings.json goes to a fresh .bak.<T>.<pid>.
orig_case3() {
  name="orig3: a first install with settings.json.orig present keeps .orig and backs the plain file to .bak.<T>.<pid>"
  h=$(new_home); cfg="$h/.claude-cfg"; co="$work/orig3-checkout"
  make_checkout "$co" "# orig3 content"
  cp "$INSTALL_SH" "$co/install.sh"
  mkdir -p "$cfg"
  printf '{"orig": "kept"}\n' > "$cfg/settings.json.orig"
  printf '{"mine": 3}\n' > "$cfg/settings.json"

  out=$(run_local_install "$co" "$h" "$cfg"); rc=$?
  orig=$(cat "$cfg/settings.json.orig" 2>/dev/null)
  fresh=$(fresh_baks "$cfg")
  fresh_count=$(printf '%s\n' "$fresh" | grep -c .)
  total=$(ls "$cfg"/settings.json.bak.* 2>/dev/null | wc -l | tr -d ' ')

  if [ $rc -ne 0 ]; then
    bad "$name" "install.sh exited $rc: $out"
  elif [ "$orig" != '{"orig": "kept"}' ]; then
    bad "$name" "settings.json.orig changed to [$orig]"
  elif [ "$fresh_count" != 1 ]; then
    bad "$name" "expected one new settings.json.bak.<T>.<pid>, found $fresh_count"
  elif [ "$(cat "$fresh")" != '{"mine": 3}' ]; then
    bad "$name" "the new backup holds [$(cat "$fresh")], expected the plain settings.json"
  elif [ "$total" != 1 ]; then
    bad "$name" "expected one settings.json.bak.* in total, found $total"
  else
    ok "$name"
  fi
  rm -rf "$h"
}

# ---- bin case: the shim lands, and only the three stale Banchi files go ------------------------
bin_case1() {
  name="bin1: claude-janitor shim lands; janitor.py, reap.py, session-teardown.sh removed; others kept"
  if [ "$SYMLINK_CAPABLE" != 1 ]; then
    skip "$name" "$NO_SYMLINK_REASON"
    return
  fi
  h=$(new_home); cfg="$h/.claude-cfg"; co="$work/bin1-checkout"
  make_checkout "$co" "# bin1 content"
  cp "$INSTALL_SH" "$co/install.sh"
  cp "$REPO_ROOT/bin/claude-janitor" "$co/bin/claude-janitor"
  mkdir -p "$cfg/bin"
  printf 'old shim\n' > "$cfg/bin/claude-janitor"
  # Stale: reap.py is a foreign symlink, janitor.py is a repo link (kept), session-teardown.sh
  # is a plain file. Decoys that must all survive: foo.sh, claude-janitor-old, a dir named
  # janitor-dir. bin2 covers a dir named janitor.py.
  printf 'x\n' > "$cfg/bin/session-teardown.sh"
  printf 'x\n' > "$cfg/bin/foo.sh"
  printf 'x\n' > "$cfg/bin/claude-janitor-old"
  mkdir -p "$cfg/bin/janitor-dir"
  ln -s "$h/elsewhere" "$cfg/bin/reap.py"
  printf 'x\n' > "$co/bin/janitor.py"
  ln -s "$co/bin/janitor.py" "$cfg/bin/janitor.py"

  out=$(run_local_install "$co" "$h" "$cfg"); rc=$?
  got=$(ls -A "$cfg/bin" | sed "s/\.bak\.[0-9]*/.bak/" | sort | tr '\n' ' ')
  want="claude-janitor claude-janitor-old claude-janitor.bak foo.sh janitor-dir janitor.py "

  if [ $rc -ne 0 ]; then
    bad "$name" "install.sh exited $rc: $out"
  elif [ "$(readlink "$cfg/bin/claude-janitor")" != "$co/bin/claude-janitor" ]; then
    bad "$name" "claude-janitor is not a link to the repo shim"
  elif [ "$got" != "$want" ]; then
    bad "$name" "bin/ holds [$got], expected [$want]"
  elif [ "$(readlink "$cfg/bin/janitor.py")" != "$co/bin/janitor.py" ]; then
    bad "$name" "repo-linked janitor.py was changed"
  else
    ok "$name"
  fi
  rm -rf "$h"
}

bin_case2() {
  name="bin2: a directory named janitor.py is left alone"
  h=$(new_home); cfg="$h/.claude-cfg"; co="$work/bin2-checkout"
  make_checkout "$co" "# bin2 content"
  cp "$INSTALL_SH" "$co/install.sh"
  mkdir -p "$cfg/bin/janitor.py"
  printf 'x\n' > "$cfg/bin/janitor.py/inner"
  out=$(run_local_install "$co" "$h" "$cfg"); rc=$?
  if [ $rc -ne 0 ]; then bad "$name" "install.sh exited $rc: $out"
  elif [ ! -f "$cfg/bin/janitor.py/inner" ]; then bad "$name" "the directory was removed"
  else ok "$name"; fi
  rm -rf "$h"
}

# ---- PATH cases: install.sh puts ~/.claude/bin on PATH through the rc file of $SHELL ---------
PATH_MARK='# claude-settings: ~/.claude/bin on PATH'
PATH_LINE='export PATH="$HOME/.claude/bin:$PATH"'
run_path_install() {
  # $1 = checkout, $2 = HOME, $3 = CLAUDE_CONFIG_DIR, $4 = SHELL value
  ( cd "$1" && env -i PATH="$PATH" HOME="$2" CLAUDE_CONFIG_DIR="$3" SHELL="$4" bash ./install.sh 2>&1 )
}

path_case1() {
  name="path1: zsh SHELL gets the marked block in ~/.zshrc once, not in ~/.bashrc, second run adds nothing"
  h=$(new_home); cfg="$h/.claude-cfg"; co="$work/path1-checkout"
  make_checkout "$co" "# path1 content"
  cp "$INSTALL_SH" "$co/install.sh"
  printf '# my zshrc\n' > "$h/.zshrc"
  if [ -e "$h/.bashrc" ] || grep -q "claude-settings" "$h/.zshrc"; then
    bad "$name" "fixture precondition failed: rc files not clean"; rm -rf "$h"; return
  fi
  out1=$(run_path_install "$co" "$h" "$cfg" /usr/bin/zsh); rc1=$?
  after1=$(cat "$h/.zshrc")
  out2=$(run_path_install "$co" "$h" "$cfg" /usr/bin/zsh); rc2=$?
  marks=$(grep -cF "$PATH_MARK" "$h/.zshrc"); lines=$(grep -cF "$PATH_LINE" "$h/.zshrc")
  if [ $rc1 -ne 0 ] || [ $rc2 -ne 0 ]; then bad "$name" "install.sh exited rc1=$rc1 rc2=$rc2: $out1 / $out2"
  elif [ "$marks" != 1 ] || [ "$lines" != 1 ]; then bad "$name" "the ~/.zshrc holds $marks marks and $lines export lines, expected 1 and 1"
  elif [ "$(cat "$h/.zshrc")" != "$after1" ]; then bad "$name" "second run changed ~/.zshrc"
  elif ! head -1 "$h/.zshrc" | grep -qF "# my zshrc"; then bad "$name" "existing rc content was not kept"
  elif [ -e "$h/.bashrc" ]; then bad "$name" "a zsh SHELL also wrote ~/.bashrc"
  else ok "$name"; fi
  rm -rf "$h"
}

path_case2() {
  name="path2: bash SHELL gets the marked block in ~/.bashrc, not in ~/.zshrc"
  h=$(new_home); cfg="$h/.claude-cfg"; co="$work/path2-checkout"
  make_checkout "$co" "# path2 content"
  cp "$INSTALL_SH" "$co/install.sh"
  if [ -e "$h/.bashrc" ] || [ -e "$h/.zshrc" ]; then
    bad "$name" "fixture precondition failed: rc files exist"; rm -rf "$h"; return
  fi
  out=$(run_path_install "$co" "$h" "$cfg" /bin/bash); rc=$?
  if [ $rc -ne 0 ]; then bad "$name" "install.sh exited $rc: $out"
  elif ! grep -qF "$PATH_MARK" "$h/.bashrc" 2>/dev/null; then bad "$name" "the ~/.bashrc has no marker line"
  elif ! grep -qF "$PATH_LINE" "$h/.bashrc"; then bad "$name" "the ~/.bashrc has no export line"
  elif [ -e "$h/.zshrc" ]; then bad "$name" "a bash SHELL wrote ~/.zshrc"
  else ok "$name"; fi
  rm -rf "$h"
}

path_case3() {
  name="path3: SHELL unset under set -u does not abort install and writes ~/.bashrc"
  h=$(new_home); cfg="$h/.claude-cfg"; co="$work/path3-checkout"
  make_checkout "$co" "# path3 content"
  cp "$INSTALL_SH" "$co/install.sh"
  if [ -e "$h/.bashrc" ]; then bad "$name" "fixture precondition failed: ~/.bashrc exists"; rm -rf "$h"; return; fi
  # bash re-creates SHELL at startup, so `env -i bash ./install.sh` would not leave it unset.
  # Unset it inside the shell, assert it is unset (exit 99 if not), then source the installer.
  out=$( cd "$co" && env -i PATH="$PATH" HOME="$h" CLAUDE_CONFIG_DIR="$cfg" \
         bash -c 'unset SHELL; [ -z "${SHELL+x}" ] || exit 99; source ./install.sh' 2>&1 ); rc=$?
  if [ $rc -eq 99 ]; then bad "$name" "fixture precondition failed: SHELL could not be unset"
  elif [ $rc -ne 0 ]; then bad "$name" "install.sh exited $rc: $out"
  elif ! grep -qF "$PATH_MARK" "$h/.bashrc" 2>/dev/null; then bad "$name" "the ~/.bashrc has no marker line"
  else ok "$name"; fi
  rm -rf "$h"
}

path_case4() {
  name="path4: --cloud and CLAUDE_CODE_REMOTE=true touch no rc file"
  h=$(new_home); cfg="$h/.claude-cfg"; co="$work/path4-checkout"
  make_checkout "$co" "# path4 content"
  cp "$INSTALL_SH" "$co/install.sh"
  printf '# my bashrc\n' > "$h/.bashrc"; printf '# my zshrc\n' > "$h/.zshrc"
  out1=$( cd "$co" && env -i PATH="$PATH" HOME="$h" CLAUDE_CONFIG_DIR="$cfg" SHELL=/bin/bash bash ./install.sh --cloud 2>&1 ); rc1=$?
  out2=$( cd "$co" && env -i PATH="$PATH" HOME="$h" CLAUDE_CONFIG_DIR="$cfg" SHELL=/usr/bin/zsh CLAUDE_CODE_REMOTE=true bash ./install.sh 2>&1 ); rc2=$?
  if [ $rc1 -ne 0 ] || [ $rc2 -ne 0 ]; then bad "$name" "install.sh exited rc1=$rc1 rc2=$rc2: $out1 / $out2"
  elif [ "$(cat "$h/.bashrc")" != "# my bashrc" ]; then bad "$name" "the ~/.bashrc was changed in cloud mode"
  elif [ "$(cat "$h/.zshrc")" != "# my zshrc" ]; then bad "$name" "the ~/.zshrc was changed in cloud mode"
  else ok "$name"; fi
  rm -rf "$h"
}

caseF5() {
  name="caseF5: outside a git tree with no pointer file, stays fully silent, exit 0"
  outside="$work/caseF5-not-a-repo"; cfg="$work/caseF5-cfg"
  mkdir -p "$outside"
  # No CLAUDE_CONFIG_DIR contents at all: the pointer file itself is missing.

  # CLAUDE_CODE_REMOTE unset: a cloud session prints its session-tier line by design.
  out=$(cd "$outside" && CLAUDE_CONFIG_DIR="$cfg" GIT_CEILING_DIRECTORIES="$outside" \
        env -u CLAUDE_CODE_REMOTE sh "$SESSION_START_SH_DEFAULT" < /dev/null 2>/tmp/cF5err)
  rc=$?
  errsize=$(wc -c < /tmp/cF5err | tr -d '[:space:]'); rm -f /tmp/cF5err

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

# caseG*: the session repo (git toplevel of the hook's cwd), not the claude-settings clone.
# gfix <tag> <behind_n> builds bare origin + checkout on main, origin/HEAD set, origin ahead by n.
# Sets g_co g_cfg g_bare g_top g_err (g_err non-empty = FIXTURE failed). cfg has no pointer file,
# so the claude-settings checks stay silent and only the new line can appear.
gfix() {
  g_co="$work/$1-checkout"; g_cfg="$work/$1-cfg"; g_bare="$work/$1-origin.git"; g_err=""
  git init -q --bare "$g_bare" && git -C "$g_bare" symbolic-ref HEAD refs/heads/main
  make_checkout "$g_co" "# $1 content" "$g_bare"
  force_main_branch "$g_co"
  ( cd "$g_co" && git push -q origin main && git fetch -q origin && git remote set-head origin main ) >/dev/null 2>&1 \
    || { g_err="could not push/set origin/HEAD"; return; }
  i=0
  while [ "$i" -lt "$2" ]; do
    i=$((i+1))
    rm -rf "$work/$1-extra"
    ( git clone -q "$g_bare" "$work/$1-extra" && cd "$work/$1-extra" \
      && git config user.email t@example.com && git config user.name t \
      && echo "$i" >> extra.txt && git add extra.txt && git commit -q -m "extra$i" \
      && git push -q origin main ) >/dev/null 2>&1 || { g_err="could not advance origin"; return; }
  done
  mkdir -p "$g_cfg"
  g_top=$(cd "$g_co" && git rev-parse --show-toplevel)
  built=$(cd "$g_bare" && git rev-list --count "$(cd "$g_co" && git rev-parse main)..main" 2>/dev/null)
  [ "$built" = "$2" ] || g_err="FIXTURE behind count is [$built], wanted $2"
}

# grun: runs the hook in g_co; sets g_out g_rc, and g_ref_after (local main sha).
grun() {
  g_out=$(cd "$g_co" && CLAUDE_CONFIG_DIR="$g_cfg" sh "$SESSION_START_SH_DEFAULT" < /dev/null 2>/dev/null)
  g_rc=$?
  g_ref_after=$(cd "$g_co" && git rev-parse main 2>/dev/null)
}

caseG1() {
  name="caseG1: session repo on default branch 2 behind prints the pull line, never pulls"
  gfix caseG1 2
  [ -z "$g_err" ] || { bad "$name" "$g_err"; return; }
  ref_before=$(cd "$g_co" && git rev-parse main)
  grun
  want="checkout $g_top: main is 2 commits behind origin/main; pull before you read it"
  n=$(printf '%s\n' "$g_out" | grep -c 'pull before you read it')
  if [ "$g_rc" -ne 0 ]; then bad "$name" "exit $g_rc"
  elif [ "$n" != "1" ] || ! printf '%s\n' "$g_out" | grep -qxF "$want"; then bad "$name" "expected exactly: $want; got: $g_out"
  elif [ "$g_ref_after" != "$ref_before" ]; then bad "$name" "hook moved local main"
  else ok "$name"; fi
}

caseG2() {
  name="caseG2: session repo up to date prints no pull line"
  gfix caseG2 0
  [ -z "$g_err" ] || { bad "$name" "$g_err"; return; }
  grun
  if [ "$g_rc" -ne 0 ]; then bad "$name" "exit $g_rc"
  elif printf '%s\n' "$g_out" | grep -q 'pull before you read it\|freshness unknown'; then bad "$name" "unexpected line: $g_out"
  else ok "$name"; fi
}

caseG3() {
  name="caseG3: session repo on another branch, default branch behind, prints no pull line"
  gfix caseG3 2
  [ -z "$g_err" ] || { bad "$name" "$g_err"; return; }
  ( cd "$g_co" && git checkout -q -b feature-x ) || { bad "$name" "FIXTURE branch switch failed"; return; }
  grun
  if [ "$g_rc" -ne 0 ]; then bad "$name" "exit $g_rc"
  elif printf '%s\n' "$g_out" | grep -q 'pull before you read it\|freshness unknown'; then bad "$name" "unexpected line: $g_out"
  else ok "$name"; fi
}

caseG4() {
  name="caseG4: origin/HEAD unset prints no pull line"
  gfix caseG4 2
  [ -z "$g_err" ] || { bad "$name" "$g_err"; return; }
  ( cd "$g_co" && git remote set-head origin -d ) >/dev/null 2>&1
  if ( cd "$g_co" && git symbolic-ref refs/remotes/origin/HEAD ) >/dev/null 2>&1; then bad "$name" "FIXTURE origin/HEAD still set"; return; fi
  grun
  if [ "$g_rc" -ne 0 ]; then bad "$name" "exit $g_rc"
  elif printf '%s\n' "$g_out" | grep -q 'pull before you read it\|freshness unknown'; then bad "$name" "unexpected line: $g_out"
  else ok "$name"; fi
}

caseG5() {
  name="caseG5: session repo is the claude-settings clone, behind: one behind line, not two"
  gfix caseG5 2
  [ -z "$g_err" ] || { bad "$name" "$g_err"; return; }
  printf '@%s/CLAUDE.md\n' "$g_co" > "$g_cfg/CLAUDE.md"
  grun
  total=$(printf '%s\n' "$g_out" | grep -c 'commits behind origin/main')
  new=$(printf '%s\n' "$g_out" | grep -c 'pull before you read it')
  if [ "$g_rc" -ne 0 ]; then bad "$name" "exit $g_rc"
  elif [ "$total" != "1" ] || [ "$new" != "0" ]; then bad "$name" "want 1 existing line and 0 new, got $total/$new: $g_out"
  else ok "$name"; fi
}

caseG6() {
  name="caseG6: session repo fetch fails reports freshness unknown, one line"
  gfix caseG6 2
  [ -z "$g_err" ] || { bad "$name" "$g_err"; return; }
  git -C "$g_co" config remote.origin.url "$work/caseG6-no-such-remote"
  ref_before=$(cd "$g_co" && git rev-parse main)
  grun
  want="checkout $g_top: cannot check main against origin, the fetch did not run; freshness unknown"
  n=$(printf '%s\n' "$g_out" | grep -c 'freshness unknown')
  if [ "$g_rc" -ne 0 ]; then bad "$name" "exit $g_rc"
  elif [ "$n" != "1" ] || ! printf '%s\n' "$g_out" | grep -qxF "$want"; then bad "$name" "expected exactly: $want; got: $g_out"
  elif printf '%s\n' "$g_out" | grep -q 'pull before you read it'; then bad "$name" "printed a count off a stale ref"
  elif [ "$g_ref_after" != "$ref_before" ]; then bad "$name" "hook moved local main"
  else ok "$name"; fi
}

caseG7() {
  name="caseG7: session repo fetch killed by the timeout reports freshness unknown"
  gfix caseG7 2
  [ -z "$g_err" ] || { bad "$name" "$g_err"; return; }
  slow="$work/caseG7-slow-upload.sh"
  printf '#!/bin/sh\nsleep 5\nexec git-upload-pack "$1"\n' > "$slow"; chmod +x "$slow"
  git config -f "$g_co/.git/config" remote.origin.url "ext::sh $slow $g_bare"
  git config -f "$g_co/.git/config" protocol.ext.allow always
  g_out=$(cd "$g_co" && CLAUDE_CONFIG_DIR="$g_cfg" CLAUDE_SETTINGS_FETCH_TIMEOUT=0 sh "$SESSION_START_SH_DEFAULT" < /dev/null 2>/dev/null)
  g_rc=$?
  want="checkout $g_top: cannot check main against origin, the fetch did not run; freshness unknown"
  if [ "$g_rc" -ne 0 ]; then bad "$name" "exit $g_rc"
  elif ! printf '%s\n' "$g_out" | grep -qxF "$want"; then bad "$name" "expected: $want; got: $g_out"
  else ok "$name"; fi
}

# ---- Refuse-worktree: install.sh run from a linked git worktree stops before it writes ---------
# From a linked worktree install.sh must exit non-zero, print a line that names the main clone, and
# leave CLAUDE_CONFIG_DIR and HOME as they were. Otherwise ~/.claude/CLAUDE.md and the hooks would
# point at that temp checkout.
# keep_wt1 and keep_plain1 guard the other side: the main clone of a repo that has a linked worktree
# still installs, and a plain folder copy with no .git still installs.

# refuse_fixture NAME: a main clone with one detached linked worktree, a copy of
# install.sh in the worktree, and a config dir seeded with a pointer to the main clone. Sets rw_h
# (the fake HOME), rw_co, rw_wt, rw_cfg, rw_ptr (the seeded pointer) and rw_snap (the config dir
# listing). Returns 1 when git cannot make the worktree.
refuse_fixture() {
  rw_co="$work/$1-main"; rw_wt="$work/$1-wt"; rw_cfg="$work/$1-cfg"
  rw_h=$(new_home)
  make_checkout "$rw_co" "# $1 main"
  git -C "$rw_co" worktree add -q --detach "$rw_wt" >/dev/null 2>&1 || return 1
  cp "$INSTALL_SH" "$rw_wt/install.sh"
  for sub in $(landed_dirs); do mkdir -p "$rw_wt/$sub"; done
  seed_pointer "$rw_cfg" "$rw_co"
  rw_ptr=$(cat "$rw_cfg/CLAUDE.md"); rw_snap=$(find "$rw_cfg" | sort)
}

# refuse_check NAME RC OUT: the run must exit non-zero, name the main clone, and write nothing
# (pointer unchanged, config dir listing unchanged, fake HOME empty). Every reason found goes into
# the FAIL line, so a red run shows what the installer wrote.
refuse_check() {
  why=""
  [ "$2" -ne 0 ] || why="$why exit 0, want non-zero;"
  printf '%s\n' "$3" | grep -qi 'main clone' || why="$why no output line names the main clone;"
  [ "$(cat "$rw_cfg/CLAUDE.md" 2>/dev/null)" = "$rw_ptr" ] || why="$why pointer changed to [$(cat "$rw_cfg/CLAUDE.md" 2>/dev/null)];"
  [ "$(find "$rw_cfg" | sort)" = "$rw_snap" ] || why="$why config dir changed;"
  [ -z "$(home_entries "$rw_h")" ] || why="$why fake HOME was written;"
  if [ -z "$why" ]; then ok "$1"; else bad "$1" "$why"; fi
}

refuse_wt1() {
  name="refuse_wt1: install.sh run from a linked worktree refuses and writes nothing"
  refuse_fixture refuse_wt1 || { bad "$name" "fixture: git worktree add failed"; return; }
  out=$(cd "$rw_wt" && env -i PATH="$PATH" HOME="$rw_h" CLAUDE_CONFIG_DIR="$rw_cfg" bash ./install.sh 2>&1)
  rc=$?
  refuse_check "$name" "$rc" "$out"
  rm -rf "$rw_h"
}

refuse_wt2() {
  name="refuse_wt2: install.sh in a linked worktree refuses even when run from the main clone"
  refuse_fixture refuse_wt2 || { bad "$name" "fixture: git worktree add failed"; return; }
  out=$(cd "$rw_co" && env -i PATH="$PATH" HOME="$rw_h" CLAUDE_CONFIG_DIR="$rw_cfg" bash "$rw_wt/install.sh" 2>&1)
  rc=$?
  refuse_check "$name" "$rc" "$out"
  rm -rf "$rw_h"
}

# keep_check NAME RC OUT CFG HOME TARGET: the run must exit 0 and point CFG/CLAUDE.md at TARGET.
keep_check() {
  pointer=$(sed -n 's|^@\(.*\)/CLAUDE\.md$|\1|p' "$4/CLAUDE.md" 2>/dev/null | head -n1)
  case "$pointer" in "~"/*) pointer="$5${pointer#\~}";; esac
  if [ "$2" -ne 0 ]; then bad "$1" "install.sh exited $2: $3"
  elif [ "$(normalize_path "$pointer")" != "$(normalize_path "$6")" ]; then bad "$1" "pointer target [$pointer] != [$6]"
  else ok "$1"; fi
}

keep_wt1() {
  name="keep_wt1: main clone of a repo with a linked worktree still installs and points at its pinned checkout"
  co="$work/keep_wt1-main"; wt="$work/keep_wt1-wt"; cfg="$work/keep_wt1-cfg"
  h=$(new_home)
  make_checkout "$co" "# keep_wt1 main"
  git -C "$co" branch -q -M main
  cp "$INSTALL_SH" "$co/install.sh"
  git -C "$co" worktree add -q --detach "$wt" >/dev/null 2>&1 \
    || { bad "$name" "fixture: git worktree add failed"; rm -rf "$h"; return; }
  out=$(cd "$co" && env -i PATH="$PATH" HOME="$h" CLAUDE_CONFIG_DIR="$cfg" bash ./install.sh 2>&1)
  rc=$?
  keep_check "$name" "$rc" "$out" "$cfg" "$h" "$co-live"
  rm -rf "$h"
}

keep_plain1() {
  name="keep_plain1: a plain folder copy with no .git still installs"
  dir="$work/keep_plain1-release"; cfg="$work/keep_plain1-cfg"
  h=$(new_home)
  make_checkout "$dir" "# keep_plain1 release"
  rm -rf "$dir/.git"
  cp "$INSTALL_SH" "$dir/install.sh"
  out=$(cd "$dir" && env -i PATH="$PATH" HOME="$h" CLAUDE_CONFIG_DIR="$cfg" bash ./install.sh 2>&1)
  rc=$?
  keep_check "$name" "$rc" "$out" "$cfg" "$h" "$dir"
  rm -rf "$h"
}

# ---- pinned_wt1: install.sh run from the pinned checkout is not refused -----------------------
# The linked-worktree refusal allows exactly <clone>-live. The pinned checkout is a linked
# worktree on a detached HEAD at main's commit, at that path. refuse_wt1 keeps the other side: any
# other linked worktree is still refused.
pinned_wt1() {
  name="pinned_wt1: install.sh run from the pinned checkout <clone>-live is not refused"
  co="$work/pinned_wt1-main"; pin="$work/pinned_wt1-main-live"; cfg="$work/pinned_wt1-cfg"
  h=$(new_home)
  make_checkout "$co" "# pinned_wt1 main"
  force_main_branch "$co"
  git -C "$co" worktree add -q --detach "$pin" >/dev/null 2>&1 \
    || { bad "$name" "fixture: git worktree add failed"; rm -rf "$h"; return; }
  if [ "$(git -C "$pin" rev-parse HEAD)" != "$(git -C "$co" rev-parse refs/heads/main)" ]; then
    bad "$name" "fixture: the pinned checkout is not at local main"; rm -rf "$h"; return
  fi
  cp "$INSTALL_SH" "$pin/install.sh"
  for sub in $(landed_dirs); do mkdir -p "$pin/$sub"; done
  out=$(cd "$pin" && env -i PATH="$PATH" HOME="$h" CLAUDE_CONFIG_DIR="$cfg" bash ./install.sh 2>&1)
  rc=$?
  keep_check "$name" "$rc" "$out" "$cfg" "$h" "$pin"
  rm -rf "$h"
}

# ---- pinoff cases: the pinned checkout <clone>-live is off-main only when it is not at main ----
# Decision merge-reinstalls-from-main: the ~/.claude links point at <clone>-live,
# a detached worktree at main's commit. session_start.sh must not print an off-main line for that
# checkout, and must print one for a pin at any other commit. pinoff1: at main's commit with
# origin/main 2 ahead, the freshness line fires once and no off-main line. pinoff2: a pin one
# commit behind main prints exactly one off-main line, and it names the pin. pinoff3: a full clone
# (not a worktree) detached at main's commit prints no off-main line.
# Each case checks its own fixture first, so a broken setup never reads as a hook result.

# pin_fixture TAG BEHIND AT KIND: a bare origin on main, a clone whose main is one commit past its
# first commit, origin/main BEHIND commits past that main, and a pin at main (AT=main) or at the
# commit before it (AT=old). KIND=worktree makes the pin a linked worktree, KIND=clone a full clone.
# INSTALL=install tracks install.sh and merge/install_from_main.sh in the clone's second commit, so the pin
# holds them as a real pin does. Sets pf_pin, pf_cfg, and pf_msg (the reason it failed, when it returns 1).
pin_fixture() {
  pf_tag="$1"; pf_behind="$2"; pf_at="$3"; pf_kind="$4"; pf_install="${5:-}"; pf_msg=""
  pf_co="$work/$pf_tag-clone"; pf_pin="$work/$pf_tag-clone-live"
  pf_cfg="$work/$pf_tag-cfg"; pf_bare="$work/$pf_tag-origin.git"; pf_extra="$work/$pf_tag-extra"
  git init -q --bare "$pf_bare"
  git -C "$pf_bare" symbolic-ref HEAD refs/heads/main
  make_checkout "$pf_co" "# $pf_tag content" "$pf_bare"
  force_main_branch "$pf_co"
  printf '# %s second\n' "$pf_tag" >> "$pf_co/CLAUDE.md"
  if [ "$pf_install" = install ]; then
    # The install files are tracked in the commit, as a real pin has them: an untracked copy makes the pin dirty.
    mkdir -p "$pf_co/merge" && cp "$INSTALL_SH" "$pf_co/install.sh" \
      && cp "$REPO_ROOT/merge/install_from_main.sh" "$pf_co/merge/install_from_main.sh" \
      || { pf_msg="cannot copy the install files into the clone"; return 1; }
    ( cd "$pf_co" && git add install.sh merge/install_from_main.sh ) || { pf_msg="cannot stage the install files"; return 1; }
  fi
  if ! ( cd "$pf_co" && git add CLAUDE.md && git commit -q -m second && git push -q origin main ); then
    pf_msg="clone setup failed"; return 1
  fi
  pf_main=$(git -C "$pf_co" rev-parse HEAD)
  pf_old=$(git -C "$pf_co" rev-parse HEAD~1)
  if [ "$pf_behind" -gt 0 ]; then
    git clone -q "$pf_bare" "$pf_extra" || { pf_msg="clone to advance origin failed"; return 1; }
    i=1
    while [ "$i" -le "$pf_behind" ]; do
      if ! ( cd "$pf_extra" && git config user.email t@example.com && git config user.name t \
          && echo "e$i" >> extra.txt && git add extra.txt && git commit -q -m "extra$i" ); then
        pf_msg="extra commit $i failed"; return 1
      fi
      i=$((i + 1))
    done
    ( cd "$pf_extra" && git push -q origin main ) || { pf_msg="push to origin failed"; return 1; }
  fi
  behind_built=$(git -C "$pf_bare" rev-list --count "$pf_main..main")
  if [ "$behind_built" != "$pf_behind" ]; then
    pf_msg="origin/main is $behind_built commits past the clone's main, wanted $pf_behind"; return 1
  fi
  if [ "$pf_at" = old ]; then pf_commit="$pf_old"; else pf_commit="$pf_main"; fi
  if [ "$pf_kind" = clone ]; then
    git clone -q "$pf_bare" "$pf_pin" && git -C "$pf_pin" checkout -q --detach "$pf_commit" \
      || { pf_msg="full clone pin failed"; return 1; }
    [ -d "$pf_pin/.git" ] || { pf_msg="pin is not a full clone"; return 1; }
  else
    git -C "$pf_co" worktree add -q --detach "$pf_pin" "$pf_commit" \
      || { pf_msg="git worktree add failed"; return 1; }
    [ -f "$pf_pin/.git" ] || { pf_msg="pin is not a linked worktree"; return 1; }
  fi
  pf_head=$(git -C "$pf_pin" rev-parse HEAD 2>/dev/null)
  if [ "$pf_head" != "$pf_commit" ]; then pf_msg="pin HEAD $pf_head is not $pf_commit"; return 1; fi
  if git -C "$pf_pin" symbolic-ref -q HEAD >/dev/null 2>&1; then
    pf_msg="pin is on a branch, not detached"; return 1
  fi
  mkdir -p "$pf_cfg"
  printf '@%s/CLAUDE.md\n' "$pf_pin" > "$pf_cfg/CLAUDE.md"
  return 0
}

pinoff1() {
  name="pinoff1: pinned worktree at main's commit, origin/main 2 ahead: one freshness line, no off-main line"
  if ! pin_fixture pinoff1 2 main worktree; then bad "$name" "FIXTURE $pf_msg"; return; fi
  out=$(cd "$pf_pin" && CLAUDE_CONFIG_DIR="$pf_cfg" sh "$SESSION_START_SH_DEFAULT" < /dev/null 2>"$work/pinoff1.err")
  rc=$?
  errsize=$(wc -c < "$work/pinoff1.err" | tr -d '[:space:]')
  off_lines=$(printf '%s\n' "$out" | grep -c 'not main')
  stale_lines=$(printf '%s\n' "$out" | grep -c 'commits behind origin/main')

  if [ $rc -ne 0 ]; then
    bad "$name" "exit $rc"
  elif [ "$errsize" != "0" ]; then
    bad "$name" "wrote to stderr"
  elif [ "$off_lines" != "0" ]; then
    bad "$name" "false off-main line for a checkout at main's commit: $out"
  elif [ "$stale_lines" != "1" ]; then
    bad "$name" "expected one freshness line, got $stale_lines: $out"
  else
    ok "$name"
  fi
}

pinoff2() {
  name="pinoff2: pinned worktree one commit behind main: exactly one off-main line, naming the pin"
  if ! pin_fixture pinoff2 0 old worktree; then bad "$name" "FIXTURE $pf_msg"; return; fi
  out=$(cd "$pf_pin" && CLAUDE_CONFIG_DIR="$pf_cfg" sh "$SESSION_START_SH_DEFAULT" < /dev/null 2>"$work/pinoff2.err")
  rc=$?
  errsize=$(wc -c < "$work/pinoff2.err" | tr -d '[:space:]')
  off_lines=$(printf '%s\n' "$out" | grep -c 'not main')
  named_lines=$(printf '%s\n' "$out" | grep 'not main' | grep -c 'clone-live')

  if [ $rc -ne 0 ]; then
    bad "$name" "exit $rc"
  elif [ "$errsize" != "0" ]; then
    bad "$name" "wrote to stderr"
  elif [ "$off_lines" != "1" ]; then
    bad "$name" "expected exactly one off-main line, got $off_lines: $out"
  elif [ "$named_lines" != "1" ]; then
    bad "$name" "the off-main line does not name the pinned checkout: $out"
  else
    ok "$name"
  fi
}

pinoff3() {
  name="pinoff3: full clone detached at main's commit: no off-main line"
  if ! pin_fixture pinoff3 0 main clone; then bad "$name" "FIXTURE $pf_msg"; return; fi
  out=$(cd "$pf_pin" && CLAUDE_CONFIG_DIR="$pf_cfg" sh "$SESSION_START_SH_DEFAULT" < /dev/null 2>"$work/pinoff3.err")
  rc=$?
  errsize=$(wc -c < "$work/pinoff3.err" | tr -d '[:space:]')
  off_lines=$(printf '%s\n' "$out" | grep -c 'not main')

  if [ $rc -ne 0 ]; then
    bad "$name" "exit $rc"
  elif [ "$errsize" != "0" ]; then
    bad "$name" "wrote to stderr"
  elif [ "$off_lines" != "0" ]; then
    bad "$name" "false off-main line for a detached clone at main's commit: $out"
  else
    ok "$name"
  fi
}

# ---- install-set cases: one install swaps every guard file at once,
# and one install runs at a time. Copy mode is `install.sh --cloud`: only that path stamps each guard
# file with its INSTALL_ID through put_file, so only that path can show a mix. install.sh has no
# seam, so a `mv` shim first on PATH holds an install between two guard landings. That is the stall a
# held file makes on Windows (install-set.test.ps1 uses a share lock). The shim logs each guard landing
# with its build. The stall outlasts guard.py's own load wait (_LOAD_WAIT_SECONDS, read from guard.py),
# so a guard that still fails after that wait is a crash a user would see.
TMO=""; command -v timeout >/dev/null 2>&1 && TMO="timeout 150"

# The two files the install-set cases share: the probe that prints the INSTALL_IDs the guard loads, and
# the guard payload, a plain `ls`. install-set.test.ps1 has the same probe (Get-LoadedId).
install_set_setup() {
  cat > "$work/loaded-ids.py" <<'EOF'
import runpy, sys
ns = runpy.run_path(sys.argv[1], run_name="guard_probe")
ids = {str(getattr(m, "INSTALL_ID", "(none)")) for name, m in list(sys.modules.items()) if name.startswith("guard")}
ids.add(str(ns.get("INSTALL_ID", "(none)")))
print("\n".join(sorted(ids)))
EOF
  printf '%s' '{"tool_name": "Bash", "tool_input": {"command": "ls"}, "cwd": "/"}' > "$work/guard-payload.json"
}

# A guard fixture at build $2 in clone folder $1: install.sh, the landed-dirs list, the install files, and
# every hook module from this repo (testing/tracked_tree.sh), with a "# build $2" line appended to guard.py
# and each guard_*.py. The rest stay unstamped. Mirrors New-Clone in install-set.test.ps1.
make_guard_clone() {
  mkdir -p "$1/hooks"
  cp "$INSTALL_SH" "$1/install.sh"
  cp "$REPO_ROOT/landed-dirs.txt" "$1/landed-dirs.txt"
  printf '# fixture CLAUDE.md %s\n' "$2" > "$1/CLAUDE.md"
  printf '{}\n' > "$1/settings.json"
  copy_folder hooks "$1/hooks" || return 1
  for f in "$1/hooks/guard.py" "$1"/hooks/guard_*.py; do
    printf '\n# build %s\n' "$2" >> "$f"
  done
}

# The mv shim, in folder $1. install.sh lands each file with `mv -f "$t" "$dest"`. For a guard file the
# shim does three things. Before the second guard landing of an install whose SWAP_PAUSE is set, it
# logs "paused" to $SWAP_EVENTS and sleeps $SWAP_PAUSE seconds, once: install.sh retries a failed mv,
# and the retry must not pause again. It runs the real mv. After the landing it logs
# "landed <epoch seconds> <build>". When SWAP_INSTALL_LOG is set, each stamped guard file (guard.py,
# guard_*.py) also logs "install.sh: landed id=<id>" to it; shared_names.py and git_reads.py carry no stamp
# and are not logged. Before put_file's rename (its source ends in .cs-new) it logs
# "premv <dest> <present|absent> <bytes of the new file>" to $SWAP_EVENTS, whatever the dest. Every other
# mv passes straight through.
make_swap_bin() {
  mkdir -p "$1"
  real_mv=$(command -v mv)
  cat > "$1/mv" <<EOF
#!/bin/sh
dest=""; src=""
for a in "\$@"; do src="\$dest"; dest="\$a"; done
case "\$src" in
  *.cs-new)
    printf 'premv %s %s %s\n' "\$dest" "\$([ -f "\$dest" ] && echo present || echo absent)" "\$(wc -c < "\$src" | tr -d ' ')" >> "\$SWAP_EVENTS" ;;
esac
case "\$dest" in
  */hooks/guard*.py)
    if [ -n "\${SWAP_PAUSE:-}" ] && [ "\$(grep -c '^landed' "\$SWAP_EVENTS")" = 1 ] && ! grep -q '^paused' "\$SWAP_EVENTS"; then
      printf 'paused\n' >> "\$SWAP_EVENTS"; sleep "\$SWAP_PAUSE"
    fi ;;
esac
"$real_mv" "\$@" || exit \$?
case "\$dest" in
  */hooks/guard*.py)
    printf 'landed %s %s\n' "\$(date +%s)" "\$(sed -n 's/^# build //p' "\$dest" | head -n1)" >> "\$SWAP_EVENTS"
    case "\$(basename "\$dest")" in
      guard.py|guard_*.py)
        if [ -n "\${SWAP_INSTALL_LOG:-}" ]; then
          printf '%s install.sh: landed id=%s\n' "\$(date +%Y-%m-%dT%H:%M:%S)" "\$(sed -n 's/^INSTALL_ID = "\([^"]*\)".*/\1/p' "\$dest" | head -n1)" >> "\$SWAP_INSTALL_LOG"
        fi ;;
    esac ;;
esac
EOF
  chmod +x "$1/mv"
}

# One copy-mode install of clone $1 into config dir $2, logging guard landings to events file $3. $4,
# when given, is the stall in seconds before the second guard landing. The caller sets $h (home) and
# $swap_bin (the shim folder). Run it in the background to overlap two installs.
run_cloud() {
  ( cd "$1" && env HOME="$h" CLAUDE_CONFIG_DIR="$2" SWAP_EVENTS="$3" ${4:+SWAP_PAUSE="$4"} ${5:+SWAP_INSTALL_LOG="$5"} \
      PATH="$swap_bin:$PATH" $TMO bash ./install.sh --cloud )
}

# The distinct INSTALL_ID values the real guard loads from config dir $1, one per line.
loaded_ids() {
  env -u CLAUDE_CODE_SESSION_ID CLAUDE_CONFIG_DIR="$1" HOME="$h" PYTHONPATH= \
    python3 -B "$work/loaded-ids.py" "$1/hooks/guard.py" 2>/dev/null | sort -u
}

# One guard run through the installed hook, the way Claude Code runs it: the payload on stdin. Stdout
# goes to file $2. Empty stdout is an allow. A crash deny names guard-crash.
guard_run() {
  env -u CLAUDE_CODE_SESSION_ID CLAUDE_CONFIG_DIR="$1" HOME="$h" CLAUDE_GUARD_ROOT_PID="$$" PYTHONPATH= \
    python3 -B "$1/hooks/guard.py" < "$work/guard-payload.json" > "$2" 2>/dev/null
}

# ---- swap1sh: a copy-mode install stalled between two guard landings never makes the guard crash ----
swap1sh() {
  name="swap1sh: a copy-mode install stalled between two guard landings never makes the guard crash, and after it the guard loads one new set"
  install_set_setup
  h=$(new_home); cfg="$h/.claude-cfg"; swap_bin="$work/swap1sh-bin"
  make_swap_bin "$swap_bin"
  make_guard_clone "$work/swap1sh-one" one
  make_guard_clone "$work/swap1sh-two" two
  wait_s=$(sed -n 's/^_LOAD_WAIT_SECONDS = \([0-9][0-9]*\).*/\1/p' "$REPO_ROOT/hooks/guard.py" | head -n1)
  pause=$(( ${wait_s:-5} * 2 + 2 ))
  ev1="$work/swap1sh-ev1"; ev2="$work/swap1sh-ev2"; : > "$ev1"; : > "$ev2"
  run_cloud "$work/swap1sh-one" "$cfg" "$ev1" > "$work/swap1sh-run1" 2>&1; rc1=$?
  id1=$(loaded_ids "$cfg")
  run_cloud "$work/swap1sh-two" "$cfg" "$ev2" "$pause" > "$work/swap1sh-run2" 2>&1 &
  p2=$!
  # Bounded sampler: real guard runs while install 2 is alive, at most 300 of them.
  loads=0; crashes=0; others=0; n=0; gout="$work/swap1sh-guard.out"
  while kill -0 "$p2" 2>/dev/null && [ "$n" -lt 300 ]; do
    n=$((n + 1))
    guard_run "$cfg" "$gout"
    loads=$((loads + 1))
    if grep -q 'guard-crash' "$gout"; then crashes=$((crashes + 1))
    elif [ -s "$gout" ]; then others=$((others + 1)); fi
  done
  wait "$p2"; rc2=$?
  stalled=$(grep -c '^paused' "$ev2")
  id2=$(loaded_ids "$cfg")

  if [ "$rc1" -ne 0 ] || [ "$(printf '%s\n' "$id1" | grep -c .)" != 1 ]; then
    bad "$name" "setup: install 1 exit $rc1, loaded ids [$id1]"
  elif [ "$stalled" != 1 ]; then bad "$name" "precondition: the stall never fired, so the case proves nothing"
  elif [ "$rc2" -ne 0 ]; then bad "$name" "install 2 exit $rc2: $(cat "$work/swap1sh-run2")"
  elif [ "$crashes" -gt 0 ]; then bad "$name" "$crashes of $loads guard runs during install 2 were guard-crash denies, while install 2 was stalled between guard landings"
  elif [ "$others" -gt 0 ]; then bad "$name" "$others of $loads guard runs during install 2 were a deny, not an allow"
  elif [ "$loads" -lt 3 ]; then bad "$name" "precondition: only $loads guard runs during install 2, so the window is not covered"
  elif [ "$(printf '%s\n' "$id2" | grep -c .)" != 1 ] || [ "$id2" = "$id1" ]; then
    bad "$name" "after install 2 the guard loads [$id2] (install 1: [$id1]), want one new id"
  else ok "$name"
  fi
  rm -rf "$h"
}

# The install-log span check for lock1sh. A guard landing is logged "install.sh: landed id=<id>", where <id>
# is the INSTALL_ID that put_file stamped into the landed guard file, so it names its install. Prints
# "bad <problem>" for each landing with no id or outside the start and end lines of its own id, then
# "in A <n>" and "in B <n>": the tagged landings inside the first and the second install's span.
landing_span_report() {
  awk '
    /install\.sh: (start|end|landed)/ {
      if ($0 ~ /install\.sh: start/) kind = "start"
      else if ($0 ~ /install\.sh: end/) kind = "end"
      else kind = "landed"
      id = ""
      if (match($0, /id=[^ ]*/)) id = substr($0, RSTART + 3, RLENGTH - 3)
      if (kind == "start") { if (!(id in s)) order[++m] = id; s[id] = NR }
      else if (kind == "end") e[id] = NR
      else lands[NR] = id
    }
    END {
      for (n = 1; n <= NR; n++) {
        if (!(n in lands)) continue
        id = lands[n]
        if (id == "") { print "bad guard landing at install log line " n " carries no install id"; continue }
        if (!(id in s) || !(id in e) || s[id] > n || e[id] < n) {
          print "bad guard landing of install " id " at install log line " n " is outside its own start and end"
          continue
        }
        if (id == order[1]) a++
        else if (id == order[2]) b++
      }
      print "in A " (a + 0)
      print "in B " (b + 0)
    }
  ' "$1"
}

# ---- lock1sh: a second install waits for the first, or refuses with one clear line ----------------
lock1sh() {
  name="lock1sh: a second copy-mode install started while the first is stalled lands no guard file before the first exits, or exits with one lock line"
  install_set_setup
  h=$(new_home); cfg="$h/.claude-cfg"; swap_bin="$work/lock1sh-bin"
  make_swap_bin "$swap_bin"
  make_guard_clone "$work/lock1sh-one" A
  make_guard_clone "$work/lock1sh-two" B
  evA="$work/lock1sh-evA"; evB="$work/lock1sh-evB"; : > "$evA"; : > "$evB"
  run_cloud "$work/lock1sh-one" "$cfg" "$evA" 6 "$cfg/claude-settings-install.log" > "$work/lock1sh-runA" 2>&1 &
  pA=$!
  sleep 0.3
  alive=no; kill -0 "$pA" 2>/dev/null && alive=yes
  run_cloud "$work/lock1sh-two" "$cfg" "$evB" "" "$cfg/claude-settings-install.log" > "$work/lock1sh-runB" 2>&1 &
  pB=$!
  # Bounded wait: both installs end, at most 3000 polls. The order comes from the install log, never from a
  # clock. install.sh appends "start" after it takes the lock and "end" before it releases it, both to one log,
  # so the line order is the order of the lock. A clock here would time when this loop saw A exit, not when A let go.
  n=0
  while { kill -0 "$pA" 2>/dev/null || kill -0 "$pB" 2>/dev/null; } && [ "$n" -lt 3000 ]; do
    n=$((n + 1))
    sleep 0.05
  done
  wait "$pA"; rcA=$?
  wait "$pB"; rcB=$?
  order=$(grep -E -o 'install\.sh: (start|end)' "$cfg/claude-settings-install.log" 2>/dev/null | sed 's/install\.sh: //' | tr '\n' ' ')
  bFirst=$(sed -n 's/^landed \([0-9][0-9]*\) .*/\1/p' "$evB" | head -n1)
  lockLines=$(grep -ciE 'lock|another install|already running|waiting' "$work/lock1sh-runB")
  span=$(landing_span_report "$cfg/claude-settings-install.log")
  spanBad=$(printf '%s\n' "$span" | sed -n 's/^bad //p' | head -n1)
  inA=$(printf '%s\n' "$span" | sed -n 's/^in A //p')
  inB=$(printf '%s\n' "$span" | sed -n 's/^in B //p')

  if [ "$alive" != yes ]; then bad "$name" "precondition: install A had already exited when install B started, so the case proves nothing"
  elif [ "$(grep -c '^paused' "$evA")" -lt 1 ]; then
    bad "$name" "precondition: install A never stalled, so the case proves nothing; A events [$(tr '\n' ' ' < "$evA")], A output [$(tail -n 3 "$work/lock1sh-runA" | tr '\n' ' ')]"
  elif [ "$order" != "start end " ] && [ "$order" != "start end start end " ]; then
    bad "$name" "install B took the install lock before install A ended, while A was stalled: install log order [$order], want A's start and end before B's start"
  elif [ -n "$bFirst" ] && [ "$order" != "start end start end " ]; then
    bad "$name" "install B landed guard files without taking the install lock: install log order [$order], want A's start and end, then B's start and end"
  elif [ -n "$spanBad" ]; then bad "$name" "$spanBad"
  elif [ "${inA:-0}" -lt 1 ]; then bad "$name" "precondition: no guard landing of install A is logged inside its own start and end, so the case proves nothing"
  elif [ -n "$bFirst" ] && [ "${inB:-0}" -lt 1 ]; then
    bad "$name" "install B landed guard files, but none is logged inside its own start and end"
  elif [ -z "$bFirst" ] && [ "$lockLines" != 1 ]; then
    bad "$name" "install B landed no guard file and printed $lockLines lock line(s), want one clear line"
  elif [ "$rcA" -ne 0 ]; then bad "$name" "install A exit $rcA: $(cat "$work/lock1sh-runA")"
  elif [ -n "$bFirst" ] && [ "$rcB" -ne 0 ]; then bad "$name" "install B landed its guard files but exit $rcB"
  else
    builds=$(sed -n 's/^# build //p' "$cfg"/hooks/guard*.py | sort -u | wc -l | tr -d ' ')
    if [ "$builds" = 1 ]; then ok "$name"
    else bad "$name" "after both installs the guard files carry $builds builds, want one whole set"
    fi
  fi
  rm -rf "$h"
}

# ---- putfile_nogap1: put_file replaces a landed file by one rename over it, never by a delete -----
# A guard hook reads a hook file at any moment, and a missing one fails closed. Install 2 replaces every file
# install 1 landed in hooks/. The mv shim logs "premv <dest> <present|absent> <bytes>" just before each
# put_file rename. Each file needs a premv line that found the old file present. That fails a delete before the
# rename, and a rewrite in place, which has no rename at all. The new file's size at that moment must be the
# landed file's size, so the file is whole before it takes the name. The guard files, shared_names.py and a
# plain hook go through put_file.
putfile_nogap1() {
  name="putfile_nogap1: a copy-mode install replaces each landed hook file by one rename over the old file, never by a delete or a rewrite in place"
  h=$(new_home); cfg="$h/.claude-cfg"; swap_bin="$work/putfile_nogap1-bin"
  make_swap_bin "$swap_bin"
  one="$work/putfile_nogap1-one"; two="$work/putfile_nogap1-two"
  make_guard_clone "$one" one
  make_guard_clone "$two" two
  printf '# plain hook one\n' > "$one/hooks/notify.sh"
  printf '# plain hook two, longer\n' > "$two/hooks/notify.sh"
  ev1="$work/putfile_nogap1-ev1"; ev2="$work/putfile_nogap1-ev2"; : > "$ev1"; : > "$ev2"
  run_cloud "$one" "$cfg" "$ev1" > "$work/putfile_nogap1-run1" 2>&1; rc1=$?
  names=$(ls "$two/hooks")
  missing1=""; for f in $names; do [ -f "$cfg/hooks/$f" ] || missing1="$missing1 $f"; done
  run_cloud "$two" "$cfg" "$ev2" > "$work/putfile_nogap1-run2" 2>&1; rc2=$?
  why=""
  for f in $names; do
    d="$cfg/hooks/$f"
    seen=$(awk -v d="$d" '$1 == "premv" && $2 == d { print $3 " " $4 }' "$ev2" | tail -n 1)
    size=$(wc -c < "$d" 2>/dev/null | tr -d ' ')
    case "$seen" in
      "present $size") ;;
      "") why="$why $f: no rename over it, so it was written in place;" ;;
      absent*) why="$why $f: absent just before the rename;" ;;
      *) why="$why $f: [$seen] before the rename, but the landed file is $size bytes;" ;;
    esac
  done
  left=$(find "$cfg" -name '*.cs-new' | head -n 1)
  new_notify=$(cat "$cfg/hooks/notify.sh" 2>/dev/null)

  if [ "$rc1" -ne 0 ] || [ -n "$missing1" ] || [ -z "$names" ]; then
    bad "$name" "setup: install 1 exit $rc1, not landed:$missing1"
  elif [ "$rc2" -ne 0 ]; then bad "$name" "install 2 exit $rc2: $(tail -n 3 "$work/putfile_nogap1-run2")"
  elif [ -n "$why" ]; then bad "$name" "$why"
  elif [ -n "$left" ]; then bad "$name" "a temp file is left behind: $left"
  elif [ "$new_notify" != "# plain hook two, longer" ]; then bad "$name" "install 2 did not land the new notify.sh, found [$new_notify]"
  else ok "$name"
  fi
  rm -rf "$h"
}

# ---- putfile_prose1: only the exact placeholder line is stamped; a prose comment is copied unchanged ----
# A comment that starts INSTALL_ID = " but says something else is not the placeholder. put_file must leave
# it as it is, so each landed copy is the source, and still parses as Python. The exact line
# # INSTALL_ID = "uninstalled" is stamped with a real id. A guard file lands twice: in guard.d/<id>/ and flat.
putfile_prose1() {
  name="putfile_prose1: a copy-mode install stamps only the exact INSTALL_ID placeholder line and copies a prose comment unchanged"
  h=$(new_home); cfg="$h/.claude-cfg"; swap_bin="$work/putfile_prose1-bin"
  clone="$work/putfile_prose1-clone"
  make_guard_clone "$clone" one
  printf '%s\nX = 1\n' '# INSTALL_ID = "<id>", and the cases put that line at the top of every copy, as an install does.' > "$clone/hooks/guard_prose.py"
  printf '# INSTALL_ID = "uninstalled"\nY = 2\n' > "$clone/hooks/guard_stamp.py"
  ev="$work/putfile_prose1-ev"; : > "$ev"
  run_cloud "$clone" "$cfg" "$ev" > "$work/putfile_prose1-run" 2>&1; rc=$?
  why=""
  for p in "$cfg/hooks/guard_prose.py" "$cfg"/hooks/guard.d/*/guard_prose.py; do
    cmp -s "$clone/hooks/guard_prose.py" "$p" 2>/dev/null || why="$why prose comment changed or missing in $p;"
    python3 -c 'import ast, sys; ast.parse(open(sys.argv[1]).read())' "$p" 2>/dev/null || why="$why $p does not parse as Python;"
  done
  for p in "$cfg/hooks/guard_stamp.py" "$cfg"/hooks/guard.d/*/guard_stamp.py; do
    grep -q '^INSTALL_ID = "[^"][^"]*"' "$p" 2>/dev/null && ! grep -q uninstalled "$p" || why="$why placeholder not stamped in $p;"
    python3 -c 'import ast, sys; ast.parse(open(sys.argv[1]).read())' "$p" 2>/dev/null || why="$why $p does not parse as Python;"
  done

  if [ "$rc" -ne 0 ]; then bad "$name" "install exit $rc: $(tail -n 3 "$work/putfile_prose1-run")"
  elif [ -n "$why" ]; then bad "$name" "$why"
  else ok "$name"
  fi
  rm -rf "$h"
}

# ---- installlog1: one install writes a start line and an end line that name the same id and pid ----
# A reader pairs the end line to its start line by the id and the pid. An end line with another id
# leaves the run looking unfinished and the id looking like a second run.
installlog1() {
  name="installlog1: one install writes one start line and one end line with the same id and pid, and the end line says exit=0"
  h=$(new_home); cfg="$h/.claude-cfg"; swap_bin="$work/installlog1-bin"
  clone="$work/installlog1-clone"
  make_guard_clone "$clone" one
  ev="$work/installlog1-ev"; : > "$ev"
  run_cloud "$clone" "$cfg" "$ev" > "$work/installlog1-run" 2>&1; rc=$?
  log="$cfg/claude-settings-install.log"
  lines=$(wc -l < "$log" 2>/dev/null | tr -d ' ')
  s=$(sed -n 's/^[^ ]* install\.sh: start id=\([0-9][0-9]*\) pid=\([0-9][0-9]*\)$/\1 \2/p' "$log" 2>/dev/null)
  e=$(sed -n 's/^[^ ]* install\.sh: end exit=0 id=\([0-9][0-9]*\) pid=\([0-9][0-9]*\)$/\1 \2/p' "$log" 2>/dev/null)

  if [ "$rc" -ne 0 ]; then bad "$name" "install exit $rc: $(tail -n 3 "$work/installlog1-run")"
  elif [ "$lines" != 2 ]; then bad "$name" "the log holds [$lines] lines, want 2: $(cat "$log" 2>/dev/null)"
  elif [ -z "$s" ]; then bad "$name" "no start line with a numeric id and pid: $(cat "$log")"
  elif [ -z "$e" ]; then bad "$name" "no end line with exit=0 and a numeric id and pid: $(cat "$log")"
  elif [ "$s" != "$e" ]; then bad "$name" "start names [$s], end names [$e] (id pid)"
  else ok "$name"
  fi
  rm -rf "$h"
}

# ---- pinlive cases: <clone>-live is the one linked worktree allowed, and only at local main ----
# Decision merge-reinstalls-from-main: the path <clone>-live is not enough. A linked
# worktree at that path is allowed only when it is detached at the clone's local main commit.
# pinlive1: a -live worktree on a lane branch is refused. pinlive2: a -live worktree detached at a
# commit that is not main is refused. pinned_wt1 keeps the other side: detached at main passes.

# pinlive_check NAME RC OUT CFG HOME PTR SNAP: a refusal exits non-zero, leaves the pointer and the
# config dir listing unchanged, and writes nothing into the fake HOME.
pinlive_check() {
  why=""
  [ "$2" -ne 0 ] || why="$why exit 0, want non-zero;"
  [ "$(cat "$4/CLAUDE.md" 2>/dev/null)" = "$6" ] || why="$why pointer changed to [$(cat "$4/CLAUDE.md" 2>/dev/null)];"
  [ "$(find "$4" | sort)" = "$7" ] || why="$why config dir changed;"
  [ -z "$(home_entries "$5")" ] || why="$why fake HOME was written;"
  if [ -z "$why" ]; then ok "$1"; else bad "$1" "$why output: $3"; fi
}

pinlive1() {
  name="pinlive1: install.sh run from <clone>-live on a lane branch is refused and writes nothing"
  co="$work/pinlive1-main"; pin="$work/pinlive1-main-live"; cfg="$work/pinlive1-cfg"
  h=$(new_home)
  make_checkout "$co" "# pinlive1 main"
  force_main_branch "$co"
  git -C "$co" worktree add -q -b lane "$pin" >/dev/null 2>&1 \
    || { bad "$name" "fixture: git worktree add failed"; rm -rf "$h"; return; }
  if [ "$(git -C "$pin" symbolic-ref -q --short HEAD)" != lane ]; then
    bad "$name" "fixture: the pinned path is not on branch lane"; rm -rf "$h"; return
  fi
  cp "$INSTALL_SH" "$pin/install.sh"
  for sub in $(landed_dirs); do mkdir -p "$pin/$sub"; done
  seed_pointer "$cfg" "$co"
  ptr=$(cat "$cfg/CLAUDE.md"); snap=$(find "$cfg" | sort)
  out=$(cd "$pin" && env -i PATH="$PATH" HOME="$h" CLAUDE_CONFIG_DIR="$cfg" bash ./install.sh 2>&1)
  rc=$?
  pinlive_check "$name" "$rc" "$out" "$cfg" "$h" "$ptr" "$snap"
  rm -rf "$h"
}

pinlive2() {
  name="pinlive2: install.sh run from <clone>-live detached at a commit that is not main is refused and writes nothing"
  co="$work/pinlive2-main"; pin="$work/pinlive2-main-live"; cfg="$work/pinlive2-cfg"
  h=$(new_home)
  make_checkout "$co" "# pinlive2 main"
  force_main_branch "$co"
  git -C "$co" worktree add -q --detach "$pin" >/dev/null 2>&1 \
    || { bad "$name" "fixture: git worktree add failed"; rm -rf "$h"; return; }
  # The pin stays at the old main; main then moves on, as it does between a merge and the move.
  printf '# pinlive2 second\n' >> "$co/CLAUDE.md"
  if ! git -C "$co" commit -q -am second; then
    bad "$name" "fixture: commit on main failed"; rm -rf "$h"; return
  fi
  if [ "$(git -C "$pin" rev-parse HEAD)" = "$(git -C "$co" rev-parse refs/heads/main)" ]; then
    bad "$name" "fixture: the pinned checkout did not stay behind main"; rm -rf "$h"; return
  fi
  cp "$INSTALL_SH" "$pin/install.sh"
  for sub in $(landed_dirs); do mkdir -p "$pin/$sub"; done
  seed_pointer "$cfg" "$co"
  ptr=$(cat "$cfg/CLAUDE.md"); snap=$(find "$cfg" | sort)
  out=$(cd "$pin" && env -i PATH="$PATH" HOME="$h" CLAUDE_CONFIG_DIR="$cfg" bash ./install.sh 2>&1)
  rc=$?
  pinlive_check "$name" "$rc" "$out" "$cfg" "$h" "$ptr" "$snap"
  rm -rf "$h"
}

# ---- pinmove cases: a cloud install whose pointer names the live pin takes the clone as its source ----
# Decision merge-reinstalls-from-main, ruling 1: no work runs in the pin. The pin is <clone>-live-<12 hex>, a
# locked worktree detached at main, and <clone>-live is an absolute link to it (merge/install_from_main.sh).
# install.sh's candidate loop takes the pointer dir first, so a pointer at either form makes the pin the source.
# The cloud own-checkout block then moves that pin to origin/main, and the pointer is written to the pin.
# Each case points the pointer at one form (pin, link or the clone) and asserts that the source is the clone.

# live_pin_fixture TAG: pin_fixture's clone and bare origin, with origin/main 2 commits past the clone's main.
# Its pin at main is renamed to <clone>-live-<12 hex>, locked, and <clone>-live is made a link to it. The clone's
# origin is the GitHub URL, which the case's HOME redirects to the bare repo (write_redirect). checkout_at then
# accepts the clone, and the cloud fetch stays local. Sets lp_co, lp_bare, lp_pin, lp_link and lp_msg (the reason
# it failed, when it returns 1).
live_pin_fixture() {
  lp_msg=""
  if ! pin_fixture "$1" 2 main worktree "${2:-}"; then lp_msg="$pf_msg"; return 1; fi
  lp_co="$pf_co"; lp_bare="$pf_bare"; lp_link="$pf_co-live"
  lp_pin="$lp_co-live-$(git -C "$pf_pin" rev-parse --short=12 HEAD 2>/dev/null)"
  git -C "$lp_co" worktree move "$pf_pin" "$lp_pin" >/dev/null 2>&1 \
    || { lp_msg="cannot rename the pin to $lp_pin"; return 1; }
  git -C "$lp_co" worktree lock --reason "claude-settings live pin" "$lp_pin" >/dev/null 2>&1 \
    || { lp_msg="cannot lock the pin"; return 1; }
  ln -s "$lp_pin" "$lp_link" && [ -L "$lp_link" ] || { lp_msg="cannot make the link"; return 1; }
  git -C "$lp_co" remote set-url origin https://github.com/shivinate7/claude-settings.git \
    || { lp_msg="cannot set origin to the GitHub URL"; return 1; }
  lp_head=$(git -C "$lp_pin" rev-parse HEAD 2>/dev/null)
  lp_main=$(git -C "$lp_co" rev-parse --verify -q refs/heads/main 2>/dev/null)
  lp_origin=$(git -C "$lp_bare" rev-parse --verify -q refs/heads/main 2>/dev/null)
  if [ "$lp_head" != "$lp_main" ]; then lp_msg="the pin is not at the clone's main"; return 1; fi
  if [ "$lp_head" = "$lp_origin" ] || ! git -C "$lp_bare" merge-base --is-ancestor "$lp_head" "$lp_origin"; then
    lp_msg="origin/main does not hold the pin's commit as an ancestor, so the move cannot happen"; return 1
  fi
  if [ -n "$(git -C "$lp_pin" status --porcelain 2>/dev/null)" ]; then lp_msg="the pin has changes"; return 1; fi
  if git -C "$lp_pin" symbolic-ref -q HEAD >/dev/null 2>&1; then lp_msg="the pin is on a branch"; return 1; fi
  return 0
}

# pinmove_run TAG WHERE: one cloud install, piped as the setup script runs it, from a folder that is no checkout,
# with the pointer at WHERE: pin, link or clone. Builds live_pin_fixture TAG first. Sets pm_co, pm_pin, pm_out,
# pm_rc, pm_ptr (the pointer target after the run), and pm_head_before and pm_head_after (the pin's HEAD around the
# run). Returns 1 with pm_msg when the fixture failed.
pinmove_run() {
  pm_msg=""
  if ! live_pin_fixture "$1"; then pm_msg="$lp_msg"; return 1; fi
  pm_co="$lp_co"; pm_pin="$lp_pin"
  case "$2" in
    pin) pm_target="$lp_pin" ;;
    link) pm_target="$lp_link" ;;
    clone) pm_target="$lp_co" ;;
  esac
  pm_head_before=$(git -C "$pm_pin" rev-parse HEAD 2>/dev/null)
  h=$(new_home); write_redirect "$h" "$lp_bare"
  cfg="$work/$1-cfg"; seed_pointer "$cfg" "$pm_target"
  elsewhere="$work/$1-elsewhere"; mkdir -p "$elsewhere"
  stub_bin="$work/$1-bin"; make_curl_stub "$stub_bin"
  pm_out=$(cd "$elsewhere" && env -i PATH="$stub_bin:$PATH" HOME="$h" CLAUDE_CONFIG_DIR="$cfg" \
        GIT_CEILING_DIRECTORIES="$elsewhere" CLAUDE_SETTINGS_SEARCH_ROOTS="$work/no-such-root" \
        bash -s -- --cloud < "$INSTALL_SH" 2>&1)
  pm_rc=$?
  pm_head_after=$(git -C "$pm_pin" rev-parse HEAD 2>/dev/null)
  pm_ptr=$(sed -n 's|^@\(.*\)/CLAUDE\.md$|\1|p' "$cfg/CLAUDE.md" 2>/dev/null | head -n1)
  rm -rf "$h"
  return 0
}

# pinmove_source OUT: the path the "found existing checkout" line of OUT names as the source, or nothing.
pinmove_source() {
  printf '%s\n' "$1" | sed -n 's|^.*found existing checkout of [^ ]* at \(.*\); using it as source$|\1|p' | head -n1
}

# pinmove1, pinmove2: the pointer at the pin, then at the link. The log must name the clone as the source.
pinmove1() {
  name="pinmove1: pointer at the live pin <clone>-live-<12 hex>: the log names the clone as the source"
  if [ "$SYMLINK_CAPABLE" != 1 ]; then skip "$name" "$NO_SYMLINK_REASON"; return; fi
  if ! pinmove_run pinmove1 pin; then bad "$name" "fixture: $pm_msg"; return; fi
  src=$(pinmove_source "$pm_out")
  if [ "$pm_rc" -ne 0 ]; then bad "$name" "install.sh exited $pm_rc: $pm_out"
  elif [ -z "$src" ]; then bad "$name" "no found-checkout line: $pm_out"
  elif [ "$(normalize_path "$src")" != "$(normalize_path "$pm_co")" ]; then
    bad "$name" "log names [$src] as the source, want the clone [$pm_co]"
  else ok "$name"; fi
}

pinmove2() {
  name="pinmove2: pointer at the link <clone>-live: the log names the clone as the source"
  if [ "$SYMLINK_CAPABLE" != 1 ]; then skip "$name" "$NO_SYMLINK_REASON"; return; fi
  if ! pinmove_run pinmove2 link; then bad "$name" "fixture: $pm_msg"; return; fi
  src=$(pinmove_source "$pm_out")
  if [ "$pm_rc" -ne 0 ]; then bad "$name" "install.sh exited $pm_rc: $pm_out"
  elif [ -z "$src" ]; then bad "$name" "no found-checkout line: $pm_out"
  elif [ "$(normalize_path "$src")" != "$(normalize_path "$pm_co")" ]; then
    bad "$name" "log names [$src] as the source, want the clone [$pm_co]"
  else ok "$name"; fi
}

# pinmove3: the pin is not moved, by either pointer form. A run that moves it leaves HEAD at origin/main.
pinmove3() {
  name="pinmove3: pointer at the live pin or its link: the pin keeps its HEAD and its place"
  if [ "$SYMLINK_CAPABLE" != 1 ]; then skip "$name" "$NO_SYMLINK_REASON"; return; fi
  for form in pin link; do
    if ! pinmove_run "pinmove3-$form" "$form"; then bad "$name" "fixture ($form): $pm_msg"; return; fi
    if [ "$pm_rc" -ne 0 ]; then bad "$name" "install.sh exited $pm_rc ($form): $pm_out"; return; fi
    if [ ! -d "$pm_pin" ]; then bad "$name" "the pin is gone after a $form run"; return; fi
    if [ "$pm_head_after" != "$pm_head_before" ]; then
      bad "$name" "a $form run moved the pin from $pm_head_before to $pm_head_after"; return
    fi
  done
  ok "$name"
}

# pinmove4: the pointer install.sh writes names the clone, never the pin, for either pointer form.
pinmove4() {
  name="pinmove4: pointer at the live pin or its link: the written pointer names the clone, not the pin"
  if [ "$SYMLINK_CAPABLE" != 1 ]; then skip "$name" "$NO_SYMLINK_REASON"; return; fi
  for form in pin link; do
    if ! pinmove_run "pinmove4-$form" "$form"; then bad "$name" "fixture ($form): $pm_msg"; return; fi
    if [ "$pm_rc" -ne 0 ]; then bad "$name" "install.sh exited $pm_rc ($form): $pm_out"; return; fi
    if [ "$(normalize_path "$pm_ptr")" != "$(normalize_path "$pm_co")" ]; then
      bad "$name" "a $form run wrote the pointer [$pm_ptr], want the clone [$pm_co]"; return
    fi
  done
  ok "$name"
}

# pinmove5: control. The pointer at the clone itself still picks the clone, on the same fixture.
pinmove5() {
  name="pinmove5: control: pointer at the clone itself: the log names the clone and the pointer keeps it"
  if [ "$SYMLINK_CAPABLE" != 1 ]; then skip "$name" "$NO_SYMLINK_REASON"; return; fi
  if ! pinmove_run pinmove5 clone; then bad "$name" "fixture: $pm_msg"; return; fi
  src=$(pinmove_source "$pm_out")
  if [ "$pm_rc" -ne 0 ]; then bad "$name" "install.sh exited $pm_rc: $pm_out"
  elif [ "$(normalize_path "$src")" != "$(normalize_path "$pm_co")" ]; then
    bad "$name" "log names [$src] as the source, want the clone [$pm_co]"
  elif [ "$(normalize_path "$pm_ptr")" != "$(normalize_path "$pm_co")" ]; then
    bad "$name" "pointer [$pm_ptr] is not the clone [$pm_co]"
  else ok "$name"; fi
}

# ---- mergepin cases: a cloud merge run from the clone never moves the live pin off local main ----------
# Decision merge-reinstalls-from-main, ruling 4: only merge/install_from_main.sh moves the pin. That run takes
# the install lock and runs install.sh from the pin. In a cloud run install.sh takes the pin as its source (its
# SCRIPT_DIR branch), so its cloud blocks see the pin, and they must leave it at local main. The one move is the
# rename in merge/install_from_main.sh, and that runs only when local main is past the pin.
# Each case runs the clone's own merge/install_from_main.sh from the clone, as the coordinator's merge does.

s12() { printf '%.12s' "$1"; }

# merge_run TAG SETUP: one cloud run of the clone's merge/install_from_main.sh, from live_pin_fixture TAG built
# with its install files tracked. SETUP is plain; mirror (the clone carries claude-settings.cloudMirror, as a
# clone install.sh made does); or local (main gets one commit that origin/main lacks). Sets mr_co, mr_pin, mr_link,
# mr_origin, mr_want (the clone's local main after SETUP, before the run), mr_path_before (the link's resolved
# path before the run), mr_out, mr_rc, mr_head_after (the pin's HEAD after) and mr_path_after (the link's resolved
# path after). Returns 1 with mr_msg when the fixture or SETUP failed.
merge_run() {
  mr_msg=""
  if ! live_pin_fixture "$1" install; then mr_msg="$lp_msg"; return 1; fi
  mr_co="$lp_co"; mr_pin="$lp_pin"; mr_link="$lp_link"; mr_origin="$lp_origin"
  case "$2" in
    plain) ;;
    mirror) git -C "$mr_co" config claude-settings.cloudMirror true || { mr_msg="cannot set the cloudMirror marker"; return 1; } ;;
    local) git -C "$mr_co" commit -q --allow-empty -m "local main commit" || { mr_msg="cannot commit to the clone's main"; return 1; } ;;
    *) mr_msg="unknown setup $2"; return 1 ;;
  esac
  mr_want=$(git -C "$mr_co" rev-parse --verify -q refs/heads/main)
  mr_path_before=$(realpwd "$mr_link")
  h=$(new_home); write_redirect "$h" "$lp_bare"
  cfg="$work/$1-cfg"; stub_bin="$work/$1-bin"; make_curl_stub "$stub_bin"
  mr_out=$(cd "$mr_co" && env -i PATH="$stub_bin:$PATH" HOME="$h" CLAUDE_CONFIG_DIR="$cfg" CLAUDE_CODE_REMOTE=true \
        GIT_CEILING_DIRECTORIES="$work" CLAUDE_SETTINGS_SEARCH_ROOTS="$work/no-such-root" \
        bash ./merge/install_from_main.sh 2>&1)
  mr_rc=$?
  mr_head_after=$(git -C "$mr_link" rev-parse HEAD 2>/dev/null)
  mr_path_after=$(realpwd "$mr_link")
  rm -rf "$h"
  return 0
}

# merge_pin_check NAME: after mr's run the pin keeps local main, the clone's main did not move, and the pin keeps
# its path. A HEAD at origin/main is the defect's own mark, so it is named first. Returns 1 after a bad line.
merge_pin_check() {
  if [ "$mr_head_after" = "$mr_origin" ] && [ "$mr_origin" != "$mr_want" ]; then
    bad "$1" "the cloud merge moved the live pin to origin/main ($(s12 "$mr_origin")), not local main ($(s12 "$mr_want"))"; return 1
  fi
  if [ "$mr_head_after" != "$mr_want" ]; then
    bad "$1" "the live pin HEAD is ${mr_head_after:-unreadable} after the run, want local main $(s12 "$mr_want")"; return 1
  fi
  if [ "$(git -C "$mr_co" rev-parse --verify -q refs/heads/main)" != "$mr_want" ]; then
    bad "$1" "the run moved the clone's local main off $(s12 "$mr_want")"; return 1
  fi
  if [ "$mr_path_after" != "$mr_path_before" ]; then
    bad "$1" "the live pin path moved from $mr_path_before to ${mr_path_after:-nothing}"; return 1
  fi
  return 0
}

# merge_run_check NAME: the run reached install.sh and exited 0. A run that stopped earlier leaves the pin where it
# was, so that alone would pass for the wrong reason. Returns 1 after a bad line.
merge_run_check() {
  if [ "$mr_rc" -ne 0 ]; then bad "$1" "merge/install_from_main.sh exited $mr_rc: $mr_out"; return 1; fi
  case "$mr_out" in *"Installing from "*) return 0 ;; esac
  bad "$1" "install.sh did not run (no 'Installing from' line): $mr_out"; return 1
}

# mergepin1: a cloud merge from a plain clone leaves the live pin at local main, at its own path.
mergepin1() {
  name="mergepin1: cloud merge, plain clone: the live pin keeps local main and its own path"
  if [ "$SYMLINK_CAPABLE" != 1 ]; then skip "$name" "$NO_SYMLINK_REASON"; return; fi
  if ! merge_run mergepin1 plain; then bad "$name" "fixture: $mr_msg"; return; fi
  if merge_pin_check "$name" && merge_run_check "$name"; then ok "$name"; fi
}

# mergepin2: the same with the clone marked cloudMirror. The mirror resume is the other cloud block that can move the pin.
mergepin2() {
  name="mergepin2: cloud merge, clone marked cloudMirror: the live pin keeps local main and its own path"
  if [ "$SYMLINK_CAPABLE" != 1 ]; then skip "$name" "$NO_SYMLINK_REASON"; return; fi
  if ! merge_run mergepin2 mirror; then bad "$name" "fixture: $mr_msg"; return; fi
  if merge_pin_check "$name" && merge_run_check "$name"; then ok "$name"; fi
}

# mergepin3: control. Local main is one commit past origin/main, a commit origin/main lacks, so the cloud blocks
# cannot move the pin to origin/main. The rename in merge/install_from_main.sh is the only move: the pin path
# becomes <clone>-live-<new 12 hex> and its HEAD is the new local main.
mergepin3() {
  name="mergepin3: control: local main one commit past origin: the cloud merge moves the pin to it by the rename"
  if [ "$SYMLINK_CAPABLE" != 1 ]; then skip "$name" "$NO_SYMLINK_REASON"; return; fi
  if ! merge_run mergepin3 local; then bad "$name" "fixture: $mr_msg"; return; fi
  want_path=$(realpwd "$mr_co-live-$(git -C "$mr_co" rev-parse --short=12 "$mr_want")")
  if ! merge_run_check "$name"; then return; fi
  if [ -z "$want_path" ] || [ "$mr_path_after" != "$want_path" ]; then
    bad "$name" "the pin path is ${mr_path_after:-nothing}, want the rename target ${want_path:-not made}"
  elif [ "$mr_head_after" != "$mr_want" ]; then
    bad "$name" "the pin HEAD is ${mr_head_after:-unreadable}, want the new local main $(s12 "$mr_want")"
  else ok "$name"; fi
}

# ---- guardset1, guardset2: shared_names.py lands inside the atomic guard set -------------------------
# Owner ruling: hooks/shared_names.py is the one home of PROJECT_FROZEN_FILES and config_dir. The guard
# imports it with no fallback copy, so a guard run that loads guard.d/<id>/ must find it there. The flat
# copy is the other way in, and the config watch is a flat hook that must find the set's copy the way
# guard.py finds the set. hooks/git_reads.py is the one home of the git and session reads the guard and
# the janitor share. guard_core.py imports it the same way, so the set holds it too, equal to the flat copy.
guardset_install() {
  install_set_setup
  h=$(new_home); cfg="$h/.claude-cfg"; swap_bin="$work/$1-bin"
  make_swap_bin "$swap_bin"
  make_guard_clone "$work/$1-clone" one
  cp "$REPO_ROOT/hooks/config_watch.py" "$work/$1-clone/hooks/config_watch.py"
  ev="$work/$1-ev"; : > "$ev"
  run_cloud "$work/$1-clone" "$cfg" "$ev" > "$work/$1-run" 2>&1; rc=$?
  set_id=$(sed -n 's/^INSTALL_ID = "\([^"]*\)".*/\1/p' "$cfg/hooks/guard.py" 2>/dev/null | head -n1)
}

guardset1() {
  name="guardset1: the guard set landed by a copy-mode install holds shared_names.py and git_reads.py"
  guardset_install guardset1
  if [ "$rc" -ne 0 ] || [ -z "$set_id" ]; then
    bad "$name" "setup: install exit $rc, stamped id [$set_id]: $(tail -n 3 "$work/guardset1-run")"
  elif [ ! -f "$cfg/hooks/guard.d/$set_id/shared_names.py" ]; then
    bad "$name" "guard.d/$set_id holds [$(ls "$cfg/hooks/guard.d/$set_id" | tr '\n' ' ')], no shared_names.py"
  elif [ ! -f "$cfg/hooks/guard.d/$set_id/git_reads.py" ]; then
    bad "$name" "guard.d/$set_id holds [$(ls "$cfg/hooks/guard.d/$set_id" | tr '\n' ' ')], no git_reads.py"
  elif [ ! -f "$cfg/hooks/git_reads.py" ]; then
    bad "$name" "hooks holds no flat git_reads.py beside the set"
  elif ! cmp -s "$cfg/hooks/guard.d/$set_id/git_reads.py" "$cfg/hooks/git_reads.py"; then
    bad "$name" "the set's git_reads.py differs from the flat copy"
  else ok "$name"
  fi
  rm -rf "$h"
}

guardset3() {
  name="guardset3: the guard set holds question_form.py and precompact_handoff.py, the modules guard.py imports for the question form, each equal to the flat copy"
  guardset_install guardset3
  missing=""
  for m in question_form.py precompact_handoff.py; do
    if [ ! -f "$cfg/hooks/guard.d/$set_id/$m" ]; then
      missing="$missing $m (not in the set)"
    elif ! cmp -s "$cfg/hooks/guard.d/$set_id/$m" "$cfg/hooks/$m"; then
      missing="$missing $m (differs from the flat copy)"
    fi
  done
  if [ "$rc" -ne 0 ] || [ -z "$set_id" ]; then
    bad "$name" "setup: install exit $rc, stamped id [$set_id]: $(tail -n 3 "$work/guardset3-run")"
  elif [ -n "$missing" ]; then
    bad "$name" "guard.d/$set_id holds [$(ls "$cfg/hooks/guard.d/$set_id" | tr '\n' ' ')];$missing"
  else ok "$name"
  fi
  rm -rf "$h"
}

guardset2() {
  name="guardset2: the installed config watch reverts an unasked cap raise with no flat shared_names.py or git_reads.py beside it"
  guardset_install guardset2
  key="CLAUDE_CODE_""SUBAGENT_MODEL"
  proj="$h/proj"; mkdir -p "$proj/.claude"
  file="$proj/.claude/settings.local.json"
  printf '{"env": {"%s": "sonnet"}}\n' "$key" > "$file"
  rm -f "$cfg/hooks/shared_names.py" "$cfg/hooks/git_reads.py"
  # Claude Code sends a native cwd. On Windows the MSYS form (/c/...) is no folder to native Python.
  wproj=$(cd "$proj" && pwd -W 2>/dev/null || pwd)
  payload=$(printf '{"tool_name": "Bash", "tool_input": {"command": "cp x .claude/settings.local.json"}, "cwd": "%s", "session_id": "c"}' "$wproj")
  watch_run() {
    printf '%s' "$payload" | env -u CLAUDE_CODE_SESSION_ID CLAUDE_CONFIG_DIR="$cfg" HOME="$h" PYTHONPATH= \
      python3 -B "$cfg/hooks/config_watch.py" 2> "$work/guardset2-err"
  }
  watch_run > /dev/null; rc_a=$?
  printf '{"env": {"%s": "opus"}}\n' "$key" > "$file"
  out=$(watch_run); rc_b=$?
  if [ "$rc" -ne 0 ] || [ -z "$set_id" ]; then
    bad "$name" "setup: install exit $rc, stamped id [$set_id]"
  elif [ "$rc_a" -ne 0 ] || [ "$rc_b" -ne 0 ]; then
    bad "$name" "the watch exited $rc_a then $rc_b: $(tail -n 1 "$work/guardset2-err")"
  elif ! printf '%s' "$out" | grep -q 'unasked write' || grep -q opus "$file"; then
    bad "$name" "the raise was not reverted and reported: stdout [$out], file [$(cat "$file")], stderr [$(tail -n 1 "$work/guardset2-err")]"
  else ok "$name"
  fi
  rm -rf "$h"
}

# ---- win_sh1, win_sh2, win_sh3: install.sh does nothing under a Windows uname ---------------------------
# install.ps1 is the Windows installer. Run by hand under MINGW, MSYS or CYGWIN, install.sh stops at its top:
# exit 0, one line naming install.ps1, nothing written (no config dir, no log, no lock, no rc-file line, no
# pinned checkout).
win_sh_case() {
  name="$1: install.sh under uname $2 exits 0 at once, names install.ps1, and writes nothing"
  h=$(new_home); cfg="$h/.claude-cfg"; co="$work/$1-checkout"
  make_checkout "$co" "# repo CLAUDE.md $1"
  git -C "$co" branch -q -M main
  cp "$INSTALL_SH" "$co/install.sh"
  make_uname_stub "$work/$1-bin" "$2"

  out=$(cd "$co" && env -i PATH="$work/$1-bin:$PATH" HOME="$h" CLAUDE_CONFIG_DIR="$cfg" \
        bash ./install.sh 2>&1)
  rc=$?
  left=$(home_entries "$h" | head -n 1)
  lines=$(printf '%s\n' "$out" | wc -l | tr -d ' ')

  if [ $rc -ne 0 ]; then
    bad "$name" "exit $rc, want 0: $out"
  elif ! printf '%s' "$out" | grep -q 'install\.ps1'; then
    bad "$name" "output does not name install.ps1: $out"
  elif [ "$lines" -ne 1 ]; then
    bad "$name" "output is $lines lines, want one: $out"
  elif [ -n "$left" ]; then
    bad "$name" "wrote under HOME: $left"
  elif [ -e "$co-live" ]; then
    bad "$name" "made the pinned checkout $co-live"
  else
    ok "$name"
  fi
  rm -rf "$h"
}
win_sh1() { win_sh_case win_sh1 MINGW64_NT-10.0-26200; }
win_sh2() { win_sh_case win_sh2 MSYS_NT-10.0-26200; }
win_sh3() { win_sh_case win_sh3 CYGWIN_NT-10.0-26200; }

# ---- cloud fetch: a clone of the repo at main, refreshed on resume, the tarball only when the clone fails ----
# The GitHub repo is a bare repo built here from this repo's own tarball. Every case's HOME gets a
# .gitconfig from default_home (new_home for a mktemp HOME). A case that clones GitHub sets its own
# with write_redirect. The redirect sends the GitHub URLs to a file:// path (git's insteadOf), and
# protocol.allow refuses every transport but file, so no case reaches the network: a URL the redirect
# misses fails, it does not leak.
make_github_fixture() {
  mkdir -p "$1/src"
  tar -xzf "$work/repo.tar.gz" --strip-components=1 -C "$1/src"
  git init -q -b main "$1/src"
  git -C "$1/src" add -A
  git -C "$1/src" -c user.email=t@example.com -c user.name=t commit -q -m "fixture main"
  git clone -q --bare "$1/src" "$1/bare.git"
}
# Commit one change, named $2, to the fixture's main and push it to the bare repo. With $3 = merge, the
# change is a merge of a two-commit branch named $2, so the history under main is merge-based.
advance_github_fixture() {
  if [ "${3:-}" = merge ]; then
    git -C "$1/src" checkout -q -b "side-$2"
    printf 'side %s a\n' "$2" > "$1/src/SIDE-$2-a.txt"
    git -C "$1/src" add -A
    git -C "$1/src" -c user.email=t@example.com -c user.name=t commit -q -m "side $2 a"
    printf 'side %s b\n' "$2" > "$1/src/SIDE-$2-b.txt"
    git -C "$1/src" add -A
    git -C "$1/src" -c user.email=t@example.com -c user.name=t commit -q -m "side $2 b"
    git -C "$1/src" checkout -q main
    git -C "$1/src" -c user.email=t@example.com -c user.name=t merge -q --no-ff -m "merge $2" "side-$2"
    git -C "$1/src" push -q "$1/bare.git" HEAD:refs/heads/main
    return
  fi
  printf 'advance %s\n' "$2" > "$1/src/RESUME.txt"
  git -C "$1/src" add RESUME.txt
  git -C "$1/src" -c user.email=t@example.com -c user.name=t commit -q -m "advance $2"
  git -C "$1/src" push -q "$1/bare.git" HEAD:refs/heads/main
}
# Commit a branch, named $2, off main that deletes CLAUDE.md, and push it to the bare repo. Main is unchanged.
branch_without_claude_md() {
  git -C "$1/src" checkout -q -b "$2"
  git -C "$1/src" rm -q CLAUDE.md
  git -C "$1/src" -c user.email=t@example.com -c user.name=t commit -q -m "no CLAUDE.md on $2"
  git -C "$1/src" push -q "$1/bare.git" HEAD:refs/heads/$2
  git -C "$1/src" checkout -q main
}
fixture_sha() { git -C "$1/bare.git" rev-parse refs/heads/main; }
# write_redirect HOME BARE: HOME's .gitconfig sends the GitHub repo, with or without ".git", to BARE, and
# allows only the file transport. Caution: `git remote get-url origin` shows the rewritten path, not the
# GitHub URL. install.sh reads the config value, so a clone of this repo passes its origin check here.
# K3 (not K4) catches an install.sh that reads origin through get-url: its resume never refreshes the clone.
write_redirect() {
  {
    printf '[url "file://%s"]\n' "$2"
    printf '\tinsteadOf = https://github.com/shivinate7/claude-settings.git\n'
    printf '\tinsteadOf = https://github.com/shivinate7/claude-settings\n'
    printf '[url "file://%s/no-network/"]\n' "$work"
    printf '\tinsteadOf = https://github.com/\n'
    printf '[protocol]\n\tallow = never\n[protocol "file"]\n\tallow = always\n'
  } > "$1/.gitconfig"
}
# default_home DIR: the default HOME. Its GitHub URLs go to a file:// path that is never created, so a
# clone or fetch fails at once instead of reaching github.com.
default_home() { mkdir -p "$1"; write_redirect "$1" "$work/no-such-github.git"; }
# new_home: a fresh temp HOME with the default .gitconfig. Prints its physical path.
new_home() { d=$(mktemp -d "$work/home.XXXXXX"); d=$(realpwd "$d"); default_home "$d"; printf '%s\n' "$d"; }
# The entries a run left under a fake HOME, not counting its default .gitconfig.
home_entries() { find "$1" -mindepth 1 ! -path "$1/.gitconfig" 2>/dev/null; }
# One cloud install, piped as the setup script runs it: HOME $1, a cwd $2 that is no checkout, the curl
# stub folder $3, and the ref $4 (empty means main). Sets rc and out.
cloud_install() {
  out=$(cd "$2" && env -i PATH="$3:$PATH" HOME="$1" CLAUDE_CONFIG_DIR="$1/.claude-cfg" \
        CLAUDE_SETTINGS_REF="${4:-}" GIT_CEILING_DIRECTORIES="$2" CLAUDE_SETTINGS_SEARCH_ROOTS="$work/no-such-root" \
        bash -s -- --cloud < "$INSTALL_SH" 2>&1)
  rc=$?
}
# The WARN, ERROR and fatal lines of the last install: a failure message names the problem, not the whole log.
install_problems() { printf '%s\n' "$out" | grep -E 'WARN|ERROR|fatal' | head -n 3; }

# ---- caseK1: a fresh cloud install clones the repo at main, sets the marker, and never fetches the tarball ----
caseK1() {
  name="caseK1: a fresh cloud install clones the repo at main, sets the cloudMirror marker, and never fetches the tarball"
  fx="$work/k1-fx"; h="$work/k1-home"; scratch="$work/k1-scratch"; bin="$work/k1-bin"
  mkdir -p "$h" "$scratch"
  make_github_fixture "$fx"; want=$(fixture_sha "$fx")
  write_redirect "$h" "$fx/bare.git"
  make_curl_stub "$bin" fail-tarball
  cloud_install "$h" "$scratch" "$bin"
  co="$h/claude-settings"
  pointer=$(sed -n 's|^@\(.*\)/CLAUDE\.md$|\1|p' "$h/.claude-cfg/CLAUDE.md" 2>/dev/null | head -n1)
  case "$pointer" in "~"/*) pointer="$h${pointer#\~}";; esac

  if [ $rc -ne 0 ]; then
    bad "$name" "install.sh exited $rc: $(install_problems)"
  elif grep -q 'tar\.gz' "$bin/calls" 2>/dev/null; then
    bad "$name" "install.sh fetched the tarball; the clone path did not run"
  elif [ ! -d "$co/.git" ]; then
    bad "$name" "no clone at $co/.git: $(install_problems)"
  elif [ "$(git -C "$co" rev-parse HEAD)" != "$want" ]; then
    bad "$name" "clone HEAD is $(git -C "$co" rev-parse HEAD), want the fixture main $want"
  elif [ "$(git -C "$co" symbolic-ref -q HEAD)" != refs/heads/main ]; then
    bad "$name" "clone is not on branch main: $(git -C "$co" symbolic-ref -q HEAD)"
  elif [ "$(git -C "$co" config --get remote.origin.url)" != "https://github.com/shivinate7/claude-settings.git" ]; then
    bad "$name" "clone origin is $(git -C "$co" config --get remote.origin.url)"
  elif [ "$(git -C "$co" config --get claude-settings.cloudMirror)" != true ]; then
    bad "$name" "clone has no claude-settings.cloudMirror marker"
  elif [ "$(normalize_path "$pointer")" != "$(normalize_path "$co")" ]; then
    bad "$name" "pointer target [$pointer] != clone [$co]"
  else
    ok "$name"
  fi
}

# ---- caseK2: an old tarball copy (no .git) at the clone path is replaced by a clone at main ----
caseK2() {
  name="caseK2: an old tarball copy with no .git at the clone path is replaced by a clone at main"
  fx="$work/k2-fx"; h="$work/k2-home"; scratch="$work/k2-scratch"; bin="$work/k2-bin"
  co="$h/claude-settings"
  mkdir -p "$co" "$scratch"
  tar -xzf "$work/repo.tar.gz" --strip-components=1 -C "$co"
  printf 'only in the old copy\n' > "$co/OLD-TARBALL-ONLY.txt"
  make_github_fixture "$fx"; want=$(fixture_sha "$fx")
  write_redirect "$h" "$fx/bare.git"
  make_curl_stub "$bin" fail-tarball
  cloud_install "$h" "$scratch" "$bin"

  if [ $rc -ne 0 ]; then
    bad "$name" "install.sh exited $rc: $(install_problems)"
  elif [ ! -d "$co/.git" ]; then
    bad "$name" "the old copy at $co still has no .git: $(install_problems)"
  elif [ "$(git -C "$co" rev-parse HEAD)" != "$want" ]; then
    bad "$name" "clone HEAD is $(git -C "$co" rev-parse HEAD), want the fixture main $want"
  elif [ "$(git -C "$co" symbolic-ref -q HEAD)" != refs/heads/main ]; then
    bad "$name" "clone is not on branch main: $(git -C "$co" symbolic-ref -q HEAD)"
  elif [ "$(git -C "$co" config --get claude-settings.cloudMirror)" != true ]; then
    bad "$name" "clone has no claude-settings.cloudMirror marker"
  elif [ -e "$co/OLD-TARBALL-ONLY.txt" ]; then
    bad "$name" "a file only the old copy had survived, so the copy was patched, not replaced"
  else
    ok "$name"
  fi
}

# ---- caseK3: a cloud install on a marked clone refreshes it in place: HEAD moves to the new main commit ----
caseK3() {
  name="caseK3: a cloud install on a marked clone refreshes it in place: HEAD moves to the new main commit"
  fx="$work/k3-fx"; h="$work/k3-home"; scratch="$work/k3-scratch"; bin="$work/k3-bin"
  co="$h/claude-settings"
  mkdir -p "$h" "$scratch"
  make_github_fixture "$fx"; first=$(fixture_sha "$fx")
  write_redirect "$h" "$fx/bare.git"
  make_curl_stub "$bin" fail-tarball
  cloud_install "$h" "$scratch" "$bin"
  if [ $rc -ne 0 ] || [ "$(git -C "$co" rev-parse HEAD 2>/dev/null)" != "$first" ] \
     || [ "$(git -C "$co" config --get claude-settings.cloudMirror 2>/dev/null)" != true ]; then
    bad "$name" "the first install did not leave a marked clone at $first, so there was nothing to resume: $(install_problems)"
    return
  fi

  # A file inside .git that only a refresh in place keeps: a clone that is replaced loses it.
  : > "$co/.git/caseK3-sentinel"
  advance_github_fixture "$fx" second; want=$(fixture_sha "$fx")
  if [ "$want" = "$first" ]; then
    bad "$name" "setup: the fixture main did not move, so the resume has nothing new to fetch"
    return
  fi
  cloud_install "$h" "$scratch" "$bin"

  if [ $rc -ne 0 ]; then
    bad "$name" "install.sh exited $rc on the resume: $(install_problems)"
  elif [ "$(git -C "$co" rev-parse HEAD)" != "$want" ]; then
    bad "$name" "after the resume HEAD is $(git -C "$co" rev-parse HEAD), want the new main $want (the first install was $first)"
  elif [ ! -e "$co/.git/caseK3-sentinel" ]; then
    bad "$name" "the clone was replaced by a new one, not refreshed in place"
  elif [ "$(git -C "$co" symbolic-ref -q HEAD)" != refs/heads/main ]; then
    bad "$name" "after the resume the clone is not on branch main: $(git -C "$co" symbolic-ref -q HEAD)"
  elif [ "$(git -C "$co" config --get claude-settings.cloudMirror)" != true ]; then
    bad "$name" "the resume dropped the cloudMirror marker"
  else
    ok "$name"
  fi
}

# ---- caseK4: an unmarked clone at the clone path is never moved, even when main has a new commit ----
caseK4() {
  name="caseK4: an unmarked clone of the repo on a branch at the clone path stays on its commit when main moves"
  fx="$work/k4-fx"; h="$work/k4-home"; scratch="$work/k4-scratch"; bin="$work/k4-bin"
  co="$h/claude-settings"
  mkdir -p "$h" "$scratch"
  make_github_fixture "$fx"; first=$(fixture_sha "$fx")
  write_redirect "$h" "$fx/bare.git"
  setup_err=$(env -i PATH="$PATH" HOME="$h" git clone -q --depth 1 --branch main \
    https://github.com/shivinate7/claude-settings.git "$co" 2>&1)
  if [ "$(git -C "$co" rev-parse HEAD 2>/dev/null)" != "$first" ] \
     || [ "$(git -C "$co" config --get remote.origin.url)" != "https://github.com/shivinate7/claude-settings.git" ]; then
    bad "$name" "setup: no unmarked clone at $first with the GitHub origin: $setup_err"
    return
  fi

  advance_github_fixture "$fx" second
  if [ "$(fixture_sha "$fx")" = "$first" ]; then
    bad "$name" "setup: the fixture main did not move, so the case proves nothing about a new commit"
    return
  fi
  make_curl_stub "$bin" fail-tarball
  cloud_install "$h" "$scratch" "$bin"

  if [ $rc -ne 0 ]; then
    bad "$name" "install.sh exited $rc: $(install_problems)"
  elif [ "$(git -C "$co" rev-parse HEAD)" != "$first" ]; then
    bad "$name" "the unmarked clone moved to $(git -C "$co" rev-parse HEAD), want it kept at $first"
  elif [ -n "$(git -C "$co" config --get claude-settings.cloudMirror)" ]; then
    bad "$name" "install.sh set the cloudMirror marker on a clone it did not make"
  else
    ok "$name"
  fi
}

# ---- caseK5: a clone that fails falls back to the tarball, which lands CLAUDE.md, and leaves no clone or stray entry ----
caseK5() {
  name="caseK5: a clone that fails falls back to the tarball, which lands CLAUDE.md, and leaves no clone or stray entry"
  h="$work/k5-home"; scratch="$work/k5-scratch"; bin="$work/k5-bin"
  co="$h/claude-settings"
  mkdir -p "$h" "$scratch"
  write_redirect "$h" "$work/k5-missing.git"   # this path is never created, so the clone fails
  make_curl_stub "$bin"
  cloud_install "$h" "$scratch" "$bin"
  left=$(find "$h" -mindepth 1 -maxdepth 1 ! -name .gitconfig ! -name .claude-cfg ! -name claude-settings | head -n 1)

  if [ $rc -ne 0 ]; then
    bad "$name" "install.sh exited $rc: $(install_problems)"
  elif ! grep -q 'tar\.gz' "$bin/calls" 2>/dev/null; then
    bad "$name" "install.sh did not fall back to the tarball after the clone failed"
  elif ! cmp -s "$co/CLAUDE.md" "$REPO_ROOT/CLAUDE.md"; then
    bad "$name" "CLAUDE.md at $co is not the repo's CLAUDE.md: the fallback did not land"
  elif [ -e "$co/.git" ]; then
    bad "$name" "the fallback copy has a .git: a clone was left behind"
  elif [ -n "$left" ]; then
    bad "$name" "a stray entry is left under HOME after the failed clone: $left"
  else
    ok "$name"
  fi
}

# ---- caseK6: a .git at the clone path that is not this repo is kept, and the tarball path runs ----
# The GitHub repo is served here, so a clone would succeed. Only the guard on the clone step keeps
# install.sh from making one; without it the clone replaces the foreign checkout and its .git and sentinel go.
caseK6() {
  name="caseK6: a .git at the clone path with another origin is kept, and the tarball path runs"
  fx="$work/k6-fx"; h="$work/k6-home"; scratch="$work/k6-scratch"; bin="$work/k6-bin"; co="$h/claude-settings"
  mkdir -p "$h" "$scratch"
  make_github_fixture "$fx"
  write_redirect "$h" "$fx/bare.git"
  make_checkout "$co" "# K6 other checkout" "https://gitlab.com/someone/else.git"
  printf 'keep me\n' > "$co/K6-SENTINEL.txt"
  make_curl_stub "$bin"
  cloud_install "$h" "$scratch" "$bin"

  if [ $rc -ne 0 ]; then
    bad "$name" "install.sh exited $rc: $(install_problems)"
  elif [ ! -d "$co/.git" ]; then
    bad "$name" "the .git at $co was removed"
  elif [ "$(git -C "$co" config --get remote.origin.url)" != "https://gitlab.com/someone/else.git" ]; then
    bad "$name" "the origin of the checkout at $co changed to $(git -C "$co" config --get remote.origin.url)"
  elif [ ! -f "$co/K6-SENTINEL.txt" ]; then
    bad "$name" "the sentinel in the checkout at $co was removed"
  elif ! grep -q 'tar\.gz' "$bin/calls" 2>/dev/null; then
    bad "$name" "install.sh did not run the tarball path"
  else
    ok "$name"
  fi
}

# ---- caseK7: a failed clone leaves an old copy with no .git in place, and the tarball path runs ----
caseK7() {
  name="caseK7: a failed clone leaves an old copy with no .git in place, and the tarball path runs"
  h="$work/k7-home"; scratch="$work/k7-scratch"; bin="$work/k7-bin"; co="$h/claude-settings"
  mkdir -p "$co" "$scratch"
  printf 'only in the old copy\n' > "$co/OLD-COPY-ONLY.txt"
  default_home "$h"   # the clone fails: its redirect points at a path that is never created
  make_curl_stub "$bin"
  cloud_install "$h" "$scratch" "$bin"

  if [ $rc -ne 0 ]; then
    bad "$name" "install.sh exited $rc: $(install_problems)"
  elif ! grep -q 'tar\.gz' "$bin/calls" 2>/dev/null; then
    bad "$name" "install.sh did not run the tarball path after the clone failed"
  elif [ "$(cat "$co/OLD-COPY-ONLY.txt" 2>/dev/null)" != "only in the old copy" ]; then
    bad "$name" "the old copy's file at $co did not survive"
  elif [ -e "$co/.git" ]; then
    bad "$name" "a clone was swapped in over the old copy"
  else
    ok "$name"
  fi
}

# ---- caseK8: a ref whose tree lacks CLAUDE.md is not swapped in, and an old copy with no .git survives ----
caseK8() {
  name="caseK8: a ref whose tree lacks CLAUDE.md is not swapped in; an old copy with no .git survives"
  fx="$work/k8-fx"; h="$work/k8-home"; scratch="$work/k8-scratch"; bin="$work/k8-bin"; co="$h/claude-settings"
  mkdir -p "$co" "$scratch"
  printf 'old copy sentinel\n' > "$co/OLD-COPY-ONLY.txt"
  make_github_fixture "$fx"
  branch_without_claude_md "$fx" no-claude-md
  write_redirect "$h" "$fx/bare.git"
  make_curl_stub "$bin"
  cloud_install "$h" "$scratch" "$bin" no-claude-md

  if [ -e "$co/.git" ]; then
    bad "$name" "the clone of the ref without CLAUDE.md was swapped in over the old copy"
  elif [ "$(cat "$co/OLD-COPY-ONLY.txt" 2>/dev/null)" != "old copy sentinel" ]; then
    bad "$name" "the old copy's file at $co did not survive: $(install_problems)"
  else
    ok "$name"
  fi
}

# ---- caseK9: a marked clone whose main has a commit origin lacks keeps that commit on resume ----
caseK9() {
  name="caseK9: a marked clone with a local main commit that origin lacks keeps it on resume, exit 0"
  fx="$work/k9-fx"; h="$work/k9-home"; scratch="$work/k9-scratch"; bin="$work/k9-bin"; co="$h/claude-settings"
  mkdir -p "$h" "$scratch"
  make_github_fixture "$fx"
  write_redirect "$h" "$fx/bare.git"
  make_curl_stub "$bin" fail-tarball
  cloud_install "$h" "$scratch" "$bin"
  if [ $rc -ne 0 ] || [ "$(git -C "$co" config --get claude-settings.cloudMirror 2>/dev/null)" != true ]; then
    bad "$name" "setup: no marked clone after the first install: $(install_problems)"
    return
  fi

  git -C "$co" -c user.email=t@example.com -c user.name=t commit -q --allow-empty -m "local only"
  local_sha=$(git -C "$co" rev-parse HEAD)
  advance_github_fixture "$fx" second
  cloud_install "$h" "$scratch" "$bin"

  if [ $rc -ne 0 ]; then
    bad "$name" "install.sh exited $rc on the resume: $(install_problems)"
  elif [ "$(git -C "$co" rev-parse HEAD)" != "$local_sha" ]; then
    bad "$name" "the resume moved main to $(git -C "$co" rev-parse HEAD) and dropped the local commit $local_sha"
  else
    ok "$name"
  fi
}

# ---- caseK10: a stale clone temp folder older than the run is removed; a newer one is kept ----
caseK10() {
  name="caseK10: a stale claude-settings.clone temp folder is removed by a cloud install; a newer one is kept"
  fx="$work/k10-fx"; h="$work/k10-home"; scratch="$work/k10-scratch"; bin="$work/k10-bin"
  mkdir -p "$h" "$scratch"
  make_github_fixture "$fx"
  write_redirect "$h" "$fx/bare.git"
  make_curl_stub "$bin" fail-tarball
  stale="$h/claude-settings.clone.4242"; newer="$h/claude-settings.clone.4343"
  mkdir -p "$stale" "$newer"
  : > "$stale/partial"; : > "$newer/partial"
  touch -t 202001010000 "$stale"; touch -t 209901010000 "$newer"
  cloud_install "$h" "$scratch" "$bin"

  if [ $rc -ne 0 ]; then
    bad "$name" "install.sh exited $rc: $(install_problems)"
  elif [ -e "$stale" ]; then
    bad "$name" "the stale temp folder $stale is still there"
  elif [ ! -e "$newer" ]; then
    bad "$name" "the newer temp folder $newer was removed"
  else
    ok "$name"
  fi
}

# ---- caseK11: a resume after upstream merges fetches only the new tip, not the history under it ----
# Both installs run on a merge-based main. The first install is a depth-1 clone, so the resume is the
# only fetch that could pull history. A full-history fetch leaves more than the new tip's commits here.
caseK11() {
  name="caseK11: a resume after upstream merges fetches only the new tip, not the merged history"
  fx="$work/k11-fx"; h="$work/k11-home"; scratch="$work/k11-scratch"; bin="$work/k11-bin"; co="$h/claude-settings"
  mkdir -p "$h" "$scratch"
  make_github_fixture "$fx"
  advance_github_fixture "$fx" m1 merge
  advance_github_fixture "$fx" m2 merge
  advance_github_fixture "$fx" m3 merge
  write_redirect "$h" "$fx/bare.git"
  make_curl_stub "$bin" fail-tarball
  cloud_install "$h" "$scratch" "$bin"
  if [ $rc -ne 0 ] || [ "$(git -C "$co" config --get claude-settings.cloudMirror 2>/dev/null)" != true ]; then
    bad "$name" "setup: no marked clone after the first install: $(install_problems)"
    return
  fi
  if [ "$(git -C "$co" rev-parse --is-shallow-repository)" != true ]; then
    bad "$name" "setup: the first install is not a shallow clone, so the resume proves nothing about depth"
    return
  fi
  if [ "$(git -C "$fx/bare.git" rev-list --merges --count main)" -lt 3 ]; then
    bad "$name" "FIXTURE main has fewer than 3 merges, so the history is not merge-based"
    return
  fi

  advance_github_fixture "$fx" m4 merge
  advance_github_fixture "$fx" m5 merge
  want=$(fixture_sha "$fx")
  cloud_install "$h" "$scratch" "$bin"
  if [ $rc -ne 0 ]; then
    bad "$name" "install.sh exited $rc on the resume: $(install_problems)"
  elif [ "$(git -C "$co" rev-parse HEAD)" != "$want" ]; then
    bad "$name" "after the resume HEAD is $(git -C "$co" rev-parse HEAD), want the new main $want"
  else
    n=$(git -C "$co" rev-list --count HEAD)
    if [ "$n" -gt 2 ]; then
      bad "$name" "the clone holds $n commits reachable from main after the resume: the resume fetched history, not the new tip"
    else
      ok "$name"
    fi
  fi
}

# ---- caseL: the merge allow rules come from the source checkout, and the log says what was written ----
# The log names `merge allow rules`, not `merge --confirm allow rules`: the file holds the role rules as well as the confirm rules.
# allow_case NAME HAS: a session's own checkout at $work/NAME-co with settings.json `{}`. HAS=1 adds this repo's
# merge/cloud_allow.json; HAS=0 is a checkout on a commit from before the rules landed. Then one piped cloud install
# from inside it. Sets h, co, rc and out.
allow_case() {
  h=$(new_home); co="$work/$1-co"
  make_checkout "$co" "# $1 content"
  if [ "$2" = 1 ]; then
    mkdir -p "$co/merge"; cp "$REPO_ROOT/merge/cloud_allow.json" "$co/merge/cloud_allow.json"
    git -C "$co" add -A; git -C "$co" -c user.email=t@example.com -c user.name=t commit -q -m rules
  fi
  allow_install
}
# One piped cloud install from inside $co, with HOME $h. Sets rc and out.
allow_install() {
  out=$(cd "$co" && env -i PATH="$PATH" HOME="$h" CLAUDE_CONFIG_DIR="$h/.claude-cfg" \
        CLAUDE_SETTINGS_SEARCH_ROOTS="$work/no-such-root" bash -s -- --cloud < "$INSTALL_SH" 2>&1)
  rc=$?
}
# Every allow rule in the written settings.json, sorted. The source settings.json is `{}`, so all of them were added.
written_allow() { jq -r '.permissions.allow[]?' "$h/.claude-cfg/settings.json" 2>/dev/null | sort; }
want_allow() { jq -r '.permissions.allow[]' "$REPO_ROOT/merge/cloud_allow.json" | sort; }
settings_lines() { printf '%s\n' "$out" | grep settings.json; }

caseL1() {
  name="caseL1: a checkout without merge/cloud_allow.json gets no merge allow rules and a WARNING, never a claim of rules"
  if ! command -v jq >/dev/null 2>&1; then skip "$name" "jq not found"; return; fi
  allow_case l1 0
  sha=$(git -C "$co" rev-parse --short HEAD)
  if [ $rc -ne 0 ]; then
    bad "$name" "install.sh exited $rc: $(install_problems)"
  elif [ -n "$(written_allow)" ]; then
    bad "$name" "allow rules were written with no rules file: $(written_allow | tr '\n' ' ')"
  elif printf '%s\n' "$out" | grep -q "allow rules from\|merge/cloud_allow.json rules)"; then
    bad "$name" "the log claims rules that were not written: $(settings_lines)"
  elif ! printf '%s\n' "$out" | grep -q "WARNING: wrote .* with no merge allow rules: $co at $sha has no rules in merge/cloud_allow.json"; then
    bad "$name" "no WARNING names the checkout and its commit: $(settings_lines)"
  else
    ok "$name"
  fi
  rm -rf "$h"
}

caseL2() {
  name="caseL2: a checkout with merge/cloud_allow.json adds exactly its rules, and the log names the count and the commit"
  if ! command -v jq >/dev/null 2>&1; then skip "$name" "jq not found"; return; fi
  allow_case l2 1
  sha=$(git -C "$co" rev-parse --short HEAD)
  count=$(want_allow | wc -l | tr -d ' ')
  if [ $rc -ne 0 ]; then
    bad "$name" "install.sh exited $rc: $(install_problems)"
  elif [ "$(written_allow)" != "$(want_allow)" ]; then
    bad "$name" "allow rules [$(written_allow | tr '\n' ' ')] != the file's [$(want_allow | tr '\n' ' ')]"
  elif ! printf '%s\n' "$out" | grep -qF "+ $count merge allow rules from $co at $sha)"; then
    bad "$name" "the log does not name the count, the checkout and its commit: $(settings_lines)"
  else
    ok "$name"
  fi
  rm -rf "$h"
}

caseL3() {
  name="caseL3: when jq cannot build settings.json, the log claims no write"
  if ! command -v jq >/dev/null 2>&1; then skip "$name" "jq not found"; return; fi
  h=$(new_home); co="$work/l3-co"
  make_checkout "$co" "# l3 content"
  printf '{ not json\n' > "$co/settings.json"
  git -C "$co" -c user.email=t@example.com -c user.name=t commit -q -am broken
  allow_install
  if printf '%s\n' "$out" | grep -q "^claude-settings: wrote $h/.claude-cfg/settings.json"; then
    bad "$name" "the log claims a write that jq refused: $(settings_lines)"
  elif ! printf '%s\n' "$out" | grep -q "WARNING: could not write $h/.claude-cfg/settings.json"; then
    bad "$name" "no WARNING names the failed write: $(settings_lines)"
  elif [ -e "$h/.claude-cfg/settings.json.tmp" ]; then
    bad "$name" "the partial settings.json.tmp was left behind"
  else
    ok "$name"
  fi
  rm -rf "$h"
}

# ---- caseM: a cloud install moves a clean, detached session checkout to main, and only that one ----------------
# move_fixture NAME: a GitHub fixture whose main went: the repo, then commit OLD without merge/cloud_allow.json,
# then the file back. A session's own checkout at $work/NAME-co (unmarked, origin the GitHub URL) sits detached at
# OLD, as a cloud session left on its creation commit. HOME $h sends GitHub to the fixture. Sets fx, h, co, old, want.
move_fixture() {
  fx="$work/$1-fx"; h="$work/$1-home"; co="$work/$1-co"
  mkdir -p "$h"
  make_github_fixture "$fx"
  gc() { git -C "$fx/src" -c user.email=t@example.com -c user.name=t "$@"; }
  gc rm -q merge/cloud_allow.json; gc commit -q -m "before the rules"
  old=$(git -C "$fx/src" rev-parse HEAD)
  gc checkout -q HEAD~1 -- merge/cloud_allow.json; gc commit -q -m "the rules"
  git -C "$fx/src" push -q "$fx/bare.git" HEAD:refs/heads/main
  want=$(fixture_sha "$fx")
  git clone -q "$fx/bare.git" "$co"
  git -C "$co" config remote.origin.url https://github.com/shivinate7/claude-settings.git
  git -C "$co" checkout -q --detach "$old"
  write_redirect "$h" "$fx/bare.git"
}
move_install() {
  out=$(cd "$co" && env -i PATH="$PATH" HOME="$h" CLAUDE_CONFIG_DIR="$h/.claude-cfg" \
        CLAUDE_SETTINGS_SEARCH_ROOTS="$work/no-such-root" bash -s -- --cloud < "$INSTALL_SH" 2>&1)
  rc=$?
}
merge_rule_count() { jq '[.permissions.allow[]? | select(startswith("Bash(~/.claude/bin/merge"))] | length' "$h/.claude-cfg/settings.json" 2>/dev/null; }
# The count main's merge/cloud_allow.json holds, read from the fixture's main (move_fixture set fx): install must write that many.
want_merge_count() { git -C "$fx/src" show HEAD:merge/cloud_allow.json | jq '.permissions.allow | length'; }

# The count comes from the rules file, which holds the role rules as well as the confirm rules, so a tier added to the file needs no edit here.
# A file with no rules fails: an empty file would otherwise pass as 0 = 0.
caseM1() {
  name="caseM1: a clean, detached checkout on an old main commit moves to main and gets the merge allow rules"
  if ! command -v jq >/dev/null 2>&1; then skip "$name" "jq not found"; return; fi
  move_fixture m1
  move_install
  if [ $rc -ne 0 ]; then
    bad "$name" "install.sh exited $rc: $(install_problems)"
  elif [ "$(git -C "$co" rev-parse HEAD)" != "$want" ] || git -C "$co" symbolic-ref -q HEAD >/dev/null; then
    bad "$name" "the checkout is not detached at main [$want]: $(git -C "$co" rev-parse HEAD) $(install_problems)"
  elif ! [ "$(want_merge_count)" -gt 0 ]; then
    bad "$name" "main's merge/cloud_allow.json in the fixture has no allow rules, so the count proves nothing"
  elif [ "$(merge_rule_count)" != "$(want_merge_count)" ]; then
    bad "$name" "settings.json has $(merge_rule_count) merge allow rules, not $(want_merge_count) from main's merge/cloud_allow.json"
  elif [ "$(git -C "$co" rev-parse --is-shallow-repository)" != false ]; then
    bad "$name" "the fetch made the checkout shallow"
  else
    ok "$name"
  fi
}

caseM2() {
  name="caseM2: a detached checkout with uncommitted changes stays where it is, with a WARN"
  if ! command -v jq >/dev/null 2>&1; then skip "$name" "jq not found"; return; fi
  move_fixture m2
  printf 'local edit\n' >> "$co/README.md"
  move_install
  if [ $rc -ne 0 ]; then
    bad "$name" "install.sh exited $rc: $(install_problems)"
  elif [ "$(git -C "$co" rev-parse HEAD)" != "$old" ] || ! grep -q 'local edit' "$co/README.md"; then
    bad "$name" "the dirty checkout was moved or its edit lost"
  elif ! printf '%s\n' "$out" | grep -q "WARN: the checkout $co has uncommitted changes; left as is"; then
    bad "$name" "no WARN names the dirty checkout: $(install_problems)"
  elif [ "$(merge_rule_count)" != 0 ]; then
    bad "$name" "settings.json got $(merge_rule_count) merge allow rules from a checkout without the file"
  else
    ok "$name"
  fi
}

caseM3() {
  name="caseM3: a checkout on a branch stays on it, with a WARN"
  if ! command -v jq >/dev/null 2>&1; then skip "$name" "jq not found"; return; fi
  move_fixture m3
  git -C "$co" checkout -q -b lane
  move_install
  if [ $rc -ne 0 ]; then
    bad "$name" "install.sh exited $rc: $(install_problems)"
  elif [ "$(git -C "$co" symbolic-ref --short HEAD 2>/dev/null)" != lane ] || [ "$(git -C "$co" rev-parse HEAD)" != "$old" ]; then
    bad "$name" "the branch checkout was moved"
  elif ! printf '%s\n' "$out" | grep -q "WARN: the checkout $co is on branch lane; left as is"; then
    bad "$name" "no WARN names the branch: $(install_problems)"
  else
    ok "$name"
  fi
}

caseM4() {
  name="caseM4: a clean, detached checkout at a commit main does not hold stays, so the commit is not lost"
  if ! command -v jq >/dev/null 2>&1; then skip "$name" "jq not found"; return; fi
  move_fixture m4
  git -C "$co" -c user.email=t@example.com -c user.name=t commit -q --allow-empty -m "local only"
  mine=$(git -C "$co" rev-parse HEAD)
  move_install
  if [ $rc -ne 0 ]; then
    bad "$name" "install.sh exited $rc: $(install_problems)"
  elif [ "$(git -C "$co" rev-parse HEAD)" != "$mine" ]; then
    bad "$name" "the checkout left a commit main does not hold"
  elif ! printf '%s\n' "$out" | grep -q "WARN: the checkout $co is at .* a commit main does not hold; left as is"; then
    bad "$name" "no WARN names the unheld commit: $(install_problems)"
  else
    ok "$name"
  fi
}

# The runner's own HOME is a default home too, so a case that runs git without its own HOME (the
# session_start.sh cases) gets the same redirect as every other case.
default_home "$work/runner-home"; HOME="$work/runner-home"; export HOME

# Optional case filter: `sh hooks/test_install_src.sh caseF4 caseF6` runs only those cases.
# No arguments runs every case. lint/check_unknown_reads_contract.py uses it.
ONLY=" $* "
run() { [ "$ONLY" = "  " ] || case "$ONLY" in *" $1 "*) ;; *) return 0 ;; esac; "$1"; }

run case1
run case2
run case3
run case_origins
run case7
run case8
run pointer_case1
run pointer_case2
run pointer_case3
run pointer_case4
run pointer_case5
run pointer_case6
run case4
run case5
run case6
run case9
run case10
run prune_case1
run prune_case2
run prune_case3
run prune_case4
run prune_case5
run prune_case6
run skills_case1
run skills_case2
run cloud_settings1
run skills_bak1
run skills_bak2
run skills_bak3
run skills_bak4
run skills_bak5
run skills_bak6
run copymode_case1
run backup_case1
run backup_case2
run settings_repeat_case1
run settings_repeat_case2
run settings_repeat_case3
run settings_repeat_case4
run orig_case1
run orig_case2
run bakname_case1
run bakfail_case1
run legacy_case1
run orig_case3
run bin_case1
run bin_case2
run path_case1
run path_case2
run path_case3
run path_case4
run caseF1
run caseF2
run caseF3
run caseF4
run caseF5
run caseF6
run caseF7
run caseF8
run caseG1
run caseG2
run caseG3
run caseG4
run caseG5
run caseG6
run caseG7
run refuse_wt1
run refuse_wt2
run keep_wt1
run keep_plain1
run pinned_wt1
run pinoff1
run pinoff2
run pinoff3
run swap1sh
run lock1sh
run putfile_nogap1
run putfile_prose1
run installlog1
run pinlive1
run pinlive2
run guardset1
run guardset2
run guardset3
run win_sh1
run win_sh2
run win_sh3
run caseK1
run caseK2
run caseK3
run caseK4
run caseK5
run caseK6
run caseK7
run caseK8
run caseK9
run caseK10
run caseK11
run caseL1
run caseL2
run caseL3
run caseM1
run caseM2
run caseM3
run caseM4
run pinmove1
run pinmove2
run pinmove3
run pinmove4
run pinmove5
run mergepin1
run mergepin2
run mergepin3

printf '%s passed, %s failed, %s skipped\n' "$PASS" "$FAIL" "$SKIP"
[ "$FAIL" -eq 0 ]

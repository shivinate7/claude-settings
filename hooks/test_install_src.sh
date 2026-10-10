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
# never touched. SESSION_START_SH lets a case point at a different (e.g. pre-fix) copy of
# the hook, the same way GUARD_UNDER_TEST works in hooks/test_guard.py.

set -u

HERE="$(cd "$(dirname "$0")" && pwd)"
REPO_ROOT="$(cd "$HERE/.." && pwd)"
INSTALL_SH="${INSTALL_SH_UNDER_TEST:-$REPO_ROOT/install.sh}"
SESSION_START_SH_DEFAULT="${SESSION_START_SH_UNDER_TEST:-$REPO_ROOT/hooks/session_start.sh}"

PASS=0
FAIL=0
SKIP=0

ok() { PASS=$((PASS + 1)); printf 'ok   - %s\n' "$1"; }
bad() { FAIL=$((FAIL + 1)); printf 'FAIL - %s: %s\n' "$1" "$2"; }
skip() { SKIP=$((SKIP + 1)); printf 'SKIP - %s: %s\n' "$1" "$2"; }

# Detect once whether this account can create a real symbolic link, and reuse the answer
# everywhere below. Windows needs SeCreateSymbolicLinkPrivilege for `ln -s`. Developer Mode,
# or an elevated account, grants it. Without that privilege, MSYS/git-bash's `ln -sfn` still
# exits 0. It copies the target's bytes into a plain file instead of linking it. A case that
# only checks the exit code never sees this. Checking `[ -L ]` on the result does. This is a
# capability probe, never an OS-name check. A Windows machine with Developer Mode on still
# runs every case below for real.
probe_dir=$(mktemp -d)
printf 'probe\n' > "$probe_dir/target"
ln -sfn "$probe_dir/target" "$probe_dir/link" 2>/dev/null
if [ -L "$probe_dir/link" ]; then
  SYMLINK_CAPABLE=1
else
  SYMLINK_CAPABLE=0
fi
rm -rf "$probe_dir"
NO_SYMLINK_REASON="this account cannot create a real symlink (SeCreateSymbolicLinkPrivilege is not held, turn on Developer Mode or run elevated on Windows)"

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

work=$(mktemp -d); work=$(realpwd "$work")
cleanup() { rm -rf "$work"; }
trap cleanup EXIT

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
case "\$*" in
  *.tar.gz*) cp "$work/repo.tar.gz" "\$out" ;;
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
  elif [ "$(normalize_path "$pointer")" != "$(normalize_path "$co")" ]; then
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
  h=$(mktemp -d); h=$(realpwd "$h"); cfg="$h/.claude-cfg"; scratch="$work/case8-scratch"
  mkdir -p "$scratch"

  stub_bin="$work/case8-bin"
  make_curl_stub "$stub_bin"

  out=$(cd "$scratch" && env -i PATH="$stub_bin:$PATH" HOME="$h" CLAUDE_CONFIG_DIR="$cfg" \
        GIT_CEILING_DIRECTORIES="$scratch" CLAUDE_SETTINGS_SEARCH_ROOTS="$work/no-such-root" \
        bash -s -- --cloud < "$INSTALL_SH" 2>&1)
  rc=$?

  missing=""
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
  elif [ "$(normalize_path "$pointer")" != "$(normalize_path "$expect")" ]; then
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
  elif [ "$(normalize_path "$pointer")" != "$(normalize_path "$expect")" ]; then
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
  elif [ "$(normalize_path "$pointer")" != "$(normalize_path "$co")" ]; then
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
  # fix's same-repository gate passes and the raw content differs, so the line must print.
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

case9() {
  name="case9: unrelated repo with its own CLAUDE.md stays silent (the banchi repro)"
  co="$work/case9-checkout"; pointer_co="$work/case9-pointer-checkout"; cfg="$work/case9-cfg"
  # $co is its own repo, a different origin than the pointer target, with its own,
  # differing CLAUDE.md. This is the live defect: banchi is not a claude-settings clone.
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
  h=$(mktemp -d); h=$(realpwd "$h"); cfg="$h/.claude-cfg"; co="$work/prune1-checkout"
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
  h=$(mktemp -d); h=$(realpwd "$h"); cfg="$h/.claude-cfg"; co="$work/prune2-checkout"
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
  h=$(mktemp -d); h=$(realpwd "$h"); cfg="$h/.claude-cfg"; co="$work/prune3-checkout"
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
  h=$(mktemp -d); h=$(realpwd "$h"); cfg="$h/.claude-cfg"; co="$work/prune4-checkout"
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
  h=$(mktemp -d); h=$(realpwd "$h"); cfg="$h/.claude-cfg"; co="$work/prune5-checkout"
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
  h=$(mktemp -d); h=$(realpwd "$h"); cfg="$h/.claude-cfg"; co="$work/prune6-checkout"
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

caseF1() {
  name="caseF1: pointer on main and behind origin/main prints the stale line"
  co="$work/caseF1-checkout"; cfg="$work/caseF1-cfg"; bare="$work/caseF1-origin.git"
  extra="$work/caseF1-extra"
  git init -q --bare "$bare"
  # A bare repo's HEAD follows init.defaultBranch, which this machine may set to
  # main but a GitHub runner leaves unset, defaulting to master. Force it, the
  # same way force_main_branch already does for checkouts, so this case does not
  # depend on the runner's git config.
  git -C "$bare" symbolic-ref HEAD refs/heads/main
  make_checkout "$co" "# caseF1 content" "$bare"
  force_main_branch "$co"
  ( cd "$co" && git push -q origin main )
  # Advance origin two commits past the checkout's own main, from a second clone, so
  # the checkout is behind by an exact, known count. Captured, not swallowed: a
  # setup step whose exit status nobody reads can silently fail to build the state
  # the case is about to judge the hook against.
  extra_log=$( { git clone -q "$bare" "$extra" \
      && cd "$extra" && git config user.email t@example.com && git config user.name t \
      && echo a >> extra.txt && git add extra.txt && git commit -q -m extra1 \
      && echo b >> extra.txt && git add extra.txt && git commit -q -m extra2 \
      && git push -q origin main ; } 2>&1 )
  extra_rc=$?
  mkdir -p "$cfg"
  printf '@%s/CLAUDE.md\n' "$co" > "$cfg/CLAUDE.md"

  # Precondition: verify the fixture actually built "checkout is 2 behind origin",
  # by comparing the checkout's own main to the bare repo's main directly, never by
  # asking the hook under test. A hook failure and a fixture failure must never be
  # reported as the same thing.
  co_main=$(cd "$co" && git rev-parse main 2>/dev/null)
  bare_main=$(cd "$bare" && git rev-parse main 2>/dev/null)
  behind_built=$(cd "$bare" && git rev-list --count "$co_main..$bare_main" 2>/dev/null)

  if [ "$extra_rc" -ne 0 ]; then
    bad "$name" "FIXTURE failed to advance origin: $extra_log"
    return
  elif [ "$behind_built" != "2" ]; then
    bad "$name" "FIXTURE did not build the behind-by-2 state (checkout vs origin main differ by [$behind_built])"
    return
  fi

  out=$(cd "$co" && CLAUDE_CONFIG_DIR="$cfg" sh "$SESSION_START_SH_DEFAULT" < /dev/null 2>/tmp/cF1err)
  rc=$?
  errsize=$(wc -c < /tmp/cF1err | tr -d '[:space:]'); rm -f /tmp/cF1err

  if [ $rc -ne 0 ]; then
    bad "$name" "exit $rc"
  elif [ "$errsize" != "0" ]; then
    bad "$name" "wrote to stderr"
  elif ! printf '%s\n' "$out" | grep -q "$co is 2 commits behind origin/main"; then
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
  # a clean check, which is the exact defect CI caught (caseF1 read as
  # silent, identical to this case, when the fetch did not land).
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
# continue`) skips every directory entry, so skills/fresh-prose/ never lands: this case is
# the regression test for that defect.
skills_case1() {
  name="skills1: a shipped skill lands as one whole-directory symlink, a person's own skill is untouched"
  if [ "$SYMLINK_CAPABLE" != 1 ]; then
    skip "$name" "$NO_SYMLINK_REASON"
    return
  fi
  h=$(mktemp -d); h=$(realpwd "$h"); cfg="$h/.claude-cfg"; co="$work/skills1-checkout"
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
  h=$(mktemp -d); h=$(realpwd "$h"); cfg="$h/.claude-cfg"; co="$work/skills2-checkout"
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
  bak=$(ls -d "$cfg/skills/"fresh-prose.bak.* 2>/dev/null | head -n1)
  own_content=$(cat "$cfg/skills/my-own/SKILL.md" 2>/dev/null)

  if [ $rc -ne 0 ]; then
    bad "$name" "install.sh exited $rc: $out"
  elif [ -z "$bak" ]; then
    bad "$name" "no fresh-prose.bak.* directory was created; the old content was dropped"
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

# ---- copy-mode case: a fake `ln` that copies instead of linking (D: copy-mode-overwrites- ---
# no-backup) must not pile up .bak entries across repeated runs. This is the exact fault
# measured 2026-10-03: Git Bash's `ln -sfn` on a Windows account without symlink rights
# makes a real copy, so the next run sees a real file/dir where land_dir()/land_skills_dir()
# expect a symlink, and backs it up before copying again. Builds a stub `ln` first on PATH
# that always copies, so this reproduces without needing a literal no-symlink-rights host.
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
  name="copymode1: two runs under a copying \`ln\` leave no .bak and land current content"
  h=$(mktemp -d); h=$(realpwd "$h"); cfg="$h/.claude-cfg"; co="$work/copymode1-checkout"
  make_checkout "$co" "# copymode1 content"
  cp "$INSTALL_SH" "$co/install.sh"
  mkdir -p "$co/skills/sample-skill"
  printf 'v1\n' > "$co/skills/sample-skill/SKILL.md"
  printf 'agent v1\n' > "$co/agents/sample.md"

  fake_bin="$work/copymode1-bin"
  make_fake_ln_bin "$fake_bin"
  run1=$(cd "$co" && env -i PATH="$fake_bin:$PATH" HOME="$h" CLAUDE_CONFIG_DIR="$cfg" \
         bash ./install.sh 2>&1); rc1=$?

  # Change a skill's source content between runs, the way a real `git pull` would.
  printf 'v2\n' > "$co/skills/sample-skill/SKILL.md"

  run2=$(cd "$co" && env -i PATH="$fake_bin:$PATH" HOME="$h" CLAUDE_CONFIG_DIR="$cfg" \
         bash ./install.sh 2>&1); rc2=$?

  baks=$(find "$cfg" -name '*.bak.*' 2>/dev/null)
  skill_got=$(cat "$cfg/skills/sample-skill/SKILL.md" 2>/dev/null)
  agent_got=$(cat "$cfg/agents/sample.md" 2>/dev/null)
  agent_src=$(cat "$co/agents/sample.md" 2>/dev/null)

  if [ $rc1 -ne 0 ]; then
    bad "$name" "run 1 exited $rc1: $run1"
  elif [ $rc2 -ne 0 ]; then
    bad "$name" "run 2 exited $rc2: $run2"
  elif [ -n "$baks" ]; then
    bad "$name" "run 2 left .bak entries under $cfg:$baks"
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
  h=$(mktemp -d); h=$(realpwd "$h"); cfg="$h/.claude-cfg"; co="$work/backup1-checkout"
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
  name="backup2: a pre-existing real settings.json is moved to a backup, not replaced silently"
  if [ "$SYMLINK_CAPABLE" != 1 ]; then
    skip "$name" "$NO_SYMLINK_REASON"
    return
  fi
  h=$(mktemp -d); h=$(realpwd "$h"); cfg="$h/.claude-cfg"; co="$work/backup2-checkout"
  make_checkout "$co" "# backup2 content"
  cp "$INSTALL_SH" "$co/install.sh"
  mkdir -p "$cfg"
  printf '{"mine": true}\n' > "$cfg/settings.json"

  out=$(run_local_install "$co" "$h" "$cfg"); rc=$?
  bak=$(ls "$cfg"/settings.json.bak.* 2>/dev/null | head -n1)

  if [ $rc -ne 0 ]; then
    bad "$name" "install.sh exited $rc: $out"
  elif [ -z "$bak" ]; then
    bad "$name" "no settings.json.bak.* file; the person's own settings.json was lost"
  elif [ "$(cat "$bak")" != '{"mine": true}' ]; then
    bad "$name" "the backup does not hold the original content"
  elif [ ! -L "$cfg/settings.json" ]; then
    bad "$name" "settings.json is not a symlink after install"
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
  h=$(mktemp -d); h=$(realpwd "$h"); cfg="$h/.claude-cfg"; co="$work/bin1-checkout"
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
  h=$(mktemp -d); h=$(realpwd "$h"); cfg="$h/.claude-cfg"; co="$work/bin2-checkout"
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
  h=$(mktemp -d); h=$(realpwd "$h"); cfg="$h/.claude-cfg"; co="$work/path1-checkout"
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
  elif [ "$marks" != 1 ] || [ "$lines" != 1 ]; then bad "$name" "~/.zshrc holds $marks marks and $lines export lines, expected 1 and 1"
  elif [ "$(cat "$h/.zshrc")" != "$after1" ]; then bad "$name" "second run changed ~/.zshrc"
  elif ! head -1 "$h/.zshrc" | grep -qF "# my zshrc"; then bad "$name" "existing rc content was not kept"
  elif [ -e "$h/.bashrc" ]; then bad "$name" "a zsh SHELL also wrote ~/.bashrc"
  else ok "$name"; fi
  rm -rf "$h"
}

path_case2() {
  name="path2: bash SHELL gets the marked block in ~/.bashrc, not in ~/.zshrc"
  h=$(mktemp -d); h=$(realpwd "$h"); cfg="$h/.claude-cfg"; co="$work/path2-checkout"
  make_checkout "$co" "# path2 content"
  cp "$INSTALL_SH" "$co/install.sh"
  if [ -e "$h/.bashrc" ] || [ -e "$h/.zshrc" ]; then
    bad "$name" "fixture precondition failed: rc files exist"; rm -rf "$h"; return
  fi
  out=$(run_path_install "$co" "$h" "$cfg" /bin/bash); rc=$?
  if [ $rc -ne 0 ]; then bad "$name" "install.sh exited $rc: $out"
  elif ! grep -qF "$PATH_MARK" "$h/.bashrc" 2>/dev/null; then bad "$name" "~/.bashrc has no marker line"
  elif ! grep -qF "$PATH_LINE" "$h/.bashrc"; then bad "$name" "~/.bashrc has no export line"
  elif [ -e "$h/.zshrc" ]; then bad "$name" "a bash SHELL wrote ~/.zshrc"
  else ok "$name"; fi
  rm -rf "$h"
}

path_case3() {
  name="path3: SHELL unset under set -u does not abort install and writes ~/.bashrc"
  h=$(mktemp -d); h=$(realpwd "$h"); cfg="$h/.claude-cfg"; co="$work/path3-checkout"
  make_checkout "$co" "# path3 content"
  cp "$INSTALL_SH" "$co/install.sh"
  if [ -e "$h/.bashrc" ]; then bad "$name" "fixture precondition failed: ~/.bashrc exists"; rm -rf "$h"; return; fi
  # bash re-creates SHELL at startup, so `env -i bash ./install.sh` would not leave it unset.
  # Unset it inside the shell, assert it is unset (exit 99 if not), then source the installer.
  out=$( cd "$co" && env -i PATH="$PATH" HOME="$h" CLAUDE_CONFIG_DIR="$cfg" \
         bash -c 'unset SHELL; [ -z "${SHELL+x}" ] || exit 99; source ./install.sh' 2>&1 ); rc=$?
  if [ $rc -eq 99 ]; then bad "$name" "fixture precondition failed: SHELL could not be unset"
  elif [ $rc -ne 0 ]; then bad "$name" "install.sh exited $rc: $out"
  elif ! grep -qF "$PATH_MARK" "$h/.bashrc" 2>/dev/null; then bad "$name" "~/.bashrc has no marker line"
  else ok "$name"; fi
  rm -rf "$h"
}

path_case4() {
  name="path4: --cloud and CLAUDE_CODE_REMOTE=true touch no rc file"
  h=$(mktemp -d); h=$(realpwd "$h"); cfg="$h/.claude-cfg"; co="$work/path4-checkout"
  make_checkout "$co" "# path4 content"
  cp "$INSTALL_SH" "$co/install.sh"
  printf '# my bashrc\n' > "$h/.bashrc"; printf '# my zshrc\n' > "$h/.zshrc"
  out1=$( cd "$co" && env -i PATH="$PATH" HOME="$h" CLAUDE_CONFIG_DIR="$cfg" SHELL=/bin/bash bash ./install.sh --cloud 2>&1 ); rc1=$?
  out2=$( cd "$co" && env -i PATH="$PATH" HOME="$h" CLAUDE_CONFIG_DIR="$cfg" SHELL=/usr/bin/zsh CLAUDE_CODE_REMOTE=true bash ./install.sh 2>&1 ); rc2=$?
  if [ $rc1 -ne 0 ] || [ $rc2 -ne 0 ]; then bad "$name" "install.sh exited rc1=$rc1 rc2=$rc2: $out1 / $out2"
  elif [ "$(cat "$h/.bashrc")" != "# my bashrc" ]; then bad "$name" "~/.bashrc was changed in cloud mode"
  elif [ "$(cat "$h/.zshrc")" != "# my zshrc" ]; then bad "$name" "~/.zshrc was changed in cloud mode"
  else ok "$name"; fi
  rm -rf "$h"
}

caseF5() {
  name="caseF5: outside a git tree with no pointer file, stays fully silent, exit 0"
  outside="$work/caseF5-not-a-repo"; cfg="$work/caseF5-cfg"
  mkdir -p "$outside"
  # No CLAUDE_CONFIG_DIR contents at all: the pointer file itself is missing.

  out=$(cd "$outside" && CLAUDE_CONFIG_DIR="$cfg" GIT_CEILING_DIRECTORIES="$outside" \
        sh "$SESSION_START_SH_DEFAULT" < /dev/null 2>/tmp/cF5err)
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
run copymode_case1
run backup_case1
run backup_case2
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
run caseG1
run caseG2
run caseG3
run caseG4
run caseG5
run caseG6
run caseG7

printf '%s passed, %s failed, %s skipped\n' "$PASS" "$FAIL" "$SKIP"
[ "$FAIL" -eq 0 ]

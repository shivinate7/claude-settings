#!/bin/sh
# install.sh under the real Git Bash uname, no stub: it exits 0 at once, prints one line that names
# install.ps1, and writes nothing. HOME is a temp folder, so the default target (HOME/.claude) is temp
# too. A run that does install leaves its files there: bin/rm, the PATH line in .bashrc, the config
# folder, the install log. The check is that HOME holds no file at all afterwards.
#
#   sh hooks/test_install_windows.sh
#
# Windows only (a MINGW, MSYS or CYGWIN uname); elsewhere it prints SKIP and exits 0.
# INSTALL_SH_UNDER_TEST runs another copy of install.sh, as in hooks/test_install_src.sh. That suite
# covers the same guard under a stub uname (win_sh1 to win_sh3), on the Linux checks job and the macOS job in CI.

set -u

HERE="$(cd "$(dirname "$0")" && pwd)"
. "$HERE/../lint/_test_git.sh"  # test-run signing opt-out
REPO_ROOT="$(cd "$HERE/.." && pwd)"
INSTALL_SH="${INSTALL_SH_UNDER_TEST:-$REPO_ROOT/install.sh}"
NAME="install.sh under the real Windows uname exits 0 at once, names install.ps1, and writes nothing"

case "$(uname -s)" in
  MINGW*|MSYS*|CYGWIN*) ;;
  *) printf 'SKIP - %s: uname is %s\n' "$NAME" "$(uname -s)"; exit 0 ;;
esac

work=$(mktemp -d)
cleanup() { rm -rf "$work"; }
trap cleanup EXIT

# A small clone, so a run that does install finds its checkout and never reaches for the network.
h="$work/home"; co="$work/clone"
mkdir -p "$h" "$co"
tr -d '\r' < "$INSTALL_SH" > "$co/install.sh"   # a CRLF checkout (autocrlf) would stop bash at the first line end
cp "$REPO_ROOT/landed-dirs.txt" "$co/landed-dirs.txt"
sed 's/#.*//; s/[[:space:]]//g' "$co/landed-dirs.txt" | grep -v '^$' | while read -r sub; do mkdir -p "$co/$sub"; done
printf '# fixture\n' > "$co/CLAUDE.md"
printf '{}\n' > "$co/settings.json"
( cd "$co" && git init -q -b main && git config user.email t@example.com && git config user.name t \
    && git remote add origin https://github.com/shivinate7/claude-settings.git \
    && git add -A && git commit -q -m init ) || { printf 'FAIL - %s: could not build the fixture clone\n' "$NAME"; exit 1; }

out=$(cd "$co" && env -i PATH="$PATH" HOME="$h" timeout 60 bash ./install.sh 2>&1)
rc=$?
left=$(find "$h" -mindepth 1 2>/dev/null | head -n 5 | tr '\n' ' ')
lines=$(printf '%s\n' "$out" | wc -l | tr -d ' ')

if [ "$rc" -eq 124 ]; then
  why="did not exit within 60 s"
elif [ "$rc" -ne 0 ]; then
  why="exit $rc, want 0: $out"
elif ! printf '%s' "$out" | grep -q 'install\.ps1'; then
  why="output does not name install.ps1: $out"
elif [ "$lines" -ne 1 ]; then
  why="output is $lines lines, want one: $out"
elif [ -n "$left" ]; then
  why="wrote under HOME: $left"
else
  printf 'ok   - %s\n' "$NAME"
  exit 0
fi
printf 'FAIL - %s: %s\n' "$NAME" "$why"
exit 1

#!/bin/sh
# Shared command-hook wrapper. Takes one argument: a path relative to the Claude config
# dir (e.g. "lint/report_gate.py"). It resolves that path, exits 0 if the file is
# missing, then execs python3 if available, else python, else exits 0.
#
# This replaces the near-identical "[ -f ... ] || exit 0; for p in python3 python; do
# ... done; exit 0" boilerplate that used to be copy-pasted into every command hook
# entry in settings.json. One shared script means one place to fix.
d="${CLAUDE_CONFIG_DIR:-$HOME/.claude}"
g="$d/$1"
[ -f "$g" ] || exit 0
for p in python3 python; do
  command -v "$p" >/dev/null 2>&1 && exec "$p" "$g"
done
exit 0

#!/usr/bin/env bash
# Runs the plain-english-map check (MAP1 to MAP9) at the repo root. The exit code is the verdict: 1 when any check says FAIL.
# It installs typescript first, in the form mod-tests.sh uses. The map cites .mjs files (docs/map/homes.md), so MAP8 and MAP9
# read them with the typescript parser (lib/lazy-typescript.mjs), and a bare checkout has no node_modules.
# The command is here, not inline in checks.yml, because lint/test_windows_split.py keeps the name of the skill out of every run step.
set -e
[ -d node_modules/typescript ] || npm ci --ignore-scripts --no-audit --no-fund
exec node skills/plain-english-map/scripts/map-check.mjs

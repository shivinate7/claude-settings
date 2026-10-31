#!/usr/bin/env bash
# Runs the plain-english-map check (MAP1 to MAP9) at the repo root. The exit code is the verdict: 1 when any check says FAIL.
# It needs no `npm ci`: no pilot fact cites a JS or TS file, and MAP8 never loads typescript here (measured). A later fact on a
# JS or TS file reads as unknown, and MAP9 then fails and says so.
# The command is here, not inline in checks.yml, because lint/test_windows_split.py keeps the name of the skill out of every run step.
exec node skills/plain-english-map/scripts/map-check.mjs

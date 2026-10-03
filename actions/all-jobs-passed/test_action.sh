#!/usr/bin/env bash
# Red proof: the gate must fail on failure, cancelled, skipped and empty needs; pass on all success.
set -u
here="$(cd "$(dirname "$0")" && pwd)"
bad=0
expect() { # want label json
  NEEDS="$3" bash "$here/check.sh" >/dev/null 2>&1; got=$?
  if { [ "$1" = pass ] && [ $got -eq 0 ]; } || { [ "$1" = fail ] && [ $got -ne 0 ]; }; then echo "ok   $2"
  else echo "FAIL $2 (exit $got, wanted $1)"; bad=1; fi
}
expect pass all-success '{"a":{"result":"success"},"b":{"result":"success"}}'
expect fail one-failed  '{"a":{"result":"success"},"b":{"result":"failure"}}'
expect fail one-cancelled '{"a":{"result":"cancelled"}}'
expect fail one-skipped '{"a":{"result":"success"},"b":{"result":"skipped"}}'
expect fail empty-needs '{}'
exit $bad

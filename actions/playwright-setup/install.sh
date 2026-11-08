#!/usr/bin/env bash
# The one install script of actions/playwright-setup. The composite action and bin/ci-job both call it, so each command lives here once.
#   install.sh deps      npm ci in $DIR (only when NPM_CI is true in any case, as GitHub's == 'true' reads it, or unset; any other value, empty too, skips it), then pin.sh, which writes version, os and cli to $GITHUB_OUTPUT.
#   install.sh browsers  `node "$CLI" install $BROWSERS`, then the opt-in apt step when $DEPS is set (webkit, firefox; Linux only; CAP s).
#   install.sh local     bin/ci-job's call: npm ci and pin.sh into a temp GITHUB_OUTPUT. It downloads no browser and runs no apt:
#                        decision playwright-install-once, one Playwright install, never from an agent.
# Cost of `local`: one npm ci of $DIR (1.1 s for .github/shoot, 1 run, cloud container, warm npm cache) and two node calls in pin.sh (the playwright-core path, then its version).
set -euo pipefail
here=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)

npm_ci() {
  case "${NPM_CI-true}" in [Tt][Rr][Uu][Ee]) ;; *) return 0 ;; esac  # a case pattern, not ${v,,}: macOS bash 3.2 has no case change
  npm ci --prefix "${DIR:?}" --ignore-scripts --no-audit --no-fund
}

browsers() {
  # No --with-deps, on purpose. On a cache hit this only checks the browsers are there.
  # shellcheck disable=SC2086  # BROWSERS is a space-separated list, split on purpose
  node "$CLI" install $BROWSERS
  # Opt-in apt for WebKit and Firefox only: ubuntu-latest lacks their libraries (libgtk-4, gstreamer).
  # CAP is 300 s. The slow mirror on 2026-10-26 ran past 11 min, so the cap ends that case in under
  # half the time. The normal apt time is unmeasured.
  [ -n "${DEPS:-}" ] || return 0
  # A blank value would run install-deps with no names, which installs every browser's libraries.
  [ -n "${DEPS//[[:space:]]/}" ] || { echo "::error::system-deps holds no browser name. Name webkit or firefox, or leave it unset."; return 1; }
  for b in $DEPS; do
    case "$b" in
      webkit|firefox) ;;
      *) echo "::error::system-deps takes webkit or firefox only, not '$b'. Chromium needs no apt."; return 1 ;;
    esac
  done
  [ "${RUNNER_OS:-}" = Linux ] || return 0
  # shellcheck disable=SC2086  # DEPS is a space-separated list, split on purpose
  # -k 30: a process that ignores SIGTERM at the cap is killed 30 s later.
  timeout -k 30 "$CAP" node "$CLI" install-deps $DEPS || {
    rc=$?
    [ "$rc" = 124 ] && echo "::error::system-deps apt step passed its $CAP s cap." >&2
    return "$rc"
  }
}

case "${1:-}" in
  deps) npm_ci; bash "$here/pin.sh" ;;
  browsers) browsers ;;
  local)
    out=$(mktemp)
    trap 'rm -f "$out"' EXIT
    npm_ci
    GITHUB_OUTPUT=$out bash "$here/pin.sh"
    ;;
  *) echo "usage: install.sh deps|browsers|local" >&2; exit 2 ;;
esac

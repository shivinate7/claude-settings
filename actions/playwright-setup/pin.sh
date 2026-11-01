#!/usr/bin/env bash
# Prints the pinned playwright-core version, its CLI path and the OS id to GITHUB_OUTPUT. playwright and
# @playwright/test both depend on playwright-core, which owns the browser download.
# The OS id keys the browser cache: a browser built for one OS release fails on another. On Linux it
# is ID-VERSION_ID from os-release (ubuntu-24.04). Elsewhere it is ImageOS, else RUNNER_OS.
set -euo pipefail
if [ "${RUNNER_OS:-}" = Linux ]; then
  # A subshell, so os-release variables never leak into this script.
  os_id=$(. "${OS_RELEASE:-/etc/os-release}" && echo "${ID:?}-${VERSION_ID:?}") || {
    echo "::error::No ID and VERSION_ID in ${OS_RELEASE:-/etc/os-release}." >&2
    exit 1
  }
else
  os_id=${ImageOS:-${RUNNER_OS:-unknown}}
fi
dir=$(cd "${DIR:?}" && pwd)
pkg=$(node -p "require.resolve('playwright-core/package.json', {paths: [process.argv[1]]})" "$dir" 2>/dev/null) || {
  echo "::error::No playwright-core under $dir/node_modules. Pin playwright or @playwright/test in $dir/package.json." >&2
  exit 1
}
version=$(node -p "require(process.argv[1]).version" "$pkg")
echo "version=$version" >> "${GITHUB_OUTPUT:?}"
echo "os=$os_id" >> "$GITHUB_OUTPUT"
echo "cli=$(dirname "$pkg")/cli.js" >> "$GITHUB_OUTPUT"
echo "Playwright $version on $os_id"

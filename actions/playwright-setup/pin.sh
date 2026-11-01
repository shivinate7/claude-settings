#!/usr/bin/env bash
# Prints the pinned playwright-core version, its CLI path and the OS id to GITHUB_OUTPUT. playwright and
# @playwright/test both depend on playwright-core, which owns the browser download.
# The OS id keys the browser cache: a browser built for one OS release fails on another. On Linux it
# is ID-VERSION_ID from os-release (ubuntu-24.04). A rolling distro has no VERSION_ID, so it is ID alone.
# With no os-release file it is RUNNER_OS. Each fallback warns. Elsewhere it is ImageOS, else RUNNER_OS.
set -euo pipefail
if [ "${RUNNER_OS:-}" = Linux ]; then
  os_id=$RUNNER_OS
  release=${OS_RELEASE:-/etc/os-release}
  if [ -r "$release" ]; then
    # A subshell, so os-release variables never leak out. ID and VERSION_ID are unset first, so a value
    # exported in the environment never fills a gap in the file.
    fields=$(unset ID VERSION_ID; . "$release" 2>/dev/null; printf '%s\n%s\n' "${ID:-}" "${VERSION_ID:-}")
    # The command substitution strips the trailing newline, so `read` of an empty last field hits EOF.
    { read -r id || true; read -r ver || true; } <<< "$fields"
    if [ -z "$id" ]; then
      echo "::warning::$release has no ID. The browser cache key uses the OS name only."
    elif [ -z "$ver" ]; then
      os_id=$id
      echo "::warning::$release has no VERSION_ID. The browser cache key uses $id only."
    else
      os_id=$id-$ver
    fi
  else
    echo "::warning::No os-release file at $release. The browser cache key uses the OS name only."
  fi
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

#!/usr/bin/env bash
# Prints the pinned playwright-core version and its CLI path to GITHUB_OUTPUT. playwright and
# @playwright/test both depend on playwright-core, which owns the browser download.
set -euo pipefail
dir=$(cd "${DIR:?}" && pwd)
pkg=$(node -p "require.resolve('playwright-core/package.json', {paths: [process.argv[1]]})" "$dir" 2>/dev/null) || {
  echo "::error::No playwright-core under $dir/node_modules. Pin playwright or @playwright/test in $dir/package.json." >&2
  exit 1
}
version=$(node -p "require(process.argv[1]).version" "$pkg")
echo "version=$version" >> "${GITHUB_OUTPUT:?}"
echo "cli=$(dirname "$pkg")/cli.js" >> "$GITHUB_OUTPUT"
echo "Playwright $version"

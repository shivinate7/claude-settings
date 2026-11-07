# MAP11 misses a shell command inside quotes

- **What.** `out="$(python3 src/retry.py)"` reads as not loading `src/retry.py`, because `blankShell` blanks all text inside double quotes, so a common idiom fails MAP11 (a false fail).
- **Where.** `skills/plain-english-map/scripts/lib/source-text.mjs` `blankShell`, and `skills/plain-english-map/scripts/lib/fact-readers.mjs` `shellWords`.
- **Decision.** `map-tested-by-line` (the map names a file's tests on a checked tested-by line).
- **Retire.** `shellWords` reads the words inside a `$(...)` in double quotes, and a fixture test with `out="$(python3 src/retry.py)"` passes MAP11.

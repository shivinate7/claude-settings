# MAP11 misses a shell command inside quotes

- **What.** A quoted string is one word, blanks included. `shellLoads` skips a word that still holds `$` after a leading `$NAME/` anchor is dropped. So `out="$(python3 src/retry.py)"` does not load `src/retry.py`: its one word is `$(python3 src/retry.py)`, a false fail. Unquoted `out=$(python3 src/retry.py)` matches, so for that idiom the gap is quoting only. `sh -c "python3 src/retry.py"` and `bash -c '...'` read as no match: the one word holds a blank, so it never equals the path. `"$(dirname "$0")/../src/retry.py"` reads as no match because its word holds `$`. All fail closed.
- **Where.** `skills/plain-english-map/scripts/lib/fact-readers.mjs` `shellWords` and `shellLoads`.
- **Decision.** `map-tested-by-line` (the map names a file's tests on a checked tested-by line).
- **Retire.** `shellWords` reads the words inside a `$(...)` in double quotes, and a fixture test with `out="$(python3 src/retry.py)"` passes MAP11.

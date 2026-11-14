# MAP11 reads a shell test only through its quoted strings

- **What.** MAP11 reads a shell test through its quoted strings. A bare word that names the file, as in `python3 src/x.py`, is no string, and a quoted path that starts with a variable, as in `python3 "$ROOT/src/x.py"`, names no file. MAP11 reads such a test as not loading the file, and fails.
- **Where.** `skills/plain-english-map/scripts/lib/source-text.mjs`, `shellStrings`, and `skills/plain-english-map/scripts/lib/fact-readers.mjs`, `readShellLoads`.
- **Decision.** `map-tested-by-line` (the map names a file's tests on a checked tested-by line).
- **Retire.** A fixture shell test that runs its file by `python3 src/x.py`, or by `python3 "$ROOT/src/x.py"`, passes MAP11.

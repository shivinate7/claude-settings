# MAP11 cannot read a shell test

- **What.** MAP11 has no reader for a shell test. A tested-by line that names a `.sh` test fails as an unknown read, even when the test runs the file.
- **Where.** `skills/plain-english-map/scripts/map-check.mjs`, check MAP11.
- **Decision.** `map-tested-by-line` (the map names a file's tests on a checked tested-by line).
- **Retire.** MAP11 reads shell string literals through `blankShell` in `scripts/lib/source-text.mjs`, and a test with a `.sh` tested-by link passes.

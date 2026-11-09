# MAP11 misses a path built from pieces

- **What.** MAP11 counts only a whole path string. A test that runs `os.path.join(ROOT, "src", "x.py")` or `path.join(__dirname, "..", "src", "x.ts")` reads as not loading the file, and MAP11 fails.
- **Where.** `skills/plain-english-map/scripts/lib/py-facts.py` and `scripts/lib/fact-readers.mjs`, the `loads` op.
- **Decision.** `map-tested-by-line` (the map names a file's tests on a checked tested-by line).
- **Retire.** The `loads` op joins literal-only `join` calls, and a fixture test for each language passes MAP11.

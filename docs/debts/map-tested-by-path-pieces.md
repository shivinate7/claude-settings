# MAP11 misses a path joined from a variable

- **What.** In a test under a `tests/` folder, MAP11 reads a `join` only when every piece is a string literal. A test that runs `path.join(__dirname, "..", "src", "x.ts")` or `os.path.join(ROOT, "src", "x.py")` reads as not loading the file, and MAP11 fails.
- **Where.** `skills/plain-english-map/scripts/lib/fact-readers.mjs`, `namedFiles`, and `skills/plain-english-map/scripts/lib/py-facts.py`, `literal_joins`.
- **Decision.** `map-tested-by-line` (the map names a file's tests on a checked tested-by line).
- **Retire.** A fixture test under `tests/` that joins from `__dirname` (JavaScript) or from `ROOT` (Python) passes MAP11.

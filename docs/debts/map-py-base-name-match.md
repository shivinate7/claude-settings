# The Python import reader matches by base name alone

- **What.** `py-facts.py` resolves an import by the module's last name. A test with stdlib `import queue` reads as loading a mapped `jobs/queue.py`, so MAP11 passes a false link. A MAP9 `uses` fact reads the same way.
- **Where.** `skills/plain-english-map/scripts/lib/py-facts.py`, `resolve`.
- **Decision.** `map-tested-by-line` (the map names a file's tests on a checked tested-by line).
- **Retire.** `resolve` matches the dotted path against the file's path from a source root, and a fixture test with stdlib `import queue` fails MAP11 for `jobs/queue.py`.

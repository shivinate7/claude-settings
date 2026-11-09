# MAP11 and MAP9 cannot read an import by path alias

- **What.** The import reader skips a specifier that does not start with `.`. A test that imports `@/src/y` reads as not loading `src/y.ts`, so MAP11 fails, and a `uses` fact through an alias fails MAP9.
- **Where.** `skills/plain-english-map/scripts/lib/import-reader.mjs`, the specifier resolver.
- **Decision.** `map-tested-by-line` (the map names a file's tests on a checked tested-by line).
- **Retire.** The reader resolves `paths` from the host's `tsconfig.json`, and a fixture test that imports by alias passes MAP11.

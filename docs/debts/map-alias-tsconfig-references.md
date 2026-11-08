# A root tsconfig with project references reads as no aliases

- **What.** A root `tsconfig.json` with `files: []` and `references` reads as no aliases, so an alias import loads nothing and the alias tests fail silently, with no unknown read.
- **Where.** `skills/plain-english-map/scripts/lib/tsconfig-paths.mjs` `readPathAliases`.
- **Decision.** `map-tested-by-line` (a test is tied to the file it tests by a tested-by line).
- **Retire.** `readPathAliases` follows `references` to the tsconfig that declares `paths`. A case with a root tsconfig of `references` and an alias import passes MAP11.

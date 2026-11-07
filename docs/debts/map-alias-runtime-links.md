# MAP8 and the map picture read no path aliases

- **What.** MAP8 and the map picture read no path aliases, so a trace step that names a file by an `@/` import fails MAP8, and the picture draws no edge for it. MAP11 reads aliases already.
- **Where.** `skills/plain-english-map/scripts/map-check.mjs` `runtimeLinks` (about line 616), `skills/plain-english-map/scripts/map-picture.mjs` link builder (about line 112).
- **Decision.** `map-tested-by-line` (a test is tied to the file it tests by a tested-by line).
- **Retire.** `runtimeLinks` and the picture pass the aliases from `readPathAliases` to the import reader. A case with an `@/` trace step passes MAP8.

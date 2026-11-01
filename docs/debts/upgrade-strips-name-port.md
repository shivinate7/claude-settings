# The version 2 upgrade strips a port after a code-file name

- **What.** The version 1 to 2 upgrade removes `:N` after a name whose extension is in `codeExtensions`. A token like `node.js:18` has that shape. In a repository that lists `js`, the upgrade removes `:18`, and the sentence loses that number.
- **Where.** The 1 to 2 step in `skills/plain-english-map/scripts/map-upgrade.mjs`.
- **Decision.** `map-skill-lives-here` (the map skill lives in claude-settings, and a host pins the install link).
- **Retire.** The step strips `:N` only after a file the host repository tracks, and a test holds a `node.js:18` that survives.

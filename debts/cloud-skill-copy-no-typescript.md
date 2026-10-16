# A cloud copy of the map skill finds no typescript

- **What.** A cloud install copies the skill folder outside the clone. The copy finds no `node_modules`, so `map-check.mjs` and `map-picture.mjs` cannot load `typescript` there. The installer skips `npm ci` in cloud.
- **Where.** `skills/plain-english-map/scripts/lib/lazy-typescript.mjs` and the cloud branch of `install.sh`.
- **Decision.** `map-skill-lives-here` (the map skill lives in claude-settings, and a host pins a copy).
- **Retire.** The skill runs in a cloud session with no `typescript` found beside the clone, for example through a bundled copy of the parser. A test that runs the check command from a copied folder with no `node_modules` goes green.

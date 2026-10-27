# Mods install from the claude-settings GitHub marketplace, with no installer step

## The ruling

The shared `settings.json` declares one marketplace, `claude-settings`, from the GitHub repo `shivinate7/claude-settings`, with `autoUpdate` set to true. The same file enables each mod that `.claude-plugin/marketplace.json` lists, by key. No machine path goes in a shared file.

Reason: work saved here must reach every PC and Mac with no step a person runs. A third-party marketplace does not refresh unless `autoUpdate` is true, so without it each mod stays at the copy of the first install. A local-path marketplace writes an absolute path into `settings.json`, which is a link to the shared copy on a Mac, so one machine path would reach every machine.

Kind: process
Home: settings.json

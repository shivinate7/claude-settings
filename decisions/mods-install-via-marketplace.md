# Mods install from the claude-settings GitHub marketplace, with no installer step

## The ruling

The shared `settings.json` declares one marketplace, `claude-settings`, from the GitHub repo
`shivinate7/claude-settings`. The same file enables four mods by key: `token-weather`,
`desktop-statusline`, `plain-diff`, `session-board`. `.claude-plugin/marketplace.json` lists all four.
No machine path goes in a shared file.

Reason: work saved here must reach every PC and Mac with no step a person runs. A local-path
marketplace writes an absolute path into `settings.json`, which is a link to the shared copy on a
Mac, so one machine path would reach every machine.

## Holes, named

Debts: `mods-macos-untested`, `mods-marketplace-no-ref-pin`, `mods-refresh-cadence-unmeasured`,
`mods-load-needs-new-session`.

Kind: process
Home: settings.json

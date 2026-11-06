# A JS layout reader beside the Python one

- **What.** The map skill reads the debts folder from `lint/layout.json` in JS, because the only layout reader is Python and a `python3` start would add a process to every map check run. It is a bandaid. It skips `legacy-repos`, and throws if the layout ever lists `debts` there.
- **Where.** `debtsDir` in `skills/plain-english-map/scripts/lib/decisions.mjs`, and `path()` in `lint/layout.py`.
- **Decision.** `one-layout-every-repo` (each kind of file has one home in the layout).
- **Retire.** Build one shared JS reader of the layout, or have the map skill read through it. Delete `debtsDir`'s own read. A test shows a repo that keeps `debts` through `legacy-repos` gets its folder.

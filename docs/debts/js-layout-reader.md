# A JS layout reader beside the Python one

- **What.** The map skill reads the debts folder from `lint/layout.json` in JS. The only layout reader is Python, and a `python3` start would add a process to every map check run. It is a bandaid. It skips `legacy-repos`, and throws if the layout ever lists `debts` there.
- **Where.** `debtsDir` in `skills/plain-english-map/scripts/lib/decisions.mjs`, and `path()` in `lint/layout.py`.
- **Decision.** `one-layout-every-repo` (each kind of file has one home in the layout).
- **Retire.** Build one shared JS reader of the layout, and have the map skill read through it. Then delete the read in `debtsDir`. Add a case to `skills/plain-english-map/tests/record-named.test.mjs` that shows a repo keeping `debts` through `legacy-repos` gets its folder.

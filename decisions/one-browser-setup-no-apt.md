# One shared action installs Playwright, with no apt step

## The ruling

Roadmap step c78 (one shared browser-test setup), 2026-10-26: one composite action installs the browser-test setup for every repo, so a CI fix lands once.

`actions/playwright-setup`:

- Runs `npm ci` in `package-dir` (default `.`), unless `npm-ci` is `false`.
- Reads the pinned `playwright-core` version from that folder. No pin there stops the job with one line.
- Caches `~/.cache/ms-playwright`, keyed by the runner OS, that version and the browsers.
- Runs `playwright install <browsers>` (default `chromium`) with no `--with-deps`. The runner image already has the libraries. A missing library fails the suite, never skips it.
- Callers pin it by commit SHA. The `gates-shoot` job is its first caller.

`python3 lint/compliance_probes.py playwright <child root>` flags a Playwright install that runs apt (`--with-deps` or `install-deps`) in a workflow, an action, a Makefile, a shell script or a package.json script. Comments do not count.

Why, a named incident: on 2026-10-26 the apt step of `playwright install --with-deps` spent more than 11 min on a slow Ubuntu mirror and cancelled a claude-settings batch run twice (roadmap step c64). The same day it timed out degen's batch PR 263. claude-settings had fixed it for itself, and the fix had no way to reach degen.

Protected by `lint/test_compliance_probes.py` (class `Playwright`) and the `gates-shoot` job, which runs the action whenever its files change.

## Limits

- Child repos adopt the action in their own lanes, after the owner checks each plan.
- The probe reads text. An apt install of the libraries by name, without `playwright` on the line, is not found.

Kind: build
Home: actions/playwright-setup/action.yml

# One shared action installs Playwright, with no apt step

## The ruling

Roadmap step c78 (one shared browser-test setup), 2026-10-26: one composite action installs the browser-test setup for every repo, so a CI fix lands once.

`actions/playwright-setup`:

- Runs `npm ci` in `package-dir` (default `.`), unless `npm-ci` is `false`.
- Reads the pinned `playwright-core` version from that folder. No pin there stops the job with one line.
- Caches `~/.cache/ms-playwright`, keyed by the runner OS, that version and the browsers.
- Runs `playwright install <browsers>` (default `chromium`) with no `--with-deps`. The runner image already has the libraries. A missing library fails the suite, never skips it.
- Callers pin it by commit SHA. The `gates-shoot` job is its first caller.

`python3 lint/compliance_probes.py playwright <child root>` flags a Playwright install that runs apt (`--with-deps` or `install-deps`) in a CI or build file. It reads workflows, actions, Makefiles, shell scripts, Dockerfiles, justfiles, Taskfiles, dev container files and package.json scripts. Comments do not count. A folded YAML command (`run: >`) counts as one line.

Why, a named incident: on 2026-10-26 the apt step of `playwright install --with-deps` spent more than 11 min on a slow Ubuntu mirror and cancelled a claude-settings batch run twice (roadmap step c64). The same day it timed out degen's batch PR 263. claude-settings had fixed it for itself, and the fix had no way to reach degen.

Protected by `lint/test_compliance_probes.py` (class `Playwright`) and the `gates-shoot` job, which runs the action whenever its files change.

## Limits

- Child repos adopt the action in their own lanes, after the owner checks each plan.
- The probe reads text, so it misses three forms:
  - an apt install of the libraries by name, with no `playwright` in the command;
  - a flag that a script name hides (`npm run x -- --with-deps`);
  - an install from a JavaScript or Python script.
- Quoted text that names the install, such as an `echo`, is a hit.
- pnpm's strict layout does not link `playwright-core` at the top level, so the action stops with its one-line error there.

Kind: build
Home: actions/playwright-setup/action.yml

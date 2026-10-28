# One shared action installs Playwright, with no apt step for Chromium

## The ruling

Roadmap step c78 (one shared browser-test setup), 2026-10-26: one composite action installs the browser-test setup for every repo, so a CI fix lands once.

`actions/playwright-setup`:

- Runs `npm ci` in `package-dir` (default `.`), unless `npm-ci` is `false`.
- Reads the pinned `playwright-core` version from that folder. No pin there stops the job with one line.
- Caches `~/.cache/ms-playwright`, keyed by the runner OS, that version and the browsers.
- Runs `playwright install <browsers>` (default `chromium`) with no `--with-deps`. The runner image already has Chromium's libraries. A missing library fails the suite, never skips it.
- Runs no apt for Chromium. WebKit and Firefox may opt in with the `system-deps` input, such as `system-deps: webkit`. Its default is empty, so the default path runs no apt.
- With `system-deps` set, it runs `install-deps` for exactly those browsers, on Linux only. Chromium, any other name, or a blank value fails the job with one line. A blank value would install every browser's libraries.
- That apt step has a 300 s cap. The slow mirror of 2026-10-26 ran past 11 min, so the cap ends that case in under half the time. The normal apt time is unmeasured. `timeout -k 30` kills a process that ignores SIGTERM 30 s after the cap.
- Callers pin it by commit SHA. The `checks-shoot` job is its first caller.

`python3 lint/compliance_probes.py playwright <child root>` flags a Playwright install that runs apt (`--with-deps` or `install-deps`) in a CI or build file. It reads workflows, actions, Makefiles, shell scripts, Dockerfiles, justfiles, Taskfiles, dev container files and package.json scripts. Comments do not count. A folded YAML command (`run: >`) counts as one line. A caller that passes `system-deps:` writes no `install-deps`, so the probe stays quiet on it.

Why, a named incident: on 2026-10-26 the apt step of `playwright install --with-deps` spent more than 11 min on a slow Ubuntu mirror and cancelled a claude-settings batch run twice (roadmap step c64). The same day it timed out degen's batch PR 263. claude-settings had fixed it for itself, and the fix had no way to reach degen.

Why WebKit and Firefox may opt in, a named incident: joyous PR 47, run 40653154924. WebKit could not launch on ubuntu-latest: "Host system is missing dependencies" (libgtk-4, libgraphene, libevent, libopus, gstreamer). 228 WebKit tests were cancelled.

Protected by `lint/test_compliance_probes.py` (class `Playwright`), `actions/playwright-setup/test_action.py` in the `checks` job, and the `checks-shoot` job, which runs the action whenever its files change.

## Limits

- Child repos adopt the action in their own lanes, after the owner checks each plan.
- `actions/playwright-setup/test_action.py` proves the shape of the `system-deps` step and its script, with a fake `node`. It does not prove a real WebKit launch. joyous's c78 lane proves that.
- The probe reads text, so it misses three forms:
  - an apt install of the libraries by name, with no `playwright` in the command;
  - a flag that a script name hides (`npm run x -- --with-deps`);
  - an install from a JavaScript or Python script.
- Quoted text that names the install, such as an `echo`, is a hit.
- pnpm's strict layout does not link `playwright-core` at the top level, so the action stops with its one-line error there.

Kind: build
Plan: docs/decisions/one-browser-setup-no-apt.md#the-ruling (all)
Home: actions/playwright-setup/action.yml

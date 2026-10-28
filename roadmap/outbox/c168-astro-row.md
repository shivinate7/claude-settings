# c168-astro-row (lane session_013NEJL4497N2oBH8yey6bAM)

- c168 note: when a repo calls the action, it still runs `npx -p @astrojs/check@0.9.12`, so nested dependencies are not locked. Only CI's own test step installs from the lockfile in actions/code-check/tools/. zizmor does not flag this. The pipx tools have the same gap.

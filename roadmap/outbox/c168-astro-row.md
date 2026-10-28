# c168-astro-row (lane session_013NEJL4497N2oBH8yey6bAM)

Branch `c168-astro-row`, commit bbf71b8f, which adds an Astro row to code-check. Review round 1 is running. No PR yet.

- c168: the brief named `roadmap/outbox/joyous-lane.md`, but that file is not on origin/roadmap. I worked from the step note only.
- c168: the typecheck runs `astro-check` from @astrojs/check 0.9.12, not `astro check`. Without project node_modules, `astro check` prompts to install and exits 0, which is a false green. astro itself is not pinned: the checker uses the project's own astro.
- c168, tsc question: yes, unscoped run_tsc blocks joyous if joyous tracks an Astro tsconfig.json. On a fixture, `tsc --noEmit -p` gives TS6053 (`astro/tsconfigs/strict` not found without node_modules) and TS2307 (a .ts file imports a .astro file). Even with this row, such a repo stays red on tsc.
  - Possible fix, not built: run_tsc skips a tsconfig that sits in an astro.config folder, since astro-check also checks .ts files there. That changes a gate's verdict, so it needs a ruling and a step.
  - Not verified on joyous itself: the session's read-only attach of joyous was refused.
- c168: astro-check runs on whole project folders, so it ignores `.code-check.json` exclude entries. tsc does the same today. This is a note, not a debt.

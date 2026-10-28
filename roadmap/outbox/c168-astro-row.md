# c168-astro-row (lane session_013NEJL4497N2oBH8yey6bAM)

Draft PR #756, the code-check Astro row. Head bbf71b8f. Local gates pass, silent-undo passes, and review round 1 (Opus) approved it.

- c168: the brief named `roadmap/outbox/joyous-lane.md`, but that file is not on origin/roadmap. I worked from the step note only.
- c168: the typecheck runs `astro-check` from @astrojs/check 0.9.12, not `astro check`. Without project node_modules, `astro check` prompts to install and exits 0, which is a false green. astro itself is not pinned: the checker uses the project's own astro.
- c168, tsc question: yes, unscoped run_tsc blocks joyous if joyous tracks an Astro tsconfig.json. On a fixture, `tsc --noEmit -p` gives TS6053 (`astro/tsconfigs/strict` not found without node_modules) and TS2307 (a .ts file imports a .astro file). Even with this row, such a repo stays red on tsc.
  - Possible fix, not built: run_tsc skips a tsconfig that sits in an astro.config folder, since astro-check also checks .ts files there. That changes a gate's verdict, so it needs a ruling and a step.
  - Not verified on joyous itself: the session's read-only attach of joyous was refused.
- c168: astro-check runs on whole project folders, so it ignores `.code-check.json` exclude entries. tsc does the same today. This is a note, not a debt.
- c168, the joyous blocker: a real Astro repo is red under both tsc and astro-check while its node_modules are absent. `astro:content` gives TS2307, and `astro/tsconfigs/strict` gives TS6053. joyous's code-check adoption needs one of two things: its workflow installs the project dependencies before code-check runs, or the action installs them. Which one is the owner's call.
- c168 note: the Node 20 runner is unmeasured with @astrojs/check. The first CI run will show it.
- c168 note: in gates.yml, the npm install pins only the top-level packages, with no lockfile. The pipx installs above it have the same gap. Adding `--ignore-scripts` would be free.
- c168 note: a root astro.config plus a nested one gives two runs. If the nested project's tsconfig defines path aliases that the root lacks, the root run could go red falsely. Unmeasured.

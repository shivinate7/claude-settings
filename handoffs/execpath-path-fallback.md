# Handoff: execpath-path-fallback

- PR: #1116 (draft), "Compaction check finds claude on PATH when CLAUDE_CODE_EXECPATH is missing".
- Branch: execpath-path-fallback. Reviewed head: 23e0bbf. `merge --lane-lint 1116`: PASS on 23e0bbf.
- Commits:
  - 2525347: tests, red on da8d807, 1 failing.
  - d40b779: the build. A mutant with the lookup removed goes red.
  - 3fca00d: decision precompact-handoff, item 12, rewritten in place.
  - 23e0bbf: review notes.
- Review: round 1 says merge, with no safety hole. Four findings are notes in docs/debts/notes.md: execpath-fallback-script, execpath-fallback-key-split, execpath-fallback-windows-cwd and execpath-fallback-untested-mutants.
- Lint: `ci-job checks --lint` gave 0 failures and 12 platform skips.
- Limit: this container has CLAUDE_CODE_EXECPATH set, so the incident was not reproduced. Green proves the fixtures only.
- Owner of the merge: the batch runner. This lane does not merge.

# Handoff: lane other-clone-cd-refuse

Lane session: session_013NEJL3j68czTNq1sY16t1h. Coordinator: session_013NEJL2pASwRjgJDnsvnpNe.
Batch runner to tell at PR time: batch runner 7 (session_013NEJKyjt96cx7d1uCdtb8U).

## Goal

The shared guard rule `other-checkout` (hooks/guard.py `other_checkout_hit`) refuses a `cd` into,
or a write into, a separate clone of the same repo. It also refuses any write while cwd is stranded
in such a clone. Why: banchi #1003 (lane c174) drops its own tree clause and waits for this lane
(banchi DEBT-guard-misses-other-clones).

## Rulings

- Same repo only (coordinator, 2026-11-02 10:06 CST). A clone of another repo passes. Same repo =
  `origin` URLs read as files, compared by `owner/repo`; local-path origins matched; unknown passes.
- The temp exemption is `tempfile.gettempdir()` only, with no literal `/tmp` clause (lane, 2026-11-02 10:23 CST, process-only).
- Round 1 (2026-11-02 11:11 CST, lane): "any write" from a stranded cwd includes the git verbs in
  `SESSION_HOME_GIT_VERBS`, and `git -C <separate clone>` with those verbs. The remedy names only
  `git -C <dir> log` / `show`.
- No new git spawn (design). Same rule id, so an owner override lifts it.

## State

- Branch `other-clone-cd-refuse` on origin. Base main 62bdb8a6. No PR opened yet.
- Head of lane work at handoff: e46e284e (builder try 3, opus: own-checkout git verbs spend no list; its report says the suite, mutation run and lint have no red). The handoff file sits in the commit after it.
- Review: round 1 FAIL (reviewer haiku), fixed. Round 2 FAIL (reviewer sonnet): one finding, a git
  verb in the own checkout spends one `git worktree list`. Round 3: test-author rows red at 049f8d8c
  (cost case 0-list rows for `git commit`, `git checkout -b`, `git stash list`); builder try 3 (opus)
  landed the fix at e46e284e. Round 3 review not started (wind-down, owner 12:31 CST).
- Design: the appendix below. Record: docs/decisions/an-agent-outside-its-home-tree-must-stop.md (updated).
  Debt notes added: other-clone-unread-writers, other-clone-project-dir-unmeasured.

## Next

1. The round-3 fix is at e46e284e. The "Defect" section below holds its brief, for reference only.
2. Review round 3 of 3 (reviewer sonnet, xhigh), with the net-value test against main (`roles-review-cap-three`).
3. Lane lint: `~/.claude/bin/verdict ~/.claude/bin/ci-job checks --lint`,
   `python3 lint/check_silent_undo.py --upstream origin/main --head HEAD --strict`, `~/.claude/bin/merge --lane-lint <pr>`.
4. Open a draft PR. Send its number, head and verdict to batch runner 7 and the coordinator.
5. Remove this handoffs/ file from the lane branch before the batch, unless the coordinator wants it kept.
6. Optional note: add `git -C <sep> add|rm|branch -D|tag|push` and `--git-dir=` to the debt note
   other-clone-unread-writers (round-2 reviewer note).

## Defect (round 2)

hooks/guard.py, in `other_checkout_hit`, `writes = writes or _git_verb_called(command)`. It spends the
`git worktree list` for any SESSION_HOME_GIT_VERBS verb. Fix: spend it only when a stat or file read
shows the call can hit. That is a stranded cwd, or a `-C`/`cd` folder whose nearest `.git` differs
from the cwd's.

## Open questions

None open. All rulings are above.

## Hazard

Agent worktrees share the local branch ref. Work on your own branch, and push with
`git push origin HEAD:other-clone-cd-refuse`. Commit acd5fb5f reverted guard.py by mistake for this
reason, and d632c8a0 restored it.

## Appendix: design

Base: main 62bdb8a6. Home: `other_checkout_hit` in `hooks/guard.py`, rule id `other-checkout`,
decision `docs/decisions/an-agent-outside-its-home-tree-must-stop.md` (section `other-checkout`).
Extend that function. Build no second scanner.

## The hole

`elsewhere()` in `other_checkout_hit` returns False when `_owning_checkout(resolved, roots)` is "".
`roots` holds only this clone's checkouts (`git worktree list`). So a target in a separate clone,
such as `/root/claude-settings-main` from a session in `/home/user/claude-settings`, reads as
"in no checkout" and passes. The same holds for a `cd` move: the stat filter finds the other `.git`,
then `elsewhere(move, ...)` drops it.

## The new act: a separate clone of the same repo

A path P is in a **separate clone** when all hold:
1. A stat walk (`_checkout_root_by_stat`) finds R, the nearest folder at or above P with a `.git`
   entry. R is outside `roots`. R sits outside the own checkout (a submodule sits inside). R is no
   ancestor of the own checkout (a dotfiles repo at `~` is one).
2. R's git common dir differs from the own clone's common dir. Read by file, no git spawn: a `.git`
   folder is its own git dir; a `.git` file names `gitdir: <dir>`, and `<dir>/commondir` names the
   common dir, relative to `<dir>`.
3. R's clone is the **same repo**: the `[remote "origin"] url` in `<common dir>/config` of each
   clone, read as a file, names the same repo. Normalize a URL to its last two path parts
   (`owner/repo`), lower case, `.git` and a trailing `/` dropped; this covers https, ssh
   `git@host:owner/repo`, and a proxy URL like `http://proxy@127.0.0.1:N/git/owner/repo`. A local
   path origin matches when it realpaths to the other clone's top folder or common dir.
   An unreadable or missing origin on either side is unknown, and passes.
4. P sits outside the temp folder (`tempfile.gettempdir()` realpath only, the root
   `under_session_scratchpad` uses; no literal `/tmp` clause — lane ruling 2026-11-02 10:23 CST, so
   test fixtures under a moved TMPDIR still read as refuse rows). This covers the session's own
   scratchpad, other scratchpads and throwaway test clones.

A different repo (a clone that `add_repo` made, nvm, Homebrew) passes: different origin.

### Acts refused (same rule id `other-checkout`, so an owner override lifts it)

- A Write, Edit, MultiEdit or NotebookEdit target in a separate clone.
- A shell write target in a separate clone, as `_shell_write_hit` reads it (it calls `elsewhere`).
- A `cd`, `pushd` or `Set-Location` move into a separate clone (bare, chained, relative climb,
  subshell), read as `_cd_targets` reads it today.
- **cwd stranded in a separate clone.** The session's home clone is the clone holding the hook's
  `CLAUDE_PROJECT_DIR` env var (Claude Code hooks docs; unmeasured live here). The part applies
  when that var names a folder in a clone and cwd sits in a separate clone of it. (This is the test
  above, with own and other swapped.) Then every write target inside cwd's clone is refused, and so is a shell write
  with a relative target. A var that is unset, names no clone, or is unreadable: unknown, passes.
- **Recovery stays open.** From a stranded cwd, a `cd` into the home clone (any of its checkouts)
  passes. Read, Grep and shell reads pass. An owner override lifts every part.

The refusal names no path (`git-remedy-never-names-target`). The new detail prefixes are
`"cd into another clone: "` and `"write into another clone: "`. The reason constant is its own:
"Rule (other checkout): this command changes directory into, or writes into, a separate clone of this
repo, not the checkout this session stands in. Remedy: stay in your own checkout. To read another
clone, use `git -C <dir>` or a path, never `cd`."

### Cost

No new git spawn. Stat walks plus at most four small file reads (`.git` file, `commondir`, two
`config` files) per call, and only when a target or move sits under a `.git` entry that is not in
`roots`. A call with no write hint and no cd word adds nothing. Extend
`worktree_home_cross_checkout_cost_case` to count spawns for the new rows.

## Rows (test-author: red on 62bdb8a6 for each refuse row)

Refuse:
- `cd /abs/<separate clone>` bare; `cd <sep> && make`; relative climb `cd ../<sep>`; subshell
  `(cd <sep> && touch x)`; `pushd <sep>`.
- absolute shell write, no cd: `echo x > <sep>/f`.
- Write tool target `<sep>/f`.
- cwd in `<sep>`, CLAUDE_PROJECT_DIR = own clone: `echo x > f` and Write `<sep>/f`.
- a separate clone whose `.git` is a linked worktree of a third clone of the same repo (`.git` file).
- local-path origin: `<sep>` cloned from own clone's path.

Pass (green controls):
- own checkout; own linked worktree under roots (existing rules still apply).
- a submodule-shaped nested repo inside own checkout.
- a clone of a different repo (different origin).
- a separate same-repo clone under the temp folder / own scratchpad.
- separate clone with no origin, or unreadable config.
- reads: `cat <sep>/f`, `git -C <sep> log`, Read tool.
- stranded cwd: `cd <own checkout>` back home passes; stranded with CLAUDE_PROJECT_DIR unset passes.
- an owner override lifts a refuse row.
- `cd` words in a quote, comment or heredoc body stay text (existing scanner; one row).

Fixtures: build the clones outside the temp folder exemption. Read how the existing other-checkout
and scratchpad cases point `tempfile.gettempdir()` elsewhere, and reuse that fixture home.

Mutants: add rows to `hooks/mutate_guard.py` for the same-repo test and the stranded-cwd test.

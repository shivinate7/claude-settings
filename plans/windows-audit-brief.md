# Brief: Windows audit and fix session

Owner: shivinate7. Repo: shivinate7/claude-settings. Written 2026-10-11 by the orchestrator of session
1b2c13df, at wind-down.

## The two outcomes

Judge every change by these two outcomes for the owner:

1. No "allow once" prompts for actions the owner always allows. The owner denies about 1 in 10,000.
2. Agents and sessions stay tidy. Each one cleans up after itself. None runs a command that can affect
   a fellow agent, another session or the parent session.

## Read first

- `plans/windows-audit-grade.txt`: a Fable grade of the whole repo (C+). It has the evidence, the cut
  list and the next steps in order. Its main finding: `~/.claude/guard.log` logs every guard verdict
  and nobody reads it. 3,838 denies in 23 days. The `waiter` rule alone gave 1,087 denies, because the
  guard refuses `sleep` and `settings.json` denies the Monitor tool. An agent that must wait has no
  allowed way to wait.
- The owner works on Windows all day for q_max, so the Windows CI jobs stay.

## State of each open branch

Nothing below is merged to main. The owner said that unreviewed or red work can stay on its branch,
provided this brief names what was not checked.

### PR #346, branch `fix-windows-gates`: Windows CI red on main

Main CI job `gates-windows-guard` is red on every main run from 1c883cc (02:47Z) through 040d4e8.
Main has no required status checks, so 14 merges went in on red.

- Done: `repo_rel` in `hooks/guard.py` (about line 4906) no longer lowercases paths, so 16 Xcode and
  Swift test-path cases match on Windows. `_rm_real` and `_rm_target_bad` (about lines 5571-5588)
  use forward slashes, case-fold and treat a drive root as `/`. In `hooks/test_guard.py`, `mask_child`
  passes its script on stdin, because a 98 KB argv broke the 32 KB Windows limit (WinError 206).
- Checked: full `test_guard.py` PASS on macOS (2c72e9c).
- CI at wind-down: `gates-windows-guard` PASS on the PR, the job that was red on main. Other jobs
  were still pending. Read `gh pr checks 346` for their verdicts.
- Not checked: the review was stopped before it reported. Open risk: keeping case in `repo_rel` could let `Tests/` or `TESTS/`
  escape a protected-path rule on a case-insensitive file system. List each caller of `repo_rel`
  and check it.
- More Windows failures can show once the WinError 206 crash is gone, because that crash hid every
  case after it.
- After it is green: make the `gates` checks required on main.

### PR #345, branch `build-dir-reap`: build folders are reaped at agent end

Owner ruling: "Agent-end hook + low-disk guard". Then, after the grade: build the reap first, and
build the low-disk guard after a measured threshold.

- Done: the agent-end reap deletes `native/build`, `.build` (at any depth), `DerivedData` and any
  name in `buildDirs` in a finished agent's own worktree (82de8c6). It renames each folder to a
  trash name, then deletes it in a detached child. A later reap or the janitor deletes leftover
  trash. Decision build-dirs-reaped-at-agent-end; deferred item build-disk-guard (742cb98).
- Checked: `janitor/test_sweep.py` and `janitor/mutate_sweep.py` PASS on macOS.
- Not checked: no reviewer has read the reap. CI has not run, because the PR is a draft.
- The disk-guard cases are gone from `hooks/test_guard.py` (9c2cbb8, full suite PASS on macOS). The
  three "allow" disk cases went with them. After build-disk-guard is built, restore all five.
- Windows, FIRST TASK for this session: the reap deletes nothing on Windows, the same as the
  janitor's husks (`HUSKS_DELETABLE` in `janitor/sweep.py`). The cause is that Python 3.11 does not
  see a junction as a link. Add one shared link-or-junction check that reads the Windows
  reparse-point flag (`os.lstat(p).st_file_attributes & stat.FILE_ATTRIBUTE_REPARSE_POINT`).
  Use it in the build-dir reap and in the husks. Prove it with a real junction on the Windows
  runner: the reap removes the junction and never touches its target.
- Incident: feed-build, 2026-10-11. The disk reached 540 MB free, and about 330 GB was in 77 agent
  worktrees.

### Branch `worktree-file-discard`: per-file discard in a linked worktree (no PR)

Owner ruling: "Allow per-file". In a linked worktree, `git checkout <file>` and `git restore <file>`
run with no ask. The shared checkout still denies them. Decision stash-push-is-clone-wide,
paragraph "In a linked worktree".

- Five review rounds each found a new way to misjudge which checkout a command runs in. The Fable
  re-grade said keep the per-file allow (78e8446) and the operand fixes, and drop `segment_roots`.
- Built at db9f340: `segment_roots` is gone. A new `one_place()` in `hooks/guard.py` gates the
  per-file allow. The command must hold no `cd`, `pushd` or `popd`, and at most one distinct
  `git -C` target. Each discard segment takes its own `git -C` root, else `command_root`. One new
  mutant.
- Full `test_guard.py` FAILS 6 of 1931. No case gives a wrong allow.
  - Got ask, want allow (3): `cd <lane> && git restore f.txt` (the control), the same command
    repeated, and the incident form (cd into the worktree, one file, then python). Expected under
    the gate. Re-point each to ask, or tell agents to use `git -C <lane> restore f.txt`.
  - Got ask, want deny (3): `cd <shared> && git -C . restore f.txt` from a worktree, and the two
    heredoc lone-quote cases. The shared checkout gets ask, not deny. Main gives the same verdict,
    because `_run_dir` takes the first `-C` relative to the shell cwd. Decide: fix `-C .` after a
    `cd` to deny, or re-point to "deny or ask" and name the limit.
- Not checked: `mutate_guard.py` with the new gate mutant. The test it names may not exist. No
  suite ran after the last edit. No review.
- Then rewrite "Holes, named" in the decision for the gate. Drop the `segment_roots` limits.
- `guard.log` measures this ask at 1 to 2 per day. The record says "unmeasured", which is wrong.

### Branch `windows-audit-brief`: this file

## Next, in order

1. #346: green Windows CI, then required checks on main.
2. #345: the Windows junction check, a review, then merge.
3. `worktree-file-discard`: finish the gate, re-point the tests, review, PR, merge.
4. A weekly reader of `guard.log`: denies and asks by rule and by day. This is the meter for both
   outcomes.
5. Fix the `waiter` and Monitor collision: give agents one allowed way to wait.
6. Look at the next two rules by deny count: `silent-write` (920) and `env-file` (558).
7. Build the `PermissionRequest` hook from `deferred/rm-prompt-answer-hook.md`. The owner granted one
   Opus agent for this build.
8. A two-round review cap in `agents/reviewer.md`. After two rounds, each open bypass becomes a named
   limit, and the PR merges.
9. Split `hooks/test_guard.py` into case families, so that a change to one rule tests in under 60 s.

## Rulings with no home yet

- rm PATH wrapper, active only in Claude sessions. Owner: "Yes, only for Claude sessions". It refuses
  an `rm` whose real path is `/`, home, the cwd or a parent of them. First, check whether Claude Code
  sets an env marker that can gate it.
- The plan above. Owner, to the first grade: "the rest of it agreed".

## Cleanup left

- Sibling worktrees on the Mac: `../claude-settings-rm-var-guard` (merged), `../claude-settings-wt-discard`
  and `../claude-settings-brief`.
- Locked agent worktrees a158b4f7, a5863109 and aa46e11f. Branch `claude/port-other-checkout-cases`.

## Rules that bit this session

- Brief each agent to push only with `git push origin HEAD:<branch>`. One builder pushed to a new
  branch.
- Put each probe command in a file. `rm -rf $VAR/` text on a command line prompts the owner.
- The guard refuses `gh pr merge` while checks run. Use `merge <pr> --confirm`.

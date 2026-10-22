# An owner override pass lets a refused or asked act through

## The ruling

The owner types `override` as a whole prompt. The guard then lets a refusal or an ask through, once or for a time.

Owner words, 2026-10-18 CDT:

- 15:27: `one act pass and time mode so if i just say override it's then but override <time> is length of pass`. A bare `override` is a one-act pass. `override <time>` is a timed pass of that length.
- 15:27: use the pass to force through the removal of unrecognized worktrees and the stop of runaway processes.
- 15:30: the test cases also cover a worktree or branch that is in use or unpushed, `git checkout <path>`, and the stash help flag. A WSL node case is dropped, because `wsl-allow-list` already allows it.
- 15:34: a timed pass reaches helper agents (subagents). A one-act pass does not.
- 15:34: `why cap it let me say`. A timed pass has no cap. The owner picks the length.
- 15:34: an act that a typed pass lets through is not a safety hole under `roles-review-cap-three` (a change gets three review rounds).

Owner, 2026-10-19 00:07 CDT, process-only: after round 3, a test-only re-point of mutation anchors lands with CI's mutation run as its proof, with no 4th review.

Orchestrator's call, not an owner word:

- A pass covers only the session where the owner typed it.
- A one-act pass that nothing uses ends after 10 minutes.
- A bare number is minutes: `override 15` is 15 minutes. The units are `m` and `h`.
- `override off` ends any pass at once.
- The keyword counts only as the whole owner prompt, in any case: `^override(\s+(off|\d+[mh]?))?$`. A longer message, a notice tag, tool output, a file or text from an agent grants nothing.
- A pass file that is missing, unreadable or corrupt is no pass.
- The pass check sits at the top of `refuse()` in `hooks/guard_core.py`, the one place that prints a deny or an ask.
- A valid pass writes one guard log line, `override <rule>`, and prints nothing, so the normal permission flow runs.

## Outside every pass

- Owner, 2026-10-18 15:34 CDT: a write to a frozen path, and a command that sets a git location variable (`git-env-set-denied`, a git-env-set command is denied).
- Owner, 2026-10-18 16:00 CDT, `Never pass them`: a kill of pid 0, 1 or -1 (`a-kill-by-pid-needs-an-owned-pid`, a kill by pid needs an owned pid).
- Owner, 2026-10-18 16:25 CDT: the role and model guards (`subagent-model-cap`, `subagent-model-floor`, `roles-third-try-steps-up`, `builder-test-edit` and the other role guards).
- Owner, 2026-10-18 18:37 CDT, `Never lift it`: `worktree-home`, the guard that keeps a subagent inside its own worktree (`an-agent-outside-its-home-tree-must-stop`, an agent outside its home tree must stop).
- Orchestrator's call, because no pass check reaches them: the missing-module deny in `hooks/guard.py`, the `pkill` and `killall` entries in the `settings.json` deny list, the `bin/rm` and `bin/merge` shims, and each other PreToolUse gate (`question_outcome`, `sendmessage_state`, the prompt judges).

Why: the owner needs a way to force through a refusal that blocks real work. Two examples are the removal of an unrecognized worktree and the stop of a runaway process.

Kind: build
Plan: decisions/owner-override-pass.md#the-ruling (all)

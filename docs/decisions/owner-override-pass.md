# An owner override pass lets a refused or asked act through

## The ruling

The owner starts a prompt with the word `override`. The guard then lets a refusal or an ask through, once or for a time. The words after `override` are the reason, written to `guard.log` as one line.

Owner words, 2026-10-18 CDT:

- 15:27: `one act pass and time mode so if i just say override it's then but override <time> is length of pass`. A bare `override` is a one-act pass. `override <time>` is a timed pass of that length.
- 15:27: use the pass to force through the removal of unrecognized worktrees and the stop of runaway processes.
- 15:30: the test cases also cover a worktree or branch that is in use or unpushed, `git checkout <path>`, and the stash help flag. A WSL node case is dropped, because `wsl-allow-list` already allows it.
- 15:34: a timed pass reaches helper agents (subagents). A one-act pass does not.
- 15:34: `why cap it let me say`. A timed pass has no cap. The owner picks the length.
- 15:34: an act that a typed pass lets through is not a safety hole under `roles-review-cap-three` (a change gets three review rounds).

Owner, 2026-10-26 15:28 CDT, "Fix the hook": an active pass lifts the SendMessage judges too. Both run in `hooks/sendmessage_state.py`, and its deny goes through `refuse()`.

Owner, 2026-10-26 (step c41, answer a): build an Opus-only pass word. It lifts only the Opus spawn ask of `subagent-model-cap`, for the session and its subagents, until it ends.

Owner, 2026-10-19 00:07 CDT, process-only: after round 3, a test-only re-point of mutation anchors lands with CI's mutation run as its proof, with no 4th review.

Orchestrator's call, not an owner word:

- A pass covers only the session where the owner typed it.
- A one-act pass that nothing uses ends after 10 minutes.
- A bare number is minutes: `override 15` is 15 minutes. The units are `m` and `h`.
- `override off` ends any pass at once.
- The keyword counts only as the first word of the owner prompt, after leading whitespace, in any case. `override` alone, or with a reason (`override: use opus for that one review agent`), is a one-act pass. The reason keeps its case, folds newlines and tabs to spaces, and goes to `guard.log` through the guard's own locked log writer. `override <n>[m|h]` and `override off` keep their meaning only as the whole prompt: a word after a length or after `off` (`override 15m please`) is ambiguous and grants nothing, so an intended "off" never becomes a grant. A word that only starts with the keyword (`overrides`, `override15m`), a later line that starts with it, a notice tag, tool output, a file or text from an agent grants nothing.
- A pass file that is missing, unreadable or corrupt is no pass.
- `override` also lifts the Opus spawn ask of `subagent-model-cap`. It never lifts that rule's settings-write ask.
- The pass check sits at the top of `refuse()` in `hooks/guard_core.py`, the one place that prints a deny or an ask.
- A valid pass writes one guard log line, `override <rule>`, and prints nothing, so the normal permission flow runs.

## The Opus pass

- `opus 2h` or `opus 15m` lifts the Opus spawn ask for every role until it ends. `opus builders 2h` (or `opus builder 2h`) lifts it only for spawns of that role. The roles are `OPUS_ROLES` in `hooks/override_pass.py`. Plan and Explore are not in it, because they run Opus by standing word. `opus off` ends the pass. A spawn with no role counts as `general-purpose`.
- It lifts nothing else: not the settings-write ask of `subagent-model-cap`, and no other rule.
- It reaches subagents, as a timed `override` does. It covers only the session where the owner typed it.
- The unit is required. `opus 4` may name a model, so it grants nothing.
- The word counts only as the whole prompt, in any case. Any other text after `opus` grants nothing.
- The file is `state/override/opus/<session>.json`. It has the format of the override pass, with kind `opus` and one more field, `role`. It sits in its own folder, so an Opus pass and an override pass do not replace each other, and `override off` leaves an Opus pass in place. `state/` is frozen against Claude's writes, so a session cannot grant itself a pass.
- An Opus spawn that both passes cover uses the Opus pass, so a one-act `override` stays unspent.
- `guard.log` gets one line per grant (`opus-grant`, with the role and the end), per lift (`opus-pass`), per end (`opus-off`), and per unreadable file (`opus-unread`).

Orchestrator's call, not an owner word: the required unit, the role list, and the `general-purpose` default.

## Outside every pass

- Owner, 2026-10-18 15:34 CDT: a write to a frozen path, and a command that sets a git location variable (`git-env-set-denied`, a git-env-set command is denied).
- Owner, 2026-10-18 16:00 CDT, `Never pass them`: a kill of pid 0, 1 or -1 (`a-kill-by-pid-needs-an-owned-pid`, a kill by pid needs an owned pid).
- Owner, 2026-10-18 16:25 CDT: the role and model guards (the settings-write ask of `subagent-model-cap`, `subagent-model-floor`, `roles-third-try-steps-up`, `builder-test-edit` and the other role guards).
- Owner, 2026-10-18 18:37 CDT, `Never lift it`: `worktree-home`, the guard that keeps a subagent inside its own worktree (`an-agent-outside-its-home-tree-must-stop`, an agent outside its home tree must stop).
- Orchestrator's call, because no pass check reaches them: the missing-module deny in `hooks/guard.py`, the `pkill` and `killall` entries in the `settings.json` deny list, the `bin/rm` and `bin/merge` shims, and each other PreToolUse gate (the prompt judges, the question reviewer agent hook).

Why: the owner needs a way to force through a refusal that blocks real work. Two examples are the removal of an unrecognized worktree and the stop of a runaway process.

Kind: build
Plan: docs/decisions/owner-override-pass.md#the-ruling (all)

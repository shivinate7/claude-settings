# An owner override lets a refused or asked act through

## The ruling

The owner starts a prompt with the word `override`. The guard then lets a refusal or an ask through, once or for a time. The words after `override` are the reason, written to `guard.log` as one line.

Owner words, 2026-10-18 CDT:

- 15:27: `one act pass and time mode so if i just say override it's then but override <time> is length of pass`. A bare `override` is a one-act override. `override <time>` is a timed override of that length.
- 15:27: use the override to force through the removal of unrecognized worktrees and the stop of runaway processes.
- 15:30: the test cases also cover a worktree or branch that is in use or unpushed, `git checkout <path>`, and the stash help flag. A WSL node case is dropped, because `wsl-allow-list` already allows it.
- 15:34: a timed override reaches the agents the session starts. A one-act override does not.
- 15:34: `why cap it let me say`. A timed override has no cap. The owner picks the length.
- 15:34: an act that a typed override lets through is not a safety hole under `roles-review-cap-three` (a change gets three review rounds).

Owner, 2026-10-26 15:28 CDT, "Fix the hook": an active override lifts the SendMessage judges too. Both run in `hooks/sendmessage_state.py`, and its refusal goes through `refuse()`.

Step c80, option (a), Oct 26-27: a refusal names the override line. `refuse()` ends the printed reason with the line the owner types (`override.offer`), or with `override.NO_OVERRIDE` when the act is outside every override. Option (b), an AskUserQuestion answer that grants the override, stays deferred. Text from an agent grants nothing, so printing the line cannot let a session grant itself an override.

Owner, 2026-10-26 (step c41, answer a): build an Opus-only override word. It lifts only the Opus spawn ask of `agent-model-cap`, for the session and its agents, until it ends.

Owner, 2026-10-19 00:07 CDT, process-only: after round 3, a test-only re-point of mutation anchors lands with CI's mutation run as its proof, with no 4th review.

Orchestrator's call, not an owner grant:

- An override covers only the session where the owner typed it.
- A one-act override that nothing uses ends after 10 minutes.
- A bare number is minutes: `override 15` is 15 minutes. The units are `m` and `h`.
- `override off` ends any override at once.
- The keyword counts only as the first word of the owner prompt, after leading whitespace, in any case. `override` alone, or with a reason (`override: use opus for that one review agent`), is a one-act override. The reason keeps its case, folds newlines and tabs to spaces, and goes to `guard.log` through the guard's own locked log writer. `override <n>[m|h]` and `override off` keep their meaning only as the whole prompt: a word after a length or after `off` (`override 15m please`) is ambiguous and grants nothing, so an intended "off" never becomes a grant. A word that only starts with the keyword (`overrides`, `override15m`), a later line that starts with it, a notice tag, tool output, a file or text from an agent grants nothing.
- An override file that is missing, unreadable or corrupt is no override.
- `override` also lifts the Opus spawn ask of `agent-model-cap`. It never lifts that rule's settings-write ask.
- The override check sits at the top of `refuse()` in `hooks/guard_core.py`, the one place that prints a deny or an ask.
- A valid override writes one guard log line, `override <rule>`, and prints nothing, so the normal permission flow runs.

## The Opus override

- `opus 2h` or `opus 15m` lifts the Opus spawn ask for every role until it ends. `opus builders 2h` (or `opus builder 2h`) lifts it only for spawns of that role. The roles are `OPUS_ROLES` in `hooks/override.py`. Plan and Explore are not in it, because they run Opus by standing grant. `opus off` ends the override. A spawn with no role counts as `general-purpose`.
- It lifts nothing else: not the settings-write ask of `agent-model-cap`, and no other rule.
- It reaches agents, as a timed `override` does. It covers only the session where the owner typed it.
- The unit is required. `opus 4` may name a model, so it grants nothing.
- The word counts only as the whole prompt, in any case. Any other text after `opus` grants nothing.
- The file is `state/override/opus/<session>.json`. It has the format of the override, with kind `opus` and one more field, `role`. It sits in its own folder, so an Opus override and an override do not replace each other, and `override off` leaves an Opus override in place. `state/` is frozen against Claude's writes, so a session cannot grant itself an override.
- An Opus spawn that both overrides cover uses the Opus override, so a one-act `override` stays unspent.
- `guard.log` gets one line per grant (`opus-grant`, with the role and the end), per lift (`opus-override`), per end (`opus-off`), and per unreadable file (`opus-unread`).

Orchestrator's call, not an owner grant: the required unit, the role list, and the `general-purpose` default.

## The step grant

- A grant on the lane's roadmap step lifts the Opus spawn ask too, and nothing else (decision `agent-model-cap`). Triage writes it. `role` is null for every role, or one role from `OPUS_ROLES`.
- `take()` reads it after the Opus override and before the override, so a lift spends no one-act override.
- The lane id is `session_<x>` when `CLAUDE_CODE_REMOTE_SESSION_ID` is `cse_<x>`, else the session id. Exactly one step must name the lane, and its status must not be `done`.
- A record that cannot be read, a grant of the wrong shape, an unknown role or a git error is no lift.
- `guard.log` gets one line per lift (`step-grant`, with the step) and per unreadable record (`step-grant-unread`).

## Outside every override

- Owner, 2026-10-18 15:34 CDT: a write to a frozen path, and a command that sets a git location variable (`git-env-set-refused`, a git-env-set command is refused).
- Owner, 2026-10-18 16:00 CDT, `Never pass them`: a kill of pid 0, 1 or -1 (`a-kill-by-pid-needs-an-owned-pid`, a kill by pid needs an owned pid).
- Owner, 2026-10-18 16:25 CDT: the role and model guards (the settings-write ask of `agent-model-cap`, `agent-model-floor`, `roles-third-round-steps-up`, `builder-test-edit` and the other role guards).
- Owner, 2026-10-18 18:37 CDT, `Never lift it`: `worktree-home`, the guard that keeps an agent inside its own worktree (`an-agent-outside-its-home-tree-must-stop`, an agent outside its home tree must stop).
- Orchestrator's call, because no override check can reach them: the missing-module refusal in `hooks/guard.py`, the `bin/rm` shim and the `bin/merge` shim. The shims run inside the command, after the guard, and the failed guard cannot check the acts above. Each of these refusals says that no override lifts it.
- Step c85: the Agent spawn judge and the AskUserQuestion reviewer (`hooks/call_judge.py`) and the prose judge (`hooks/prose_judge.py`) refuse through `refuse()`, so an override lifts them. The `pkill` and `killall` deny entries left `settings.json`, because `hooks/guard_kill.py` refuses both through `refuse()`. An Explore spawn on a model that is neither Sonnet nor Opus is the Explore row of `agent-model-cap`, a model guard, so no override lifts it.
- Known limit: a call that two sibling hooks both refuse spends a one-act override on the first refusal. A timed override lifts both.

Why: the owner needs a way to force through a refusal that stops real work. Two examples are the removal of an unrecognized worktree and the stop of a runaway process.

Kind: build
Plan: docs/decisions/owner-override.md#the-ruling (all)

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

Owner, 2026-10-26 (step c41, answer a): build an Opus-only override word. It lifts only the Opus spawn refusal of `agent-model-cap` (an ask until 2026-11-01 17:25 CST, a refusal since, item 127, pick a), for the session and its agents, until it ends.

Owner, 2026-10-19 00:07 CDT, process-only: after round 3, a test-only re-point of mutation anchors lands with CI's mutation run as its proof, with no 4th review.

Orchestrator's call, not an owner grant:

- An override covers only the session where the owner typed it.
- A one-act override that nothing uses ends after 10 minutes.
- A bare number is minutes: `override 15` is 15 minutes. The units are `m` and `h`.
- `override off` ends any override at once.
- The keyword counts only as the first word of the owner prompt, after leading whitespace, in any case. `override` alone, or with a reason (`override: use opus for that one review agent`), is a one-act override. One punctuation mark may follow the word (`,` `.` `!` `;` `:` or a dash). It is dropped before the reason, so `override, yes` is `override yes`. All marks but `:` count only with whitespace or the end after them: `override.py is broken` and `override-15m` grant nothing. The reason keeps its case, folds newlines and tabs to spaces, and goes to `guard.log` through the guard's own locked log writer. `override <n>[m|h]` and `override off` keep their meaning only as the whole prompt after that mark: a word after a length or after `off` (`override 15m please`) grants nothing on this route, so an intended "off" never becomes a grant. A rest that holds a length goes to the plain override ask below. A word that only starts with the keyword (`overrides`, `override15m`), a later line that starts with it, a notice tag, tool output, a file or text from an agent grants nothing. The plain ask below grants nothing from these either, nor from `<pasted_content>` blocks.
- An override file that is missing, unreadable or corrupt is no override.
- `override` also lifts the Opus spawn refusal of `agent-model-cap`, and a refusal of a spawn above its role's row (`agent-role-model`; owner, 2026-11-01 17:25 CST, item 127, pick a, same for Sonnet and Opus). It never lifts that rule's settings-write ask, nor the no-model refusal of `agent-role-model`.
- The override check sits at the top of `refuse()` in `hooks/guard_core.py`, the one place that prints a deny or an ask.
- A valid override writes one guard log line, `override <rule>`, and prints nothing, so the normal permission flow runs.

## The plain override ask

- Owner ask, 2026-11-07 12:44 CST (page ask `ask-mw6r5ldefg`): a plain typed override ask, such as `override that for 15 minutes please` or `yes override that`, lifts a refusal, as the plain Opus ask does. Departs from: main, keyword forms only for `override` — adds a judged plain-word route.
- `hooks/local_time.py` calls `override.grant_override_ask` after `grant()` and `grant_opus_ask` granted nothing. It writes the same override file `grant()` writes: timed for a length in the words (`15m`, `15 minutes`, or a bare number right after a first word `override`, in minutes), else one-act with the 10-minute window.
- `grant()` defers to it only for a first word `override` whose rest is no whole keyword form and holds a length. A judge no or error keeps main's result: a reason form stays one-act, and `override 15m please` grants nothing. A judge error never widens one-act to timed.
- It shares the Opus ask's gates (one helper): the `source` check, a notice start, cut pasted and notice blocks (a `<cross-session-message>` block too), a fired-task block, a `promptSource` `system` record, and the cloud seed check. Its judge is `call_judge.override_ask`, the same fail-closed call as `opus_ask` with its own prompt head.
- A pasted refusal line from `override.offer` grants nothing: the word counts only outside backtick code spans.
- These get no judge call and no grant: no whole word `override` outside code spans, and a `NEGATIONS` word or `off` within `NEGATION_SPAN` words of it. So do a `?`, two lengths, a decimal or compound length, and the whole word `opus`, which the Opus route owns.
- Cost: at most one model call per owner prompt, only for a prompt that holds the whole word `override` and passes the gates. None for any other prompt.

## The Opus override

- `opus 2h` or `opus 15m` lifts the Opus spawn refusal for every role until it ends. `opus builders 2h` (or `opus builder 2h`) lifts it only for spawns of that role. The roles are `OPUS_ROLES` in `hooks/override.py`. Plan is not in it, because it runs Opus by standing grant. Explore is not in it either: an Explore on Opus with no `Audit:` marker is refused, and `opus 2h` or `override` lifts it (owner, 2026-11-01 18:38 CST, item 137, pick a). No scoped `opus explore` form exists (option b, not picked). `opus off` ends the override. A spawn with no role counts as `general-purpose`.
- It lifts nothing else: not the settings-write ask of `agent-model-cap`, and no other rule.
- It reaches agents, as a timed `override` does. It covers only the session where the owner typed it.
- The unit is required. `opus 4` may name a model, so it grants nothing.
- The keyword counts only as the whole prompt, in any case. Any other text after `opus` grants nothing on this route. The plain ask below is the other route.
- The file is `state/override/opus/<session>.json`. It has the format of the override, with kind `opus` and one more field, `role`. It sits in its own folder, so an Opus override and an override do not replace each other, and `override off` leaves an Opus override in place. `state/` is frozen against Claude's writes, so a session cannot grant itself an override.
- An Opus spawn that both overrides cover uses the Opus override, so a one-act `override` stays unspent.
- `guard.log` gets one line per grant (`opus-grant`, with the role and the end), per lift (`opus-override`), per end (`opus-off`), and per unreadable file (`opus-unread`).
- The plain ask (owner, 2026-11-03 19:47 CST, chat, "a read plain asks"): a plain Opus ask in the owner's own typed prompt, such as `send opus judges`, lifts the Opus spawn refusal with no keyword. The step grant route stays.
- `hooks/local_time.py` calls `override.grant_opus_ask` only when the keyword forms granted nothing. It reads only the owner's typed prompt. A prompt that starts with a `shared_names.MACHINE_TAGS` notice grants nothing. A `MACHINE_TAGS` or `NOTICE_FRAMES` block anywhere, a `<pasted_content>` block, and the text after an unclosed one are cut first. In a cloud session, a prompt with no earlier owner turn in the transcript is a seed prompt from another session, so it grants nothing. These records are never an owner turn: a `/effort` command record, an `isMeta` record, a record with `promptSource` `system`, and a record whose `origin.kind` is not human. A record with a fired-task block is never an owner turn either, and neither is the record of the current prompt itself. The plain ask grants only when the UserPromptSubmit payload's `source` is `user`, absent or null (`OPUS_ASK_SOURCES`). Any other value, such as `loop_wakeup`, `schedule_wakeup` or `system`, grants nothing. The keyword forms do not read `source`. When `source` is absent, the transcript reads below are the fallback. When the last user prompt record in the transcript tail is the prompt itself with `promptSource` `system`, the prompt grants nothing, in a local session too. Attachment and assistant records after it do not count. A prompt that carries a fired-task block (`<system-reminder>This task fired at`) grants nothing (owner, 2026-11-03 22:31 CST, cockpit item 225, pick a). The plain path skips a prompt whose first word is `override`. It also skips a first word `opus` followed by `off`, a length, or a role then a length (the whole-prompt rule holds).
- A model judge, `call_judge.opus_ask` (haiku), answers yes or no. It reads only the ask's own typed text. A question, a hedge, a negation or quoted agent text grants nothing. Any judge error grants nothing (fails closed). Context never flips a no and never widens a grant.
- Roles the ask names win: each `OPUS_ROLES` role the words name is granted. Two or more named roles grant all of them (coordinator, 2026-11-04 08:14 CST, under Cockpit item 226 b; this overturns the 2026-11-03 review-round refusal of two roles), but only when a plain list joins them: commas, `and`, `or`, `&`, `plus` (`PLAIN_LIST`). Any other words between two roles grant nothing. `claude` is the addressee here, never a role. `NEGATIONS` holds the negation and exclusion words: `not`, `no`, `never`, `except`, `without`, `don't`, `excluding`, `exclude`, `skip`, `ignore`, `instead`, `rather`, `besides`, `minus`. A role with one of them within three words before or after it, two lengths, a decimal length or a compound length grant nothing. `builders, no problem` grants nothing too: the rule fails closed. The length is a length in the words (`30m`, `1 hour`), else 2h.
- When the ask names no role and the yes/no call said yes, a second judge, `call_judge.opus_scope`, reads the newest 10 earlier owner prompts in the transcript tail. Only prompts before the ask count (owner, 2026-11-04 08:03 CST, Cockpit item 226 b: scope from context, fall back to every role; coordinator 08:14 CST: before the ask only). In a cloud session the first owner turn is the seed brief, and the read skips it (`_seed_record`, the seed check's one home). Each passes the seed check's owner-turn test (`isMeta`, `promptSource` `system`, non-human origin, command and fired-task records are out). Pasted and notice blocks are cut first, then each prompt is cut to 2000 characters. The judge returns the model's role strings as given. `override._scoped_roles` is the one filter: it ignores case and keeps only roles in ASK_ROLES (OPUS_ROLES less `claude`, so `claude` never counts). None, an unknown role, or any error: every role for 2h. With no earlier owner prompt, no scope call runs, and every role for 2h applies. Whether it also reads prompts after the ask is an open owner question on the Cockpit.
- A plain-ask grant writes the same Opus override file. Its `role` is null for every role, one role, or a list of two or more roles. When a scope read runs, the every-role file (null) is written first. A valid answer narrows it, so a kill at the prompt hook's 30s timeout leaves the every-role file with no `opus-grant` line. An interrupt or exit during the read logs the every-role line. One `opus-grant` line in `guard.log` logs the final scope and carries the owner's words. Keyword forms write `role` as before.
- Cost: at most one model call per owner prompt with the word `opus` that takes the plain path. One scope call runs only for a judged-yes ask that names no role and has earlier owner prompts. None for any other prompt.

Orchestrator's call, not an owner grant: the required unit, the role list, and the `general-purpose` default.

## The step grant

- A grant on the lane's roadmap step lifts the Opus spawn refusal too, and nothing else (decision `agent-model-cap`). Triage writes it. `role` is null for every role, or one role from `OPUS_ROLES`.
- `take()` reads it after the Opus override and before the override. So a step-grant lift spends no one-act override, as the typed Opus override already does.
- The load brake runs before the Opus spawn refusal, so no lift of it skips a load-brake deny.
- The lane id is `session_<x>` when `CLAUDE_CODE_REMOTE_SESSION_ID` is `cse_<x>`, else the session id. Exactly one step must name the lane, and its status must not be `done`.
- A record that cannot be read, a grant of the wrong shape, an unknown role or a git error is no lift.
- `guard.log` gets one line per lift (`step-grant`, with the step) and per unreadable record (`step-grant-unread`).

## Outside every override

- Owner, 2026-10-18 15:34 CDT: a write to a frozen path, and a command that sets a git location variable (`git-env-set-refused`, a git-env-set command is refused).
- Owner, 2026-10-18 16:00 CDT, `Never pass them`: a kill of pid 0, 1 or -1 (`a-kill-by-pid-needs-an-owned-pid`, a kill by pid needs an owned pid).
- Owner, 2026-10-18 16:25 CDT: the role and model guards (the settings-write ask of `agent-model-cap`, `agent-model-floor`, the no-model refusal of `agent-role-model` (its above-row refusal is liftable, owner, 2026-11-01 17:25 CST, item 127, pick a), `roles-third-round-steps-up`, `builder-test-edit` and the other role guards).
- Owner, 2026-10-18 18:37 CDT, `Never lift it`: `worktree-home`, the guard that keeps an agent inside its own worktree (`an-agent-outside-its-home-tree-must-stop`, an agent outside its home tree must stop).
- Orchestrator's call, because no override check can reach them: the missing-module refusal in `hooks/guard.py`, the `bin/rm` shim and the `bin/merge` shim. The shims run inside the command, after the guard, and the failed guard cannot check the acts above. Each of these refusals says that no override lifts it.
- Step c85: the Agent spawn judge and the AskUserQuestion reviewer (`hooks/call_judge.py`) and the prose judge (`hooks/prose_judge.py`) refuse through `refuse()`, so an override lifts them. The `pkill` and `killall` deny entries left `settings.json`, because `hooks/guard_kill.py` refuses both through `refuse()`. An Explore spawn on a model that is neither Sonnet nor Opus is the Explore row of `agent-model-cap`, a model guard, so no override lifts it.
- Known limit: a call that two sibling hooks both refuse spends a one-act override on the first refusal. A timed override lifts both.

Why: the owner needs a way to force through a refusal that stops real work. Two examples are the removal of an unrecognized worktree and the stop of a runaway process.

Kind: build
Plan: docs/decisions/owner-override.md#the-ruling (all)

# Haiku prompt hooks

The model and effort of each hook named here are rows of the model table (decision `agent-model-cap`, the model per role). This record holds no copy.

## The ruling

**Prompt hooks judge rules that no script can parse.** Each refuses the call when it finds a breach (owner ruling 2026-10-07). A prompt hook cannot warn: it answers `ok` and shows nothing, or refuses with a reason. A refusal returns its reason to the session and the turn goes on (`continueOnBlock`). `settings.json` holds none (counted from its `type: prompt` entries): the Agent and AskUserQuestion judges are one command hook, so an override can lift them.

| Hook on | Rules it judges |
|---|---|
| `Agent` (`hooks/call_judge.py`) | `roles-brief-contents`, `tokens-point-brief-at-files`, and the Explore-audit guard of `agent-model-cap` |

- The Agent spawn judge and the AskUserQuestion reviewer are one command hook, `hooks/call_judge.py`, so an override can lift them.
- The SendMessage wording judge is a command hook, `hooks/sendmessage_state.py`, so an override can lift it. It judges `parallelism-no-mid-task-talk` by wording alone.
- The Edit and Write judge on `docs/decisions/` is a command hook, `hooks/prose_judge.py`, at Haiku `xhigh`. It judges `speak-rewrite-superseded-in-place` and `rulings-declare-kind`.
- A prompt hook sees only the event's input, never the chat. So no hook judges `style-question-inside-box` or `roles-one-role-per-agent`.
- The rules that these hooks read stay `unmechanized` in `lint/rule_mechanisms.json` until a hook catches a real defect.
- A hook that cries wolf is spent (`verification-cry-wolf-guard-is-spent`). Remove one that refuses good input. The trial review of 2026-10-17 11:33 CDT: the refusing judges stay.

**The owner prefers Haiku at `xhigh`** (owner ruling 2026-10-12), but a prompt hook takes no effort field, so a judge that needs it is a command hook that calls Haiku through `decision_watch.invoke_model`. The two prompt judges move to Haiku at `xhigh`, and this record changes in place, when one of these happens:

- Claude Code adds an effort field to prompt hooks.
- A mod judge has its own model call that takes an effort level.

A prompt hook names a full model id, because the prompt-hook evaluator rejects the alias `haiku`. When the model retires, change the `model` value in the judge hooks of `settings.json`, the one place. `lint/test_settings_matcher.py` pins it.

## The six model-call hooks stay command hooks

Owner, Cockpit item 248, pick b, 2026-11-06 12:19 CST: keep all six, state each one's cost, and re-check on the triggers below. An Opus audit at main 111b566b (2026-11-05 08:43 CST) found that none can move to a prompt hook without loss: a prompt hook gets only the tool input, has no fail-closed path and no effort field, and the owner's typed override cannot lift its deny. Each model call is a child inside its hook's budget (rule `outcomes-mechanize-rules`).

Cost, per `outcomes-mechanize-rules`. `decision_watch.invoke_model` is the one model caller. Each call starts one `claude -p` with the owner's token, bounded by the caller's timeout, and removes its temp root on every path (`hooks/test_decision_watch.py` `CostTests`). Per hook fire:

| Hook (event) | Process starts | Files written | How often |
|---|---|---|---|
| `call_judge` (PreToolUse on Agent, AskUserQuestion, ArtifactData) | a judged call: 1 model call, 1 `git` read; fast exit: none | a refusal: one `guard.log` line | each matching call |
| `prose_judge` (PreToolUse on Edit and Write) | 1 model call per edit under `docs/decisions/`; any other path: none | a refusal: one `guard.log` line | each Edit or Write |
| `reply_judge` (Stop) | a sampled Stop: 1 model call; a sampled-out Stop: none | its sample counter | each Stop |
| `feedback_guard` (Stop) | a judging Stop: 1 model call, 1 `grep`, 1 `git rev-parse`; a quiet Stop: none | turn state and the inbox | each Stop |
| `report_guard` (Stop) | a reply with two or more questions: 1 model call, 1 `git` read; else none | none | each Stop |
| `sendmessage_state` (PreToolUse on SendMessage) | a busy receiver: 2 model calls and 1 `node` board read; idle: 1 model call and 1 `node`; a structured message: 1 model call, no `node`. The `node` read is killed, with its group, at its timeout | none | each SendMessage |

Each row's file under `hooks/` or `lint/` holds a `CostTests` class that pins its counts.

One more model caller is not among the six and is not ruled here: `decision_watch.run`, in the decision-watch mod. `hooks/local_time.py` makes no model call (checked by grep).

Re-check the move to prompt hooks, and rewrite this section in place, when Claude Code adds any of these:

- an effort field for prompt hooks;
- a fail-closed setting for prompt hooks;
- a way to lift a prompt hook's deny.

Kind: process
Home: settings.json

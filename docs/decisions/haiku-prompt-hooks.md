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
- A prompt hook sees only the event's input, never the chat. On Stop that input holds the final reply (`last_assistant_message`), but no earlier message. So no prompt hook judges `roles-one-role-per-agent`. For `style-question-inside-box`, a Stop prompt hook could see whether a reply's question stands alone, but no prompt hook sees the text written before a question box.
- The rules that these hooks read stay `unmechanized` in `lint/rule_mechanisms.json` until a hook catches a real defect.
- A hook that cries wolf is spent (`verification-cry-wolf-guard-is-spent`). Remove one that refuses good input. The trial review of 2026-10-17 11:33 CDT: the refusing judges stay.

**The owner prefers Haiku at `xhigh`** (owner ruling 2026-10-12), but a prompt hook takes no effort field, so a judge that needs it is a command hook that calls Haiku through `decision_watch.invoke_model`. The two prompt judges move to Haiku at `xhigh`, and this record changes in place, when one of these happens:

- Claude Code adds an effort field to prompt hooks.
- A mod judge has its own model call that takes an effort level.

A prompt hook names a full model id, because the prompt-hook evaluator rejects the alias `haiku`. When the model retires, change the `model` value in the judge hooks of `settings.json`, the one place. `lint/test_settings_matcher.py` pins it.

## The six model-call hooks stay command hooks

Owner ruling, Cockpit item 248 (model-call hooks), pick b, 2026-11-06 12:19 CST: keep all six, state each one's cost, and re-check on the triggers below. An Opus audit at main 111b566b (2026-11-05 08:43 CST) found that none can move to a prompt hook without loss. A prompt hook gets only the tool input. It has no fail-closed path and no effort field. The owner's typed override cannot lift its deny. Each model call is a child inside its hook's budget (rule `outcomes-mechanize-rules`).

Cost, per `outcomes-mechanize-rules`: the one model caller is `decision_watch.invoke_model`. Each call starts one `claude` child, and removes its temp root on every path (`hooks/test_decision_watch.py`, class `CostTests`). The six hooks cost, per fire:

| Hook (event) | Child starts | Model calls | Files written | How often | Test (class `CostTests`) |
|---|---|---|---|---|---|
| `call_judge` (PreToolUse on Agent, AskUserQuestion, ArtifactData) | a judged question or page write: 2 `git` reads, and a third for a roadmap entry that names `lands_in` (unmeasured); an Agent spawn or a page read: none | 1 per judged question or write; 0 otherwise | a refusal: one `guard.log` line; an allow: none | each matching call | `hooks/test_call_judge.py` |
| `prose_judge` (PreToolUse on Edit and Write) | none | 1 per Edit or Write under `docs/decisions/`; 0 elsewhere | a refusal: one `guard.log` line; an allow: none | each Edit or Write | `hooks/test_prose_judge.py` |
| `reply_judge` (Stop) | none | 1 on a judged Stop: Stops 1, 6 and 11 of a session (`SAMPLE_EVERY` 5), and any Stop whose reply holds a table separator; 0 on a sampled-out Stop | a counter file on each judged or sampled-out Stop (none on a `stop_hook_active` or empty-reply Stop); a finding adds one `guard.log` line | each Stop | `hooks/test_reply_judge.py` |
| `feedback_guard` (Stop) | a judging Stop: 2 `git` reads (`grep`, and `rev-parse --show-toplevel`); a quiet Stop: none | 1 on a judging Stop; 0 on a quiet Stop | a judging Stop: turn state, and the inbox only when a repeat is marked; a quiet Stop: no byte | each Stop | `hooks/test_feedback_inbox.py` |
| `report_guard` (Stop) | a Stop whose replies since the last owner or peer message hold a question: 2 `git` reads (`ls-tree` of the ruled store, `cat-file` of the roadmap), and a third for a `lands_in` entry (unmeasured); otherwise none | 1 per such Stop; 0 otherwise | none; a refused question blocks the Stop once | each Stop | `lint/test_report_guard.py` |
| `sendmessage_state` (PreToolUse on SendMessage) | a plain message: 1 `node` read; a structured or malformed message: none | a plain message to a busy receiver: 2 (wording, busy); to an idle receiver: 1 (wording); a structured message: 1 (wording); malformed: 0 | none | each SendMessage | `hooks/test_sendmessage_state.py` |

Open, not fixed: the busy path of `sendmessage_state` runs its wording call and its busy call beside each other, not in a row. The code's budget comment gives 47 s at most, against the 50 s row, and start-up is not counted (`hooks/sendmessage_state.py`, the time budget comment). No test pins that sum against the row (note `sendmessage-busy-path-timing`).

Two more model callers are not among the six, and this record does not rule on them. `decision_watch.run`, in the decision-watch mod, is not measured here. `hooks/local_time.py` (UserPromptSubmit) starts no child on any prompt. A plain prompt makes no model call. A prompt with the whole word `override` makes one judge call. A prompt with the whole word `opus` makes one judge call for the ask, and one scope read only after a yes. A keyword grant (`opus <n>[m|h]`, `opus off`) makes none. Each prompt appends to the inbox, and the repo sidecar is written once per session (`hooks/test_local_time.py`, class `CostTests`).

Re-check the move to prompt hooks, and rewrite this section in place, when Claude Code adds any of these:

- an effort field for prompt hooks;
- a fail-closed setting for prompt hooks;
- a way to lift a prompt hook's deny.

Kind: process
Home: settings.json

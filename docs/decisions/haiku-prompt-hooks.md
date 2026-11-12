# Haiku prompt hooks

The model and effort of each hook named here are rows of the model table (decision `agent-model-cap`, the model per role). This record holds no copy.

## The ruling

**Prompt hooks judge rules that no script can parse.** Each refuses the call when it finds a breach (owner ruling 2026-10-07). A prompt hook cannot warn: it answers `ok` and shows nothing, or refuses with a reason. A refusal returns its reason to the session and the turn goes on (`continueOnBlock`). `settings.json` holds none (counted from its `type: prompt` entries): the Agent and AskUserQuestion judges are one command hook, so an override can lift them.

| Hook on | Rules it judges |
|---|---|
| `Agent` (`hooks/call_judge.py`) | `roles-brief-contents`, `tokens-point-brief-at-files`, and the Explore-audit guard of `agent-model-cap` |

- The Agent spawn judge and the AskUserQuestion reviewer are one command hook, `hooks/call_judge.py`, so an override can lift them.
- The Agent spawn judge also reads the owner rulings a writing role's brief names. A decision named as `decision <slug>` (also `decision: <slug>`, `decision **<slug>**`, or a newline between), `decisions/<slug>` (also `docs/decisions/<slug>.md`) or a backticked slug, with a record in the repo or the claude-settings checkout, adds its `## The ruling` text (1500 characters, 8 records at most) after the reply line. A ruling cut at the cap is followed by a line `[cut: N chars more, read docs/decisions/<slug>.md]`. Each record dropped past the 8 is named on one stderr line. The judge refuses a brief that orders what a shown ruling forbids, at any brief length, and its reason names the record and the ruling's date. A refusal stands whatever record it cites: a cite of a record not shown is no reason to allow. A record that cannot be read fails open with one stderr line. Cost: no new model call. Any brief with a backticked word imports `agent_brief`. A writing role's brief also imports `question_form` and stats one record per backticked word (measured 76-80 ms, no subprocess), then reads up to 8 of the records it names.
- The SendMessage wording judge is a command hook, `hooks/sendmessage_state.py`, so an override can lift it. It judges `parallelism-no-mid-task-talk` by wording alone.
- The Edit and Write judge on `docs/decisions/` is a command hook, `hooks/prose_judge.py`, at Haiku `xhigh`. It judges `speak-rewrite-superseded-in-place` and `rulings-declare-kind`.
- A prompt hook sees only the event's input, never the chat. On Stop that input holds the final reply (`last_assistant_message`), but no earlier message. So no prompt hook judges `roles-one-role-per-agent`. For `style-question-inside-box`, a Stop prompt hook could see whether a reply's question stands alone, but no prompt hook sees the text written before a question box.
- The rules that these hooks read stay `unmechanized` in `lint/rule_mechanisms.json` until a hook catches a real defect.
- A hook that cries wolf is spent (`verification-cry-wolf-guard-is-spent`). Remove one that refuses good input. The trial review of 2026-10-17 11:33 CDT: the refusing judges stay.

**The owner prefers Haiku at `xhigh`** (owner ruling 2026-10-12), but a prompt hook takes no effort field, so a judge that needs it is a command hook that calls Haiku through `decision_watch.invoke_model`. The two prompt judges move to Haiku at `xhigh`, and this record changes in place, when one of these happens:

- Claude Code adds an effort field to prompt hooks.
- A mod judge has its own model call that takes an effort level.

A prompt hook names a full model id, because the prompt-hook evaluator rejects the alias `haiku`. When the model retires, change the `model` value in the judge hooks of `settings.json`, the one place. `lint/test_settings_matcher.py` pins it.

Kind: process
Home: settings.json

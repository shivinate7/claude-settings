# Haiku prompt hooks

The model and effort of each hook named here are rows of the model table (decision `agent-model-cap`, the model per role). This record holds no copy.

## The ruling

**Prompt hooks judge rules that no script can parse.** Each refuses the call when it finds a breach (owner ruling 2026-10-07). A prompt hook cannot warn: it answers `ok` and shows nothing, or refuses with a reason. A refusal returns its reason to the session and the turn goes on (`continueOnBlock`). `settings.json` holds one (counted from its `type: prompt` entries). The AskUserQuestion judge is an Opus agent hook, `question-reviewer-agent-hook`.

| Hook on | Rules it judges |
|---|---|
| `Agent` | `roles-brief-contents`, `tokens-point-brief-at-files`, and the Explore-audit gate of `agent-model-cap` |

- The SendMessage wording judge is a command hook, `hooks/sendmessage_state.py`, so an override can lift it. It judges `parallelism-no-mid-task-talk` by wording alone.
- The Edit and Write judge on `docs/decisions/` is a command hook, `hooks/prose_judge.py`, at Haiku `xhigh`. It judges `speak-rewrite-superseded-in-place` and `rulings-declare-kind`.
- A prompt hook sees only the event's input, never the chat. So no hook judges `style-question-inside-box` or `roles-one-role-per-agent`.
- The rules that these hooks read stay `unmechanized` in `lint/rule_mechanisms.json` until a hook catches a real defect.
- A hook that cries wolf is spent (`verification-cry-wolf-guard-is-spent`). Remove one that refuses good input. The trial review of 2026-10-17 11:33 CDT: the refusing judges stay.

**The owner prefers Haiku at `xhigh`** (owner ruling 2026-10-12), but a prompt hook takes no effort field, so a judge that needs it is a command hook that calls Haiku through `decision_watch.invoke_model`. The two prompt judges move to Haiku at `xhigh`, and this record changes in place, when one of these happens:

- Claude Code adds an effort field to prompt hooks.
- A mod judge has its own model call that takes an effort level.

A prompt hook names a full model id, because the prompt-hook evaluator rejects the alias `haiku`. When the model retires, change the `model` value in the judge hooks of `settings.json`, the one place. `lint/test_settings_matcher.py` pins it.

Kind: process
Home: settings.json

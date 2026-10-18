# Haiku prompt hooks

The model and effort of each hook named here are rows of the model table (decision `subagent-model-cap`, the model per role). This entry holds no copy.

## The ruling

**Prompt hooks judge rules that no script can parse.** Each blocks the call when it finds a breach (owner ruling 2026-10-07). A prompt hook cannot warn: it answers `ok` and shows nothing, or blocks with a reason. A block returns its reason to the session and the turn goes on (`continueOnBlock`). `settings.json` holds five (counted from its `type: prompt` entries).

| Hook on | Rules it judges |
|---|---|
| `AskUserQuestion` | `style-option-says-effect`, `style-question-states-problem`, `output-bring-decisions-as-question` |
| `Agent` | `roles-brief-contents`, `tokens-point-brief-at-files`, and the Explore-audit gate of `subagent-model-cap` |
| `Edit` or `Write` on `decisions/` | `speak-rewrite-superseded-in-place`, `rulings-declare-kind` |
| `SendMessage` | `parallelism-no-mid-task-talk` |

- A prompt hook sees only the event's input, never the chat. So no hook judges `style-question-inside-box` or `roles-one-role-per-worker`. The SendMessage hook cannot see the receiver's task, so it judges by wording alone.
- The rules these hooks and the reply judge judge stay `unmechanized` in `lint/rule_mechanisms.json` until a hook catches a real defect.
- A hook that cries wolf is spent (`verification-cry-wolf-guard-is-spent`). Remove one that blocks good input. The trial review of 2026-10-17 11:33 CDT: the blocking judges stay.

**The judges run on Sonnet** for now (owner ruling 2026-10-12). The owner prefers Haiku at `xhigh`, but a prompt hook takes no effort field. The judges move back to Haiku at `xhigh`, and this record changes in place, when one of these happens:

- Claude Code adds an effort field to prompt hooks.
- A mod judge has its own model call that takes an effort level.

A prompt hook names a full model id, because the prompt-hook evaluator rejects the alias `haiku`. When the model retires, change the `model` value in the judge hooks of `settings.json`, the one place. `lint/test_settings_matcher.py` pins it.

**The Stop reply judge** is `hooks/reply_judge.py`, a command hook (owner ruling 2026-10-12), because a prompt hook cannot exit on a field in code.

- It judges 1 Stop in 5. Only Stops that carry a reply count: Stops 1, 6, 11, and so on (owner ruling 2026-10-13 14:40 CDT). Reason: the judge is advisory, so a model call on every turn end costs calls and latency, and a sample still shows the owner the pattern.
- A damaged, missing or unwritable counter means that Stop is judged. It never refuses and never crashes (`gate-hooks-fail-closed`). A frozen counter therefore means judge every Stop (owner ruling 2026-10-13 17:52 CDT).
- The model call is `decision_watch.invoke_model`, the one home. Model and effort are the reply judge row of the model table.
- A finding never blocks (owner ruling 2026-10-13 11:33 CDT). The hook runs `async: true` and passes the finding as a note at the start of the next turn. Reason: a block came after the owner had read the reply, so the session sent the reply twice. The report-shape gate still blocks.
- It fails open. An error, a timeout or an odd answer prints one stderr line and blocks nothing.
- Its rules are `output-start-with-point`, `style-cut-narration` and `output-never-paste-passing-output`.

Kind: process
Home: hooks/reply_judge.py
Home: settings.json

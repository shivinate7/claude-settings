# Haiku prompt hooks

The model and effort of each hook named here are rows of the model table (decision
`subagent-model-cap`, the model per role). This entry holds no copy.

## The ruling

**Five prompt hooks** judge rules that no script can parse. Each one blocks the call when it finds a
breach (owner ruling 2026-10-07). A prompt hook cannot warn: it answers `ok` and shows nothing, or
blocks with a reason.

| Hook on | Rules it judges |
|---|---|
| `AskUserQuestion` | `style-option-says-effect`, `style-question-states-problem`, `output-bring-decisions-as-question` |
| `Agent` | `roles-brief-contents`, `tokens-point-brief-at-files` |
| `Edit` or `Write` on `decisions/` | `speak-rewrite-superseded-in-place` |
| `SendMessage` | `parallelism-no-mid-task-talk` |

A prompt hook sees only the event's input, never the chat. So no hook judges
`style-question-inside-box` or `roles-one-role-per-worker`. A block returns its reason to the session
and the turn goes on (`continueOnBlock`). The rules these hooks judge stay `unmechanized` in
`lint/rule_mechanisms.json` until a hook catches a real defect. The SendMessage hook cannot see the
receiver's task, so it judges by wording alone. A hook that cries wolf is spent, by
`verification-cry-wolf-guard-is-spent`. Remove one that blocks good input. The trial review of
2026-10-17 11:33 CDT: the blocking judges stay. They work well and can still improve.

**The judges run on Sonnet** for now (owner ruling 2026-10-12). The owner prefers Haiku at `xhigh`.
A prompt hook takes no effort field, so the gap stays open until one of these:

- Claude Code adds an effort field to prompt hooks.
- A mod judge has its own model call that takes an effort level.

Then the judges move back to Haiku at `xhigh`, and this record changes in place. Cost is why
`hooks/decision_watch.py` left Sonnet.

A prompt hook names a full model id. The prompt-hook evaluator rejects the alias `haiku`
(`unrecognized_model`). When the model retires, change the `model` value in the judge hooks of
`settings.json`, the one place. `lint/test_settings_matcher.py` pins it. `hooks/decision_watch.py`
calls the CLI itself, so the alias works there.

**The Stop reply judge** is `hooks/reply_judge.py`, a command hook (owner ruling 2026-10-12). A prompt
hook cannot exit on a field in code, and the old one looped on done replies.

- The loop guard is code. `stop_hook_active` true: exit 0, print nothing, no model call.
- It judges 1 Stop in 5. Only Stops that carry a reply count: Stops 1, 6, 11, and so on (owner ruling
  2026-10-13 14:40 CDT). Reason: the judge is advisory. A Haiku call on every turn end costs model
  calls and latency, and a sample still shows the owner the pattern.
- One counter file per session holds the Stops so far: `state/reply-judge/<sha256 of session id>.count`
  under the config folder. A damaged, missing or unwritable counter means that Stop is judged. It
  never refuses and never crashes (`gate-hooks-fail-closed`). A failed write removes the counter file.
  A frozen counter therefore means judge every Stop (owner ruling 2026-10-13 17:52 CDT).
- The model call is `decision_watch.invoke_model`, the one home. Model and effort are the reply judge
  row of the model table. The caller passes the accepted answer, `{"ok": true|false}`.
- The child runs isolated, as in `decision_watch`, so it cannot fire this hook again.
- A finding never blocks (owner ruling 2026-10-13 11:33 CDT). The hook runs `async: true` and passes
  the finding as a note at the start of the next turn. Reason: a block came after the owner had read
  the reply, so the session sent the reply twice. The report-shape gate still blocks.
- It fails open. An error, a timeout or an odd answer prints one stderr line and blocks nothing.
- Its rules are `output-start-with-point`, `style-cut-narration` and `output-never-paste-passing-output`.
  They stay `unmechanized` in `lint/rule_mechanisms.json` until the hook catches a real defect.

Kind: process
Home: hooks/reply_judge.py
Home: settings.json

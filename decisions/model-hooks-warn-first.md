# Model hooks warn first

The owner ruled on 2026-10-07 which hooks may call a model, and on which model.

## decision_watch

`hooks/decision_watch.py` runs its judgment on `haiku` at effort `xhigh`, with a
120-second model limit. Before, it ran Sonnet with a 60-second limit. The reason: cost.
The hook entry's own timeout in `settings.json` grows to fit the new budget. A timeout
still reads as UNKNOWN, never as ALLOW.

## Four prompt hooks

Four `type: prompt` hooks run on `haiku`. Each one judges a rule that no script can parse.
Each one warns and never blocks. A hook may block only after it catches a real defect,
by `verification-trust-guard-after-red`, trust a guard only once it goes red.

| Hook on | Rules it judges |
|---|---|
| `AskUserQuestion` | `style-option-says-effect`, `style-question-states-problem`, `style-question-inside-box`, `output-bring-decisions-as-question` |
| `Agent` | `roles-brief-contents`, `tokens-point-brief-at-files`, `roles-one-role-per-worker` |
| `Edit` or `Write` on `decisions/` | `speak-rewrite-superseded-in-place` |
| `SendMessage` | `parallelism-no-mid-task-talk` |

A prompt hook sees only the tool call's input, never the chat. The SendMessage hook
cannot see the receiver's task, so it judges by wording alone. A hook that cries wolf is
spent, by `verification-cry-wolf-guard-is-spent`. Remove one that warns on good input.

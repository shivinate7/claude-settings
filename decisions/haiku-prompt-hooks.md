# Haiku prompt hooks

The owner ruled on 2026-10-07 which hooks may call a model, and on which model.

## decision_watch

`hooks/decision_watch.py` runs its judgment on `haiku` at effort `xhigh`, with a
120-second model limit. Before, it ran Sonnet with a 60-second limit. The reason: cost.
The hook entry's own timeout in `settings.json` grows to fit the new budget. A timeout
still reads as UNKNOWN, never as ALLOW.

## Five prompt hooks

Five `type: prompt` hooks run on `haiku`. Each one judges a rule that no script can parse.
Each one blocks the call when it finds a breach, by owner ruling 2026-10-07. This is a trial.
The owner reviews with the orchestrator on 2026-10-14 whether the blocks land well, and
rules then to keep, change or remove each hook. A prompt hook
cannot warn: it answers `ok` and shows nothing, or blocks with a reason.

| Hook on | Rules it judges |
|---|---|
| `AskUserQuestion` | `style-option-says-effect`, `style-question-states-problem`, `style-question-inside-box`, `output-bring-decisions-as-question` |
| `Agent` | `roles-brief-contents`, `tokens-point-brief-at-files`, `roles-one-role-per-worker` |
| `Edit` or `Write` on `decisions/` | `speak-rewrite-superseded-in-place` |
| `SendMessage` | `parallelism-no-mid-task-talk` |
| `Stop`, on `last_assistant_message` | reply rules such as `output-start-with-point`, `style-cut-narration`, `output-never-paste-passing-output` |

A prompt hook sees only the event's input, never the chat. The SendMessage hook cannot
see the receiver's task, so it judges by wording alone. The Stop hook answers `ok` when
`stop_hook_active` is true, so one block never loops. A hook that cries wolf is spent, by
`verification-cry-wolf-guard-is-spent`. Remove one that blocks good input.

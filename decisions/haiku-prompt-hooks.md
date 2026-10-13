# Haiku prompt hooks

The owner ruled on 2026-10-07 which hooks may call a model. On 2026-10-12 the owner ruled
on the model for the prompt hooks.

## decision_watch

`hooks/decision_watch.py` runs its judgment on `haiku` at effort `xhigh`, with a
120-second model limit. Before, it ran Sonnet with a 60-second limit. The reason: cost.
The hook entry's own timeout in `settings.json` grows to fit the new budget. A timeout
still reads as UNKNOWN, never as ALLOW.

## Five prompt hooks

Five `type: prompt` hooks run on `claude-sonnet-5-5`. Each one judges a rule that no script can parse.
Each one blocks the call when it finds a breach, by owner ruling 2026-10-07. This is a trial.
The owner reviews with the orchestrator on 2026-10-14 whether the blocks land well, and
rules then to keep, change or remove each hook. A prompt hook
cannot warn: it answers `ok` and shows nothing, or blocks with a reason.

| Hook on | Rules it judges |
|---|---|
| `AskUserQuestion` | `style-option-says-effect`, `style-question-states-problem`, `output-bring-decisions-as-question` |
| `Agent` | `roles-brief-contents`, `tokens-point-brief-at-files` |
| `Edit` or `Write` on `decisions/` | `speak-rewrite-superseded-in-place` |
| `SendMessage` | `parallelism-no-mid-task-talk` |

A prompt hook sees only the event's input, never the chat. So no hook judges
`style-question-inside-box` or `roles-one-role-per-worker`, because neither hook can see
what those rules need. A block returns its reason to the session and the turn goes on
(`continueOnBlock`). The rules these hooks judge stay `unmechanized` in
`lint/rule_mechanisms.json` until a hook catches a real defect in the trial. The SendMessage hook cannot
see the receiver's task, so it judges by wording alone. A hook that cries wolf is spent, by
`verification-cry-wolf-guard-is-spent`. Remove one that blocks good input.

## Stop reply judge, pulled

The `Stop` prompt judge is removed from `settings.json`, by owner ruling 2026-10-12. Incident:
it ignored its own line "if `stop_hook_active` is true, answer ok". It blocked done replies
in a loop. A prompt hook cannot exit on a field in code. Rebuild it as a command hook that
exits on `stop_hook_active` in code and calls the model itself, as `decision_watch` does.
It stays off until then. Its rules (`output-start-with-point`, `style-cut-narration`,
`output-never-paste-passing-output`) have no judge meanwhile.

## Judge model

The five judges run on Sonnet for now, by owner ruling 2026-10-12. A prompt hook takes no effort
field: the hooks docs list `type`, `prompt`, `model`, `timeout` and `continueOnBlock`, and
the CLI binary agrees. The owner prefers Haiku at `xhigh`, as `decision_watch` runs. The
gap stays open until one of these:

- Claude Code adds an effort field to prompt hooks.
- A mod judge makes its own model call with an effort setting (mods plan, step E).

Then the judges move back to Haiku at `xhigh`, and this record changes in place.

A prompt hook names a full model id. Since 2026-10-08 the prompt-hook evaluator rejects the
alias `haiku` (`unrecognized_model`), so every judge failed open until 2026-10-12.
Measured 2026-10-12, CLI 2.1.296: `claude-sonnet-5-5` returns a verdict in 1.8 to 1.9 seconds
for the longest judge prompt (the `Agent` hook, 3 runs) and for a trivial prompt. The
30-second hook timeout stays. When the model retires, change the `model` value in the judge
hooks of `settings.json`, the one place. `lint/test_settings_matcher.py` pins it.
`hooks/decision_watch.py` is a script that calls the CLI itself, and it keeps `haiku`. Its
`claude -p --model haiku` call works (measured 2026-10-12: it replied "ok"). Only the
settings prompt-hook evaluator rejects the alias.

Limits, named:

- The test checks the `claude-` prefix only. A well-formed wrong id, such as `claude-sonnet-5`,
  passes the test and fails open. Only a live call proves the id.
- Tested in the headless CLI only, not in the desktop app.
- The latency run used a Bash call as input. A real judged input is longer, so the figure
  is a floor.
- The judge on Sonnet costs more than Haiku. Unmeasured.
- `lint/rule_mechanisms.json` still says "Haiku prompt hook" in its reasons.

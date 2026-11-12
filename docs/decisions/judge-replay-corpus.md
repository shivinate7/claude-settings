# Each model judge has a corpus of known allow and deny cases, replayed in CI when the judge changes

## The ruling

Owner, 2026-11-06 12:43 CST (waiting-page item 279, pick b): a replay corpus per model judge, with known allow and deny cases, in the style of decision `mutation-ci-report-and-replay`. CI runs a judge's corpus only when its prompt, model or code changes. A normal use makes no model call. A CI run that touches a judge makes one call per case. The repo secret `CLAUDE_CODE_OAUTH_TOKEN` is set (owner, waiting-page items 283 and 282 b).

## Departs from

Item 279 pick b, whole text: "Replay cases for each judge. A set of known allow and deny cases runs in CI whenever a judge's prompt or model changes." Gain: "A judge that starts allowing what it should refuse is caught before it merges." Lose: "Model calls in CI only, when a judge changes." The owner picked a, b and d at 12:43 CST on 2026-11-06. It names the corpus and nothing else. It says nothing about a retry or a batch cap. So three `feedback_guard` behaviours are lane choices pending the owner, with no ruling found in the repo. They are the retry of an item that got no verdict, the cap of 20 new items per Stop (REPEAT_BATCH, hooks/feedback_guard.py), and the marking split. In the marking split, the model gives a verdict and then writing the ` repeats` mark to the inbox raises. The sent items stay in `judged`, so the next Stop does not send them again (`judge_stop`; proved by `case_repeat_mark_failure_after_verdict_keeps_items_judged`). Main treats every failure as judged, so this is not new behaviour. The lane choice is the split: a failure while judging keeps the items unjudged, and a failure while marking does not. Triage found no other item for them (asked 08:15 CST, 2026-11-12). Decision owner-feedback-inbox holds all three.

The per-source caps of 400 candidates in all and 200 roadmap, 100 backlog and 100 inbox lines (`REPEAT_MAX` and `REPEAT_SHARES`, hooks/feedback_guard.py) are not on this list. They exist on main already, and decision owner-feedback-inbox holds them.

## The shape

- The runner is `hooks/judge_replay.py`. Its modes: `--changed BASE` (the judges whose scope the committed diff BASE...HEAD touches, or every judge when the diff moves the claude CLI pin), `--judge NAME`, `--all`, `--paths` (names the touched judges from paths on stdin), `--probe` (one small call, to prove the sign-in) and `--runs N` (default 1).
- Eleven judges, one corpus each, in `.github/judge-replay/corpus/<name>.json`, except the page judge, which has none yet: `call_judge.spawn`, `call_judge.question`, `call_judge.page`, `call_judge.opus_ask`, `call_judge.opus_scope`, `prose_judge`, `reply_judge`, `feedback_guard` (the repeat check), `report_guard.past_ruling`, `sendmessage_state` (the state judge and the wording judge) and `decision_watch`.
- The page judge's 5 cases are pending step `judge-replay-page-cases`. Their expected verdicts can only be recorded by a CI run with the secret, and no unrecorded verdict enters a batch (coordinator, 2026-11-12 07:41 and 08:35 CST). Until then the page judge has no corpus file, its row runs zero cases and reads `no cases yet` and `pending step judge-replay-page-cases`, and it exits 0. A judge with no corpus file reads `no cases yet` too.
- A case is `{id, expect, source, input, agreement}`. `expect` is `allow` or `deny`. `source` names the fixture case or record it came from. `input` is the judge's own input. The runner holds no prompt: one adapter per judge turns `input` into the arguments of the judge's real entry function, and the entry builds its own prompt and calls `decision_watch.invoke_model`, the one model seam.
- The adapter reads what the entry did. A refusal, a finding or a flag is `deny`. An entry that ran and said nothing is `allow`. No model call, or a model error, is `unknown`: an entry that fails open prints no verdict, so the adapter reads the model's own answer to tell the two apart.
- The runner replaces `guard_core.refuse` and `record` while an entry runs, so a replay writes no `guard.log` line and no override file lifts a refusal. `question_form.past_rulings` is replaced by the case's own `rulings`, so a prompt does not move with this repo's records. A `decision_watch` case builds a temp git repo and a transcript, and removes both.
- Each judge row in `JUDGES` also holds `answers`: the model answer, in that judge's own shape, that its entry maps to `allow` and to `deny`. A later test can drive PASS and MISS with them.
- The scope of a judge is the seam (`hooks/decision_watch.py`), `hooks/guard.py` (`decision_watch` imports it) and `hooks/shared_names.py` (it holds prompt text: the spawn marker and the gh logins) and `hooks/_nowindow.py` (`decision_watch.run` starts every model call in it), the judge's own files, any module its prompt or model comes from (`report_guard` reads `call_judge.PAST_RULING_MODEL`; the page and question judges build their prompt tail in `hooks/question_form.py`; `opus_scope` reads its roles from `hooks/override.py`) and its corpus. A change to one of these touches every judge: the runner, its test, the CLI pin (`.github/judge-replay/package.json` or its `package-lock.json`), a `hooks/guard_*.py` module, `hooks/git_reads.py` (`hooks/guard.py` loads them), or a corpus file that belongs to no judge.
- A case is PASS or MISS only when one answer holds a strict majority of its runs. A run whose model call fails or never happens is no answer: it never counts as agreeing with an answer or with another error, so two allows and an error read allow, and one allow and two errors read UNKNOWN. A split with no majority is UNKNOWN too. The agreement string is `answered-and-agreeing/runs`, so an error shows as a shortfall.

## The CI job

`.github/scripts/ci-scope.sh` sets `judge_replay` from `hooks/judge_replay.py --paths`, the one home of the scope lists. It is true on a pull request whose diff touches a scope path. It is also true on a diff it cannot read, on a change to the script or the workflow, and on `workflow_dispatch`. It is false on a push or a schedule, because the pull request already ran the replay.

The `judge-replay` job in `checks.yml` is in `all-jobs-passed` and `ci-done`. Like every scoped job it always runs, and its steps carry the scope condition. A pull request from a fork skips them: it has no secret. The steps install the `claude` CLI with `npm ci` from `.github/judge-replay/` (a `package.json` and a lockfile that hold only the pin, 2.1.319; the install scripts run, because the package links its native binary in a postinstall step), write the secret to `<CLAUDE_CONFIG_DIR>/state/hook-token` (the file `decision_watch._hook_token` reads; no file when the secret is empty), run `--probe`, then `--changed origin/<base> --runs 3` on a pull request or `--all --runs 3` on dispatch. `hooks/test_judge_replay.py` runs in the `checks` job. The pin has one home, `.github/judge-replay/package.json`. `--changed` reads the diff for a change to that folder, and also for an added or removed workflow line that names `@anthropic-ai/claude-code@`, a pin typed into a step. Either one replays every judge, because a new CLI can move a verdict.

## The unknown rule

A replay that cannot get an answer is UNKNOWN, and under `CI` it exits 1 (decision `ci-unknown-is-red`). With no sign-in the line is: `UNKNOWN: model calls cannot authenticate. Add repo secret CLAUDE_CODE_OAUTH_TOKEN (owner, waiting page item 283).` The probe step prints it and exits 1 whatever `CI` holds, so a missing or bad secret is red before any case runs. A MISS always exits 1.

## Measured

2026-11-06, in a cloud container, the real models, 3 runs of each case through `replay(name, runs=3)`. The table counts the 53 cases of the corpus: 159 calls, 159 answers equal to the expected answer. The page judge's 5 cases are not in it (pending step `judge-replay-page-cases`).

| Judge | Allow | Deny | Agreement |
|---|---|---|---|
| `call_judge.spawn` | 3 | 4 | 3/3 each |
| `call_judge.question` | 3 | 3 | 3/3 each |
| `call_judge.page` | pending | pending | pending step `judge-replay-page-cases` |
| `call_judge.opus_ask` | 3 | 4 | 3/3 each |
| `call_judge.opus_scope` | 2 | 2 | 3/3 each |
| `prose_judge` | 2 | 3 | 3/3 each |
| `reply_judge` | 3 | 3 | 3/3 each |
| `feedback_guard` | 2 | 2 | 3/3 each |
| `report_guard.past_ruling` | 2 | 2 | 3/3 each |
| `sendmessage_state` | 3 | 3 | 3/3 each |
| `decision_watch` | 2 | 2 | 3/3 each |

Cases that did not hold stayed out, so the corpus keeps only 3/3 cases and each carries `"agreement": "3/3"`:

- `call_judge.question` `ship-today-passes` read 2/3 with the old fixture's `Departs from` line, which names `main` and a guard. It was rewritten in plain words and read 3/3.
- `call_judge.question` `cited-ruling-reask-passes` read 3/3 deny. The model refused it because its `Departs from` line did not fit the question. It was rewritten with new facts (40 Renovate PRs in a week) and a fitting line, and read 3/3 allow.
- `call_judge.opus_scope` `context-names-builders-and-test-authors` read 2/3, and `context-names-test-author-and-reviewer` read 3/3 allow in one run and 3/3 deny in the next. Both were dropped. A third try with one test-author prompt read 2 of 4. The builders case replaced them (4 of 4).
- `sendmessage_state` `wording-progress-check-between-peers` read 2/3 and was dropped.

One serial `--all` run, one run per case, made before the page judge's cases left the corpus: 58 calls in 201 s. The 53-case corpus is unmeasured.

## Cost

- Normal use: no call and no process. The runner is not named in `settings.json` or in any hook.
- A CI run that touches a judge: N calls, N being the cases of each touched judge times 3 (`--runs 3`; a case needs a strict majority of all 3 runs, so 2 agreeing answers and 1 error pass at 2/3, and 1 answer and 2 errors read UNKNOWN). `--all`, and a change that touches every judge, is 159 calls and the probe (about 9 min, unmeasured in CI: 3 x the 201 s local run, scaled from 58 to 53 cases). The job runs only with the secret `CLAUDE_CODE_OAUTH_TOKEN` and skips a pull request from a fork, so a fork costs no call. The job reads the diff with the `--paths` call of the scope step (one Python start, no call) and starts one `claude -p` process per call. A `decision_watch` case also starts the git processes of its temp repo and of the judge's own status, diff and log reads, and removes the folder after.
- Files written: none in the repo. The CI job writes one token file (`state/hook-token`) in a runner temp folder.
- Job cap (decision `ci-job-caps`): 75 minutes, the interim stopgap (owner, 2026-11-10 12:11 CST). The 53 cases' timeouts add up to 2122 s. If every call hung to its timeout, the replay would run 3 x 2122 s (6366 s, about 106 min), and the cap would cancel the job. `all-jobs-passed` reads a cancelled job as not passed, so the run still fails, but with no red step. A step-level timeout is not added. The figure at 75 is unmeasured; the first CI run on a pull request that touches a judge replaces it.

## The reader

CI, on a pull request that touches a judge. A MISS names the case and what the judge answered, and fails `all-jobs-passed`. A judge change that flips a known case is then a visible, fixable red, or a corpus change with its reason.

## Limits

- A prompt that a judge reads from a file at run time, such as a record, is not in scope. The `rulings` of a case replace it.
- The `feedback_guard` adapter calls `feedback_guard.judge(homes, inbox, blocks, new)` with no repo, so only the inbox's own earlier messages are candidates. A `why` from `judge` (an error, an off-shape answer or a bad entry) reads UNKNOWN. A change to the signature turns the adapter red, which the suite reads as an error, not a verdict.
- The `sendmessage_state` entry always starts the wording judge, and starts the state judge for a busy receiver. One case drives one of them. The adapter answers the other call itself, so it is no model call of the case. It tells the wording call by its model, `sendmessage_state.WORDING_MODEL`, and holds no prompt text.
- The no-secret path is proven by the fake no-answer in `hooks/test_judge_replay.py`. The real secret has not been read from CI yet: the first CI run is the proof.

Kind: process
Home: hooks/judge_replay.py

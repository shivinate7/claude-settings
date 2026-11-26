# A merge config change that needs new tool code lands in two pull requests

## The ruling

- A pull request may change the merge config alone when the merge tool on the stable branch already reads each value and key it adds.
- A change to the merge config that needs new merge-tool code lands in two pull requests.
- The first pull request lands the tool code.
- The second pull request changes the config, and it lands only after the stable branch holds the tool code.
- Why: the launcher runs the merge tool from the stable branch, and the tool reads the config from main, so a config value can outrun the tool.
- Related: decision `stable-branch` (the stable branch follows each green push run of main); decision `merge-reinstalls-from-main` (the launcher's pin moves to the stable branch).

## Mistake

- On 2026-11-25 at 11:13 CST, pull request #3863 (branch `confirm-needs-proof`) set `merge.requiredChecks` in `.github/stamp.json` to a value that the tool reads only in the same pull request.
- Pull request #3871 (branch `lint-runs-listed-suites`) added the key `merge.lintSuites` the same way.
- The stable branch was 352 commits behind main.
- So the tool refused main's config, and every merge in the repo was refused.
- The stable branch could not catch up, because main's push runs were queued for runners.

## Harm

- No session could merge in the repo.
- The way out was the launcher's recovery switch, read `merge/launch.py`.

## Check

- `merge/merge.py` `head_config_refusal` judges a pull request head's `.github/stamp.json` with the running tool's own `parse_config`.
- It judges only a pull request whose diff against its base touches that file.
- It runs in the lane lint of a pull request number, in the ready path (`draft_step`) and in `confirm()`, each before any claim or push.
- It does not run under `--fast-checks`, nor for a ref or commit target.
- The refusal gives the parser's reason, then a remedy that follows the cause. The cause comes from the key (`ConfigValueStop.cause`): `requiredChecks` is `newer`, `method` is `either`, and every other key is `wrong`. An unknown field in the merge block is `newer`, whatever its spelling.
  - `newer` (an unknown key, `requiredChecks`): the stable branch does not know the value or key yet, so every merge in the repo would be refused once the change lands. The remedy: land the tool change first, wait until the stable branch holds it, then change the file in a second pull request.
  - `either` (`method`): names both causes and each fix. Either the stable branch does not know the value yet, so land the tool change first and wait, then change the file in a second pull request. Or the value is a typo, so fix the file and push.
  - `wrong` (every other key): the reason and the fix, with no stable clause.
- A head whose top level or `merge` key is not an object, or whose file is not valid JSON, gets one line with the reason and a fix-first remedy, and no stable part.

## Limits

- It protects only once this change is on the stable branch.
- An unreadable diff or an unreadable head file is unknown and refuses. So is a stop from the head's parse that is not a verdict on a value: an `ignoreChecks` entry with no name or reason, or a workflow file the caps cannot read.
- Only a file the pull request deletes is not judged: the base's stamp decides.
- A run from the pull request's own tree passes by construction, so the check protects only a run of an older tool.
- It does not retire the older-tool debt, titled "An older merge tool refuses the stamp", which is about machines whose installed tool is older than this change.

## Cost

- At most one `git diff --name-status --no-renames origin/<base>...<head> -- .github/stamp.json` per call.
- A touched file adds at most one `git show` of the head file and one parse. The parse reads the head's workflow caps: at most one `git ls-tree` of `.github/workflows`, at most one `git show` per workflow file, and at most one `git check-ref-format --branch` per `keepBranches` entry that passes the name check. At head af4a47b89e (the round-2 code head) that is at most 5 workflow files and at most 5 `keepBranches` entries, counted with `git ls-tree -r --name-only af4a47b89e -- .github/workflows` and `git show af4a47b89e:.github/stamp.json`.
- No process, log or timer is added.

Kind: process
Home: merge/merge.py
Done check: `merge/test_lane_lint.py`: `ConfigAtPrHead` (lane lint) and the `test_pre_ready_` cases of `ReadyChecks` (ready path). `merge/test_merge.py`: `HeadConfigOnConfirm` (confirm) and `ConfigFile` (the base's stamp, read by the same `parse_config`).
Source: the consultant's own mistake, 2026-11-25 11:13 CST. No owner ruling.
Recorded: 2026-11-25 11:49 CST.

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
- It runs in the lane lint of a pull request number, and in the ready path before any push.
- It does not run under `--fast-checks`, nor for a ref or commit target.
- Its refusal has three parts: the parser's reason; that the stable branch does not know the value or key yet; the remedy, which is to land the tool change first, wait until the stable branch holds it, then change the file in a second pull request.
- A head whose top level or `merge` key is not an object, or whose file is not valid JSON, gets one line with the reason and a fix-first remedy, and no stable part.

## Limits

- It protects only once this change is on the stable branch.
- An unreadable diff, a deleted file or an unreadable file is not judged, and the base's stamp decides.
- A run from the pull request's own tree passes by construction, so the check protects only a run of an older tool.
- It does not retire the older-tool debt, titled "An older merge tool refuses the stamp", which is about machines whose installed tool is older than this change.

## Cost

- One `git diff --name-only` per judged pull request.
- A touched file adds one `git show` and one parse.
- No process, log or timer is added.

Kind: process
Home: merge/merge.py
Done check: `merge/test_lane_lint.py` (`ConfigAtPrHead`, `ReadyChecks`) and `merge/test_merge.py` (`ConfigFile`).
Source: the consultant's own mistake, 2026-11-25 11:13 CST. No owner ruling.
Recorded: 2026-11-25 11:49 CST.

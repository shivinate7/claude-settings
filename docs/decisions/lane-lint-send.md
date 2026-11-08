# A lane hands a batch runner only a pull request that passed its lint

## The ruling

Rule `lane-lint-send` in `hooks/guard.py` refuses a `send_message` to a batch runner that names an open pull request with no review record at its live head. Its home is `lane_lint_send_hit` in `hooks/guard_merge.py`. The review record is the proof of a lint pass, because `merge <pr> --review-record` refuses a head with no lint marker (decision `pr-review-record`). Step `handoff-needs-lane-lint` (2026-11-08): refuse a lane's hand-off message to the batch runner for a pull request whose live head has no passing `merge --lane-lint`.

- The mistake: at 11:49 CST on 2026-11-08, lane override-plain-ask handed pull requests 1463, 1513 and 1583 to the batch runner before their lint. All three failed it.
- The harm: the batch runner took heads that fail CI's lint steps. Each failure costs a fix lane, a new review record and a rerun of the batch's one CI run (`git-integration-branch-merge`).
- The target is a runner when its newest session record carries `cs-build:batch-runner`. A record is a `get_session` result, a `create_session` call and its result, or a `list_sessions` row (`own_session_read(..., listed=True)` in `hooks/own_session.py`). The newest record decides. The own-role proof of rule `merge-role-proof` leaves `listed` off, so it never rests on a list.
- The message is judged on each `#n` and each `github.com/<owner>/<name>/pull/<n>` URL, at most five. A bare `#n` takes the repo from the target's `cs-repo:` tag, else from the origin of the checkout holding the cwd. A number with no `#` names no pull request.
- A closed or merged pull request passes. So does an issue: `pulls/<n>` answers 404 and `issues/<n>` answers an object with no `pull_request` key. A number that is neither is unknown.
- An open pull request passes only when its newest review record parses and its `Head` equals the live head. `hand_off_read` in `merge/merge.py` makes the read and `newest_review` parses it. `reviewed_read` calls `newest_review` too, so no second reader of "the record of this pull request" exists.
- A send to a target that is no runner makes no pull request read. A message that names no pull request makes no read at all.
- The refusal names each open pull request and the remedy: run `merge --lane-lint <pr>`, write the record with `merge <pr> --review-record`, post it, then send again. An override lifts it.
- Unknown allows, with one guard.log line and one stderr line. Unknown is: a read that fails, a read past `LANE_LINT_SEND_SECONDS` (default 25 s, one deadline for the message), a bare `#n` with no repo, a merge tool that does not load, and a sixth pull request. Why: a check that blocks on its own fault cries wolf (`guard-that-cries-wolf-is-spent`). The hand-off cost is one retry, and CI still carries every step.

## The lint marker

`merge --lane-lint` writes an empty file named by the full 40-hex head under `${CLAUDE_CONFIG_DIR:-~/.claude}/state/lane-lint/`. It writes it on a pass, and on an unknown that `--lint-unknown-ok` lifted with a reason. A failed lint and an unexcused unknown write none. `merge <pr> --review-record` refuses when there is no marker for `--head`, and prints no record. The marker's one reader is that refusal. The guard reads no marker: it reads the record. A marker is per machine, so a lane that lints in one session and writes its record in another runs the lint again.

## Lane picks

None is an owner ruling. Lane pick, 2026-11-08 CST.

- A target with no usable record, or one retagged after its record, is refused once per target per session with a steer to `get_session` on the target alone, then retry. The retry passes, found by an earlier send to that target in the transcript whose result names this rule. This matches `brief_hit`. Not taken: refuse every send until a record exists, which would loop for a target the sender cannot read.
- The newest review record decides, as in `merge --reviewed`. A record with `Head` equal to the live head clears the pull request whatever its round verdicts say: the lint is the gate here, and the done rules stay the batch runner's.
- Skip a closed or merged pull request. A hand-off may name one in a status line.
- More than five pull requests is unknown, not a refusal: five reads fit the cap, and a larger message is a status report.
- The 404 of `pulls/<n>` is checked against `issues/<n>` before a number is skipped as an issue, so a repo the guard cannot read never passes as a list of issues.

## Cost

- A message with no pull request, or to a target that is no runner: one transcript read, no `gh` call, no file.
- A message to a runner: one pulls read per judged number (one issues read more for a number that is no pull request), and, when any is an open pull request, one paged read of the repo's issue comments since the oldest of them opened. At most five numbers. A URL of another repo adds that repo's reads. All reads share one deadline. Each is one `gh` process, and none stays.
- A bare `#n` with no `cs-repo` tag starts one `git` read for the origin.
- One marker file per lint pass. No timer, log or cache beyond the unknown allow's one guard.log line.
- Proven by the lane-lint-send cases in `hooks/test_guard.py`: a non-runner target makes no read, and a runner target makes at least one.

Protected by `hooks/test_guard.py` (the lane-lint-send cases), `merge/test_merge.py` (`LaneLintMarker`) and `merge/test_lane_lint.py`, red before the rule landed.

Kind: process
Home: hooks/guard_merge.py

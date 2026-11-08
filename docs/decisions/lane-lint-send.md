# A lane hands a batch runner only a pull request that passed its lint

## The ruling

Rule `lane-lint-send` in `hooks/guard.py` refuses a `send_message` to a batch runner that names an open pull request. It refuses when that pull request has no review record at its live head, or no lint marker for that head in this container. Its home is `lane_lint_send_hit` in `hooks/guard_merge.py`. The review record is the proof of a lint pass, because `merge <pr> --review-record` refuses a head with no lint marker (decision `pr-review-record`). Step `handoff-needs-lane-lint` (2026-11-08): refuse a lane's hand-off message to the batch runner for a pull request whose live head has no passing `merge --lane-lint`.

- The mistake: at 11:49 CST on 2026-11-08, lane override-plain-ask handed pull requests 1463, 1513 and 1583 to the batch runner before their lint. All three failed it.
- The harm: the batch runner took heads that fail CI's lint steps. Each failure costs a fix lane, a new review record and a rerun of the batch's one CI run (`git-integration-branch-merge`).
- The target is a runner when its newest session record carries `cs-build:batch-runner`. A record is a `get_session` result, a `create_session` call and its result, or a `list_sessions` row (`own_session_read(..., listed=True)` in `hooks/own_session.py`). The newest record decides. The own-role proof of rule `merge-role-proof` leaves `listed` off, so it never rests on a list.
- The message is judged on each `#n`, each `PR#n`, each `owner/name#n` and each `github.com/<owner>/<name>/pull/<n>` URL, at most five. The URL may carry `https://`, `www.`, both or neither. A bare `#n` takes the repo from the target's `cs-repo:` tag, else from the origin of the checkout holding the cwd. A number with no `#` names no pull request.
- A closed or merged pull request passes. So does an issue: `pulls/<n>` answers 404 and `issues/<n>` answers an object with no `pull_request` key. A number that is neither is unknown.
- An open pull request passes only when its newest review record parses, its `Head` equals the live head, and the live head has its lint marker. `hand_off_read` in `merge/merge.py` makes the read and `newest_review` parses it. `reviewed_read` calls `newest_review` too, so no second reader of "the record of this pull request" exists. `record_at_head` is the one head compare, called by `review_state` and `hand_off_read`. `lane_lint_passed` is the one marker reader, called by `hand_off_read` and the `--review-record` refusal.
- A send to a target that is no runner makes no pull request read. A message that names no pull request makes no read at all.
- An override lifts the refusal.
- Unknown allows, with one guard.log line and one stderr line. Unknown is: a read that fails, a read past `LANE_LINT_SEND_SECONDS` (default 25 s, one deadline for the message), or a repo token that is no GitHub owner/name. A bare `#n` with no repo, a merge tool that does not load, and a sixth pull request are unknown too. Why: a check that refuses on its own fault cries wolf (`guard-that-cries-wolf-is-spent`). The hand-off cost is one retry, and CI still carries every step.

## The lint marker

`merge --lane-lint` writes an empty file named by the full 40-hex head under `${CLAUDE_CONFIG_DIR:-~/.claude}/state/lane-lint/`. It writes it on a pass, and on an unknown that `--lint-unknown-ok` lifted with a reason. A failed lint and an unexcused unknown write none. `merge <pr> --review-record` refuses when there is no marker for `--head`, and prints no record. The marker has two callers of its one reader, `lane_lint_passed`: that refusal, and the hand-off guard, which reads the folder through `LANE_LINT_MARKER_DIR` in `merge/merge.py`, its one home.

A marker is per container. Lane pick, 2026-11-08 CST: the guard requires it of the sender. So any sender in another container than the one that linted runs `merge --lane-lint <pr>` before the hand-off passes, even when the record is already posted. That cost falls on:

- a coordinator that relays a lane's hand-off to the runner;
- a lane resumed in a fresh container, or after a restart that lost the marker folder;
- a hand-off sent again to a rotated runner from a session in a new container.

Each pays one lint run per head. Not taken: trust the record alone, which passes a record written from another container's lint.

## Lane picks

Each is a lane pick, 2026-11-08 CST. None is an owner ruling.

- Two refusal texts. Lane pick, 2026-11-08 CST. A pull request with no record at its live head: the remedy is to run the lint, write the record with `merge <pr> --review-record`, and post the review record. A pull request with a record at its head but no marker here: the remedy is to run `merge --lane-lint <pr>`, and the text says the marker is per container. A message with both kinds gets both texts in one refusal. `hand_off_read` returns `unlinted` for the second kind, so the guard tells them apart without a second read.
- The retry. Lane pick, 2026-11-08 CST. A `session_` target with no usable record, or one retagged after its record, is refused with a steer to `get_session` on the target alone, then retry. The exact retry passes only when a `get_session` call on that target follows the refusal in the transcript, whatever that call returned (`_send_refusal_spent`). A readable record from it is the target's newest record, so the retry is judged by it. An unreadable one lets the retry pass, and a later identical retry passes too, so the guard never loops. A send with other text is judged afresh. Not taken: refuse every send until a record exists, which loops for a target the sender cannot read. Not taken: pass any retry after one refusal, which skipped the read the steer asks for. Not taken: pass any send after one refusal, which let a different hand-off through unjudged.
- A target that is not a `session_` id, such as `@parent`, with no record: no refusal and no read. Lane pick, 2026-11-08 CST. The sender cannot `get_session` an address, so the steer could only loop.
- Each repo is judged alone. Lane pick, 2026-11-08 CST. A failed read, or a repo token that is no plausible owner/name, leaves only that repo's pull requests unknown, with one note for the message. It never voids the rest: in `PR#1463/PR#1513` the token `1463/PR` fails alone and `#1463` and `#1513` are judged; in `docs/foo.md#12 and #1463` the `docs/foo.md` read fails and `#1463` is judged. A read past the shared deadline leaves each later repo unknown too, since each gets about 0.05 s.
- A `/` after a digit separates refs. Lane pick, 2026-11-08 CST. `#1463/#1513/#1583` judges all three. A `/` after a letter still blocks the match, so `docs/#41` names no pull request.
- With no transcript to read, the refusal could never be spent, so the send passes with one note.
- `owner/name#n` is judged and takes its repo from the prefix. A `name#n` with no owner is not judged: it names no repo the guard can read. `PR#n` is judged as a bare `#n`.
- The newest review record decides, as in `merge --reviewed`. A record with `Head` equal to the live head clears the pull request whatever its round verdicts say: the lint is the check here, and the done rules stay the batch runner's.
- Skip a closed or merged pull request. A hand-off may name one in a status line.
- More than five pull requests is unknown, not a refusal: five reads fit the cap, and a larger message is a status report. Debt `lane-send-five-pr-cap`.
- The 404 of `pulls/<n>` is checked against `issues/<n>` before a number is skipped as an issue, so a repo the guard cannot read never passes as a list of issues.
- Known gaps: debt `lane-send-no-sender-check` (a "do not take #n" line to a runner is refused). Debt `lane-send-comment-paging` (the comment read pages since the oldest open pull request). Debt `lane-send-marker-per-container` (a relayed hand-off re-runs the lint in each new container). Debt `lane-send-first-send-steer` (a first hand-off to a parent is refused once for no record). A send addressed by `to:` with no `session_id` is not judged (notes line `lane-send-to-unjudged`).

## Cost

- A message with no pull request: no read. A message that names one, to a target that is no runner, or to a non-`session_` target with no record: one transcript read, no `gh` call, no file. A `session_` target with no usable record costs a second transcript read, the scan for a spent refusal and a later `get_session`.
- A message to a runner costs, per repo, one pulls read per judged number. A number that is no pull request adds one issues read. When any is an open pull request, it adds one paged read of the repo's issue comments since the oldest of them opened. At most five numbers. A URL or `owner/name#n` of another repo adds that repo's reads. A token that is no owner/name makes no read. All reads share one deadline. Each is one `gh` process, and none stays.
- A bare `#n` with no `cs-repo` tag starts one `git` read for the origin.
- One marker file per lint pass, and one `exists` check per open pull request with a record at its head. No timer, log or cache beyond the unknown allow's one guard.log line.
- Proven by the lane-lint-send cases in `hooks/test_guard.py`: a non-runner target and an `@parent` target make no read, and a runner target makes at least one.

Protected by `hooks/test_guard.py` (the lane-lint-send cases), `merge/test_merge.py` (`LaneLintMarker`) and `merge/test_lane_lint.py`, red before the rule landed.

Kind: process
Home: hooks/guard_merge.py

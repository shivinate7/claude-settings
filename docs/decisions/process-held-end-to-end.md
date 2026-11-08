# Every hand-over in the work process gets a mechanical hold

## The ask

Owner, page, 2026-11-07 about 19:05 CST: "this whole process should have been mechanically held end to end."

- A hand-over is one step from one stage of the work to the next. There are 15, from a found gap to an archived step.
- The table names each hand-over's check, its status, the break the audit saw, the gold state, and the proposal with its done check.
- Source: a five-part audit by Explore agents. It is unverified. Every file:symbol cell was grepped against the code. The record branch's `roadmap/build.py` was read on `origin/roadmap`.

Status values: held (a check refuses or asks), partial (some check, a named gap), detective (flags after the fact), prose only (a rule in text), in build (a step builds the check).

## The hand-overs

| Hand-over | Held by today (file:symbol) | Status | Break seen | Gold (what held looks like) | Proposal + done check |
|---|---|---|---|---|---|
| 1. Found gap to note or step | `docs/debts/README.md` (prose, line 24). `lint/report_guard.py:mistake_problem`, `MISTAKE_REASON`, `refusal_reason`. Rule `roles-findings-are-debts-or-notes` (each finding is a debt or a note) is unmechanized. | in build: `notes-name-their-fix` (each new notes or debt line names its fix). Prose only today. | Break 6: 1,508 notes entries (audit count), 28 with `Fix:`, 1,480 without. | Each new gap line names a step slug, or a listed reason for no fix. A recorded gap with no started fix is refused. | `notes-name-their-fix`. Step done check: red tests for a notes line with no fix and for a recorded gap with no started fix, then green. |
| 2. Note to step | `origin/roadmap:roadmap/build.py:check_staged` (refuses a note past `NOTE_WORDS`, 250 words), `conflict_markers`, `upkeep` (warns only). | prose only. No gap-key check. | Break 8: five gaps, each filed as two steps. | A new step that repeats an open step's gap key is refused at the commit that stages it. | New step `step-names-its-gap` (a new step names its gap key; see Proposals). Done check: a red test where a staged step whose gap key matches an open step's is refused, then green. |
| 3. Step to lane start | `skills/roadmap/build.py:todo_pairs` (`PAIR_LINE`) and `stalled` (`STALLED_LINE`): after the fact, on demand. CI runs `test_build.py` only. `hooks/guard.py:lane_effort_hit`, `lane_repo_tag_hit`: checks at create_session. `hooks/guard_merge.py:ARCHIVE_STEP_PREFIX`: a `cs-step` tag (a session tag naming its step) is read only at archive. | detective. in build: `lane-start-overlap-check` (a lane start checks for overlap). Named by audit, not read: `doing-needs-live-lane` (a doing step needs a live lane), `one-lane-one-step`. | None named. Gap: a lane can start with no `cs-step` tag, so no step is named. | A lane cannot start unless it names one open step, and an overlap is refused. | `lane-start-overlap-check`, extended (see Proposals). Step done check: a red test where a create_session with a `cs-step` tag an open lane already holds is refused. |
| 4. Lane start to brief | `hooks/call_judge.py:SPAWN_PROMPT`: a model judge that fails open, with no report cap, on Agent spawns only. `hooks/agent_brief.py` (advisory). `hooks/blind_brief.py` (designer briefs only). `hooks/guard.py:marker_scan`, `brief_markers` (model markers only). Rule `roles-brief-contents` (a brief carries its parts) is unmechanized. | partial (model judge). Named by audit, not read: `brief-claim-has-probe` (a brief claim needs a probe), `guard-brief-reproduces-incident` (a guard reproduces an incident). | None named. Gap: the judge checks no report cap and never sees a lane brief sent by `send_message`. | A brief missing its task, files, rulings, failure classes, check or report cap is refused before the agent starts. | `brief-claim-has-probe` and `guard-brief-reproduces-incident`, both steps. The cap and `send_message` gaps: one note (see Notes). |
| 5. Brief to red run | `lint/check_red_run.py:main`, run by the CI step "Red-run trailer" in `.github/workflows/checks.yml` (PR only), and `merge/merge.py:lane_lint`. | partial: checked after the push. in build: `red-run-pre-push` (the guard checks the `Red-run:` line before a push). | Test commit 1f35b617 was pushed with no `Red-run:` line. Commit af063548b was pushed with a malformed line. Both were found after the push (audit B, not in the d-breaks file). | Each test commit's `Red-run:` line is checked before the push sends it. | `red-run-pre-push`. Step done check: a red test on a push of a test commit with no Red-run line, then green. |
| 6. Red run to builder | `hooks/guard.py:own_changes`: refuses a builder's commit, push, Edit or Write on a test path (rules `builder-diff` and `builder-test-edit`, which refuse a builder's test change). | held. | None named. Gaps (audit B): a squash or `cherry-pick -n` route; an unread diff is logged and allowed (rule `role-diff-unread`); the main session is not covered; an author's diff is only logged. | A builder cannot change a test by any git route. | None on the final list. The four gaps need a note or a debt (see Input Needed). |
| 7. Builder to review rounds | `hooks/guard.py:step_up_reason` (round 2 reviewer on Sonnet, round 3 builder on Opus), `opus_spawn_hit`. Not held: that a reviewer is spawned at all. The three-round cap (rule `roles-review-cap-three`: three review rounds at most; unmechanized, though `merge/merge.py:parse_review` rejects a round above 3). `merge/merge.py:confirm` never reads `review_state`. | partial. | None logged. Gap: a PR with no record can merge. | A merge refuses a lane tip with no PASS record for that head. | The open question below. No step. |
| 8. Review rounds to review record | `merge/merge.py:review_body`, `parse_review`, `review_state`, `reviewed_lines`, `round_arg`, `Host.review_comments`. Form only: `review_comments` accepts any marker comment. | partial (form only). in build: `review-record-provenance` (a review record comes only from the tool), `review-record-post-parses` (a posted record parses), `review-record-from-render` (a posted record's Head is the live head), `review-record-needs-reviewer` (a record carries a reviewer ref), `fail-record-ancestor-head` (a FAIL record names the live head). | Breaks 1 to 3: five PRs whose records were written by hand (#1494, #1506, #1597, #1667, #1668), PR #1512 (three bare records), PR #1472 (two bare records). | A record exists only when the merge tool rendered it for the head the review read, and the posted text is the tool's. | `review-record-provenance` (see Breaks for its MCP status). `review-record-post-parses` (done: a guard test refuses a record with trailing prose and allows the bare record). `review-record-from-render` (PR #1601). `review-record-needs-reviewer`, `fail-record-ancestor-head`: done checks in their steps. |
| 9. Record to fix check | `merge/merge.py:fix_check_arg`: tool only. No check on a push past a reviewed head. `--reviewed` shows `stale` only. | partial. in build: `reviewed-head-push-ask` (a push past a passing head asks first). | Break 4: PR #1683 (a lane PR with a fix check). Head 8293e4b passed round 3 with a fix check. Three later commits (b8db2e4, 630d519, dac6e3a) added Fix lines, then reverted. Five records; the last two claim PASS for heads no reviewer read. | A push past a reviewed head asks the owner first. A fix check counts only for its own head. | `reviewed-head-push-ask`. Its ask covers only a PR that already has a fix check, so the first push past a passing head is not asked (see Feedback). Done check: in the step. |
| 10. Lane to hand-off to batch runner | `merge/merge.py:lane_lint` (not required at hand-off; prose in `docs/decisions/lanes-run-no-full-ci-job.md`, where a lane runs no full CI job). A lane never merges: `merge/merge.py:confirm` stops without `read_merge_role`; `MERGE_ROLES`; `hooks/guard_merge.py:role_proof_hit`. | held at merge. Prose only at hand-off. | Break 5: PR #1502. Lane-lint skip unconfirmed from PR text. Record edited by hand. A test file ran in no CI workflow until PR #1585 (per audit). | A hand-off carries a lint run the tool read for the lane head. A lane cannot merge. | `review-record-provenance` refuses a PASS unless lane-lint passes on the head. Gap with no proposal: no local role check (see Input Needed). |
| 11. Hand-off to batch | Prose only: skill `ci-hygiene` (CI upkeep), step 8 (batch lanes). `merge/merge.py:MERGE_DEFAULTS` (method merge). `lane_tips`, `refuse_dropped_lane` (refuse a lane that a revert dropped). Review before joining: none. | prose only. | None named. | A lane joins a batch only with a PASS record for its head. | The open question below. No step. |
| 12. Batch to integration CI | `merge/merge.py:batch_refusal`. `hooks/guard_merge.py:merge_check` (batch: `gh pr merge`, `--auto`, MCP `merge_pull_request`). Only the integration PR goes ready: drafts are held at create (rule `draft-pr`, a draft PR at create, in `hooks/guard.py`). | held at merge. Partial at the ready mark. in build: `auto-merge-refused-for-claude` (a hook refuses auto-merge for Claude). | Ready mark: `gh pr ready` and MCP `update_pull_request` with draft=false are not refused. Debts `pr-ready-unguarded` (a PR can go ready unguarded) and `ready-checks-skipped-by-mcp` (a ready mark by MCP skips checks) already name it. | No merge of any kind while a batch's CI runs. A PR goes ready only through the draft step. | `auto-merge-refused-for-claude` covers auto-merge only. Named gaps (Merge button, raw `gh api` PUT merge, MCP `enable_pr_auto_merge`, a race before runs exist) have no step. |
| 13. CI to merge | `merge/merge.py:confirm` (never merges red). `hooks/guard_merge.py:merge_check`. Branch protection (`docs/decisions/main-branch-protection.md`: the all-jobs-passed check). Force push: `hooks/guard_push_delete.py:push_verdict`. | held on red. Partial on auto-merge. in build: `auto-merge-refused-for-claude`. | Break 4: the merge tool reads a record for a head that no reviewer read (PR #1683). Break 7: seven notes entries (2026-11-02 to 2026-11-04) record the classifier refusing lanes' own `--force-with-lease`. The audit ties the cause to row 5. | Merge reads the record and the CI run for the same head. Auto-merge stays with the owner. | `auto-merge-refused-for-claude`. Head match: the open question below. |
| 14. Merge to step done | `skills/roadmap/build.py:laneless`: flags a doing or active step with no lane or PR, exits 1. `lint/report_guard.py`: holds triage's Stop on stalled lines. `hooks/guard_merge.py:record_writer_hit` (rule `roadmap-one-writer`: one writer of the roadmap). | detective. | None named. Gap: a todo or ready step whose PR has merged is not flagged. | A merged PR closes its step in the store. | `pr-state-is-on-the-pr` (one next act per open PR): one ledger gives each open PR one next act and an owner. It partly covers rows 10, 11 and 14, by visibility. The merged-step gap: one note (see Notes). |
| 15. Step done to archive | `hooks/guard_branch_worktree.py:branch_delete_subject`, `BRANCH_DELETE_DENY_REASON` (refuses a branch delete; remedy: archive push). Merged lanes: `merge/merge.py:cut_lanes`. | held on a local delete. Partial. | None named. Gaps: `git push origin :branch` off the default branch passes. No proof that the archive push happened. | No branch is deleted before its archive push succeeds. | One note for the remote delete (see Notes). The missing proof is on no list (see Input Needed). |

## The breaks

Numbers follow the audit's break file. Each break names its hand-over.

- Break 1 (hand-over 8): five hand-written records, PRs #1494, #1506, #1597, #1667 and #1668. Lane-composed. Prose after the CI line. 9-character heads. No reviewer ref. Edited after posting. Step `review-record-provenance` names them.
- Break 2 (hand-over 8): PR #1512, three bare records with full heads. `merge --review-record` minted them from any flags. Hand-written: UNKNOWN. It rests on the provenance step text.
- Break 3 (hand-overs 8 and 9): PR #1472, two bare records. The second adds a fix check on a new head. Cause beyond the step text: UNKNOWN.
- Break 4 (hand-overs 9 and 13): PR #1683. Covered in row 9.
- Break 5 (hand-over 10): PR #1502. Lane-lint skip unconfirmed from PR text. Record edited by hand. A test file ran in no CI workflow until PR #1585. Cause: UNKNOWN.
- Break 6 (hand-over 1): notes gaps. Counts are in row 1.
- Break 7 (hand-over 13, cause in row 5): force-push refusals. None found 2026-11-05 to 2026-11-08.
- Break 8 (hand-over 2): five gaps, each filed as two steps. Audit refs are commits.
  - `red-run-at-commit` (a Red-run check at commit) and `red-run-pre-push`, folded in audit ref 5a8a25719.
  - `explore-no-create-session` and `reviewer-no-session-tools` (agent session tools, by name), audit ref b619241c4.
  - `guard-pipe-on-merge-lint`, `verdict-pipe-masks-exit` and `bg-tail-loses-verdict` (pipes and exit codes, by name), audit ref d40f35fdb.
  - `stale-prose-standing` (by name), folded into `prose-governance-workflow`, audit ref b0d65e04d.
  - `resumed-agent-stale-tree` (by name), with two steps folded in, audit ref f6046813b.
- UNKNOWN, kept open:
  - The cause of the PR #1502 lane-lint skip (break 5).
  - Why PRs #1512 and #1472 count as hand-written (breaks 2 and 3). It rests on step text.
  - Whether the CI step "Red-run trailer" (`if: pull_request`, in `.github/workflows/checks.yml`) runs under lane-lint.
- Covered, not built: whether `review-record-provenance` covers the MCP comment tool. The provenance lane reported at 19:13 CST. PR #1601 (`review-record-from-render`) guards `mcp__github__add_issue_comment` through `merge/merge.py:parse_review`. The provenance step adds a tool-only Stamp line that `parse_review` requires. Not built yet.

## In build

Status and order come from the step files on `origin/roadmap` (`roadmap/data/steps`). Work order is stated in words.

- `pr-state-is-on-the-pr` (todo; one next act per open PR): one ledger gives each open PR one next act and an owner. Covers rows 10, 11 and 14, partly.
- `review-record-from-render` (doing): the guard refuses a posted record whose Head is not the PR's live head. PR #1601. Not built yet. Work order: first. PR #1671 extends it, and `review-record-provenance` stacks on PR #1671.
- `review-record-post-parses` (doing): a posted record always parses. Built as PR #1671, which extends PR #1601's guard.
- `review-record-provenance` (doing): the guard refuses a review record posted outside the tool. It also refuses a PASS unless lane-lint passes on the head (PR #1502). Stacked on PR #1671.
- `review-record-needs-reviewer` (todo): a record carries a reviewer ref that the merge tool checks.
- `fail-record-ancestor-head` (doing): a FAIL record from a round run before its PR exists names the live head. Done check: a red test where the FAIL record names an ancestor, then the record names the live head or is refused.
- `reviewed-head-push-ask` (doing): the guard asks before a push past a passing head that already has a fix check.
- `red-run-pre-push` (doing): before a push, the guard runs `lint/check_red_run.py` on the commits the push sends. Absorbs `red-run-at-commit`. Depends on `commit-refuses-conflict-markers` (a commit with conflict markers is refused).
- `notes-name-their-fix` (doing): each new notes or debt line names its fix. The report guard refuses a recorded gap with no started fix. Coordinator picks add a ratchet and an `Until:` date on each `Fix: none` line.
- `auto-merge-refused-for-claude` (todo): a hook refuses auto-merge for Claude. The merge button stays the owner's. Owner pick a, waiting-page item 369, 19:03 CST.
- `lane-start-overlap-check` (todo): refuses a create_session whose `cs-step` tag an open lane already holds. Home: rule `lane-one-topic` (one topic per lane) in `hooks/guard.py`, per the step's note.
- Named by audit, not read: `doing-needs-live-lane` and `one-lane-one-step` (row 3); `brief-claim-has-probe` and `guard-brief-reproduces-incident` (row 4).
- Adjacent, not a hand-over: `lint-before-record-push` (doing). It runs STE lint at push, for Markdown only. Waiting-page item 377, pick a.

## Proposals

### New step: `step-names-its-gap` (hand-over 2)

- Mistake: one gap filed as two steps (break 8).
- Gap key: a new step file carries the note slug or gap key.
- Home: `check_staged` in `roadmap/build.py` on the record branch. One home.
- Done check: a red test where a staged step whose gap key matches an open step's is refused, then green.

### Extension: `lane-start-overlap-check` (hand-over 3)

- Also refuse a lane create_session with no `cs-step` tag that names an existing step.
- Same home: rule `lane-one-topic` in `hooks/guard.py`.
- Done check (new in this record): a red test where a create_session with no `cs-step` tag naming an existing step is refused, then green.

### Open question, not a step

Merge refusal on a lane tip with no PASS record. Written up under The open question. Waits on the owner.

### Notes (no step; no incident yet, rule `building-guard-needs-incident`: a guard needs a real incident first)

Three lines go in `docs/debts/notes.md`:

- `spawn-judge-no-report-cap` (hand-over 4).
- `merged-step-left-todo` (hand-over 14).
- `remote-delete-only-copy` (hand-over 15).

Not added: a lane PR marked ready (hand-over 12). Debts `pr-ready-unguarded` and `ready-checks-skipped-by-mcp` already hold it. A second line breaks rule `building-one-home-per-capability` (one home per capability).

### Feedback to an in-flight lane (the orchestrator sends it)

- Lane `reviewed-head-push-ask`: the guard asks only when the PR already has a fix check. The first push past a passing head is not asked (PR #1683). Ask on that push too.

## The open question: merge refuses a lane tip with no PASS record

Stale-decision protocol (rule `outcomes-stale-decision-protocol`: name the record and sentence, measure or say unmeasured, name the outcome and what protects it, propose a fix, wait for the grant). Not a step. Waits on the owner.

- Record: `docs/decisions/pr-review-record.md`, Lane picks, Q1 (whether preview or confirm refuses a PR with no valid record). The sentence: "Pick a: no refusal now." The coordinator answered at 23:14. The record gives no date.
- Departs from: that Q1 pick a. Ruling 113 a (owner, 2026-11-01 04:26 CST, waiting-page item 113 a) "names discovery only" (rule `outcomes-grant-covers-named-act`: a grant covers the act it names).
- Hand-overs: 7, 9, 11 and 13.
- Incidents since: PR #1683 (PASS claimed for heads no reviewer read). Five hand-written records (PRs #1494, #1506, #1597, #1667, #1668).
- Outcome Q1 protected: unmeasured. The record names no outcome.
- Measured: no. The audit does not count lane tips merged with no PASS record.
- What protects it now: nothing refuses. `merge --reviewed` lists state only. Once landed: `review-record-provenance`, `review-record-from-render` (PR #1601), `review-record-needs-reviewer`.
- Proposed fix: `merge confirm` refuses a lane tip whose newest record is not a PASS for that head. Done check: a red test where a lane head with a stale record is refused, then green.
- Needs the owner's grant to change Q1.

## Cost

No process, file or timer. This record's only other file change is three lines in `docs/debts/notes.md`. Each proposed step states its own cost when it lands.

Kind: process
Home: roadmap/build.py (`check_staged`), for `step-names-its-gap`
Home: hooks/guard.py (rule `lane-one-topic`), for `lane-start-overlap-check`

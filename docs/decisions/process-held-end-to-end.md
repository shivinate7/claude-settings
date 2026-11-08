# Every link in the work process gets a mechanical hold

## The ask

Owner, page, 2026-11-07 about 19:05 CST: "this whole process should have been mechanically held end to end."

- A link is one step from one stage of the work to the next. There are 15, from a found gap to an archived step.
- The table names each link's check, its status, the break the audit saw, the gold state, and the proposal with its done check.
- Rule `outcomes-mechanize-rules` (turn each rule into a hook or check, and record its cost) drives the proposals.
- Source: a five-part audit by Explore agents. It is unverified. Every file:symbol cell was grepped against the code, and the rows were re-read after two review rounds. Step statuses are from the step files on `origin/roadmap` (`roadmap/data/steps`) as of this change. Gaps with no proposal are in their own section.

Status values: held (a check refuses or asks), partial (a check with a named gap), detective (flags after the fact), prose only (a rule in text), in build (a step builds the check), landed (a step is done on main).

## The links

| Link | Held by today (file:symbol) | Status | Break seen | Gold (what held looks like) | Proposal + done check |
|---|---|---|---|---|---|
| 1. Found gap to note or step | `docs/debts/README.md` (prose, line 24). `lint/report_guard.py:mistake_problem` (refuses a Deviations admission that names no step, debt or guard, with its ref). `lint/report_guard.py:refusal_reason` (asks for a notes line, and never reads `notes.md`). Rule `roles-findings-are-debts-or-notes` (each finding is a debt or a note) is unmechanized. | partial (report-time checks only). in build: `notes-name-their-fix` (each new notes or debt line names its fix). | Break 6: 1,508 notes entries (audit count), 28 with `Fix:`, 1,480 without. | Each new gap line names a step slug, or a listed reason for no fix. A recorded gap with no started fix is refused. | `notes-name-their-fix`. Step done check: red tests for a notes line with no fix and for a recorded gap with no started fix, then green. |
| 2. Note to step | `origin/roadmap:roadmap/build.py:check_staged` (line 176: refuses a note past `NOTE_WORDS`, 250 words), `conflict_markers`, `upkeep` (warns only). | partial. `check_staged` holds only in a checkout where `roadmap/hooks/install.sh` ran (origin/roadmap CLAUDE.md line 15). It checks no gap key, and there is no Fix-line parser. | Break 8: two gaps, each filed as more than one step. | A new step that repeats an open step's gap key is refused at the commit that stages it. | New step `step-names-its-gap` (a new step names its gap key; see Proposals). Done check: a red test where a staged step whose gap key matches an open step's is refused, then green. |
| 3. Step to lane start | `skills/roadmap/build.py:todo_pairs` (`PAIR_LINE`) and `stalled` (`STALLED_LINE`): after the fact, on demand. CI runs `test_build.py` only. `hooks/guard.py:lane_effort_hit` and `lane_repo_tag_hit`: refuse a lane `create_session` with no effort prompt or no repo tag. `hooks/guard_merge.py:brief_hit`: reads `cs-step` at send_message, with `LANE_BRIEF_MARKER` (rule `lane-one-topic`, one topic per lane). `hooks/guard_merge.py:archive_hit`: reads `cs-step` at archive (`ARCHIVE_STEP_PREFIX`). | partial. The create_session checks refuse on tags and effort, not on step. The step check acts at send_message, not at lane start. in build: `lane-start-overlap-check` (todo; refuses a lane whose `cs-step` tag an open lane holds). Landed: `doing-needs-live-lane`, `one-lane-one-step` (see In build). | Incident for the overlap step: q_max lane qmax-main-map-ts (13:59 CST) duplicated lane qmax-map-format-skew (13:45 CST) on the MAP1-MAP10 failures. Triage caught it by hand. | A lane starts only on one open step, and an overlap is refused. | `lane-start-overlap-check`. Step done check: a red test where a create_session with a `cs-step` tag an open lane already holds is refused, then green. The no-`cs-step`-tag gap has no incident, so it is one note (see Notes). |
| 4. Lane start to brief | `hooks/call_judge.py:SPAWN_PROMPT`: a model judge that fails open, with no report cap, on Agent spawns only. `hooks/agent_brief.py` (advisory). `hooks/blind_brief.py` (designer briefs only). `hooks/guard.py:marker_scan`, `brief_markers` (model markers only). Rule `roles-brief-contents` (a brief carries its parts) is unmechanized. | partial (model judge). in build: `brief-claim-has-probe` (todo; a brief's claim about main carries its probe), `guard-brief-reproduces-incident` (doing; the test-author records the reproduction before refusal cases). | Incident #1581 (coordinator, 16:24 CST Nov 7): a brief stated main's behaviour with no probe behind the claim. Gap: the judge checks no report cap, and never sees a lane brief sent by `send_message`. | A brief missing its task, files, rulings, failure classes, check or report cap is refused before the agent starts. | `brief-claim-has-probe` (done check: a brief with a main-behaviour claim and no probe is red, and one with the probe passes). `guard-brief-reproduces-incident` (homes: `agents/test-author.md`, the guard part of the brief rules, and a lane-lint check that refuses a review record with `Guard or check: yes` and no reproduction line). The cap and `send_message` gaps: one note (see Notes). |
| 5. Brief to red run | `lint/check_red_run.py:main`, run by the CI step "Red-run trailer" in `.github/workflows/checks.yml` (PR only), and `merge/merge.py:lane_lint`. | partial: checked after the push. in build: `red-run-pre-push` (the guard checks the `Red-run:` line before a push). | Test commit 1f35b617 was pushed with no `Red-run:` line. Commit af063548b was pushed with a malformed line. Both were found after the push (audit B, not in the d-breaks file). | Each test commit's `Red-run:` line is checked before the push sends it. | `red-run-pre-push`. Step done check: a red test on a push of a test commit with no Red-run line, then green. Gaps: a claim, not proof; checked after the push. |
| 6. Red run to builder | `hooks/guard.py:own_changes`: refuses a builder's commit, push, Edit or Write on a test path (rules `builder-diff`, `builder-test-edit`). It logs, and never refuses, a hand-resolved cherry-pick, a revert, and a rebase squash, fixup or continue. | partial. | None named. Gaps are in Gaps with no proposal. | A builder cannot change a test by any git route. | None on the final list (see Gaps with no proposal). |
| 7. Builder to review rounds | `hooks/guard.py:step_up_reason` (round 2 reviewer on Sonnet, round 3 builder on Opus), `opus_spawn_hit`. Not held: that a reviewer is spawned at all. The three-round cap (rule `roles-review-cap-three`: three review rounds at most; unmechanized, though `merge/merge.py:parse_review` rejects a round above 3). `merge/merge.py:confirm` reads each lane tip's record through `refuse_owed_round`. | partial. in build (PR #1871, not on main): `merge-unreviewed-head`. | None logged. Gap, closed by PR #1871 (not on main): a lane tip with no record could merge. | A merge refuses a lane tip with no done record for that head. | `merge-unreviewed-head`, in build (PR #1871, not on main). See The open question. |
| 8. Review rounds to review record | `merge/merge.py:review_body`, `parse_review`, `review_state`, `reviewed_lines`, `round_arg`, `Host.review_comments`. `merge --review-record --head SHA` refuses a closed PR or a head mismatch. Form only: `review_comments` accepts any marker comment. | partial (form only). in build: `review-record-provenance` (doing; a review record comes only from the tool), `review-record-post-parses` (doing; a posted record parses), `review-record-from-render` (doing; a posted record's Head is the live head), `review-record-needs-reviewer` (todo; a record carries a reviewer ref), `fail-record-ancestor-head` (doing; a FAIL record names the live head). | Breaks 1 to 3: five PRs whose records were written by hand (#1494, #1506, #1597, #1667, #1668), PR #1512 (three bare records), PR #1472 (two bare records). Also incident #1565: a FAIL record named an ancestor of the live head. | A record exists only when the merge tool rendered it for the head the review read, and the posted text is the tool's. | `review-record-provenance` (see Breaks for its MCP status). `review-record-post-parses` (done check: a guard test refuses a record with trailing prose and allows the bare record). `review-record-from-render` (PR #1601). `review-record-needs-reviewer`, `fail-record-ancestor-head`: done checks in their steps. |
| 9. Record to fix check | `merge/merge.py:fix_check_arg`: tool only. No check on a push past a reviewed head. `--reviewed` (`merge/merge.py:reviewed_lines`) prints done, open, held, stale and bad for each open pull request that has a record. | partial. in build: `reviewed-head-push-ask` (doing; a push past a passing head asks first). It covers only the second fix, not the first. in build (PR #1871, not on main): `merge-unreviewed-head`. | Break 4: PR #1683 (a lane PR with a fix check). Head 8293e4b passed round 3 with a fix check. Later commits: 630d519 adds two Fix lines; dac6e3a moves two Fix lines into their Retire parts; b8db2e4 adds one notes entry, with no Fix text. Five records; the last two claim PASS for heads no reviewer read. | A push past a reviewed head asks the owner first. A fix check counts only for its own head. | `reviewed-head-push-ask`. Its ask covers only a PR that already has a fix check, so the first push past a passing head is not asked (see Feedback). Done check: in the step. |
| 10. Link to the batch runner | `merge/merge.py:main`: the role gate runs only when `CLAUDE_CODE_REMOTE` is `true`, so a local session passes (line 3349). A lane never merges there: `read_merge_role`, `MERGE_ROLES`, `hooks/guard_merge.py:role_proof_hit`. `merge/merge.py:lane_lint` (not required before that link; prose in `docs/decisions/lanes-run-no-full-ci-job.md`, where a lane runs no full CI job). | partial. The role gate covers remote sessions only. Lane lint before that link is prose only. | Break 5: PR #1502. Lane-lint skip unconfirmed from PR text. Record edited by hand. A test file ran in no CI workflow until PR #1585 (step `test-file-in-ci`, which puts a test file in CI). | The link to the batch runner carries a lint run the tool read for the lane head. A lane cannot merge, local or remote. | `review-record-provenance` refuses a PASS unless lane-lint passes on the head. Gaps with no proposal: see Gaps with no proposal. |
| 11. Link to batch | Prose only: skill `ci-hygiene` (CI upkeep), step 8 (batch lanes). `merge/merge.py:refuse_dropped_lane` refuses a lane that a revert dropped. `MERGE_DEFAULTS` (method merge). Review before joining: `merge/merge.py:confirm` runs `refuse_owed_round` on the batch's lane tips and refuses a tip with no done record (PR #1871, not on main). The join itself is ungated. | partial: `refuse_dropped_lane` refuses. The review check is held at merge, not at the join. in build (PR #1871, not on main): `merge-unreviewed-head`. | None named. | A lane joins a batch only with a done record for its head. | `merge-unreviewed-head`, in build (PR #1871, not on main). See The open question. |
| 12. Batch to integration CI | `merge/merge.py:batch_refusal`. `hooks/guard_merge.py:merge_check` (batch: `gh pr merge`, `--auto`, MCP `merge_pull_request`). Only the integration PR goes ready: drafts are held at create (rule `draft-pr`, in `hooks/guard.py`). Ready checks run only on the draft step (`merge/merge.py:draft_step`). The ready mark is governed by classifier prose in `settings.json`. | held at merge. Partial at the ready mark. in build: `auto-merge-refused` (doing; a hook refuses auto-merge for Claude). | Ready mark: `gh pr ready` and MCP `update_pull_request` with draft=false are not refused. Debts `pr-ready-unguarded` (a PR can go ready unguarded) and `ready-checks-skipped-by-mcp` (a ready mark by MCP skips checks) already name it. | No merge of any kind while a batch's CI runs. A PR goes ready only through the draft step. | `auto-merge-refused` covers auto-merge only. The other named merge gaps: see Gaps with no proposal. |
| 13. CI to merge | `merge/merge.py:confirm` (never merges red). `hooks/guard_merge.py:merge_check`. Branch protection (`docs/decisions/main-branch-protection.md`: the all-jobs-passed check). Force push: `hooks/guard_push_delete.py:push_verdict`. | held on red. Partial on auto-merge: `gh --auto` is judged, a green run only asks, and MCP `enable_pr_auto_merge` has no hook. in build: `auto-merge-refused`. in build (PR #1871, not on main): `merge-unreviewed-head`. | Break 4 is PR #1683 (see row 9). Gap, closed by PR #1871 (not on main): `merge/merge.py:confirm` reads the record for each lane tip, through `refuse_owed_round`. Break 7: nine notes entries (lines 1146, 1167, 1182, 1257, 1281, 1294, 1342, 1343, 1380; 2026-11-02 to 2026-11-04) record the classifier refusing lanes' own `--force-with-lease`. The audit ties the cause to row 5. | Merge reads the record and the CI run for the same head. Auto-merge stays with the owner. | `auto-merge-refused`. Head match: the open question below. |
| 14. Merge to step done | `skills/roadmap/build.py:laneless`: flags a doing or active step with no lane or PR, on demand, exit 1. `lint/report_guard.py:stalled_entries`: reads the newest build output in the transcript and holds triage's Stop. `hooks/guard_merge.py:record_writer_hit` (rule `roadmap-one-writer`), called from `hooks/guard.py`: refuses a push to the record branch unless the own record proves the triage tier. | partial. `laneless`, `ready_steps`, `landed_marks` and `upkeep` in `skills/roadmap/build.py` each flag some open steps. Some flagged steps have landed work. A step whose PR merged with no `Step:` trailer can stay open unflagged, outside the now phase or when `lane_live` counts a stale session. The full coverage map is unmeasured. | None named. Gap: `laneless`, `ready_steps`, `landed_marks` and `upkeep` in `skills/roadmap/build.py` each flag some open steps. Some flagged steps have landed work. A step whose PR merged with no `Step:` trailer can stay open unflagged, outside the now phase or when `lane_live` counts a stale session. The full coverage map is unmeasured. | A merged PR closes its step in the store. | `pr-state-is-on-the-pr` (todo; one next act per open PR): one ledger gives each open PR one next act and an owner. It partly covers rows 10, 11 and 14, by visibility. The merged-step gap: one note (see Notes). |
| 15. Step done to archive | `hooks/guard_branch_worktree.py:branch_delete_subject` with `hooks/git_reads.py:branch_is_empty`, which refuses only an only-copy branch: not an ancestor of the default branch, its patches not on it, and no remote-tracking ref contains its tip (`branch_on_remote`). `BRANCH_DELETE_DENY_REASON` names the archive push as the remedy. Remote delete: `hooks/guard_push_delete.py:push_verdict`. Remote delete: prose, the "Archived Branch Delete" rule in `settings.json` (line 44). It allows `git push origin :<branch>` when this session pushed an archive ref for the branch with no later commit. Rule (2) names a branch whose PR "this session visibly merged"; its default-branch clause names only `git branch -d`. | held for an only-copy branch. Partial: any remote-tracking ref that contains the tip passes, not only an `archive/` name, and the test reads local tracking refs without a fetch. | None named. Gap: `git push origin :branch` off the default branch passes, per the audit. | No branch is deleted before its archive push succeeds. | One note for the remote delete (see Notes). The tracking-ref gap: see Gaps with no proposal. |

## The breaks

Numbers follow the audit's break file. Each break names its link.

- Break 1 (link 8): five hand-written records, PRs #1494, #1506, #1597, #1667 and #1668. Lane-composed. Prose after the CI line. 9-character heads. No reviewer ref. Edited after posting. Step `review-record-provenance` names them.
- Break 2 (link 8): PR #1512, three bare records with full heads. `merge --review-record` minted them from any flags. Hand-written: UNKNOWN. It rests on the provenance step text.
- Break 3 (links 8 and 9): PR #1472, two bare records. The second adds a fix check on a new head. Cause beyond the step text: UNKNOWN.
- Break 4 (links 9 and 13): PR #1683. Covered in row 9.
- Break 5 (link 10): PR #1502. Lane-lint skip unconfirmed from PR text. Record edited by hand. A test file ran in no CI workflow until PR #1585 (step `test-file-in-ci`). Cause: UNKNOWN.
- Break 6 (link 1): notes gaps. Counts are in row 1.
- Break 7 (link 13, cause in row 5): force-push refusals. A peer session also sent a hand force-push recipe for merge-lock/main (notes line 1374). None found 2026-11-05 to 2026-11-08.
- Break 8 (link 2): two gaps, each filed as more than one step. Audit refs are commits.
  - `explore-no-create-session` and `reviewer-no-session-tools` (agent session tools, by name), audit ref b619241c4.
  - `guard-pipe-on-merge-lint`, `verdict-pipe-masks-exit` and `bg-tail-loses-verdict` (pipes and exit codes, by name).
- Traced from code, not executed: the Red-run trailer runs under lane lint. `lane_lint` calls `ci-job checks --lint --base origin/<base>` (`merge/merge.py:lane_lint`). `lane_head_and_base` defaults the base to `main`. ci-job sets the pull-request flag from the base (`bin/ci-job`, `bool(base)` in its plan calls), so the step's `if:` reads true. Its run line is a lint command (`LINT_CMD`).
- UNKNOWN, kept open:
  - The cause of the PR #1502 lane-lint skip (break 5).
  - Why PRs #1512 and #1472 count as hand-written (breaks 2 and 3). It rests on step text.
- Covered, not built: whether `review-record-provenance` covers the MCP comment tool. The provenance lane reported at 19:13 CST that PR #1601 (`review-record-from-render`) guards `mcp__github__add_issue_comment` through `merge/merge.py:parse_review`. The lane's cite is `hooks/guard_merge.py` `review_record_hit`. That function is in commit ae991eba0, on PR #1601's branch review-record-from-render (head ae991eba0, per gh api at 20:39 CST); origin/main lacks it. The provenance step adds a marker only the tool writes (step `review-record-provenance`, not built).

## In build

Status and order come from the step files on `origin/roadmap` (`roadmap/data/steps`). Work order is stated in words.

- `pr-state-is-on-the-pr` (todo; one next act per open PR): one ledger gives each open PR one next act and an owner. Covers rows 10, 11 and 14, partly.
- `review-record-from-render` (doing): the guard refuses a posted record whose Head is not the PR's live head. PR #1601, in review at round 3 (per the post-parses note). Work order: first. PR #1671 extends it, and `review-record-provenance` stacks on PR #1671.
- `review-record-post-parses` (doing): a posted record always parses. Built as PR #1671, which extends PR #1601's guard.
- `review-record-provenance` (doing): the guard refuses a review record posted outside the tool. It also refuses a PASS unless lane-lint passes on the head (PR #1502). Stacked on PR #1671. It adds a marker only the tool writes; not built yet.
- `review-record-needs-reviewer` (todo): a record carries a reviewer ref that the merge tool checks.
- `fail-record-ancestor-head` (doing; incident #1565): a FAIL record from a round run before its PR exists names the live head. Done check: a red test where the FAIL record names an ancestor, then the record names the live head or is refused.
- `reviewed-head-push-ask` (doing): the guard asks before a push past a passing head that already has a fix check.
- `red-run-pre-push` (doing): before a push, the guard runs `lint/check_red_run.py` on the commits the push sends. Absorbs `red-run-at-commit`. Depends on `commit-refuses-conflict-markers` (todo: a commit-time guard that refuses staged conflict markers; incident: lane merge-waits-required-only, 2026-11-07 02:36 CST).
- `notes-name-their-fix` (doing): each new notes or debt line names its fix. The report guard refuses a recorded gap with no started fix. Coordinator picks add a ratchet and an `Until:` date on each `Fix: none` line.
- `auto-merge-refused` (doing; lane started 19:04 CST): a hook refuses auto-merge for Claude. The merge button stays the owner's. Owner pick a, waiting-page item 369, 19:03 CST.
- `brief-claim-has-probe` (todo; incident #1581): a brief that states main's behaviour carries the probe that showed it.
- `guard-brief-reproduces-incident` (doing): the test-author records the command and the observed harm before refusal cases. Homes: `agents/test-author.md`, the guard part of the brief rules, and a lane-lint check that refuses a review record with `Guard or check: yes` and no reproduction line.
- `lane-start-overlap-check` (todo; incident: the q_max lanes above): refuses a create_session whose `cs-step` tag an open lane already holds. Home: rule `lane-one-topic` in `hooks/guard_merge.py`. The step's note names `hooks/guard.py` instead. Confirm the file before the step lands.
- Landed:
  - `doing-needs-live-lane` (done; on main at 79e04f36e): a doing step with no live lane and no open PR shows as stalled.
  - `one-lane-one-step` (done; on main at 967a7ea0f): the topic rule `lane-one-topic`. The guard is `brief_hit` in `hooks/guard_merge.py`.
- Adjacent, not a link: `lint-before-record-push` (doing). It runs STE lint at push, for Markdown only. Waiting-page item 377, pick a.

## Proposals

### New step: `step-names-its-gap` (link 2)

- Mistake: one gap filed as more than one step (break 8).
- Gap key: a new step file carries the note slug or gap key.
- Home: `check_staged` in `roadmap/build.py` on the record branch (`origin/roadmap`, line 176). `roadmap/hooks/pre-commit` runs `roadmap/build.py --check-staged`, so that check refuses the commit. Rule `building-one-home-per-capability` (one home per capability) decides it: one home, the one that runs at commit.
- Done check: a commit on the record branch that stages a step whose gap key matches an open step's is refused, red then green.

### Open question, not a step

Merge refusal on a lane tip with no done record. Answered: owner pick a, page item 382, 21:26 CST 2026-11-07. In build (PR #1871, not on main): `merge-unreviewed-head`. See The open question.

### Notes (no step; no incident yet, rule `building-guard-needs-incident`: a guard needs a real incident first)

Five lines go in `docs/debts/notes.md`:

- `spawn-judge-no-report-cap` (link 4).
- `lane-without-cs-step` (link 3): a lane starts with no `cs-step` tag, and nothing refuses a step that is not doing. The overlap step covers the duplicate-step case.
- `merged-step-left-todo` (link 14).
- `remote-delete-only-copy` (link 15).
- `two-roadmap-build-files` (link 2): `skills/roadmap/build.py` and the record branch's `roadmap/build.py` both hold `conflict_markers` and `upkeep`.

Not added: a lane PR marked ready (link 12). Debts `pr-ready-unguarded` and `ready-checks-skipped-by-mcp` already hold it. A second line breaks rule `building-one-home-per-capability` (one home per capability).

### Feedback to an in-flight lane (the orchestrator sends it)

- Lane `reviewed-head-push-ask`: the guard asks only when the PR already has a fix check. The first push past a passing head is not asked (PR #1683). Ask on that push too.

## Gaps with no proposal

Audit claims with no step or note in this record. The owner's orchestrator decides each one: note, debt or step.

- Row 6, builder routes: a squash or `cherry-pick -n` route; an unread role diff is logged and allowed (rule `role-diff-unread`); the main session is not covered; an author's diff is only logged.
- Row 10, lane to merge: the role gate runs only where `CLAUDE_CODE_REMOTE` is `true`; `gh pr merge` on a green run only asks (rule `bare-merge` in `hooks/guard.py`); MCP `merge_pull_request` checks only the verdict.
- Row 12, merge routes: the Merge button; raw `gh api` PUT merge; a race before runs exist. MCP `enable_pr_auto_merge` is UNKNOWN: its step note is silent on MCP, so whether `auto-merge-refused` covers it is unknown.
- Row 15, archive: any remote-tracking ref that contains the tip passes, not only an `archive/` name, and the test reads local tracking refs without a fetch.
- Audit claims not placed in a row: none.

## The open question: merge refuses a lane tip with no done record

Stale-decision protocol (rule `outcomes-stale-decision-protocol`: name the record and sentence, measure or say unmeasured, name the outcome and what protects it, propose a fix, wait for the grant). Not a step. Answered: owner pick a, page item 382, 21:26 CST 2026-11-07, with `docs/decisions/pr-review-record.md` Q1 rewritten to match. In build (PR #1871, not on main): `merge-unreviewed-head`.

- Record: `docs/decisions/pr-review-record.md`, Q1 in Lane picks (whether preview or confirm refuses a PR with no valid record). Q1 now reads pick a, as the owner rewrote it at 21:26 CST 2026-11-07 (page item 382). The coordinator answered at 23:14. The record gives no date.
- Departs from: that Q1 pick a. Ruling 113 a reads "Each PR carries a review record. The batch runner finds reviewed, green PRs itself. No merge message." It names no refusal (rule `outcomes-grant-covers-named-act`: a grant covers the act it names). Ruling 113 a: owner, 2026-11-01 04:26 CST, waiting-page item 113 a.
- Links: 7, 9, 11 and 13.
- Incidents since: PR #1683 (PASS claimed for heads no reviewer read). Five hand-written records (PRs #1494, #1506, #1597, #1667, #1668).
- Outcome Q1 protected: unmeasured. The record names no outcome.
- Measured: no. The audit does not count lane tips merged with no done record.
- What protects it now: `refuse_owed_round` refuses it at confirm (in build, PR #1871, not on main). `merge --reviewed` lists the state and CI of each PR that has a record, and refuses no merge. Once landed: `review-record-provenance`, `review-record-from-render` (PR #1601), `review-record-needs-reviewer`.
- Fix (in build, PR #1871, not on main): `merge confirm` refuses a lane tip whose `review_state` is not `done` for that exact head (`merge/merge.py:review_state`). Q2 (`docs/decisions/pr-review-record.md`, Lane picks) counts round 3 as done, whatever its verdict, so the key is `done`, not PASS. Done check: a red test where a lane head whose `review_state` is not `done` is refused, then green.
- Grant given: owner pick a, page item 382, 21:26 CST 2026-11-07 (links 7, 9, 11 and 13; in build, `merge-unreviewed-head`, PR #1871, not on main).

## Cost

No process, file or timer. This record's only other file change is five lines in `docs/debts/notes.md`. Each proposed step states its own cost when it lands.

Kind: process
Home: hooks/guard_merge.py
Home: skills/roadmap/build.py

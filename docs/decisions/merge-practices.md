# Merging practices that held up in more than one repo

## The ruling

Owner, page item 150, pick a, 2026-11-06 12:58 CST ("Build the small proof"): decision `test-practices` stays the testing chapter. This record is its merging sibling. A planner reads both before it plans a test or merge change (`agents/plan.md`). For two weeks, lessons from reviewer findings and owner corrections are added here and in `test-practices` by hand. Then a count of cites and repeats decides on the full shivpedia plan (roadmap step `craft-book`).

M1. A child repo names the shared merge ruling and never copies its text.
- home, degen, ios-adblock — after three rewrites of the merge grant on 2026-11-01, each child `CLAUDE.md` still said the coordinator merges, in copied text (decision `child-cites-not-copies`).
Applies to: each child `CLAUDE.md` line about merging.

M2. Before a merge, judge the base branch's newest completed run per event group, not only the PR's own run.
- joyous #68 — a red scheduled run on old main blocked every joyous merge until a newer green run of the same jobs cleared it (decision `no-merge-onto-red-main`).
Applies to: every batch merge.

M3. Merge only on a green run that holds for the current base tip.
- claude-settings steps c97 and c150 (decision `merge-needs-current-base`).
Applies to: every batch merge.

M4. Read every page of a PR's file list, or read git.
- banchi #1042 — batch runner 9 read only the first page of 30 files, missed a deletion, and reported a script as left behind (note `pr-files-api-first-page`).
Applies to: a batch runner or reviewer that lists a PR's files through the GitHub API.

M5. Keep the output of every push that takes or releases a lock.
- q_max, 2026-11-04 — a released merge lock blocked every later merge. The lock code read each failed push as a rival run and dropped its output, so the cause is unmeasured (note `cloud-released-lock-stuck`, rule `git-never-discard-output`).
Applies to: the merge lock and any ref write the merge tool makes.

M6. A small fix to a review finding gets a fix check on its own diff, then merges on green when Guard or check is `no`. Decision `pr-review-record` holds the done rules for `yes`.
- degen page item 83 — five PRs were held about 2 hours for new rounds (decision `hold-unsafe-after-round-3`).
Applies to: a fix that answers one named finding.

M7. Merge an append-only file by union. Rebuild a generated table; never merge it by union.
- claude-settings `docs/debts/notes.md` merges by union; `docs/records.md` is rebuilt by the merge tool (decisions `notes-merge-union`, `records-index-at-merge`).
Applies to: each file that two lanes edit in one batch.

M2 and M3 are held by the merge tool. M7 is held by `.gitattributes` and the merge tool. M1, M4, M5 and M6 have no check.

Kind: process
Home: agents/plan.md

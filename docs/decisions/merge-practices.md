# Merging practices that held up in more than one repo

## The ruling

Owner, page item 150, pick a, 2026-11-06 12:58 CST ("Build the small proof"): decision `test-practices` stays the testing chapter. This record is its merging sibling. A planner reads both before it plans a test or merge change (`agents/plan.md`). For two weeks, lessons from reviewer findings and owner corrections are added here and in `test-practices` by hand. Then a count of cites and repeats decides on the full shivpedia plan (roadmap step `craft-book`).

M1. A child repo names the shared merge ruling and never copies its text.
- home, degen, ios-adblock — after three rewrites of the merge grant on 2026-11-01, each child `CLAUDE.md` still said the coordinator merges, in copied text (decision `child-cites-not-copies`).
Applies to: each child `CLAUDE.md` line about merging.

M2. Before a merge, judge the base branch's newest completed run per event group, not only the PR's own run.
- joyous #68 — a red scheduled run on old main blocked every joyous merge until a newer green run of the same jobs cleared it (decision `no-merge-onto-red-main`).
Applies to: every merge.

M3. Merge only on a head that merges cleanly with the base tip, and whose own run is green or still pending under a lane-lint PASS for that head, or whose heal commits sit on a green proven head (decision `merge-needs-current-base`). The head need not hold the tip. A finished red run, an UNKNOWN main and a PASS for another head refuse. A known red main refuses nothing (ruling Q5 v, decision `no-merge-onto-red-main`). A PASS for another head counts only when it carries over claim commits, or, for a PR that replaces a source PR, an identical tree. A stale records page is healed inside the confirm, on the default base, under any merge.requiredChecks: the tool merges the base in when the base gained a record, pushes one page commit, and merges that sha, with no second confirm. Under "none" it waits only for GitHub to show the pushed head (page item 926 a, 14:32 CST, 2026-11-16). Under a list or "protection" the proof is the green checks of the proven head under page-only commits and clean merges of the base, any number (decision `merge-needs-current-base`). A relayed yes covers page-only commits and clean merges of the base, any number. A PR GitHub reads BLOCKED under "none" refuses and names the branch protection and requiredChecks; under a list it refuses when the green head is blocked for another cause.
- claude-settings steps c97 and c150 (decision `merge-needs-current-base`, a clean merge with the base tip and a green or lint-passed run).
- Owner ruling `own-merge-on-lint-pass` (owner, 2026-11-15 18:21 CST, typed "B for sure"): main's run after the merge is the check. A red main becomes the top lane at once (its revert or fix), and a PR may merge onto it; no lint PASS lifts a pending head while main is red (decision `no-merge-onto-red-main`).
Applies to: every merge.

M4. Read every page of a PR's file list, or read git.
- banchi #1042 — batch runner 9 read only the first page of 30 files, missed a deletion, and reported a script as left behind (note `pr-files-api-first-page`).
Applies to: a batch runner or reviewer that lists a PR's files through the GitHub API.

M5. Keep the output of every push that takes or releases a lock.
- q_max, 2026-11-04 — a released merge lock blocked every later merge. The lock code read each failed push as a rival run and dropped its output, so the cause is unmeasured (note `cloud-released-lock-stuck`, rule `git-never-discard-output`).
Applies to: the merge lock and any ref write the merge tool makes.

M6. A small fix to a review finding gets a fix check on its own diff. A passing fix check merges on green after any round, for every change (record `pr-review-record`). After a merge from main, the fix check reads `git diff origin/main...<head>` for its size test (item 401 a, owner, 2026-11-08 06:08 CST). It reads the same diff for the guard question (claude-settings coordinator, 2026-11-07 23:15 CST, lane batch63-lint-a; not the owner's words).
- degen page item 83 — five PRs were held about 2 hours for new rounds (decision `hold-unsafe-after-round-3`).
Applies to: a fix that answers one named finding.

M7. Give each note its own file, so lanes that each add a note never edit the same file. Rebuild a generated table; never merge it by union.
- claude-settings: each note is one file in `docs/notes/`. The old notes file takes deletes only. `docs/records.md` is rebuilt by the merge tool (decisions `notes-merge-union`, `records-index-at-merge`).
Applies to: each file that two open lanes edit.

M2 and M3 are held by the merge tool. M7 is held by `lint/check_record_slugs.py` (the old notes file takes deletes only), `.gitattributes` (its union line for that file) and the merge tool. M1, M4, M5 and M6 have no check.

Kind: process
Home: agents/plan.md

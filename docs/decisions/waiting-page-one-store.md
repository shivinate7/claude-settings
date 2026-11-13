# The page's database is its one store, and git is a timely backup

## The ruling

Owner, 2026-11-12 12:40 CST, relayed by the coordinator, as written: "the artifact is never operated upon by two accounts at the same time ... before it runs on another account i tend to wind it all down ... so as long as the artifact/data gets exported in a timely enough matter (not real time) it's morerso okay from that aspect of acocunt switching ... now if there are other problems /concerns like even within the same account the setup with all the lanes + triage is causing some sorta internal lag ... then we should still be open to the switchr otue".

Basis: owner R28, 2026-11-11 11:50 CST (restart plan item 3.14, `docs/plans/restart-plan.md` 554-555): "remember ij [sic] just care about the outcomes not the plumbing to reach it". Owner, 2026-11-12 11:24 CST, through the retrospective: "it shouldn't be a skill thing though it should be pretty mechanized". Owner, 12:10 CST, relayed by the coordinator: "Custom connectors are not allowed", which rules out route D. The 12:40 ruling overrides the 12:10 route B pick: route C is chosen, and route B is the fallback on the triggers under "What triggers route B".

- The page's database is the one store. Sessions read and write it live through ArtifactData. The page keeps `db` and `comments`, and nothing changes on the page.
- The copy in git is a backup for an account move and for recovery. It is exported in a timely way, not in real time. No session reads it as the truth.
- Route B (the owner's own site) is the fallback. A measured problem in the same account triggers it. See "What triggers route B".
- Mechanized: the timely export is a check, never a skill step (owner, 11:24 CST). The Stop check enforces it, and Mechanism step 1 closes its cloud-writer miss. The copy steps in `skills/waiting-page/reference/copies-and-accounts.md` are the run the check asks for.

This record rewrites `waiting-data-in-repo` (the git-copy decision) in part: its line that git is each artifact's home no longer holds for the waiting page.

Routes judged (Plan agent, Opus, then a refuter, Opus, verdict `revise`; the owner's rulings then chose among them):

| Route | Verdict |
|---|---|
| A. Db off, page shows a baked git snapshot | Fails: loses Send, Undo, Withdraw, Ask, Park, Mark read; a baked snapshot is a copy with lag. |
| B. Owner's own site, a Worker holds a token, git is the store | The fallback. Keeps every feature. Survives an account switch. Needs a Cloudflare account, a token and an access gate. |
| C. The page database is the store, git is a derived backup | Chosen. Costs nothing to build. Its gap is the backup's age, which has no set bound. The export check holds a page write to a later copy commit, except a cloud writer until Mechanism step 1 lands. |
| D. Page on claude.ai, no `db`, git through a connector | Ruled out: custom connectors are not allowed (owner, 12:10 CST). |

## Why C is enough today (read from `skills/waiting-page/page.html`, checked on origin/main at commit 36807ad19a)

- The Questions tab reads the database live (`onSnapshot`, 3185-3197). A lane's write shows at once. The page does not drift from the store, because the page is the store's view.
- What drifts is the backup. The writer copies it by hand at each wake (`skills/waiting-page/reference/copies-and-accounts.md`). On 2026-11-11 it went 11 hours stale because the Stop check
  missed a cloud writer. The cause is a code read, and its red case is the first act of step `waiting-export-miss-cloud`: `hooks/feedback_guard.py` 1353-1355 matches the writer id against the bare session id only. The step note for this decision measured the copy 58 items behind the database at 12:40 CST (577 against 519).
- The Status tab is baked into the page and changes only on a republish (`page.html` 1018-1019, 3201-3206). That lag is the republish, not the database.
- It is unknown which of these the owner saw as stale data. The two accounts, which he winds down before a switch, are the only case where the database and git must agree.

## What triggers route B

Each is a measured event in the same account, never a guess. The one who meets it files a debt that points to this decision, and triage asks the owner for the switch.

1. The owner reports a card that shows data older than a lane's write. His report is the check; nothing else reads it.
2. A write loses a field another writer set: an item that was closed or marked read shows open again, because a `set` replaced the document (SKILL.md "The database"). The writer sees it at its wake. A refused close that the writer retries (SKILL.md 452-453) is normal and does not count.
3. A Send takes long enough to read as lag. Step `waiting-lag-read` prints each answer's delay from `at` to its receipt `read`. The threshold is unmeasured. The owner's report of a stale card counts too.

## If route B is triggered

Each act that cannot be undone or costs money needs one owner yes, asked by the coordinator at the step that does it. The acts are a Cloudflare account (free plan), a GitHub token mint, a deploy, the access gate, and deleting the old claude.ai page. A custom domain or a paid plan costs money and is not planned.

- A Worker (Cloudflare) serves the page and an API. It holds a GitHub token as a Worker secret, so no token sits in a page. It reads and writes `waiting/<collection>/<id>.json` on the record branch through the GitHub API.
- The Worker writes only what the page writes today: `answers/` and `asks/` records, the `dismissed` read mark on an item or an ask, and the delete of `receipts/<id>` on Undo (`page.html` 2382 for the delete, 2810 for the dismissed write).
- The page polls the Worker, which asks GitHub with a conditional read. The wake from a save has no claude.ai `comments`. A webhook to a session's `watch_url` is likely blocked, because its signing secret is sealed to the artifact service (decision `session-messages`, line 37). Unmeasured.
- An access gate is part of the route. Without it, anyone with the URL could write answers.
- The token is scoped to the repo, and a fine-grained token cannot be limited to one branch. Decision `main-branch-protection`, ruling r, rules a ruleset for main that is not yet built.
- The steps then are a measuring probe on a scratch branch, the Worker and page build, the wake route, the writer and tools on git, and the copy's retirement. They are filed then, as new steps.

## Picks

Taken by the coordinator at 11:43 CST on 2026-11-12, as an undoable pick (no owner question): build a guard that refuses a session write to the page database's `answers/`. Claude writing an answer by mistake is a likely error, and it forges a grant. Step `answers-session-write-guard` is that guard, started as its own lane. Every session write already passes the PreToolUse hook, ArtifactData writes included (`settings.json` 251).

## Known gaps

- The backup's age has no set bound. The owner said "timely enough (not real time)". The export check (Mechanism step 1) blocks a turn that wrote the page without a later copy, except a cloud writer until step 1 lands. That is stricter than he asked. Unmeasured: whether that check costs more than it protects.
- The git copy holds five collections and no `receipts` (`export_page.py`, `lint/layout.py:275`). A recovery from it loses the receipts. Whether that matters is unmeasured.
- Two accounts: the owner winds one down by hand before using the other, and the skill's "Before you switch Claude accounts" export covers it (read `skills/waiting-page/reference/copies-and-accounts.md`). No check makes him do it.
- The Status tab stays baked and lags until a republish.

## Mechanism (build steps, handed to the coordinator as step text)

1. `waiting-export-miss-cloud` (existing step, blockedBy none): the writer match in `hooks/feedback_guard.py` 1353-1355 also reads the cloud session id inside "Triage (session_...)". Red first: a transcript with a page write after the last copy commit, writer named by cloud id, must block. This is the timely export, mechanized.
2. `waiting-copy-backup-only` (blockedBy none): the skill, the export script and the checks name the copy as a backup for recovery and account moves. When a tool other than the recovery, merge and export modes of `export_page.py` or `stale_pages.py --lag` (step 3) reads the copy folder as a live source, the check fails. Red first.
3. `waiting-lag-read` (blockedBy none): `stale_pages.py --lag <folder>` reads the folder the writer already saves at each wake. It prints each answer's delay from `at` to its receipt `read`, and each answer with no receipt older than a set age. No new store, no timer, no process. The named reader is the writer at its wake.
4. `answers-session-write-guard` (blockedBy none): the guard of Picks. Already a lane.

The R28 steps `prose-tending-contract`, `prose-tending-move-stores`, `feedback-log-tends-itself` and `shared-job-finder` stay as they are. The copy is one store that `prose-tending-contract` tends: its "still true?" test compares the copy with its live source, the database.

## Why

Protects: the owner sees live data on the page. A lost page or an account switch loses what the copy has not yet caught, and the copy's age has no set bound. It also protects against building a second system the owner does not need.

## Cost

`waiting-export-miss-cloud`, `waiting-copy-backup-only` and `waiting-lag-read` add no process, timer or log. The export check already runs at a Stop. The lag read runs inside the writer's existing wake and prints on demand. Route B, if triggered, adds a hosted Worker on the free plan.

Refuter: refuter opus, 2026-11-12, revise. It refuted the plan that judged all four routes. The owner's rulings at 12:10 and 12:40 CST then chose among its routes; no new plan was made.

Kind: process
Home: skills/waiting-page/SKILL.md

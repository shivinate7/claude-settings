# Git is the page's home, and the database is its live view

## The ruling

Git is the page's home. The page database is the live view that one account writes through. It is exported to git in a timely way, not in real time. Nothing points to one claude.ai link as the real data set (owner, 2026-11-13 12:03 CST, relayed by the retrospective, as written: "nothing points to a specific link of the artifact as the real dataset, only git data in a sense").

Owner, 2026-11-12 12:40 CST, relayed by the coordinator, as written: "the artifact is never operated upon by two accounts at the same time ... before it runs on another account i tend to wind it all down ... so as long as the artifact/data gets exported in a timely enough matter (not real time) it's morerso okay from that aspect of acocunt switching ... now if there are other problems /concerns like even within the same account the setup with all the lanes + triage is causing some sorta internal lag ... then we should still be open to the switchr otue".

Anchor: decision `waiting-data-in-repo` (owner, 2026-11-02 14:58 CST): "Git is each artifact's home. The claude.ai link is one account's view of it." The 12:40 ruling fits it on timing and does not replace it. Ruling `page-git-is-home` (on the roadmap branch) records this fit.

Basis: owner R28, 2026-11-11 11:50 CST (restart plan item 3.14, `docs/plans/restart-plan.md` 554-555): "remember ij [sic] just care about the outcomes not the plumbing to reach it". Owner, 2026-11-12 11:24 CST, through the retrospective: "it shouldn't be a skill thing though it should be pretty mechanized". Owner, 12:10 CST, relayed by the coordinator: "Custom connectors are not allowed", which rules out route D. The 12:40 ruling overrides the 12:10 route B pick: route C is chosen, and route B is the fallback on the triggers under "What triggers route B".

- The page database is the live view. In one account, sessions read and write it live through ArtifactData. The page keeps `db` and `comments`, and nothing changes on the page.
- The copy in git is the home. It is exported in a timely way, not in real time, so it can be behind the live view by the export's age. For an account move, for recovery, and for a read from another account, the copy is the data.
- A session in the account that owns the page reads the database for what is newest. A session in any other account reads the git copy, read-only, and knows its age (step `waiting-copy-age-read`).
- Route B (the owner's own site) is the fallback. A measured problem triggers it. See "What triggers route B".
- Mechanized: the timely export is a check, never a skill step (owner, 11:24 CST). The Stop check enforces it, and Mechanism step 1 closes its cloud-writer miss. The copy steps in `skills/waiting-page/reference/copies-and-accounts.md` are the run the check asks for.

This record keeps `waiting-data-in-repo` (the git-copy decision) as it stands. It adds how the database and git work together for the page.

Routes judged (Plan agent, Opus, then a refuter, Opus, verdict `revise`; the owner's rulings then chose among them):

| Route | Verdict |
|---|---|
| A. Db off, page shows a baked git snapshot | Fails: loses Send, Undo, Withdraw, Ask, Park, Mark read; a baked snapshot is a copy with lag. |
| B. Owner's own site, a Worker holds a token, git is the live store too | The fallback. Keeps every feature. Survives an account switch. Needs a Cloudflare account, a token and an access gate. |
| C. Git is the home, the page database is the live view, git gets a timely export | Chosen. Costs nothing to build. Its gap is the copy's age, which has no set bound. The export check holds a page write to a later copy commit, except a cloud writer until Mechanism step 1 lands. |
| D. Page on claude.ai, no `db`, git through a connector | Ruled out: custom connectors are not allowed (owner, 12:10 CST). |

## Why C is enough today (read from `skills/waiting-page/page.html`, checked on origin/main at commit 7dd44c41c)

- The Questions tab reads the database live (`onSnapshot`, 3214-3226). A lane's write shows at once. The page does not drift from the database, because the page is the database's view.
- What drifts is the git copy. The writer copies it by hand at each wake (`skills/waiting-page/reference/copies-and-accounts.md`). On 2026-11-11 it went 11 hours stale because the Stop check
  missed a cloud writer. The cause is a code read, and its red case is the first act of step `waiting-export-miss-cloud`: `hooks/feedback_guard.py` 1353-1355 compares the page's writer value with the session id and the remote session id by equality, and the page stores "Triage (session_...)". The step note for this decision measured the copy 58 items behind the database at 12:40 CST (577 against 519).
- The Status tab is baked into the page and changes only on a republish (`page.html` 1019-1020, 3230-3235). That lag is the republish, not the database.
- It is unknown which of these the owner saw as stale data. The two accounts, which he winds down before a switch, are the only case where the database and git must agree.

## What triggers route B

Each is a measured event, never a guess. Triggers 1 to 3 are same-account lag. Trigger 4 is cross-account. The one who meets it files a debt that points to this decision, and triage asks the owner for the switch.

1. The owner reports a card that shows data older than a lane's write. His report is the check; nothing else reads it.
2. A write loses a field another writer set: an item that was closed or marked read shows open again, because a `set` replaced the document (SKILL.md "The database"). The writer sees it at its wake. A refused close that the writer retries (SKILL.md 452-453) is normal and does not count.
3. A Send takes long enough to read as lag. Step `waiting-lag-read` prints each answer's delay from `at` to its receipt `read`. The threshold is unmeasured. The owner's report of a stale card counts too.
4. A session in one account must read the page's data from another account, and the git copy is too old for it. The copy's age comes from step `waiting-copy-age-read`. The age that counts as too old is unmeasured. The owner's report that a cross-account read was stale counts too.

## If route B is triggered

Each act that cannot be undone or costs money needs one owner yes, asked by the coordinator at the step that does it. The acts are a Cloudflare account (free plan), a GitHub token mint, a deploy, the access gate, and deleting the old claude.ai page. A custom domain or a paid plan costs money and is not planned.

- A Worker (Cloudflare) serves the page and an API. It holds a GitHub token as a Worker secret, so no token sits in a page. It reads and writes `waiting/<collection>/<id>.json` on the record branch through the GitHub API.
- The Worker writes only what the page writes today: `answers/` and `asks/` records, the `dismissed` read mark on an item or an ask, and the delete of `receipts/<id>` on Undo (`page.html` 2411 for the delete, 2839 for the dismissed write).
- The page polls the Worker, which asks GitHub with a conditional read. The wake from a save has no claude.ai `comments`. A webhook to a session's `watch_url` is likely blocked, because its signing secret is sealed to the artifact service (decision `session-messages`, line 37). Unmeasured.
- An access gate is part of the route. Without it, anyone with the URL could write answers.
- The token is scoped to the repo, and a fine-grained token cannot be limited to one branch. Decision `main-branch-protection`, ruling r, rules a ruleset for main that is not yet built.
- The steps then are a measuring probe on a scratch branch, the Worker and page build, the wake route, the writer and tools on git, and the copy's retirement. They are filed then, as new steps.

## Picks

Taken by the coordinator at 11:43 CST on 2026-11-12, as an undoable pick (no owner question): build a guard that refuses a session write to the page database's `answers/`. Claude writing an answer by mistake is a likely error, and it forges a grant. Step `answers-session-write-guard` is that guard, started as its own lane. Every session write already passes the PreToolUse hook, ArtifactData writes included (`settings.json` 251).

## Known gaps

- The copy's age has no set bound. The owner said "timely enough (not real time)". The export check (Mechanism step 1) blocks a turn that wrote the page without a later copy (read hooks/feedback_guard.py:1332), except a cloud writer until step 1 lands. That is stricter than he asked. Unmeasured: whether that check costs more than it protects.
- The git copy holds five collections and no `receipts` (`export_page.py`, `lint/layout.py:275`). A recovery from it loses the receipts. Plan item 2 adds them.
- Two accounts: the owner winds one down by hand before using the other, and the skill's "Before you switch Claude accounts" export covers it (read `skills/waiting-page/reference/copies-and-accounts.md`). No check makes him do it.
- The Status tab stays baked and lags until a republish.

## Mechanism (build steps, handed to the coordinator as step text)

1. `waiting-export-miss-cloud` (existing step, blockedBy none): the writer match in `hooks/feedback_guard.py` 1353-1355 also reads the cloud session id inside "Triage (session_...)". Red first: a transcript with a page write after the last copy commit, writer named by cloud id, must block. This is the timely export, mechanized.
2. `waiting-copy-backup-only` (blockedBy none): the skill, the export script and the checks name the copy as the home for recovery, account moves and cross-account reads. They never name it the live view in the owning account. The allow list of tools that may read the copy folder holds the recovery, merge and export modes of `export_page.py`, `stale_pages.py --lag` and `--copy-age` (steps 3 and 5), and one more entry: a read-only read of another account's git copy. That read is the only route from this account to the Home and Degen pages, which it cannot reach through ArtifactData. A tool that reads the copy folder for any other reason fails the check. The cross-account entry is read-only: a tool that writes to another account's copy fails the check. Red first, for both the extra reader and the write.
3. `waiting-lag-read` (blockedBy none): `stale_pages.py --lag <folder>` reads the folder the writer already saves at each wake. It prints each answer's delay from `at` to its receipt `read`, and each answer with no receipt older than a set age. No new store, no timer, no process. The named reader is the writer at its wake.
4. `answers-session-write-guard` (blockedBy none): the guard of Picks. Already a lane.
5. `waiting-copy-age-read` (blockedBy `waiting-lag-read`, which gives the reader its home in `stale_pages.py`): `stale_pages.py --copy-age <folder>` prints the copy's age, the time since its last export commit, and the age of the newest item or answer the copy holds. It is a step because it needs code. Reader: the page writer at its wake, and any session that reads another account's copy, which sees the age beside the data. No new store, timer or process. Red first: a copy folder with a last commit older than the set age must print its age and the word late.

The R28 steps `prose-tending-contract`, `prose-tending-move-stores`, `feedback-log-tends-itself` and `shared-job-finder` stay as they are. The copy is a store that `prose-tending-contract` tends: its "still true?" test compares the copy with the database, its live view. The copy is the home, so a difference is the copy's lag, never the database's error.

## Plan: the steps that make "git is home" true end to end

Coordinator, 2026-11-13 12:14 CST, from the retrospective's blind review. This record names them. It builds none of the code. Triage files each as a step.

1. A page writer exports the same document to git and pushes in the same turn, before any relay. Step `waiting-export-miss-cloud` makes the Stop check catch a cloud writer.
2. The `receipts` collection joins the exported ones. `lint/layout.py:275` drops it today.
3. Readers move from the page database to git: the answer check in `page_grant.py` and the Relayed Grant entry. This needs the owner's grant first. Step `page-one-store-answers` holds it.
4. Every repo registers every artifact with its account label. Each account's sessions export their own, with `export_page.py --all --account`. The label "current" names a different account in each repo, so it is replaced. A label names the account itself, one fixed name per account, never an email. The copy-age reader reports per account.
5. The cite check covers handoffs and CLAUDE.md, or they resolve links through `lint/layout.py`. This changes the line in `waiting-data-in-repo` that the cite check does not read briefs and handoffs.
6. The copy-age reader (step `waiting-copy-age-read`) flags a copy older than its page's last write.

Done proof: a fresh clone on the other account rebuilds each page from git alone, receipts included.

## Why

Protects: the owner sees live data on the page, and the data survives a lost page or an account switch because git is its home. A lost page or an account switch loses what the copy has not yet caught, and the copy's age has no set bound. A session in another account reads the copy with its age beside it. It also protects against building a second system the owner does not need.

## Cost

`waiting-export-miss-cloud`, `waiting-copy-backup-only`, `waiting-lag-read` and `waiting-copy-age-read` add no process, timer or log. The export check already runs at a Stop. The lag and copy-age reads run inside the writer's existing wake, and each prints on demand. Route B, if triggered, adds a hosted Worker on the free plan.

Refuter: refuter opus, 2026-11-12, revise. It refuted the plan that judged all four routes. The owner's rulings at 12:10 and 12:40 CST then chose among its routes; no new plan was made.

Kind: process
Home: skills/waiting-page/SKILL.md

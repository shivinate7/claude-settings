# The waiting page has one store, and it is git

## The ruling

Owner, 2026-11-11 11:50 CST (ruling R28, restart plan item 3.14, `docs/plans/restart-plan.md` 554-555): "ya if anything the actual
page gets its database disableed [sic] if that's possible and then it's never an issue ... remember ij [sic] just care about
the outcomes not the plumbing to reach it". The plan reads it as: one store, no copy step, no lag; the design pass picks the route.
Owner, 11:55 CST: "The fallback is moving off artifacts to your own site ... this doesnt sound so bad tho tbh". Owner,
2026-11-12 11:24 CST, through the retrospective: "it shouldn't be a skill thing though it should be pretty mechanized".
Owner, 2026-11-12 12:10 CST, relayed by the coordinator at 12:11 CST: "Custom connectors are not allowed -- so we can do route B".
The design pass (the plan's direction, not an owner quote) makes git the first write.

- The waiting page's data has one store: the record branch of the repo. Git is the first write. No copy step, no lag.
  This replaces the copy half of decision `waiting-data-in-repo` (git is each artifact's home, the writer copies the page at each
  wake): the copy stays live as the safety net until step 7 of Mechanism lands, and then that record is rewritten in place.
- Route chosen: B, the owner's own site. A small Worker (Cloudflare) serves the page and an API. It holds a GitHub token as a
  Worker secret, so no token sits in a page. It reads and writes `waiting/<collection>/<id>.json` on the record branch through the GitHub API.
  The page no longer lives on claude.ai and declares no `db`.
- Route D (the page stays on claude.ai, git through a connector) is ruled out. Custom connectors are not allowed (owner, 12:10 CST). The
  coordinator's relay adds that the connector directory has no GitHub connector (checked 12:08 CST); this lane read no source for that.
- Mechanized: two checks, never a skill step (owner, 11:24 CST). See Mechanism.

Routes judged (Plan agent, Opus, then a refuter, Opus, verdict `revise`; the revisions are taken below):

| Route | Verdict |
|---|---|
| A. Db off, page shows a baked git snapshot | Fails: loses Send, Undo, Withdraw, Ask, Park, Mark read; a baked snapshot is a copy with lag. |
| B. Owner's own site, a Worker holds a token | Chosen on the owner's ruling. Keeps every feature in the page's own UI. Survives an account switch. Loses claude.ai `comments`, so the wake needs a new route. Needs a Cloudflare account, a token and an access gate. |
| C. Db stays the store, git a derived read | Fails: git is a later copy, so it keeps today's lag and the lost-page loss. |
| D. Page on claude.ai, no `db`, git through a connector | Ruled out by the owner, 12:10 CST. |

## What B changes (read from `skills/waiting-page/page.html`, checked on main at commit 2deb827ad)

- The page's six collections move from `window.claude.use("db")` to the Worker's API. `sendAll` returns when there is no db (2299), and Withdraw
  (1815), Undo (2371), asks (2552, 2609) and Mark read (2806) fail the same way, so every one of them is re-pointed. `comments` is fetched only
  after the db exists (3179), and the claude.ai `comments` wake does not exist off claude.ai, so the boot and the wake change.
- The Worker writes only what the page writes today: `answers/` and `asks/` records, the `dismissed` read mark on an item or an ask, and
  the delete of `receipts/<id>` on Undo (`page.html` 2378, 2806). It writes no other field of an item and no `meta/`. A session writes the receipt
  otherwise (SKILL.md "Read the answers"). The Worker checks each write against that list.
- A Send of several answers is meant to be one commit (GitHub trees API; step 1 measures it). Undo and Withdraw become a second commit. Git history keeps the undone
  answer; today Undo deletes it (SKILL.md "Read the answers").
- The Worker commits under its own committer name, so a guard can tell the page's writes from a session's.
- The git copy holds five collections and no `receipts` (`export_page.py`, `waiting-data-in-repo`). `receipts` and
  `meta.woke` join the record-branch layout (`WAITING_COLLECTIONS` in `lint/layout.py:275`).
- `stale_pages.py` unread mode reads four list files (lines 91-93, 744-748), not one file per doc, so it needs a new loader.
  `page_grant.py` already reads per-doc files (line 12).
- Designs and the Status tab read from files in git at each load. Today they are baked into the page and change only on a republish
  (`page.html` 1010, 1017, 3198-3202), so that lag ends. The republish, account-switch and merge-copy parts of the skill have nothing left to do.
- Today the Questions tab updates live through `onSnapshot` (3181-3193). Under B it polls the Worker, which asks GitHub with a
  conditional read. This is a lag against "no lag". The coordinator took it as a pick (see Picks), and the owner can overrule it.
- An answer guard is possible: every session write passes the PreToolUse hook, ArtifactData writes included (`settings.json` 251),
  and the Worker's own writes never do. None is built, so SKILL.md "Read the answers" says "this sentence is the only guard". Picked below.
- Who can write answers is a gate. A Worker open to anyone with the URL would let anyone write answers, which is wider than today's grant.
  An access gate (Cloudflare Access, or a login the Worker checks) is part of the route, not an extra.
- The token is scoped to this repo. A fine-grained token cannot be limited to one branch, so only a ruleset on main keeps it off main. Decision `main-branch-protection`, ruling r, rules a ruleset that blocks deletion and force-push of main and requires `all-jobs-passed`; that ruleset is ruled, not yet built. A pull request requirement is planned, not ruled. The probe measures the token's reach.

## Picks

Taken by the coordinator at 11:43 CST on 2026-11-12, as undoable picks (no owner question). Pick 1 is reworded for route B.

1. Live view: poll about every 30 s while the page is open, and refresh on load and focus. The 30 s is tunable and unmeasured, never a
   rule. The Worker answers a poll with a cheap change check (an etag or the branch head), and the page fetches only on change.
   Today's view is instant (`page.html` 3181-3193), so this is a lag against "no lag", kept as small as the API allows.
2. Build a guard that refuses a session write to `waiting/answers/**`. Claude writing an answer by mistake is a likely error, and it forges a grant.
3. Undo and Withdraw keep the undone answer in git history. Nothing reads it as an answer once a later commit removes it.

Each act that cannot be undone or costs money needs one owner yes, asked by the coordinator at the step that does it. These acts are: a Cloudflare account (free plan), a token mint, a deploy, the access gate, deleting the old claude.ai page (step 7), and any custom domain or paid plan. The plan uses the free
`workers.dev` address and a free plan. Pick 1 can be overruled by the owner. His word is also needed on the Relayed Grant entry (step 2).

## Known gaps

- Unmeasured, decided by the probe:
  - Whether a Worker can wake the writer on a save. The candidate is a POST from the Worker to a webhook URL that the writer made with its `watch_url` tool, which arrives in the writer's conversation. Decision `session-messages` (line 37) says a webhook to `watch_url` is likely blocked. Its signing secret is sealed to the artifact service, so a Worker may not be able to sign it. The fallback is the turn-start read of `answers/`.
  - The delay from a click to a commit on the record branch, and the cost of a poll in GitHub API calls.
  - Whether the free Cloudflare plan and its Access gate cover one owner on a phone.
  - Whether one commit can carry several files, and whether the token can be kept off main by the ruleset alone.
- API commits can make a session's push to the record branch non-fast-forward. The cure is fetch and rebase, never a force push.
- Until step `retire-page-copy` lands, the copy step and its Stop check stay live. The copy is the safety net.

## Mechanism (build steps, handed to the coordinator as step text)

1. `waiting-site-probe` (blockedBy none): on a scratch branch, never the record branch, measure a test Worker. Measure one commit of several files, a conditional read and the click-to-commit delay. Measure a wake by webhook to a session, the Access login on a phone, the free plan's limits and the token's reach. Owner acts: a Cloudflare account, a token, a test deploy and the access gate.
2. `page-one-store-answers` (blockedBy 1): the owner's word to re-point the `settings.json` "Relayed Grant" entry (line 54), which reads answers fetched with ArtifactData.
3. `waiting-item-check` (blockedBy 2): one validator over `waiting/**.json` for the item rules now keyed on ArtifactData (`guard.py`, `question_form.py`, `call_judge.py`, `local_time.py --page-note`). It runs as a PreToolUse on a commit or push touching `waiting/`. It also runs in record-branch CI, which does not exist today (`checks.yml` 3-7 runs on main and PRs). Red first on the old commit. The Worker checks only the shape of what it writes (answers, asks); the item rules stay here.
4. `waiting-site-build` (blockedBy 1, 3): the Worker, its API and the access gate, kept in this repo. `page.html` moves its collections from db to the API, with one commit per Send, Undo or Ask batch and a poll with a change check. Designs and Status read from git. Owner acts: the token mint, the deploy, the gate (one yes each).
5. `site-wakes-writer` (blockedBy 4): the Worker wakes the writer on a save, by the route step 1 measured; the turn-start read stays as the fallback.
6. `writer-writes-git` (blockedBy 2, 3, 4): the writer and tools read and write the record branch; new loader in `stale_pages.py`; the SKILL.md database section is rewritten in place.
7. `retire-page-copy` (blockedBy 5, 6): the copy ends here, and `waiting-data-in-repo` is rewritten in place. Delete the export mode of `export_page.py` and `export_check` in `hooks/feedback_guard.py` (1332); keep `--all` for other artifacts; close `waiting-export-miss-cloud` as superseded. A guard refuses an ArtifactData write that names a waiting-page URL, and a lint fails if `page.html` calls `use("db")`; each red first. Delete the old claude.ai page last, after the owner's yes (it cannot be undone).
8. `answers-session-write-guard` (blockedBy none): refuse a session write to `waiting/answers/**` on ArtifactData and every git write tool (Bash git, `create_or_update_file`, `push_files`, `delete_file`). Red first. (Pick 2.) Started as its own lane.
9. `waiting-skill-drops-artifact` (blockedBy 7): the waiting-page skill drops the parts that exist only for a claude.ai page: republish, account switch, merge of two copies, the artifact registry entry for the waiting page.

The R28 steps `prose-tending-contract`, `prose-tending-move-stores`, `feedback-log-tends-itself` and `shared-job-finder` stay as they are. The waiting page's store is one of the stores `prose-tending-contract` tends, and it needs no tending once there is one copy.

## Why

Protects: the owner sees the same data in git and on the page. A lost page or an account switch loses nothing, because git is the store and the site does not depend on a Claude account.

## Cost

No long-lived process or timer of ours. The Worker is hosted by Cloudflare on the free plan (unmeasured limits). The open page polls (pick 1): the viewer's browser runs it. A check runs at each commit or push that touches `waiting/` (step 3), and one record-branch CI job. One commit per Send, Undo or Ask batch.

Refuter: revise, on the plan that judged all four routes (taken: the `stale_pages.py` loader, the `receipts` layout, the probe gaps, the Status tab, the forgery claim, the live-view pick). The owner's ruling at 12:10 CST picked route B from that plan; no new plan was made.

Kind: process
Home: skills/waiting-page/SKILL.md

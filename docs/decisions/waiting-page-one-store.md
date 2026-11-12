# The waiting page has one store, and it is git

## The ruling

Owner, 2026-11-11 11:50 CST (ruling R28, restart plan item 3.14, `docs/plans/restart-plan.md` 554-555): "ya if anything the actual
page gets its database disableed [sic] if that's possible and then it's never an issue ... remember ij [sic] just care about
the outcomes not the plumbing to reach it". The plan reads it as: one store, no copy step, no lag; the design pass picks the route.
Owner, 11:55 CST: "The fallback is moving off artifacts to your own site ... this doesnt sound so bad tho tbh". Owner,
2026-11-12 11:24 CST, through the retrospective: "it shouldn't be a skill thing though it should be pretty mechanized".
The design pass (the plan's direction, not an owner quote) makes git the first write.

- The waiting page's data has one store: the record branch of the repo. Git is the first write. No copy step, no lag.
  This replaces the copy half of decision `waiting-data-in-repo` (git is each artifact's home, the writer copies the page at each
  wake): the copy stays live as the safety net until step 7 of Mechanism lands, and then that record is rewritten in place.
- The page declares no `db`. It reads and writes `waiting/<collection>/<id>.json` on the record branch through a
  claude.ai connector, with the viewer's own login. No token sits in the page. It keeps `comments`, which wakes the writer.
- Route chosen: D (page on claude.ai, git through a connector), on the condition of the probe below. It is not settled until the probe reads. Which connector is open: GitHub's own (D1), or the
  owner's Worker served as a custom connector (D2). Step `page-git-connector-probe` measures it first. If the probe
  rules D out, the route falls back to B (the owner's own site) and this record is rewritten in place.
- Mechanized: two checks, never a skill step (owner, 11:24 CST). See Mechanism.

Routes judged (Plan agent, Opus, then a refuter, Opus, verdict `revise`; the revisions are taken below):

| Route | Verdict |
|---|---|
| A. Db off, page shows a baked git snapshot | Fails: loses Send, Undo, Withdraw, Ask, Park, Mark read; a baked snapshot is a copy with lag. |
| B. Owner's own site, a Worker holds a token | Keeps features. Loses `comments`, so the wake moves to a PR comment (unmeasured). Needs a Cloudflare account, a token and an access gate. Best at surviving an account switch. The fallback. |
| C. Db stays the store, git a derived read | Fails: git is a later copy, so it keeps today's lag and the lost-page loss. |
| D. Page on claude.ai, no `db`, git through a connector | Chosen. Keeps the write features and the wake. Costs below. |

## What D changes (read from `skills/waiting-page/page.html`, checked on main at commit 2deb827ad)

- Turning the db off alone kills every write: `sendAll` returns when there is no db (2299), and Withdraw (1815), Undo (2371),
  asks (2552, 2609) and Mark read (2806) fail too. `comments` is fetched only after the db exists (3179), so the
  boot is reordered.
- Undo and Withdraw become a second commit. Git history keeps the undone answer; today Undo deletes it (SKILL.md "Read the answers").
- The git copy holds five collections and no `receipts` (`export_page.py`, `waiting-data-in-repo`). `receipts` and
  `meta.woke` join the record-branch layout (`WAITING_COLLECTIONS` in `lint/layout.py:275`).
- `stale_pages.py` unread mode reads four list files (lines 91-93, 744-748), not one file per doc, so it needs a new loader.
  `page_grant.py` already reads per-doc files (line 12).
- Today the Questions tab updates live through `onSnapshot` (3181-3193). Under D it polls (`watchTool refetchInterval`, about 30 s
  floor, paused while hidden; `mcp.d.ts` 632-633). This is a lag against "no lag". The coordinator took it as a pick (see Picks), and the owner can overrule it.
- An answer guard is possible on either route: every session write passes the PreToolUse hook, ArtifactData writes included
  (`settings.json` 251), and the page's own writes never do. None is built, so SKILL.md "Read the answers" says "this sentence is the
  only guard". Picked below.

## Picks

Taken by the coordinator at 11:43 CST on 2026-11-12, as undoable picks (no owner question).

1. Live view: poll about every 30 s while the page is open, and refresh on load and focus. The 30 s is tunable and unmeasured, never a
   rule. If the connector offers a cheap change check (an etag or the branch head), the page polls that and fetches only on change.
   Today's view is instant (`page.html` 3181-3193), so this is a lag against "no lag", kept as small as the connector allows.
2. Build a guard that refuses a session write to `waiting/answers/**`. Claude writing an answer by mistake is a likely error, and it forges a grant.
3. Designs stay baked into the page and change on a republish. The mockups are not data the owner answers with.
4. Undo and Withdraw keep the undone answer in git history. Nothing reads it as an answer once a later commit removes it.

Still needs the owner: adding the connector (step 1) and his word on re-pointing the Relayed Grant entry (step 2). Pick 1 can be overruled by him.

## Known gaps

- Unmeasured, decided by the probe:
  - Whether a page can reach a connector from a phone. No source read says.
  - Whether each write raises an approval prompt (`approval_required`, 232-243), and whether `sendToClaude` still follows the click after one (page.html 2263-2265).
  - How Send and Undo behave when a write may have run (`server_unavailable`, `upstream_error`, 76-80).
  - Whether the connector deletes several files in one commit. This session's GitHub tools only have a single-file delete.
  - Calls per page load for D1, and the commit delay between click and wake.
- Whether a claude.ai page can call a Worker origin directly: no `.d.ts` says.
- This account has no GitHub connector (`docs/plans/restart-plan.md` 556-558, read 11:52 CST on 2026-11-11), so D1 needs the owner to add one, or D2 is used. This session could not re-check: no token.
- API commits can make a session's push to the record branch non-fast-forward. The cure is fetch and rebase, never a force push.
- Until step `retire-page-copy` lands, the copy step and its Stop check stay live. The copy is the safety net.

## Mechanism (build steps, handed to the coordinator as step text)

1. `page-git-connector-probe` (blockedBy none): measure a page writing git through `mcp`: the Known gaps list. Includes an owner task to add the connector.
2. `page-one-store-answers` (blockedBy 1): re-point the `settings.json` "Relayed Grant" entry (line 54), which reads answers fetched with ArtifactData. It needs his word. The SKILL.md database section is rewritten at step 5.
3. `waiting-item-check` (blockedBy 2): one validator over `waiting/**.json` for every item rule now keyed on ArtifactData (`guard.py`, `question_form.py`, `call_judge.py`, `local_time.py --page-note`), it runs as a PreToolUse on a commit or push that touches `waiting/`. It also runs in record-branch CI, which does not exist today (`checks.yml` 3-7 runs on main and PRs). Red first on the old commit.
4. `page-reads-writes-git` (blockedBy 1, 3): `page.html` moves its six collections from db to the connector; one commit per Send, Undo or Ask batch; reorder the boot; the wake stays.
5. `writer-writes-git` (blockedBy 2, 3, 4): the writer and tools read and write the record branch; new loader in `stale_pages.py`; the SKILL.md database section is rewritten in place.
6. `page-db-off-guard` (blockedBy 4, 5): refuse an ArtifactData write that names a waiting-page URL and a waiting-page publish that declares `db`; a lint fails when `page.html` calls `use("db")`. Each red first.
7. `retire-page-copy` (blockedBy 6): the copy ends here, and `waiting-data-in-repo` is rewritten in place. Delete the export mode of `export_page.py` and `export_check` in `hooks/feedback_guard.py` (1332); keep `--all` for other artifacts; close `waiting-export-miss-cloud` as superseded.
8. `answers-session-write-guard` (blockedBy none): refuse a session write to `waiting/answers/**`, by a PreToolUse check on ArtifactData and on every git write tool (Bash git, `create_or_update_file`, `push_files`, `delete_file`) that touches it. Red first on the old code. (Pick 2.)
9. `status-tab-reads-git` (blockedBy 1): the Status tab reads steps through the connector, not the baked block. Its own step, apart from this ruling.

The R28 steps `prose-tending-contract`, `prose-tending-move-stores`, `feedback-log-tends-itself` and `shared-job-finder` stay as they are. The waiting page's store is one of the stores `prose-tending-contract` tends, and it needs no tending once there is one copy.

## Why

Protects: the owner sees the same data in git and on the page, and a lost page or an account switch loses nothing, because git is the store.

## Cost

No long-lived process, timer or log of ours. The open page polls (Picks 1): the viewer's browser runs it, and each poll is one connector call, or a cheap change check. A check runs at each commit or push that touches `waiting/` (step 3), and one record-branch CI job. D1 makes one connector call per file on a page load, D2 one call (both unmeasured). One commit per Send, Undo or Ask batch.

Refuter: revise (taken: the `stale_pages.py` loader, the `receipts` layout, the probe gaps, the Status tab split out, the forgery claim, the live-view question).

Kind: process
Home: skills/waiting-page/SKILL.md

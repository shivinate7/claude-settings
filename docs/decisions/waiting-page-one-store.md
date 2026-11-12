# The waiting page has one store, and it is git

## The ruling

Owner R28, 2026-11-11 11:39-11:55 CST (restart plan item 3.14): "ya if anything the actual page gets its
database disabled if that's possible and then it's never an issue ... remember i just care about the outcomes
not the plumbing to reach it". Owner, 2026-11-12 11:24 CST, via the retrospective: "it shouldn't be a skill
thing though it should be pretty mechanized".

- The waiting page's data has one store: the record branch of the repo. Git is the first write. No copy step, no lag.
- The page declares no `db`. It reads and writes `waiting/<collection>/<id>.json` on the record branch through a
  claude.ai connector, with the viewer's own login. No token sits in the page. It keeps `comments`, which wakes the writer.
- Route chosen: D (page on claude.ai, git through a connector). Which connector is open: GitHub's own (D1), or the
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

## What D changes (read from `skills/waiting-page/page.html`, checked at 2deb827ad)

- Turning the db off alone kills every write: `sendAll` returns when there is no db (2299), and Withdraw (1815), Undo (2371),
  asks (2552, 2609) and Mark read (2806) fail too. `comments` is fetched only after the db exists (3176-3178), so the
  boot is reordered.
- Undo and Withdraw become a second commit. Git history keeps the undone answer; today Undo deletes it (SKILL.md "Read the answers").
- The git copy holds five collections and no `receipts` (`export_page.py`, `waiting-data-in-repo`). `receipts` and
  `meta.woke` join the record-branch layout (`lint/layout.json`).
- `stale_pages.py` unread mode reads four list files (lines 91-93, 744-748), not one file per doc, so it needs a new loader.
  `page_grant.py` already reads per-doc files (line 12).
- Today the Questions tab updates live through `onSnapshot` (3181-3193). Under D it polls (`watchTool refetchInterval`, about 30 s
  floor, paused while hidden; `mcp.d.ts` 632-633). This is a lag against "no lag": an owner question, below.
- Answers get a guard today's route cannot have: every session git write passes the PreToolUse hook (`settings.json` 251),
  the page's connector calls do not, so a session write to `waiting/answers/**` can be refused. Today "this sentence is the
  only guard" (SKILL.md "Read the answers"). Whether to build it is the owner's call (rule `building-guard-needs-incident`).

## Open for the owner

Brought in question form by the lane's report; none is built.

1. Live view: poll about every 30 s while the page is open (a lag, but the page is current), or refresh on load and focus only.
   Today's view is instant. It touches the ruled "no lag".
2. A guard that refuses session writes to `waiting/answers/**`, so only the owner's page sends an answer.
3. Designs stay baked into the page and change on a republish. The mockups are not data the owner answers with.

## Known gaps

- Unmeasured, decided by the probe:
  - Whether a page can reach a connector from a phone (`host:` fails outside the desktop app, `mcp.d.ts` 110-124).
  - Whether each write raises an approval prompt (`approval_required`, 232-243), and whether `sendToClaude` still follows the click after one (page.html 2263-2265).
  - How Send and Undo behave when a write may have run (`server_unavailable`, `upstream_error`, 76-80).
  - Whether the connector deletes several files in one commit. This session's GitHub tools only have a single-file delete.
  - Calls per page load for D1, and the commit delay between click and wake.
- Whether a claude.ai page can call a Worker origin directly: no `.d.ts` says.
- Whether this account has a GitHub connector at all: the read failed here (no token).
- API commits can make a session's push to the record branch non-fast-forward. The cure is fetch and rebase, never a force push.
- Until step `retire-page-copy` lands, the copy step and its Stop check stay live. The copy is the safety net.

## Mechanism (build steps, handed to the coordinator as step text)

1. `page-git-connector-probe` (blockedBy none): measure a page writing git through `mcp`: the Known gaps list. Includes an owner task to add the connector.
2. `page-one-store-answers` (blockedBy 1): owner items 1 and 2 above, and the `settings.json` "Relayed Grant" entry (line 54), which reads answers fetched with ArtifactData: re-point it. It needs his word. Rewrite `waiting-data-in-repo` and the SKILL.md database section in place.
3. `waiting-item-check` (blockedBy 2): one validator over `waiting/**.json` for every item rule now keyed on ArtifactData (`guard.py`, `question_form.py`, `call_judge.py`, `local_time.py --page-note`), it runs as a PreToolUse on a commit or push that touches `waiting/`. It also runs in record-branch CI, which does not exist today (`checks.yml` 3-7 runs on main and PRs). Red first on the old commit.
4. `page-reads-writes-git` (blockedBy 1, 3): `page.html` moves its six collections from db to the connector; one commit per Send, Undo or Ask batch; reorder the boot; the wake stays.
5. `writer-writes-git` (blockedBy 2, 3): the writer and tools read and write the record branch; new loader in `stale_pages.py`.
6. `page-db-off-guard` (blockedBy 4, 5): refuse an ArtifactData write that names a waiting-page URL and a waiting-page publish that declares `db`; a lint fails when `page.html` calls `use("db")`. Each red first.
7. `retire-page-copy` (blockedBy 6): delete the export mode of `export_page.py` and `export_check` in `hooks/feedback_guard.py` (1332); keep `--all` for other artifacts; close `waiting-export-miss-cloud` as superseded.
8. `status-tab-reads-git` (blockedBy 1): the Status tab reads steps through the connector, not the baked block. Its own step, apart from this ruling.

The R28 steps `prose-tending-contract`, `prose-tending-move-stores`, `feedback-log-tends-itself` and `shared-job-finder` stay as they are. The waiting page's store is one of the stores `prose-tending-contract` tends, and it needs no tending once there is one copy.

## Why

Protects: the owner sees the same data in git and on the page, and a lost page or an account switch loses nothing, because git is the store.

## Cost

No process, timer or log of ours. D1 makes one connector call per file on a page load, D2 one call (both unmeasured). One commit per Send, Undo or Ask batch.

Refuter: revise (taken: the `stale_pages.py` loader, the `receipts` layout, the probe gaps, the Status tab split out, the forgery claim, the live-view question).

Kind: process
Home: skills/waiting-page/SKILL.md

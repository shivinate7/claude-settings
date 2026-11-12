# Plan: gather other repos' outbox findings into claude-settings triage

Step `outbox-aggregate-plan` (owner ask, page item 493 a, 2026-11-10 11:59 CST: "eventually session mailbox
though ... propose a plan to aggregate all of those findings so that the outbox clears from the other repos,
and then let me know later how you'd want that mechanized"). Plan only. Nothing here is built.
Heads read 2026-11-12: main bcbeaa26a, origin/roadmap 612199608, origin/restart-plan 0a36899cd.

## Sweep

| Repo | Outbox read | Result |
|---|---|---|
| claude-settings | yes, origin/roadmap bb19d28a3 | triage.md 893 bullets (note 75, debt 52, step 9, stands 7, incident 6, decision 3, 741 untagged; Oct 28 to Nov 12); batch62-unbacked-lines.md 1; child-cites-briefs.md 3 briefs for home, degen, ios-adblock; pick-stands-audit.md 41 rows; one lane handoff, not counted |
| tile-windows, session-mailbox, mailaudit, banchi, joyous, home, ios-adblock, q_max, degen, adblock-lists, inbox-engine, advisor, Brewer-KYC, mailaudit-data, frag-head-beta, note-scrape | no | **unknown**: this session's GitHub scope is claude-settings only |

Item 490 measured q_max, banchi, degen, home and mailaudit outboxes holding README.md only (11:12 CST Nov 10).
The files pushed after that go from claude-settings to the children, not the other way.
So the owner's premise ("a lot" waits in other outboxes) is **unmeasured, leaning false**.

## Premises

- P1 [ruling] Other outboxes hold many findings for claude-settings. Source: item 493 note. Unknown, leaning fails (above).
- P2 [ruling] End state is the session mailbox. Holds, with a gap: `own_addrs` (hooks/mail.py:225-236) gives
  only `cloud/<id>` or `pc/<host>/<repo>`; triage rotates, so no fixed address names "claude-settings triage".
- P3 [read] An outbox is `roadmap/outbox/<slug>.md` on the repo's record branch (operating-model.md:164).
  Holds for claude-settings. The record branch name in other repos is unknown (lint/layout.py `record_branch()`).
- P4 [read] Triage removes what it filed (operating-model.md:166). Holds inside one repo only. No route clears
  another repo's outbox, and pick 493 a says every session still writes only in its own repo, no guard changes.
- P5 [read] Mailbox faults are open: partly fails. Restart-plan R49 measured Windows and turns the default on for
  cloud and Windows. R57 rules the wake route (a background mail-wait). Mac auth is still open. Reach from the
  ssemwal-cdc account is unmeasured.
- P6 [ruling] Pick 493 a lets triage read other outboxes: holds for the 5 repos it names (q_max, banchi, degen,
  home, mailaudit); the other 11 have no grant.
- P7 [notes] 16 other repos. Source: the lane brief. No list in this repo.

Simpler route: a finding is non-urgent, so it needs no wake. Read it when triage wakes; the wake fault and the
doorbell then block nothing. `roadmap/build.py` already counts outbox files at each wake (build.py:207-209):
the read belongs there, one home.
Trap: gathering into `roadmap/outbox/triage.md` clears nothing. It already holds 893 bullets owed to
`docs/debts/notes.md` on main.

## Acts, in order

1. **Read every repo once.** A session with access lists the owner's repos. Per repo: one `ls-remote` for the
   record branch, then fetch and list `roadmap/outbox/*.md` only if it exists. Sort each into A holds items for
   claude-settings, B README only, C no record branch or outbox, D no access, E retired
   (lint/test_retired_repos.py). Proof: a 17-row table, no blank cell. Cost: about 17 to 34 git starts, once;
   one scratch fetch, deleted after.
2. **Sort the items.** An item belongs to claude-settings if it names a claude-settings rule, hook, skill,
   decision, the shared page template, or a gap in how Shivam works. Child-own items stay. Unclear items are
   listed, never moved.
3. **File each item in its home, never in triage.md.** Notes and debts: `docs/debts/notes.md` and `docs/debts/`
   on main, through one lane (merge by union). Steps: written by triage. Rulings: their decision record.
   Every filed line cites `<repo>@<outbox blob sha>` plus the item's first 60 characters; before filing, triage
   greps the record branch and main for that cite, so nothing files twice.
4. **Clear the outboxes.** The owning repo's triage removes each line whose cite appears in a claude-settings
   commit on main or the record branch. Proof: that commit's sha. No cross-repo write. Departs from item 490's
   route (one owner override lets a claude-settings session push into child record branches); that route is the
   fallback if a child triage is not running.
5. **Backlog drain is acts 1 to 4, once.** Steady state before the mailbox: at each triage wake, `build.py` runs
   one `ls-remote` per granted repo and fetches only when the sha moved (the pattern of hooks/mail.py:112-120).
   Cost: N git starts per wake (N = granted repos); no timer, no new process; one cached sha listing whose
   reader is triage.
6. **Mechanism (end state: the mailbox).** Senders use one fixed folder,
   `mail/role/shivinate7-claude-settings/triage/` (`SAFE`, mail.py:29, accepts it; `send --to` and
   `read --addr` already serve it, bin/mail:35,106): no code change. `build.py` adds one `mail read --addr`
   line beside the outbox count. Triage files the item citing the message id, then runs `mail take`; a crash
   between the two leaves the item open, and the id cite catches the re-file. `take` refuses a second take
   (bin/mail:67-71), so the take is the clear. Children's operating-model line: a finding for claude-settings
   goes by mail; the outbox keeps own-repo items only. Blocker: Mac `ls-remote` auth. Until measured, a Mac
   sender writes its own outbox and act 5's per-repo read stays on. Gate: a sender session needs
   session-mailbox attached (session-messages.md:190).
7. **Tests for `build.py`.** A `file://` bare repository as the mailbox store (as hooks/test_mail.py:246 does);
   red on a named old commit; each failure message names one cause; no real clock; fixtures with an empty
   outbox, a README-only outbox and a full one; the check tested on its rule's own cases.

## Risks and unknowns

- Act 2 sorting is judgement; the list of unclear items goes to a refuter or the owner.
- If no child triage runs, act 4 stalls.
- `build.py` wake cost grows with each repo granted.
- Unknown: does guard `roadmap-one-writer` check the repo or only the `cs-build:triage` tag? If only the tag, claude-settings triage could push to a child's record branch. The plan does not use it.
- Unknown: contents and record branch names of the 16 repos; whether any child triage runs; reach from the ssemwal-cdc account; whether #2965 is on main (a grep found no commit).
- New name: GLOSSARY.md has no row for "triage mailbox folder". Act 6 adds one, or the owner names it.

## Owner acts

- a. A read grant for every repo beyond the 5 that pick 493 a names, by name or "all shivinate7 repos"; in the cloud also attach them to the session, or run act 1 from the Mac.
- b. Pick the clearing route: each child's triage clears (recommended), or a one-time override push per repo (item 490 route).
- c. Measure Mac `ls-remote` auth (session-messages.md step 2) before the mailbox is the only route.

## Next

Run act 1 (needs owner act a). Then plan acts 2 and 3 item by item.

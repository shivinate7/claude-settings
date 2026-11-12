# Waiting page, step ask-dismiss: dismiss an answered ask (design notes)

Mockup: `docs/design/ask-dismiss.html`. Screen: `skills/waiting-page/page.html` at ask-dismiss 7975f6d8. Its CSS
(lines 8–840) is copied whole into the mockup. Only `#newcss` is new.
Deep links: `#s=open|folded-too|just-dismissed|just-dismissed-count|reply-waiting|next-load|dismissed-list|restored|all-dismissed|failed|offline`,
`&w=all|390|800|1280`, `&t=light|dark`, `&lab=off`, `&hide=<state>,...`. Each state is a `data-state` element in `#pics`.
Sizes: phone 390, mid 800 and wide 1280, as the brief names. `layout.py devices` prints `unknown` for this repo.
Themes: light and dark. In the frames, Dismiss turns a row into its Dismissed line, and Restore turns it back.
Owner ask, Nov 6 11:22 CST: answered asks stay on the page for good, so old ones bury new ones. Triage's done line: a Dismiss
press beside Reply writes `dismissed` on `asks/<id>` with `update`; the page hides dismissed asks; the writer never rewrites one.

## 1. What Dismiss stores, and where. Owner grant: yes

- Pick: one field, `dismissed` (ISO time), on the thread's root ask only (`asks/<root id>`), written with the db handle's
  `update` (a merge write; it rejects when the record is gone, so a dismiss never brings back a deleted ask; runtime `db.d.ts`).
  Gain: one write, one Restore, and the thread is what the list draws (`askThreads`, `askItem`). Reply records stay untouched.
- Other option: `dismissed` on every record of the thread. Gain: each record says it alone. Loss: N writes for one press, a
  part-failed dismiss, and a reply sent later (from another tab) lands undismissed in a dismissed thread anyway.
- Restore writes `dismissed: null` with `update`. The runtime has no field-delete call. The page reads only a valid ISO time as dismissed.
- Nothing is deleted. The record, its `text` and the session's `reply` stay in the store (ruling: a dismissed ask keeps its record).
- Who reads it: the page, to hide the thread. The writer routes and answers a dismissed record as any other, with `update`, which
  keeps `dismissed`. No session writes `dismissed`.
- A thread shows again, whatever `dismissed` says, when a record in it waits, or has an `answered` later than `dismissed`.
  So an answer never lands hidden (a reply sent from another tab before this dismiss reached it).
- Departs from: SKILL.md "The database", which says the page writes `id`, `text` and `at` once, at Send. `dismissed` is a second
  page write, later, by the owner's press. Not blocking.

## 2. Where Dismiss shows (pick: "On folded rows too")

- In the open card (both options): Dismiss sits beside Reply at the thread's end, in one cluster `.endrow`, Reply first. It is
  today's `.btn.quiet`, 44 px: the quieter act. Its name says its target: `aria-label="Dismiss: <ask text, 60 chars>"`.
- Option "On folded rows too" (`#s=folded-too`, focus `#pick-folded`, pick). Each folded answered row gets Dismiss beside the
  row button, a sibling, never inside it (`.frow` is one button). Gain: one press per old answer; the folded rows are the ones that
  bury. Loss: a second target on each row. At 390 the row has no room for "Show answer": it stays in the row button's name,
  visually hidden, and the whole row stays the press. Departs from: today's phone folded row (`askItem`), which shows "Show answer". Not blocking.
- Option "In the open card only" (`#s=open`, focus `#pick-open`). Folded rows stay as today. Gain: no change to the row. Loss: two
  presses per old answer (Show answer, then Dismiss), and the open card grows first.
- Hide controls: "In the open card only", "On folded rows too". The waiting page stamps its own letters, so no option has one.
- Other option, not drawn: "Dismiss all seen answers" at the list's end. Gain: one press clears the backlog. Loss: a batch write,
  and it dismisses answers the owner never reopened. Draw it if he wants it.

## 3. Taking a dismiss back (pick: "Restore, no count")

- Option "Restore, no count" (`#s=just-dismissed`, focus `#pick-nocount`, pick). After the write, the row becomes its Dismissed line
  in the same place, at the folded row's height: "Dismissed. <ask text>" with Restore. It stays until the next load
  (today's rule: a fold changes only at a load or a press). Focus moves to the line: the `li` has `tabindex="-1"`, its `p.sline` has `role="status"`; Tab reaches Restore.
- Why no count: today's 8-second Undo (`undoAsk`, `syncUndo`) exists because the writer routes an ask 10 seconds after its `at`
  ("Route an ask"). Nothing acts on `dismissed`, so there is nothing to race, and Restore can stay for the whole visit.
  Departs from: the Send Undo's 8-second count. Not blocking.
- Option "Undo with an 8-second count" (`#s=just-dismissed-count`, focus `#pick-count`). Today's pattern: "Undo (6)", then hidden
  (`.spent`). Gain: one Undo pattern on the page. Loss: after 8 seconds the way back is only "Show N dismissed asks".
- Either way the dismiss Undo is not `askState.sent` and not `#askUndo`. It never locks Send ask, and never replaces a reply's Undo.
- One name for the act: Restore, in the Dismissed line and in the dismissed list.

## 4. Found again: "Show N dismissed asks"

- State `next-load`: dismissed threads are gone from the list. One more `.unfold` under "Show N older asks" counts them:
  "Show 3 dismissed asks". Absent at zero (ux-control-earns-place). The freed place goes to the next older seen answer, at the load.
- State `dismissed-list`: it opens `ol.dlist` after itself: each dismissed thread as a folded row, newest first by the root's `at`,
  on a dashed edge (the page's look for a thing set aside), with Restore beside it. Show answer still opens the thread.
- State `restored`: Restore on a dismissed row writes `dismissed: null`. The row stays in place, says "Restored. It joins the
  list at the next load.", and shows Dismiss in place of Restore (ux-order-holds-still).
- The `shown` filter of `renderAskList` reads dismissed threads once per load. A dismiss this visit keeps its row as the Dismissed
  line, so no row comes up from behind "Show N older asks" mid-visit. A dismiss from another tab also draws the Dismissed line here.
- The dismissed count and list are read at load too. A thread dismissed this visit lives only as its Dismissed line until the
  next load, so it never shows twice (drawn: "Show 2 dismissed asks" in `just-dismissed`).
- A thread with a waiting record shows again at once, mid-visit: section 1's "an answer never lands hidden" wins over the
  once-per-load set. A thread restored or dismissed this visit leaves the dismissed list or the Dismissed line when a reply waits.
- State `all-dismissed`: nothing waits and every thread is dismissed. Today's "Nothing asked yet." would be false. New sentence:
  "No ask on the list. Type above, and a session answers here." The dismissed unfold stays.
  Departs from: today's empty sentence in `renderAskList`, only in this case. Not blocking.

## 5. A thread with a waiting reply: Dismiss is off

- State `reply-waiting`. While any record of the thread waits (`askWaitsIn`), Dismiss is off: dashed edge, `aria-disabled="true"`,
  and its reason beside it: "Dismiss turns on once your reply has its answer." Why: a dismissed thread would hide the answer he waits for.
- Off, not absent: he saw Dismiss on the other cards, so its absence would read as a bug (ux-control-earns-place: an expected control says why).
- A folded row with a waiting reply (`.fwait`) has no Dismiss. Its row has no room for the reason; Show answer leads to it.
- An ask with no answer has no thread end, so no Reply and no Dismiss, as today.
- Departs from: triage's line "each answered ask has a Dismiss press". An answered root with a waiting reply has one, but it is off. Not blocking.

## 6. Failure states

- Press: Dismiss reads "Dismissing…" in the box of its widest label (today's `.fixw`) until the write answers. Not drawn.
- State `failed`: the write fails. The card stays. The line at the thread's end (today's `.sline`, above the buttons) says
  "Not dismissed (permission-denied). The ask stays on the list." Dismiss stays on and tries again. On a folded row the same line
  shows under the row, outside the button (as `.fwait`). Restore that fails: "Not restored (<code>). It stays dismissed."
- State `offline` (`state.db === false`): today's "Your asks cannot be read in this view." No list, so no Dismiss. As today.
- A store not yet answered: today's "Loading your asks…". No Dismiss.

## 7. Selectors and ids for the builder

- Per thread, keyed by the root ask id `<k>`: `#dis-<k>` (Dismiss, `.btn.quiet.dismiss`, `data-ask`, `aria-label`), `#dw-<k>` (the
  reason while off, the button's `aria-describedby`), `#res-<k>` (Restore, `.btn.alt.restore`), `li#row-<k>.askc.dropped`
  (the Dismissed line, `tabindex="-1"`), `#dun-<k>` (Undo, count option only).
- `.replyend .endrow` (Reply and Dismiss), `li.askc.folded.withd` (a folded row with a side button), `#askDismissed` (the unfold,
  `.unfold.older`, `aria-expanded`), `ol#askDList.asklist.dlist` (`aria-label="Dismissed asks, newest first"`).
- `askState` gains `gone: {}` (root id to `{ state: "busy"|"done"|"fail", code }`, this visit) and `showGone: false`.

## 8. Sizes and themes

- 390: a folded row with Dismiss puts its text on line 1 (two lines, clamped) and its time on line 2. The Dismissed line clamps
  its text to two lines, with Restore at the right.
- 800 and 1280: today's one-line folded row, with Dismiss after "Show answer". All new targets are 44 px or more.
- Colour: only page tokens. The Dismissed line and the dismissed rows use `--faint` dashed edges, as the stack and the unfolds do.

## 9. Checked

- Playwright, Chromium: all 11 states at 390, 800 and 1280, light and dark (66 runs). No script error, no sideways scroll, no
  element past the frame edge, every new control 44 px or more each way. Red first on a script error, and on a broken copy
  (a 900 px end row, a 30 px Dismiss).
- `check_designs.mjs` on this branch's page with this mockup in `designData`: item "Where Dismiss shows" (`folded-too`
  `#pick-folded`, `open` `#pick-open`) and item "Taking a dismiss back" (`just-dismissed` `#pick-nocount`,
  `just-dismissed-count` `#pick-count`): exit 0, `problem: null` each. Red (exit 1) on an item with a focus the mockup lacks.
- `label_once.py` on each state at 390: no hit.
- impeccable critique, in one context (no tool to start an agent; `impeccable context` refused by guard rule impeccable-review-only):
  the detector found nothing. Fixed: at 390, "Show answer" and the time overlapped on a folded row with Dismiss; the row now puts
  the time on line 2 and keeps "Show answer" in the button's name (item 2, a named departure). Left, to match today: the store
  code in the failure line ("permission-denied"), and the two dashed unfolds under the list, whose words differ.

## 10. Work outside this folder (for the builder)

- page.html:
  - `askThreads` / `renderAskList`: a thread is dismissed when its root has a valid `dismissed`, no record waits, and no
    `answered` is later. Drop such threads before the `shown` count, at load; keep this visit's dismisses as `.dropped` lines.
  - `askItem` and `askReplyEnd`: `.endrow` with Reply and Dismiss; Dismiss on folded rows (option pick); off with `#dw-<k>` while `askWaitsIn`.
  - New `dismissAsk(k)` and `restoreAsk(k)`: `state.db.collection("asks").doc(k).update({ dismissed: <ISO now> | null })`, one
    write at a time per record; result lines in place. No wake comment: the writer has nothing to do.
  - `#askDismissed` and `ol#askDList`; the all-dismissed empty sentence.
  - `paintLine` skips `.sline.dline`, the row's own result line, so a send-line repaint never erases a Dismiss or Restore line.
  - The Dismissed line: `role="status"` sits on its inner `p.sline`, not on `li#row-<k>`, which keeps the id and `tabindex="-1"`.
  - CSS: this mockup's `#newcss` above the sample-label block.
- SKILL.md, "The database" (`asks/<id>`): the page also writes `dismissed` (ISO time, or `null` at Restore) on a thread's root
  ask, with `update`, at the owner's press. No session writes `dismissed`. A session that answers a dismissed record uses `update`, which keeps it. The page
  hides a dismissed thread unless a record in it waits or has a later answer. "No session deletes or replaces an ask" stays.
- skill `waiting-page`, "Route an ask": the writer routes and answers a record with `dismissed` as any other, with `update`.
  Dismiss is drawn off while a reply waits. It is on only when every record has its `reply`.
- Tests (`skills/waiting-page/tests/page.test.mjs`): dismiss, restore, the waiting override, the frozen `shown` count, and a failed update.

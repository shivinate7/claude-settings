# A decision always reaches a pick you can click

## The ruling

Roadmap step c118, 2026-10-27. When the last reply's Input Needed item offers a pick with options, the stop passes only if one of these holds for the same main-session turn.

- It called `AskUserQuestion`, the question box. The guard does not re-check that nothing runs. `hooks/call_judge.py` and `questions-go-to-owner` already refuse the box while work runs, and the guard does not repeat that.
- The reply text holds the repo's waiting page URL, from `layout.waiting_page`. No page write is needed.
- The Input Needed item names a 5-minute phrase (`5 min`, `5 minutes`, `5-minute` or `five minutes`) and the words "waiting page". It passes this guard in an owner-facing session, never in a lane. The pick-send check in the decision `questions-go-to-owner` (Chat first, then the page) then holds the session to its promise: an open pick over 5 minutes old, with no owner message and no send, blocks the Stop.

For an owner-facing session, the box passes in every repo. Owner ruling, 2026-10-28 15:10 CDT, under roadmap step c202 (chat first, then the page), added the last two. Each page path needs a waiting page in the repo, so in a repo with none only the box passes.

A lane is different. Its Stop passes only with a send tool call (`send_message`) in the same turn. For a lane, the 5-minute clause, the page link and the box do not pass. The lane pick guard in `lint/report_guard.py` enforces this.

The refusal is one line: "Pick guard: Input Needed offers a pick with options and gives no way to answer it. Ask in chat and say it goes to the waiting page after 5 minutes unanswered, link the waiting page, or, only with nothing running, open the question box."

Incident, named: on 2026-10-27 a degen session put "Two ways: A (my pick) ... B ..." under Input Needed as report text only. No control offered a click, and the owner found it late. This guard is the answer to that named incident. It also guards a likely risk: any session ends a report this way.

Incident, named: owner, 2026-11-01 23:26 CST. A coordinator promised "send after 5 min" in each report from 22:25 and sent none until 23:25. Its lanes kept their picks in their own chat. The pick-send check and the lane pick guard answer it. Kind: named incident. Landed 2026-11-02.

**What counts as a pick with options.** `OPTION_LINE_RE`, `OPTION_INLINE_RE`, `OPTION_TAG_RE`, `OPTION_BARE_RE` and `OPTION_OR_RE` in `lint/report_guard.py` hold it. It reads the Input Needed item only.

- Two or more distinct lettered markers. A marker is a lettered item at a line start (`A:`, `A)`, `A.`, `A (my pick):`), or an inline letter A to F followed by `:`, `)` or a "(my pick)" or "(recommended)" tag. After a tagged letter, another bare capital letter A to F counts too.
- Pick context is a tag, a lettered marker, or one of the words pick, option, way, choose or recommended in the same item. Two numbered items (`1.`, `2)`) count only with pick context, so "1. Approve the cap raise. 2. Confirm the date." (separate asks) passes. The phrase "A or B" (letters A to F) counts only with pick context or a numbered item, so "Does Q or A mode apply?" passes.

One marker alone is not a pick. "You picked A on Oct 26; I went with it" quotes an earlier answer and passes. A plain ask with no options passes. A report with no Input Needed label passes.

**Which turns.** Any turn whose reply carries the report labels, not only the turns that ran a git write. The incident report had Done, Input Needed and Next, and nothing says its turn landed a commit. A guard limited to landed turns would miss an ask-only turn. On an unlanded turn the guard judges the pick alone and leaves the report shape to the landed-turn rules.

**Whose calls count.** Only the main session's records. A record marked `isSidechain` (an agent's lines) never counts, so a builder's box cannot clear the main session's pick.

**Failure.** The check fails open on any error, as the rest of the guard does. A rewrite turn (`stop_hook_active`) stays quiet.

Known limits:

- A drive name such as "the A: drive and the B: drive" reads as two lettered markers.
- An owner message clears every open pick asked before it, not only the one it answers. A pick the next report still lists is asked again, with a fresh clock.
- Any send in the asking turn counts as the send of that pick. A lane's pick passes on any send in the turn, not only one to its parent.
- A send made before a peer message, a task notice or a queued message does not count for a pick asked after it: each of those starts a new turn.
- A meta record, such as Stop hook feedback, is never an owner message, so it clears no pick.
- A lane with no get_session record of its own reads as owner-facing.

Cost: no new process, timer or log. One layout read per turn whose Input Needed offers a pick and that opened no box. One JSON file per owner-facing session, `<handoffs dir>/<session_id>.picks`, written only at a Stop that records or clears a pick, and deleted when empty. It also keeps each sent pick's key for 24 hours, so a repeat of a sent pick is not asked again. One stat and one module import (`local_time`) per Stop otherwise. No extra transcript read: the Stop guard reads it already. Test: a Stop whose reply has no pick writes no file.

Kind: process
Home: lint/report_guard.py

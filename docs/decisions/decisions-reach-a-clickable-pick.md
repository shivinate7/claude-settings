# A decision always reaches a pick you can click

## The ruling

Roadmap step c118, 2026-10-27. When the last reply's Input Needed item offers a pick with options, the stop passes only if one of these holds for the same main-session turn.

- It called `AskUserQuestion`, the question box. The guard does not re-check that nothing runs. `hooks/call_judge.py` and `questions-go-to-owner` already refuse the box while work runs, and the guard does not repeat that.
- The reply text holds the repo's waiting page URL, from `layout.waiting_page`. No page write is needed.
- The Input Needed item names a 5-minute phrase (`5 min`, `5 minutes`, `5-minute` or `five minutes`) and the words "waiting page".

The box passes in every repo. Owner ruling, 2026-10-28 15:10 CDT, under roadmap step c202 (chat first, then the page), added the last two. Each page path needs a waiting page in the repo, so in a repo with none only the box passes.

The refusal is one line: "Pick guard: Input Needed offers a pick with options and gives no way to answer it. Ask in chat and say it goes to the waiting page after 5 minutes unanswered, link the waiting page, or, only with nothing running, open the question box."

Incident, named: on 2026-10-27 a degen session put "Two ways: A (my pick) ... B ..." under Input Needed as report text only. No control offered a click, and the owner found it late. This guard is the answer to that named incident. It also guards a likely risk: any session ends a report this way.

**What counts as a pick with options.** `OPTION_LINE_RE`, `OPTION_INLINE_RE`, `OPTION_TAG_RE`, `OPTION_BARE_RE` and `OPTION_OR_RE` in `lint/report_guard.py` hold it. It reads the Input Needed item only.

- Two or more distinct lettered markers. A marker is a lettered item at a line start (`A:`, `A)`, `A.`, `A (my pick):`), or an inline letter A to F followed by `:`, `)` or a "(my pick)" or "(recommended)" tag. After a tagged letter, another bare capital letter A to F counts too.
- Pick context is a tag, a lettered marker, or one of the words pick, option, way, choose or recommended in the same item. Two numbered items (`1.`, `2)`) count only with pick context, so "1. Approve the cap raise. 2. Confirm the date." (separate asks) passes. The phrase "A or B" (letters A to F) counts only with pick context or a numbered item, so "Does Q or A mode apply?" passes.

One marker alone is not a pick. "You picked A on Oct 26; I went with it" quotes an earlier answer and passes. A plain ask with no options passes. A report with no Input Needed label passes.

**Which turns.** Any turn whose reply carries the report labels, not only the turns that ran a git write. The incident report had Done, Input Needed and Next, and nothing says its turn landed a commit. A guard limited to landed turns would miss an ask-only turn. On an unlanded turn the guard judges the pick alone and leaves the report shape to the landed-turn rules.

**Whose calls count.** Only the main session's records. A record marked `isSidechain` (an agent's lines) never counts, so a builder's box cannot clear the main session's pick.

**Failure.** The check fails open on any error, as the rest of the guard does. A rewrite turn (`stop_hook_active`) stays quiet.

Known limit: a drive name such as "the A: drive and the B: drive" reads as two lettered markers.

Cost: no new process, file or timer. One layout read per turn whose Input Needed offers a pick and that opened no box.

**Rewrite-stamp check (`reports-rewrite-stamp`).** The same guard has a second check, landed 2026-11-01. On a landed turn, a reply sentence may say decision D was rewritten (rewritten, rewrote, rewrites, rewrite of) for a ruling. It blocks when D's record was last committed before that ruling. Both the default branch and HEAD must predate it.
- Kind: named incident F119. Sessions said decision `ci-job-caps` was rewritten for the owner's 2026-11-01 18:44 CST ruling, and main showed it last touched on Oct 28.
- Ruling time: a stamp in the sentence (`YYYY-MM-DD HH:MM <zone>`, or `HH:MM <zone>` on the turn's Central date). Else, for "under" or "by" decision R, R's last commit on the default branch. "In place" alone does not trigger.
- Fails open: an unknown id, no time, or a failed git read passes.
- Cost: one regex read of the reply. Only on a reply that matches it, one `git log -1` per cited record (at most 5) plus the default-branch lookup. No file, no timer, no log.

Kind: process
Home: lint/report_guard.py

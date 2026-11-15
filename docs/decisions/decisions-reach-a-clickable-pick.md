# A decision always reaches a pick you can click

## The ruling

Roadmap step c118, 2026-10-27, rewritten under owner ruling 2026-11-01 23:31 CST (decision `questions-go-to-owner`, "Same turn to the page"). When the last reply's Input Needed item offers a pick with options, the stop passes only if the same turn holds a qualifying act. The act no longer depends on a clock or on words in the reply. Decision `questions-go-to-owner` and the spec `questions-reach-page` hold the full rule, including the lane route and the other questions the guard reads ("?" sentences).

- Owner-facing session: a send to the page writer, or an ArtifactData set, update or batch under collection `items` to this repo's page. The question box (`AskUserQuestion`, main session) passes only in a repo with no waiting page (owner, 2026-11-01 23:31 CST, pick a). A send to `@parent` reaches no one here. The guard does not re-check that nothing runs: `hooks/call_judge.py` and `questions-go-to-owner` already refuse the box while work runs.
- Lane: a send to its parent (`@parent` counts only here) or to the page writer. A box, a page link and a promise pass nothing.
- A page link in the reply and a 5-minute promise pass nothing now. Owner ruling 2026-10-28 15:10 CDT (chat first, then the page) added both; the 2026-11-01 23:31 CST ruling retired them, because a promise passed while nothing was sent.

The refusal names the route. Owner-facing: "Pick guard: every question goes to the page writer in the same turn it is asked ... Send it now: send_message to the writer <id>, or read meta/page first." Lane: "Lane pick guard: a lane's own chat does not reach the owner. Send this question to your parent (send_message session_id @parent) now."

Incident, named: on 2026-10-27 a degen session put "Two ways: A (my pick) ... B ..." under Input Needed as report text only. No control offered a click, and the owner found it late. This guard is the answer to that named incident. It also guards a likely risk: any session ends a report this way.

**What counts as a pick with options.** `OPTION_LINE_RE`, `OPTION_INLINE_RE`, `OPTION_TAG_RE`, `OPTION_BARE_RE` and `OPTION_OR_RE` in `lint/report_guard.py` hold it. It reads the Input Needed item only.

- Two or more distinct lettered markers. A marker is a lettered item at a line start (`A:`, `A)`, `A.`, `A (my pick):`), or an inline letter A to F followed by `:`, `)` or a "(my pick)" or "(recommended)" tag. After a tagged letter, another bare capital letter A to F counts too.
- Pick context is a tag, a lettered marker, or one of the words pick, option, way, choose or recommended in the same item. Two numbered items (`1.`, `2)`) count only with pick context, so "1. Approve the cap raise. 2. Confirm the date." (separate asks) passes. The phrase "A or B" (letters A to F) counts only with pick context or a numbered item, so "Does Q or A mode apply?" passes.

One marker alone is not a pick. "You picked A on Oct 26; I went with it" quotes an earlier answer and passes. A plain ask with no options passes. A report with no Input Needed label passes.

**Which turns.** Any turn whose reply carries the report labels, not only the turns that ran a git write. The incident report had Done, Input Needed and Next, and nothing says its turn landed a commit. A guard limited to landed turns would miss an ask-only turn. On an unlanded turn the guard judges the pick alone and leaves the report shape to the landed-turn rules.

**Whose calls count.** Only the main session's records. A record marked `isSidechain` (an agent's lines) never counts, so a builder's box cannot clear the main session's pick.

**Failure.** The check fails open on any error, as the rest of the guard does. A rewrite turn (`stop_hook_active`) stays quiet.

Known limit: a drive name such as "the A: drive and the B: drive" reads as two lettered markers.

Cost: no new process, file or timer. No file written. The extra reads come only on a turn that asks with no send to the page writer. In a session with a remote id, that turn adds the own-record import and one more transcript read (unmeasured). A lane reads no layout; an owner-facing turn with no counted send reads it once (unmeasured). A repo with no waiting page is not blocked: the guard prints a systemMessage, and a lane is never failed open.

Kind: process
Home: lint/report_guard.py

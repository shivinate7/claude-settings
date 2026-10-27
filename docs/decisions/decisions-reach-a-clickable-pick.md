# A decision always reaches a pick you can click

## The ruling

Roadmap step c118, 2026-10-27. When the last reply's Input Needed item offers a pick with options, the stop passes only if the same main-session turn did one of two things.

- It called `AskUserQuestion`, the question box. The gate does not re-check that nothing runs. `hooks/call_judge.py` and `questions-go-to-owner` already refuse the box while work runs, and the gate does not repeat that.
- It called `ArtifactData` with a `set` or `update`, or a `batch` holding such a write, on collection `items`. The URL is the one `layout.waiting_page` gives for this repo, and the reply text holds that URL. When the repo has no waiting page, only the box passes.

The refusal is one line. It says to open the question box, or to put the item on the repo's waiting page and link it.

Incident, named: on 2026-10-27 a degen session put "Two ways: A (my pick) ... B ..." under Input Needed as report text only. No control offered a click, and the owner found it late. This gate is the answer to that named incident. It also guards a likely risk: any session ends a report this way.

**What counts as a pick with options.** `OPTION_LINE_RE`, `OPTION_INLINE_RE`, `OPTION_TAG_RE`, `OPTION_BARE_RE` and `OPTION_OR_RE` in `lint/report_gate.py` hold it. It reads the Input Needed item only.

- Two or more distinct lettered markers. A marker is a lettered item at a line start (`A:`, `A)`, `A.`, `A (my pick):`), or an inline letter A to F followed by `:`, `)` or a "(my pick)" or "(recommended)" tag. After a tagged letter, another bare capital letter A to F counts too.
- Pick context is a tag, a lettered marker, or one of the words pick, option, way, choose or recommended in the same item. Two numbered items (`1.`, `2)`) count only with pick context, so "1. Approve the cap raise. 2. Confirm the date." (separate asks) passes. The phrase "A or B" (letters A to F) counts only with pick context or a numbered item, so "Does Q or A mode apply?" passes.

One marker alone is not a pick. "You picked A on Oct 26; I went with it" quotes an earlier answer and passes. A plain ask with no options passes. A report with no Input Needed label passes.

**Which turns.** Any turn whose reply carries the report labels, not only the turns that ran a git write. The incident report had Done, Input Needed and Next, and nothing says its turn landed a commit. A gate limited to landed turns would miss an ask-only turn. On an unlanded turn the gate judges the pick alone and leaves the report shape to the landed-turn rules.

**Whose calls count.** Only the main session's records. A record marked `isSidechain` (an agent's lines) never counts, so a builder's page write cannot clear the main session's pick.

**Failure.** The check fails open on any error, as the rest of the gate does. A rewrite turn (`stop_hook_active`) stays quiet.

Known limit: a drive name such as "the A: drive and the B: drive" reads as two lettered markers.

Cost: no new process, file or timer. One layout read, only when the turn wrote to `ArtifactData`.

Kind: process
Home: lint/report_gate.py

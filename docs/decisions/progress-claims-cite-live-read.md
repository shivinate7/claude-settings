# A reply line that says how far a step, lane, batch or PR has got cites a live read

## The ruling

The progress-claim check, in the Stop hook `lint/report_guard.py` (rule `progress-claims-cite-live-read`), refuses a reply when a line of it says how far a step, lane, batch or PR has got and cites no live read on that line. It runs on any turn, landed or not. One refusal per turn lists the lines and joins any other reason. A rewrite after a missing-report refusal is checked too, once. A rewrite after a progress-only refusal stays quiet, as with the answered-source check (`stop_hook_active`).

**What it reads.** The last reply, outside fences, blockquote markers removed, judged per paragraph. Soft-wrapped lines join. A table row, list item, heading or bold-labelled line starts its own block. A claim is a sentence with a progress phrase and a subject. The subject may sit in the sentence or in an earlier sentence of its block, or in the header of its table ("Lane 4 finished its checks. It has not finished the merge."; a table whose header says Lane).

- Subject: the word step, lane or batch (plural too), `PR #<n>`, `PR <n>`, a bare `#<n>`, or a kebab-case step id in a code span. A subject inside a code span counts.
- Progress phrase: "in progress", "still going", "still running", "nearly", "almost" or "close to" before done, finished, complete or there, "waiting on", "waiting for", "in flight", "stalled", "hasn't finished", "has not finished", or a percentage before done or complete. A phrase inside a code span is a mention, not a claim. "work in progress" (the noun, as in "the work in progress marker") and "in-progress" as an adjective are no phrase.
- A subject carries to later sentences of its own block, and across a table's rows from its header. A table row, list item, heading or bold label (a report label such as `**Next**`, blockquote or not) starts a block with no carried subject, so a Done item's PR does not become the subject of the Next item.
- A wait on the owner ("waiting on you", "your", "the owner", "the owner's") is no progress claim. A wait on CI or a PR still is.
- A state word alone ("merged", "done", "finished at 19:42 CST") is no phrase. The step asks how far a step or lane "has got", not what state it is in. A phrase with no subject ("work is in progress on my laptop") is no claim.
- A `?` ends only its own sentence. A question sentence is no claim, and a claim before it in the same line still is.

**What counts as a live read.** A named read in the claim's block (its line, or the lines soft-wrapped with it), inside an inline code span or not: `get_session`, `list_events`, `pull_request_read`, `list_pull_requests`, "REST API" or "REST read" (upper case), or a PR URL (`/pull/<n>`). The words "live read" with no named tool are no read. The words "unmeasured", "not read" and "unknown" also pass: they say the line claims no read. A time stamp alone ("read at 11:43 CST"), a bare "REST" ("the REST tests"), a bare `PR #<n>`, `#<n>`, a repo path, a commit hash and `item <n>` are no live read. They name a thing or a time and read nothing. This is why the answered-source patterns are not reused. A stamp passes only beside a named read ("get_session read at 11:43 CST: idle"). The refusal names the reads and offers no bare stamp.

**What is exempt.** A line inside a fence (``` or ~~~). An inline code span is masked over its whole paragraph, so a span that breaks across a line cannot leave its text as a claim, and a `#`, `//` or `/*` inside a span opens nothing. A lone quote or a lone backtick is text.

**Lane choices, process-only.** The refusal names `get_session` on the step's lane for a step line (coordinator ruling on the test-author's question, in the lane brief, 2026-11-13), and the batch's PR for a batch line. The refusal holds facts only (decision `guard-remedy-not-to-owner`). A reply that ran the check but could not finish it reports UNKNOWN in a system message, as the review-record check does.

Incident: 2026-11-13 11:41 CST. A session told the owner that step `rounds-rules-one-record` was "still in progress" from its roadmap status alone. Its lane had finished at 19:42 CST on Nov 12, and its PR sat green in batch 133, unmerged. Risk kind: named incident.

Cost: a regex over the reply. No file, no process, no timer, no log. `ProgressClaimTests` in `lint/test_report_guard_progress.py` watches every file the check opens: the transcript and the stamped guard copy that the hook already reads at load, and no other.

Known limit: the check sees that a line cites a read, not that the read happened. A session can name `get_session` and not call it. A paragraph that uses another phrase ("about halfway", "should land soon") passes. A double-quoted phrase is not masked, so a quoted mention of a phrase on a lane line is flagged; an inline code span is the route for a mention. Search-total counts ("12 open PRs") are outside this check. They belong to step `counts-from-rest` (lane #3172, counts from the REST API).

Kind: process
Home: lint/report_guard.py

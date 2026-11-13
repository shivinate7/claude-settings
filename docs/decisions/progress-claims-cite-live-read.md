# A reply line that says how far a step, lane, batch or PR has got cites a live read

## The ruling

The progress-claim check, in the Stop hook `lint/report_guard.py` (rule `progress-claims-cite-live-read`), refuses a reply when a line of it says how far a step, lane, batch or PR has got and cites no live read on that line. It runs on any turn, landed or not. One refusal per turn lists the lines and joins any other reason. A rewrite after a missing-report refusal is checked too, once. A rewrite after a progress-only refusal stays quiet, as with the answered-source check (`stop_hook_active`).

**What it reads.** Each line of the last reply, outside fences, blockquote markers removed. A sentence of the line is a claim when it holds both a subject and a progress phrase.

- Subject: the word step, lane or batch (plural too), `PR #<n>`, or a bare `#<n>`.
- Progress phrase: "in progress", "still going", "still running", "nearly", "almost" or "close to" before done, finished, complete or there, "waiting on", "waiting for", "in flight", "stalled", "hasn't finished", "has not finished", or a percentage before done or complete.
- A state word alone ("merged", "finished at 19:42 CST") is no phrase. A phrase with no subject ("work is in progress on my laptop") is no claim.

**What counts as a live read.** One of these on the same line, inside an inline code span or not: `get_session`, `list_events`, `pull_request_read`, `list_pull_requests`, "live read", "REST" (upper case, not "counts-from-rest"), a PR URL (`/pull/<n>`), a read stamp (`read at HH:MM`). The words "unmeasured", "not read" and "unknown" also pass: they say the line claims no read. A bare `PR #<n>`, `#<n>`, a repo path, a commit hash, `item <n>` and a time alone are no live read. They name a thing and read nothing. This is why the answered-source patterns are not reused.

**What is exempt.** A line that ends in `?` asks and claims nothing. Fences opened by ``` or by ~~~ are skipped. An inline code span is masked over its whole paragraph, so a span that breaks across a line cannot leave its text as a claim, and a `#`, `//` or `/*` inside a span opens nothing. A lone quote or a lone backtick is text.

**Lane choices, process-only.** The refusal names `get_session` on the step's lane for a step line (coordinator ruling on the test-author's question, in the lane brief, 2026-11-13), and the batch's PR for a batch line. A bare time ("read at" with no tool) is no live read, and no test pins it. The refusal holds facts only (decision `guard-remedy-not-to-owner`).

Incident: 2026-11-13 11:41 CST. A session told the owner that step `rounds-rules-one-record` was "still in progress" from its roadmap status alone. Its lane had finished at 19:42 CST on Nov 12, and its PR sat green in batch 133, unmerged. Risk kind: named incident.

Cost: a regex over the reply. No file, no process, no timer, no log. `ProgressClaimTests` in `lint/test_report_guard_progress.py` watches every file the check opens: the transcript and the stamped guard copy that the hook already reads at load, and no other.

Known limit: the check sees that a line cites a read, not that the read happened. A session can name `get_session` and not call it. A line that uses another phrase ("about halfway", "should land soon") passes. A double-quoted phrase is not masked, so a quoted mention of a phrase on a lane line is flagged; an inline code span is the route for a mention. Search-total counts ("12 open PRs") are outside this check. They belong to step `counts-from-rest` (lane #3172, counts from the REST API).

Kind: process
Home: lint/report_guard.py

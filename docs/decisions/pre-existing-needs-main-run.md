# A pre-existing claim names a run on the base branch's tip

## The ruling

The pre-existing check, in the Stop hook `lint/report_guard.py` (rule `pre-existing-needs-main-run`), refuses a reply when a sentence makes a pre-existing claim and its line names no run on the base branch's tip. A false "pre-existing" lets a lane ship its own red. The batch or main then goes red. The check runs on any turn, landed or not. One refusal per turn lists the lines and joins any other reason. A rewrite after a missing-report refusal is checked too, once, as with the answered check.

**What it reads.** Each sentence of the last reply, outside fences, quoted text and inline code spans. A sentence that ends in `?` asks and claims nothing, but a claim in the sentence before a question is judged. A sentence is a claim when it holds one of three forms:

- the word "pre-existing", "preexisting" or "pre existing", in a sentence that also holds a failure word (fail, red, broken, error, break, regress, flaky). A word joined to another by a hyphen (`pre-existing-needs-main-run`) is not the word.
- "already" and then red, fail, broken, there or present, in a sentence that also holds a failure word.
- a failure word, "too", "also" or "as well", and "on" or "at" then a commit hash or a base, in one clause. A clause ends at a conjunction (and, but, so, while, because, since, although) as well as at punctuation. A hash is 7 to 40 hex characters with at least one digit.

**What counts as a run on the base branch's tip.** One of these on the same line. A source inside an inline code span counts. "On <base> at <hash>", or a CI run URL (`/actions/runs/<n>`) on a line that also says "on <base>". The base is main, master, or origin/<branch>. A bare "on origin/main" names no run. A hash with no base is no run. "On the PR head" is no run. Ruling: coordinator, 2026-11-08 03:52 CST.

**What is exempt.** A claim with a negator in the same clause before it (the answered check's list: not, n't, no, none, nothing, nobody, never, cannot, yet to). Quoted text and code spans are no claim. Fenced blocks are skipped.

Incident 2026-11-07: a lane report said a failure "fails on 32b5f8b8e too, pre-existing". `32b5f8b8e` was the PR's own head, not main, so the failure came from the PR. The lane had measured it on its own head.

Risk kind: likely risk. A lane that runs a failing test on its own branch can call the red pre-existing by mistake.

Cost: runs inside the Stop hook already running; no process start, no file written. `PreExistingNeedsMainRunTests` in `lint/test_report_guard.py` proves the verdicts.

Known limit: a line that names a run on main for one failure clears a pre-existing claim about another failure on the same line. The check reads the form "on main at <hash>", not that the hash is the tip of main, so a wrong hash passes. A claim in other words passes (debt `pe-claims-in-other-words-pass`).

Kind: process
Home: lint/report_guard.py

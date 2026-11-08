# A pre-existing claim names a run on main

## The ruling

The pre-existing check, in the Stop hook `lint/report_guard.py` (rule `pre-existing-needs-main-run`), refuses a reply when a line of it calls a failure pre-existing and names no run on main on that line. It runs on any turn, landed or not. One refusal per turn lists the lines and joins any other reason. A rewrite after a missing-report refusal is checked too, once, as with the answered check.

**What it reads.** Each line of the last reply, outside fences, quoted text and inline code spans. A line that ends in `?` asks and claims nothing. A line is a claim when it holds one of three forms:

- the word "pre-existing" or "preexisting". A word joined to another by a hyphen (`pre-existing-needs-main-run`) is not the word.
- "already red on main", or "already failing", "failed" or "broken" on main.
- a failure word (fail, fails, failed, failing, red, broken, breaks), a commit hash and "too" or "also", in one sentence. The incident line has no "pre-existing" word, so this form is needed.

**What counts as a run on main.** One of these on the same line. A source inside an inline code span counts. The list: "on main at `<hash>`", "on origin/main", or a CI run URL (`/actions/runs/<n>`) on a line that also says "on main". A hash with no main word is no run on main. "On the PR head" is no run on main.

**What is exempt.** A claim with a negator in the same clause before it (the answered check's list: not, n't, no, none, nothing, nobody, never, cannot, yet to). Quoted text and code spans are no claim. Fenced blocks are skipped.

Incident 2026-11-07: a lane report said a failure "fails on 32b5f8b8e too, pre-existing". `32b5f8b8e` was the PR's own head, not main, so the failure came from the PR. The lane had measured it on its own head.

Risk kind: likely risk. A lane that runs a failing test on its own branch can call the red pre-existing by mistake.

Cost: a regex over the reply. No file, no process. `PreExistingNeedsMainRunTests` in `lint/test_report_guard.py` proves the verdicts.

Known limit: a line that names a run on main for one failure clears a pre-existing claim about another failure on the same line. Code reads the line, not what each run covers. A claim in other words ("this was broken before my change") is not read.

Kind: process
Home: lint/report_guard.py

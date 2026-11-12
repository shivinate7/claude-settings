# A pre-existing claim names a run on the base branch's tip

## The ruling

The pre-existing check, in the Stop hook `lint/report_guard.py` (rule `pre-existing-needs-main-run`), refuses a reply when a sentence makes a pre-existing claim and its line names no run on the base branch's tip. A false "pre-existing" lets a lane ship its own red. The batch or main then goes red. The check runs on any turn, landed or not. One refusal per turn lists the lines and joins any other reason. A rewrite after a missing-report refusal is checked too, once, as with the answered check.

**What it reads.** Each sentence of the last reply, outside fences, quoted text and inline code spans. A sentence that ends in `?` asks and claims nothing, but a claim in the sentence before a question is judged. A sentence is a claim when it holds a failure word (fail, red, broken, error, break, regress, flaky) and one of three forms:

- the word "pre-existing", "preexisting" or "pre existing", when it describes the failure. Next comes a failure noun ("a pre-existing failure"), a preposition, or no word. Or before it comes is, was or it ("the failure is pre-existing", "makes it pre-existing"). "A pre-existing test" or "the pre-existing guard" modifies another noun and is no claim. A word joined to another by a hyphen (`pre-existing-needs-main-run`) is not the word.
- "already" and then red, fail, broken, there or present, in a sentence that names a base or "before this change". "Already red on the old code" names neither and is no claim.
- a failure word, "too", "also" or "as well", and "on" or "at" then a commit hash or a base, in one clause. A clause that starts with that ref ("fails here, on main too") takes the failure word from an earlier clause. A clause ends at a conjunction (and, but, or, so, yet, then, because), at a subordinator (since, as, while, although, though), at "which" and at punctuation. A period with no space after it ends a clause when a lowercase letter comes before it and a capital then a lowercase letter after it ("main.The"). A dot inside a token (`report_guard.py`, v1.2) ends none. "Yet" ends a clause only when it joins two clauses. In a verb group it is an adverb and ends none ("not yet confirmed", "have yet to", "not yet been shown"). "As" ends a clause only when a verb follows it ("as it is pre-existing"). "Confirmed as pre-existing" does not end it, and "as well" never does. A hash is 7 to 40 hex characters with at least one digit.

**What counts as a run on the base branch's tip.** One of these on the same line. A source inside an inline code span counts. "On <base> at <hash>", "on <base> at commit <hash>", "on <base> (<hash>)", "<base>@<hash>", or a CI run URL (`/actions/runs/<n>`) on a line that also says "on <base>". The base is main, master, or origin/<branch>. A bare "on origin/main" names no run. A hash with no base is no run. "On the PR head" is no run. Ruling: coordinator, 2026-11-08 03:52 CST.

**What is exempt.** A claim with a negator in the same clause before it (the answered check's list: not, n't, no, none, nothing, nobody, never, cannot, yet to). "I have not yet confirmed the failure is pre-existing" is exempt: "yet" ends no clause there, so the negator reaches the claim. "The lint did not start yet the failure is pre-existing" is not exempt: "yet" ends the clause, so the negator does not reach the claim. Quoted text and code spans are no claim. Fenced blocks are skipped.

Incident 2026-11-07: a lane report said a failure "fails on 32b5f8b8e too, pre-existing". `32b5f8b8e` was the PR's own head, not main, so the failure came from the PR. The lane had measured it on its own head.

Risk kind: likely risk. A lane that runs a failing test on its own branch can call the red pre-existing by mistake.

Cost: runs inside the Stop hook already running; no process start, no file written. `PreExistingNeedsMainRunTests` in `lint/test_report_guard.py` proves the verdicts.

Known limit: a line that names a run on main for one failure clears a pre-existing claim about another failure on the same line. The check reads the form "on main at <hash>", not that the hash is the tip of main, so a wrong hash passes. A claim in other words passes (debt `pe-claims-in-other-words-pass`).

Kind: process
Home: lint/report_guard.py

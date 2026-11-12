# A claim that a check passed cites a verdict line

## The ruling

Question: what backs a session's claim that a check passed? Ruling: coordinator, 2026-11-12 11:23 CST, pick A, with the lane's rulings below. The rule belongs under `tokens-run-through-verdict` (run each check through verdict). The guard is named `pass-claim-cites-verdict`. It adds no new rule anchor.

- A report line or a message that says a check passed must be backed by a verdict line from this session's own transcript.
- The cite is a verbatim `PASS <cmd> (<secs>s)` line in the result of a non-sidechain Bash call whose program is `verdict`. `<cmd>` must be the words that call ran. Both sides read `~` and `$HOME` as the shell expands them. `uv run verdict` counts.
- The cite must match the claim's check. A lint or ci-job claim needs a roster command: `merge --lane-lint`, `merge --release-check` or `ci-job` (a test run is not one; `merge --review-record` is not one) (the roster in `hooks/guard_stream.py`, one home). A tests or suite claim needs a command that names a test, such as `python3 lint/test_x.py` or `pytest`. A checks claim takes either. `verdict true` backs nothing.
- The newest verdict line per command wins. A FAIL after a PASS of the same command cancels it. A SKIP line backs no claim.
- Text in a reply, an Agent result, a sidechain call or a bare run is no cite.
- A claim an agent made is attributed ("builder reports green") and is no claim of this session.
- The roster of bare runs that `verdict` should wrap is the other half of the rule. It lives in `background-check-through-verdict`. "Tests" are not on that roster: no incident names a test command, and a guard on them would cry wolf (`guard-that-cries-wolf-is-spent`).

## Incident, risk and cost

Incident: owner, 2026-11-10 17:17 CST. A session read its own `echo $?` as "lane lint passes". Risk kind: named incident.

Build: `hooks/pass_claim.py` holds the claim detector and the cite reader. Two hooks call it. `lint/report_guard.py` (Stop) judges the report blockquote on landed and unlanded turns. `hooks/guard.py` (PreToolUse) judges a `SendMessage` and a `mcp__claude-code-remote__send_message`. Both fail open on any error, with one stderr line, and an import failure in `hooks/guard.py` leaves the later checks running. The steps for a refusal are in `guard-remedy-not-to-owner`, under "Pass-claim guard".

Claim: a claim word ("passed", "passes", "pass", "green", "clean") within four words of a check noun (lint, tests, checks, suite, ci-job). "passed", "passes" and "pass" need the noun before them. "green" and "clean" take it on either side. CI and build are no noun: no verdict run can cite a GitHub CI result. "Lint: PASS.", "All checks pass." and "Lint `passed`." are claims.

What passes (each has a red sibling in the tests):

- A whole sentence in backticks or in a code fence, and a question. A single word in backticks still counts, so "Lint `passed`." is a claim.
- A negation or a condition within four words before the claim word, in the same clause ("not green", "hasn't passed", "when lint passes"). A comma, semicolon, parenthesis or dash ends the clause, so "No failures, lint passed." is a claim.
- A named speaker within five words before the claim word ("Reviewer: lint passed", "the builder reports lint green").
- A count: a number, or a fraction, before the claim word, with at most one of tests, checks, suites, cases, jobs, files or specs between ("12 passed", "3/5 tests passed"). "PR 7 lint passed." is a claim.
- A claim word with no check noun near it ("the merge is clean", "I passed the brief").
- A claim outside the report blockquote, in a reply.
- A send whose payload carries a non-empty `agent_id`. That is an agent's own report (coordinator, 2026-11-12, lane ruling).

Known gaps:

- An agent sender is not checked (the `agent_id` skip above). An agent's uncited claim reaches its parent.
- A verdict run in the background shows its PASS line in a later notice, not in the call's result, so it is no cite.
- A claim inside a fence is skipped, so it can hide an uncited claim.
- A cite never goes stale: a PASS from before an edit still backs a later claim.
- A speaker word within five words before the claim word exempts it even from another clause ("Builder done, lint passed.").
- Other check nouns ("test", "check" in the singular, "build", "CI") are not on the list.

Cost: none at run time. No file is written and no process starts. The transcript is read once, and only when a claim is found.

Kind: process
Home: hooks/pass_claim.py

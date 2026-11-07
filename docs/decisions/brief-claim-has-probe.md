# A brief's claim about main carries the probe that showed it

## The ruling

Rule `brief-claim-has-probe` in `hooks/guard.py` refuses an Agent or Task brief to a builder or a test-author that says what main, origin/main or "today" passes, allows, accepts or refuses for an input, unless the brief carries the probe that showed it. Its home is `brief_claim_gaps` in `hooks/guard.py`, beside the other brief checks (`marker_scan`, `builder_third_round`). Layer: the coordinator's order, 2026-11-07 CST, after the incident below.

- The mistake (2026-11-07 16:08 CST, PR #1581): a test-author brief said main passes `globalHotkey: Ctrl+Alt+2` and "password: none for guests and visitors". Main refused all of them. The brief was written from memory of main. The builder narrowed the rule to match, and the narrowing let through secrets that main refuses. A fix check caught it before merge.
- The harm: an agent builds to a false picture of main. The error is shipped as a test or a rule, and it looks reviewed because the brief said so.
- A claim: one sentence with a subject word (`main`, `origin/main` or `today`, any case), then up to four words, then a verb (passes, allows, accepts, refuses, or the -ed form). Its inputs are the backticked spans after the verb, else every backticked span in the sentence. `The main branch is the base` and `Today the lane starts on it` name no verb and pass. A claim sentence with no backticked input names nothing to probe and is not judged.
- A probe for an input: a command line that holds the input, with a result line right under it. The command line stands on a line of its own, in a fence, in backticks, or after `$ `, and starts with python, python3, git, verdict, bash, sh, node, npm, npx, pytest, gh, grep, rg or jq. The result line is the next non-blank line, or text after the closing backtick on the same line. The input may stand in the command or in the result line. A probe for another input does not show the claim. A command with no result line, or a result line with no command, is no probe.
- Scope: the roles `builder` and `test-author`, on an Agent or Task call. A reviewer, Explore, designer or any other role passes. A Workflow `agent()` call is not read.
- The scan is one pass over the lines, and only backticks open an input. A lone quote (`Don't`) opens nothing. A lone backtick reads to the line's end. A fence marker with no partner is a plain line. A claim on any line, line 30 and later too, is read.
- The refusal names the input with no probe, and the remedy: add the command and its result, or drop the claim. It names no forbidden target.
- The override lifts it (`owner-override`). It is not in `never_lifted`: the owner may mean the brief as it stands.
- Accepted limits: a claim in other words (`main rejects`, `x passes on main`) or with an input in plain quotes is not read. A command that reads its input from a file and prints a result that does not repeat it is no probe: put the input on the command line. These are the forms Claude is unlikely to write by mistake (`guard-guards-mistakes-only`).
- Cost: pure text work inside the guard call already running. No process start, no file written, no log line beyond the refusal's own.

Protected by the `brief-claim:` cases in `hooks/test_guard.py` (11 deny, 9 allow), red before the rule landed. The mutants in `hooks/mutate_guard.py` labelled `brief-claim:` break each edge once.

Kind: process
Home: hooks/guard.py

# A brief's claim about main carries the probe that showed it

## The ruling

Rule `brief-claim-has-probe` in `hooks/guard.py` refuses an Agent or Task brief to a builder or a test-author that says what main, origin/main or "today" passes, allows, accepts, refuses, rejects or blocks for an input, unless the brief carries the probe that showed it. Its home is `brief_claim_gaps` in `hooks/guard.py`, beside the other brief checks (`marker_scan`, `builder_third_round`). Layer: the coordinator's order, 2026-11-07 CST, after the incident below. Review round 1 of PR #1664 found fifteen edges the first build missed or wrongly refused; they are closed here.

- The mistake (2026-11-07 16:08 CST, PR #1581): a test-author brief said main passes `globalHotkey: Ctrl+Alt+2` and "password: none for guests and visitors". Main refused all of them. The brief was written from memory of main. The builder narrowed the rule to match, and the narrowing let through secrets that main refuses. A fix check caught it before merge.
- The harm: an agent builds to a false picture of main. The error is shipped as a test or a rule, and it looks reviewed because the brief said so.
- An input: a backtick span, a double-quoted string, or a single-quoted string that opens after a non-word character. A lone quote or an apostrophe (`Don't`) opens nothing. A lone backtick reads to the line's end.
- A claim, active form: `main` or `origin/main` (a backticked `main` is still the word) with the verb next to it, or one adverb between (still, also, now, today, currently, already, even, always). Or "today" followed by it, they, guard, hook, rule or check, then the verb. "The main session" and "the main checkout" have no verb next to main, so they are no subject. "Today the builder passes ..." names no subject from that list, so it is a time word. The inputs are those after the verb, else every input in the sentence.
- A claim, passive form: `X` is refused on main, `X` refused by main, `X` passes today. The inputs are those before the verb.
- Verbs: passes, allows, accepts, refuses, rejects, blocks, and their -ed forms.
- Fenced text is read for claims. A claim in a fence after `Cases:` counts.
- A path is a locator, not an input, when it follows in, at, from, under, inside, within or via and has no space and holds `/` or `.`.
- A line that starts with `Add a case:` or `Must deny:` (also `Add the case`, `Must allow`, `Must refuse`, `Must pass`, `Must accept`) holds case data, not a claim.
- A claim sentence with no input names nothing to probe and is not judged.
- A probe for an input: a command line that holds the input as the whole text between quotes, or as the whole line, with a result line right under it. A longer input that merely contains it (`git push --force` for `git push`) is another input. The command line stands on a line of its own, in a fence, in backticks, or after `$ `, and starts with python, python3, git, verdict, bash, sh, node, npm, npx, pytest, gh, grep, rg or jq. The result line is the next non-blank line, or text after the closing backtick on the same line. The input may stand in the result line the same way. A line that holds a claim is a claim first, so a claim line is never its own probe. A command with no result line, or a result line with no command, is no probe.
- Scope: the roles `builder` and `test-author`, on an Agent or Task call. A reviewer, Explore, designer or any other role passes. A Workflow `agent()` call is not read.
- The scan is one pass over the lines. A claim on any line, line 30 and later too, is read.
- The refusal names the input with no probe, and the remedy: add the command and its result, or drop the claim. It names no forbidden target.
- The override lifts it (`owner-override`). It is not in `never_lifted`: the owner may mean the brief as it stands.
- Accepted limits: a claim in other verbs (`denies`, `fails`) or other words (`on the main branch`) is not read. A command that reads its input from a file, with no quotes around the input and no result line that quotes it, is no probe: put the input on the command line in quotes. A case-data line is skipped whole, so a real claim later on that line hides. These are forms Claude is unlikely to write by mistake (`guard-guards-mistakes-only`).
- Cost: pure text work inside the guard call already running. No process start, no file written, no log line beyond the refusal's own.

Protected by the `brief-claim:` cases in `hooks/test_guard.py` (20 deny, 15 allow, 35 in all), red before the rule landed. The mutants in `hooks/mutate_guard.py` labelled `brief-claim:` break each edge once.

Kind: process
Home: hooks/guard.py

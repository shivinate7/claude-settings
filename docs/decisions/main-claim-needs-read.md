# A reply line that compares the work with main cites a read of main

## The ruling

The main-claim check, in the Stop hook `lint/report_guard.py` (rule `claim-vs-main-needs-read`, function `main_claim_problem`), refuses a reply when a line of it says how the work compares with main and cites no read of main on that line. It extends the answered-source check (decision `answered-needs-source`) and shares its line reader, code-span strip and hash pattern. It runs on any turn, landed or not. One refusal per turn lists the lines and joins any other reason. A rewrite after a missing-report refusal is checked too, once. A rewrite after a main-claim-only refusal stays quiet, as with the answered and Done-format refusals (`stop_hook_active`). A rewrite with no refusal before it stays quiet too.

**What counts as a claim.** A line of the last reply, in any case, outside fences and inline code spans, that holds one of these phrases as whole words: "not a regression", "no regression", "not worse than main", "worse than main", "same as main", "main's own", "already on main", "pre-existing on main", "matches main", "regression from main". "Not a regression" and "no regression" count with no other word on the line. A hyphen joins words into a name, so "not-worse-than-main" is no phrase. A claim that sits only inside an inline code span is a mention, not a claim.

**What counts as a cite.** One of these on the same line. A source inside an inline code span counts. The list is closed: a path with a line (`file.ext:123`), `origin/main`, `main@<sha>`, `git show main:` or `git show origin/main:`, a commit hash next to the word main ("main at 36807ad19"), or "main screenshot" or "main's screenshot" with a path or URL. A bare "main", a path or file name with no line, a time, an item number and a `#<n>` PR ref are no cite. The hash pattern is `DONE_REF_RE`'s hex form.

**What is exempt.** A hedge word on the line, as a whole word: "unmeasured", "unknown" or "not read" ("not ready" is no hedge). A line that ends in `?` asks and claims nothing. Fences opened by ``` or by ~~~ are skipped. The nouns "regression test(s)" and "regression suite(s)" are a test count, not a claim ("No regression tests were added."); "No regression in the layout." stays refused.

**Named incident.** The Downloads filter open-Duo layout was called "main's own, not a regression" with no read of main behind it (degen report row D5). The tests hold that line as a replay, with a cited twin that passes.

Risk kind: likely risk. Cost: a regex over the reply. No process, no file beyond the one bounded read of `hooks/guard.py` the Stop hook already makes at load (unmeasured). `MainClaimTests` in `lint/test_report_guard.py` proves it by watching every file the check opens: exactly the transcript and `hooks/guard.py`.

Known limit: code reads phrases and tokens, not what they cite. A line that cites a path with a line for another reason passes. A claim worded another way ("unchanged from main") is not read. A hedge word anywhere on the line exempts it.

Kind: process
Home: lint/report_guard.py

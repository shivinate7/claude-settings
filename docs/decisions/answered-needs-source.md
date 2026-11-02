# A reply line that says "answered" cites its source

## The ruling

The answered-source check, in the Stop hook `lint/report_guard.py` (rule `answered-needs-source`), refuses a reply when a line of it says "answered" and cites no source on that line. It runs on any turn, landed or not. One refusal per turn lists the lines and joins any other reason. A rewrite after a missing-report refusal is checked too, once. A rewrite after an answered-only refusal stays quiet, as with the cite-gloss and Done-format refusals (`stop_hook_active`). A rewrite with no refusal before it stays quiet too.

**What it reads.** Each line of the last reply that holds the whole word "answered", in any case, outside fences and inline code spans. A word joined to another by a hyphen (`answered-needs-source`) is not the word.

**What counts as a source.** One of these on the same line. The item, page, fb-, session_ and URL patterns ignore case. The ref, hash and path patterns do not. A source inside an inline code span counts. The list: a URL, `#<n>`, a PR ref, a commit hash, a repo path, `item <n>`, `page:<n>`, an `fb-` id, a `session_` id, or a time `HH:MM`. A repo path is one of three things. First, a token with `/` and a dotted part (a letter or digit, a dot, a letter or digit). Second, a token with `/` and a known top dir as a segment (docs/, hooks/, lint/, bin/, skills/, agents/, roadmap/). Third, a bare file name with a known extension. So "and/or" is no source. The ref and hash patterns are `DONE_REF_RE`, the same ones the Done check uses.

**What is exempt.** A line where a negator sits in the same clause before the word: not, n't, no, none, nothing, nobody, never, cannot, yet to. A line that ends in `?` asks and claims nothing, so it is exempt. Fences opened by ``` or by ~~~ are skipped. The word "unanswered" is not the word at all. The inbox home word `[question] -> answered` is exempt.

**Lane choices, process-only.** A source inside an inline code span counts. "Not yet answered" is exempt. "and/or" is no repo path. A double-quoted phrase is not a source: a quoted label such as "Departs from" would cite any line.

Risk kind: likely risk. The incident F188 (claude-settings draft PR #1008, `docs/plans/owner-feedback-audit.md`) is related: its real line never used the word, so the tests hold a synthetic replay. Landed 2026-11-02.

Cost: a regex over the reply. No file, no process. `AnsweredNeedsSourceTests` in `lint/test_report_guard.py` proves it by watching every file the check opens.

Known limit: a negator anywhere earlier in the clause exempts the word, so "Q2 was not skipped and Q1 was answered" passes. A line that cites a time or number for another reason passes. Code reads tokens, not what they cite.

Kind: process
Home: lint/report_guard.py

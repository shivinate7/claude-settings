# A Cost line backs each file and count it states

## The ruling

A Cost sentence may name a file or state a count only when the same sentence backs it:

- For a file: a test file that exists and holds the file's name.
- For a count: the code span nearest the count word must be one that a test file holds as a whole name, or a bound, or a mark. A held span farther away does not rescue a near one that no test holds. The docstring lists the bounds.
- For either: a mark, "not pinned", "unpinned", "unmeasured" or "no test".
- A count in a debt note is `among N` or `N of M`. It passes on a bound, a mark, a date (YYYY-MM-DD), or a test named in the sentence that holds its nearest code span. It also passes on `run` and digits that `of` does not follow. A run of backticks that nothing closes is plain text in a note, with no finding. A note's count is a dated past observation, not a standing fact. An undated count in a note went stale at once, as in work item #2063.

A check refuses any Cost sentence that does none of these. A count with no code span needs a bound or a mark.

Use "(not pinned)" only where a figure was measured. Use "(unmeasured)" where it was not.

- The check is `lint/check_cost_pins.py`. It reads the decision records (kind `decisions` in `lint/layout.json`) and the debt notes file (kind `debt-notes`). A debt record's Cost line is not read. Each test file is read once per run.
- A Cost paragraph starts at a line whose first word is `Cost` followed by a character that is not a letter: `Cost:`, `Cost.`, `Cost, per`, `Cost of`, `**Cost**:`. The line may follow a list marker (`-`, `*`, `8.`, `3)`) or bold marks. `Costs` and `Costly` start none. A sentence that starts in one of those forms after the stop of an earlier sentence on its line starts a paragraph too, from that sentence. The stop is the sentence rule's stop, so a stop inside a code span or after `e.g.` counts for nothing. A `Cost:` inside a sentence starts none.
- A paragraph ends at a blank line, a heading, a code fence, or a list item at the same or a lesser indent than the Cost line. A deeper line or list item stays in it. Fenced code is not read. A heading is one to six `#`, a space, then text. A line of `#` alone, or `#` with no space such as `#1850`, is text.
- A heading of any level whose text starts with `Cost` before a non-letter (`## Cost`, `### Cost per call`) opens a cost section. Its body up to the next heading is cost text, and each paragraph in it is read as a Cost paragraph. The heading line itself is not read.
- A paragraph with an unclosed code span cannot be read. It is one finding on its first line: `unbalanced backtick in a Cost paragraph`. A run of backticks opens a span, and the next run of the same length closes it, so a double-backtick span is one span. One pass over the backticks gives both the sentences and the code spans. A span with one space at each end has that space dropped, unless the span is all spaces.
- Each sentence is read alone. A sentence ends at a full stop, `!` or `?` outside backticks, with any `)`, `*`, `"` or `'` after it, then a space or the end. `e.g.` and `i.e.` end no sentence. A test named in a neighbouring sentence pins nothing.
- A file token is a backticked name that ends in a known extension in any case, or starts with `~/` or `.git/`. A trailing `:<digits>` is dropped before the test, and the token is reported as written. A test file name (`test_*`, `*_test.*`, `*.test.*`, `*Tests.swift`, and `*.spec.*` ending in js, jsx, ts, tsx, mjs, cjs, mts or cts) is a pin, not a file token. A token is flagged whether or not its file exists.
- A file token is pinned when a test file named in the same sentence exists and holds the token's name as a whole name: its basename, or for a `<placeholder>` basename the folder before it. `box.json` does not pin `x.json`, and `HEADER` does not pin `HEAD`.
- A count word is zero to six, ten, a single, digits, once, twice, thrice or Nx. A count word needs a cost noun with at most three words between. Once, twice, thrice and Nx count only after a verb of work, with at most three words between, never before a noun. The docstring of `lint/check_cost_pins.py` lists every count word, cost noun and verb of work.
- A count passes on a test only when the test is named in the same sentence and holds, as a whole name, the code span nearest the count word. A test-name span is never the nearest span.
- Code spans, dates, times, versions, decimals, numbers with a time unit or a size unit, line references, ids, "Round N of M", "PR N" and "one" before "of" are not read as part of a claim. The docstring lists each unit and id form.
- A finding is one line on the token's own line: `<record>:<line>: <token> named in a Cost sentence with no pin`. A count with no backing is one finding per sentence, on the line of its count word: `<record>:<line>: count in a Cost sentence with no reader`. Exit 1 when there is a finding.

## Why and harm

PR #1850 (judge an MCP write or merge by the repo it names) had a Cost line that said the guard reads `lint/layout.json` once. It was written from memory, and no test pinned it. Three fix-check passes followed.

Mistake: a Cost line stated as fact with no test behind it. Hand-written read counts in the drive-lease ruling of `sim-test-is-the-one-boot-path`, on PR #2061 (tests for a hold drive with no device list), failed review four times.

Harm: a false Cost line misleads every session that trusts it. The owner trusts an unmeasured number or file claim, and a wrong one costs review rounds.

Source: step `cost-line-pinned` (file pins) and step `cost-line-has-reader` (count rule), lane briefs of 2026-11-08; coordinator, 09:33 and 09:47 CST. The count rulings are the coordinator's, 2026-11-08.

Corpus: coordinator, 09:47 CST: mark the flagged sentences "unmeasured", or "(not pinned)" where a measured figure stands. This lane checks counts only; refusal reasons are a separate finding.

Cost: one python start per CI run, and no file written (unmeasured). It reads the debt notes file once per run (not pinned). `lint/layout.py` reads `lint/layout.json` and the repo's extras file again on each record-kind lookup, with no cache (not pinned: no test counts these reads). It also reads git files to name the repo. It reads each decision record at most once. It reads each test file that a Cost sentence or a debt note names once per run, from a cache (unmeasured: no test counts the reads). `lint/test_check_cost_pins.py` proves the flag and the pin.

## Known limits

- A bound passes a count unread.
- A test named in the sentence pins nothing unless the counted thing is a code span it holds; a sentence that only names the test needs a mark.
- The check does not tell "(not pinned)" from "(unmeasured)". The writer picks the mark.
- A count whose noun comes first, as in "starts one `git diff`", is missed.
- A plain word can be the pinned span when the test holds it. Debt note: `cost-count-hollow-pin`.
- Secs, hrs, KiB, days, weeks, "line N of" and "N percent" are flagged as counts; the unit lists lack them. Debt note: `cost-count-units-gap`.
- Seven to nine, twelve, fetch, stat, invocation, append and round trip as nouns, "two-process" and "a second time" are missed, and "up to date" or "at least" passes as a bound. Debt note: `cost-count-misses`.
- A leading once, twice or thrice is no claim.
- A trailing once, twice, thrice or Nx counts only after a verb of work, with at most three words between.
- A refusal reason in ordinary prose is not read. Fix: none in this lane. Triage holds it as a separate finding.
- A pin is the file's whole name found in the test text. The test may hold the name and not prove the claim. Review reads that.
- Only these extensions mark a file: md, py, mjs, js, ts, tsx, json, jsonl, sh, ps1, cmd, bat, html, css, swift, jsx, cjs, mts, cts, yml, yaml, toml, txt, log, csv, tmpl, sql, cfg, ini, lock and xml. A file with another extension is not seen.
- A path with no extension is not a file token, so `bin/verdict` is not seen. A name outside backticks is not read at all.
- A heading with an underline of `===` or `---` is not a heading here. A table row that starts with `| Cost` opens no paragraph.

Kind: process
Home: lint/check_cost_pins.py
Check: lint/check_cost_pins.py

# A Cost line names a file only when a test pins it

## The ruling

A decision record's Cost sentence may name a file only when a test in that same sentence holds the file's name, or the sentence says the claim is not pinned. A check refuses a Cost sentence that names a file and does neither.

- The check is `lint/check_cost_pins.py`. It reads the decision records only. A debt's Cost line is not read.
- A Cost paragraph starts at a line whose first word is `Cost` followed by a character that is not a letter: `Cost:`, `Cost.`, `Cost, per`, `Cost of`, `**Cost**:`. The line may follow a list marker or bold marks. `Costs` and `Costly` start none.
- A paragraph ends at a blank line, a heading, a code fence, or a list item at the same or a lesser indent than the Cost line. A deeper list item stays in it. Fenced code is not read.
- A paragraph with an odd number of backticks cannot be read. It is one finding on its first line: `unbalanced backtick in a Cost paragraph`. One pass over the backticks gives both the sentences and the code spans.
- Each sentence is read alone. A sentence ends at a full stop, `!` or `?` outside backticks, with any `)`, `*`, `"` or `'` after it, then a space or the end. A Proof sentence next door pins nothing.
- A file token is a backticked name that ends in a known file extension in any case, or starts with `~/` or `.git/`. A trailing `:<digits>` is dropped before the test, and the token is reported as written. A test file name (`test_*`, `*_test.*`, `*.test.*`) is a pin, not a file token. A token is flagged whether or not its file exists.
- A token is pinned when a test file named in the same sentence exists and holds the token's name as a whole name: its basename, or for a `<placeholder>` basename the folder before it. `box.json` does not pin `x.json`, and `HEADER` does not pin `HEAD`.
- A sentence that says "not pinned", "unpinned", "unmeasured" or "no test" is exempt. The writer has said the claim is unmeasured.
- A finding is one line: record, the token's own line, token. Exit 1 when there is one.

Why: PR #1850 (judge an MCP write or merge by the repo it names) had a Cost line that said the guard reads `lint/layout.json` once. It was written from memory. No test pinned it, and three fix-check passes followed. A cost line the owner trusts is a claim about the machine. When no test holds it, it is unmeasured, and the owner cannot tell.

Mistake: a Cost line stated as fact with no test behind it. Harm: the owner trusts an unmeasured number or file claim, and a wrong one costs review rounds.

Source: lane brief of step `cost-line-pinned`, 2026-11-08. The brief's rulings: a finding names the token's own line; a paragraph also starts at `Cost.`; a token is flagged whether or not its file exists. Review round 1 widened the paragraph start, the nesting rule, the sentence ends, the pin match and the extension test. The records the check flagged now name a pin or say "not pinned".

Cost: one python start per CI run, and no file written. It reads `lint/layout.json` through `lint/layout.py`, which opens that file many times inside one call to find the record folder (not pinned: no test counts the reads; about 50 opens measured with strace on 2026-11-08). It reads each decision record once. It reads each test file that a Cost sentence names once per run, from a cache (not pinned: no test counts the reads). `lint/test_check_cost_pins.py` proves the flag and the pin.

Known limit: a pin is the file's whole name found in the test text. The test may hold the name and not prove the claim. Review reads that.

Known limit: only a fixed list of extensions marks a file. The list is md, py, mjs, js, ts, tsx, json, jsonl, sh, ps1, cmd, bat, html and css. It also holds yml, yaml, toml, txt, log, csv, tmpl, sql, cfg, ini, lock and xml. A file with another extension is not seen.

Known limit: a path with no extension is not a file token, so `bin/verdict` is not seen. A name outside backticks is not read at all.

Known limit: a test file is a pin candidate only when its name is `test_*`, `*_test.*` or `*.test.*`. A name such as `FooTests.swift` or `page.spec.ts` is a token with a file extension but no pin, so a Cost sentence naming it must say "not pinned". No record does yet.

Kind: process
Home: lint/check_cost_pins.py
Check: lint/check_cost_pins.py

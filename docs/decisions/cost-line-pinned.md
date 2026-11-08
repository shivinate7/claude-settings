# A Cost line names a file only when a test pins it

## The ruling

A decision record's Cost sentence may name a file only when a test in that same sentence holds the file's name, or the sentence says the claim is not pinned. A check refuses a Cost sentence that names a file and does neither.

- The check is `lint/check_cost_pins.py`. It reads `docs/decisions/` only. A debt's Cost line is not read.
- A Cost paragraph starts at a line that opens with `Cost:` or `Cost.`, bare or after a list marker or bold marks. It ends at a blank line, a list item that is not a Cost line, a heading or a code fence. Fenced code is not read.
- Each sentence is read alone. A sentence ends at a full stop, `!` or `?` followed by a space, outside backticks. A Proof sentence next door pins nothing.
- A file token is a backticked name that ends in a known file extension, or starts with `~/` or `.git/`. A test file name (`test_*`, `*_test.*`, `*.test.*`) is a pin, not a file token. A token is flagged whether or not its file exists.
- A token is pinned when a test file named in the same sentence exists and holds the token's basename. For a basename with a `<placeholder>`, it holds the folder before it.
- A sentence that says "not pinned", "unpinned", "unmeasured" or "no test" is exempt. The writer has said the claim is unmeasured.
- A finding is one line: record, the token's own line, token. Exit 1 when there is one.

Why: PR #1850 (judge an MCP write or merge by the repo it names) had a Cost line that said the guard reads `lint/layout.json` once. It was written from memory. No test pinned it, and three fix-check passes followed. A cost line the owner trusts is a claim about the machine. When no test holds it, it is unmeasured, and the owner cannot tell.

Mistake: a Cost line stated as fact with no test behind it. Harm: the owner trusts an unmeasured number or file claim, and a wrong one costs review rounds.

Source: lane brief of step `cost-line-pinned`, 2026-11-08. The brief's rulings: a finding names the token's own line; a paragraph also starts at `Cost.`; a token is flagged whether or not its file exists. The 7 records the check first flagged now name a pin or say "not pinned".

Cost: one python start per CI run. It reads each decision record once and each test file a Cost sentence names, and writes no file. `lint/test_check_cost_pins.py` proves the flag and the pin; no test counts the reads (unmeasured).

Known limit: a pin is the file's name found in the test text. The test may hold the name and not prove the claim. Review reads that. A Cost line that opens with `Cost, per` or `Cost of` is not a Cost paragraph here, so its files are not read.

Kind: process
Home: lint/check_cost_pins.py
Check: lint/check_cost_pins.py

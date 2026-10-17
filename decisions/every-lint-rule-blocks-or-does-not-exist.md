# A lint rule blocks, or it does not exist, bar six advisory codes

## The ruling

Owner: a lint rule either blocks or does not exist. A rule nobody can see is not a rule. The rule set and the six advisory codes are in `plain-prose-lint` (the STE lint becomes a plain-prose lint). `RULES` in `lint/ste_lint.py` is the home. The rules run on Markdown and on front-end copy. They do not run on source comments and docstrings unless a caller passes `--source-prose` (`source-prose-lint-ships-dark`).

- A lookup rule (a fixed phrase, a fixed pronoun set, a missing conjunction, a word order) may block. A judgment rule (a style call that settles differently each time a reader looks) must not be an `error`. Why: a guard that goes red on prose the project already lives with finds no defect and is spent (`verification-cry-wolf-guard-is-spent`). The deleted judgment rules fired on 25% to 81% of accepted Markdown.
- Deleted: STE002, STE004, STE005, STE010, STE012, STE014, STE016, STE019 (judgment), and STE006 (semicolon) and STE018 (gendered pronoun). Rows, detection code, word tables, regexes and config keys that served only a deleted rule went with them. Surviving codes keep their numbers.
- The deletion does not make passive, vague or over-clustered prose acceptable. It stops a pattern from gating a style it cannot judge. `CLAUDE.md` keeps "Write plainly: short sentences, one term per meaning, no filler."
- STE006 and STE018 left by owner ruling (2026-09-23). STE001 caps a semicolon pair as one sentence. Nothing protects neutral words for an unspecified person, and the owner accepts that. CLAUDE.md holds no semicolon line (`a-rule-with-no-gate-leaves-claude-md`).
- A finding the STE gate fixes is not a block. A finding it cannot fix still blocks (`ste-gate-fixes-not-nags`).
- Front-end copy: the linter reads the text a user sees in `.tsx`, `.jsx`, `.html` and `.vue` files, and the write hook blocks on it (owner, 2026-09-28, `fewest-words-mandate`). STE020 caps a button, label or `aria-label` at 4 words. The owner accepts the risk of a false red on a label that needs 5 words. Reopen the cap if it goes red on a correct label more than once: measure and bring the count to the owner. STE021 requires a UI escape comment to name a rule and a reason. STE011 holds wordiness pairs copied from the Vale style packs (MIT and BSD-3-Clause; notices in `lint/LICENSE-ste_lint`).
- Both gates (`lint/ste_gate.py`, `lint/md_sweep.py`) split findings by severity: an `error` blocks and a `warning` goes in a non-blocking note. Each prints a `NOTE` naming the blocking Markdown rules, and `lint/ste_gate.py` prints a `UI_NOTE` naming the 4-word cap for a UI file.
- `lint/test_gates.py` pins the severity of every remaining row, and that the deleted codes hold no row in `RULES`.
- `README.md` quotes CLAUDE.md's own rule text inside quotation marks with `<!-- ste-disable-line STE015 -->`, because a reworded quote would misreport CLAUDE.md.
- Unmeasured: how often each rule denied a write. Neither gate keeps a log of a denial.

Kind: process
Home: lint/ste_lint.py

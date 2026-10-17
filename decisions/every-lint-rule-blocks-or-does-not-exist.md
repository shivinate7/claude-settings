# A lint rule blocks, or it does not exist, bar six advisory codes

## The ruling

Owner: a lint rule either blocks or does not exist. A rule nobody can see is not a rule. The six advisory codes are the one exception (`plain-prose-lint`). `RULES` in `lint/ste_lint.py` is the home.

- A lookup rule (a fixed phrase, a fixed pronoun set, a missing conjunction, a word order) may block. A judgment rule (a style call that settles differently each time a reader looks) must not be an `error`.

Why: a guard that goes red on prose the project already lives with finds no defect and is spent (`verification-cry-wolf-guard-is-spent`).

Kind: process
Home: lint/ste_lint.py

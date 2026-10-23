# Fewest words, most of all in front-end copy

## The rulings

Owner, 2026-09-28: omit each word and phrase that is not necessary. Prefer one word over a phrase. This counts most in front-end work.

- Keep `lint/ste_lint.py`. Do not replace it with Vale. Why: Vale also cannot judge whether a word is necessary. It needs a Go binary where the write hook runs. A replacement means porting the rules and the shared action. A copy of its word lists gets its value.
- The lint rules that carry the mandate (`RULES` in `lint/ste_lint.py`): the front-end copy scope and the Vale word pairs in STE011.
- The reviewer agent flags front-end copy that is not needed. That part is judgment, so it does not block.
- Owner, 2026-10-22 10:10 CDT: the 4-word label cap (STE020) is dropped. The icon-and-label rule and design review carry label length.

Reopen when a Vale rule catches a defect that no `ste_lint` rule can express.

Kind: process
Home: lint/ste_lint.py

# Fewest words, most of all in front-end copy

## The rulings

Owner, 2026-09-28: omit each word and phrase that is not necessary. Prefer one word over a phrase. This counts most in front-end work.

- Keep `lint/ste_lint.py`. Do not replace it with Vale. Why: Vale also cannot judge whether a word is necessary. It needs a Go binary where the write hook runs. A replacement means porting 11 rules, the hook, the sweep and the shared action. A copy of its word lists gets its value.
- The lint rules that carry the mandate (`every-lint-rule-blocks-or-does-not-exist`): the front-end copy scope, the 4-word cap on a button, label or `aria-label`, and the Vale word pairs in STE011.
- The reviewer agent flags front-end copy that is not needed. That part is judgment, so it does not block.

Reopen when a Vale rule catches a defect that no `ste_lint` rule can express.

Kind: process
Home: lint/ste_lint.py

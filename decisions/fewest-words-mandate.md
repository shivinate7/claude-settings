# Fewest words, most of all in front-end copy

On 2026-09-28 the owner asked for a verbiage mandate. Omit each word and phrase that is not
necessary. Prefer one word over a phrase or a sentence. This counts most in front-end work.

## The rulings

- Keep `lint/ste_lint.py`. Do not replace it with Vale.
- The lint rules that carry the mandate are in `every-lint-rule-blocks-or-does-not-exist`,
  a lint rule blocks, or it does not exist. They are the front-end copy scope, the 4-word
  cap on a button, label or `aria-label`, and the Vale word pairs in STE011.
- The reviewer agent flags front-end copy that is not needed. That part is a judgment, so it
  does not block.

## Why Vale does not replace `ste_lint`

MEASURED only by reading, not by a run. Vale uses the same kind of fixed lookup as STE011,
so it cannot judge whether a word is necessary either. It needs a Go binary on each machine
where the write hook runs, and `ste_lint` needs nothing. Replacing it means porting the 11
rules, the hook, the sweep and the shared action. The value in Vale is its word lists, and a
copy of those lists gets that value.

## What would reopen this

A Vale rule catches a defect that no `ste_lint` rule can express.

Kind: process
Home: lint/ste_lint.py

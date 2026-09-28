# Fewest words, most of all in front-end copy

On 2026-09-28 the owner asked for a verbiage mandate. Omit each word and phrase that is not
necessary. Prefer one word over a phrase or a sentence. This counts most in front-end work.

## The rulings

- Keep `lint/ste_lint.py`. Do not replace it with Vale. Copy the wordiness pairs from the
  Vale style packs into STE011, bloat, after a license check.
- Lint front-end copy. `ste_lint` reads the text a user sees in `.tsx`, `.jsx`, `.html` and
  `.vue` files. The write hook blocks on it, the same way it blocks on Markdown.
- Cap a button, label or `aria-label` at 4 words. The owner chose to build the cap now, and
  accepted the risk of a false red on a label that needs 5 words.
- The reviewer agent flags front-end copy that is not needed. That part is a judgment, so it
  does not block.

## Why Vale does not replace `ste_lint`

MEASURED only by reading, not by a run. Vale uses the same kind of fixed lookup as STE011,
so it cannot judge whether a word is necessary either. It needs a Go binary on each machine
where the write hook runs, and `ste_lint` needs nothing. Replacing it means porting 11
blocking rules, the hook, the sweep and the shared action. The value in Vale is its word
lists, and a copy of those lists gets that value.

## What would reopen this

- The label cap goes red on a label that is correct, more than once. Measure how often it
  fires, and bring the count to the owner.
- A Vale rule catches a defect that no `ste_lint` rule can express.

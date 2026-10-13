# The STE gate fixes what it can and denies the rest

## The question

When a write has STE errors, does the STE gate refuse the write, or fix the text first?

## The ruling

The gate fixes first. For a Markdown write, it rewrites the fixable STE errors and returns the
fixed text through `updatedInput`. It denies only the errors that remain after the rewrite.
A UI file is never rewritten. A UI file with STE errors is denied, as before. The UI suffixes
are `.tsx`, `.jsx`, `.html` and `.vue`.

Owner intent: the gate fixes. It does not nag. The owner marks no golden set.

The mechanism:

- The fixer runs in a child process. Its limit is 5 s. Env `STE_FIXER_LIMIT_S` sets the limit.
- Text over 262144 bytes skips the fixer. Env `STE_FIXER_MAX_BYTES` sets the ceiling.
- A fixer crash, a timeout, or oversize input falls back to plain lint. Plain lint denies the
  errors it finds, as before. The hook exits 0 on that path. The fixer adds no refusal of its own.
- Unsafe or ambiguous patterns stay unfixed. An unfixed error denies the write.
- A fix never changes the line count.
- The gate reads stdin as UTF-8 bytes.

Files: `lint/ste_gate.py` (`autofix`, `run_autofix`, `rewrite_output`) and `lint/ste_lint.py`
(`apply_fixes`).

## Why

A deny sends the writer back for another write. The owner wants the gate to fix, not nag.
How often a deny led to a retry is unmeasured.

The fixer changes words, not line counts. A word swap is the only kind of change it makes.

## What it costs

A rewrite can change meaning. See Holes. The fixed text lands without the writer editing it.

## What protects it

- `lint/test_ste_autofix.py`. It runs on the Linux job only (see Holes).
- The crash rule in gate-hooks-fail-closed (a fixer crash keeps plain lint, never a refusal).

## Holes, named

Each hole ships under the three-round review cap.

- The Edit and MultiEdit path tracks only plain fences and front matter. Text inside a
  blockquote fence, a multi-line pre block, a script block, or an HTML comment is rewritten on
  an Edit. The same text is denied on a Write.
- `e.g.` or `i.e.` at a line end becomes "for example." or "that is." with a period. That breaks
  hard-wrapped prose. Example: a line ending in `e.g.` becomes `for example.`, and a sentence
  that wraps there ends early.
- The fixer limit (5 s) plus the lint timeout (15 s) equals the hook timeout (20 s). A very
  large input with many quote marks can reach 20 s. The hook is then killed, and the gate fails
  open. The old lint timeout failed open the same way.
- Some fixes change meaning:
  - `It's all been fixed` becomes `It is all been fixed`.
  - `ad hoc` becomes `unplanned`.
  - `in between` becomes `between`.
  - `in terms of` becomes `for`.
  - `it would appear that` becomes `apparently`.
  - All-capitals `IT'S A TEST` becomes `It is A TEST`.
  - The heading `Don't Trust` becomes `Do not Trust`.
- A comment that holds `>` ends its mask early. Example: `<!-- a > b -->`.
- The lint still reports `e.g.` inside a blockquote fence or a pre block.
- `lint/test_ste_autofix.py` runs on the Linux job only. The macOS and Windows runner cost is
  unmeasured.
- macOS is unverified for the child-process route.

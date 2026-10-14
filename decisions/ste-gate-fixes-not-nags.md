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
- Each outcome writes one guard.log line through `guard_logger`: `fixed`, `deny`, or `noted`
  with rule STE-fallback (fixer timeout, crash or oversize) or STE-unchecked (lint could not
  run). md_sweep writes one Stop `deny` line per blocked run. The line format is in
  guard-log-read-weekly, the record of what the reader counts. A write with no fix, deny,
  fallback or unchecked outcome writes no line.

Files: `lint/ste_gate.py` (`autofix`, `run_autofix`, `rewrite_output`) and `lint/ste_lint.py`
(`apply_fixes`). Logging: `lint/_transcript.py` (`guard_logger`).

## Why

A deny sends the writer back for another write. The owner wants the gate to fix, not nag.
How often a deny led to a retry is still unmeasured. The log counts denies, fixes and fallbacks per
session, with `--by-session`. It does not pair a deny with the retry that followed. Each line holds
the time, the session and the basename, so a count can be made by hand.

The fixer changes words, not line counts. A word swap is the only kind of change it makes.

## What it costs

A rewrite can change meaning. See Holes. The fixed text lands without the writer editing it.

## What protects it

- `lint/test_ste_autofix.py`. It runs on the Linux job only (see Holes).
- The crash rule in gate-hooks-fail-closed (a fixer crash keeps plain lint, never a refusal).

## Holes, named

Debts: `ste-edit-fence-blind` (Edit rewrites text inside fences that Write denies). `ste-eg-line-end-rewrite` (`e.g.` at a line end becomes a full stop). `ste-hook-timeout-fails-open` (the hook timeout can kill the gate). `ste-fix-changes-meaning` (some autofixes change the meaning). `ste-comment-gt-mask-early` (a > inside a comment ends the mask). `ste-eg-in-fence-reported` (`e.g.` inside a fence is still reported). `ste-autofix-tests-linux-only` (the autofix tests run on Linux only). `ste-macos-child-route-unverified` (the macOS child-process route is unverified).

Kind: process
Home: lint/ste_gate.py

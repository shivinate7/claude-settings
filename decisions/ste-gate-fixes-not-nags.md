# The STE gate fixes what it can and denies the rest

## The ruling

The gate fixes first. For a Markdown write, it rewrites the fixable STE errors and returns the fixed text
through `updatedInput`. It denies only the errors that remain after the rewrite. The gate fixes and does
not nag. Reason: a deny sends the writer back for another write.

- Only STE011 bloat phrases are fixable (`plain-prose-lint`). Five borderline rows have no fix:
  `in a timely manner`, `along the lines of`, `close down`, `of major importance` and `except when`. A
  bloat phrase in ALL CAPS has no fix.
- Latin abbreviations, contractions and nominalizations are advisory and never rewritten. An advisory
  finding never denies and never rewrites. The gate prints it as a non-blocking note, which a denied
  write does not show. The owner accepts the note as a temporary nudge.
- A UI file is never rewritten. A UI file with STE errors is denied. The UI suffixes are `.tsx`, `.jsx`,
  `.html` and `.vue`.
- The fixer runs in a child process. Its limit is 5 s. Env `STE_FIXER_LIMIT_S` sets the limit.
- Text over 262144 bytes skips the fixer. Env `STE_FIXER_MAX_BYTES` sets the ceiling.
- A fixer crash, a timeout, or oversize input falls back to plain lint. Plain lint denies the errors it
  finds. The hook exits 0 on that path. The fixer adds no refusal of its own (`gate-hooks-fail-closed`).
- Unsafe or ambiguous patterns stay unfixed. An unfixed error denies the write.
- A fix changes words, never the line count.
- The gate reads stdin as UTF-8 bytes.
- Each outcome writes one guard.log line through `guard_logger`: `fixed`, `deny`, or `noted` with rule
  STE-fallback (fixer timeout, crash or oversize) or STE-unchecked (lint could not run). md_sweep writes
  one Stop `deny` line per blocked run. The line format is in `guard-log-read-weekly`. A write with no
  fix, deny, fallback or unchecked outcome writes no line. A write with advisory findings only writes no
  line (debt `advisory-note-not-logged`).

Files: `lint/ste_gate.py` (`autofix`, `run_autofix`, `rewrite_output`) and `lint/ste_lint.py`
(`apply_fixes`). Logging: `lint/_transcript.py` (`guard_logger`).

Protection: `lint/test_ste_autofix.py` runs on the Linux job only. `KeptFixesTests` pins the rows that
fix. `RemovedFixesTests` and `RemovedFixesGateTests` pin the rows that do not.

Kind: process
Home: lint/ste_gate.py

## Holes, named

Debts: `ste-edit-fence-blind`, `ste-hook-timeout-fails-open`, `ste-comment-gt-mask-early`,
`ste-eg-in-fence-reported`, `ste-autofix-tests-linux-only`, `ste-macos-child-route-unverified`,
`kept-bloat-rows-unaudited`. A rewrite of a bloat phrase can change meaning in a sentence that no test
holds. How often a deny led to a retry is unmeasured.

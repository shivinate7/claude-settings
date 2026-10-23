# The STE gate fixes what it can and denies the rest

## The ruling

The gate fixes first. For a Markdown write, it rewrites the fixable STE errors and returns the fixed text
through `updatedInput`. It denies only the errors that remain after the rewrite. The gate fixes and does
not nag. Reason: a deny sends the writer back for another write.

- Only STE011 bloat phrases are fixable (`plain-prose-lint`, which lists the rows with no fix).
- Advisory findings (Latin abbreviations, contractions, nominalizations) never deny and are never
  rewritten. The gate prints them as a non-blocking note, which a denied write does not show. The owner
  accepts the note as a temporary nudge.
- A UI file is never rewritten. A UI file with STE errors is denied. The UI suffixes are `.tsx`, `.jsx`,
  `.html` and `.vue`.
- The fixer runs in a child process. Its limit is 5 s (env `STE_FIXER_LIMIT_S`). Text over 262144 bytes
  skips the fixer (env `STE_FIXER_MAX_BYTES`).
- A fixer crash, a timeout, or oversize input falls back to plain lint. Plain lint denies the errors it
  finds. The hook exits 0 on that path. The fixer adds no refusal of its own (`gate-hooks-fail-closed`).
- Unsafe or ambiguous patterns stay unfixed. An unfixed error denies the write.
- A fix changes words, never the line count. The gate reads stdin as UTF-8 bytes.
- Each outcome writes one guard.log line (`lint/ste_gate.py` writes the format): `fixed`, `deny`, or
  `noted` with rule STE-fallback (fixer timeout, crash or oversize) or STE-unchecked (lint could not run).
  A write with no such outcome, and a write with advisory findings only, writes no line.

Kind: process
Home: lint/ste_gate.py

# Edit rewrites text inside fences that Write denies

- **What.** The Edit and MultiEdit path tracks only plain fences and front matter. Text inside a blockquote fence, a multi-line pre block, a script block, or an HTML comment is rewritten on an Edit. The same text is denied on a Write.
- **Where.** The autofix path in `lint/ste_gate.py`.
- **Decision.** `ste-gate-fixes-not-nags` (the STE gate fixes text, not nags).
- **Retire.** Edit and Write share one fence mask. A test with the same text in each block gives the same verdict on both paths.

# The lint reports `e.g.` inside a fence or pre block

- **What.** The lint reports `e.g.` inside a blockquote fence or a pre block as an STE007 warning. That is a false alarm. The warning never blocks. The gate and the sweep show it in an advisory note.
- **Where.** The STE007 scan of `LATIN` in `lint/ste_lint.py`.
- **Decision.** `plain-prose-lint` (the STE lint becomes a plain-prose lint).
- **Retire.** Skip fenced and pre text in the scan. A test with `e.g.` in each block gives no report.

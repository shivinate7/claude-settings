# No STE hook runs on a write; CI carries the lint

## The ruling

Owner, 2026-10-22 10:10 CDT: `settings.json` wires no STE write gate (`ste_gate.py`) and no markdown
sweep (`md_sweep.py`). Both scripts are deleted. A hook that rewrites or denies a write
sends the writer back for another write, and it starts a process on every Write, Edit and MultiEdit.

- CI's STE lint (`actions/ste-lint`) carries the lint. It fails the step on STE001, STE011 and STE013
  on changed lines (`plain-prose-lint`).
- The autofix stays a hand tool: `lint/ste_lint.py --fix` rewrites fixed STE011 bloat phrases in
  Markdown. No hook calls it.
- STE020 (label length) is dropped. STE021 (bad UI escape) folds away with it. The icon-and-label rule
  and design review carry label length.
- The real safety gates stay fail-closed: `guard.py` and `rm_prompt_answer.py`
  (`gate-hooks-fail-closed`).

Unmeasured: how often a writer now meets an STE error first in CI instead of at the write.

Kind: process
Home: actions/ste-lint/action.yml

# Notes: findings too unlikely to hit to be debts
- SendMessage prompt hook may never fire: check that a logged SendMessage call gets a verdict. Decision: haiku-prompt-hooks (blocking prompt hooks trial).
- AskUserQuestion gain/loss rule may block terse real choices: check it on real questions. Decision: haiku-prompt-hooks (blocking prompt hooks trial).
- hooks/guard_wsl.py plain-node form excludes only `*` and `?`, so a bracket glob passes: `wsl -e node mods/[ab]/x.test.mjs` (first-file false green). Fix: exclude `*?[]` too, with a deny case. Decision: wsl-allow-list (WSL allow list).

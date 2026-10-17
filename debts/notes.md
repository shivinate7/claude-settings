# Notes: findings too unlikely to hit to be debts
- SendMessage prompt hook may never fire: check that a logged SendMessage call gets a verdict. Decision: haiku-prompt-hooks (blocking prompt hooks trial).
- AskUserQuestion gain/loss rule may block terse real choices: check it on real questions. Decision: haiku-prompt-hooks (blocking prompt hooks trial).

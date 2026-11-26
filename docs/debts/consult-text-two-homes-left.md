# Two homes still print the old pick remedy

- **What.** Two homes tell a session to take its own pick and say it in the reply, with no consult step first. The consult step is in rule `parallelism-keep-going`. The guard's stake reason and the waiting-page skill's owner-judge step both print the old remedy.
- **Where.** `hooks/question_form.py`, the `STAKE_REASON` constant. `skills/waiting-page/SKILL.md`, the owner-judge test step under "Before you write a decision".
- **Decision.** `questions-go-to-owner` (questions go to the owner; a session consults before it takes a pick it would otherwise bring to the owner).
- **Retire.** Both homes name the consult step before the pick. A case in `hooks/test_question_form.py` pins the consult text in the stake reason, red on the old text.

Seen: 2026-11-25 x1

- **Reported.** 2026-11-25 10:29 CST (lane `consult-before-pick`).

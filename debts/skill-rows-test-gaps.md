# Three skill rows shapes have no test

- **What.** No test covers a tilde line inside a backtick fence. No test covers an unclosed fence or comment at the end of the file. No test covers a lone backtick before a comment opener.
- **Where.** The fixture suite for `lint/check_skill_model_rows.py`.
- **Decision.** `subagent-model-cap` (the subagent model cap, and its skill rows check).
- **Retire.** Add one test per shape. A test for a misread shape goes red on the current code.

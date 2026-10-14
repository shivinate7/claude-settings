# Owner message cut at 1500 chars

- **What.** The judge prompt cuts an owner message over 1500 chars (MESSAGE_MAX). argv holds at most 32,767 chars on Windows, so the cap is a bandaid. PROMPT_MAX (30,000) counts chars, but Windows counts the quoted command line in UTF-16 units, so quotes and emoji can still go over the limit: the check then did not run.
- **Where.** `MESSAGE_MAX` in `hooks/question_outcome.py`; the model call passes the prompt in argv.
- **Decision.** `question-outcome-check` (the question outcome check; its "Holes, named" section names this gap).
- **Retire.** Lane model-prompt-stdin passes the prompt on stdin. Then raise or remove `MESSAGE_MAX`. A test with a 5,000-char owner message shows it whole in the prompt.

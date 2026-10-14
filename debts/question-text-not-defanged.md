# Judge prompt: question text not defanged

- **What.** The question text and option labels go into the judge prompt with no fence and no defang, so an asker can forge an Owner block. The defang also skips case and spacing variants of the fence tokens, such as `<<<end>>>`.
- **Where.** `hooks/question_outcome.py`: the question and options lines near line 385, and `FENCE_TOKEN` near line 250.
- **Decision.** `question-outcome-check` (the AskUserQuestion judge and its context).
- **Retire.** Pass the question and labels through `_defang`, and match the tokens without regard to case or spacing. A test with a forged Owner block in the question, and one with `<<<end>>>`, shows each prompt holds exactly three Owner blocks.

# The Departs from word list misses some restatements

- **What.** `question-departs` reads a no-change word in the first clause of the change side. Restatements with other words pass: "remains", "is still", "no-op", "not changed", "the ask is kept".
- **Where.** `NO_CHANGE` and `departs_hit` in `hooks/question_form.py`.
- **Decision.** `port-keeps-behaviour` (a port keeps the existing app's behaviour; every owner question names what it changes from main).
- **Retire.** Add the synonyms, so each restatement in What is refused, in `hooks/test_question_form.py`.

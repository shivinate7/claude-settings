# The Departs from word list misses some restatements and refuses some changes

- **What.** `question-departs` reads a no-change word in the first clause of the change side. Restatements with other words pass: "remains", "is still", "no-op", "not changed", "the ask is kept". Real changes that open with a kept part are refused: "keeps Suspense cards and adds Reset", "none of the existing screens change; adds a new tab".
- **Where.** `NO_CHANGE` and `departs_hit` in `hooks/question_form.py`.
- **Decision.** `port-keeps-behaviour` (a port keeps the existing app's behaviour; every owner question names what it changes from main).
- **Retire.** Add the synonyms, and judge a leading no-change word or the whole side, so both lists above get the right verdict in `hooks/test_question_form.py`.

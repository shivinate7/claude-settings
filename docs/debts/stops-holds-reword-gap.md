# A reword of holds can drop an entry that stops names

- **What.** `stops_hit` judges a `set` and an `update` that carry `stops`, and passes an update or a `str_replace` that carries `holds` alone, since the stored `stops` is unseen. A normal rewording of `holds` can drop an entry that `stops` still lists, so the Blocking count and the words disagree. No incident yet; the reason is that ordinary rewording does it.
- **Where.** `hooks/question_form.py` `stops_hit`; its pinned case is `case_stops_str_replace_on_holds_is_a_known_gap` in `hooks/test_question_form.py`.
- **Decision.** question-form (one question form and one guard, for the chat box and the waiting page).
- **Retire.** The guard reads the stored `stops` for a write that changes `holds`, and refuses a write that leaves an entry unnamed. The pinned case is re-pointed to a refusal, red then green, in `hooks/test_question_form.py`.

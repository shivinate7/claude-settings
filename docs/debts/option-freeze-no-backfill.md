# An open waiting-page item from before the freeze has no ids and no shown list

**What.** Guard rule `option-letters-frozen` refuses every write of an open decision that carries `options` but no `shown` and no option ids. An item written before the rule has neither, so even a same-options re-send is refused until a session adds ids and `shown`. Claude hits this when it edits any old open item.

**Where.** `hooks/question_form.py`, `frozen_letters_hit`. The page has no step that adds ids and `shown` to open items.

**Decision.** option-keys-are-letters (ruling R60, roadmap r60).

**Retire.** One command or writer step adds a unique id per option and a `shown` list equal to the options to each open decision, without changing a key, label or position. A case in `hooks/test_question_form_letters_frozen.py` shows an old open item passes after it runs.

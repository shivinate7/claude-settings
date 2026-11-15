# An open waiting-page item from before the freeze has no ids and no shown list

**What.** Guard rule `option-letters-frozen` refuses every write of an open decision that carries `options` but no `shown` and no option ids. An item written before the rule has neither, so even a same-options re-send is refused until a session adds ids and `shown`. Claude hits this when it rewrites the options of an old open item.

A `set` of a legacy open decision is refused too. The copy-back step in `skills/waiting-page/reference/republish.md` (step 5, each batch entry is a `set`) hits this for an old open decision that carries no ids and no `shown`.

**Where.** `hooks/question_form.py`, `frozen_letters_hit`. The page has no step that adds ids and `shown` to open items.

**Decision.** option-keys-are-letters (ruling R60, roadmap r60).

**Retire.** One command or writer step adds a unique id per option and a `shown` list equal to the options to each open decision, without changing a key, label or position. A new case in `hooks/test_question_form_letters_frozen.py` runs the step on an old item and shows the item then passes the rule.

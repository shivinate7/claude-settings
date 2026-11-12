# A question that adds a field is refused for "no change"

**What.** `Departs from: adds a field (no change to existing rows)` is refused. The first clause of the change side holds "no change", so the rule reads the line as restating main. A new field is a real change.

**Where.** `hooks/question_form.py`, `departs_hit`.

**Decision.** cull-guard-wrong-refusals (the guard cull), which lists this gap.

**Retire.** Closed when a case in `hooks/test_question_form.py` passes a Departs from line that adds a field and names "no change" to existing rows.

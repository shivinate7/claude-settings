# The Departs-line ruling check cannot see a page edit's whole item

- **What.** `question_form.departs_ruling_hit` reads only the text a write carries. A `str_replace` on a page item's `context` is judged on `new_str` alone, so (a) an edit that rewrites a Departs line while the `Based on (ruling):` cite sits outside `new_str` is refused though it cites the ruling, and (b) an edit of only the change side, or an options-only update, skips the check. Both limits already hold on main for the form checks; this lane did not widen them.
- **Where.** `hooks/question_form.py` `page_units`; `hooks/call_judge.py` `main`. The hook cannot read the stored item (the Artifact tool is out of its reach).
- **Decision.** `question-form` (the one question form). Step `question-checks-rulings-first` built the check.
- **Retire.** Hit when a session's real page edit is refused for a cite it already has, or a covered question reaches the page through an edit. Fix: read the stored item through the page writer's save path, then judge the whole item. A test with a cite outside `new_str` goes green.

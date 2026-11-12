"""The widening sentences the judge tests pin: one home for hooks/test_call_judge.py and hooks/test_reply_judge.py.

Each sentence is held whole. A case passes only when the whole sentence is in the prompt, with case and spacing
ignored, so a dropped clause fails it, and no keyword list can stand in for it. The tests import these; none copies them.
"""

# Owner ruling on the widening scope: an option with no mark that adds to a shared allow-list or a second accepted
# form is widening, unless it says it applies to every repo. The scope may not turn on a stated motive alone, since
# an option that names no repo would then pass.
UNMARKED_OPTION_IS_WIDENING = ("an unmarked option that adds to a shared allow-list or a second accepted form counts "
                               "as widening unless it says it applies to every repo")
# Current wording of the exemption, pinned whole: its motive clause is part of the sentence.
SAME_CHANGE_IS_NOT_WIDENING = "a change made the same way for every repo, for every repo's sake, is not widening"
# Current wording of the definition in call_judge.py (WIDENING_TEMPLATE), pinned whole, motive clause included.
CALL_DEFINITION = ("widening is when the shared tool changes to fit one repo: it accepts a second form, an allow-list "
                   "entry or an exception for that repo's sake.")
# Current wording of the definition in reply_judge.py (the style-question-form line), pinned whole.
REPLY_DEFINITION = ("meaning the tool changes to fit one repo: it accepts a second form, an allow-list entry or an "
                    "exception for that repo's sake.")


def in_text(sentence, text):
    """True when `sentence` is in `text` whole, with case and any run of spaces ignored."""
    return " ".join(sentence.lower().split()) in " ".join((text or "").lower().split())

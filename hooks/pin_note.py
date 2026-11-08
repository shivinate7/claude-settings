"""The one home of the pin note's two names (decision action-pins-follow-sessions).

ENV: bin/ci-job sets it to 1 for its ste-lint step only; bin/ste-changed reads it, and then a drifted pin is a note, not exit 3.
MARKER: the text that starts each drift line bin/ste-changed prints under ENV. bin/ci-job reads those lines back from the step's
log into its PASS line, and merge/merge.py reads them from ci-job's stdout. Standard library only, no side effect.
"""

ENV = "STE_CHANGED_PIN_NOTE"
MARKER = "ste-changed: pin note: "

"""The one home of the sha pin of this repo's actions (decision action-pins-follow-sessions).

pin_regex(actions) matches `<owner>/claude-settings/actions/<action>@<40-hex sha>` for the named actions; group 1 is the
action, group 2 the sha. bin/ste-changed finds the pins of a workflow with it, bin/ci-job reads a step's uses: with it.
Standard library only, no side effect.
"""
import re


def pin_regex(actions):
    return re.compile(r"[\w.-]+/claude-settings/actions/(%s)@([0-9a-f]{40})" % "|".join(map(re.escape, actions)))

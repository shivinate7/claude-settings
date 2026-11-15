"""The one home of the pin of this repo's actions (decision action-pins-follow-sessions).

pin_regex(actions) matches `<owner>/claude-settings/actions/<action>@<40-hex sha>` for the named actions; group 1 is the
action, group 2 the sha. With moving=True group 2 is any ref (a sha, or a branch or tag such as the stable branch CI pins);
is_sha(ref) tells the two apart. bin/ste-changed finds the sha pins of a workflow with it, bin/ci-job reads a step's uses:
with it. Standard library only, no side effect.
"""
import re

SHA = re.compile(r"[0-9a-f]{40}")


def is_sha(ref):
    return bool(SHA.fullmatch(ref))


def pin_regex(actions, moving=False):
    return re.compile(r"[\w.-]+/claude-settings/actions/(%s)@(%s)" % ("|".join(map(re.escape, actions)),
                                                                      r"[\w.+/-]+" if moving else SHA.pattern))

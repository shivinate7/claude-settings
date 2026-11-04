"""The one home of the name of the one required check: the all-jobs-passed rollup (actions/all-jobs-passed).

Decision same-check-kinds: branch protection requires this one check. merge/merge.py (the draft run skips it) and
skills/project-ops/scripts/protect.py (it refuses any other name) both import it. Standard library only, no side effect.
"""

REQUIRED_CHECK = "all-jobs-passed"

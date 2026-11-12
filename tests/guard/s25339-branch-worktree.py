# section 25339
FAMILY = "branch-worktree"
for _label, _check in (
        ("git_reads: branch_is_ancestor reads True for an ancestor", git_reads_ancestor_true_case),
        ("git_reads: branch_is_ancestor reads False for a full clone's non-ancestor", git_reads_ancestor_false_case),
        ("git_reads: branch_is_ancestor reads None for an unknown revision", git_reads_ancestor_unknown_rev_case),
        ("git_reads: branch_is_ancestor reads None, not False, in a shallow clone that cuts the path",
         git_reads_ancestor_shallow_case),
        ("git_reads: origin_slug reads None for a one-segment origin (https://host/r)", git_reads_origin_one_segment_case),
        ("branch delete, shallow clone: the only copy is denied", git_reads_branch_only_copy_shallow_case),
        ("branch delete, shallow clone: the on-remote proof allows", git_reads_branch_on_remote_shallow_case)):
    FIXTURELESS_CHECKS.add(_check)
    LOG_CHECKS_EXTRA.append((_label, _check))


# --------------------------------------------------------------------------- a port question departs or is not asked

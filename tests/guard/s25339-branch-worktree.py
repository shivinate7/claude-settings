# section 25339
FAMILY = "branch-worktree"
for _label, _check in (
        ("git_reads: branch_is_ancestor reads True for an ancestor", git_reads_ancestor_true_case),
        ("git_reads: branch_is_ancestor reads False for a full clone's non-ancestor", git_reads_ancestor_false_case),
        ("git_reads: branch_is_ancestor reads None for an unknown revision", git_reads_ancestor_unknown_rev_case),
        ("git_reads: branch_is_ancestor reads None, not False, in a shallow clone that cuts the path",
         git_reads_ancestor_shallow_case),
        ("git_reads: origin_slug reads None for a one-segment origin (https://host/r)", git_reads_origin_one_segment_case),
        ("git_reads: origin_slug reads a backslash Windows drive origin as a path", git_reads_origin_windows_drive_case),
        ("git_reads: origin_slug reads a C:/ origin with backslashes as a path", git_reads_origin_drive_mixed_separators_case),
        ("branch delete, shallow clone: the only copy is denied", git_reads_branch_only_copy_shallow_case),
        ("branch delete, shallow clone: the on-remote proof allows", git_reads_branch_on_remote_shallow_case)):
    FIXTURELESS_CHECKS.add(_check)
    LOG_CHECKS_EXTRA.append((_label, _check))
# The forced-remove check of the stale-record case in section 3975 reads the fixture WTSTALECFG (built in section 442),
# so it stays out of FIXTURELESS_CHECKS and runs with the fixture build.
LOG_CHECKS_EXTRA.append(("log: a forced remove of a clean tree, with a removed record folder, is allowed and not noted",
                         stale_record_forced_remove_quiet_case))
LOG_CHECKS_EXTRA.append(("log: a forced remove, a record under an absent parent, is noted as unconfirmed",
                         stale_record_parent_gone_forced_remove_noted_case))
# The process cases of section 3975 read the fixture WTCLEAN (built in section 442), so they stay out of
# FIXTURELESS_CHECKS and run with the fixture build. The three live-process cases start a sleep child; the two
# read-failure cases copy the guard instead.
LOG_CHECKS_EXTRA.append(("log: a live process in a clean tree refuses the remove when its record's folder is gone",
                         stale_record_live_process_in_tree_case))
LOG_CHECKS_EXTRA.append(("log: a live process outside a clean tree allows the remove when a record's folder is gone",
                         stale_record_process_outside_tree_case))
LOG_CHECKS_EXTRA.append(("log: a gone record beside a live record in a clean tree still refuses the remove",
                         stale_record_beside_live_record_case))
LOG_CHECKS_EXTRA.append(("log: a process read that raises refuses the remove when a record's folder is gone",
                         stale_record_process_read_fails_refused_case))
LOG_CHECKS_EXTRA.append(("log: a process read that finds nothing allows the remove when a record's folder is gone",
                         stale_record_process_read_empty_allowed_case))


# --------------------------------------------------------------------------- a port question departs or is not asked

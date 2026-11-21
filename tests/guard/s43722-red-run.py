# section 43722
FAMILY = "worktree-home"
# The red-run command, called plainly by an agent from its own worktree, is allowed. Rule 0 (worktree-home) and the
# other-checkout rule judge its cwd and the folders its words name; the scratchpad-owner rule reads a run word only
# when its path is a scratchpad file, so bin/red-run (a repo path) and the test path after `--` pass it. These rows
# reuse the agent-home fixture of section 32594 (_gcx_fixture, _gcx_row), so no fixture is copied here. An allow row is
# a pin, not a red: the old guard already allows these calls, so each row guards against a later false alarm.
RED_RUN_SHA = "9f2c1d0a7b3e4f5061728394a5b6c7d8e9f01234"  # a commit's sha, as the test-author names it
RED_RUN_TEST = "python3 lint/test_check_red_run.py"
# Late sections join LOG_CHECKS directly: LOG_CHECKS_EXTRA joined in section 40805, and a later append is in no run.
RED_RUN_CHECKS = (
    ("red-run: an agent's plain bin/red-run call from its own worktree is allowed",
     _gcx_row("allow", "home", "bin/red-run " + RED_RUN_SHA + " -- " + RED_RUN_TEST)),
    ("red-run: an agent's bin/red-run call with --add of its own test file is allowed",
     _gcx_row("allow", "home", "bin/red-run " + RED_RUN_SHA + " --add lint/test_red_run.py -- " + RED_RUN_TEST)),
    ("red-run: an agent's bin/red-run call with --replace of a repo file is allowed",
     _gcx_row("allow", "home", "bin/red-run " + RED_RUN_SHA + " --replace src/app.py \"return 1\" \"return 2\" -- "
              + RED_RUN_TEST)),
)
for _label, _check in RED_RUN_CHECKS:
    LOG_FAMILY[_label] = FAMILY
LOG_CHECKS = LOG_CHECKS + RED_RUN_CHECKS

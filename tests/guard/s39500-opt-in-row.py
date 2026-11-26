# section 39500
# The opt-in row: a run that names no family prints one SKIP row for each opt-in family, and the row
# gives the command that runs the family. Each check runs this runner in a child on a copy of the section files, with
# GUARD_SHARD set past the end of any selection, so the child prints its rows and runs no case or check. The checks sit
# in their own section, with no fixtureless reference, so the red run can copy this file onto an older commit.

OPT_IN_ROW = ("SKIP  fixtureless  (opt-in family, not run unless named: "
              "GUARD_FAMILY=fixtureless python3 hooks/test_guard.py)")
OPT_IN_NONE_LABEL = "opt-in family: a run that names no family prints one SKIP row with the command that runs it"
OPT_IN_NAMED_LABEL = "opt-in family: a run that names the family runs its check and prints no SKIP row"
OPT_IN_EMPTY_SHARD = "100000/100000"  # a shard number past the end of any selection, so the shard holds nothing


def opt_in_child(family):
    """This runner in a child on a copy of the section files, under `family` (None names none), in the empty shard.
    -> (rc, output), rc None when the child does not end in 300 s."""
    folder = tempfile.mkdtemp(dir=ROOT)
    build_with_extra("s39499-empty.py", "# section 39499\n")(folder)
    return section_child_run(folder, family=family, extra_env={"GUARD_SHARD": OPT_IN_EMPTY_SHARD})


def opt_in_none_check():
    rc, out = opt_in_child(None)
    if rc is None:
        return False, "the run that names no family did not end within 300 s"
    rows = [line for line in out.splitlines() if line.rstrip() == OPT_IN_ROW]
    if len(rows) != 1:
        return False, "the run that names no family printed the opt-in row %d times, want 1" % len(rows)
    return True, "one opt-in row, and it gives the command that runs the family"


def opt_in_named_check():
    rc, out = opt_in_child("fixtureless")
    if rc is None:
        return False, "the run that names the family did not end within 300 s"
    if "GUARD_FAMILY=fixtureless: " not in out:
        return False, "the run that names the family did not print its selection line"
    if "SKIP  fixtureless" in out:
        return False, "the run that names the family still printed the opt-in row"
    return True, "the run that names the family prints no opt-in row"


for _label, _check in ((OPT_IN_NONE_LABEL, opt_in_none_check), (OPT_IN_NAMED_LABEL, opt_in_named_check)):
    LOG_CHECKS_EXTRA.append((_label, _check))
    LOG_FAMILY[_label] = "sections"
    FIXTURELESS_CHECKS.add(_check)

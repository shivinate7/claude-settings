# section 21306
FAMILY = "conflict-markers"

# THE CRASH FALLBACK OF CONFLICT-MARKERS. A crash in the cd walk gives no folder, so conflict-markers judges the
# commit in command_root's folder, the last cd. The commit runs from a folder that is no repository, so only that
# fallback reaches the triplet repo. The intact copy is the control. Each failure names one cause.
CMK_CRASH_LABEL = ("conflict-markers: a crash in the cd walk falls back to the last cd, so a commit after a cd into a "
                   "triplet repo, run from a folder that is no repository, is refused, and the crash is logged")

def conflict_markers_crash_check():
    folder = os.path.join(ROOT, "cmk-crash")
    shutil.rmtree(folder, ignore_errors=True)
    nogit = os.path.join(folder, "nogit")
    os.makedirs(nogit)
    guards, cause = planted_cd_walk_guards(folder)
    if guards is None:
        return False, cause
    command = "cd %s; %s commit -m x" % (slash(CMK_STAGED), VCS)
    control, reason, _log = planted_verdict(guards, folder, "intact", command, nogit)
    if control != "deny" or CMK_RULE not in reason:
        return False, "control: the intact copy's verdict on the triplet commit is %r, want deny by %s" % (control, CMK_RULE)
    decision, reason, logged = planted_verdict(guards, folder, "planted", command, nogit)
    if "guard-crash" not in logged or "planted walk fault" not in logged:
        return False, "the plant did not fire: no guard-crash line in the log, so the fallback was not read"
    if decision != "deny":
        return False, "the planted copy's verdict on the triplet commit is %r, want deny" % decision
    if CMK_RULE not in reason:
        return False, "the planted deny is not the conflict-markers rule: %r" % reason[:90]
    return True, "a crash in the cd walk falls back to the last cd, and the triplet commit is refused by conflict-markers"

# The conflict-markers crash check reads the triplet fixture CMK_STAGED, so it is not fixtureless: the run builds it.
LOG_CHECKS_EXTRA.append((CMK_CRASH_LABEL, conflict_markers_crash_check))

LOG_FAMILY[CMK_CRASH_LABEL] = "conflict-markers"

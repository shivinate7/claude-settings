# section 43014
#
# Cases for the folder of a wrapped script segment (judge_shell rule 1, hooks/guard.py) when one wrapper text runs
# twice, and for a `git -C` inside a wrapper, which reads its folder from the folder the wrapper runs in. The
# fixtures are those of section 43011: a dirty checkout (SUBJDIRTY), a clean checkout (SUBJCLEAN), and a reset --hard,
# with the twin folder below for the `git -C` cases.
FAMILY = "shared-tree"
materialize(SUBJDIRTY)
materialize(SUBJCLEAN)

# A folder holding the subject names with the opposite state. The `git -C` cases below run from it, so a read
# against the call's cwd lands on a tree whose state is the reverse of the subject's.
TWINDIR = os.path.join(ROOT, "cwdtwin")
TWINCLEAN = os.path.join(TWINDIR, os.path.basename(SUBJDIRTY))  # clean, under the dirty subject's name
TWINDIRTY = os.path.join(TWINDIR, os.path.basename(SUBJCLEAN))  # dirty, under the clean subject's name


def _build_twins():
    make_repo(TWINCLEAN, {"f.txt": "base\n", "keep.txt": "base\n"})
    _require_clean(TWINCLEAN)
    make_repo(TWINDIRTY, {"f.txt": "base\n", "keep.txt": "base\n"})
    write(os.path.join(TWINDIRTY, "f.txt"), "uncommitted\n")
    write(os.path.join(TWINDIRTY, "new.txt"), "untracked\n")
    _require_dirty(TWINDIRTY, "f.txt", "new.txt", "keep.txt")


lazy_fixture([TWINDIR], _build_twins)
materialize(TWINDIR)

# The discarding write, and the wrapper that runs it. The two calls below repeat the wrapper text.
WRAPPED = "sh -c '" + VCS + " reset --hard HEAD'"

# A REPEATED WRAPPER TEXT TAKES ITS FOLDERS IN ORDER. The first run is after a cd to the clean folder, the second
# after a cd to the dirty folder. The second run is the discard, so the call denies.
sh("cd-walk: a repeated sh -c reset, first after a cd to a clean folder, then after a cd to a dirty one, denies",
   "cd " + slash(SUBJCLEAN) + "; " + WRAPPED + "; cd " + slash(SUBJDIRTY) + "; " + WRAPPED,
   "deny", "shared-tree", cwd=NOGIT)
# The reverse order. The first run is the discard in the dirty folder, so the call denies.
sh("cd-walk: a repeated sh -c reset, first after a cd to a dirty folder, then after a cd to a clean one, denies",
   "cd " + slash(SUBJDIRTY) + "; " + WRAPPED + "; cd " + slash(SUBJCLEAN) + "; " + WRAPPED,
   "deny", "shared-tree", cwd=NOGIT)

# A `git -C` INSIDE A WRAPPER READS ITS FOLDER AGAINST THE FOLDER THE WRAPPER RUNS IN. The subject is named by its
# basename, relative to ROOT. The call's cwd is TWINDIR, which holds the same names with the opposite state.
sh("cd-walk: a sh -c reset with git -C into a dirty folder, after a cd to the folder above it, denies",
   "cd " + slash(ROOT) + " && sh -c '" + VCS + " -C " + os.path.basename(SUBJDIRTY) + " reset --hard HEAD'",
   "deny", "shared-tree", cwd=TWINDIR)
# GREEN. The same shape on the clean checkout: a reset of a clean tree is allowed.
sh("cd-walk: a sh -c reset with git -C into a clean folder, after the same cd, allows",
   "cd " + slash(ROOT) + " && sh -c '" + VCS + " -C " + os.path.basename(SUBJCLEAN) + " reset --hard HEAD'",
   "allow", cwd=TWINDIR)

# section 4769
FAMILY = "pointer-edit"
FAMILIES["pointer-edit"] = "the pointer checkout's own files: a Write, Edit, MultiEdit or NotebookEdit into them is refused, naming EnterWorktree; its .git, a linked worktree, a target outside it, a stood-down pointer and the read tools pass"
#
# Rule pointer-edit: a Write, Edit, MultiEdit or NotebookEdit whose TARGET is one of the pointer
# checkout's own files is refused, and the remedy names the EnterWorktree tool. Every session on this
# machine runs its hooks, its lint and its agents out of that checkout, so a file edited in it is live
# for all of them at once. pointer-head guards a branch switch there and nothing else.
#
# The rule reads the TARGET path, never the cwd. Its passes are the pointer's own `.git`, a linked
# worktree of the same clone (nested under the pointer, or elsewhere), and any target outside the
# pointer. A rules file that is missing, unreadable or names no pointer stands the rule down. Read,
# Grep, Artifact and ArtifactData are never judged: the gate is WRITE_TOOLS. A shell write into the
# pointer is out of scope: a note only.
#
# The targets are plain fixture files, never the pointer's CLAUDE.md or anything under hooks/, lint/ or
# agents/. frozen-path judges those only for the config-dir spelling, or when the pointer is the live pin
# or the main mirror, so these cases must not depend on it. TEMP_DIR is ROOT/tmp for this section, as in the
# hand-made-worktree section below, so ROOT under the system temp is not read as temp.
TEMP_DIR = os.path.join(ROOT, "tmp")
PE_TARGET = os.path.join(PTRMAIN, "f.txt")                       # a tracked file of the pointer checkout
PE_NEW = os.path.join(PTRMAIN, "docs", "brand-new.md")           # a file the pointer does not hold yet
PE_NOTEBOOK = os.path.join(PTRMAIN, "docs", "scratch.ipynb")     # a notebook path in the pointer
PE_TEMP = os.path.join(TEMP_DIR, "probe.txt")                    # a file in the guard's temp folder
PE_GITDIR = os.path.join(PTRMAIN, ".git", "pointer-edit-probe")  # inside the pointer's own .git
# Under the directory PTRGONECFG names, which the fixture never creates. Its stand-down is the only
# thing that passes this write: with the directory taken as the pointer, the target is inside it.
PE_GONE_TARGET = os.path.join(ROOT, "nosuchcheckout", "f.txt")

# THE DENY CASES. Each names the pointer itself as cwd, except the last, from a directory that is no
# checkout, which proves the TARGET decides. Each reason must carry the EnterWorktree tool. Each stand-
# down case below names the same target under a stood-down config, so the pair pins the cause.
add("pointer-edit: Write of a tracked file in the pointer checkout is refused", "deny", "pointer-edit",
    tool="Write", cwd=PTRMAIN, config=PTRCFG, file_path=PE_TARGET, content="changed\n",
    carries="EnterWorktree")
add("pointer-edit: Edit of a tracked file in the pointer checkout is refused", "deny", "pointer-edit",
    tool="Edit", cwd=PTRMAIN, config=PTRCFG, file_path=PE_TARGET, old_string="base",
    new_string="changed", carries="EnterWorktree")
add("pointer-edit: MultiEdit of a tracked file in the pointer checkout is refused", "deny", "pointer-edit",
    tool="MultiEdit", cwd=PTRMAIN, config=PTRCFG, file_path=PE_TARGET,
    edits=[{"old_string": "base", "new_string": "changed"}], carries="EnterWorktree")
add("pointer-edit: NotebookEdit into the pointer checkout is refused", "deny", "pointer-edit",
    tool="NotebookEdit", cwd=PTRMAIN, config=PTRCFG, notebook_path=PE_NOTEBOOK, new_source="x = 1\n",
    carries="EnterWorktree")
add("pointer-edit: Write of a new file in the pointer checkout is refused", "deny", "pointer-edit",
    tool="Write", cwd=PTRMAIN, config=PTRCFG, file_path=PE_NEW, content="# new\n",
    carries="EnterWorktree")
add("pointer-edit: Write into the pointer checkout from a directory that is no checkout is refused",
    "deny", "pointer-edit", tool="Write", cwd=NOGIT, config=PTRCFG, file_path=PE_TARGET,
    content="changed\n", carries="EnterWorktree")

# THE PASSES. Each pins a write or read the rule must let through: the pointer's own .git, a linked
# worktree (nested or elsewhere), another checkout, the temp folder, a directory that is no checkout,
# a stood-down rule, and the read tools. A refusal here would block a lane's own work.
# The nested worktree's scope (its own git directory) is checked where the fixture is built.
add("pointer-edit: Write into the pointer's own .git is not judged", "allow", tool="Write",
    cwd=PTRMAIN, config=PTRCFG, file_path=PE_GITDIR, content="probe\n")
add("pointer-edit: Write into a linked worktree nested under the pointer is allowed", "allow",
    tool="Write", cwd=PTRNEST, config=PTRCFG, file_path=os.path.join(PTRNEST, "f.txt"), content="lane\n")
add("pointer-edit: Write into a linked worktree elsewhere is allowed", "allow", tool="Write",
    cwd=PTRWT, config=PTRCFG, file_path=os.path.join(PTRWT, "f.txt"), content="lane\n")
add("pointer-edit: Write into another checkout is allowed", "allow", tool="Write",
    cwd=GITMAIN, config=PTRCFG, file_path=os.path.join(GITMAIN, "notes.txt"), content="x\n")
add("pointer-edit: Write into the temp folder is allowed, with the pointer as cwd", "allow",
    tool="Write", cwd=PTRMAIN, config=PTRCFG, file_path=PE_TEMP, content="x\n")
add("pointer-edit: Write into a directory that is no checkout is allowed", "allow", tool="Write",
    cwd=NOGIT, config=PTRCFG, file_path=os.path.join(NOGIT, "notes.txt"), content="x\n")
add("pointer-edit: a rules file with no pointer line stands the rule down", "allow", tool="Write",
    cwd=PTRMAIN, config=PTRBADCFG, file_path=PE_TARGET, content="changed\n")
add("pointer-edit: a pointer naming a directory that is gone stands the rule down", "allow",
    tool="Write", cwd=PTRMAIN, config=PTRGONECFG, file_path=PE_GONE_TARGET, content="changed\n")
add("pointer-edit: no global rules file at all stands the rule down", "allow", tool="Write",
    cwd=PTRMAIN, config=PTRNOCFG, file_path=PE_TARGET, content="changed\n")
add("pointer-edit: Read of a file in the pointer checkout is never judged", "allow", tool="Read",
    cwd=PTRMAIN, config=PTRCFG, file_path=PE_TARGET)
add("pointer-edit: Grep under the pointer checkout is never judged", "allow", tool="Grep",
    cwd=PTRMAIN, config=PTRCFG, pattern="base", path=PTRMAIN)
# The gate is WRITE_TOOLS. Artifact and ArtifactData reach the guard with a file_path too, so they
# must be named here: a gate dropped to every tool would refuse them, and these cases go red.
add("pointer-edit: Artifact with a pointer file as file_path is not a write and is allowed", "allow",
    tool="Artifact", cwd=PTRMAIN, config=PTRCFG, file_path=PE_TARGET)
add("pointer-edit: ArtifactData with a pointer file as file_path is not a write and is allowed", "allow",
    tool="ArtifactData", cwd=PTRMAIN, config=PTRCFG, file_path=PE_TARGET)

TEMP_DIR = None   # back to the system temp for the sections below


# =========================================================================== 1c. hand-made worktree

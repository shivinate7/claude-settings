# section 2747
FAMILY = "shared-tree"
#
# TRAPLN holds one real directory, a link to it, a file and a link to it.
TRAPLN = os.path.join(ROOT, "trapln")


def build_trap_fixtures():
    os.makedirs(os.path.join(TRAPLN, "realdir"))
    write(os.path.join(TRAPLN, "file.txt"), "x\n")
    if LINKS_MADE:
        os.symlink("realdir", os.path.join(TRAPLN, "linkdir"))
        os.symlink("file.txt", os.path.join(TRAPLN, "linkfile"))


build_trap_fixtures()
_mark("build_trap_fixtures, DOTDOTWT and SYMWT")
beat("trap fixtures at import")

CFG_SETTINGS = slash(os.path.join(CFG, "settings.json"))
CFG_CLAUDEMD = slash(os.path.join(CFG, "CLAUDE.md"))
CFG_HOOK = slash(os.path.join(CFG, "hooks", "guard.py"))
CFG_LINT = slash(os.path.join(CFG, "lint", "prose.py"))
CFG_AGENT = slash(os.path.join(CFG, "agents", "builder.md"))
# A skill this repo ships (frozen) and one it does not (a person's own, never frozen).
CFG_SKILL = slash(os.path.join(CFG, "skills", "fresh-prose", "SKILL.md"))
CFG_OWN_SKILL = slash(os.path.join(CFG, "skills", "my-own", "SKILL.md"))
# The baseline store `hooks/config_watch.py` restores from. A session that could rewrite the
# baseline could launder a cap lift into it, so it is frozen on the same terms as the hooks.
CFG_STATE = slash(os.path.join(CFG, "state", "config-watch", "entry.json"))
PROJ_SETTINGS = slash(os.path.join(PROJ, ".claude", "settings.json"))
PROJ_LOCAL = slash(os.path.join(PROJ, ".claude", "settings.local.json"))
PROJ_HOOK = slash(os.path.join(PROJ, ".claude", "hooks", "g.py"))
PROJ_HOOKDIR = slash(os.path.join(PROJ, ".claude", "hooks"))
CLONE_SETTINGS = slash(os.path.join(CLONE, "settings.json"))
PY_PATH = os.path.dirname(sys.executable)


def _program_folder(name):
    """The folder that holds `name`, found on this process's own PATH. A raise when there is none: a case that needs the program on the
    guard's narrow PATH cannot run without it."""
    found = shutil.which(name, path=os.environ.get("PATH"))
    if not found:
        raise RuntimeError("test_guard: %r is not on this process's PATH, and the cases that read the current branch need it on the guard's" % name)
    return os.path.dirname(found)


# c53: a merge that names no pull request reads the branch of the working directory, so Host.pr_number runs `git rev-parse` (the old
# `gh pr view` ran git itself). The guard's narrow PATH is the fake gh's folder and the interpreter's, and on CI the interpreter's folder
# (the toolcache) has no git: those cases add git's own folder.
GIT_PATH = _program_folder(VCS)


# =========================================================================== 1. shared trees
#
# Ported from job-cost-reporting harness/test_guard.py. The cases about that repository's read-only
# folder and its workbook binaries are left behind, because they are its own rules.
#
# In a directory that is not a git tree the rule denies, which is the fail-closed half: an unknown
# tree is not a safe tree.

sh("stash: set work aside in a shared tree", VCS + " stash push -u -m lane", "deny", "shared-tree",
   cwd=NOGIT)
sh("stash: a bare stash pushes, same as `stash push`", VCS + " stash", "deny", "shared-tree",
   cwd=NOGIT)
sh("stash: save is the old name for push", VCS + " stash save lane", "deny", "shared-tree",
   cwd=NOGIT)
sh("stash: drop destroys stashed work with no way back", VCS + " stash drop", "deny",
   "shared-tree", cwd=NOGIT)
sh("stash: clear destroys every stash with no way back", VCS + " stash clear", "deny",
   "shared-tree", cwd=NOGIT)
# `list` and `show` only read the stack, so they allow everywhere. Every other action takes an
# entry OFF the stack, and the stack belongs to the whole clone, so each one denies here. Owner's
# ruling, 2026-09-19: the old exemption for `apply` and `pop` read the wrong subject. Git does
# refuse to overwrite a modified file, which the old note MEASURED on 2026-09-17, but the thing
# at risk is the shared entry, not this tree.
sh("stash: list only reads, no subcommand match", VCS + " stash list", "allow", cwd=NOGIT)
sh("stash: show only reads", VCS + " stash show", "allow", cwd=NOGIT)
sh("stash: apply takes an entry off a stack the whole clone shares", VCS + " stash apply", "deny",
   "shared-tree", cwd=NOGIT)
sh("stash: pop consumes the entry it applies", VCS + " stash pop stash@{0}", "deny",
   "shared-tree", cwd=NOGIT)
sh("stash: branch consumes the entry it builds from", VCS + " stash branch lane", "deny",
   "shared-tree", cwd=NOGIT)
sh("reset: throws the tree away", VCS + " reset --hard origin/main", "deny", "shared-tree",
   cwd=NOGIT)
sh("reset: --hard with no argument", VCS + " reset --hard", "deny", "shared-tree", cwd=NOGIT)
# The Monitor tool's command gets the Bash verdict (see monitor() in the fixtures section).
monitor("Monitor: reset throws the tree away, as in Bash", VCS + " reset --hard origin/main",
        "deny", "shared-tree")
# A bare reset, `--soft` and `--mixed` leave the working tree alone, and `--hard` rewrites it.
# `--merge` rewrites it too: it reverts a staged edit and deletes a staged new file. `--keep` and
# `--merge` both move the branch at another commit, so they take `--hard`'s verdict.
sh("reset: a plain reset only unstages, the working tree is untouched", VCS + " reset HEAD~1",
   "allow", cwd=NOGIT)
sh("reset: a bare reset with no argument", VCS + " reset", "allow", cwd=NOGIT)
sh("reset: an explicit mixed reset", VCS + " reset --mixed HEAD~1", "allow", cwd=NOGIT)
sh("reset: a soft reset moves the branch and touches nothing else", VCS + " reset --soft HEAD~1",
   "allow", cwd=NOGIT)
sh("reset: --keep at another commit refuses where there is no git tree",
   VCS + " reset --keep HEAD~1", "deny", "shared-tree", cwd=NOGIT)
sh("reset: --merge at another commit refuses where there is no git tree",
   VCS + " reset --merge HEAD~1", "deny", "shared-tree", cwd=NOGIT)
sh("reset: a reset naming a path only touches the index",
   VCS + " reset -- app/src/50_engine.js", "allow", cwd=NOGIT)
sh("reset: a reset at a commit naming a path only touches the index",
   VCS + " reset HEAD~1 -- app/src/50_engine.js", "allow", cwd=NOGIT)
sh("restore: overwrites a file", VCS + " restore app/src/50_engine.js", "deny", "shared-tree",
   cwd=NOGIT)
sh("restore: the whole tree", VCS + " restore .", "deny", "shared-tree", cwd=NOGIT)
sh("restore: staged and worktree together", VCS + " restore --staged --worktree src/jobStore.ts",
   "deny", "shared-tree", cwd=NOGIT)
sh("restore: the worktree flag alone still overwrites the file",
   VCS + " restore --worktree src/jobStore.ts", "deny", "shared-tree", cwd=NOGIT)
# `--staged` alone writes only the index. The working tree file is left as it was (MEASURED
# against a real uncommitted change, 2026-09-17).
sh("restore: staged alone only touches the index", VCS + " restore --staged src/jobStore.ts",
   "allow", cwd=NOGIT)
sh("restore: the short staged flag alone only touches the index",
   VCS + " restore -S src/jobStore.ts", "allow", cwd=NOGIT)
sh("checkout: a path after the double dash", VCS + " checkout -- app/src/50_engine.js", "deny",
   "shared-tree", cwd=NOGIT)
sh("checkout: a start point and a path", VCS + " checkout HEAD app/src/50_engine.js", "deny",
   "shared-tree", cwd=NOGIT)
sh("checkout: a folder", VCS + " checkout docs/", "deny", "shared-tree", cwd=NOGIT)
sh("checkout: the working directory", VCS + " checkout .", "deny", "shared-tree", cwd=NOGIT)
sh("checkout: a relative path", VCS + " checkout ./x", "deny", "shared-tree", cwd=NOGIT)
sh("checkout: HEAD and the double dash", VCS + " checkout HEAD -- CLAUDE.md", "deny",
   "shared-tree", cwd=NOGIT)
sh("checkout: an older commit and a path", VCS + " checkout HEAD~1 -- src/utils/benchmark.ts",
   "deny", "shared-tree", cwd=NOGIT)
sh("checkout: a branch and a path", VCS + " checkout main -- harness/check-invariants.mjs", "deny",
   "shared-tree", cwd=NOGIT)
sh("checkout: a named file", VCS + " checkout -- README.md", "deny", "shared-tree", cwd=NOGIT)

# PICKING A CONFLICT SIDE is not a discard. `--theirs` (or `--ours`, or `--merge`) resolves one
# side of an existing conflict; the tree is already left open by git itself, which will not let a
# commit go through silently. Built with a REAL merge conflict, never mocked, the same way the
# worktree cases above use a real checkout.
sh("checkout: --theirs resolves a real, unresolved merge conflict",
   VCS + " checkout --theirs docs/DEBTS.md", "allow", cwd=CONFLICT, silent=True)
# GITMAIN carries a real uncommitted change to this same file, so the call has a subject to
# destroy and the case is still about the missing conflict, not about an empty tree.
sh("checkout: the same call with no conflict in progress keeps today's decision",
   VCS + " checkout --theirs docs/DEBTS.md", "deny", "shared-tree", cwd=GITMAIN)
sh("checkout: a path with no conflict-side flag still denies, even in the conflicted tree",
   VCS + " checkout -- docs/DEBTS.md", "deny", "shared-tree", cwd=CONFLICT)
sh("checkout: a branch and a path still denies, even in the conflicted tree",
   VCS + " checkout main -- docs/", "deny", "shared-tree", cwd=CONFLICT)

# THE SUBJECT READ, BOTH SIDES OF EVERY ARM. The rule reads what the call would TAKE, with the
# two reads git itself makes: `git status --porcelain` for a working-tree subject and `git stash
# list` for a stack subject. An empty subject passes, and a non-empty subject is refused exactly
# as before. Every fixture below is real state, asserted in build_fixtures: SUBJCLEAN is a clean
# tree with no stash, SUBJDIRTY holds a modified `f.txt`, an untracked `new.txt`, and a clean
# tracked `keep.txt`, and SUBJSTASH holds one stash entry over a clean tree.
sh("subject: a hard reset in a clean tree takes nothing", VCS + " reset --hard HEAD", "allow",
   cwd=SUBJCLEAN)
sh("subject: a hard reset over a real uncommitted change still denies", VCS + " reset --hard HEAD",
   "deny", "shared-tree", cwd=SUBJDIRTY)
sh("subject: a bare hard reset in a clean tree takes nothing", VCS + " reset --hard", "allow",
   cwd=SUBJCLEAN)
sh("subject: a bare hard reset in a clean worktree takes nothing", VCS + " reset --hard", "allow",
   cwd=SUBJCLEANWT)
sh("subject: a hard reset at HEAD in a clean worktree takes nothing",
   VCS + " reset --hard HEAD", "allow", cwd=SUBJCLEANWT)
# A `reset --hard` THAT NAMES ANOTHER COMMIT also moves the branch. Another session standing in
# that checkout is then on rewritten history, and the reflog that recovers the commit belongs to
# the tree that ran the reset, not to theirs. So a clean tree is NOT a pass for these forms, and
# the deny-or-ask split stays: deny in the shared checkout, ask in the worktree.
sh("subject: a hard reset one commit back moves the branch, clean tree or not",
   VCS + " reset --hard HEAD~1", "deny", "shared-tree", cwd=SUBJCLEAN)
sh("subject: the same reset in a clean worktree asks", VCS + " reset --hard HEAD~1", "ask",
   "shared-tree", cwd=SUBJCLEANWT)
sh("subject: a hard reset at a remote branch moves the branch", VCS + " reset --hard origin/main",
   "deny", "shared-tree", cwd=SUBJCLEAN)
sh("subject: a hard reset at a raw sha moves the branch",
   VCS + " reset --hard 380d5fca1b2c3d4e5f60718293a4b5c6d7e8f901", "deny", "shared-tree",
   cwd=SUBJCLEAN)
sh("subject: a hard reset at a raw sha in a clean worktree asks",
   VCS + " reset --hard 380d5fca1b2c3d4e5f60718293a4b5c6d7e8f901", "ask", "shared-tree",
   cwd=SUBJCLEANWT)
sh("subject: a quiet hard reset at HEAD is still a pass in a clean tree",
   VCS + " reset -q --hard HEAD", "allow", cwd=SUBJCLEAN)
# THE `--merge` AND `--keep` FORMS TAKE `--hard`'s VERDICT. Each form has its own deny or ask line,
# so dropping either flag alone turns a line red. SUBJSTAGED holds a staged edit and a staged new
# file, so any change denies.
sh("reset: --merge at HEAD over a staged edit and a staged new file refuses",
   VCS + " reset --merge HEAD", "deny", "shared-tree", cwd=SUBJSTAGED)
sh("reset: a bare --merge over a staged edit refuses", VCS + " reset --merge", "deny",
   "shared-tree", cwd=SUBJSTAGED)
sh("reset: --merge at HEAD in a clean tree takes nothing", VCS + " reset --merge HEAD", "allow",
   cwd=SUBJCLEAN)
sh("reset: --keep at HEAD in a clean tree takes nothing", VCS + " reset --keep HEAD", "allow",
   cwd=SUBJCLEAN)
sh("reset: --keep at another commit moves the branch, so a shared checkout refuses",
   VCS + " reset --keep HEAD~1", "deny", "shared-tree", cwd=SUBJCLEAN)
sh("reset: --keep at another commit asks in a clean worktree", VCS + " reset --keep HEAD~1",
   "ask", "shared-tree", cwd=SUBJCLEANWT)
sh("reset: --merge at another commit asks in a clean worktree", VCS + " reset --merge HEAD~1",
   "ask", "shared-tree", cwd=SUBJCLEANWT)
sh("reset: a flag after the commit still counts, --merge refuses", VCS + " reset HEAD~1 --merge",
   "deny", "shared-tree", cwd=SUBJCLEAN)
sh("reset: --merge aimed at a dirty checkout with -C refuses",
   VCS + " -C " + slash(SUBJSTAGED) + " reset --merge", "deny", "shared-tree", cwd=SUBJCLEAN)
sh("reset: an echo that quotes a merge reset is not a call", 'echo "git reset --merge"', "allow",
   cwd=SUBJSTAGED)
sh("reset: a soft reset over a staged edit stays allowed", VCS + " reset --soft HEAD~1", "allow",
   cwd=SUBJSTAGED)
sh("subject: setting aside a clean tree takes nothing", VCS + " stash push -u -m lane", "allow",
   cwd=SUBJCLEAN)
sh("subject: setting aside real uncommitted work still denies", VCS + " stash push -u -m lane",
   "deny", "shared-tree", cwd=SUBJDIRTY)
sh("subject: a bare stash over a clean tree takes nothing", VCS + " stash", "allow",
   cwd=SUBJCLEAN)
# THE PATHSPEC AND OPTION-VALUE FORMS OF A PUSH (owner's Mac test, 2026-10-13; decision
# stash-stack-is-a-shared-subject, the stash stack is shared). Git may omit `push` before `--`, before a pathspec after `--`, and
# before an option, so `stash -- <path>`, `stash -q -- <path>` and `stash -m <msg>` are pushes.
# A word that is no known action reads as a push, so a pathspec such as `f.txt` pushes too.
# These rows run in SUBJDIRTY, a real checkout with real uncommitted work, so each push form must
# deny with the push remedy. `stash .` is not a push: git refuses a pathspec outside `--`, so it
# takes nothing. It stays a deny anyway, because the guard must not rely on git's refusal.
PUSH_FRAGMENT = "puts work onto the stash stack"  # only PUSH_DENY_REASON says this
sh("stash pathspec: stash -- over real uncommitted work denies like a push",
   VCS + " stash -- f.txt", "deny", "shared-tree", cwd=SUBJDIRTY, carries=PUSH_FRAGMENT)
sh("stash pathspec: stash -- . over real uncommitted work denies like a push",
   VCS + " stash -- .", "deny", "shared-tree", cwd=SUBJDIRTY, carries=PUSH_FRAGMENT)
sh("stash pathspec: stash -q -- over real uncommitted work denies like a push",
   VCS + " stash -q -- f.txt", "deny", "shared-tree", cwd=SUBJDIRTY, carries=PUSH_FRAGMENT)
sh("stash pathspec: stash -m over real uncommitted work denies like a push",
   VCS + " stash -m lane", "deny", "shared-tree", cwd=SUBJDIRTY, carries=PUSH_FRAGMENT)
sh("stash pathspec: stash . over real uncommitted work denies", VCS + " stash .", "deny",
   "shared-tree", cwd=SUBJDIRTY)
# Combined short flags and abbreviated long options take a value as the next word too (git's
# parse-options). Each one is a push, so each deny carries the push remedy.
sh("stash pathspec: stash -qm over real uncommitted work denies like a push",
   VCS + " stash -qm list", "deny", "shared-tree", cwd=SUBJDIRTY, carries=PUSH_FRAGMENT)
sh("stash pathspec: stash -um over real uncommitted work denies like a push",
   VCS + " stash -um show", "deny", "shared-tree", cwd=SUBJDIRTY, carries=PUSH_FRAGMENT)
sh("stash pathspec: stash -pm over real uncommitted work denies like a push",
   VCS + " stash -pm show", "deny", "shared-tree", cwd=SUBJDIRTY, carries=PUSH_FRAGMENT)
sh("stash pathspec: stash --mess over real uncommitted work denies like a push",
   VCS + " stash --mess list", "deny", "shared-tree", cwd=SUBJDIRTY, carries=PUSH_FRAGMENT)
sh("stash pathspec: stash --m over real uncommitted work denies like a push",
   VCS + " stash --m list", "deny", "shared-tree", cwd=SUBJDIRTY, carries=PUSH_FRAGMENT)
sh("stash pathspec: stash --pathspec-from over real uncommitted work denies like a push",
   VCS + " stash --pathspec-from list", "deny", "shared-tree", cwd=SUBJDIRTY,
   carries=PUSH_FRAGMENT)
# `import` and `export` are not git subcommands, but main reads them as stack actions, and they keep
# that side. Over a real entry in a clean checkout they deny with the stack remedy. Over an empty
# stack in a dirty checkout they take nothing, the same verdict as main.
STACK_FRAGMENT = "takes a stash entry"  # only STACK_DENY_REASON says this
sh("stash import: over a real stack entry in a clean checkout denies, as on main",
   VCS + " stash import abc123", "deny", "shared-tree", cwd=SUBJSTASH, carries=STACK_FRAGMENT)
sh("stash export: over a real stack entry in a clean checkout denies, as on main",
   VCS + " stash export", "deny", "shared-tree", cwd=SUBJSTASH, carries=STACK_FRAGMENT)
sh("stash import: over an empty stack in a dirty checkout takes nothing, as on main",
   VCS + " stash import abc123", "allow", cwd=SUBJDIRTY)
sh("stash export: over an empty stack in a dirty checkout takes nothing, as on main",
   VCS + " stash export", "allow", cwd=SUBJDIRTY)
# Pins that stay green. The reads stay allowed, and an explicit push still denies here.
sh("stash pathspec pin: an explicit stash push -- still denies over real uncommitted work",
   VCS + " stash push -- f.txt", "deny", "shared-tree", cwd=SUBJDIRTY, carries=PUSH_FRAGMENT)
# STASH HELP FLAGS (owner ruling 2026-10-17). `stash -h` and
# `stash --help` allow over a dirty shared tree when the flag comes first after `stash`: the flag
# prints usage and reads no stack and no tree. Every other shape stays a push. `push -h` stays
# denied because the ruling names the first flag only. Git's own output for `push -h` is
# unmeasured here, and the verdict does not depend on it.
sh("stash help: -h over real uncommitted work allows", VCS + " stash -h", "allow", cwd=SUBJDIRTY)
sh("stash help: --help over real uncommitted work allows", VCS + " stash --help", "allow",
   cwd=SUBJDIRTY)
sh("stash help pin: a bare stash over real uncommitted work still denies like a push",
   VCS + " stash", "deny", "shared-tree", cwd=SUBJDIRTY, carries=PUSH_FRAGMENT)
sh("stash help pin: stash -u over real uncommitted work still denies like a push",
   VCS + " stash -u", "deny", "shared-tree", cwd=SUBJDIRTY, carries=PUSH_FRAGMENT)
sh("stash help pin: stash push -h still denies, the flag is not first after stash",
   VCS + " stash push -h", "deny", "shared-tree", cwd=SUBJDIRTY, carries=PUSH_FRAGMENT)
sh("stash help pin: stash -- -h denies, the -h is a pathspec",
   VCS + " stash -- -h", "deny", "shared-tree", cwd=SUBJDIRTY, carries=PUSH_FRAGMENT)
sh("stash help pin: stash -u -h still denies, the flag is not first after stash",
   VCS + " stash -u -h", "deny", "shared-tree", cwd=SUBJDIRTY, carries=PUSH_FRAGMENT)
sh("stash help pin: stash # -h is a bare stash in the shell, still denies",
   VCS + " stash # -h", "deny", "shared-tree", cwd=SUBJDIRTY, carries=PUSH_FRAGMENT)
sh("stash help pin: a help call chained with a bare stash still denies",
   VCS + " stash -h && " + VCS + " stash", "deny", "shared-tree", cwd=SUBJDIRTY,
   carries=PUSH_FRAGMENT)
# A help flag with anything after it keeps main's verdict: the flag is skipped and the next word decides
# (measured on main, 2026-10-18, these cases already pass there). The action word keeps its side. A
# second flag, or a word that is no action, reads as a push.
sh("stash help pin: stash -h list reads as list, allowed over real uncommitted work",
   VCS + " stash -h list", "allow", cwd=SUBJDIRTY)
sh("stash help pin: stash -h pop reads as pop, denied with the stack remedy",
   VCS + " stash -h pop", "deny", "shared-tree", cwd=SUBJSTASH, carries=STACK_FRAGMENT)
sh("stash help pin: stash --help -h reads as a push, still denies",
   VCS + " stash --help -h", "deny", "shared-tree", cwd=SUBJDIRTY, carries=PUSH_FRAGMENT)
sh("stash help pin: stash -h -h reads as a push, still denies",
   VCS + " stash -h -h", "deny", "shared-tree", cwd=SUBJDIRTY, carries=PUSH_FRAGMENT)
sh("stash help pin: stash --help x reads as a push, still denies",
   VCS + " stash --help x", "deny", "shared-tree", cwd=SUBJDIRTY, carries=PUSH_FRAGMENT)
# THE STACK IS ITS OWN SUBJECT. Every action that takes an entry off the stack is read with `git
# stash list`, never with the tree. SUBJDIRTY is dirty and its stack is empty. SUBJSTASH is clean
# and its stack holds one entry. The two cases cross, which is what proves the right read is made.
#
# A CLEAN TREE IS NOT A PASS FOR THESE ARMS. MEASURED 2026-09-19 against the guard before this
# change: `git stash pop` allowed in a clean checkout holding a real entry, which is exactly the
# state in which taking another session's work leaves no trace. The SUBJSTASH rows below are that
# case, one per action.
sh("subject: dropping an empty stash stack destroys nothing", VCS + " stash drop", "allow",
   cwd=SUBJDIRTY)
sh("subject: dropping a real stash entry still denies", VCS + " stash drop", "deny",
   "shared-tree", cwd=SUBJSTASH, carries=STACK_FRAGMENT)
sh("subject: dropping a real stash entry from a worktree still denies, the stack is clone-wide",
   VCS + " stash drop", "deny", "shared-tree", cwd=SUBJSTASHWT)
sh("subject: clearing an empty stash stack destroys nothing", VCS + " stash clear", "allow",
   cwd=SUBJDIRTY)
sh("subject: clearing a stack holding a real entry still denies", VCS + " stash clear", "deny",
   "shared-tree", cwd=SUBJSTASH, carries=STACK_FRAGMENT)
sh("subject: popping a real entry from a CLEAN checkout still denies", VCS + " stash pop",
   "deny", "shared-tree", cwd=SUBJSTASH, carries=STACK_FRAGMENT)
sh("subject: popping a real entry from a worktree still denies, the stack is clone-wide",
   VCS + " stash pop", "deny", "shared-tree", cwd=SUBJSTASHWT)
sh("subject: applying a real entry from a CLEAN checkout still denies", VCS + " stash apply",
   "deny", "shared-tree", cwd=SUBJSTASH)
sh("subject: the named-entry apply is the same act", VCS + " stash apply stash@{0}", "deny",
   "shared-tree", cwd=SUBJSTASH)
sh("subject: branching off a real entry still denies", VCS + " stash branch lane", "deny",
   "shared-tree", cwd=SUBJSTASH)
sh("subject: branching off an empty stash stack takes nothing", VCS + " stash branch lane",
   "allow", cwd=SUBJDIRTY)
# THE TWO READS STAY ALLOWED where the stack really holds an entry, which is the only place the
# allow means anything.
sh("subject: list reads the stack that holds a real entry", VCS + " stash list", "allow",
   cwd=SUBJSTASH)
sh("subject: show reads the entry without taking it", VCS + " stash show stash@{0}", "allow",
   cwd=SUBJSTASH)
sh("subject: a hard reset in the tree that holds the stash takes nothing",
   VCS + " reset --hard HEAD", "allow", cwd=SUBJSTASH)
# `git stash create` writes a stash commit object and prints its hash. It adds no entry, changes no
# ref, index or working tree, and loses no work, so it is a read even over a real stack entry. The
# rows below pin that, with and without a message argument. The SUBJDIRTY row runs over an empty
# stack in a dirty tree, which pins that a dirty tree alone does not turn `create` into a write.
sh("stash create: over a real entry in a dirty checkout takes nothing", VCS + " stash create",
   "allow", cwd=SUBJSTASHDIRTY)
sh("stash create: a message argument over a real entry takes nothing",
   VCS + " stash create lane", "allow", cwd=SUBJSTASHDIRTY)
sh("stash create: captured into a variable over a real entry takes nothing",
   "WORK=$(" + VCS + " stash create)", "allow", cwd=SUBJSTASHDIRTY)
sh("stash create: over a real entry in a clean checkout takes nothing", VCS + " stash create",
   "allow", cwd=SUBJSTASH)
sh("stash create: over a real entry from a worktree takes nothing, the stack is clone-wide",
   VCS + " stash create", "allow", cwd=SUBJSTASHWT)
sh("stash create: over an empty stack in a dirty checkout takes nothing", VCS + " stash create",
   "allow", cwd=SUBJDIRTY)
# `store` writes the stack's own ref, so it stays a stack action and keeps its deny.
sh("stash store: writes the stack ref over a real entry, still denies",
   VCS + " stash store -m lane HEAD", "deny", "shared-tree", cwd=SUBJSTASH,
   carries=STACK_FRAGMENT)
# `_run_dir` cases: the cwd is SUBJDIRTY (real, dirty) and the command only ATTACHES or MENTIONS SUBJCLEAN, so both deny.
sh("run-dir bypass: an attached `-C<path>` is not a spelling git accepts, so it names no tree",
   VCS + " -C" + SUBJCLEAN + " status; " + VCS + " reset --hard HEAD",
   "deny", "shared-tree", cwd=SUBJDIRTY)
sh("run-dir bypass: a `cd` inside an interpreter heredoc body never moves the outer shell",
   "python3 <<'EOF'\ncd " + SUBJCLEAN + "\nprint('hi')\nEOF\n" + VCS + " reset --hard HEAD",
   "deny", "shared-tree", cwd=SUBJDIRTY)
# A body `cd` is a live line when a stray `EOF` closes the body early, so the reset after the closer runs in the dirty tree.
# The body never runs, so this deny is a bandaid, kept under the no-safety-hole ruling (hold-unsafe-after-round-3).
sh("run-dir r3-bd: a body cd after a stray EOF line, a reset after the closer, denies as on main",
   "cat <<'EOF-1' > x.sh\nEOF\ncd " + slash(SUBJDIRTY) + "\nEOF-1\n" + VCS + " reset --hard HEAD",
   "deny", "shared-tree", cwd=SUBJCLEAN)
# PER PATH for `restore` and `checkout <path>`: the pathspec goes to git, and an empty answer
# proves the write changes nothing. Both named paths sit in the SAME dirty tree.
sh("subject: restoring a clean path inside a dirty tree changes nothing",
   VCS + " restore keep.txt", "allow", cwd=SUBJDIRTY)
sh("subject: restoring the modified path still denies", VCS + " restore f.txt", "deny",
   "shared-tree", cwd=SUBJDIRTY)
sh("subject: restoring the whole clean tree changes nothing", VCS + " restore .", "allow",
   cwd=SUBJCLEAN)
sh("subject: checking out a clean path inside a dirty tree changes nothing",
   VCS + " checkout -- keep.txt", "allow", cwd=SUBJDIRTY)
sh("subject: checking out the modified path still denies", VCS + " checkout -- f.txt", "deny",
   "shared-tree", cwd=SUBJDIRTY)
sh("subject: a start point and a clean path change nothing",
   VCS + " checkout HEAD -- keep.txt", "allow", cwd=SUBJDIRTY)
sh("subject: a start point and the modified path still denies",
   VCS + " checkout HEAD -- f.txt", "deny", "shared-tree", cwd=SUBJDIRTY)
# `clean -f` deletes the UNTRACKED part of that same output, so that part is its subject.
sh("subject: a clean with no untracked file deletes nothing", VCS + " clean -fd", "allow",
   cwd=SUBJCLEAN)
sh("subject: a clean over a real untracked file still denies", VCS + " clean -fd", "deny",
   "shared-tree", cwd=SUBJDIRTY)
sh("subject: a clean scoped to a tracked path deletes nothing", VCS + " clean -fd keep.txt",
   "allow", cwd=SUBJDIRTY)
# `-e` carries a value. The value is NOT a pathspec, and reading it as one would narrow the read
# and let the delete of everything else pass on an empty answer.
sh("subject: an exclude pattern is not a pathspec", VCS + " clean -fd -e build", "deny",
   "shared-tree", cwd=SUBJDIRTY)
# THIS SESSION'S SCRATCHPAD, BY PATH. The same dirty repository answers three ways: private to
# the session the payload names, shared to any other session, and shared with no session at all.
add("scratchpad: a discard in this session's own scratchpad is private", "allow", cwd=PRIVREPO,
    session=FAKE_SESSION, command=VCS + " reset --hard HEAD")
add("scratchpad: another session's scratchpad is not this session's", "deny", "shared-tree",
    cwd=PRIVREPO, session=OTHER_SESSION, command=VCS + " reset --hard HEAD")
add("scratchpad: no session id names no scratchpad", "deny", "shared-tree", cwd=PRIVREPO,
    command=VCS + " reset --hard HEAD")
add("scratchpad: the same session id outside the scratchpad proves nothing", "deny",
    "shared-tree", cwd=SUBJDIRTY, session=FAKE_SESSION, command=VCS + " reset --hard HEAD")
# AN UNREADABLE SUBJECT IS ALLOWED, and logged under its own rule (checked in
# subject_unread_log_case). The cwd is the REAL dirty repository, so the only difference from the
# deny case above is that the git on PATH gives no answer.
if os.name != "nt":
    sh("subject: a git that cannot answer the status read allows, rather than guess",
       VCS + " reset --hard HEAD", "allow", cwd=SUBJDIRTY, env_path=GITBLIND)
    sh("subject: the same blind git on a stack subject allows", VCS + " stash drop", "allow",
       cwd=SUBJSTASH, env_path=GITBLIND)
else:
    skip_case("subject: a git that cannot answer the status read allows, rather than guess", NO_STAND_IN)
    skip_case("subject: the same blind git on a stack subject allows", NO_STAND_IN)

# RULE 1 KEEPS GOVERNING A PATH OPERATION IN THIS CHECKOUT, UNCHANGED. `f.txt` is really modified
# there, so rule 1 denies; `keep.txt` is really clean, so rule 1's empty-subject arm passes. Both
# answers are rule 1's own, and the pointer rule never sees either call.
sh("pointer: checkout of a dirty path keeps rule 1's deny", VCS + " checkout -- f.txt", "deny",
   "shared-tree", cwd=PTRMAIN, config=PTRCFG)
sh("pointer: checkout of a clean path keeps rule 1's empty-subject pass",
   VCS + " checkout -- keep.txt", "allow", cwd=PTRMAIN, config=PTRCFG)
sh("pointer: a bare path argument is still rule 1's subject", VCS + " checkout f.txt", "deny",
   "shared-tree", cwd=PTRMAIN, config=PTRCFG)
sh("pointer: --theirs is a path operation, not a branch switch",
   VCS + " checkout --theirs f.txt", "deny", "shared-tree", cwd=PTRMAIN, config=PTRCFG)
sh("pointer: a branch plus a path writes one file, and rule 1 judges it",
   VCS + " checkout somebranch -- f.txt", "deny", "shared-tree", cwd=PTRMAIN, config=PTRCFG)

# A DIRECTORY THAT IS NO GIT TREE IS NOT AN UNREADABLE SUBJECT. git answers there, and the answer
# is "no tree", so the rule keeps its fail-closed deny. Every NOGIT case above rests on this.
sh("subject: a directory that is no git tree still denies", VCS + " reset --hard HEAD", "deny",
   "shared-tree", cwd=NOGIT)

sh("clean: -fd deletes untracked files", VCS + " clean -fd", "deny", "shared-tree", cwd=NOGIT)
sh("clean: the long force flag", VCS + " clean --force -d", "deny", "shared-tree", cwd=NOGIT)
sh("clean: the doubled force flag", VCS + " clean -ff", "deny", "shared-tree", cwd=NOGIT)
sh("clean: the flags bundled the other way", VCS + " clean -df", "deny", "shared-tree", cwd=NOGIT)
sh("shared tree: inside a compound command", "node harness/gate.js && " + VCS + " reset --hard",
   "deny", "shared-tree", cwd=NOGIT)
sh("shared tree: on a second line", VCS + " status\n" + VCS + " reset --hard\n", "deny",
   "shared-tree", cwd=NOGIT)
sh("shared tree: against another checkout", VCS + " -C ../other-worktree reset --hard", "deny",
   "shared-tree", cwd=NOGIT)
sh("shared tree: from the PowerShell tool as well", VCS + " reset --hard", "deny", "shared-tree",
   tool="PowerShell", cwd=NOGIT)
sh("shared tree: a stash from the PowerShell tool", VCS + " stash", "deny", "shared-tree",
   tool="PowerShell", cwd=NOGIT)

sh("clean: -n only lists", VCS + " clean -n", "allow", cwd=NOGIT)
sh("checkout: a new branch keeps every file", VCS + " checkout -b claude/lane main", "allow",
   cwd=NOGIT)
sh("checkout: a branch move keeps every file", VCS + " checkout main", "allow", cwd=NOGIT)
sh("checkout: a branch name holding a slash", VCS + " checkout claude/shared-tree-guard", "allow",
   cwd=NOGIT)
sh("checkout: the previous branch", VCS + " checkout -", "allow", cwd=NOGIT)
sh("checkout: a forced new branch at a commit", VCS + " checkout -B tmp 380d5fc", "allow",
   cwd=NOGIT)
sh("checkout: tracking a remote branch", VCS + " checkout --track origin/main", "allow", cwd=NOGIT)

# THE REDIRECT FALSE POSITIVE. MEASURED in guard.log: `git checkout origin/claude/pass3-seam 2>&1`
# was refused while the same call with no redirect passed, because `2>&1` reached
# `checkout_names_a_path` as a second plain word. A redirect must never change what a `git checkout`
# call is judged to name.
sh("checkout: a start point survives a merged-output redirect",
   VCS + " checkout origin/claude/pass3-seam 2>&1", "allow", cwd=NOGIT)
sh("checkout: a start point survives a discarded-error redirect",
   VCS + " checkout main 2>/dev/null", "allow", cwd=NOGIT)
sh("checkout: a new branch survives a log redirect and merged output",
   VCS + " checkout -b feat/x origin/feat/x >log.txt 2>&1", "allow", cwd=NOGIT)
sh("checkout: a status piped onward is not a checkout at all",
   VCS + " status 2>&1 | head -5", "allow", cwd=NOGIT)
sh("checkout: a path after the double dash survives a merged-output redirect",
   VCS + " checkout -- README.md 2>&1", "deny", "shared-tree", cwd=NOGIT)
sh("checkout: an older commit and a path survive a discarded-output redirect",
   VCS + " checkout HEAD~1 src/app.py >/dev/null", "deny", "shared-tree", cwd=NOGIT)
sh("stash: a discarded-error redirect is not a way past the rule",
   VCS + " stash 2>/dev/null", "deny", "shared-tree", cwd=NOGIT)
sh("shared tree: reading the tree", VCS + " status --porcelain", "allow", cwd=NOGIT)
sh("shared tree: a log is not a discard", VCS + " log main..HEAD --oneline", "allow", cwd=NOGIT)
sh("shared tree: a diff naming a path is not a discard", VCS + " diff --stat main..HEAD -- src/",
   "allow", cwd=NOGIT)
sh("shared tree: a cherry-pick is not a discard", VCS + " cherry-pick -n 380d5fc", "allow",
   cwd=NOGIT)
sh("shared tree: a fast-forward merge is not a discard", VCS + " merge --ff-only a6ab78d", "allow",
   cwd=NOGIT)
sh("shared tree: a compound of allowed commands", VCS + " checkout -b lane; " + VCS + " status",
   "allow", tool="PowerShell", cwd=NOGIT)

# THE WORKTREE HALF. A discard in a linked worktree asks, because the lane is the only thing it can
# lose. In the shared checkout it denies. The guard asks git which tree it stands in, so these four
# cases drive a real checkout and a real worktree built beside it. The per-file carve-out that
# lifts the ask for a checkout or restore of named files is in the block below.
sh("worktree: a hard reset in the shared checkout denies", VCS + " reset --hard", "deny",
   "shared-tree", cwd=GITMAIN)
sh("worktree: the same reset inside a worktree asks", VCS + " reset --hard", "ask",
   "shared-tree", cwd=GITWT)
# other-checkout refuses a -C that names another checkout of the clone, as the cd form does (coordinator ruling,
# valid from 2026-11-08 17:15 CST, keep deny: matches the cd form, an owner override lifts it).
sh("worktree: -C naming the worktree is refused, from the shared checkout",
   VCS + " -C " + slash(GITWT) + " reset --hard", "deny", "other-checkout", cwd=GITMAIN)
# A leading cd is no second command (ask-commands-run-alone). The -C reset is refused alone, as the line above.
sh("worktree: a leading cd into the shared checkout's own root, then a -C reset of the worktree, is refused",
   "cd " + slash(GITMAIN) + " && " + VCS + " -C " + slash(GITWT) + " reset --hard", "deny",
   "other-checkout", cwd=GITMAIN, lacks=(CHAIN_ASK,))
# DATA, NOT A DISCARD. A reset named inside a JSON payload piped to python runs nothing in the lane, so it allows.
sh("worktree data: a reset named in a JSON payload piped to python, inside a worktree, allows",
   "printf '%s' '" + json.dumps({"tool_input": {"command": VCS + " reset --hard"}})
   + "' | python hooks/guard.py", "allow", cwd=GITWT)

# THE PER-FILE CARVE-OUT (owner ruling 2026-10-11, "Allow per-file"; decision
# agent-worktree-discard-is-noted). In a linked worktree, a checkout or restore that names only FILES writes the
# lane's own change to those files, so it runs with no ask. A folder, a glob, `.`, and a whole-tree
# reset keep the ask. A shared checkout denies every form here. Each case is tagged "per-file", so
# MUTATE_ONLY=per-file runs this block alone. The fixtures are real: fixtures/a.json,
# fixtures/media-players.json and src/app.py are tracked and modified in all four trees.

# ALLOW, in a linked worktree (GITWT). Each names one tracked file the lane changed.
sh("per-file allow: checkout of one modified file", VCS + " checkout fixtures/a.json",
   "allow", cwd=GITWT)
sh("per-file allow: checkout -- of one modified file", VCS + " checkout -- f.txt",
   "allow", cwd=GITWT)
sh("per-file allow: checkout HEAD -- of one modified file", VCS + " checkout HEAD -- f.txt",
   "allow", cwd=GITWT)
sh("per-file allow: restore of one modified file", VCS + " restore f.txt", "allow", cwd=GITWT)
sh("per-file allow: restore --staged --worktree of one modified file",
   VCS + " restore --staged --worktree f.txt", "allow", cwd=GITWT)
# one_place (guard.py): a cd anywhere in the command keeps the ask, because a cd can hide the shared
# checkout behind the lane. Here other-checkout refuses the -C form first, so the deny names that rule.
# The chained ask rows below (ask-alone) pin the chain itself.
sh("per-file ask: the incident form, a leading cd into the shared checkout's own root, a -C checkout of one worktree file, then python, denies by other-checkout",
   "cd " + slash(GITMAIN) + " && " + VCS + " -C " + slash(GITWT)
   + " checkout fixtures/media-players.json && python3 x.py", "deny", "other-checkout", cwd=GITMAIN)

# ASK, in a linked worktree (GITWT). Each names a whole tree, a folder, a glob, or a reset.
sh("per-file ask: checkout . in a worktree still asks", VCS + " checkout .", "ask",
   "shared-tree", cwd=GITWT)
sh("per-file ask: restore . in a worktree still asks", VCS + " restore .", "ask",
   "shared-tree", cwd=GITWT)
sh("per-file ask: checkout -- of a folder in a worktree still asks", VCS + " checkout -- src/",
   "ask", "shared-tree", cwd=GITWT)
sh("per-file ask: restore of a glob in a worktree still asks", VCS + " restore '*.json'",
   "ask", "shared-tree", cwd=GITWT)

# DENY, in the shared checkout (GITMAIN). Every form above, the allow and the ask rows alike.
sh("per-file deny: checkout of one file in the shared checkout", VCS + " checkout fixtures/a.json",
   "deny", "shared-tree", cwd=GITMAIN)
sh("per-file deny: checkout -- of one file in the shared checkout", VCS + " checkout -- f.txt",
   "deny", "shared-tree", cwd=GITMAIN)
sh("per-file deny: checkout HEAD -- of one file in the shared checkout",
   VCS + " checkout HEAD -- f.txt", "deny", "shared-tree", cwd=GITMAIN)
sh("per-file deny: restore of one file in the shared checkout", VCS + " restore f.txt", "deny",
   "shared-tree", cwd=GITMAIN)
sh("per-file deny: restore --staged --worktree of one file in the shared checkout",
   VCS + " restore --staged --worktree f.txt", "deny", "shared-tree", cwd=GITMAIN)
sh("per-file deny: the incident form, a leading cd into the worktree's own root, then a -C checkout in the shared checkout, from a worktree",
   "cd " + slash(GITWT) + " && " + VCS + " -C " + slash(GITMAIN)
   + " checkout fixtures/media-players.json && python3 x.py", "deny", "other-checkout", cwd=GITWT)
sh("per-file deny: checkout . in the shared checkout", VCS + " checkout .", "deny",
   "shared-tree", cwd=GITMAIN)
sh("per-file deny: restore . in the shared checkout", VCS + " restore .", "deny",
   "shared-tree", cwd=GITMAIN)
sh("per-file deny: checkout -- of a folder in the shared checkout", VCS + " checkout -- src/",
   "deny", "shared-tree", cwd=GITMAIN)
sh("per-file deny: restore of a glob in the shared checkout", VCS + " restore '*.json'",
   "deny", "shared-tree", cwd=GITMAIN)
# A QUOTED PATHSPEC. The guard splits the command on whitespace and does not strip the quotes, so
# `'*.json'` reaches git's status read as the literal text `'*.json'`, matches nothing, and reads
# as an empty subject. A discard then passes. The shared checkout must still deny it.
sh("per-file deny: a double-quoted path in the shared checkout", VCS + ' restore "f.txt"',
   "deny", "shared-tree", cwd=GITMAIN)

# BRANCH SWITCH, pinned to today's answer. `checkout main` names no path, so the shared-tree rule
# never reads it, and a worktree keeps whatever it does now. This case must pass before and after.
sh("per-file branch switch: checkout main in a worktree keeps today's answer",
   VCS + " checkout main", "allow", cwd=GITWT)

# BARE CHECKOUT OF AN EXTENSIONLESS FILE. With no `--`, git reads one operand as a path when no
# branch has that name. checkout_names_a_path reads a single operand as a path only when it has an
# extension, a leading ./, a backslash or a trailing slash, or when it is a folder. So `checkout
# Makefile` and `checkout tools/runner` were never judged. Both are modified in the shared checkout
# and in the hand-made worktree. LICENSE stays clean. Rows marked (pin) hold behaviour this change keeps.
sh("per-file bare: checkout of an extensionless file in the shared checkout denies",
   VCS + " checkout Makefile", "deny", "shared-tree", cwd=GITMAIN)
sh("per-file bare: checkout of a folder's extensionless file in the shared checkout denies",
   VCS + " checkout tools/runner", "deny", "shared-tree", cwd=GITMAIN)
sh("per-file bare: checkout -- of an extensionless file in the shared checkout denies (pin)",
   VCS + " checkout -- Makefile", "deny", "shared-tree", cwd=GITMAIN)
sh("per-file bare: restore of an extensionless file in the shared checkout denies (pin)",
   VCS + " restore Makefile", "deny", "shared-tree", cwd=GITMAIN)
sh("per-file bare: restore of a folder's extensionless file in the shared checkout denies (pin)",
   VCS + " restore tools/runner", "deny", "shared-tree", cwd=GITMAIN)
sh("per-file bare: checkout of a clean extensionless file in the shared checkout allows",
   VCS + " checkout LICENSE", "allow", cwd=GITMAIN)
sh("per-file bare: restore of a clean extensionless file in the shared checkout allows",
   VCS + " restore LICENSE", "allow", cwd=GITMAIN)
sh("per-file bare: checkout of an extensionless file in a hand-made worktree allows",
   VCS + " checkout Makefile", "allow", cwd=GITWT)
sh("per-file bare: restore of an extensionless file in a hand-made worktree allows",
   VCS + " restore Makefile", "allow", cwd=GITWT)
sh("per-file bare: checkout of a branch name in the shared checkout keeps today's answer",
   VCS + " checkout agent-x-branch", "allow", cwd=GITMAIN)

# THE GATES IN lone_operand_is_dirty_file (guard_shared_tree.py). A lone name reads as a path only
# when it exists, is no revision, and has a tracked change. The first row pins the status gate: an
# untracked file is no tracked change. The second pins the revision gate. The last two pin the
# subfolder form and a staged entry.
sh("per-file bare: checkout of an untracked extensionless file in the shared checkout allows",
   VCS + " checkout scratch", "allow", cwd=GITMAIN)
# A dirty file whose name is also a branch. Git reads a name that is both a branch and a file as
# the branch: it switches and keeps the file. The guard allows it, as main does.
sh("per-file bare: checkout of a dirty file that is also a branch in the shared checkout allows",
   VCS + " checkout hotfix", "allow", cwd=GITMAIN)
# A relative path from a subfolder. Git reads `runner` against tools/, so it discards tools/runner.
sh("per-file bare: checkout of a dirty file named from a subfolder in the shared checkout denies",
   "cd tools && " + VCS + " checkout runner", "deny", "shared-tree", cwd=GITMAIN)
# A staged-only change. Git keeps it ("Updated 0 paths"), since the tree holds the staged text.
# The guard reads the staged entry as a dirty file and denies. This pins that choice.
sh("per-file bare: checkout of a staged-only file in the shared checkout denies "
   "(pin: staged counts as dirty, though git keeps it)",
   VCS + " checkout staged-note", "deny", "shared-tree", cwd=GITMAIN)

# AN UNREADABLE LONE OPERAND (guard_shared_tree.lone_operand_is_dirty_file). A bare `checkout Makefile`
# is judged as a path only when git can say what the name is and what its status is. When a read gets
# no answer, the call is allowed (the verdict stays silent) and logged once as `noted`/`subject-unread`.
# The two reads fail in different places, so each branch has its own case: no git at all (the revision
# read gets no answer), and a git that answers the repo test only (the revision read fails, then the
# status read gets no answer). The checks register with LOG_CHECKS_EXTRA below, where that list exists.
UNREAD_NOGIT_LABEL = ("per-file bare log: a bare checkout of a dirty file with no git on PATH is allowed "
                      "and logged once as subject-unread")
UNREAD_STATUS_LABEL = ("per-file bare log: a bare checkout of a dirty file whose status git cannot read "
                       "is allowed and logged once as subject-unread")


def unread_lone_operand_no_git_case():
    """No git on PATH: the revision read gets no answer, so the lone operand is allowed and logged once."""
    os.makedirs(NOGIT_PATH, exist_ok=True)
    return subject_unread_log_case(VCS + " checkout Makefile", cwd=GITMAIN, search_path=NOGIT_PATH,
                                   needle="checkout Makefile")


def unread_lone_operand_status_case():
    """A git that answers the repo test only: the revision read fails, the status read gets no answer."""
    return subject_unread_log_case(VCS + " checkout Makefile", cwd=GITMAIN, search_path=GITBLIND,
                                   needle="checkout Makefile")

# THE DISCARD FORMS THAT JOIN THE RULE (decision agent-worktree-discard-is-noted, "These discard forms
# join the rule"). A linked worktree keeps the ask for each one: the lane's own change is not a
# named file. The shared checkout denies each one. Each case is tagged "per-file".

# ASK, in a linked worktree (GITWT). A folder, a whole tree, an option the carve-out does not read,
# a quote the tokenizer cannot close, or a form with more than one operand.
sh("per-file ask: checkout . with a second operand in a worktree still asks",
   VCS + " checkout . guard.py", "ask", "shared-tree", cwd=GITWT)
sh("per-file ask: checkout of a folder and a file in a worktree still asks",
   VCS + " checkout hooks guard.py", "ask", "shared-tree", cwd=GITWT)
sh("per-file ask: restore --pathspec-from in a worktree still asks",
   VCS + " restore --pathspec-from " + slash(PATHSPEC_LIST) + " f.txt", "ask", "shared-tree",
   cwd=GITWT)
sh("per-file ask: restore --pathspec-from-file in a worktree still asks",
   VCS + " restore --pathspec-from-file=" + slash(PATHSPEC_LIST), "ask", "shared-tree", cwd=GITWT)
sh("per-file ask: restore -p of one file in a worktree still asks",
   VCS + " restore -p f.txt", "ask", "shared-tree", cwd=GITWT)
sh("per-file ask: restore -s HEAD~5 of one file in a worktree still asks",
   VCS + " restore -s HEAD~5 f.txt", "ask", "shared-tree", cwd=GITWT)
sh("per-file ask: restore of an unterminated quote in a worktree still asks",
   VCS + ' restore "f.txt', "ask", "shared-tree", cwd=GITWT)
sh("per-file ask: checkout -f of one file in a worktree still asks",
   VCS + " checkout -f f.txt", "ask", "shared-tree", cwd=GITWT)

# ALLOW, in a linked worktree (GITWT). Each names only existing tracked files, with a form the
# carve-out reads. `checkout fixtures/a.json` is already pinned above as "per-file allow: checkout
# of one modified file", so it is not repeated here.
sh("per-file allow: checkout -- of two modified files in a worktree",
   VCS + " checkout -- a.txt b.txt", "allow", cwd=GITWT)
sh("per-file allow: restore --staged --worktree -- of one modified file in a worktree",
   VCS + " restore --staged --worktree -- a.txt", "allow", cwd=GITWT)
sh("per-file allow: restore -S -W of one modified file in a worktree",
   VCS + " restore -S -W a.txt", "allow", cwd=GITWT)

# A FORCED BRANCH SWITCH. The shared checkout denies it, and a worktree asks, because a forced
# switch throws away the local changes of the tree it runs in.
sh("per-file deny: checkout -f main in the shared checkout", VCS + " checkout -f main", "deny",
   "shared-tree", cwd=GITMAIN)
sh("per-file ask: checkout -f main in a worktree still asks", VCS + " checkout -f main", "ask",
   "shared-tree", cwd=GITWT)
sh("per-file deny: checkout --force main in the shared checkout", VCS + " checkout --force main",
   "deny", "shared-tree", cwd=GITMAIN)
sh("per-file ask: checkout --force main in a worktree still asks",
   VCS + " checkout --force main", "ask", "shared-tree", cwd=GITWT)

# THE SWITCH FORMS OF A FORCED BRANCH SWITCH. `git switch -f`, `--force`
# and `--discard-changes` throw the local changes away as `checkout -f` does, so each takes the same
# verdict: deny in the shared checkout, ask in a worktree. A plain switch and a new branch discard
# nothing, so they pass in both checkouts.
for _flag in ("-f", "--force", "--discard-changes"):
    sh("looser-git-acts: switch %s main is denied in the shared checkout" % _flag,
       VCS + " switch %s main" % _flag, "deny", "shared-tree", cwd=GITMAIN)
    sh("looser-git-acts: switch %s main still asks in a worktree" % _flag,
       VCS + " switch %s main" % _flag, "ask", "shared-tree", cwd=GITWT)
for _command in ("switch main", "switch -c newbranch"):
    sh("looser-git-acts: %s is allowed in the shared checkout" % _command, VCS + " " + _command,
       "allow", cwd=GITMAIN)
    sh("looser-git-acts: %s is allowed in a worktree" % _command, VCS + " " + _command,
       "allow", cwd=GITWT)

# A FOLDER WITH NO `--`. Git reads a bare name as a path, so a folder is a whole-folder discard.
sh("per-file deny: checkout of a folder with no -- in the shared checkout",
   VCS + " checkout hooks", "deny", "shared-tree", cwd=GITMAIN)
sh("per-file ask: checkout of a folder with no -- in a worktree still asks",
   VCS + " checkout hooks", "ask", "shared-tree", cwd=GITWT)

# A PATHSPEC FILE, under the long name and under a unique prefix git accepts.
sh("per-file deny: checkout --pathspec-from-file in the shared checkout",
   VCS + " checkout --pathspec-from-file=" + slash(PATHSPEC_LIST), "deny", "shared-tree",
   cwd=GITMAIN)
sh("per-file ask: checkout --pathspec-from-file in a worktree still asks",
   VCS + " checkout --pathspec-from-file=" + slash(PATHSPEC_LIST), "ask", "shared-tree",
   cwd=GITWT)
sh("per-file deny: checkout --pathspec-from in the shared checkout",
   VCS + " checkout --pathspec-from " + slash(PATHSPEC_LIST), "deny", "shared-tree", cwd=GITMAIN)
sh("per-file ask: checkout --pathspec-from in a worktree still asks",
   VCS + " checkout --pathspec-from " + slash(PATHSPEC_LIST), "ask", "shared-tree", cwd=GITWT)

# EACH -C. The last -C sets the checkout the rule judges, whichever -C comes first.
sh("per-file deny: -C names the shared checkout last, from a worktree",
   VCS + " -C " + slash(NOGIT) + " -C " + slash(GITMAIN) + " checkout -- f.txt", "deny",
   "other-checkout", cwd=GITWT)
sh("per-file deny: -C names a worktree first and the shared checkout last, from a plain folder",
   VCS + " -C " + slash(GITWT) + " -C " + slash(GITMAIN) + " checkout -- f.txt", "deny",
   "shared-tree", cwd=NOGIT)
sh("per-file allow: -C names the shared checkout first and a worktree last, from a plain folder",
   VCS + " -C " + slash(GITMAIN) + " -C " + slash(GITWT) + " checkout -- f.txt", "allow",
   cwd=NOGIT)

# THE LAST THREE BULLETS (decision agent-worktree-discard-is-noted, "These discard forms join the
# rule"): each -C, every operand of restore as a path, and a pathspec the guard cannot read. Each
# case is tagged "per-file".

# EACH -C, FROM A CLEAN WORKTREE. The chained target is the shared checkout (GITMAIN, dirty), so
# the rule judges it and denies. SUBJCLEANWT, the call's own tree, is clean and must not decide.
sh("per-file deny: -C shared checkout then -C . reset --hard, from a clean worktree",
   VCS + " -C " + slash(GITMAIN) + " -C . reset --hard", "deny", "shared-tree", cwd=SUBJCLEANWT)

# EACH -C, A RELATIVE SECOND -C THAT LANDS IN A WORKTREE. The second -C joins the first, so the
# chained target is GITWT, a linked worktree. The carve-out reads it and allows the named file.
sh("per-file allow: -C parent then a relative -C lane, checkout -- of one file",
   VCS + " -C " + slash(ROOT) + " -C lane checkout -- f.txt", "allow", cwd=NOGIT)

# EVERY OPERAND OF restore IS A PATH. A folder or a dot named before `--` is a whole-folder
# discard, so a linked worktree keeps the ask. README.md is dirty in every tree.
sh("per-file ask: restore --worktree hooks -- README.md in a worktree still asks",
   VCS + " restore --worktree hooks -- README.md", "ask", "shared-tree", cwd=GITWT)
sh("per-file ask: restore . -- README.md in a worktree still asks",
   VCS + " restore . -- README.md", "ask", "shared-tree", cwd=GITWT)

# AN UNREADABLE PATHSPEC. A brace, a variable, a backtick or a glob the guard cannot expand is a
# discard of unknown size. The shared checkout denies it. A linked worktree asks.
sh("per-file deny: restore --worktree {hooks,README.md} in the shared checkout",
   VCS + " restore --worktree {hooks,README.md}", "deny", "shared-tree", cwd=GITMAIN)
sh("per-file ask: restore --worktree {hooks,README.md} in a worktree still asks",
   VCS + " restore --worktree {hooks,README.md}", "ask", "shared-tree", cwd=GITWT)
sh("per-file deny: restore \"$F\" in the shared checkout", VCS + ' restore "$F"', "deny",
   "shared-tree", cwd=GITMAIN)
sh("per-file ask: restore \"$F\" in a worktree still asks", VCS + ' restore "$F"', "ask",
   "shared-tree", cwd=GITWT)
sh("per-file deny: restore `cat list` in the shared checkout", VCS + " restore `cat list`",
   "deny", "shared-tree", cwd=GITMAIN)
sh("per-file ask: restore `cat list` in a worktree still asks", VCS + " restore `cat list`",
   "ask", "shared-tree", cwd=GITWT)
sh("per-file deny: checkout -- '*.md' in the shared checkout", VCS + " checkout -- '*.md'",
   "deny", "shared-tree", cwd=GITMAIN)
sh("per-file ask: checkout -- '*.md' in a worktree still asks", VCS + " checkout -- '*.md'",
   "ask", "shared-tree", cwd=GITWT)

# SECOND SET (decision agent-worktree-discard-is-noted, "These discard forms join the rule"). The
# operand before `--` is a path, and the clean file after `--` must not hide it. keep.txt is clean
# in every tree; f.txt is dirty in the shared checkout and in the lane.
sh("per-file deny: restore f.txt -- keep.txt in the shared checkout, operand before --",
   VCS + " restore f.txt -- keep.txt", "deny", "shared-tree", cwd=GITMAIN)
sh("per-file ask: restore . -- keep.txt in a worktree: a dot before -- is a whole tree",
   VCS + " restore . -- keep.txt", "ask", "shared-tree", cwd=GITWT)
sh("per-file deny: restore \"$F\" -- keep.txt in the shared checkout, unreadable before --",
   VCS + ' restore "$F" -- keep.txt', "deny", "shared-tree", cwd=GITMAIN)
sh("per-file ask: restore \"$F\" -- keep.txt in a worktree still asks, unreadable before --",
   VCS + ' restore "$F" -- keep.txt', "ask", "shared-tree", cwd=GITWT)
# EACH -C IN ITS OWN CALL. The second git call names the shared checkout, so it is the one judged.
# The first call's -C reads the lane, which has f.txt dirty too and would allow a per-file restore.
sh("per-file deny: -C lane status, then -C shared restore f.txt, from a plain folder",
   VCS + " -C " + slash(GITWT) + " status && " + VCS + " -C " + slash(GITMAIN) + " restore f.txt",
   "deny", "shared-tree", cwd=NOGIT)
# A leading cd into the worktree's own root names no other checkout, so the shared checkout is named by -C:
# a cd into it is refused by other-checkout first. The row pins other-checkout's deny on the restore, not a chain ask.
sh("per-file deny: a leading cd into the worktree's own root, then git -C shared restore f.txt, from a worktree",
   "cd " + slash(GITWT) + " && " + VCS + " -C " + slash(GITMAIN) + " restore f.txt", "deny",
   "other-checkout", cwd=GITWT, lacks=(CHAIN_ASK,))
sh("per-file deny: -C parent then a relative -C repo, from a plain folder",
   VCS + " -C " + slash(ROOT) + " -C repo restore f.txt", "deny", "shared-tree", cwd=NOGIT)
# IDENTICAL SEGMENTS (decision agent-worktree-discard-is-noted, section "Named files in a linked
# worktree"): each git call is judged in its own checkout. The lane and the shared checkout both hold
# f.txt dirty, so a per-file restore allows in the lane and denies in the shared checkout, even when the
# segment text repeats.
sh("per-file deny: cd lane; restore f.txt; cd shared; the same restore f.txt, joined by ;",
   "cd " + slash(GITWT) + "; " + VCS + " restore f.txt; cd " + slash(GITMAIN) + "; "
   + VCS + " restore f.txt", "deny", "shared-tree", cwd=NOGIT)
# The && forms end in `&& echo done`. A segment keeps the blank before its `&&`, so the two
# restore segments only read as identical when a later `&&` gives the second one that blank too.
# The bare form without a trailing join is judged correctly on the base, because its last segment
# has no trailing blank, so it is not a repeat of the first.
sh("per-file deny: cd lane && restore f.txt && cd shared && the same restore f.txt, && joins",
   "cd " + slash(GITWT) + " && " + VCS + " restore f.txt && cd " + slash(GITMAIN) + " && "
   + VCS + " restore f.txt && echo done", "deny", "shared-tree", cwd=NOGIT)
sh("per-file deny: cd lane && git -C . restore f.txt && cd shared && the same -C . restore, && joins",
   "cd " + slash(GITWT) + " && " + VCS + " -C . restore f.txt && cd " + slash(GITMAIN) + " && "
   + VCS + " -C . restore f.txt && echo done", "deny", "shared-tree", cwd=NOGIT)
sh("per-file deny: cd lane; git -C . restore f.txt; cd shared; the same -C . restore",
   "cd " + slash(GITWT) + "; " + VCS + " -C . restore f.txt; cd " + slash(GITMAIN) + "; "
   + VCS + " -C . restore f.txt", "deny", "shared-tree", cwd=NOGIT)
# CONTROL. Both calls stay in the lane, so the repeat stays an allow.
chained_ask("per-file ask: cd lane && restore f.txt && cd lane && the same restore f.txt, a cd keeps the ask, chained it denies",
            "cd " + slash(GITWT) + " && " + VCS + " restore f.txt && cd " + slash(GITWT) + " && "
            + VCS + " restore f.txt && echo done", cwd=NOGIT)

# HEREDOC BODY WITH A LONE QUOTE, THEN A CD. segment_roots (guard.py ~1228) loses sync when a heredoc
# body holds a lone quote, and drops every later `cd`. The cwd is in no checkout, so the cd act does
# not refuse the cd below; the shared-tree rule reads the folder it moves to, and the restore runs in
# the shared checkout, so it must deny. A lone quote inside a shell `#` comment does not desync, so the
# python body keeps its quote outside any comment.
sh("per-file deny: node heredoc, a lone apostrophe in the body, then cd shared and restore f.txt",
   "node <<'EOF'\n// don't\nEOF\ncd " + slash(GITMAIN) + " && " + VCS + " restore f.txt",
   "deny", "shared-tree", cwd=NOGIT)
sh("per-file deny: python heredoc, a lone double quote in the body, then cd shared and restore",
   "python3 <<'EOF'\ntotal = \"\nEOF\ncd " + slash(GITMAIN) + " && " + VCS + " restore f.txt",
   "deny", "shared-tree", cwd=NOGIT)

# SYNC LOSS (fixture shape). When segment_roots (guard.py ~1228) loses sync with the segments,
# every later segment is judged as the shared checkout, so a later discard of a dirty file is denied.
# A cd into the shared checkout is refused by other-checkout, and so is a -C into it from a worktree, so
# each restore names the shared checkout with -C and denies as other-checkout, chained or not.
sh("per-file deny: two heredocs with lone apostrophes, then -C shared restore f.txt, cd lane last, from a worktree",
   "node <<'EOF'\nit's\nEOF\ncat <<EOF2\nwe're\nEOF2\n" + VCS + " -C " + slash(GITMAIN)
   + " restore f.txt\ncd " + slash(GITWT), "deny", "other-checkout", cwd=GITWT, lacks=(CHAIN_ASK,))
sh("per-file deny: the node lone-apostrophe case with -C shared restore, then && cd lane, from a worktree",
   "node <<'EOF'\n// don't\nEOF\n" + VCS + " -C " + slash(GITMAIN) + " restore f.txt && cd "
   + slash(GITWT), "deny", "other-checkout", cwd=GITWT, lacks=(CHAIN_ASK,))
# CONTROL. No heredoc, so the walk stays in sync, and the cd keeps the ask command. A leading cd is no
# second command (ask-commands-run-alone), so this asks. The case name keeps the first words that
# hooks/mutate_guard.py names for this case.
sh("per-file ask: cd lane && restore f.txt with no heredoc asks, the leading cd is no second command",
   "cd " + slash(GITWT) + " && " + VCS + " restore f.txt", "ask", "shared-tree", cwd=NOGIT,
   lacks=(CHAIN_ASK,))
# TWO -C TARGETS (one_place, `len(targets) <= 1`). No cd, both calls are per-file forms in a linked
# worktree, but they name two different trees (lane, and FARWT, a second linked worktree). other-checkout
# refuses the -C into FARWT, so the deny names that rule. FARWT holds b.txt dirty (the fixtures have no g.txt).
sh("per-file ask: two -C targets, lane then a second linked worktree, both per-file restores, denies by other-checkout",
   VCS + " -C " + slash(GITWT) + " restore f.txt && " + VCS + " -C " + slash(FARWT)
   + " restore b.txt", "deny", "other-checkout", cwd=GITWT)
# CONTROL. One -C target, repeated, no cd: the per-file allow stands.
sh("per-file allow: one -C target repeated, lane restore f.txt then lane restore b.txt",
   VCS + " -C " + slash(GITWT) + " restore f.txt && " + VCS + " -C " + slash(GITWT)
   + " restore b.txt", "allow", cwd=GITWT)
# TWO SPELLINGS OF ONE CHECKOUT (one_place, `len(targets) <= 1`). Both -C targets are the lane, once by its
# path and once by `.` (the cwd), so other-checkout stays quiet. They are two strings, so one_place reads two
# targets and both restores ask; two asks chained deny as ask-alone. The control above repeats one string.
chained_ask("per-file ask: two -C targets in one checkout, the lane by path then by ., both per-file restores, chained it denies",
            VCS + " -C " + slash(GITWT) + " restore f.txt && " + VCS + " -C . restore b.txt", cwd=GITWT)

# FIVE SHAPES THAT RUN A PER-FILE DISCARD IN THE SHARED CHECKOUT. Each one points the discard at
# the shared checkout while the shell, or a `-C` that names the lane, still reads as the lane. Each
# verdict is the one each row below pins: deny for all five (4 is a Set-Location move, read as a cd;
# 5 is an env -C or --chdir, read as the run folder, so other-checkout denies it as it denies git -C).
# Controls that stay allowed are pinned above: "per-file allow: restore of one modified file"
# (cwd lane) and "one -C target repeated".
# 1. --work-tree names the shared checkout, whatever -C says.
sh("per-file deny: -C lane with --work-tree naming the shared checkout, from a worktree",
   VCS + " -C " + slash(GITWT) + " --work-tree=" + slash(GITMAIN) + " restore f.txt",
   "deny", "shared-tree", cwd=GITWT)
# 2. A GIT_WORK_TREE setter in front of a per-file restore is denied by git-env-set, not asked.
# The setter rows sit in the git-env family, below the shared-tree section.
GIT_ENV_RULE = "git-env-set"
# 3. A segment with no -C must not borrow another segment's -C. From the shared checkout, the bare
# restore runs in the shared checkout whichever side the lane's -C status stands on. main asks the
# command; chained with the status, it denies as a chained ask command (ask-alone).
chained_ask("per-file ask: -C lane status, then a bare restore f.txt, from the shared checkout, denies as a chained ask command",
            VCS + " -C " + slash(GITWT) + " status && " + VCS + " restore f.txt", cwd=GITMAIN)
chained_ask("per-file ask: a bare restore f.txt, then -C lane status, from the shared checkout, denies as a chained ask command",
            VCS + " restore f.txt && " + VCS + " -C " + slash(GITWT) + " status", cwd=GITMAIN)
# 4. A PowerShell Set-Location into the shared checkout, from a cwd in no checkout. The cd act does not
# judge it there, so the shared-tree rule reads the folder it moved to and denies the restore.
# From a worktree, Set-Location and its aliases (sl, chdir, Push-Location) move into another checkout,
# which other-checkout refuses (worktree_home_cd_parse_forms_case).
sh("per-file deny: PowerShell Set-Location into the shared checkout, then restore f.txt, from a folder in no checkout",
   "Set-Location " + slash(GITMAIN) + "; " + VCS + " restore f.txt",
   "deny", "shared-tree", tool="PowerShell", cwd=NOGIT, lacks=(CHAIN_ASK,))
for _cd in ("sl", "chdir", "Push-Location"):
    sh("per-file ask: PowerShell %s into the shared checkout, then restore f.txt, from a worktree, denies by other-checkout"
       % _cd, _cd + " " + slash(GITMAIN) + "; " + VCS + " restore f.txt",
       "deny", "other-checkout", tool="PowerShell", cwd=GITWT)
# 5. env's own chdir flags. The guard reads env -C and env --chdir as the run folder, the folder git
# then runs in, so other-checkout denies each one as it denies a git -C into the shared checkout.
sh("per-file ask: env -C into the shared checkout, then restore f.txt, from a worktree, denies by other-checkout",
   "env -C " + slash(GITMAIN) + " " + VCS + " restore f.txt", "deny", "other-checkout", cwd=GITWT)
sh("per-file ask: env --chdir into the shared checkout, then restore f.txt, from a worktree, denies by other-checkout",
   "env --chdir=" + slash(GITMAIN) + " " + VCS + " restore f.txt", "deny", "other-checkout",
   cwd=GITWT)
# A `cd` after an `env -C` sets the folder the restore runs in, so the restore is judged in the shared
# checkout, as the plain `cd` form is. The control is the same chain without the env wrapper, which the
# reader already reads the way the rule needs, so it stays green.
sh("per-file deny: env -C into the lane, then cd into the shared checkout and restore f.txt, from a folder in no checkout, denies by shared-tree",
   "env -C " + slash(GITWT) + " " + VCS + " status && cd " + slash(GITMAIN) + " && " + VCS + " restore f.txt",
   "deny", "shared-tree", cwd=NOGIT, lacks=(CHAIN_ASK,))
sh("per-file deny: control, a plain status, then cd into the shared checkout and restore f.txt, from a folder in no checkout, denies by shared-tree",
   VCS + " status && cd " + slash(GITMAIN) + " && " + VCS + " restore f.txt",
   "deny", "shared-tree", cwd=NOGIT, lacks=(CHAIN_ASK,))
# A bare restore of the whole tree is a discard the lane's own dirty tracked file would lose, so it asks in the
# lane, and chained with a status it denies. The control is that chain with no env wrapper. The decision row puts
# an env -C on a clean checkout ahead of the status. The shell's folder stays the lane, so the restore must still
# deny. The verb is restore ., not restore f.txt: a restore of one modified file in the lane is allowed by design
# (the per-file allow rows), so that verb cannot tell the two readings apart.
chained_ask("per-file deny: control, a status and a bare restore of the whole tree in a lane with a dirty file, denies as a chained ask command",
            VCS + " status && " + VCS + " restore .", cwd=GITWT)
chained_ask("per-file deny: env -C into a clean checkout, then a bare restore of the whole tree in the lane, denies as a chained ask command",
            "env -C " + slash(SUBJCLEAN) + " " + VCS + " status && " + VCS + " restore .", cwd=GITWT)

# LATE PROBES (named "late probe", so MUTATE_ONLY="late probe" runs this block alone). Each runs a
# per-file restore in the shared checkout from the lane. env -vC is read as env -C, so other-checkout
# denies it. The --ch= abbreviation is not read as --chdir, so it still asks. The control stays allowed.
_SH = slash(GITMAIN)
sh("per-file ask: late probe, env -vC names the shared checkout, from a worktree, denies by other-checkout",
   "env -vC " + _SH + " " + VCS + " restore f.txt", "deny", "other-checkout", cwd=GITWT)
sh("per-file ask: late probe, env --ch= abbreviation names the shared checkout, from a worktree",
   "env --ch=" + _SH + " " + VCS + " restore f.txt", "ask", "shared-tree", cwd=GITWT)
sh("per-file allow: late probe control, a harmless GIT_TRACE prefix in the lane",
   "GIT_TRACE=1 " + VCS + " restore f.txt", "allow", cwd=GITWT)

# Kill cases for mutate_guard: a quoted refspec and a quoted force in a commit message are verdicts.
sh("per-file kill: a quoted refspec keeps its quotes, so a force push asks",
   VCS + " push origin \"+main\" \"x", "ask", cwd=GITWT)
sh("per-file kill: false alarm: --force quoted in a commit message stays allowed",
   VCS + " commit -m \"release git push --force notes\" \"x", "allow", cwd=GITWT)

# NORMAL COMMITS WITH AN ANSI-C MESSAGE ALLOW. The guard decodes a bash `$'...'` word before it reads a
# command (guard_core.decode_ansi_c), so each of these commits must still read as a plain commit.
sh("per-file allow: an ANSI-C commit message with an escaped quote allows",
   VCS + " commit -m $'it\\'s fine'", "allow", cwd=GITWT)
sh("per-file allow: an ANSI-C commit message over two lines allows",
   VCS + " commit -m $'line one\\nline two'", "allow", cwd=GITWT)
sh("per-file allow: an ANSI-C commit message naming git push --force as text allows",
   VCS + " commit -m $'release git push --force notes'", "allow", cwd=GITWT)
# THE FORM THAT ALLOWS, PINNED. A commit message whose quote never closes is a bash syntax error, so the
# shell runs nothing. push_text blanks the open quote's tail (_push_scan), so the quoted `git push --force`
# is text, not a push, and the call reads as a plain commit.
sh("per-file allow: a commit message whose quote never closes names git push --force, allows",
   VCS + " commit -m \"release git push --force notes", "allow", cwd=GITWT)

# THE AGENT-OWNED CARVE-OUT (owner ruling 2026-10-03, decision agent-worktree-discard-is-noted, section "Agent-owned worktree").
# A linked worktree under <repo>/.claude/worktrees/ is agent-owned: a discard there is ALLOWED,
# not asked (checked as a log/noted case below, since an allow prints nothing to assert on here).
# Near misses must still ask or deny, proven against real git state, not a path guess.
sh("agent worktree: a linked worktree elsewhere that merely says \"worktrees\" still asks",
   VCS + " reset --hard", "ask", "shared-tree", cwd=FARWT)
sh("agent worktree: checkout -- . in that near-miss worktree still asks",
   VCS + " checkout -- .", "ask", "shared-tree", cwd=FARWT)
sh("agent worktree: a textual .claude/worktrees/.. that resolves back outside still asks",
   VCS + " reset --hard", "ask", "shared-tree", cwd=DOTDOTWT)
if SYMWT_MADE:
    sh("agent worktree: a symlink into .claude/worktrees/ aliasing an outside worktree still asks",
       VCS + " reset --hard", "ask", "shared-tree", cwd=SYMWT)
sh("agent worktree: the main checkout nested under its own .claude/worktrees/-shaped path "
   "still denies", VCS + " reset --hard", "deny", "shared-tree", cwd=DECOYMAIN)
sh("agent worktree: a stash push there still denies, the stack is clone-wide",
   VCS + " stash push -u -m lane", "deny", "shared-tree", cwd=AGENTWT)
sh("agent worktree: a bare stash there still denies, the stack is clone-wide",
   VCS + " stash", "deny", "shared-tree", cwd=AGENTWT)

# THE PUSH ARM. `refs/stash` lives in the COMMON git directory (MEASURED above, next to
# SUBJSTASHWT), so a push from a worktree lands on the SAME one-entry-wide stack the primary
# checkout and every other lane share. The worktree "ask" that `reset --hard` and `restore` earn
# just above never applies to this arm: it is earned for a subject that lives in THIS tree
# alone, and a stash push's subject does not.
sh("worktree: a stash push in a dirty worktree denies, the stack is clone-wide",
   VCS + " stash push -u -m lane", "deny", "shared-tree", cwd=GITWT)
sh("worktree: stash save in a dirty worktree denies, the stack is clone-wide",
   VCS + " stash save lane", "deny", "shared-tree", cwd=GITWT)

# THE TABLE'S ROWS, checked in a linked worktree. A read, a reset that keeps the tree, or a
# restore of one staged file is allowed whichever tree the call runs in. A reset that moves the
# branch to another commit asks here, as `--hard` does.
sh("stash: list allows in the worktree", VCS + " stash list", "allow", cwd=GITWT)
sh("stash: show allows in the worktree", VCS + " stash show", "allow", cwd=GITWT)
sh("stash: apply over an empty stack allows in the worktree", VCS + " stash apply", "allow",
   cwd=GITWT)
sh("stash: pop over an empty stack allows in the worktree", VCS + " stash pop", "allow",
   cwd=GITWT)
sh("reset: a plain reset allows in the worktree", VCS + " reset HEAD~1", "allow", cwd=GITWT)
sh("reset: --soft allows in the worktree", VCS + " reset --soft HEAD~1", "allow", cwd=GITWT)
sh("reset: --keep at another commit asks in a dirty linked worktree",
   VCS + " reset --keep HEAD~1", "ask", "shared-tree", cwd=GITWT)
sh("reset: --merge at another commit asks in a dirty linked worktree",
   VCS + " reset --merge HEAD~1", "ask", "shared-tree", cwd=GITWT)
sh("reset: naming a path allows in the worktree", VCS + " reset -- f.txt", "allow", cwd=GITWT)
sh("restore: --staged alone allows in the worktree", VCS + " restore --staged f.txt", "allow",
   cwd=GITWT)

# THE PATH RESET AND DISCARD RULING. Three verdicts, pinned in the three trees:
#   A. A reset that names no discard flag keeps the work tree, so it allows everywhere.
#   B. A reset with --hard, --merge or --keep keeps today's verdict, path form included: deny in the
#      shared checkout, ask in a linked worktree, allow and noted in an agent-owned worktree.
#   C. A work-tree discard (checkout -- ., checkout -q -- .) takes the same three verdicts. Its restore
#      and checkout HEAD forms each have one home per tree. restore -- <path> and checkout HEAD -- .
#      take their shared and hand-made verdicts from RULING_TREE_FORMS, below, which is ruling D, and
#      their agent-owned note from AGENT_NOTED_RULING, below. restore . takes its shared and hand-made
#      verdicts from the per-file ASK and DENY blocks, above, and its agent-owned note from
#      AGENT_NOTED_RULING, below.
# The discard and path forms name f.txt, which _build_gitmain leaves tracked and dirty in all four trees.
# A path the fixture lacks would read as an empty subject and pass for the wrong reason. reset -q and
# reset -- . name no file: ruling A allows them whatever the subject, so they pin the flag-free verdict.
RULING_RESET_FORMS = ["reset HEAD -- f.txt", "reset -- f.txt", "reset -q HEAD f.txt", "reset f.txt",
                      "reset -q", "reset -- ."]
RULING_DISCARD_FORMS = ["reset --hard HEAD -- f.txt", "reset --merge HEAD -- f.txt",
                        "reset --keep HEAD -- f.txt", "checkout -- .", "checkout -q -- ."]
for _form in RULING_RESET_FORMS:
    sh("reset ruling A: %s allows in the shared checkout" % _form, VCS + " " + _form, "allow", cwd=GITMAIN)
    if _form != "reset -- f.txt":  # the same row, in the hand-made worktree, is the one above
        sh("reset ruling A: %s allows in the hand-made worktree" % _form, VCS + " " + _form, "allow",
           cwd=GITWT)
    sh("reset ruling A: %s allows in an agent-owned worktree" % _form, VCS + " " + _form, "allow",
       cwd=AGENTWT)
for _form in RULING_DISCARD_FORMS:
    sh("reset ruling B and C: %s denies in the shared checkout" % _form, VCS + " " + _form, "deny",
       "shared-tree", cwd=GITMAIN)
    sh("reset ruling B and C: %s asks in the hand-made worktree" % _form, VCS + " " + _form, "ask",
       "shared-tree", cwd=GITWT)
# The agent-owned rows of B and C are not plain allows. Each is allowed AND logged once as noted/shared-tree, and
# an allow prints nothing, so only the log helper proves the note. Those checks register at the foot of this file.
AGENT_NOTED_RULING = [
    ("log: reset --hard HEAD -- f.txt is allowed and noted in an agent-owned worktree",
     VCS + " reset --hard HEAD -- f.txt"),
    ("log: reset --merge HEAD -- f.txt is allowed and noted in an agent-owned worktree",
     VCS + " reset --merge HEAD -- f.txt"),
    ("log: reset --keep HEAD -- f.txt is allowed and noted in an agent-owned worktree",
     VCS + " reset --keep HEAD -- f.txt"),
    ("log: checkout -- . is allowed and noted in an agent-owned worktree", VCS + " checkout -- ."),
    ("log: checkout -q -- . is allowed and noted in an agent-owned worktree", VCS + " checkout -q -- ."),
    ("log: restore . is allowed and noted in an agent-owned worktree", VCS + " restore ."),
    ("log: restore -- hooks/guard.py is allowed and noted in an agent-owned worktree",
     VCS + " restore -- hooks/guard.py"),
    ("log: checkout HEAD -- . is allowed and noted in an agent-owned worktree",
     VCS + " checkout HEAD -- ."),
]

# THE RESTORE AND CHECKOUT FORMS, one verdict per tree. The path is hooks/guard.py: _build_gitmain
# leaves it tracked and dirty in every tree. None means the agent-owned log row above pins that cell.
RULING_TREE_FORMS = [
    ("restore -- hooks/guard.py", ("deny", "shared-tree"), ("allow", None), None),
    ("restore --staged hooks/guard.py", ("allow", None), ("allow", None), ("allow", None)),
    ("restore --staged .", ("allow", None), ("allow", None), ("allow", None)),
    ("checkout HEAD -- .", ("deny", "shared-tree"), ("ask", "shared-tree"), None),
]
for _form, _shared, _hand, _agent in RULING_TREE_FORMS:
    for _tree, _cwd, _verdict in (("shared", GITMAIN, _shared), ("hand-made", GITWT, _hand),
                                  ("agent-owned", AGENTWT, _agent)):
        if _verdict is None:
            continue
        _decision, _rule = _verdict
        sh("reset ruling D: %s in the %s tree" % (_form, _tree), VCS + " " + _form, _decision, _rule,
           cwd=_cwd)

# THE OWNER'S EXACT COMMAND, carrying a redirect and a pipe into `tail`. `tail -10` is not a
# follow, so it must not trip the live-stream rule either. Both stacks are empty, so the allow
# here proves the redirect and the pipe are read, not that the act is safe: the SUBJSTASH rows
# above hold the same command against a stack that really carries an entry.
sh("stash: the owner's exact apply command over an empty stack allows in the shared checkout",
   VCS + " stash apply stash@{0} 2>&1 | tail -10", "allow", cwd=GITMAIN)

# A COMMIT MESSAGE DISCUSSES THESE COMMANDS. MEASURED in job-cost-reporting on 2026-08-20: a
# heredoc body was read as a command, and a commit message naming the protected folder was refused.
sh("heredoc: a commit message that discusses the refused commands",
   VCS + " commit -F - <<'EOF'\n"
   "guard: refuse the reset, the restore and the stash in a shared tree\n"
   "also refuse pkill -f and lsof -t, which reach the whole machine\n"
   "EOF",
   "allow", cwd=NOGIT)
sh("heredoc: prose naming the stash with no interpreter",
   "cat > notes.md <<'DOC'\nNever run " + VCS + " stash in a shared checkout.\nDOC",
   "allow", cwd=NOGIT)
sh("heredoc: a body fed to a shell stays under inspection",
   "bash <<EOF\n" + VCS + " stash\nEOF", "deny", "shared-tree", cwd=NOGIT)
# A DENY IN A PYTHON BODY STILL DENIES, one command or not (owner ruling 2026-10-14 22:25). The delimiter
# `E-F` is read as the whole word. HEREDOC_HEADER reads `E` alone, so the cat case below holds no closer:
# its body runs to the end, is dropped, and the stash after it is never judged.
sh("heredoc: a stash push in a python body still denies, in one command",
   "python3 - <<'PY'\n" + VCS + " stash push -u -m lane\nPY", "deny", "shared-tree", cwd=GITWT,
   carries="stash stack")
# An interpreter word that ends a name (`ts-node`, `node.cmd`) keeps its body in view too: INTERPRETER_HEREDOC
# reads the word after `-` and before `.cmd`. The impeccable rule reads only shell bodies, so a stash is the probe.
for _header in ("ts-node -", "babel-node -", "git-bash.exe -c", "node.cmd -"):
    sh("heredoc: a stash push in a %s body still denies" % _header.split()[0],
       _header + " <<'PY'\n" + VCS + " stash push -u -m lane\nPY", "deny", "shared-tree", cwd=GITWT,
       carries="stash stack")
sh("heredoc: a python heredoc with the delimiter E-F, then a stash push, still denies",
   "python3 - <<E-F\nx = 1\nE-F\n" + VCS + " stash push -u -m lane", "deny", "shared-tree", cwd=GITWT,
   carries="stash stack")
sh("heredoc: a cat heredoc with the delimiter E-F, then a stash push, denies",
   "cat <<E-F\nx\nE-F\n" + VCS + " stash push -u -m lane", "deny", "shared-tree", cwd=GITWT,
   carries="stash stack")


# H1: a python body under a backslash, single-quoted or double-quoted delimiter, closed at EOF,
# then a stash push. The python body stays in view.
for _label, _open in (("backslash", "E\\OF"), ("single-quoted", "E'OF'"), ("double-quoted", '"E"OF')):
    sh("heredoc: r1-hd a python heredoc, %s delimiter closed at EOF, then a stash push, denies" % _label,
       "python3 - <<" + _open + "\nx\nEOF\n" + VCS + " stash push -u -m lane", "deny", "shared-tree",
       cwd=GITWT, carries="stash stack")
# H2: a cat heredoc piped to a shell, closer EOF-X. The stash push is in the body, which the shell runs.
for _shell in ("sh", "bash"):
    sh("heredoc: r1-hd a cat heredoc piped to %s, closer EOF-X, a stash push in the body, denies" % _shell,
       "cat <<EOF-X | " + _shell + "\nx\nEOF\n" + VCS + " stash push -u -m lane\nEOF-X", "deny", "shared-tree",
       cwd=GITWT, carries="stash stack")


# `--work-tree` NAMES THE TREE WHOSE FILES A CALL DISCARDS. MEASURED 2026-09-19 with real git:
# from a CLEAN checkout, `git --work-tree=<dirty> status --porcelain` reported the OTHER tree's
# modified and untracked files. So rule 1 judges the named tree, not the one the call runs in.
# BOTH DIRECTIONS: a clean cwd pointed at a dirty tree must deny, and a dirty cwd pointed at a
# clean tree must pass, or the option is only half read.
sh("work-tree: a clean cwd pointed at a dirty tree is judged on the dirty tree",
   VCS + " --work-tree=" + slash(SUBJDIRTY) + " reset --hard", "deny", "shared-tree",
   cwd=SUBJCLEAN)
sh("work-tree: a dirty cwd pointed at a clean tree passes on the empty subject",
   VCS + " --work-tree=" + slash(SUBJCLEAN) + " reset --hard", "allow", cwd=SUBJDIRTY)
sh("work-tree: the spaced form is read the same way",
   VCS + " --work-tree " + slash(SUBJDIRTY) + " reset --hard", "deny", "shared-tree",
   cwd=SUBJCLEAN)

# A git act hides behind a glued `(git` or `$(git`, or a heredoc header in quoted text, a comment or a here-string.
for _name, _command in (
    ("a glued subshell before reset", "(" + VCS + " reset --hard origin/main)"),
    ("a glued subshell before stash", "(" + VCS + " stash push -u -m lane)"),
    ("a dollar paren before stash", "$(" + VCS + " stash push -u -m lane)"),
    ("a dollar paren inside echo before reset", "echo $(" + VCS + " reset --hard origin/main)"),
    ("a here-string header before reset", "cat <<<word\n" + VCS + " reset --hard origin/main"),
    ("a here-string header before stash", "cat <<<word\n" + VCS + " stash push -u -m lane"),
    ("a quoted header before reset", 'echo "<<EOF"\n' + VCS + " reset --hard origin/main"),
    ("a single-quoted header before stash", "echo '<<X'\n" + VCS + " stash push -u -m lane"),
    ("a comment opener in quotes before a quoted header",
     'echo "# <<EOF"\n' + VCS + " reset --hard origin/main"),
    ("a commented header before reset", "# note <<EOF\n" + VCS + " reset --hard origin/main"),
    ("a multi-line quoted text holding a header before reset",
     'echo "first\n<<EOF"\n' + VCS + " reset --hard origin/main"),
):
    sh("guard-command-position: %s denies" % _name, _command, "deny", "shared-tree", cwd=NOGIT)
for _name, _command in (
    ("an env value flag", "env -u X " + VCS + " reset --hard origin/main"),
    ("a nice value flag", "nice -n 5 " + VCS + " reset --hard origin/main"),
    ("a sudo value flag", "sudo -u root " + VCS + " reset --hard origin/main"),
    ("an xargs value flag", "xargs -n 1 " + VCS + " stash push -u -m lane"),
    ("time -p", "time -p " + VCS + " reset --hard origin/main"),
    ("exec", "exec " + VCS + " reset --hard origin/main"),
    ("builtin exec", "builtin exec " + VCS + " reset --hard origin/main"),
    ("a leading bang", "! " + VCS + " reset --hard origin/main"),
    ("a spaced subshell", "( " + VCS + " reset --hard origin/main )"),
    ("a brace group", "{ " + VCS + " stash push -u -m lane; }"),
    ("an assignment prefix", "FOO=1 " + VCS + " reset --hard origin/main"),
    ("a heredoc body, then a reset after its delimiter",
     "cat <<EOF\n" + VCS + " reset --hard origin/main\nEOF\n" + VCS + " reset --hard origin/main"),
    ("a comment opener in quotes before a reset", 'echo "# note"; ' + VCS + " reset --hard origin/main"),
    ("a lone apostrophe on the line before a reset", "echo don't\n" + VCS + " reset --hard origin/main"),
    ("a multi-line quoted text before a reset", 'echo "first\nline"\n' + VCS + " reset --hard origin/main"),
):
    sh("guard-command-position: pinned, %s denies" % _name, _command, "deny", "shared-tree",
       cwd=NOGIT)
for _name, _command in (
    ("an env value flag before status", "env -u X " + VCS + " status"),
    ("a nice value flag before status", "nice -n 5 " + VCS + " status"),
    ("a sudo value flag before status", "sudo -u root " + VCS + " status"),
    ("a glued subshell around status", "(" + VCS + " status)"),
    ("a dollar paren around status", "echo $(" + VCS + " status)"),
    ("a heredoc body that names a reset, then status",
     "cat <<EOF\n" + VCS + " reset --hard origin/main\nEOF\n" + VCS + " status"),
    ("a multi-line quoted text, then status", 'echo "first\nline"\n' + VCS + " status"),
    ("a lone apostrophe on the line before status", "echo don't\n" + VCS + " status"),
):
    sh("guard-command-position: pinned, %s allowed" % _name, _command, "allow", cwd=NOGIT)

# SUBSTITUTION. The shell runs a command inside `$( )` or backticks, in any word, assignment, double-quoted
# text, commit message or unquoted heredoc body, so each form denies the reset as the plain reset does.
for _name, _command in (
    ("an assignment from a dollar paren", "x=$(" + VCS + " reset --hard)"),
    ("a dollar paren in an echo", "echo $(" + VCS + " reset --hard)"),
    ("backticks in an echo", "echo `" + VCS + " reset --hard`"),
    ("backticks in an assignment", "x=`" + VCS + " reset --hard`"),
    ("a dollar paren in double quotes", 'echo "$(' + VCS + ' reset --hard)"'),
    ("a dollar paren in a commit message", VCS + ' commit -m "note: $(' + VCS + ' reset --hard)"'),
    ("a dollar paren after a hash in double quotes", 'echo "# $(' + VCS + ' reset --hard)"'),
    ("a dollar paren on line 2 of a multi-line double-quoted text",
     'echo "first line\n$(' + VCS + ' reset --hard)\nlast line"'),
    ("a dollar paren in an unquoted heredoc body", "cat <<EOF\n$(" + VCS + " reset --hard)\nEOF"),
):
    sh("substitution: shared tree, %s denies" % _name, _command, "deny", "shared-tree", cwd=NOGIT)
# ALLOW controls: a quoted or escaped `$(` is text, a quoted heredoc body is text, and a commit message
# that names a reset is text. A reader that judges inner text naively would deny each of these.
for _name, _command in (
    ("single quotes hold a dollar paren", "echo '$(" + VCS + " reset --hard)'"),
    ("an escaped dollar sign", "echo \\$(" + VCS + " reset --hard)"),
    ("single quotes hold a hash and a dollar paren", "echo '# $(" + VCS + " reset --hard)'"),
    ("a quoted heredoc body holds a dollar paren", "cat <<'EOF'\n$(" + VCS + " reset --hard)\nEOF"),
    ("a commit message from a quoted heredoc names a reset",
     VCS + ' commit -m "$(cat <<\'EOF\'\nfix: never run ' + VCS + ' reset --hard here\nEOF\n)"'),
    ("a commit message in double quotes names a reset", VCS + ' commit -m "never run ' + VCS + ' reset --hard"'),
):
    sh("substitution: shared tree, %s allowed" % _name, _command, "allow", cwd=NOGIT)
# HASH. An unquoted `#` opens a comment only at a word start. After a letter, a slash, a brace, a dollar
# sign or an escaped space it is text, so the `$( )` that follows still runs. A reader that takes every
# `#` as a comment lets each of these through.
for _name, _command in (
    ("a hash in a dollar brace array length", "echo ${#arr[@]} $(" + VCS + " reset --hard)"),
    ("a hash after a letter", "echo a#$(" + VCS + " reset --hard)"),
    ("a dollar hash", "echo $# $(" + VCS + " reset --hard)"),
    ("a hash in a URL fragment", "curl https://x/#$(" + VCS + " reset --hard)"),
    ("an escaped space before a hash", "echo a\\ #$(" + VCS + " reset --hard)"),
):
    sh("substitution: shared tree, %s denies" % _name, _command, "deny", "shared-tree", cwd=NOGIT)
# ALLOW control: a hash at a word start is a real comment, so the `$( )` after it is text.
sh("substitution: shared tree, a hash at a word start allowed", "echo hi #$(" + VCS + " reset --hard)",
   "allow", cwd=NOGIT)


# ============================================================ 1. branch delete / worktree remove/prune

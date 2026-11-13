# section 18211
FAMILY = "frozen"
#
# Ported from q_max, with that repository's own two frozen paths replaced by the global set. The
# file-tool check is the WALL: an exact resolved path, and no heuristics. The shell check is a
# backstop over it, and a backstop that reads a command as one blob cannot tell a write from a
# mention, so both directions are pinned below.

for tool in ("Write", "Edit", "MultiEdit"):
    add("frozen: " + tool + " of the config settings", "deny", "frozen-path", tool=tool, cwd=NOGIT,
        file_path=CFG_SETTINGS)
    add("config-edit: " + tool + " of a project settings file is allowed", "allow", tool=tool,
        cwd=NOGIT, file_path=PROJ_SETTINGS)
add("frozen: Write of the global CLAUDE.md", "deny", "frozen-path", tool="Write", cwd=NOGIT,
    file_path=CFG_CLAUDEMD)
add("frozen: Write of a config hook", "deny", "frozen-path", tool="Write", cwd=NOGIT,
    file_path=CFG_HOOK)
add("frozen: Write of a config lint script", "deny", "frozen-path", tool="Write", cwd=NOGIT,
    file_path=CFG_LINT)
add("frozen: Write of a config agent file", "deny", "frozen-path", tool="Write", cwd=NOGIT,
    file_path=CFG_AGENT)
# docs/design/ holds the house rules (decision ux-house-rules). A session that could rewrite them could
# loosen its own review bar, so it is frozen like agents/ and output-styles/. It is two levels deep, so
# its siblings under docs/, a name that only starts with "design", and a product repo's own copy stay open.
CFG_DESIGN = slash(os.path.join(CFG, "docs", "design", "principles.md"))
PROJ_DESIGN = slash(os.path.join(PROJ, "docs", "design", "principles.md"))
for tool in ("Write", "Edit"):
    add("frozen: " + tool + " of the config docs/design house rules", "deny", "frozen-path", tool=tool,
        cwd=NOGIT, file_path=CFG_DESIGN)
add("frozen: Write under the config docs/ beside docs/design is allowed", "allow", tool="Write",
    cwd=NOGIT, file_path=slash(os.path.join(CFG, "docs", "notes.md")))
add("frozen: Write under a config docs/designer folder is allowed", "allow", tool="Write",
    cwd=NOGIT, file_path=slash(os.path.join(CFG, "docs", "designer", "a.md")))
add("frozen: Write of the retired config ux folder is allowed", "allow", tool="Write",
    cwd=NOGIT, file_path=slash(os.path.join(CFG, "ux", "principles.md")))
add("frozen: Edit of a product repo's own docs/design/principles.md is allowed", "allow", tool="Edit",
    cwd=PROJ, file_path=PROJ_DESIGN)
add("frozen: Write of a skill this repo ships", "deny", "frozen-path", tool="Write", cwd=NOGIT,
    file_path=CFG_SKILL)
add("frozen: Write of a skill this repo does not ship is allowed", "allow", tool="Write",
    cwd=NOGIT, file_path=CFG_OWN_SKILL)
add("frozen: Write of the config-watch baseline store", "deny", "frozen-path", tool="Write",
    cwd=NOGIT, file_path=CFG_STATE)
# `cp` onto the store carries no readable value, so rule 8 would stay silent. Rule 7 needs only the
# PATH, which is why the store is frozen rather than merely watched.
sh("frozen: cp onto the config-watch baseline store", "cp /tmp/x.json " + CFG_STATE, "deny",
   "frozen-path", cwd=NOGIT)
sh("frozen: sed -i on the config-watch baseline store", "sed -i '' s/a/b/ " + CFG_STATE, "deny",
   "frozen-path", cwd=NOGIT)
# A real newline inside a quoted argument does not split the command: the sed -i and the frozen path it names
# stay one write.
sh("frozen: sed -i with a newline in its quoted script, onto the frozen settings",
   "sed -i '1i\\\ntext' " + CFG_SETTINGS, "deny", "frozen-path", cwd=NOGIT)
add("frozen: Read of the config-watch baseline store is allowed", "allow", tool="Read",
    cwd=NOGIT, file_path=CFG_STATE)
# OWNER RULING 2026-10-17 11:40 CDT: `cp` FROM a frozen path to a path outside the frozen set only
# reads the frozen file, so it is allowed. A copy INTO a frozen path, a copy between two frozen
# paths and a `mv` of a frozen file stay denied: `mv` takes the file away, and a copy writes into
# the frozen set.
sh("frozen: cp FROM a frozen hook to scratch is a read", "cp " + CFG_HOOK + " /tmp/guard.bak",
   "allow", cwd=NOGIT)
sh("frozen: cp FROM the frozen settings to scratch is a read",
   "cp " + CFG_SETTINGS + " /tmp/settings.copy", "allow", cwd=NOGIT)
# A loop keyword or a wrapper in front of `cp` changes nothing: the copy still reads its source and
# still writes its destination. Each deny is the matching allow with the frozen path moved to DEST.
sh("frozen: cp FROM a frozen hook to scratch after a loop keyword is a read",
   "for f in a; do cp " + CFG_HOOK + " ./x; done", "allow", cwd=NOGIT)
sh("frozen: sudo cp FROM a frozen hook to scratch is a read",
   "sudo cp " + CFG_HOOK + " ./x", "allow", cwd=NOGIT)
sh("frozen: env cp FROM a frozen hook to scratch is a read",
   "env cp " + CFG_HOOK + " ./x", "allow", cwd=NOGIT)
sh("frozen: cp TO a frozen hook after a loop keyword still denies",
   "for f in a; do cp x " + CFG_HOOK + "; done", "deny", "frozen-path", cwd=NOGIT)
sh("frozen: sudo cp TO a frozen hook still denies", "sudo cp x " + CFG_HOOK, "deny",
   "frozen-path", cwd=NOGIT)
sh("frozen: env cp TO a frozen hook still denies", "env cp x " + CFG_HOOK, "deny",
   "frozen-path", cwd=NOGIT)
sh("frozen: cp TO a frozen hook still denies", "cp /tmp/x.py " + CFG_HOOK, "deny", "frozen-path",
   cwd=NOGIT)
sh("frozen: cp from a frozen path TO a frozen path still denies",
   "cp " + CFG_HOOK + " " + CFG_SETTINGS, "deny", "frozen-path", cwd=NOGIT)
sh("frozen: mv FROM a frozen hook still denies", "mv " + CFG_HOOK + " /tmp/guard.bak", "deny",
   "frozen-path", cwd=NOGIT)
# A LINK IS NOT A COPY. `cp -l` and `cp -s` (also `-a` with either, and the long forms) make a hard or
# symbolic link to the frozen file, so a later write to the new name writes the frozen file. Only a
# plain copy reads its source.
sh("frozen: cp -al FROM a frozen hook makes a link, and stays denied",
   "cp -al " + CFG_HOOK + " /tmp/x", "deny", "frozen-path", cwd=NOGIT)
sh("frozen: cp -l FROM a frozen hook makes a hard link, and stays denied",
   "cp -l " + CFG_HOOK + " /tmp/x", "deny", "frozen-path", cwd=NOGIT)
sh("frozen: cp --link FROM a frozen hook stays denied",
   "cp --link " + CFG_HOOK + " /tmp/x", "deny", "frozen-path", cwd=NOGIT)
sh("frozen: cp -s FROM a frozen hook makes a symbolic link, and stays denied",
   "cp -s " + CFG_HOOK + " /tmp/x", "deny", "frozen-path", cwd=NOGIT)
sh("frozen: cp --symbolic-link FROM a frozen hook stays denied",
   "cp --symbolic-link " + CFG_HOOK + " /tmp/x", "deny", "frozen-path", cwd=NOGIT)
# A HARD LINK TO A DIRECTORY LINKS EACH FILE IN IT. `cp -al` of the config directory (the test's
# stand-in for ~/.claude) or `cp -Rl` of its hooks folder gives /tmp/x the frozen files themselves.
sh("frozen: cp -al of the config directory makes links into it, and stays denied",
   "cp -al " + slash(CFG) + " /tmp/x", "deny", "frozen-path", cwd=NOGIT)
sh("frozen: cp -Rl of the frozen hooks folder makes links, and stays denied",
   "cp -Rl " + slash(os.path.join(CFG, "hooks")) + " /tmp/x", "deny", "frozen-path", cwd=NOGIT)
# A redirect of stderr to the null device writes no frozen file. A redirect onto one still denies.
sh("frozen: cp FROM a frozen hook with stderr sent to /dev/null is a read",
   "cp " + CFG_HOOK + " /tmp/g 2>/dev/null", "allow", cwd=NOGIT)
sh("frozen: cp FROM a frozen hook, with a redirect onto a frozen hook, still denies",
   "cp " + CFG_HOOK + " /tmp/g > " + CFG_HOOK, "deny", "frozen-path", cwd=NOGIT)
# A line break inside a quoted operand is part of one word, so the frozen file after it is still the
# target of the write, whichever command carries the quoted text.
sh("frozen: sed -i whose quoted a-text script holds a line break still denies a frozen hook",
   "sed -i '/^x/a\\\nnew line' " + CFG_HOOK, "deny", "frozen-path", cwd=NOGIT)
sh("frozen: sed -i -e whose quoted i-text script holds a line break still denies a frozen hook",
   "sed -i -e '1i\\\nimport os' " + CFG_HOOK, "deny", "frozen-path", cwd=NOGIT)
sh("frozen: cp whose quoted source spans two lines still denies onto a frozen hook",
   "cp '/tmp/a\nb.py' " + CFG_HOOK, "deny", "frozen-path", cwd=NOGIT)

# THE LIVE PINNED CHECKOUT IS FROZEN. Owner ruling (decision merge-reinstalls-from-main, ruling 1:
# no work runs in the pinned checkout). The pin is `<clone>-live`, and each move leaves a stamped
# worktree `<clone>-live-<12 hex>`. The links in ~/.claude load from it, so a write into either one
# changes what every session runs. The fixture clone is CLONE, so its pin is ROOT/clone-live.
# ONLY THE TREE THE PIN LINKS TO IS FROZEN. install_from_main.sh makes `<clone>-live` a link to the
# current stamped tree, and the trees before it stay on disk until pruned. OLD_PIN is one of those.
LIVE_PIN = CLONE + "-live"
STAMPED_PIN = CLONE + "-live-abcdef123456"
OLD_PIN = CLONE + "-live-111111111111"
LIVE_CLAUDEMD = slash(os.path.join(LIVE_PIN, "CLAUDE.md"))
STAMPED_GUARD = slash(os.path.join(STAMPED_PIN, "hooks", "guard.py"))
OLD_GUARD = slash(os.path.join(OLD_PIN, "hooks", "guard.py"))
write(STAMPED_GUARD, "# pinned\n")
write(OLD_GUARD, "# old\n")
try:
    os.symlink(STAMPED_PIN, LIVE_PIN)
    PIN_LINKED = True
except OSError:
    PIN_LINKED = False   # no link rights: the pin is a plain folder, and the link cases do not run
write(LIVE_CLAUDEMD, "# pinned\n")
add("frozen: Write of the live pinned checkout's CLAUDE.md", "deny", "frozen-path", tool="Write",
    cwd=NOGIT, file_path=LIVE_CLAUDEMD, content="rules\n")
add("frozen: Edit of the live pinned checkout's CLAUDE.md", "deny", "frozen-path", tool="Edit",
    cwd=NOGIT, file_path=LIVE_CLAUDEMD, old_string="# pinned", new_string="# rewritten")
if PIN_LINKED:
    add("frozen: Write of a hook in the stamped tree the pin links to", "deny", "frozen-path",
        tool="Write", cwd=NOGIT, file_path=STAMPED_GUARD, content="# rewritten\n")
    sh("frozen: sed -i on a hook in the stamped tree the pin links to",
       "sed -i '' s/a/b/ " + STAMPED_GUARD, "deny", "frozen-path", cwd=NOGIT)
sh("frozen: sed -i on the live pinned checkout's CLAUDE.md", "sed -i '' s/a/b/ " + LIVE_CLAUDEMD,
   "deny", "frozen-path", cwd=NOGIT)
sh("frozen: a redirect onto the live pinned checkout's CLAUDE.md", "echo rules > " + LIVE_CLAUDEMD,
   "deny", "frozen-path", cwd=NOGIT)
sh("frozen: cp onto the live pinned checkout's CLAUDE.md", "cp /tmp/x.md " + LIVE_CLAUDEMD,
   "deny", "frozen-path", cwd=NOGIT)
sh("frozen: mv FROM the live pinned checkout's CLAUDE.md still denies",
   "mv " + LIVE_CLAUDEMD + " /tmp/live.md", "deny", "frozen-path", cwd=NOGIT)
# A copy OUT of the pin reads it, the same as the copy-out rule above.
sh("frozen: cp OUT of the live pinned checkout to scratch is a read",
   "cp " + LIVE_CLAUDEMD + " /tmp/live.md", "allow", cwd=NOGIT)
add("frozen: Read of the live pinned checkout's CLAUDE.md is allowed", "allow", tool="Read",
    cwd=NOGIT, file_path=LIVE_CLAUDEMD)
# NOT THE PIN: the clone itself, a folder whose name only starts with the pin's name, a `-live`
# folder that belongs to no clone, and a `-live-` folder whose tail is not 12 hex.
add("frozen: an edit in the clone itself is allowed", "allow", tool="Edit", cwd=CLONE,
    file_path=slash(os.path.join(CLONE, "CLAUDE.md")), old_string="rules", new_string="rewritten")
sh("frozen: sed -i on the clone's own CLAUDE.md is allowed",
   "sed -i '' s/a/b/ " + slash(os.path.join(CLONE, "CLAUDE.md")), "allow", cwd=NOGIT)
add("frozen: an edit in claude-settings-livestock is allowed", "allow", tool="Edit", cwd=NOGIT,
    file_path=slash(os.path.join(ROOT, "clone-livestock", "CLAUDE.md")),
    old_string="a", new_string="b")
add("frozen: an edit in an unrelated folder named -live is allowed", "allow", tool="Edit",
    cwd=NOGIT, file_path=slash(os.path.join(ROOT, "other-live", "CLAUDE.md")),
    old_string="a", new_string="b")
add("frozen: an edit in a -live folder whose tail is not 12 hex is allowed", "allow", tool="Edit",
    cwd=NOGIT, file_path=slash(os.path.join(ROOT, "clone-live-scratch", "CLAUDE.md")),
    old_string="a", new_string="b")
# THE RECOVERY PATH STAYS OPEN. A broken pin is repaired by running the install by hand, or by
# running the merge tool, so neither may depend on the pin being healthy
# (verification-recovery-independent-of-state). Each runs from the clone, and each from the pin itself.
sh("recovery: merge/install_from_main.sh run by hand from the clone is allowed",
   "bash merge/install_from_main.sh", "allow", cwd=CLONE)
sh("recovery: merge/install_from_main.sh run by hand from the live pin is allowed",
   "bash merge/install_from_main.sh", "allow", cwd=LIVE_PIN)
sh("recovery: the merge tool run from the clone is allowed", "python3 bin/merge 12 --confirm",
   "allow", cwd=CLONE)
sh("recovery: the merge tool run from the live pin is allowed", "python3 bin/merge 12 --confirm",
   "allow", cwd=LIVE_PIN)
# A STAMPED TREE NO LINK POINTS AT IS NOT FROZEN. install_from_main.sh says "move it aside" when a
# tree is in the way (move_pin), and prune_trees removes the old ones. Neither may be blocked.
sh("recovery: mv of an old stamped tree that no link points at is allowed",
   "mv " + OLD_PIN + " /tmp/aside", "allow", cwd=NOGIT)
sh("recovery: rm -rf of an old stamped tree that no link points at is allowed",
   "rm -rf " + OLD_PIN, "allow", cwd=NOGIT)
# A FOLDER IS A PIN ONLY WHEN ITS SIBLING CLONE HOLDS merge/install_from_main.sh, the script that
# makes the pin (orchestrator call, 2026-10-17). The two marker files alone do not make one, so a
# sibling with only settings.json, or only install.ps1, leaves `X-live` editable.
write(os.path.join(ROOT, "clonea", "settings.json"), "{}\n")
write(os.path.join(ROOT, "clonea-live", "CLAUDE.md"), "# not a pin\n")
write(os.path.join(ROOT, "cloneb", "install.ps1"), "# install\n")
write(os.path.join(ROOT, "cloneb-live", "CLAUDE.md"), "# not a pin\n")
write(os.path.join(ROOT, "clonec", "settings.json"), "{}\n")
write(os.path.join(ROOT, "clonec", "install.ps1"), "# install\n")
write(os.path.join(ROOT, "clonec-live", "CLAUDE.md"), "# not a pin\n")
write(os.path.join(ROOT, "cloned", "merge", "install_from_main.sh"), "# install\n")
write(os.path.join(ROOT, "cloned-live", "CLAUDE.md"), "# pinned\n")
add("frozen: Write of X-live beside a clone with only settings.json stays editable", "allow",
    tool="Write", cwd=NOGIT, file_path=slash(os.path.join(ROOT, "clonea-live", "CLAUDE.md")),
    content="rules\n")
add("frozen: Write of X-live beside a clone with only install.ps1 stays editable", "allow",
    tool="Write", cwd=NOGIT, file_path=slash(os.path.join(ROOT, "cloneb-live", "CLAUDE.md")),
    content="rules\n")
add("frozen: Write of X-live beside a clone with both markers and no install script stays editable",
    "allow", tool="Write", cwd=NOGIT,
    file_path=slash(os.path.join(ROOT, "clonec-live", "CLAUDE.md")), content="rules\n")
add("frozen: Write of X-live beside a clone that holds merge/install_from_main.sh is frozen",
    "deny", "frozen-path", tool="Write", cwd=NOGIT,
    file_path=slash(os.path.join(ROOT, "cloned-live", "CLAUDE.md")), content="rules\n")

# THE MAIN MIRROR IS FROZEN. A cloud install takes its files from $HOME/claude-settings-main when the session
# checkout is on a branch, dirty or at a commit main lacks (use_main_mirror in install.sh). Those files land in
# the config directory as links into the mirror, so a write there changes what every session runs, as for the
# live pin. A git command in it is allowed, as for the pin, because install.sh refreshes the mirror with git. The
# clone and a sibling folder whose name only starts with the mirror's name are not frozen. Each case runs with
# HOME set to MIRROR_HOME, because the mirror is read from the HOME the guard run sees.
MIRROR_HOME = slash(os.path.join(ROOT, "mirrorhome"))
MIRROR_ENV = {"HOME": MIRROR_HOME, "USERPROFILE": MIRROR_HOME}
MIRROR = slash(os.path.join(MIRROR_HOME, "claude-settings-main"))
MIRROR_CLAUDEMD = slash(os.path.join(MIRROR, "CLAUDE.md"))
MIRROR_HOOK = slash(os.path.join(MIRROR, "hooks", "guard.py"))
CLONE_IN_HOME = slash(os.path.join(MIRROR_HOME, "claude-settings", "CLAUDE.md"))
MAINLINE_IN_HOME = slash(os.path.join(MIRROR_HOME, "claude-settings-mainline", "CLAUDE.md"))
write(MIRROR_CLAUDEMD, "# mirror\n")
write(MIRROR_HOOK, "# mirror\n")
write(CLONE_IN_HOME, "# clone\n")
write(MAINLINE_IN_HOME, "# sibling\n")
add("frozen mirror: Write of the mirror's CLAUDE.md is refused", "deny", "frozen-path", tool="Write",
    cwd=NOGIT, file_path=MIRROR_CLAUDEMD, content="rules\n", env=MIRROR_ENV)
add("frozen mirror: Write of a hook in the mirror is refused", "deny", "frozen-path", tool="Write",
    cwd=NOGIT, file_path=MIRROR_HOOK, content="# rewritten\n", env=MIRROR_ENV)
sh("frozen mirror: sed -i on the mirror's CLAUDE.md is refused", "sed -i '' s/a/b/ " + MIRROR_CLAUDEMD,
   "deny", "frozen-path", cwd=NOGIT, env=MIRROR_ENV)
sh("frozen mirror: a redirect onto the mirror's CLAUDE.md is refused", "echo rules > " + MIRROR_CLAUDEMD,
   "deny", "frozen-path", cwd=NOGIT, env=MIRROR_ENV)
sh("frozen mirror: git fetch from the mirror is allowed", "git fetch origin main 2>&1 | tail -1",
   "allow", cwd=MIRROR, env=MIRROR_ENV)
add("frozen mirror: Write of the clone's CLAUDE.md beside the mirror is allowed", "allow", tool="Write",
    cwd=NOGIT, file_path=CLONE_IN_HOME, content="rules\n", env=MIRROR_ENV)
add("frozen mirror: Write of a sibling folder named with the mirror's name as a prefix is allowed",
    "allow", tool="Write", cwd=NOGIT, file_path=MAINLINE_IN_HOME, content="rules\n", env=MIRROR_ENV)

# --------------------------------------------------------------------------- frozen dup: a descriptor dup
#
# `2>&1`, `>&2` and `2>&-` name a file DESCRIPTOR, not a file. The shell scanner must not read the
# `&1`, `&2` or `&-` as a path. From a cwd inside a frozen place, that read makes a plain `git fetch
# 2>&1 | tail -1` a frozen write, and the guard refuses it with rule frozen-path. The ALLOW cases
# are the false alarm. The DENY cases after them stay refused: a quoted `&1` is a real file, a dup
# beside a real write still writes that file, and `&>` onto a frozen file is a write.
# Run only this block: MUTATE_ONLY="frozen dup:" python3 hooks/test_guard.py (the name filter).
DUP_HOOKS_CWD = slash(os.path.join(CFG, "hooks"))   # the config directory's hooks folder, as a cwd
# ALLOW: a descriptor dup, from the live pin and from the config directory's hooks folder.
sh("frozen dup: the REST branch delete from the live pin, a 2>&1 tail, is allowed",
   'cd /home/user && for b in batch-38 batch-37; do gh api -X DELETE "repos/shivinate7/claude-settings/git/refs/heads/$b" 2>&1 | tail -1; echo "$b exit $?"; done',
   "allow", cwd=LIVE_PIN)
sh("frozen dup: git fetch 2>&1 from the live pin's clone is allowed",
   "cd /home/user/claude-settings && git fetch origin main 2>&1 | tail -1", "allow", cwd=LIVE_PIN)
sh("frozen dup: ls >&2 from the live pin is allowed", "ls >&2", "allow", cwd=LIVE_PIN)
sh("frozen dup: ls 1>&2 from the live pin is allowed", "ls 1>&2", "allow", cwd=LIVE_PIN)
sh("frozen dup: ls 2>&- from the live pin is allowed", "ls 2>&-", "allow", cwd=LIVE_PIN)
sh("frozen dup: git fetch 2>&1 from the config directory's hooks folder is allowed",
   "git fetch 2>&1 | tail -1", "allow", cwd=DUP_HOOKS_CWD)
# DENY: each one still writes a file, so each stays refused as frozen-path.
sh("frozen dup: a quoted \"&1\" is a real file in the live pin and stays frozen",
   'ls > "&1"', "deny", "frozen-path", cwd=LIVE_PIN)
sh("frozen dup: a dup beside a real write to a frozen file stays frozen",
   "ls 2>&1 > " + CFG_SETTINGS, "deny", "frozen-path", cwd=LIVE_PIN)
sh("frozen dup: &> onto a frozen file stays frozen", "ls &> " + CFG_SETTINGS, "deny",
   "frozen-path", cwd=LIVE_PIN)
sh("frozen dup: a relative redirect inside the live pin stays frozen", "echo x > f", "deny",
   "frozen-path", cwd=LIVE_PIN)
sh("frozen dup: a redirect onto a frozen file from a plain folder stays frozen",
   "echo x > " + CFG_SETTINGS, "deny", "frozen-path", cwd=NOGIT)
# A DUP WRITTEN BEFORE A PATH. `2>&1 PATH` is one redirect and one argument: the `2>` is joined to
# `&1`, so the path after them is an argument, not the target of a `2>`. Each ALLOW reads the path
# or closes a descriptor. Each DENY still writes the path, through cp or tee.
sh("frozen dup: cat 2>&1 before a frozen settings file is allowed", "cat 2>&1 " + CFG_SETTINGS,
   "allow", cwd=NOGIT)
sh("frozen dup: grep 2>&1 before a frozen hook is allowed", "grep x 2>&1 " + CFG_HOOK,
   "allow", cwd=NOGIT)
sh("frozen dup: echo >&2 before a frozen settings file is allowed", "echo x >&2 " + CFG_SETTINGS,
   "allow", cwd=NOGIT)
sh("frozen dup: ls >&- before a frozen settings file is allowed", "ls >&- " + CFG_SETTINGS,
   "allow", cwd=NOGIT)
sh("frozen dup: cp from a dup before a frozen settings file stays frozen",
   "cp /tmp/x 2>&1 " + CFG_SETTINGS, "deny", "frozen-path", cwd=NOGIT)
sh("frozen dup: tee after a dup onto a frozen settings file stays frozen",
   "echo x | tee 2>&1 " + CFG_SETTINGS, "deny", "frozen-path", cwd=NOGIT)
# THE AMPERSAND REDIRECT. `&>` and `&>>` send both streams to a file, so a copy into a frozen path with
# one of them writes the frozen file. The `&` is a redirect, never a copy source. The forms that already
# refuse stay refused, and a copy FROM a frozen file with `&>` is still a read.
sh("frozen amp: cp onto a frozen hook with &> /dev/null stays denied",
   "cp /tmp/x.py " + CFG_HOOK + " &> /dev/null", "deny", "frozen-path", cwd=NOGIT)
sh("frozen amp: cp onto a frozen hook with &>/dev/null, no space, stays denied",
   "cp /tmp/x.py " + CFG_HOOK + " &>/dev/null", "deny", "frozen-path", cwd=NOGIT)
sh("frozen amp: cp onto a frozen settings file with &>> /dev/null stays denied",
   "cp /tmp/x.json " + CFG_SETTINGS + " &>> /dev/null", "deny", "frozen-path", cwd=NOGIT)
sh("frozen amp: cp onto a frozen hook with &> /dev/null, then a chained echo, stays denied",
   "cp /tmp/x.py " + CFG_HOOK + " &> /dev/null && echo done", "deny", "frozen-path", cwd=NOGIT)
sh("frozen amp: cp onto a frozen hook with > /dev/null stays denied",
   "cp /tmp/x.py " + CFG_HOOK + " > /dev/null", "deny", "frozen-path", cwd=NOGIT)
sh("frozen amp: cp onto a frozen hook with >& /dev/null stays denied",
   "cp /tmp/x.py " + CFG_HOOK + " >& /dev/null", "deny", "frozen-path", cwd=NOGIT)
sh("frozen amp: cp onto a frozen hook with 2>&1 stays denied",
   "cp /tmp/x.py " + CFG_HOOK + " 2>&1", "deny", "frozen-path", cwd=NOGIT)
sh("frozen amp: cp FROM a frozen hook to scratch with &> /dev/null is still a read",
   "cp " + CFG_HOOK + " /tmp/guard.bak &> /dev/null", "allow", cwd=NOGIT)
# THE DESTINATION AFTER A NULL REDIRECT. `cp SRC &> /dev/null DEST` writes DEST whatever the redirect says, so
# a frozen DEST named after the null redirect is judged, as one named before it is.
sh("frozen amp: cp /tmp/x.py &> /dev/null onto a frozen hook named last stays denied",
   "cp /tmp/x.py &> /dev/null " + CFG_HOOK, "deny", "frozen-path", cwd=NOGIT)
sh("frozen amp: cp /tmp/x.json &> /dev/null onto a frozen settings file named last stays denied",
   "cp /tmp/x.json &> /dev/null " + CFG_SETTINGS, "deny", "frozen-path", cwd=NOGIT)
# THE FROZEN SOURCE WITH A FILE REDIRECT. `cp FROZEN /tmp/x &> /tmp/build.log` reads the frozen file and writes
# scratch, so it is allowed: the `&` of `&>` is no copy source. A frozen destination with the same redirect
# still denies.
sh("frozen amp: cp FROM a frozen hook to scratch with &> to a build log is still a read",
   "cp " + CFG_HOOK + " /tmp/x &> /tmp/build.log", "allow", cwd=NOGIT)
sh("frozen amp: cp onto a frozen hook with &> to a build log stays denied",
   "cp /tmp/x.py " + CFG_HOOK + " &> /tmp/build.log", "deny", "frozen-path", cwd=NOGIT)
# THE LONE >& REDIRECT. `>&` sends both streams to a file, as `&>` does. A copy FROM a frozen hook with `>&` to a
# build log reads the frozen file and writes scratch, so it is allowed. A copy onto a frozen hook with the same
# redirect still denies.
sh("frozen amp: cp FROM a frozen hook to scratch with >& to a build log is still a read",
   "cp " + CFG_HOOK + " /tmp/x >& /tmp/l", "allow", cwd=NOGIT)
sh("frozen amp: cp onto a frozen hook with >& to a build log stays denied",
   "cp /tmp/x.py " + CFG_HOOK + " >& /tmp/l", "deny", "frozen-path", cwd=NOGIT)

add("config-edit: Edit of a project local settings file is allowed", "allow", tool="Edit",
    cwd=NOGIT, file_path=PROJ_LOCAL)
add("config-edit: Edit of a project hook is allowed", "allow", tool="Edit", cwd=NOGIT,
    file_path=PROJ_HOOK)
add("config-edit: NotebookEdit of a project hook is allowed", "allow", tool="NotebookEdit",
    cwd=NOGIT, notebook_path=PROJ_HOOK)
# MEASURED on Linux CI 2026-09-16: guard.py's own docstring scopes this equivalence to
# Windows ("a forward slash, a backslash ... all read the same on Windows"). On POSIX a
# backslash is an ordinary filename character, not a separator, so the same text swap
# builds an unrelated relative path instead of an alternate spelling of the frozen file.
add("frozen: a backslash spelling of the same path",
    "deny" if os.name == "nt" else "allow", "frozen-path" if os.name == "nt" else None,
    tool="Write", cwd=NOGIT, file_path=CFG_SETTINGS.replace("/", "\\"))
add("config-edit: a relative spelling resolved against the cwd is allowed", "allow", tool="Write",
    cwd=PROJ, file_path=".claude/settings.json")

add("frozen: a frozen path stays readable", "allow", tool="Read", cwd=NOGIT,
    file_path=CFG_SETTINGS)
add("frozen: a frozen hook stays readable", "allow", tool="Read", cwd=NOGIT, file_path=CFG_HOOK)
add("frozen: Grep may look at a frozen path", "allow", tool="Grep", cwd=NOGIT, path=CFG_SETTINGS)
# THE CLONE IS NOT FROZEN. Its settings.json is the SOURCE the install script copies into the
# config directory, so a guard that froze it would freeze the only way to change the rules.
add("frozen: the clone of claude-settings is editable", "allow", tool="Edit", cwd=CLONE,
    file_path=CLONE_SETTINGS)
add("frozen: the clone's settings by a relative name", "allow", tool="Write", cwd=CLONE,
    file_path="settings.json")
add("frozen: an ordinary source file", "allow", tool="Edit", cwd=NOGIT, file_path="src/app.py")
add("frozen: an ordinary project file by absolute path", "allow", tool="Write", cwd=NOGIT,
    file_path=slash(os.path.join(PROJ, "src", "app.py")))

# THE INSTALLED SYMLINK ITSELF STAYS FROZEN. `install.sh` lands every frozen file under the
# config directory as a real symlink into the clone (`~/.claude/hooks/guard.py -> <clone>/
# hooks/guard.py`). A realpath-only read follows that link OUT of the config directory and
# wrongly allows the write; `is_frozen` also checks the literal, un-followed path, which stays
# under the config directory.
SYMFROZEN = os.path.join(ROOT, "symfrozen")
SYM_CLONE_HOOK = os.path.join(SYMFROZEN, "clone", "hooks", "guard.py")
SYM_CFG_HOOK = os.path.join(SYMFROZEN, "cfg", "hooks", "guard.py")
SYM_CFG_NOTES = slash(os.path.join(SYMFROZEN, "cfg", "notes.md"))
os.makedirs(os.path.dirname(SYM_CLONE_HOOK), exist_ok=True)
os.makedirs(os.path.dirname(SYM_CFG_HOOK), exist_ok=True)
with open(SYM_CLONE_HOOK, "w") as f:
    f.write("# stand-in guard.py, in the clone\n")
try:
    os.symlink(SYM_CLONE_HOOK, SYM_CFG_HOOK)
    SYM_MADE = True
except Exception:
    SYM_MADE = False
# Skipped where the link cannot be made: the literal path under the config dir is frozen with or
# without a link, so an "allow" there is wrong and the case proves nothing about the resolve branch.
if SYM_MADE:
    add("frozen: the live path stays frozen even though it is a real symlink into the clone "
        "[resolve-branch proof]",
        "deny", "frozen-path",
        tool="Edit", cwd=NOGIT, config=os.path.join(SYMFROZEN, "cfg"),
        file_path=slash(SYM_CFG_HOOK), old_string="# stand-in",
        new_string="# rewritten by a session")
# THE CLONE PATH BEHIND THAT SYMLINK STAYS EDITABLE (decision recovery-independent-of-state, "the clone is not frozen"): the literal-path check must not freeze the clone
# just because a symlink elsewhere happens to point at it.
add("frozen: the clone file the symlink points at is still editable directly",
    "allow", tool="Edit", cwd=NOGIT, config=os.path.join(SYMFROZEN, "cfg"),
    file_path=slash(SYM_CLONE_HOOK), old_string="# stand-in", new_string="# rewritten by hand")
# A USER'S OWN, UNSHIPPED FILE under the config directory is not on CONFIG_FROZEN_FILES or
# CONFIG_FROZEN_DIRS, so the literal-path check must not freeze the whole config directory.
add("frozen: a user's own unshipped file under the config directory is allowed",
    "allow", tool="Edit", cwd=NOGIT, config=os.path.join(SYMFROZEN, "cfg"),
    file_path=SYM_CFG_NOTES, old_string="a", new_string="b")
# A SHIPPED SKILL LANDS AS ONE DIRECTORY SYMLINK, not a per-file one: `~/.claude/skills/
# fresh-prose -> <clone>/skills/fresh-prose`. The same literal-vs-resolved gap applies one
# level up, at the directory, so the fix must cover it too.
SYM_CLONE_SKILL_DIR = os.path.join(SYMFROZEN, "clone", "skills", "fresh-prose")
SYM_CFG_SKILL_DIR = os.path.join(SYMFROZEN, "cfg", "skills", "fresh-prose")
SYM_CFG_SKILL_MD = os.path.join(SYM_CFG_SKILL_DIR, "SKILL.md")
SYM_CFG_OWN_SKILL_MD = slash(os.path.join(SYMFROZEN, "cfg", "skills", "my-own", "SKILL.md"))
os.makedirs(SYM_CLONE_SKILL_DIR, exist_ok=True)
os.makedirs(os.path.dirname(SYM_CFG_SKILL_DIR), exist_ok=True)
os.makedirs(os.path.dirname(SYM_CFG_OWN_SKILL_MD), exist_ok=True)
with open(os.path.join(SYM_CLONE_SKILL_DIR, "SKILL.md"), "w") as f:
    f.write("# stand-in\n")
with open(SYM_CFG_OWN_SKILL_MD, "w") as f:
    f.write("# stand-in\n")
try:
    os.symlink(SYM_CLONE_SKILL_DIR, SYM_CFG_SKILL_DIR)
    SYM_SKILL_MADE = True
except Exception:
    SYM_SKILL_MADE = False
if SYM_SKILL_MADE:
    add("frozen: a shipped skill's SKILL.md stays frozen through the directory symlink into the "
        "clone [resolve-branch proof]",
        "deny", "frozen-path",
        tool="Edit", cwd=NOGIT, config=os.path.join(SYMFROZEN, "cfg"),
        file_path=slash(SYM_CFG_SKILL_MD), old_string="# stand-in",
        new_string="# rewritten by a session")
add("frozen: a user's own, unshipped skill directory is allowed", "allow", tool="Edit",
    cwd=NOGIT, config=os.path.join(SYMFROZEN, "cfg"), file_path=SYM_CFG_OWN_SKILL_MD,
    old_string="# stand-in", new_string="# rewritten by hand")

sh("config-edit: a redirect onto a project settings file is allowed",
   "echo '{}' > " + PROJ_SETTINGS, "allow", cwd=NOGIT)
sh("config-edit: an append onto a project settings file is allowed",
   "echo '{}' >> " + PROJ_SETTINGS, "allow", cwd=NOGIT)
sh("frozen: a redirect onto the global CLAUDE.md", "echo x > " + CFG_CLAUDEMD, "deny",
   "frozen-path", cwd=NOGIT)
sh("frozen: a redirect onto a config hook", "cat template.py > " + CFG_HOOK, "deny", "frozen-path",
   cwd=NOGIT)
sh("config-edit: rm of a project settings file is allowed", "rm " + PROJ_SETTINGS, "allow",
   cwd=NOGIT)
sh("config-edit: mv of a project settings file is allowed",
   "mv " + PROJ_SETTINGS + " elsewhere.json", "allow", cwd=NOGIT)
sh("config-edit: chmod of a project hook is allowed", "chmod 000 " + PROJ_HOOK, "allow", cwd=NOGIT)
sh("config-edit: sed -i on a project settings file is allowed",
   "sed -i s/a/b/ " + PROJ_SETTINGS, "allow", cwd=NOGIT)
sh("config-edit: tee onto a project settings file is allowed",
   "echo x | tee " + PROJ_SETTINGS, "allow", cwd=NOGIT)
sh("config-edit: truncate of a project hook is allowed", "truncate -s 0 " + PROJ_HOOK, "allow",
   cwd=NOGIT)
sh("config-edit: a heredoc redirected onto a settings file is allowed",
   "cat <<'DOC' > " + PROJ_SETTINGS + "\n{ \"hooks\": {} }\nDOC", "allow",
   cwd=NOGIT)
sh("frozen: a heredoc redirected onto the environment file",
   "cat <<'DOC' > " + ENV + "\nKEY=value\nDOC", "deny", "env-file", cwd=NOGIT)

sh("config-edit: PowerShell Set-Content is allowed",
   "Set-Content -Path " + PROJ_SETTINGS + " -Value 'x'", "allow", tool="PowerShell", cwd=NOGIT)
sh("config-edit: PowerShell Out-File with backslashes is allowed",
   "'x' | Out-File " + PROJ_SETTINGS.replace("/", "\\"), "allow", tool="PowerShell",
   cwd=NOGIT)
sh("config-edit: PowerShell Add-Content is allowed", "Add-Content " + PROJ_HOOK + " 'x'", "allow",
   tool="PowerShell", cwd=NOGIT)
sh("config-edit: PowerShell Remove-Item is allowed", "Remove-Item " + PROJ_SETTINGS, "allow",
   tool="PowerShell", cwd=NOGIT)
sh("config-edit: PowerShell Copy-Item is allowed", "Copy-Item other.json " + PROJ_SETTINGS,
   "allow", tool="PowerShell", cwd=NOGIT)

# THE THREE MEASURED FALSE POSITIVES of the q_max backstop. Each was a case of judging the TEXT of a
# command instead of its behaviour.
sh("frozen: a file-descriptor redirect is not a write to the file being read",
   "cat " + PROJ_SETTINGS + " 2>/dev/null", "allow", cwd=NOGIT)
sh("frozen: running a hook with merged output", "python " + PROJ_HOOK + " 2>&1", "allow",
   cwd=NOGIT)
sh("frozen: a read-only inspection of both",
   "wc -l " + PROJ_SETTINGS + " 2>/dev/null; ls " + PROJ_HOOKDIR, "allow", cwd=NOGIT)
sh("frozen: a frozen path named only in a comment",
   'echo "hello" > notes.txt   # ' + PROJ_SETTINGS + " is protected, do not edit", "allow",
   cwd=NOGIT)
sh("frozen: searching for the path name and writing the results elsewhere",
   'grep -rn "' + PROJ_SETTINGS + '" docs/ > /tmp/hits.txt', "allow", cwd=NOGIT)
sh("frozen: a heredoc writing prose that names the environment file",
   "cat > notes.md <<'DOC'\nThe guard refuses any command naming " + ENV + ".\nDOC", "allow",
   cwd=NOGIT)
# THE QUOTED SIBLING of the model-cap data cases. The same _shell_write_hit reads a frozen path inside
# a quoted echo as a write. A quoted path piped into a pure printer is data, and allows (the wc pin
# below). Piped into an interpreter it denies: an interpreter may run the text, so a pipe into one
# fails closed. A real cat-write onto that file stays denied.
sh("frozen data: a quoted cat-write onto the config settings, piped to python, denies "
   "[cap-ask-fix r1: a pipe into an interpreter fails closed]",
   "echo \"cat > " + CFG_SETTINGS + "\" | python hooks/guard.py", "deny", "frozen-path", cwd=NOGIT)
sh("frozen: a real cat-write onto the config settings stays denied",
   "cat > " + CFG_SETTINGS, "deny", "frozen-path", cwd=NOGIT)
# The PowerShell reading of a `\"` stays fail-closed: the quote may open a string, so the write is
# still judged and denied. The bash reading of the same text is a plain echo and is allowed.
sh("frozen: a PowerShell call with a backslash-quote before a config write stays denied",
   'echo "C:\\" ; Set-Content ' + CFG_SETTINGS + ' x ; echo \\"D"', "deny", "frozen-path",
   tool="PowerShell", cwd=NOGIT)

# ASK-STEP-HIDDEN (debt ask-step-hidden-in-script). A redirect glued to a `(` or a `$(` hides its path word
# from the frozen check, so each form denies as the plain redirect does.
sh("ask-step-hidden: control, a plain redirect onto the config settings denies",
   "echo x > " + CFG_SETTINGS, "deny", "frozen-path", cwd=NOGIT)
sh("ask-step-hidden: a redirect in a subshell onto the config settings denies",
   "(echo x > " + CFG_SETTINGS + ")", "deny", "frozen-path", cwd=NOGIT)
sh("ask-step-hidden: a redirect in a glued command substitution onto the config settings denies",
   "x=$(echo x > " + CFG_SETTINGS + ")", "deny", "frozen-path", cwd=NOGIT)
sh("ask-step-hidden: a redirect in glued backticks inside bash -c onto the config settings denies",
   "bash -c 'x=`echo x > " + CFG_SETTINGS + "`'", "deny", "frozen-path", cwd=NOGIT)

# VARIABLE INDIRECTION (incident 2026-10-07): the static parse saw only "$D", never the frozen
# target. A simple VAR=value assignment earlier in the same command must resolve. An unresolved
# variable, or a read of a resolved one, stays allowed.
_D = 'D="' + CFG_STATE + '"; '
for _n, _c in (
    ("the incident shape",
     'S=/tmp/scratch; ' + _D + 'ls $D 2>&1 | head -1; cp "$S/handoff.md" "$D"'),
    ("a braced ${D}", _D + 'cp /tmp/a "${D}"'),
    ("export then redirect", 'export D="' + CFG_STATE + '"; echo x > "$D"'),
    ("tee onto $D", _D + "echo x | tee $D"),
    ("sed -i on $D", _D + 'sed -i s/a/b/ "$D"'),
    ("mv onto $D", _D + "mv /tmp/a $D"),
):
    sh("frozen: var: " + _n, _c, "deny", "frozen-path", cwd=NOGIT)
sh("frozen: var: ls of $D is a read", _D + "ls $D", "allow", cwd=NOGIT)
sh("frozen: var: cat of quoted $D is a read", _D + 'cat "$D"', "allow", cwd=NOGIT)
sh("frozen: var: frozen path read into a safe $OUT",
   'OUT=/tmp/o; cat "' + CFG_STATE + '" > "$OUT"', "allow", cwd=NOGIT)
sh("frozen: var: write to a safe $OUT", "OUT=/tmp/o; echo hi > $OUT", "allow", cwd=NOGIT)
sh("frozen: var: write to an unassigned $D", "echo x > $D", "allow", cwd=NOGIT)

# P is the frozen path; every command quotes it.
_P = '"' + CFG_STATE + '"'
for _n, _c in (
    ("the last assignment wins", 'D=/tmp/o; D=' + _P + '; cp a "$D"'),
    ("a subshell", '(D=' + _P + '; cp a "$D")'),
    ("a brace group", '{ D=' + _P + '; cp a "$D"; }'),
    ("an if block", 'if true; then D=' + _P + '; cp a "$D"; fi'),
    ("declare", 'declare D=' + _P + '; cp a "$D"'),
    ("export of two names", 'export A=1 D=' + _P + '; cp a "$D"'),
):
    sh("frozen: var2: " + _n, _c, "deny", "frozen-path", cwd=NOGIT)
sh("frozen: var2: PowerShell $D assignment then Set-Content",
   '$D = ' + _P + '; Set-Content $D x', "deny", "frozen-path", tool="PowerShell", cwd=NOGIT)
# $HOME-built path (case 4) is skipped: the suite's config dir is CFG, not $HOME/.claude.
sh("frozen: var2: a later assignment to a safe path", 'D=' + _P + '; D=/tmp/o; cp a "$D"',
   "allow", cwd=NOGIT)
sh("frozen: var2: the write comes before the assignment", 'cp a "$D"; D=' + _P, "allow",
   cwd=NOGIT)
sh("frozen: var2: unset clears the variable", 'D=' + _P + '; unset D; cp a "$D"', "allow",
   cwd=NOGIT)
sh("frozen: var2: single quotes do not expand", 'D=' + _P + "; cp a '$D'", "allow", cwd=NOGIT)

# ---- resolve-vars: the resolver reads each assignment as the shell does. A value is split at its quote
# when the text after the quote is read as its own word; an apostrophe in double quotes is text; a prefix
# assignment and a subshell's assignment reach only the text the shell gives them. MUTATE_ONLY="resolve-vars"
# runs these verdicts and the unit checks in the frozen block beside the LOG_CHECKS_EXTRA registrations.
_SPLIT_SUB = slash(os.path.join(ROOT, "split", "sub"))   # an ordinary folder, not frozen
_UP_TO_CONFIG = "/../../" + os.path.basename(CFG) + "/settings.json"   # back from it into the config folder

# A value cut at its quote: `"$BASE"/../...` leaves the shell one path, and the guard read the cut value.
sh("frozen resolve-vars: a write through a value split at its quote, into the config folder, denies",
   'BASE=' + _SPLIT_SUB + '; WT="$BASE"' + _UP_TO_CONFIG + '; echo x > "$WT"', "deny", "frozen-path",
   cwd=NOGIT)
sh("frozen resolve-vars: control, the same path as one unsplit value denies",
   'WT=' + _SPLIT_SUB + _UP_TO_CONFIG + '; echo x > "$WT"', "deny", "frozen-path", cwd=NOGIT)
# An apostrophe in double quotes, then a second one, makes one span that swallows a later reassignment.
sh("frozen resolve-vars: a reassignment after an apostrophe in double quotes is seen, and its write denies",
   'D=/tmp/o; echo "don\'t"; D=' + CFG_SETTINGS + "; echo 'x'; echo x > $D", "deny", "frozen-path",
   cwd=NOGIT)
sh("frozen resolve-vars: control, the same with no apostrophe in the text denies",
   'D=/tmp/o; echo "dont"; D=' + CFG_SETTINGS + "; echo 'x'; echo x > $D", "deny", "frozen-path",
   cwd=NOGIT)
# A prefix assignment takes effect for its own command only, after the words expand: `"$D"` is the old value.
sh("frozen resolve-vars: a prefix assignment does not reach the word it expands, so a write to the old value denies",
   'D=' + CFG_SETTINGS + '; D=/tmp/o cp a "$D"', "deny", "frozen-path", cwd=NOGIT)
sh("frozen resolve-vars: control, the same word with no prefix assignment denies",
   'D=' + CFG_SETTINGS + '; cp a "$D"', "deny", "frozen-path", cwd=NOGIT)
# A subshell's assignment ends at its closing paren.
sh("frozen resolve-vars: an assignment in a subshell ends at its paren, so a write to the old value denies",
   'D=' + CFG_SETTINGS + '; (D=/tmp/o); echo x > $D', "deny", "frozen-path", cwd=NOGIT)
sh("frozen resolve-vars: control, inside the subshell the new value holds, and the write goes there",
   'D=' + CFG_SETTINGS + '; (D=/tmp/o; echo x > $D)', "allow", cwd=NOGIT)
# Controls: a brace group and a bare assignment before && both keep the assignment for the next command.
sh("frozen resolve-vars: control, a brace group keeps its assignment for the next command, denies",
   '{ D=' + CFG_SETTINGS + '; }; cp a "$D"', "deny", "frozen-path", cwd=NOGIT)
sh("frozen resolve-vars: control, a bare assignment before && keeps it for the next command, denies",
   'D=' + CFG_SETTINGS + ' && cp a "$D"', "deny", "frozen-path", cwd=NOGIT)
# Scanner traps (building-scanner-respects-strings): a comment opener or a lone quote inside double
# quotes is text, so the write after it still reaches the frozen check.
sh("frozen resolve-vars: a # inside double quotes is text, and the write after it denies",
   'echo "# note"; echo x > ' + CFG_SETTINGS, "deny", "frozen-path", cwd=NOGIT)
sh("frozen resolve-vars: a // inside double quotes is text, and the write after it denies",
   'echo "http://x"; echo x > ' + CFG_SETTINGS, "deny", "frozen-path", cwd=NOGIT)
sh("frozen resolve-vars: a /* inside double quotes is text, and the write after it denies",
   'echo "/* x"; echo x > ' + CFG_SETTINGS, "deny", "frozen-path", cwd=NOGIT)
sh("frozen resolve-vars: a lone apostrophe inside double quotes is text, and the write after it denies",
   'echo "it\'s"; echo x > ' + CFG_SETTINGS, "deny", "frozen-path", cwd=NOGIT)

# A redirect-only assignment keeps its value for the next command, as bash does: `D=... >/dev/null` sets D.
sh("frozen resolve-vars: a redirect-only assignment with >/dev/null keeps its value, so a cp to it denies",
   'D=' + CFG_SETTINGS + ' >/dev/null; cp a $D', "deny", "frozen-path", cwd=NOGIT)
sh("frozen resolve-vars: a redirect-only assignment with 2>/dev/null keeps its value, so a cp to it denies",
   'D=' + CFG_SETTINGS + ' 2>/dev/null; cp a $D', "deny", "frozen-path", cwd=NOGIT)
sh("frozen resolve-vars: a redirect-only assignment with >/dev/null keeps its value, so a write to it denies",
   'D=' + CFG_SETTINGS + ' >/dev/null; echo y > $D', "deny", "frozen-path", cwd=NOGIT)
sh("frozen resolve-vars: control, a plain assignment with no redirect keeps its value, so a cp to it denies",
   'D=' + CFG_SETTINGS + '; cp a $D', "deny", "frozen-path", cwd=NOGIT)
# A function body runs in the calling shell, so an assignment in it lasts after the call.
sh("frozen resolve-vars: an assignment in a function body lasts after the call, so a write to it denies",
   'function f { D=' + CFG_SETTINGS + '; }; f; echo y > $D', "deny", "frozen-path", cwd=NOGIT)
sh("frozen resolve-vars: control, an assignment in a f() body lasts after the call, so a write to it denies",
   'f() { D=' + CFG_SETTINGS + '; }; f; echo y > $D', "deny", "frozen-path", cwd=NOGIT)
# A verbatim heredoc body is text: its odd quote must not pair with a quote on a later line.
sh("frozen resolve-vars: an odd quote in a heredoc body is text, so a write after the heredoc denies",
   "python3 - <<'EOF'\nprint(\"x)\nEOF\nD=" + CFG_SETTINGS + '; echo "y" > $D', "deny", "frozen-path",
   cwd=NOGIT)
sh("frozen resolve-vars: control, a heredoc body with its quote closed is text, so a write after it denies",
   "python3 - <<'EOF'\nprint(\"x\")\nEOF\nD=" + CFG_SETTINGS + '; echo "y" > $D', "deny", "frozen-path",
   cwd=NOGIT)
# The shell reads an ambiguous redirect as an error and writes nothing, so the guard should allow it.
sh("frozen resolve-vars: an ambiguous redirect from a value with an escaped space writes nothing, so a write to it allows",
   'D=' + CFG_SETTINGS + '\\ x; echo y > $D', "allow", cwd=NOGIT)
# Control: the same write with a plain value is denied, so the allow above comes from the ambiguous redirect.
sh("frozen resolve-vars: control, the same assignment with no escaped space, then a write to it, denies",
   'D=' + CFG_SETTINGS + '; echo y > $D', "deny", "frozen-path", cwd=NOGIT)

# A backslash-newline joins two lines into one. So `X=1 && \` with `D=v` on the next line is `X=1 && D=v`,
# and `D=v \` with `&& cmd` on the next line is `D=v && cmd`: the assignment still starts its command.
sh("frozen resolve-vars: a backslash-newline after && does not hide an assignment, so a write to it denies",
   "X=1 && \\\n  D=" + CFG_SETTINGS + " && \\\n  echo y > $D", "deny", "frozen-path", cwd=NOGIT)
sh("frozen resolve-vars: a backslash-newline after ; does not hide an assignment, so a write to it denies",
   "true;\\\nD=" + CFG_SETTINGS + "; echo y > $D", "deny", "frozen-path", cwd=NOGIT)
sh("frozen resolve-vars: a backslash-newline before export does not hide it, so sed -i of the assigned path denies",
   "cd /tmp && \\\n export D=" + CFG_SETTINGS + " && \\\n sed -i s/a/b/ $D", "deny", "frozen-path", cwd=NOGIT)
sh("frozen resolve-vars: a backslash-newline after an assignment keeps it for the next command, so a write to it denies",
   "D=" + CFG_SETTINGS + " \\\n  && echo y > $D", "deny", "frozen-path", cwd=NOGIT)
sh("frozen resolve-vars: control, a backslash-newline chain of a safe path, then a write to it, allows",
   "X=1 && \\\n  D=/tmp/o && \\\n  echo y > $D", "allow", cwd=NOGIT)
sh("frozen resolve-vars: control, a backslash-newline after a safe assignment, then a write to it, allows",
   "D=/tmp/o \\\n  && echo y > $D", "allow", cwd=NOGIT)
sh("frozen resolve-vars: control, the same chain on one line, denies",
   "X=1 && D=" + CFG_SETTINGS + " && echo y > $D", "deny", "frozen-path", cwd=NOGIT)

# PowerShell reads `$D='v'` and `$D="v"` as an assignment with or without spaces around the equals.
sh("frozen resolve-vars: PowerShell $D='path' with no spaces, then Set-Content to $D, denies",
   "$D='" + CFG_SETTINGS + "'; Set-Content $D x", "deny", "frozen-path", tool="PowerShell", cwd=NOGIT)
sh("frozen resolve-vars: PowerShell $D=\"path\" with no spaces, then Set-Content to $D, denies",
   '$D="' + CFG_SETTINGS + '"; Set-Content $D x', "deny", "frozen-path", tool="PowerShell", cwd=NOGIT)
sh("frozen resolve-vars: PowerShell $D= 'path', a space after the equals only, then Set-Content to $D, denies",
   "$D= '" + CFG_SETTINGS + "'; Set-Content $D x", "deny", "frozen-path", tool="PowerShell", cwd=NOGIT)
sh("frozen resolve-vars: control, PowerShell $D='safe path' with no spaces, then Set-Content to $D, allows",
   "$D='/tmp/o'; Set-Content $D x", "allow", tool="PowerShell", cwd=NOGIT)
sh("frozen resolve-vars: control, PowerShell $D = 'path' with spaces, then Set-Content to $D, denies",
   "$D = '" + CFG_SETTINGS + "'; Set-Content $D x", "deny", "frozen-path", tool="PowerShell", cwd=NOGIT)

# A prefix assignment is in the environment of its command, and a heredoc is that command's input: the child
# shell reads the value. `env NAME=v` gives the same environment. An export is in the environment too.
sh("frozen resolve-vars: a prefix assignment into a bash heredoc script reaches the script, so its write denies",
   "OUT=" + CFG_SETTINGS + " bash <<'EOF'\necho y > \"$OUT\"\nEOF", "deny", "frozen-path", cwd=NOGIT)
sh("frozen resolve-vars: an env assignment before sh with a heredoc script reaches the script, so its write denies",
   "env OUT=" + CFG_SETTINGS + " sh <<'EOF'\necho y > $OUT\nEOF", "deny", "frozen-path", cwd=NOGIT)
sh("frozen resolve-vars: control, a prefix assignment of a safe path into a heredoc script, then its write, allows",
   "OUT=/tmp/o bash <<'EOF'\necho y > \"$OUT\"\nEOF", "allow", cwd=NOGIT)
sh("frozen resolve-vars: control, an export of the frozen path before a heredoc script, then its write, denies",
   "export OUT=" + CFG_SETTINGS + "; bash <<'EOF'\necho y > \"$OUT\"\nEOF", "deny", "frozen-path", cwd=NOGIT)

# A run of heredoc blocks does not hide the write after it. Each closed body is read alone, on a copy of
# the table, and the command goes on at its own depth, so the run never reaches `_NEST_LIMIT`. 20, 21 and
# 30 blocks deny. The 21-block control with a safe path allows.
_HEREDOC_BLOCK = "cat > f <<EOF\nline\nEOF\n"
for _blocks in (20, 21, 30):
    sh("frozen resolve-vars: %d heredoc blocks, then an assignment to the frozen path and a write to it, denies"
       % _blocks, _HEREDOC_BLOCK * _blocks + "D=" + CFG_SETTINGS + "\necho y > $D", "deny", "frozen-path",
       cwd=NOGIT)
sh("frozen resolve-vars: control, 21 heredoc blocks, then an assignment to a safe path and a write to it, allows",
   _HEREDOC_BLOCK * 21 + "D=/tmp/o\necho y > $D", "allow", cwd=NOGIT)

# A TOKEN IN THE COMMAND LIFTS NOTHING. `DESTRUCTIVE_OK=1` and `GIT_DISCARD_OK=1` are plain env
# assignments that the guard does not read. The one lift is the owner override (family
# `override`): the owner types it as a prompt, and the guard reads it from a state file.
sh("frozen: a leftover token is not a key to the environment rule",
   "DESTRUCTIVE_OK=1 cat " + ENV, "deny", "env-file", cwd=NOGIT)
sh("frozen: a leftover token is not a key to the frozen rule",
   "DESTRUCTIVE_OK=1 tee " + CFG_SETTINGS, "deny", "frozen-path", cwd=NOGIT)
sh("frozen: a leftover token is not a key to the shared-tree rule",
   "GIT_DISCARD_OK=1 " + VCS + " restore src", "deny", "shared-tree", cwd=NOGIT)
sh("frozen: a leftover token is not a key to the push rule",
   "GIT_DISCARD_OK=1 " + VCS + " push --force", "deny", "force-push", cwd=PUSHFEAT)


# THE SHELL RUNNERS KEEP QUOTED TEXT IN VIEW. Quoted text with a space or an operator is data, unless a
# shell reads it: text piped into `sh`, or an `iex`. The first two pins deny those shapes, and they guard
# a future regression of the data reading.
# The commit message is the allow shape that reading made data. A quoted heredoc body fed to a non-shell
# interpreter is read only at its shell spots, the calls that hand text to a shell (`os.system`, `shell=True`).
# A body with no shell spot is data, not a write; a shell write named at a spot denies.
sh("frozen shell: an echo of a quoted cat-write onto the config settings, piped to sh, denies "
   "[regression pin: passes on main and d7fb2f1]",
   'echo "cat > ' + CFG_SETTINGS + '" | sh', "deny", "frozen-path", cwd=NOGIT)
sh("frozen shell: an iex of a Set-Content onto the config settings denies "
   "[regression pin: passes on main and d7fb2f1]",
   'iex "Set-Content -Path ' + CFG_SETTINGS + ' -Value x"', "deny", "frozen-path",
   tool="PowerShell", cwd=NOGIT)
sh("frozen data: a quoted commit message naming a cat-write onto the config settings allows "
   "[new allow: red on main, passes on d7fb2f1]",
   VCS + ' commit -m "note: cat > ' + CFG_SETTINGS + ' is refused"', "allow", cwd=NOGIT)
sh("frozen data: a heredoc body naming a cat-write onto the config settings, fed to python, allows "
   "[step agent-model-cap-string-false-alarm: a false-alarm fix, interpreter string data that writes no file "
   "is not the act; incident 2026-11-02 01:16 CST]",
   "python hooks/guard.py <<'DOC'\ncat > " + CFG_SETTINGS + "\nDOC", "allow", cwd=NOGIT)
sh("frozen shell: a python heredoc that os.system-runs a cat-write onto the config settings denies "
   "[regression pin: passes on main]",
   "python3 - <<'DOC'\nimport os; os.system('cat > " + CFG_SETTINGS + "')\nDOC", "deny", "frozen-path", cwd=NOGIT)
sh("frozen shell: a heredoc body fed to bash, naming a cat-write onto the config settings, denies "
   "[regression pin: passes on main, a shell-run body stays in view]",
   "bash <<'SH'\ncat > " + CFG_SETTINGS + "\nSH", "deny", "frozen-path", cwd=NOGIT)

# Alias bypass: a shell spot reached through an import alias denies or asks, as the spelled-out call does.
sh("frozen shell: a python heredoc importing run from subprocess, a cp onto the config settings with shell=True, "
   "denies [alias bypass, main denies]",
   "python3 - <<'PY'\nfrom subprocess import run\nrun('cp x " + CFG_SETTINGS + "', shell=True)\nPY",
   "deny", "frozen-path", cwd=NOGIT)
sh("frozen shell: a python heredoc importing run from subprocess, a cp onto the hook path with shell=True, "
   "denies [alias bypass, main denies]",
   "python3 - <<'PY'\nfrom subprocess import run\nrun('cp x " + CFG_HOOK + "', shell=True)\nPY",
   "deny", "frozen-path", cwd=NOGIT)
# A python comment is text, not a shell spot: a body whose only spot is a comment is data.
sh("frozen data: a python heredoc whose only spot is a comment naming a write onto the config settings, allows "
   "[comment false alarm, main allows]",
   "python3 - <<'PY'\n# subprocess.run('echo x > " + CFG_SETTINGS + "', shell=True)\nPY", "allow", cwd=NOGIT)

# The narrowing reads a quoted word as data, a plain word as code. Each shape below is a real write, so each DENIES.
for _n, _c in (
    ("a quoted sh name", '"sh" -c "cat > ' + CFG_SETTINGS + '"'),
    ("a shell named by a variable", '$SHELL -c "cat > ' + CFG_SETTINGS + '"'),
    ("a quoted path to bash.exe with a space",
     '"/c/Program Files/Git/bin/bash.exe" -c "cat > ' + CFG_SETTINGS + '"'),
    ("env -S splitting a shell command", 'env -S \'sh -c "cat > ' + CFG_SETTINGS + '"\''),
    ("flock running a shell command", 'flock /tmp/l -c "cat > ' + CFG_SETTINGS + '"'),
    ("script running a shell command", 'script -qc "cat > ' + CFG_SETTINGS + '" /dev/null'),
):
    sh("frozen shell: F1, " + _n + ", writes the config settings, denies [r1 red]", _c, "deny",
       "frozen-path", cwd=NOGIT)
sh("frozen shell: F1, a PowerShell scriptblock built from a string, denies [r1 red]",
   '[scriptblock]::Create("Set-Content -Path ' + CFG_SETTINGS + ' -Value 1").Invoke()',
   "deny", "frozen-path", tool="PowerShell", cwd=NOGIT)
for _n, _c in (
    ("bash -c with an ANSI-C quoted command", "bash -c $'cat > " + CFG_SETTINGS + "'"),
    ("bash -c with a quote that closes mid-word", "bash -c x'; cat > " + CFG_SETTINGS + "'"),
    ("an ANSI-C escaped quote before a write", "echo $'\\'' ; cat > " + CFG_SETTINGS + " ; echo 'x'"),
):
    sh("frozen shell: F2, " + _n + ", denies [r1 red]", _c, "deny", "frozen-path", cwd=NOGIT)
sh("frozen shell: F3, a PowerShell backtick before a quote, denies [r1 red]",
   'Write-Output x`"; Set-Content -Path ' + CFG_SETTINGS + ' -Value 1; "b"',
   "deny", "frozen-path", tool="PowerShell", cwd=NOGIT)
sh("frozen shell: F5, a perl heredoc whose body runs a shell write, denies "
   "[r1 red, orchestrator call]",
   "perl <<'EOF'\nsystem(\"sh\", \"-c\", \"cat > " + CFG_SETTINGS + "\")\nEOF",
   "deny", "frozen-path", cwd=NOGIT)
sh("frozen shell: F5, a python3 heredoc whose body runs an os.system tee, denies "
   "[r1 red, orchestrator call]",
   "python3 <<'EOF'\nimport os\nos.system(\"tee " + CFG_SETTINGS + " < /dev/null\")\nEOF",
   "deny", "frozen-path", cwd=NOGIT)

# COVERAGE. A comment opener, a multi-line quoted string or a lone apostrophe must neither hide a real
# write after it, nor turn quoted text that names a write into one.
sh("frozen shell: a # in double quotes does not hide a real write after it, denies [r1 cov]",
   'echo "# keep" && cat > ' + CFG_SETTINGS, "deny", "frozen-path", cwd=NOGIT)
sh("frozen shell: a /* in double quotes does not hide a real write after it, denies [r1 cov]",
   'echo "/* keep" ; cat > ' + CFG_SETTINGS, "deny", "frozen-path", cwd=NOGIT)
sh("frozen shell: a // in single quotes does not hide a real write after it, denies [r1 cov]",
   "echo '// keep' ; cat > " + CFG_SETTINGS, "deny", "frozen-path", cwd=NOGIT)
sh("frozen shell: a # in a multi-line quoted string does not hide a real write after it, denies "
   "[r1 cov]",
   "printf 'one\n# two' ; cat > " + CFG_SETTINGS, "deny", "frozen-path", cwd=NOGIT)
sh("frozen shell: a lone apostrophe in text does not hide a real write after it, denies [r1 cov]",
   "echo don't ; cat > " + CFG_SETTINGS, "deny", "frozen-path", cwd=NOGIT)
sh("frozen shell: a lone apostrophe, a line break, then a real write, denies [r1 cov]",
   "echo don't\ncat > " + CFG_SETTINGS, "deny", "frozen-path", cwd=NOGIT)
sh("frozen data: a /* in double quotes naming a cat-write, piped to python, denies "
   "[cap-ask-fix r1: a pipe into an interpreter fails closed]",
   'echo "/* cat > ' + CFG_SETTINGS + '" | python hooks/guard.py', "deny", "frozen-path", cwd=NOGIT)
sh("frozen data: a // in a multi-line double-quoted string naming a cat-write allows [r1 cov]",
   'printf "%s\n// cat > ' + CFG_SETTINGS + '" x > notes.txt', "allow", cwd=NOGIT)
sh("frozen data: a multi-line commit message with a # naming a cat-write allows [r1 cov]",
   VCS + ' commit -m "line one\n# cat > ' + CFG_SETTINGS + '"', "allow", cwd=NOGIT)

# A command that runs its argument as a shell is code, even when the outer command is git, gh, rg,
# sort or python. Each shape writes the frozen path, so each DENIES.
for _n, _c in (
    ("a git -c alias that runs the write", "git -c alias.w='!cat > " + CFG_SETTINGS + "' w"),
    ("a git submodule foreach that runs the write", "git submodule foreach 'cat > " + CFG_SETTINGS + "'"),
    ("a git rebase -x that runs the write", "git rebase -x 'cat > " + CFG_SETTINGS + "' HEAD"),
    ("a gh alias that runs the write", "gh alias set --shell w 'cat > " + CFG_SETTINGS + "'"),
    ("a git difftool extcmd that runs the write", "git difftool --extcmd 'cat > " + CFG_SETTINGS + "'"),
    ("a git bisect run under sh -c", "git bisect run sh -c 'cat > " + CFG_SETTINGS + "'"),
    ("an rg --pre that runs the write", "rg --pre 'sh -c \"cat > " + CFG_SETTINGS + "\"' x f"),
    ("a sort compress-program that runs the write",
     "sort --compress-program='sh -c \"cat > " + CFG_SETTINGS + "\"' f"),
    ("python -W, then an os.system tee",
     "python -W ignore -c \"import os; os.system('tee " + CFG_SETTINGS + " </dev/null')\""),
    ("python -X dev, then an os.system tee",
     "python -X dev -c \"import os; os.system('tee " + CFG_SETTINGS + " </dev/null')\""),
    ("python -Bc, then an os.system tee",
     "python -Bc \"import os; os.system('tee " + CFG_SETTINGS + " </dev/null')\""),
    ("a process substitution that runs the write", "cat <(sh -c \"cat > " + CFG_SETTINGS + "\")"),
):
    sh("frozen shell: r2, " + _n + ", writes the config settings, denies [r2 red]", _c, "deny",
       "frozen-path", cwd=NOGIT)
sh("frozen shell: r2, a PowerShell iex inside Write-Output runs a Set-Content on the config settings, "
   "denies [r2 red]",
   "Write-Output (iex \"Set-Content -Path " + CFG_SETTINGS + " -Value x\")", "deny", "frozen-path",
   tool="PowerShell", cwd=NOGIT)
sh("frozen shell: r2, a # in a quoted git argument does not hide a write run by sh -c, denies [r2 red]",
   "git submodule foreach \"echo '# keep' && cat > " + CFG_SETTINGS + "\"", "deny", "frozen-path",
   cwd=NOGIT)

# Quoted text is data as the value of a named message flag,
# and as the input of a pure printer whose output runs nowhere. Each names the frozen path and allows.
sh("frozen data: r2, a gh pr create body naming a cat-write onto the config settings, allows [r2 pin]",
   "gh pr create --draft --title \"note\" --body \"cat > " + CFG_SETTINGS + " is refused\"", "allow",
   cwd=NOGIT)
sh("frozen data: r2, a gh issue create body naming a cat-write onto the config settings, allows [r2 pin]",
   "gh issue create --title \"note\" --body \"cat > " + CFG_SETTINGS + " is refused\"", "allow",
   cwd=NOGIT)
sh("frozen data: r2, an echo naming a cat-write onto the config settings, piped to wc, allows [r2 pin]",
   "echo \"cat > " + CFG_SETTINGS + "\" | wc -l", "allow", cwd=NOGIT)
sh("frozen data: r2, an add then a commit naming a cat-write onto the config settings, allows [r2 pin]",
   VCS + " add x && " + VCS + " commit -m \"note: cat > " + CFG_SETTINGS + " is refused\"", "allow",
   cwd=NOGIT)
sh("frozen data: r2, a cd then a commit naming a cat-write onto the config settings, allows [r2 pin]",
   "cd docs && " + VCS + " commit -m \"note: cat > " + CFG_SETTINGS + " is refused\"", "allow",
   cwd=NOGIT)
sh("frozen data: r2, a heredoc to notes.md naming a cat-write onto the config settings, allows [r2 pin]",
   "cat > notes.md <<'DOC'\ncat > " + CFG_SETTINGS + "\nDOC", "allow", cwd=NOGIT)

# COVERAGE. A multi-line quoted string or an apostrophe must not hide a real
# write that follows it, under the reading of a message flag.
sh("frozen shell: r2 cov, a multi-line commit message before a real write, denies [r2 cov]",
   VCS + " commit -m \"line one\n# two\" ; cat > " + CFG_SETTINGS, "deny", "frozen-path", cwd=NOGIT)
sh("frozen shell: r2 cov, a /* and an apostrophe in a commit message before a real write, denies [r2 cov]",
   VCS + " commit -m \"don't /* stop\" && cat > " + CFG_SETTINGS, "deny", "frozen-path", cwd=NOGIT)

# gh-comment-body. A quoted `>` in the body of a gh pr comment, gh issue comment or gh pr review is text, not
# a redirect: the body names a path and writes nothing. Main reads these calls as plain shell, so each form
# reds on the frozen-path rule. The controls pin what stays refused: a redirect or a substitution that
# runs in the body still reaches the rule that reads it.
for _gh_lead, _gh_label in (("gh pr comment 1", "gh pr comment"), ("gh issue comment 1", "gh issue comment"),
                            ("gh pr review 1 --comment", "gh pr review")):
    for _gh_flag, _gh_form in (("--body", '--body "a > %s"'), ("-b", '-b "a > %s"'),
                               ("glued --body=", '--body="a > %s"')):
        sh("frozen data: gh-comment-body, %s with a %s quoted > onto the config settings, allows [gh-comment-body red]"
           % (_gh_label, _gh_flag), _gh_lead + " " + _gh_form % CFG_SETTINGS, "allow", cwd=NOGIT)
sh("frozen data: gh-comment-body, gh pr edit body with a quoted > onto the config settings, allows [gh-comment-body control]",
   "gh pr edit 1 --body \"a > " + CFG_SETTINGS + "\"", "allow", cwd=NOGIT)
sh("frozen data: gh-comment-body, a redirect onto the config settings from a gh pr comment body, denies [gh-comment-body control]",
   "gh pr comment 1 --body hi > " + CFG_SETTINGS, "deny", "frozen-path", cwd=NOGIT)
sh("frozen data: gh-comment-body, a gh pr comment redirect inside bash -c onto the config settings, denies [gh-comment-body control]",
   "bash -c \"gh pr comment 1 --body hi > " + CFG_SETTINGS + "\"", "deny", "frozen-path", cwd=NOGIT)
sh("frozen data: gh-comment-body, a gh pr comment body that is only a $(echo) redirect onto the config settings, denies [gh-comment-body control]",
   "gh pr comment 1 --body \"$(echo hi > " + CFG_SETTINGS + ")\"", "deny", "frozen-path", cwd=NOGIT)
sh("frozen data: gh-comment-body, a gh pr comment body that is only a backtick redirect onto the config settings, denies [gh-comment-body control]",
   "gh pr comment 1 --body \"`echo hi > " + CFG_SETTINGS + "`\"", "deny", "frozen-path", cwd=NOGIT)
sh("env: gh-comment-body, a gh pr comment body that is only a $(cat) of the env file, denies [gh-comment-body control]",
   "gh pr comment 1 --body \"$(cat " + ENV + ")\"", "deny", "env-file", cwd=NOGIT)
sh("env: gh-comment-body, a gh pr comment body that is only a backtick cat of the env file, denies [gh-comment-body control]",
   "gh pr comment 1 --body \"`cat " + ENV + "`\"", "deny", "env-file", cwd=NOGIT)
sh("frozen shell: gh-comment-body, an apostrophe and /* in a gh pr comment body before a real write, denies [gh-comment-body control]",
   "gh pr comment 1 --body \"don't /* stop\" && cat > " + CFG_SETTINGS, "deny", "frozen-path", cwd=NOGIT)
sh("frozen shell: gh-comment-body, a multi-line gh pr comment body with a # before a real write, denies [gh-comment-body control]",
   "gh pr comment 1 --body \"line one\n# two\" ; cat > " + CFG_SETTINGS, "deny", "frozen-path", cwd=NOGIT)

# A program piped into python that reads its program from stdin
# runs as code, so a frozen write inside it must deny, as `python -` does. The /dev/stdin, /dev/fd/0,
# /proc/self/fd/0 and CON forms name the same stdin (_STDIN_FILES).
FROZEN_PY_WRITE = "import os; os.system('tee " + CFG_SETTINGS + " </dev/null')"
sh("frozen stdin: a python program echoed into python -, writes the config settings, denies [r3 pin]",
   "echo \"" + FROZEN_PY_WRITE + "\" | python -", "deny", "frozen-path", cwd=NOGIT)
for _dev in ("/dev/stdin", "/dev/fd/0", "/proc/self/fd/0", "CON"):
    sh("frozen stdin: r3, a python program echoed into python " + _dev + ", writes the config settings, "
       "denies [r3 red]",
       "echo \"" + FROZEN_PY_WRITE + "\" | python " + _dev, "deny", "frozen-path", cwd=NOGIT)

# F1 to F4: each case is a frozen write that reaches the guard as data, so each case names the form in
# its name, and each DENIES. A pipe into an interpreter fails closed by design: the interpreter may run the text.
#
# F1: `_runs_a_file` compared raw words, so a quoted, empty, escaped or variable operand read as a
# script file, and the text piped into it became data.
for _name, _arg in (
    ("a quoted dash", '"-"'),
    ("an empty quote then a dash", '""-'),
    ("a backslash-escaped dash", "\\-"),
    ("an unset variable", '"$X"'),
    ("a quoted stdin path", '"/dev/stdin"'),
):
    sh("frozen stdin: fix F1, a python program piped into python " + _name + " (" + _arg + "), writes the "
       "config settings, denies [cap-ask-fix r1 red]",
       "echo \"" + FROZEN_PY_WRITE + "\" | python " + _arg, "deny", "frozen-path", cwd=NOGIT)
# F2: `python FILE` was a data sink, so text piped into a script file allowed. The text came from an
# echo, from a git commit message, from a gh body, or from a file on a descriptor.
sh("frozen data: fix F2, an echo of a cat-write piped to python run.py, denies [cap-ask-fix r1 red]",
   "echo \"cat > " + CFG_SETTINGS + "\" | python run.py", "deny", "frozen-path", cwd=NOGIT)
sh("frozen data: fix F2, a git commit message naming a cat-write piped to python run.py, denies "
   "[cap-ask-fix r1 red]",
   VCS + " commit -m \"cat > " + CFG_SETTINGS + "\" | python run.py", "deny", "frozen-path", cwd=NOGIT)
sh("frozen data: fix F2, a gh pr create body naming a cat-write piped to python run.py, denies "
   "[cap-ask-fix r1 red]",
   "gh pr create --draft --title \"note\" --body \"cat > " + CFG_SETTINGS + "\" | python run.py",
   "deny", "frozen-path", cwd=NOGIT)
sh("frozen data: fix F2, an echo of a cat-write piped to python on descriptor 3, read from run.py, "
   "denies [cap-ask-fix r1 red]",
   "echo \"cat > " + CFG_SETTINGS + "\" | python /dev/fd/3 3<run.py", "deny", "frozen-path", cwd=NOGIT)
# F3: `_STDIN_FILES` named four stdin spellings and missed four more: a double slash, a doubled zero,
# and a thread-self path. Each is stdin, so each denies.
for _dev in ("/proc/thread-self/fd/0", "//dev/stdin", "/dev/fd/00", "/proc/self/fd/00"):
    sh("frozen stdin: fix F3, a python program piped into python " + _dev + ", writes the config settings, "
       "denies [cap-ask-fix r1 red]",
       "echo \"" + FROZEN_PY_WRITE + "\" | python " + _dev, "deny", "frozen-path", cwd=NOGIT)
# F4: the PowerShell tool reads U+201C and U+201D as double quotes, and reads the text of a `<# #>` block
# comment as nothing. The guard reads the smart quotes as plain text, so an ASCII quote pair around a
# Set-Content is data to it. A comment's ASCII quotes can pair the same way, with no smart quote at all.
# Each shape is a Set-Content that PowerShell runs, so each DENIES.
_F4_WRITE = "Set-Content -Path " + CFG_SETTINGS + " -Value 1"
sh("frozen shell: fix F4, an echo whose smart-quoted argument holds a Set-Content onto the config settings, "
   "denies [cap-ask-fix r1 red]",
   "echo “ \"; " + _F4_WRITE + "; echo \" ”", "deny", "frozen-path", tool="PowerShell", cwd=NOGIT)
sh("frozen shell: fix F4, an echo with a smart close after x, then a Set-Content, then an echo of y, "
   "denies [cap-ask-fix r1 red]",
   "echo “x\"; " + _F4_WRITE + "; echo \"y”", "deny", "frozen-path", tool="PowerShell", cwd=NOGIT)
sh("frozen shell: fix F4, a <# #> block comment holding two ASCII quotes pairs them, so a Set-Content "
   "between two echoes is echo data, denies [cap-ask-fix r1 red]",
   "echo <# \" #> ; " + _F4_WRITE + " ; <# \" #>", "deny", "frozen-path", tool="PowerShell", cwd=NOGIT)

# PWSH-C TEXT MODE. PowerShell reads U+201C and U+201D as double quotes, so `Set-Content -Path “P” -Value 1`
# writes P. The guard's path token keeps the curly quotes, so `is_frozen` does not match P, and the write
# is allowed. That holds for the PowerShell tool, and for a Bash call that runs the same text in
# `pwsh -c` or `powershell -Command`. Each write DENIES.
SMART_CFG_SETTINGS = "“" + CFG_SETTINGS + "”"
SMART_CFG_WRITE = "Set-Content -Path " + SMART_CFG_SETTINGS + " -Value 1"
sh("frozen shell: pwsh-c-text-mode, a Bash call that runs a smart-quoted config settings write in pwsh -c "
   "denies [pwsh-c-text-mode red]",
   "pwsh -c '" + SMART_CFG_WRITE + "'", "deny", "frozen-path", cwd=NOGIT)
sh("frozen shell: pwsh-c-text-mode, a Bash call that runs a smart-quoted config settings write in "
   "powershell -Command denies [pwsh-c-text-mode red]",
   "powershell -Command \"" + SMART_CFG_WRITE + "\"", "deny", "frozen-path", cwd=NOGIT)
sh("frozen shell: pwsh-c-text-mode, the PowerShell tool's smart-quoted config settings write denies "
   "[pwsh-c-text-mode red]",
   SMART_CFG_WRITE, "deny", "frozen-path", tool="PowerShell", cwd=NOGIT)
# Bash reads `\"` inside double quotes as one literal character, so with no PowerShell in the call this
# echo is text and allowed. A PowerShell reading would end the string at the `\"` and read on.
sh("frozen shell: pwsh-c-text-mode, a Bash echo of an escaped quote with no PowerShell is allowed "
   "[pwsh-c-text-mode green]",
   "echo \"a \\\" b\"", "allow", cwd=NOGIT)
# An ASCII apostrophe inside smart-quoted text pairs with a later `'`, so the text reads as one quoted string
# and the Set-Content after it goes unseen. The config settings write after the pair still DENIES.
sh("frozen shell: PowerShell tool, an apostrophe inside smart quotes pairs with a later quote, then a "
   "Set-Content onto the config settings, denies [pwsh-followups red]",
   "Set-Content docs/a.md “it's”; Set-Content -Path " + CFG_SETTINGS + " -Value 'y'", "deny", "frozen-path",
   tool="PowerShell", cwd=NOGIT)
# The same apostrophe pair ahead of a Remove-Item or a positional Set-Content of the config
# settings, each path in smart quotes. Each DENIES on the frozen path. The control after them is a docs path.
sh("frozen shell: PowerShell tool, an apostrophe inside smart quotes, then Remove-Item of the config settings "
   "in smart quotes, denies [pwsh-followups red]",
   "Set-Content docs/a.md “it's”; Remove-Item " + SMART_CFG_SETTINGS, "deny", "frozen-path",
   tool="PowerShell", cwd=NOGIT)
sh("frozen shell: PowerShell tool, an apostrophe inside smart quotes, then a positional Set-Content of the config "
   "settings in smart quotes, denies [pwsh-followups red]",
   "Set-Content docs/a.md “it's”; Set-Content " + SMART_CFG_SETTINGS + " v", "deny", "frozen-path",
   tool="PowerShell", cwd=NOGIT)
sh("frozen shell: PowerShell tool, an apostrophe inside smart quotes, then a Set-Content of a docs file, "
   "is allowed [pwsh-followups green]",
   "Set-Content docs/a.md “it's”; Set-Content docs/b.md v", "allow", tool="PowerShell", cwd=NOGIT)

# NESTED-SCRIPT PINS. `_shell_write_hit` judges the PowerShell text that `cmd /c` or `iex` runs by PowerShell's
# rules, through `_powershell_scripts_of`. Each DENIES on that step alone. The `cmd /c` text is quoted: a bare `&`
# in Bash backgrounds the first command, and detached-launch denies that before the write is read.
sh("frozen shell: pwsh-c-text-mode pin, cmd /c runs a smart-quoted config settings write after a `&` inside "
   "double quotes and denies [pwsh-c-text-mode pin]",
   "cmd /c \"echo don’t & copy NUL " + SMART_CFG_SETTINGS + "\"", "deny", "frozen-path", cwd=NOGIT)
sh("frozen shell: pwsh-c-text-mode pin, iex runs a smart-quoted config settings write whose comment holds a "
   "double quote, and denies [pwsh-c-text-mode pin]",
   "iex 'Set-Content -Path " + SMART_CFG_SETTINGS + " -Value 1 # don\"t'", "deny", "frozen-path", cwd=NOGIT)
# NESTED SHELL. A Bash, sh or env -S call that runs `pwsh -c` hands that text on as a plain string.
# `_powershell_scripts_of` reads the `pwsh -c` inside it as PowerShell. Each DENIES.
sh("frozen shell: pwsh-c-text-mode, bash -c runs a pwsh -c smart-quoted config settings write and denies "
   "[pwsh-c-text-mode red]",
   "bash -c \"pwsh -c '" + SMART_CFG_WRITE + "'\"", "deny", "frozen-path", cwd=NOGIT)
sh("frozen shell: pwsh-c-text-mode, sh -c runs a pwsh -c smart-quoted config settings write and denies "
   "[pwsh-c-text-mode red]",
   "sh -c \"pwsh -c '" + SMART_CFG_WRITE + "'\"", "deny", "frozen-path", cwd=NOGIT)
sh("frozen shell: pwsh-c-text-mode, env -S runs a pwsh -c smart-quoted config settings write and denies "
   "[pwsh-c-text-mode red]",
   "env -S \"pwsh -c '" + SMART_CFG_WRITE + "'\"", "deny", "frozen-path", cwd=NOGIT)


# ================================================================ 6a-2. cap-ask-fix (frozen)
# Each case is a frozen write the guard reads as text, so each case names its safety hole. Each DENIES. The
# cap-key twins of H2 and H3 are in the model-cap section below.
#
# H1: `_words_of` cuts a word at each quote, so a frozen path with a quote inside it reads as two
# words, and neither word is a frozen path. One case per writer in hooks/, then one per folder.
# H2: `printf` is a printer, so its quoted text is data. The text still runs: through `eval`, `bash -c`,
# a bare `$D`, or a `${F@P}` prompt expansion, which runs the `$(...)` inside its value.
# H3: `_name` reads only the basename of a command word. A function, a local script or a PATH entry
# named `cat` reads as the printer `cat`, so the text piped into it is data, and the function runs it.
R2_HOOK_SQ = slash(os.path.join(CFG, "hooks")) + "/'g.py'"        # the path with a quote pair in it
R2_HOOK_DQ = '"' + slash(os.path.join(CFG, "hooks")) + '/"g.py'   # the same, with the pair double-quoted
R2_WRITE = "echo 1 > " + CFG_SETTINGS                             # a frozen write, held as text
R2_PS_WRITE = "Set-Content -Path " + CFG_SETTINGS + " -Value 1"


def r2_printf_forms(write):
    """H2: a printf stores `write` in a variable, and each form runs the variable."""
    return (
        ("eval", "printf -v D '%s' '" + write + "'; eval \"$D\""),
        ("bash -c", "printf -v D '%s' '" + write + "'; bash -c \"$D\""),
        ("a bare $D", "printf -v D '%s' '" + write + "'; $D"),
        ("the ${F@P} prompt expansion",
         "printf -v F '%s' '$(" + write + ")'; echo \"${F@P}\""),
    )


def r2_function_forms(write):
    """H3: a command named `cat` that runs its input, or a local `cat`, takes the piped text."""
    return (
        ("a shell function named cat", "cat() { sh; }; echo '" + write + "' | cat"),
        ("a function declared with the function keyword",
         "function cat { sh; }; echo '" + write + "' | cat"),
        ("a local script named cat", "echo '" + write + "' | ./cat"),
        ("a PATH entry named cat", "PATH=./b:$PATH; echo '" + write + "' | cat"),
    )


for _writer, _command in (
    ("cp", "cp a " + R2_HOOK_SQ),
    ("echo redirect", "echo x > " + R2_HOOK_DQ),
    ("tee", "echo x | tee " + R2_HOOK_SQ),
    ("rm", "rm " + R2_HOOK_SQ),
    ("mv", "mv a " + R2_HOOK_SQ),
    ("sed -i", "sed -i 's/x/y/' " + R2_HOOK_SQ),
    ("install", "install a " + R2_HOOK_SQ),
):
    sh("frozen path: fix H1, " + _writer + " onto a hook path with a quote in it denies "
       "[cap-ask-fix r2 red]", _command, "deny", "frozen-path", cwd=NOGIT)
sh("frozen path: fix H1, Set-Content onto a hook path with a quote in it denies [cap-ask-fix r2 red]",
   "Set-Content -Path " + R2_HOOK_SQ + " -Value 1", "deny", "frozen-path", tool="PowerShell", cwd=NOGIT)
for _folder, _name in (("lint", "prose.py"), ("state", "entry.json"), ("agents", "builder.md"),
                       ("bin", "merge.py"), ("output-styles", "shiv.md")):
    sh("frozen path: fix H1, cp a " + _folder + " file with a quote in its name denies "
       "[cap-ask-fix r2 red]", "cp a " + slash(os.path.join(CFG, _folder)) + "/'" + _name + "'",
       "deny", "frozen-path", cwd=NOGIT)

for _how, _command in r2_printf_forms(R2_WRITE):
    sh("frozen shell: fix H2, printf stores a frozen write and " + _how + " runs it, denies "
       "[cap-ask-fix r2 red]", _command, "deny", "frozen-path", cwd=NOGIT)
for _how, _command in r2_function_forms(R2_WRITE):
    sh("frozen shell: fix H3, " + _how + " takes the piped frozen write, denies [cap-ask-fix r2 red]",
       _command, "deny", "frozen-path", cwd=NOGIT)
sh("frozen shell: fix H3, Set-Alias maps echo to iex, a Set-Content onto the config settings denies "
   "[cap-ask-fix r2 red]", "Set-Alias echo iex; echo '" + R2_PS_WRITE + "'", "deny", "frozen-path",
   tool="PowerShell", cwd=NOGIT)

# FIVE ALLOW PINS. Each names a frozen path or a settings copy in text a reader or a message carries,
# and each stays allowed.
sh("frozen pin: grep -n of a hooks file allows [cap-ask-fix r2 pin]",
   "grep -n \"tee\" " + CFG_HOOK, "allow", cwd=NOGIT)
sh("frozen pin: jq of the settings file allows [cap-ask-fix r2 pin]",
   "jq . " + CFG_SETTINGS, "allow", cwd=NOGIT)
sh("frozen pin: git commit -m naming a hooks path allows [cap-ask-fix r2 pin]",
   VCS + " commit -m \"edit " + CFG_HOOK + "\"", "allow", cwd=NOGIT)
sh("frozen pin: echo naming a settings copy allows [cap-ask-fix r2 pin]",
   "echo \"cp a " + CFG_SETTINGS + "\"", "allow", cwd=NOGIT)
sh("frozen pin: gh pr create --title naming the global CLAUDE.md allows [cap-ask-fix r2 pin]",
   "gh pr create --draft --title \"Update " + CFG_CLAUDEMD + "\" --body \"notes\"", "allow", cwd=NOGIT)

# A FROZEN PATH HELD IN A SHELL VARIABLE, written by a script that a `python -c` or `node -e` runs. The guard
# expands `$F` in the command text, so the script's own text names the frozen hook, and the write denies. The
# same text printed by python writes nothing, so it allows.
sh("frozen var: a frozen hook path in a shell variable, written by os.system in python -c, denies",
   "F=" + slash(CFG) + "; python3 -c \"import os; os.system('echo x >> $F/hooks/guard.py')\"",
   "deny", "frozen-path", cwd=NOGIT)
sh("frozen var: a frozen hook path in a shell variable, written by execSync in node -e, denies",
   "F=" + slash(CFG) + "; node -e \"require('child_process').execSync('echo x >> $F/hooks/guard.py')\"",
   "deny", "frozen-path", cwd=NOGIT)
sh("frozen var: a frozen hook path in a shell variable, printed by python -c, writes nothing and allows",
   "F=" + slash(CFG) + "; python3 -c \"print('echo x >> $F/hooks/guard.py')\"",
   "allow", cwd=NOGIT)

# A FROZEN PATH JOINED BY `+` INSIDE A `node -e` STRING. The whole-script reading cannot read a string join, so
# the script's text is refused whole. Each command writes the frozen hook through the joined path, so each denies.
sh("frozen join: a frozen hook path joined by + into a node -e execSync cp, denies",
   "node -e \"const p='" + CFG_HOOK + "'; require('child_process').execSync('cp /tmp/x ' + p)\"",
   "deny", "frozen-path", cwd=NOGIT)
sh("frozen join: a frozen hook path joined by + into a node -e execSync tee, denies",
   "node -e \"const p='" + CFG_HOOK + "'; require('child_process').execSync('tee ' + p)\"",
   "deny", "frozen-path", cwd=NOGIT)


# A FROZEN HOOK OR CAP PATH HELD IN A SHELL VARIABLE, WRITTEN BY A HEREDOC BODY THAT PYTHON OR NODE RUNS. The body
# is a script, so the guard reads it at its shell spots, and `$F` in it stands for the variable's value. An
# unquoted heredoc expands `$F` in the shell before the interpreter runs, so a plain `F=` is enough there. A quoted
# heredoc keeps `$F` literal, so its case exports F: the child shell that os.system or execSync starts reads `$F`
# from the environment. A plain `F=` with a quoted heredoc writes nothing, so no case uses that pair. The cap key
# is CLAUDE_CODE_SUBAGENT_MODEL, the same name CAP_KEY holds further down.
sh("frozen heredoc var: a frozen hook path in F, set by F= before an unquoted python heredoc whose os.system writes $F, denies",
   "F=" + CFG_HOOK + "; python3 - <<EOF\nimport os\nos.system(\"echo x >> $F\")\nEOF",
   "deny", "frozen-path", cwd=NOGIT)
sh("frozen heredoc var: a frozen hook path in F, exported before a quoted python heredoc whose os.system writes $F, denies",
   "export F=" + CFG_HOOK + "; python3 - <<'EOF'\nimport os\nos.system(\"echo x >> $F\")\nEOF",
   "deny", "frozen-path", cwd=NOGIT)
sh("frozen heredoc var: an apostrophe in a python comment ahead of the os.system write of $F, denies",
   "export F=" + CFG_HOOK + "; python3 - <<'EOF'\n# don't write here\nimport os\nos.system(\"echo x >> $F\")\nEOF",
   "deny", "frozen-path", cwd=NOGIT)
sh("frozen heredoc var: a # inside a python string ahead of the os.system write of $F, denies",
   "export F=" + CFG_HOOK + "; python3 - <<'EOF'\nmsg = '# note'\nimport os\nos.system(\"echo x >> $F\")\nEOF",
   "deny", "frozen-path", cwd=NOGIT)
chained_ask("cap heredoc var: a cap write to $F, set by F= before an unquoted python heredoc whose os.system writes it, denies as a chained ask command",
   "F=" + PROJ_SETTINGS + "; python3 - <<EOF\nimport os\nos.system(\"echo CLAUDE_CODE_SUBAGENT_MODEL=opus > $F\")\nEOF",
   cwd=NOGIT, carries=("agent-model-cap",))
chained_ask("cap heredoc var: a cap write to $F, exported with a semicolon before a quoted python heredoc, denies as a chained ask command",
   "export F=" + PROJ_SETTINGS + "; python3 - <<'EOF'\nimport os\nos.system(\"echo CLAUDE_CODE_SUBAGENT_MODEL=opus > $F\")\nEOF",
   cwd=NOGIT, carries=("agent-model-cap",))
sh("cap heredoc var: a cap write to $F, exported with && before a quoted python heredoc, asks as a lone command",
   "export F=" + PROJ_SETTINGS + " && python3 - <<'EOF'\nimport os\nos.system(\"echo CLAUDE_CODE_SUBAGENT_MODEL=opus > $F\")\nEOF",
   "ask", "agent-model-cap", cwd=NOGIT, carries=("agent-model-cap",))
# CONTROLS. The same bodies with the path written out keep their verdict, and a $F that python only prints allows.
sh("frozen heredoc var control: a literal frozen hook path in a quoted python heredoc, denies",
   "python3 - <<'EOF'\nimport os\nos.system(\"echo x >> " + CFG_HOOK + "\")\nEOF", "deny", "frozen-path", cwd=NOGIT)
sh("frozen heredoc var control: a literal frozen hook path in a quoted node heredoc, denies",
   "node - <<'EOF'\nrequire('child_process').execSync('echo x >> " + CFG_HOOK + "')\nEOF", "deny", "frozen-path", cwd=NOGIT)
sh("cap heredoc var control: a literal settings path in an unquoted python heredoc, asks as the cap",
   "python3 - <<EOF\nimport os\nos.system(\"echo CLAUDE_CODE_SUBAGENT_MODEL=opus > " + PROJ_SETTINGS + "\")\nEOF",
   "ask", "agent-model-cap", cwd=NOGIT, carries=("agent-model-cap",))
sh("frozen heredoc var control: $F only printed by python in a quoted heredoc, the shell writes nothing, allows",
   "export F=" + CFG_HOOK + "; python3 - <<'EOF'\nprint(\"echo x >> $F\")\nEOF", "allow", cwd=NOGIT)


# =========================================================================== 6b. the model cap

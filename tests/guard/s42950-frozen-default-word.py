# section 42950
FAMILY = "frozen"
#
# Rule 7 reads the default-word forms of a shell variable as the shell does. `${VAR:-word}` takes the word
# when VAR is unset or empty, `${VAR-word}` only when VAR is unset, and `${VAR:?}` takes the value. The value
# comes from the command's own assignment, else from the environment. A write whose resolved target is a
# frozen path is refused. The red cases name a frozen path only through such a form, so the guard allows
# them today. The controls name a folder outside the frozen set, or a value the word may not replace, and
# pass before and after the change. `${VAR:+word}` is not read, so its case pins the allow.

# With CLAUDE_CONFIG_DIR unset, the guard reads the config dir as HOME/.claude. DW_HOME stands in for the
# home folder. USERPROFILE is set too, because Windows expanduser reads it, not HOME.
DW_HOME = os.path.join(ROOT, "dwhome")
DW_OUTSIDE = os.path.join(ROOT, "dwelsewhere")   # a folder outside the frozen set
DW_UNSET = {"CLAUDE_CONFIG_DIR": None, "HOME": DW_HOME, "USERPROFILE": DW_HOME}   # the variable is not set
DW_EMPTY = {"CLAUDE_CONFIG_DIR": "", "HOME": DW_HOME, "USERPROFILE": DW_HOME}     # set, and empty
DW_DEFAULT = "${CLAUDE_CONFIG_DIR:-$HOME/.claude}"
DW_NO_COLON = "${CLAUDE_CONFIG_DIR-$HOME/.claude}"

# RED. The word names the config dir, and the variable is unset or empty, so the word is the target.
for _rel in ("hooks/guard.py", "CLAUDE.md"):
    sh("frozen: default-word: :- with CLAUDE_CONFIG_DIR unset, a write to %s, is refused" % _rel,
       'printf x > "%s/%s"' % (DW_DEFAULT, _rel), "deny", "frozen-path", cwd=NOGIT, env=DW_UNSET)
    sh("frozen: default-word: :- with CLAUDE_CONFIG_DIR set empty, a write to %s, is refused" % _rel,
       'printf x > "%s/%s"' % (DW_DEFAULT, _rel), "deny", "frozen-path", cwd=NOGIT, env=DW_EMPTY)
    sh("frozen: default-word: - with CLAUDE_CONFIG_DIR unset, a write to %s, is refused" % _rel,
       'printf x > "%s/%s"' % (DW_NO_COLON, _rel), "deny", "frozen-path", cwd=NOGIT, env=DW_UNSET)
sh("frozen: default-word: :- with CLAUDE_CONFIG_DIR unset, an unquoted write to hooks/guard.py, is refused",
   "printf x > %s/hooks/guard.py" % DW_DEFAULT, "deny", "frozen-path", cwd=NOGIT, env=DW_UNSET)

# RED. A variable read from the environment as its value: the word /tmp/x is not taken.
sh("frozen: default-word: CLAUDE_CONFIG_DIR set non-empty in the environment is read, and /tmp/x is not",
   'printf x > "${CLAUDE_CONFIG_DIR:-/tmp/x}/hooks/guard.py"', "deny", "frozen-path", cwd=NOGIT,
   env={"CLAUDE_CONFIG_DIR": CFG})
sh("frozen: default-word: DW_DIR set non-empty in the environment to the config dir is read, /tmp/x is not",
   'printf x > "${DW_DIR:-/tmp/x}/hooks/guard.py"', "deny", "frozen-path", cwd=NOGIT, env={"DW_DIR": CFG})
sh("frozen: default-word: DW_DIR set empty in the environment takes the word, the config hook",
   'printf x > "${DW_DIR:-%s}/hooks/guard.py"' % CFG, "deny", "frozen-path", cwd=NOGIT, env={"DW_DIR": ""})
sh("frozen: default-word: DW_DIR unset takes the word, the config hook",
   'printf x > "${DW_DIR:-%s}/hooks/guard.py"' % CFG, "deny", "frozen-path", cwd=NOGIT, env={"DW_DIR": None})

# RED. A variable the command assigns: its value is read, and the word is not taken.
sh("frozen: default-word: DW_DIR set in the command to the config dir is read, and /tmp/x is not",
   'DW_DIR="%s"; printf x > "${DW_DIR:-/tmp/x}/hooks/guard.py"' % CFG, "deny", "frozen-path", cwd=NOGIT,
   env={"DW_DIR": None})

# RED. `:?` takes the value, set in the environment or in the command.
sh("frozen: default-word: :? with CLAUDE_CONFIG_DIR set in the environment, a write to hooks/guard.py, is refused",
   'printf x > "${CLAUDE_CONFIG_DIR:?}/hooks/guard.py"', "deny", "frozen-path", cwd=NOGIT,
   env={"CLAUDE_CONFIG_DIR": CFG})
sh("frozen: default-word: :? of DW_DIR set in the command to the config dir, a write to hooks/guard.py, is refused",
   'DW_DIR="%s"; printf x > "${DW_DIR:?}/hooks/guard.py"' % CFG, "deny", "frozen-path", cwd=NOGIT,
   env={"DW_DIR": None})

# CONTROLS. Each passes before the change and after it.
# `-` keeps an empty value: the word is not taken, so the target is /hooks/guard.py, which is no frozen path.
sh("frozen: default-word: - with CLAUDE_CONFIG_DIR set empty keeps the empty value, /hooks/guard.py is allowed",
   'printf x > "${CLAUDE_CONFIG_DIR-/tmp/elsewhere}/hooks/guard.py"', "allow", cwd=NOGIT, env=DW_EMPTY)
sh("frozen: default-word: - with CLAUDE_CONFIG_DIR set empty does not take the frozen word, allowed",
   'printf x > "%s/hooks/guard.py"' % DW_NO_COLON, "allow", cwd=NOGIT, env=DW_EMPTY)
# A value the command assigns to a folder outside the frozen set is read, so the word CFG is not taken.
sh("frozen: default-word: DW_DIR set in the command to a folder outside the frozen set, allowed",
   'DW_DIR=/tmp/elsewhere; printf x > "${DW_DIR:-%s}/hooks/guard.py"' % CFG, "allow", cwd=NOGIT,
   env={"DW_DIR": None})
# The same for a value set non-empty in the environment.
sh("frozen: default-word: DW_DIR set in the environment to a folder outside the frozen set, allowed",
   'printf x > "${DW_DIR:-%s}/hooks/guard.py"' % CFG, "allow", cwd=NOGIT, env={"DW_DIR": DW_OUTSIDE})
# A safe default folder is no frozen path.
sh("frozen: default-word: a safe default ${OUT:-/tmp/x}/f is allowed",
   'printf x > "${OUT:-/tmp/x}/f"', "allow", cwd=NOGIT, env={"OUT": None})
# `:+` is not read. Its word x gives the target x/hooks/guard.py, a relative folder no frozen path sits under.
sh("frozen: default-word: :+ is not read: CLAUDE_CONFIG_DIR set, ${CLAUDE_CONFIG_DIR:+x}/hooks/guard.py, is allowed",
   'printf x > "${CLAUDE_CONFIG_DIR:+x}/hooks/guard.py"', "allow", cwd=NOGIT, env={"CLAUDE_CONFIG_DIR": CFG})
# Single quotes do not expand, so the target is the literal text, which no frozen path is.
sh("frozen: default-word: single quotes do not expand the default word, allowed",
   "printf x > '${CLAUDE_CONFIG_DIR:-$HOME/.claude}/hooks/guard.py'", "allow", cwd=NOGIT, env=DW_UNSET)
# The control that the fixture is right: a literal $HOME/.claude is the frozen folder once HOME is DW_HOME.
sh("frozen: default-word: control, a literal $HOME/.claude with CLAUDE_CONFIG_DIR unset, is refused",
   'printf x > "$HOME/.claude/hooks/guard.py"', "deny", "frozen-path", cwd=NOGIT, env=DW_UNSET)
sh("frozen: default-word: control, the plain ${CLAUDE_CONFIG_DIR} with it set, a write to hooks/guard.py, is refused",
   'printf x > "${CLAUDE_CONFIG_DIR}/hooks/guard.py"', "deny", "frozen-path", cwd=NOGIT,
   env={"CLAUDE_CONFIG_DIR": CFG})

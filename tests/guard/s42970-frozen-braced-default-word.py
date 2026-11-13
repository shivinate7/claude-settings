# section 42970
FAMILY = "frozen"
#
# A default word may hold a braced variable, `${CLAUDE_CONFIG_DIR:-${HOME}/.claude}`. The shell takes the word
# when the variable is unset (or empty, under `:-`), and expands the word's own `${HOME}`. Section 42950 covers the
# words with no brace. The red cases name a frozen folder only through a braced word, so the guard allows them
# today. The controls name a folder outside the frozen set, or a word the shell does not take, and pass before and
# after the change. DW_UNSET, DW_EMPTY and DW_OUTSIDE are section 42950's fixtures.

# RED. The braced word is the target: the variable is unset, or set empty under `:-`.
sh("frozen: braced default-word: :- with CLAUDE_CONFIG_DIR unset, a write to hooks/guard.py, is refused",
   'printf x > "${CLAUDE_CONFIG_DIR:-${HOME}/.claude}/hooks/guard.py"', "deny", "frozen-path", cwd=NOGIT,
   env=DW_UNSET)
sh("frozen: braced default-word: :- with CLAUDE_CONFIG_DIR set empty, a write to hooks/guard.py, is refused",
   'printf x > "${CLAUDE_CONFIG_DIR:-${HOME}/.claude}/hooks/guard.py"', "deny", "frozen-path", cwd=NOGIT,
   env=DW_EMPTY)
# RED. A value set in the environment is read, so the word is not taken: the value is the config dir.
sh("frozen: braced default-word: CLAUDE_CONFIG_DIR set in the environment is read, a write to hooks/guard.py is refused",
   'printf x > "${CLAUDE_CONFIG_DIR:-${HOME}/.claude}/hooks/guard.py"', "deny", "frozen-path", cwd=NOGIT,
   env={"CLAUDE_CONFIG_DIR": CFG})

# CONTROLS. Each passes before the change and after it.
# A value outside the frozen set is read, and the braced word, which is frozen, is not taken. DW_DIR, not the
# config variable, holds the folder: the config dir stays HOME/.claude, so DW_OUTSIDE is not frozen.
sh("frozen: braced default-word: DW_DIR set in the environment to a folder outside the frozen set, allowed",
   'printf x > "${DW_DIR:-${HOME}/.claude}/hooks/guard.py"', "allow", cwd=NOGIT,
   env=dict(DW_UNSET, DW_DIR=DW_OUTSIDE))
# A safe braced default folder is no frozen path: ${HOME}/tmp is outside the frozen set.
sh("frozen: braced default-word: a safe braced default ${OUT:-${HOME}/tmp}/f is allowed",
   'printf x > "${OUT:-${HOME}/tmp}/f"', "allow", cwd=NOGIT, env=dict(DW_UNSET, OUT=None))

# A name the command sets to `$(...)` is a value the guard cannot read. The shell reads the real value, a temp
# folder, so the word is not taken and the write is allowed. A guard that takes the word for a name it cannot
# read refuses this write, which is a false alarm.
sh("frozen: default-word: D set by $(mktemp -d) in the command is not the word, a write under ${D:-CFG/hooks} is allowed",
   'D=$(mktemp -d); printf x > "${D:-%s/hooks}/f"' % CFG, "allow", cwd=NOGIT, env={"D": None})

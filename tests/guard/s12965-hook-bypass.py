# section 12965
FAMILY = "hook-bypass"
HOOK_BYPASS = "hook-bypass"

# (1) The key on the command line, for each verb that runs hooks.
sh("hook-bypass: core.hooksPath on the command, commit, denies",
   VCS + " -c core.hooksPath=x commit -m x", "deny", HOOK_BYPASS, cwd=GITMAIN)
sh("hook-bypass: core.hooksPath on the command, merge, denies",
   VCS + " -c core.hooksPath=x merge feature/x", "deny", HOOK_BYPASS, cwd=GITMAIN)
sh("hook-bypass: core.hooksPath on the command, push, denies",
   VCS + " -c core.hooksPath=x push origin feature/x", "deny", HOOK_BYPASS, cwd=GITMAIN)
sh("hook-bypass: the key in capitals on the command, Core.HooksPath, denies",
   VCS + " -c Core.HooksPath=x commit -m x", "deny", HOOK_BYPASS, cwd=GITMAIN)
sh("hook-bypass: control, commit with no hooks key, allows",
   VCS + " commit -m x", "allow", cwd=GITMAIN)
sh("hook-bypass: control, merge with no hooks key, allows",
   VCS + " merge feature/x", "allow", cwd=GITMAIN)
sh("hook-bypass: control, push with no hooks key, allows",
   VCS + " push origin feature/x", "allow", cwd=GITMAIN)

# (2) --no-verify on commit, merge and push.
sh("hook-bypass: --no-verify on commit, denies",
   VCS + " commit --no-verify -m x", "deny", HOOK_BYPASS, cwd=GITMAIN)
sh("hook-bypass: --no-verify on merge, denies",
   VCS + " merge --no-verify feature/x", "deny", HOOK_BYPASS, cwd=GITMAIN)
sh("hook-bypass: --no-verify on push, denies",
   VCS + " push --no-verify origin feature/x", "deny", HOOK_BYPASS, cwd=GITMAIN)

# (3) -n on commit is --no-verify. Bundled with -m, and after the other flags, it is still the bypass.
sh("hook-bypass: -n on commit is --no-verify, denies",
   VCS + " commit -n -m x", "deny", HOOK_BYPASS, cwd=GITMAIN)
sh("hook-bypass: -n bundled with -m on commit, -nm x, denies",
   VCS + " commit -nm x", "deny", HOOK_BYPASS, cwd=GITMAIN)
sh("hook-bypass: --no-verify after the other flags and the message, denies",
   VCS + " commit -am x --no-verify", "deny", HOOK_BYPASS, cwd=GITMAIN)
sh("hook-bypass: control, commit -am x with no bypass, allows",
   VCS + " commit -am x", "allow", cwd=GITMAIN)
sh("hook-bypass: -mn on commit is the message n, not -n, allows",
   VCS + " commit -mn", "allow", cwd=GITMAIN)

# (4) The bypass reached through -C, a chain, a cd and a second line.
sh("hook-bypass: --no-verify after git -C <dir>, denies",
   VCS + " -C " + slash(GITMAIN) + " commit --no-verify -m x", "deny", HOOK_BYPASS, cwd=GITMAIN)
sh("hook-bypass: control, git -C <dir> commit with no bypass, allows",
   VCS + " -C " + slash(GITMAIN) + " commit -m x", "allow", cwd=GITMAIN)
sh("hook-bypass: --no-verify after a status in an && chain, denies",
   VCS + " status && " + VCS + " commit --no-verify -m x", "deny", HOOK_BYPASS, cwd=GITMAIN)
sh("hook-bypass: control, the same && chain with no bypass, allows",
   VCS + " status && " + VCS + " commit -m x", "allow", cwd=GITMAIN)
sh("hook-bypass: core.hooksPath after a cd, denies",
   "cd " + slash(GITMAIN) + " && " + VCS + " -c core.hooksPath=x commit -m x", "deny", HOOK_BYPASS,
   cwd=GITMAIN)
sh("hook-bypass: control, a cd and then a commit with no bypass, allows",
   "cd " + slash(GITMAIN) + " && " + VCS + " commit -m x", "allow", cwd=GITMAIN)
sh("hook-bypass: --no-verify on the second line of a command, denies",
   VCS + " status\n" + VCS + " commit --no-verify -m x", "deny", HOOK_BYPASS, cwd=GITMAIN)
sh("hook-bypass: control, the same two lines with no bypass, allows",
   VCS + " status\n" + VCS + " commit -m x", "allow", cwd=GITMAIN)

# (5) The key set in the environment. GIT_CONFIG_COUNT and GIT_CONFIG_PARAMETERS, each with a control that sets
# another key, so the value is read and not only the variable's name.
sh("hook-bypass: GIT_CONFIG_COUNT sets core.hooksPath for a commit, denies",
   "GIT_CONFIG_COUNT=1 GIT_CONFIG_KEY_0=core.hooksPath GIT_CONFIG_VALUE_0=/dev/null " + VCS
   + " commit -m x", "deny", HOOK_BYPASS, cwd=GITMAIN)
sh("hook-bypass: control, GIT_CONFIG_COUNT sets user.name for a commit, allows",
   "GIT_CONFIG_COUNT=1 GIT_CONFIG_KEY_0=user.name GIT_CONFIG_VALUE_0=x " + VCS + " commit -m x",
   "allow", cwd=GITMAIN)
sh("hook-bypass: GIT_CONFIG_PARAMETERS sets core.hooksPath for a push, denies",
   "GIT_CONFIG_PARAMETERS=\"'core.hooksPath'='/dev/null'\" " + VCS + " push origin feature/x",
   "deny", HOOK_BYPASS, cwd=GITMAIN)
sh("hook-bypass: control, GIT_CONFIG_PARAMETERS sets user.name for a push, allows",
   "GIT_CONFIG_PARAMETERS=\"'user.name'='x'\" " + VCS + " push origin feature/x", "allow", cwd=GITMAIN)

# (6) Scanner shapes: a lone apostrophe, and a # inside quotes, before the bypass. The guard reads the text the
# shell reads, so neither quote nor comment opener may hide the flag that follows.
sh("hook-bypass: a lone apostrophe in text before a bypass, denies",
   "echo don't; " + VCS + " commit --no-verify -m x", "deny", HOOK_BYPASS, cwd=GITMAIN)
sh("hook-bypass: control, a lone apostrophe before a plain commit, allows",
   "echo don't; " + VCS + " commit -m x", "allow", cwd=GITMAIN)
sh("hook-bypass: a # inside a quoted message does not hide a later --no-verify, denies",
   VCS + ' commit -m "a # b" --no-verify', "deny", HOOK_BYPASS, cwd=GITMAIN)
sh("hook-bypass: control, a # inside a quoted message with no bypass, allows",
   VCS + ' commit -m "a # b"', "allow", cwd=GITMAIN)
sh("hook-bypass: a # inside an echo string does not hide a bypass after it, denies",
   'echo "# note"; ' + VCS + " -c core.hooksPath=x commit -m x", "deny", HOOK_BYPASS, cwd=GITMAIN)
sh("hook-bypass: control, a # inside an echo string before a plain commit, allows",
   'echo "# note"; ' + VCS + " commit -m x", "allow", cwd=GITMAIN)

# (7) PowerShell takes the same key on the command line, and its control with no key allows.
sh("hook-bypass: PowerShell, core.hooksPath on the command, denies",
   VCS + " -c core.hooksPath=x commit -m x", "deny", HOOK_BYPASS, tool="PowerShell", cwd=GITMAIN)
sh("hook-bypass: control, PowerShell commit with no hooks key, allows",
   VCS + " commit -m x", "allow", tool="PowerShell", cwd=GITMAIN)

# (8) A bypass wrapped in another command: a shell, eval, env -S, xargs or timeout. The guard reads the command the
# wrapper runs, not only the first word, so each wrapped bypass denies. The controls wrap a commit with no bypass,
# or text that names one, and allow.
sh("hook-bypass: --no-verify in a bash -c string, denies",
   'bash -c "' + VCS + ' commit --no-verify -m x"', "deny", HOOK_BYPASS, cwd=GITMAIN)
sh("hook-bypass: -n in an sh -c string, denies",
   "sh -c '" + VCS + " commit -n -m x'", "deny", HOOK_BYPASS, cwd=GITMAIN)
sh("hook-bypass: --no-verify in an eval string, denies",
   'eval "' + VCS + ' commit --no-verify -m x"', "deny", HOOK_BYPASS, cwd=GITMAIN)
sh("hook-bypass: --no-verify in an env -S string, denies",
   'env -S "' + VCS + ' commit --no-verify -m x"', "deny", HOOK_BYPASS, cwd=GITMAIN)
sh("hook-bypass: core.hooksPath in a bash -c string, denies",
   'bash -c "' + VCS + ' -c core.hooksPath=/dev/null commit -m x"', "deny", HOOK_BYPASS, cwd=GITMAIN)
sh("hook-bypass: --no-verify fed to xargs, denies",
   "echo --no-verify | xargs " + VCS + " commit -m x", "deny", HOOK_BYPASS, cwd=GITMAIN)
sh("hook-bypass: --no-verify after timeout 5, denies",
   "timeout 5 " + VCS + " commit --no-verify -m x", "deny", HOOK_BYPASS, cwd=GITMAIN)
sh("hook-bypass: control, a bash -c string with a commit and no bypass, allows",
   'bash -c "' + VCS + ' commit -m x"', "allow", cwd=GITMAIN)
sh("hook-bypass: control, a bash -c echo that names a bypass is text, allows",
   "bash -c 'echo " + VCS + " commit --no-verify'", "allow", cwd=GITMAIN)
sh("hook-bypass: control, a sh -c string with a push -n dry run, allows",
   'sh -c "' + VCS + ' push -n"', "allow", cwd=GITMAIN)

# (8b) A config write that turns hooks off, with a commit, merge or push after it in the same command, is denied.
# DECIDED: a config write with nothing after it in the command is allowed. It sets a value and skips no hook; the
# case below pins that. The controls read the key, unset it, set another key, or name the write in text.
sh("hook-bypass: config core.hooksPath set, then a commit in the same command, denies",
   VCS + " config core.hooksPath /dev/null && " + VCS + " commit -m x", "deny", HOOK_BYPASS, cwd=GITMAIN)
sh("hook-bypass: config --local core.hooksPath set, then a commit, denies",
   VCS + " config --local core.hooksPath /dev/null && " + VCS + " commit -m x", "deny", HOOK_BYPASS, cwd=GITMAIN)
sh("hook-bypass: config --worktree core.hooksPath set, then a commit, denies",
   VCS + " config --worktree core.hooksPath /dev/null && " + VCS + " commit -m x", "deny", HOOK_BYPASS, cwd=GITMAIN)
sh("hook-bypass: config --global core.hooksPath set, then a commit, denies",
   VCS + " config --global core.hooksPath /dev/null && " + VCS + " commit -m x", "deny", HOOK_BYPASS, cwd=GITMAIN)
sh("hook-bypass: config --add core.hooksPath, then a push after a semicolon, denies",
   VCS + " config --add core.hooksPath x; " + VCS + " push", "deny", HOOK_BYPASS, cwd=GITMAIN)
sh("hook-bypass: config core.hookspath set with -C, then a merge, denies (key case-blind)",
   VCS + " -C " + slash(GITMAIN) + " config core.hookspath x && " + VCS + " merge y", "deny", HOOK_BYPASS,
   cwd=GITMAIN)
sh("hook-bypass: control, a config read of core.hooksPath, allows",
   VCS + " config core.hooksPath", "allow", cwd=GITMAIN)
sh("hook-bypass: control, a config --get of core.hooksPath, then a commit, allows",
   VCS + " config --get core.hooksPath && " + VCS + " commit -m x", "allow", cwd=GITMAIN)
sh("hook-bypass: control, a config --unset of core.hooksPath, allows",
   VCS + " config --unset core.hooksPath", "allow", cwd=GITMAIN)
sh("hook-bypass: control, a config write of user.name, then a commit, allows",
   VCS + " config user.name x && " + VCS + " commit -m x", "allow", cwd=GITMAIN)
sh("hook-bypass: control, a quoted mention of the config write, then a commit, allows",
   'echo "git config core.hooksPath /dev/null" && ' + VCS + " commit -m x", "allow", cwd=GITMAIN)
sh("hook-bypass allow: a config write with no commit, merge or push after it, allows",
   VCS + " config core.hooksPath /dev/null", "allow", cwd=GITMAIN)

# (9) False alarms. Each names a bypass flag or key as text, or reads the key, and is allowed: no hook is skipped.
sh("hook-bypass allow: push -n is --dry-run, not a bypass",
   VCS + " push -n origin feature/x", "allow", cwd=GITMAIN)
sh("hook-bypass allow: merge -n is --no-stat, not a bypass",
   VCS + " merge -n feature/x", "allow", cwd=GITMAIN)
sh("hook-bypass allow: log -n 5 counts commits",
   VCS + " log -n 5", "allow", cwd=GITMAIN)
sh("hook-bypass allow: -n as a commit message value",
   VCS + ' commit -m "-n"', "allow", cwd=GITMAIN)
sh("hook-bypass allow: --no-verify as a commit message value",
   VCS + ' commit -m "--no-verify"', "allow", cwd=GITMAIN)
sh("hook-bypass allow: a quoted --no-verify in a commit message",
   VCS + " commit -m 'never use --no-verify'", "allow", cwd=GITMAIN)
sh("hook-bypass allow: a quoted core.hooksPath in a commit message",
   VCS + ' commit -m "refuse core.hooksPath bypass"', "allow", cwd=GITMAIN)
sh("hook-bypass allow: a heredoc commit message that names --no-verify and core.hooksPath",
   VCS + " commit -F - <<'EOF'\nrefuse --no-verify and a core.hooksPath bypass\nEOF", "allow", cwd=GITMAIN)
sh("hook-bypass allow: a multi-line quoted commit message that names --no-verify",
   VCS + ' commit -m "subject\n\nrefuse --no-verify"', "allow", cwd=GITMAIN)
sh("hook-bypass allow: echo of a bypass command is text",
   'echo "git commit --no-verify"', "allow", cwd=GITMAIN)
sh("hook-bypass allow: a trailing shell comment that names --no-verify",
   VCS + " commit -m x # --no-verify is refused", "allow", cwd=GITMAIN)
sh("hook-bypass allow: reading core.hooksPath with git config",
   VCS + " config core.hooksPath", "allow", cwd=GITMAIN)
sh("hook-bypass allow: -c user.name on a commit, no hooks key",
   VCS + " -c user.name=x commit -m y", "allow", cwd=GITMAIN)
sh("hook-bypass allow: -c core.hooksPath on status, which is not commit, merge or push",
   VCS + " -c core.hooksPath=x status", "allow", cwd=GITMAIN)
# The exemption: hooks/mutate_shared.py sets core.hooksPath inside Python, for the throwaway worktree it makes.
# The guard never sees that git call, so the command that runs the file is allowed. The next pin check reads
# the file, so this allow holds only while that code still sets the key.
sh("hook-bypass allow: running hooks/mutate_shared.py, whose own checkout sets core.hooksPath",
   "python3 hooks/mutate_shared.py", "allow", cwd=GITMAIN)

# ============================================================ process arguments (rule process-args)
#
# A process's full arguments can hold a secret, an auth key in a flag, and a session that prints
# them puts the secret in its transcript. The rule refuses a command that prints other processes'
# FULL arguments. Its remedy names the forms that stay: a pid, a name, a parent id, a start time.
# Every case here is named `argv:`, so it takes the family `argv` (see _family) and GUARD_FAMILY=argv
# runs only these. Every case runs in NOGIT.
#
# A refuse case reads `allow` on a guard without the rule, so each one is red there. An allow case
# checks a form the rule must keep passing, so a fix that refuses too much fails it.

# The shell readers that the guard and the sweep spawn. They are read from source, so a reader that
# changes is tested as it now reads.
ARGV_READER_FILES = ("hooks/guard_kill.py", "hooks/git_reads.py", "janitor/sweep.py")
# The readers that print full arguments, by their exact argv. A session that typed one would be
# refused by the rule, so no case says these pass. They run in Python and never reach the hook.
ARGV_FULL_ARGS_READERS = (
    ("ps", "-o", "command=", "-p", "123"),   # janitor/sweep.py, one pid's command line
    ("ps", "-axo", "pid=,ppid=,uid=,command="),   # janitor/sweep.py, the whole table
)


def _argv_readers():
    """{argv: file} for each `ps`, `pgrep` or `lsof` list the readers build. A non-literal element
    reads as a pid, so `str(pid)` is 123. Stops the run when a reader file holds no such list, so the
    readers case never runs on nothing."""
    found = {}
    for rel in ARGV_READER_FILES:
        with open(os.path.join(HERE, "..", rel), encoding="utf-8") as handle:
            tree = ast.parse(handle.read(), filename=rel)
        lists = 0
        for node in ast.walk(tree):
            if not isinstance(node, ast.List) or not node.elts:
                continue
            head = node.elts[0]
            if not (isinstance(head, ast.Constant) and head.value in ("ps", "pgrep", "lsof")):
                continue
            lists += 1
            words = tuple(e.value if isinstance(e, ast.Constant) and isinstance(e.value, str) else "123"
                          for e in node.elts)
            found.setdefault(words, rel)
        if not lists:
            sys.exit("process-args: no ps, pgrep or lsof argv list in %s" % rel)
    return found


def _playwright_remedy_commands():
    """The commands the Playwright refusal tells a session to run: its backticked `pgrep` or `ps` spans.
    Read from the constant's literal, so a changed remedy is the one tested."""
    with open(os.path.join(HERE, "guard_kill.py"), encoding="utf-8") as handle:
        tree = ast.parse(handle.read(), filename="guard_kill.py")
    for node in tree.body:
        if isinstance(node, ast.Assign) and any(
                isinstance(t, ast.Name) and t.id == "PLAYWRIGHT_PATH_REASON" for t in node.targets):
            commands = re.findall(r"`((?:pgrep|ps)\b[^`]*)`", ast.literal_eval(node.value))
            if not commands:
                sys.exit("process-args: PLAYWRIGHT_PATH_REASON names no pgrep or ps command")
            return commands
    sys.exit("process-args: no PLAYWRIGHT_PATH_REASON literal in hooks/guard_kill.py")


ARGV_REFUSED = (
    "ps aux", "ps -ef", "ps -eo pid,args", "ps -o args", "ps -A -o pid,command", "ps auxww",
    "ps -fp 123", "ps -ef | grep tailscale", "ps -eo pid,comm,args",
    "pgrep -a x", "pgrep -fa x", "pgrep -fl x", "pgrep -af x", "pgrep -l -f x",
    "cat /proc/*/cmdline", "cat /proc/123/cmdline", r"tr '\0' ' ' < /proc/$pid/cmdline",
    "cat /proc/[0-9]*/cmdline",
    "/usr/bin/ps aux", "sudo ps aux", "bash -c 'ps -ef'", "x=$(ps aux)", "env FOO=1 ps aux",
    "ls && ps aux", "true; ps -ef", "pgrep -f node | xargs ps -fp",
)
for _cmd in ARGV_REFUSED:
    sh("argv: deny, " + _cmd, _cmd, "deny", "process-args", cwd=NOGIT)

ARGV_ALLOWED = (
    "ps -o pid,comm", "ps -eo pid,comm", "ps -A -o pid=,ppid=", "ps -o ppid= -p 123",
    "ps -o comm= -p 123", "ps -o lstart= -p 123", "ps -p 123 -o pid,comm",
    "pgrep x", "pgrep -f x", "pgrep -l x", "pgrep -x node", "pidof node",
    "cat /proc/123/status", "cat /proc/123/comm", "ls /proc/123/fd",
)
for _cmd in ARGV_ALLOWED:
    sh("argv: allow, " + _cmd, _cmd, "allow", cwd=NOGIT)

for _words, _rel in _argv_readers().items():
    if _words in ARGV_FULL_ARGS_READERS:
        continue
    _cmd = " ".join(_words)
    sh("argv: allow, the reader in %s spawns: %s" % (_rel, _cmd), _cmd, "allow", cwd=NOGIT)

# The Playwright refusal tells a session to run a pgrep. A command the rule refuses would send the
# session into a refusal, so each command it names must pass. The case fails when the rule refuses one of
# them, so a remedy that names a refused form fails here.
for _cmd in _playwright_remedy_commands():
    sh("argv: allow, the Playwright remedy tells a session to run: " + _cmd, _cmd, "allow", cwd=NOGIT)

# The remedy of the refusal names the safe forms and never a refused one, since a remedy that names a
# refused form sends the session into the same refusal.
sh("argv: deny, the remedy names the safe forms and no refused one (ps)", "ps aux", "deny", "process-args",
   cwd=NOGIT, carries=("ps -o pid,comm", "pgrep -l", "pgrep -f x", "pids only"),
   lacks=("ps aux", "ps -ef", "pgrep -a", "pgrep -fl", "pgrep -l -f"))
sh("argv: deny, the remedy names the safe forms and no refused one (pgrep)", "pgrep -fa x", "deny",
   "process-args", cwd=NOGIT, carries=("pgrep -l", "pgrep -f x", "pids only"),
   lacks=("pgrep -fa", "pgrep -af", "pgrep -a", "pgrep -fl", "pgrep -l -f", "ps aux", "ps -ef"))

# A quoted, commented or heredoc form is text: the rule judges what a shell would run, not the words.
# Each refused form after such text still refuses. These are the string cases of building-scanner-respects-strings.
ARGV_TEXT_ALLOWED = (
    ("quoted name of the form", 'echo "ps aux"'),
    ("the form in a commit message", 'git commit -m "refuse ps -ef"'),
    ("a pattern that names the path", "grep -n 'cmdline' file"),
    ("a file name that holds the word", "cat notes-about-cmdline.txt"),
    ("a lone apostrophe inside double quotes", 'echo "Don\'t run ps aux here"'),
    ("a comment opener inside double quotes", 'echo "# ps aux is text"'),
    ("a comment after a command", "echo hi # ps aux"),
    ("a comment line", "# ps aux\nls"),
    ("a quoted heredoc body", "cat > notes.md <<'EOF'\nps aux lists every process\nEOF"),
    ("a commit message from a quoted heredoc",
     "git commit -m \"$(cat <<'EOF'\nps aux lists every process\nEOF\n)\""),
    ("a multi-line double-quoted string", "printf '%s\\n' \"first line\nps aux is named here\""),
)
ARGV_TEXT_REFUSED = (
    ("a comment opener in quotes, then a real command", 'echo "a # b" && ps aux'),
    ("a lone apostrophe in quotes, then a real command", 'echo "Don\'t" && ps aux'),
    ("a quoted hash, then a real command", 'echo "#"; ps -ef'),
    ("a quoted heredoc, then a real command", "cat <<'EOF'\nnotes\nEOF\nps -ef"),
    ("a substitution inside double quotes", 'echo "$(ps -ef)"'),
    ("a substitution in double quotes, piped", 'echo "tailscale: $(ps -ef | grep tailscale)"'),
    ("a substitution in an unquoted heredoc body", "cat <<EOF\n$(ps aux)\nEOF"),
)
for _label, _cmd in ARGV_TEXT_ALLOWED:
    sh("argv: allow, text: " + _label, _cmd, "allow", cwd=NOGIT)
for _label, _cmd in ARGV_TEXT_REFUSED:
    sh("argv: deny, text: " + _label, _cmd, "deny", "process-args", cwd=NOGIT)

# Each refuse case below names a form the rule must read. Each pass control beside it names a form the
# rule must still allow, so a fix that reads too much fails a control.

# BSD `x` lists the processes with no controlling terminal. Under the BSD personality its COMMAND
# column is the full argument list. The operand form (`ps ax`) is a separate refusal with no case here.
# The flag forms are pinned, including `-a -x`, split into two words, which lists the same processes as `-ax`.
ARGV_BSD_X_REFUSED = ("ps -x", "ps -ax", "ps -Ax", "ps -ex", "ps -xw", "ps -a -x")
for _cmd in ARGV_BSD_X_REFUSED:
    sh("argv: deny, " + _cmd, _cmd, "deny", "process-args", cwd=NOGIT)
# An explicit -o format decides alone, even with the BSD x flag.
ARGV_BSD_X_ALLOWED = ("ps -xo pid,comm", "ps -x -o comm=")
for _cmd in ARGV_BSD_X_ALLOWED:
    sh("argv: allow, " + _cmd, _cmd, "allow", cwd=NOGIT)

# A read of a process's cmdline by any command, not only cat or tac. The pid is a number, a glob, a
# variable, or a thread under one (`task/N`). A command that takes the path as an argument, or reads it
# through `xargs -a`, is refused as cat is.
ARGV_CMDLINE_REFUSED = (
    "grep -a tailscale /proc/*/cmdline", "head -c 200 /proc/1/cmdline", "tail -c 200 /proc/1/cmdline",
    "strings /proc/1/cmdline", "od -c /proc/1/cmdline", "sed -n l /proc/1/cmdline",
    "xargs -0 -a /proc/1/cmdline echo", "cat /proc/1/task/1/cmdline", "cat /proc/$pid/task/1/cmdline",
    r"tr '\0' ' ' < /proc/1/task/1/cmdline",
)
for _cmd in ARGV_CMDLINE_REFUSED:
    sh("argv: deny, " + _cmd, _cmd, "deny", "process-args", cwd=NOGIT)
# The shell's own pid and self stay, under every reader. Other proc files stay, and so does a path
# that only names the cmdline inside text.
ARGV_CMDLINE_ALLOWED = (
    "cat /proc/self/cmdline", "cat /proc/$$/cmdline", "head -c 200 /proc/self/cmdline",
    "strings /proc/$$/cmdline", "cat /proc/1/comm", "cat /proc/1/status", "echo /proc/1/cmdline",
    'git commit -m "read /proc/1/cmdline"', "grep -n cmdline file.txt",
)
for _cmd in ARGV_CMDLINE_ALLOWED:
    sh("argv: allow, " + _cmd, _cmd, "allow", cwd=NOGIT)
ARGV_CMDLINE_TEXT_ALLOWED = (
    ("a heredoc body that names the read", "cat > notes.md <<'EOF'\nhead -c 200 /proc/1/cmdline\nEOF"),
    ("a comment that names the read", "ls # head -c 200 /proc/1/cmdline"),
)
for _label, _cmd in ARGV_CMDLINE_TEXT_ALLOWED:
    sh("argv: allow, text: " + _label, _cmd, "allow", cwd=NOGIT)

# pstree prints the full command line with -a or -c, and top with -c. The default tree and the
# default top columns stay.
ARGV_TREE_REFUSED = ("pstree -a", "pstree -ap", "pstree -ca", "top -c -bn1", "top -bc")
for _cmd in ARGV_TREE_REFUSED:
    sh("argv: deny, " + _cmd, _cmd, "deny", "process-args", cwd=NOGIT)
ARGV_TREE_ALLOWED = ("pstree -p", "pstree", "top -bn1", "top -b -n 1 -o %CPU")
for _cmd in ARGV_TREE_ALLOWED:
    sh("argv: allow, " + _cmd, _cmd, "allow", cwd=NOGIT)

# The PowerShell tool reads a process's command line through CIM, WMI or wmic, as the CommandLine
# property. The pid, name and process-table forms stay.
ARGV_PS_REFUSED = (
    "Get-CimInstance Win32_Process | Select CommandLine",
    "(Get-WmiObject Win32_Process).CommandLine",
    "wmic process get commandline",
    "Get-Process | Select Name,CommandLine",
)
for _cmd in ARGV_PS_REFUSED:
    sh("argv: deny, PowerShell, " + _cmd, _cmd, "deny", "process-args", tool="PowerShell", cwd=NOGIT)
ARGV_PS_ALLOWED = (
    "Get-Process", "Get-Process | Select Id,ProcessName", "Get-CimInstance Win32_Process | Select ProcessId,Name",
)
for _cmd in ARGV_PS_ALLOWED:
    sh("argv: allow, PowerShell, " + _cmd, _cmd, "allow", tool="PowerShell", cwd=NOGIT)
# PowerShell text is a string, a comment or a here-string, never a command. Each shape the scanner meets
# gets a control, and a refused command after the text still refuses.
ARGV_PS_TEXT_ALLOWED = (
    ("a quoted Win32_Process CommandLine", 'Write-Output "Win32_Process CommandLine"'),
    ("a comment opener inside double quotes", 'Write-Output "# Get-CimInstance Win32_Process | Select CommandLine"'),
    ("a comment line that names the read", "# (Get-WmiObject Win32_Process).CommandLine\nGet-Process"),
    ("a here-string that names the read",
     "@'\nGet-CimInstance Win32_Process | Select CommandLine\n'@ | Out-File notes.md"),
    ("a lone apostrophe inside double quotes", 'Write-Output "Don\'t read CommandLine"'),
)
ARGV_PS_TEXT_REFUSED = (
    ("a comment opener in quotes, then a real command",
     'Write-Output "a # b"; Get-CimInstance Win32_Process | Select CommandLine'),
    ("a lone apostrophe in quotes, then a real command", 'Write-Output "Don\'t"; wmic process get commandline'),
)
for _label, _cmd in ARGV_PS_TEXT_ALLOWED:
    sh("argv: allow, PowerShell text: " + _label, _cmd, "allow", tool="PowerShell", cwd=NOGIT)
for _label, _cmd in ARGV_PS_TEXT_REFUSED:
    sh("argv: deny, PowerShell text: " + _label, _cmd, "deny", "process-args", tool="PowerShell", cwd=NOGIT)

# The remedy names no refused form of these families. Each case's trigger is a refused form of a family
# above, so the case also pins the remedy text that the refusal prints.
ARGV_NEW_FORMS_NOT_IN_REMEDY = (
    "ps -x", "ps -ax", "ps -xw", "pstree -a", "pstree -ca", "top -c", "top -bc", "cmdline", "xargs -a",
    "CommandLine", "wmic",
)
sh("argv: deny, the remedy names no refused BSD, tree or cmdline form (trigger ps -xw)", "ps -xw", "deny",
   "process-args", cwd=NOGIT, lacks=ARGV_NEW_FORMS_NOT_IN_REMEDY)
sh("argv: deny, the remedy names no refused PowerShell form (trigger CommandLine)",
   "Get-Process | Select Name,CommandLine", "deny", "process-args", tool="PowerShell", cwd=NOGIT,
   lacks=ARGV_NEW_FORMS_NOT_IN_REMEDY)

# A grep-style command takes its pattern as a bare word, or after -e. A cmdline path given as the pattern
# names no file, so each form here passes. The path is a file only when a later operand follows.
ARGV_GREP_PATTERN_ALLOWED = (
    r'grep -rn "/proc/1/cmdline" docs',
    r'grep -e "/proc/1/cmdline" hooks/test_guard.py',
    "echo hi | grep /proc/1/cmdline",
    "egrep -n /proc/1/cmdline notes.md",
    "fgrep /proc/1/cmdline notes.md",
    'rg "/proc/1/cmdline" docs',
    "rg -n -e /proc/1/cmdline docs",
)
for _cmd in ARGV_GREP_PATTERN_ALLOWED:
    sh("argv: allow, " + _cmd, _cmd, "allow", cwd=NOGIT)
# The file operand of a grep-style command is a read, whether the pattern is bare or given with -e. These
# are controls: a fix that exempts the whole command, or reads only the first operand, fails them.
ARGV_GREP_FILE_REFUSED = (
    "grep tailscale /proc/1/cmdline", "grep -a x /proc/*/cmdline", "rg x /proc/1/cmdline",
    "grep -e tailscale /proc/1/cmdline",
)
for _cmd in ARGV_GREP_FILE_REFUSED:
    sh("argv: deny, " + _cmd, _cmd, "deny", "process-args", cwd=NOGIT)
# find runs its -exec command on each path it takes, so the command after -exec reads the cmdline file.
ARGV_FIND_EXEC_REFUSED = (
    r"find /proc/1/cmdline -exec cat {} \;",
    r"find /proc/*/cmdline -exec grep -a tailscale {} +",
)
for _cmd in ARGV_FIND_EXEC_REFUSED:
    sh("argv: deny, " + _cmd, _cmd, "deny", "process-args", cwd=NOGIT)

# =========================================================================== 5. merge into main

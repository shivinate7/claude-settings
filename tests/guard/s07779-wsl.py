# section 7779
FAMILY = "wsl"
#
WSL_RULE = "wsl-allow-list"
SAMPLE_AGENT_ID = "a64a7f84210a8721d"

sh("wsl: a node test file under mods, main session",
   "wsl -e node --test mods/plain-diff/plain-diff.test.mjs", "allow", cwd=NOGIT)
sh("wsl: two node test paths in one call",
   "wsl -e node --test mods/plain-diff/plain-diff.test.mjs mods/session-board/session-board.test.mjs",
   "allow", cwd=NOGIT)
sh("wsl: a node test file at a repo path",
   "wsl -e node --test testing/skip-locally-fail-in-ci.test.mjs", "allow", cwd=NOGIT)
sh("wsl: a pwsh test file at the repo root",
   "wsl -e pwsh -NoProfile -File install.test.ps1", "allow", cwd=NOGIT)
sh("wsl: a python test file under hooks",
   "wsl -e python3 hooks/test_guard.py", "allow", cwd=NOGIT)
sh("wsl: --exec in place of -e",
   "wsl --exec node --test mods/plain-diff/plain-diff.test.mjs", "allow", cwd=NOGIT)
sh("wsl: wrapped by verdict, node",
   "python bin/verdict wsl -e node --test mods/plain-diff/plain-diff.test.mjs", "allow", cwd=NOGIT)
sh("wsl: wrapped by verdict, python",
   "python bin/verdict wsl -e python3 hooks/test_guard.py", "allow", cwd=NOGIT)

# Owner ruling 2026-10-17 11:40 CDT: under WSL a plain `node <file>.test.mjs` runs, with no --test
# flag (CI runs the mod tests this way). Plain node runs only its
# first file, and the rest become argv. So the plain form takes exactly one literal test path. A glob
# or a second file gives a false green. `--test` keeps its glob and multi-file form.
sh("wsl: a plain node test file, no --test flag",
   "wsl -e node mods/x/x.test.mjs", "allow", cwd=NOGIT)
sh("wsl: a glob in a plain node test path is refused",
   "wsl -e node mods/*/*.test.mjs", "deny", rule=WSL_RULE, cwd=NOGIT)
sh("wsl: two test files in a plain node call are refused",
   "wsl -e node mods/a/a.test.mjs mods/b/b.test.mjs", "deny", rule=WSL_RULE, cwd=NOGIT)
sh("wsl: a test file then a script in a plain node call is refused",
   "wsl -e node x.test.mjs other.mjs", "deny", rule=WSL_RULE, cwd=NOGIT)
sh("wsl: a flag before the test file in a plain node call is refused",
   "wsl -e node --inspect x.test.mjs", "deny", rule=WSL_RULE, cwd=NOGIT)
sh("wsl: a glob in a --test node path is allowed",
   "wsl -e node --test mods/*/*.test.mjs", "allow", cwd=NOGIT)
sh("wsl: a plain node script that is not a test",
   "wsl -e node script.mjs", "deny", rule=WSL_RULE, cwd=NOGIT)
sh("wsl: a plain node file whose name only starts like a test",
   "wsl -e node x.test.mjs.evil", "deny", rule=WSL_RULE, cwd=NOGIT)
sh("wsl: plain node with an eval flag",
   'wsl -e node -e "console.log(1)"', "deny", rule=WSL_RULE, cwd=NOGIT)
sh("wsl: a plain node test path that climbs",
   "wsl -e node ../x.test.mjs", "deny", rule=WSL_RULE, cwd=NOGIT)
sh("wsl: a plain node test path that is absolute",
   "wsl -e node /tmp/evil.test.mjs", "deny", rule=WSL_RULE, cwd=NOGIT)

# The same allowed call from each role: "allowed (any role)".
sh("wsl: an allowed test call from a builder agent",
   "wsl -e node --test mods/plain-diff/plain-diff.test.mjs", "allow", cwd=NOGIT,
   agent_id=SAMPLE_AGENT_ID, agent_type="builder")
sh("wsl: an allowed test call from a test-author agent",
   "wsl -e node --test mods/plain-diff/plain-diff.test.mjs", "allow", cwd=NOGIT,
   agent_id=SAMPLE_AGENT_ID, agent_type="test-author")
sh("wsl: an allowed test call from a record-writer agent",
   "wsl -e node --test mods/plain-diff/plain-diff.test.mjs", "allow", cwd=NOGIT,
   agent_id=SAMPLE_AGENT_ID, agent_type="record-writer")
sh("wsl: an allowed test call from an Explore agent",
   "wsl -e node --test mods/plain-diff/plain-diff.test.mjs", "allow", cwd=NOGIT,
   agent_id=SAMPLE_AGENT_ID, agent_type="Explore")
sh("wsl: an allowed test call from a reviewer agent",
   "wsl -e node --test mods/plain-diff/plain-diff.test.mjs", "allow", cwd=NOGIT,
   agent_id=SAMPLE_AGENT_ID, agent_type="reviewer")

# Quoted and commented text runs nothing, and a comment hides nothing that follows it.
sh("wsl: a refused form in single quotes runs nothing",
   "echo 'wsl --shutdown'", "allow", cwd=NOGIT)
sh("wsl: a refused form inside a multi-line double-quoted string runs nothing",
   "echo \"first line\nwsl --shutdown\"", "allow", cwd=NOGIT)
sh("wsl: a comment after an allowed call",
   "wsl -e node --test mods/plain-diff/plain-diff.test.mjs # ; x", "allow", cwd=NOGIT)
sh("wsl: grep for the word, a false alarm",
   "grep -n wsl hooks/guard.py", "allow", cwd=NOGIT)

# The refused forms. Each names WSL_RULE.
sh("wsl: no -e, so the command goes through a shell",
   "wsl node --test mods/plain-diff/plain-diff.test.mjs", "deny", rule=WSL_RULE, cwd=NOGIT)
sh("wsl: bash through -e", "wsl -e bash -c ls", "deny", rule=WSL_RULE, cwd=NOGIT)
sh("wsl: sh through -e with -c", "wsl -e sh -c ls", "deny", rule=WSL_RULE, cwd=NOGIT)
sh("wsl: sh through -e with a script", "wsl -e sh x.sh", "deny", rule=WSL_RULE, cwd=NOGIT)
sh("wsl: root user with -u",
   "wsl -u root -e node --test mods/plain-diff/plain-diff.test.mjs", "deny", rule=WSL_RULE,
   cwd=NOGIT)
sh("wsl: the system distro flag",
   "wsl --system -e node --test mods/plain-diff/plain-diff.test.mjs", "deny", rule=WSL_RULE,
   cwd=NOGIT)
sh("wsl: a login shell type",
   "wsl --shell-type login -e node --test mods/plain-diff/plain-diff.test.mjs", "deny",
   rule=WSL_RULE, cwd=NOGIT)
sh("wsl: another distro with -d",
   "wsl -d Other -e node --test mods/plain-diff/plain-diff.test.mjs", "deny", rule=WSL_RULE,
   cwd=NOGIT)
sh("wsl: a working directory with --cd",
   "wsl --cd /x -e node --test mods/plain-diff/plain-diff.test.mjs", "deny", rule=WSL_RULE,
   cwd=NOGIT)
sh("wsl: the import management verb",
   "wsl --import Other C:/wsl/other C:/x.tar", "deny", rule=WSL_RULE, cwd=NOGIT)
sh("wsl: the unregister management verb", "wsl --unregister Other", "deny", rule=WSL_RULE,
   cwd=NOGIT)
sh("wsl: the mount management verb", "wsl --mount C:/x.vhdx", "deny", rule=WSL_RULE, cwd=NOGIT)
sh("wsl: the shutdown management verb", "wsl --shutdown", "deny", rule=WSL_RULE, cwd=NOGIT)
sh("wsl: the install management verb", "wsl --install", "deny", rule=WSL_RULE, cwd=NOGIT)
sh("wsl: the update management verb", "wsl --update", "deny", rule=WSL_RULE, cwd=NOGIT)
sh("wsl: a node script that is not a test",
   "wsl -e node script.js", "deny", rule=WSL_RULE, cwd=NOGIT)
sh("wsl: a python setup script that is not a test",
   "wsl -e python3 setup.py", "deny", rule=WSL_RULE, cwd=NOGIT)
sh("wsl: a pwsh script that is not a test",
   "wsl -e pwsh -NoProfile -File scripts/x.ps1", "deny", rule=WSL_RULE, cwd=NOGIT)
sh("wsl: a test file with a non-test file after it",
   "wsl -e node --test mods/plain-diff/plain-diff.test.mjs script.js", "deny", rule=WSL_RULE,
   cwd=NOGIT)
sh("wsl: a pipe after the wsl part",
   "wsl -e node --test mods/plain-diff/plain-diff.test.mjs | tail -3", "deny", rule=WSL_RULE,
   cwd=NOGIT)
sh("wsl: a redirect after the wsl part",
   "wsl -e node --test mods/plain-diff/plain-diff.test.mjs > out.txt", "deny", rule=WSL_RULE,
   cwd=NOGIT)
sh("wsl: a semicolon after the wsl part",
   "wsl -e node --test mods/plain-diff/plain-diff.test.mjs; echo hi", "deny", rule=WSL_RULE,
   cwd=NOGIT)
sh("wsl: a newline after the wsl part starts a second command",
   "wsl -e node --test mods/plain-diff/plain-diff.test.mjs\necho hi", "deny", rule=WSL_RULE,
   cwd=NOGIT)
sh("wsl: a WSLENV prefix on the wsl call",
   "WSLENV=PATH/u wsl -e node --test mods/plain-diff/plain-diff.test.mjs", "deny",
   rule=WSL_RULE, cwd=NOGIT)
sh("wsl: a refused form wrapped by verdict",
   "python bin/verdict wsl -e bash -c ls", "deny", rule=WSL_RULE, cwd=NOGIT)
sh("wsl: a lone apostrophe in text does not hide a refused verb",
   "echo don't; wsl --shutdown", "deny", rule=WSL_RULE, cwd=NOGIT)
sh("wsl: a comment opener in a string does not hide a refused verb",
   "echo \"# note\"; wsl --shutdown", "deny", rule=WSL_RULE, cwd=NOGIT)

# Launchers by path, WSLENV set in an earlier statement, test paths that
# leave the repo, and a glob in a test path. A bare `bash -c` is Git bash and keeps its verdict.
sh("wsl: a bash.exe launcher by forward-slash path",
   "C:/Windows/System32/bash.exe -c id", "deny", rule=WSL_RULE, cwd=NOGIT)
sh("wsl: a bash.exe launcher by backslash path",
   r"C:\Windows\System32\bash.exe -c id", "deny", rule=WSL_RULE, cwd=NOGIT)
sh("wsl: the wsl.exe launcher by path, through sh",
   r"C:\Windows\System32\wsl.exe -e sh -c id", "deny", rule=WSL_RULE, cwd=NOGIT)
sh("wsl: a distro launcher run id", "ubuntu.exe run id", "deny", rule=WSL_RULE, cwd=NOGIT)
sh("wsl: a versioned distro launcher run id", "ubuntu2204.exe run id", "deny", rule=WSL_RULE,
   cwd=NOGIT)
sh("wsl: a debian distro launcher run id", "debian.exe run id", "deny", rule=WSL_RULE, cwd=NOGIT)
sh("wsl: a kali distro launcher run id", "kali.exe run id", "deny", rule=WSL_RULE, cwd=NOGIT)
sh("wsl: a bare bash -c is Git bash and keeps its verdict", "bash -c x", "allow", cwd=NOGIT)
sh("wsl: WSLENV exported in an earlier statement",
   "export WSLENV=PATH/p; wsl -e node --test a.test.mjs", "deny", rule=WSL_RULE, cwd=NOGIT)
sh("wsl: WSLENV set in PowerShell in an earlier statement",
   "$env:WSLENV='PATH/p'; wsl -e node --test a.test.mjs", "deny", rule=WSL_RULE, cwd=NOGIT)
sh("wsl: a test path that climbs out of the repo with ..",
   "wsl -e node --test ../../x.test.mjs", "deny", rule=WSL_RULE, cwd=NOGIT)
sh("wsl: a test path that is absolute from the root",
   "wsl -e node --test /tmp/evil.test.mjs", "deny", rule=WSL_RULE, cwd=NOGIT)
sh("wsl: a test path with a drive letter",
   "wsl -e node --test C:/x/y.test.mjs", "deny", rule=WSL_RULE, cwd=NOGIT)
sh("wsl: a glob in a test path is allowed",
   "wsl -e node --test mods/*/x.test.mjs", "allow", cwd=NOGIT)

# WSLENV named as text is a false alarm; only an assignment refuses. A
# dot-led glob segment can expand to `..`, so it refuses too.
sh("wsl: WSLENV in a file name before a wsl call is a false alarm",
   "cat WSLENV.md; wsl -e node --test a.test.mjs", "allow", cwd=NOGIT)
sh("wsl: WSLENV in quoted text before a wsl call is a false alarm",
   "echo \"see WSLENV\"; wsl -e node --test a.test.mjs", "allow", cwd=NOGIT)
sh("wsl: a set WSLENV assignment refuses",
   "set WSLENV=PATH/p; wsl -e node --test a.test.mjs", "deny", rule=WSL_RULE, cwd=NOGIT)
sh("wsl: a test path whose bracket glob expands to ..",
   "wsl -e node --test [.][.]/x.test.mjs", "deny", rule=WSL_RULE, cwd=NOGIT)
sh("wsl: a test path whose dot-led glob expands to ..",
   "wsl -e node --test .*/x.test.mjs", "deny", rule=WSL_RULE, cwd=NOGIT)

# A WSL call hides behind a form the rule does not unwrap, a value flag, a heredoc header, or a comment opener in quotes.
for _name, _command in (
    ("exec", "exec wsl --shutdown"),
    ("builtin exec", "builtin exec wsl --shutdown"),
    ("a leading bang", "! wsl --shutdown"),
    ("a dollar paren", "$(wsl --shutdown)"),
    ("a dollar paren inside echo", "echo $(wsl --shutdown)"),
    ("a glued subshell", "(wsl --shutdown)"),
    ("cmd /c", "cmd /c wsl --shutdown"),
    ("bash -c with the call in quotes", 'bash -c "wsl --shutdown"'),
    ("exec with -a", "exec -a x wsl --shutdown"),
    ("exec with a refused shell form", "exec wsl -e bash -c ls"),
    ("a nice value flag", "nice -n 5 wsl --shutdown"),
    ("a sudo value flag", "sudo -u root wsl --shutdown"),
    ("an env value flag", "env -u X wsl --shutdown"),
    ("an xargs value flag", "xargs -n 1 wsl --shutdown"),
    ("a time format flag", '/usr/bin/time -f "%e" wsl --shutdown'),
    ("a here-string header", "cat <<<word\nwsl --shutdown"),
    ("a quoted header", 'echo "<<EOF"\nwsl --shutdown'),
    ("a commented header", "# note <<EOF\nwsl --shutdown"),
    ("a comment opener in quotes before exec", 'echo "# note"; exec wsl --shutdown'),
    ("a lone apostrophe in text before a value flag", "echo don't; nice -n 5 wsl --shutdown"),
):
    sh("guard-command-position: wsl %s denies" % _name, _command, "deny", rule=WSL_RULE, cwd=NOGIT)
for _name, _command in (
    ("an ampersand call", "& wsl --shutdown"),
    ("iex with double quotes", 'iex "wsl --shutdown"'),
    ("iex with single quotes", "iex 'wsl --shutdown'"),
):
    sh("guard-command-position: wsl PowerShell %s denies" % _name, _command, "deny",
       rule=WSL_RULE, tool="PowerShell", cwd=NOGIT)
for _name, _command in (
    ("env with a WSL prefix", "env X=1 wsl --shutdown"),
    ("command", "command wsl --shutdown"),
    ("nice", "nice wsl --shutdown"),
    ("timeout", "timeout 5 wsl --shutdown"),
    ("sudo", "sudo wsl --shutdown"),
    ("xargs", "xargs wsl --shutdown"),
    ("time", "time wsl --shutdown"),
    ("time -p", "time -p wsl --shutdown"),
    ("doas", "doas wsl --shutdown"),
    ("a spaced subshell", "( wsl --shutdown )"),
    ("a brace group", "{ wsl --shutdown; }"),
    ("an if block", "if true; then wsl --shutdown; fi"),
    ("two env wrappers", "env X=1 env Y=2 wsl --shutdown"),
    ("a lone apostrophe on the line before a call", "echo don't\nwsl --shutdown"),
):
    sh("guard-command-position: wsl pinned, %s denies" % _name, _command, "deny",
       rule=WSL_RULE, cwd=NOGIT)
for _name, _command in (
    ("an env value flag", "env -u X wsl -e node --test mods/plain-diff/plain-diff.test.mjs"),
    ("a nice value flag", "nice -n 5 wsl -e node --test mods/plain-diff/plain-diff.test.mjs"),
    ("a sudo value flag", "sudo -u root wsl -e node --test mods/plain-diff/plain-diff.test.mjs"),
    ("exec", "exec wsl -e node --test mods/plain-diff/plain-diff.test.mjs"),
    ("a glued subshell", "(wsl -e node --test mods/plain-diff/plain-diff.test.mjs)"),
    ("a dollar paren", "echo $(wsl -e node --test mods/plain-diff/plain-diff.test.mjs)"),
    ("cmd /c", "cmd /c wsl -e node --test mods/plain-diff/plain-diff.test.mjs"),
    ("bash -c with the allowed call in quotes",
     'bash -c "wsl -e node --test mods/plain-diff/plain-diff.test.mjs"'),
    ("a heredoc body that names the refused call", "cat <<'EOF'\nwsl --shutdown\nEOF"),
    ("a comment opener in quotes", 'echo "# wsl --shutdown"'),
):
    sh("guard-command-position: wsl pinned, %s allowed" % _name, _command, "allow", cwd=NOGIT)


# ---- guard-command-position.
# A real quote that opens after a letter (`sed -e's/a/b/'`, `cut -d't'`) or closes after one
# (`x'd'`) is read as a contraction, so the call after it is hidden. A quoted `(wsl` is text, and
# must allow. A long value flag (`--unset`, `--user`, `--adjustment`, `--max-args`) and the short
# value flags `-S`, `-P`, `-h` move the verb slot onto the value, as `-u` and `-n` already do.
# `$( )` outside wsl is a named gap, not covered here.
for _name, _command in (
    ("a quote opened after e in a sed flag", "sed -e's/a/b/' f; wsl --shutdown"),
    ("a quote opened after t in a cut flag", "cut -d't' f; wsl --shutdown"),
    ("a quote closed after x", "echo x'd'; wsl --shutdown"),
    ("env with a long unset flag", "env --unset X wsl"),
    ("sudo with a long user flag", "sudo --user root wsl"),
    ("nice with a long adjustment flag", "nice --adjustment 5 wsl"),
    ("xargs with a long max-args flag", "xargs --max-args 1 wsl"),
    ("env -S with the call in one string", "env -S 'wsl --shutdown'"),
    ("env -P with a path before the call", "env -P /bin wsl"),
    ("sudo -h with a host before the call", "sudo -h host wsl"),
):
    sh("guard-command-position: wsl %s denies" % _name, _command, "deny", rule=WSL_RULE, cwd=NOGIT)
for _name, _command in (
    ("a quoted run with a semicolon after a letter", "echo foo'd; X'"),
    ("a quoted glued subshell to grep", "grep -r '(wsl' ."),
):
    sh("guard-command-position: wsl %s allowed" % _name, _command, "allow", cwd=NOGIT)


# A contraction (`a's b'`) is no quote, so the call after a real quote must deny; a bundled value flag (`-Eu`) shifts the verb slot.
for _sep, _sep_name in ((";", "a semicolon"), (" && ", "and-and"), (" | ", "a pipe")):
    for _name, _command, _rule in (
        ("a contraction before wsl", "echo a's b'" + _sep + "wsl --shutdown", WSL_RULE),
    ):
        sh("guard-command-position: regression, %s, %s denies" % (_name, _sep_name), _command,
           "deny", rule=_rule, cwd=NOGIT)
# One pkill row for the contraction shape above: the wsl rows carry the separator depth.
sh("guard-command-position: regression, a contraction before pkill, a semicolon denies",
   "echo a's b'; pkill foo", "deny", rule="machine-wide-kill", cwd=NOGIT)
for _name, _command in (
    ("sudo with bundled -Eu", "sudo -Eu root wsl --shutdown"),
    ("sudo with bundled -iu", "sudo -iu root wsl --shutdown"),
    ("xargs with bundled -rn", "xargs -rn 1 wsl --shutdown"),
    ("env with bundled -iu", "env -iu X wsl --shutdown"),
    ("env with bundled -iS", "env -iS 'wsl --shutdown'"),
):
    sh("guard-command-position: wsl %s denies" % _name, _command, "deny", rule=WSL_RULE, cwd=NOGIT)
sh("guard-command-position: env -S named as echo text allows", "echo env -S 'wsl x'", "allow",
   cwd=NOGIT)
for _name, _command in (
    ("a straight apostrophe before a semicolon", "echo it's; wsl --shutdown"),
    ("a curly apostrophe before a semicolon", "echo it’s; wsl --shutdown"),
    ("a straight apostrophe before a real quote", "echo it's 'x'; wsl --shutdown"),
    ("a curly apostrophe before a real quote", "echo it’s 'x'; wsl --shutdown"),
):
    sh("guard-command-position: contraction pin, %s, wsl denies" % _name, _command, "deny",
       rule=WSL_RULE, cwd=NOGIT)


# ---- guard-command-position.
# is_contraction counted every later `'`, so a later
# apostrophe (`don't`, `"it's"`) paired with the contraction's own `'`, and the contraction read
# hid the refused call after it. The first two groups must deny. The scanner group holds comment
# openers (`#`, `//`, `/*`) inside a quote and a run that spans lines: each must deny too. The
# pins keep a lone apostrophe, and a quoted one, from hiding a later call that must stay allowed.
for _name, _command, _rule in (
    ("a contraction, a quoted apostrophe, then wsl", "echo a's b'; wsl --shutdown; echo \"it's\"",
     WSL_RULE),
    ("a contraction, a lone apostrophe, then wsl", "echo a's b'; wsl --shutdown; echo don't",
     WSL_RULE),
    ("a sed quote, a lone apostrophe, then wsl", "sed -e's;a;b;' f; wsl --shutdown; echo don't",
     WSL_RULE),
    ("a contraction, a double slash in the quote, then wsl", "echo a's // b'; wsl --shutdown",
     WSL_RULE),
):
    sh("guard-command-position: regression, %s, denies" % _name, _command, "deny", rule=_rule,
       cwd=NOGIT)
# One pkill row for the lone-apostrophe shape: the wsl rows above carry the same scanner paths.
sh("guard-command-position: regression, a lone apostrophe, then pkill, denies",
   "echo a's b'; pkill foo; echo don't", "deny", rule="machine-wide-kill", cwd=NOGIT)
sh("guard-command-position: regression, a lone apostrophe, a quoted apostrophe, then ls, allowed",
   "echo don't; echo \"it's\"; ls", "allow", cwd=NOGIT)

# `don't` opens a single quote that closes later, so the line break after it is a real separator and `pkill foo` runs.
sh("guard-command-position: round 2 bypass, a lone apostrophe in a double-quoted run, "
   "then pkill on the next line, denies",
   "echo don't \" don't \npkill foo\n \"", "deny", rule="machine-wide-kill", cwd=NOGIT)

# `env -S` is read after a `$(` too: text `env -S` before the real wrapper must not hide the call after `$(`.
sh("guard-command-position: wsl env -S text before a dollar-paren env -S denies",
   "echo env -S x $(env -S 'wsl --shutdown')", "deny", rule=WSL_RULE, cwd=NOGIT)
sh("guard-command-position: wsl pinned, env -S in a dollar paren denies",
   "echo $(env -S 'wsl --shutdown')", "deny", rule=WSL_RULE, cwd=NOGIT)
sh("guard-command-position: wsl pinned, env -S in a glued subshell denies",
   "(env -S 'wsl --shutdown')", "deny", rule=WSL_RULE, cwd=NOGIT)

# In a nested PowerShell or cmd script `\` is a path separator, so the command after `\;` or `\&&` runs.
sh("wsl: a bash pwsh -c with a backslash path before ; hides wsl --shutdown, denies",
   r'pwsh -c "cd C:\x\; wsl --shutdown"', "deny", rule=WSL_RULE, cwd=NOGIT)
sh("wsl: a bash cd with a backslash before && hides wsl --shutdown, denies",
   r"cd C:\x\&& wsl --shutdown", "deny", rule=WSL_RULE, cwd=NOGIT)
sh("wsl: a bash cmd /c in double quotes, a backslash before && hides wsl --shutdown, denies",
   r'cmd /c "cd C:\x\&& wsl --shutdown"', "deny", rule=WSL_RULE, cwd=NOGIT)
sh("wsl: a comment opener in an echo string does not hide wsl after a backslash before &&",
   r'echo "# x"; cd C:\x\&& wsl --shutdown', "deny", rule=WSL_RULE, cwd=NOGIT)
sh("wsl: a PowerShell cd with a quoted backslash path before ; still denies wsl --shutdown",
   r'cd "C:\x\"; wsl --shutdown', "deny", rule=WSL_RULE, tool="PowerShell", cwd=NOGIT)
sh("wsl: a lone apostrophe, then a backslash path before ; still denies wsl --shutdown",
   r"echo don't; cd C:\x\; wsl --shutdown", "deny", rule=WSL_RULE, cwd=NOGIT)
sh("wsl: a comment opener inside a single-quoted pwsh -c string still denies wsl --shutdown",
   'pwsh -c "cd C:\\x\\; echo \'# x\'; wsl --shutdown"', "deny", rule=WSL_RULE, cwd=NOGIT)
sh("wsl: a multi-line pwsh -c string with a backslash before its newline denies wsl --shutdown",
   "pwsh -c \"cd C:\\x\\\n; wsl --shutdown\"", "deny", rule=WSL_RULE, cwd=NOGIT)
sh("wsl: a bash backslash before ; is text, so echo a\\; wsl --shutdown is one echo, allowed",
   r"echo a\; wsl --shutdown", "allow", cwd=NOGIT)

# The iex and Invoke-Expression arms of nested_script return PowerShell text, which must not be read with bash rules.
PWSH_IEX_SHAPES = (
    ("iex with escaped double quotes", r'iex \"echo C:\x\; %s\"'),
    ("iex with single quotes", r"iex 'echo C:\x\; %s'"),
    ("Invoke-Expression with single quotes", r"Invoke-Expression 'echo C:\x\; %s'"),
    ("iex with the path in single quotes", r"iex 'C:\x\; %s'"),
)
for _name, _inner in PWSH_IEX_SHAPES:
    sh("wsl: a bash pwsh -c with %s hides wsl --shutdown after a backslash path, denies" % _name,
       'pwsh -c "%s"' % (_inner % "wsl --shutdown"), "deny", rule=WSL_RULE, cwd=NOGIT)
sh("wsl: a comment opener in quotes in a nested iex, then a backslash path, denies wsl --shutdown",
   r'''pwsh -c "iex \"echo '# x' C:\x\; wsl --shutdown\""''', "deny", rule=WSL_RULE, cwd=NOGIT)
sh("wsl: a lone apostrophe in a nested iex, then a backslash path, denies wsl --shutdown",
   r'''pwsh -c "iex \"echo don't C:\x\; wsl --shutdown\""''', "deny", rule=WSL_RULE, cwd=NOGIT)
sh("wsl: a line break in a nested iex, after a backslash path, denies wsl --shutdown",
   r'pwsh -c "iex \"echo C:\x' + "\\" + "\n" + r'; wsl --shutdown\""', "deny", rule=WSL_RULE,
   cwd=NOGIT)
# Bash reads each escaped `\;` or `\&` as text, so these allow.
sh("wsl: a bash -c with a backslash before ; keeps echo one command, allowed",
   r"bash -c 'echo C:\x\; wsl --shutdown'", "allow", cwd=NOGIT)
sh("wsl: a sed script with a backslash before & is text, allowed",
   r"sed 's/a/\&/g'", "allow", cwd=NOGIT)
sh("wsl: a sed script with a backslash before & and a trigger word after it, allowed",
   r"sed 's/a/\& wsl --shutdown/g' notes.txt", "allow", cwd=NOGIT)
sh("wsl: a find -exec with a backslash before ; is text, allowed",
   r"find . -name '*.md' -exec grep -l wsl {} \;", "allow", cwd=NOGIT)

# Each case pins one read: quote_advance for the escaped quote, _split_reading for the backslash-newline,
# the cmd /c tail of nested_script.
sh("wsl: a pwsh -c with an escaped quote before ; hides wsl --shutdown, denies",
   r"""pwsh -c 'echo "a\"; wsl --shutdown'""", "deny", rule=WSL_RULE, cwd=NOGIT)
sh("wsl: a pwsh -c with a backslash before a line break hides wsl --shutdown, denies",
   'pwsh -c "cd C:\\x\\' + "\n" + 'wsl --shutdown"', "deny", rule=WSL_RULE, cwd=NOGIT)
sh("wsl: a cmd /c with a backslash before ; hides wsl --shutdown in a PowerShell script, denies",
   r'cmd /c "echo C:\x\; wsl --shutdown"', "deny", rule=WSL_RULE, cwd=NOGIT)
# The PowerShell tool's own text: a doubled quote in a single-quoted pwsh -c string must not end the
# quote early, or the `;` reads as quoted.
sh("wsl: a PowerShell tool doubled single quote then wsl --shutdown, denies",
   "pwsh -c '\"a`''\"; wsl --shutdown'", "deny", rule=WSL_RULE, tool="PowerShell", cwd=NOGIT)

# ---- PowerShell quoting, safety holes F1 to F3.
# F1: PowerShell opens `<#` and `@'` only at a token start, so mid-word they are text. F2: a
# PowerShell call reads an sh -c or bash -c script with PowerShell rules. F3: pwsh -c and iex keep
# a backtick that the outer string already consumed.
sh("wsl: a PowerShell comment opener mid-word, then wsl --shutdown, denies",
   "echo a<# ; wsl --shutdown #>", "deny", rule=WSL_RULE, tool="PowerShell", cwd=NOGIT)
sh("wsl: a Bash pwsh -c with a comment opener mid-word, then wsl --shutdown, denies",
   "pwsh -c 'echo a<# ; wsl --shutdown #>'", "deny", rule=WSL_RULE, cwd=NOGIT)
sh("wsl: a sh -c script in a PowerShell call, a backtick pair then wsl --shutdown, denies",
   "sh -c 'echo `x`; wsl --shutdown'", "deny", rule=WSL_RULE, tool="PowerShell", cwd=NOGIT)
sh("wsl: a PowerShell iex with a double-quoted backtick pair then wsl --shutdown, denies",
   'iex "echo `x`; wsl --shutdown"', "deny", rule=WSL_RULE, tool="PowerShell", cwd=NOGIT)
sh("wsl: a Bash pwsh -c with a double-quoted backtick pair then wsl --shutdown, denies",
   'pwsh -c "echo `x`; wsl --shutdown"', "deny", rule=WSL_RULE, cwd=NOGIT)
# KEEP ALLOWED. A closed comment at a token start hides its text. An unclosed one runs to the end.
sh("wsl: a PowerShell closed comment at a token start hides wsl --shutdown, allowed",
   "echo ok <# wsl --shutdown #>", "allow", tool="PowerShell", cwd=NOGIT)
sh("wsl: a PowerShell unclosed comment at a token start with no call after it, allowed",
   "echo hi <# note", "allow", tool="PowerShell", cwd=NOGIT)
sh("wsl: a Bash pwsh -c with a closed comment at a token start hides wsl --shutdown, allowed",
   "pwsh -c 'echo ok <# wsl --shutdown #>'", "allow", cwd=NOGIT)

# ---- safety hole F4: a backtick hides the next `;` before an env read.
# It sits here, not in the env section below, so it stays above the TEMP_DIR = None line.

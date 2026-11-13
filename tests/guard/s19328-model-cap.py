# section 19328
FAMILY = "model-cap"
#
# Rule 8. A project settings file overrides the owner's user settings, so a write there can lift
# the agent model cap the user settings hold. The decision is `ask`, never `deny`: the same
# write is how an Opus agent gets enabled on purpose.
#
# THE ASK NAMES THE VALUE AND THE FILE. `REASON_MAY_NAME` holds that exemption, keyed by this
# rule's name and no case's say-so, and each ask case pins the fragment the approver must read
# through `carries`. The generic-reason rule the exemption steps around governs a REFUSAL'S REMEDY,
# where naming the target reads as permission to run it. This is an ask whose whole job is to say
# what is being turned on.
#
# BOTH DIRECTIONS ARE PINNED here too: the settings write that touches neither variable keeps the
# silent Decision 7 allow, and the config directory's own settings keep rule 7's deny.

CAP_KEY = "CLAUDE_CODE_SUBAGENT_MODEL"
CAP_FORCE = CAP_KEY + "_FORCE"
OPUS = "claude-opus-5"
MANAGED_SETTINGS = slash(os.path.join(ROOT, "managed", "managed-settings.json"))
PROJ_README = slash(os.path.join(PROJ, "README.md"))


def cap_settings(model=OPUS, force="1", compact=False):
    """The text of a settings file that sets the cap variables."""
    body = {"env": {CAP_KEY: model, CAP_FORCE: force}}
    if compact:
        return json.dumps(body, separators=(",", ":"))
    return json.dumps(body, indent=2)


add("cap: Write of a project local settings file setting an opus model asks", "ask",
    "agent-model-cap", tool="Write", cwd=NOGIT, file_path=PROJ_LOCAL, content=cap_settings(),
    carries=(OPUS, "settings.local.json"))
add("cap: Write of a project settings file setting an opus model asks", "ask",
    "agent-model-cap", tool="Write", cwd=NOGIT, file_path=PROJ_SETTINGS, content=cap_settings(),
    carries=(OPUS, "settings.json"))
add("cap: a relative project settings path setting an opus model asks", "ask",
    "agent-model-cap", tool="Write", cwd=PROJ, file_path=".claude/settings.local.json",
    content=cap_settings(), carries=(OPUS,))
add("cap: Edit turning the force flag off asks", "ask", "agent-model-cap", tool="Edit",
    cwd=NOGIT, file_path=PROJ_SETTINGS,
    old_string='"' + CAP_FORCE + '": "1"', new_string='"' + CAP_FORCE + '": "0"',
    carries=(CAP_FORCE + " = 0",))
add("cap: Edit naming the model variable with no value asks", "ask", "agent-model-cap",
    tool="Edit", cwd=NOGIT, file_path=PROJ_LOCAL,
    old_string='"' + CAP_KEY + '": "sonnet",', new_string="",
    carries=(CAP_KEY + " = sonnet",))
add("cap: MultiEdit reaching an opus model asks", "ask", "agent-model-cap", tool="MultiEdit",
    cwd=NOGIT, file_path=PROJ_LOCAL,
    edits=[{"old_string": '"' + CAP_KEY + '": "sonnet"',
            "new_string": '"' + CAP_KEY + '": "' + OPUS + '"'}],
    carries=(OPUS,))
add("cap: a managed settings file is a settings file", "ask", "agent-model-cap", tool="Write",
    cwd=NOGIT, file_path=MANAGED_SETTINGS, content=cap_settings(), carries=(OPUS,))
# The workflow agent model is a cap variable too: set to opus, it lifts the model of a workflow's agents.
for _key in ("CLAUDE_CODE_WORKFLOW_SUBAGENT_MODEL", "CLAUDE_CODE_WORKFLOW_SUBAGENT_MODEL_FORCE"):
    add("cap: Write of a project settings file setting %s to opus asks" % _key, "ask",
        "agent-model-cap", tool="Write", cwd=NOGIT, file_path=PROJ_LOCAL,
        content=json.dumps({"env": {_key: "opus"}}), carries=(_key + " = opus",))

# THE EDIT LIST IS READ WHOLE, not the first 200 edits: the lift after 200 no-op edits still asks. This
# case pins that boundary, so a count bound cannot come back unseen.
CAP_NOOP_EDITS = [{"old_string": "line %d" % index, "new_string": "row %d" % index}
                  for index in range(200)]
add("cap: 200 no-op edits ahead of the lift still asks", "ask", "agent-model-cap",
    tool="MultiEdit", cwd=NOGIT, file_path=PROJ_SETTINGS,
    edits=CAP_NOOP_EDITS + [{"old_string": '"' + CAP_KEY + '": "sonnet"',
                             "new_string": '"' + CAP_KEY + '": "' + OPUS + '"'}],
    carries=(OPUS,))
add("cap: the lift in the last of 400 edits still asks", "ask", "agent-model-cap",
    tool="MultiEdit", cwd=NOGIT, file_path=PROJ_LOCAL,
    edits=(CAP_NOOP_EDITS * 2) + [{"old_string": '"' + CAP_FORCE + '": "1"',
                                   "new_string": '"' + CAP_FORCE + '": "0"'}],
    carries=(CAP_FORCE + " = 0",))

# A SYMLINK IS A SPELLING OF THE FILE IT POINTS AT. Rule 7 resolves its paths, so rule 8 resolves
# too, else an alias walks past this rule and not past that one. A platform that refuses the link
# gets the honest answer for the path that is then only a name: allow.
CAP_ALIAS = slash(os.path.join(PROJ, "alias.json"))
try:
    os.symlink(os.path.join(PROJ, ".claude", "settings.json"), CAP_ALIAS.replace("/", os.sep))
    CAP_ALIAS_MADE = True
except Exception:
    CAP_ALIAS_MADE = False
add("cap: a symlink to a project settings file resolves and asks [resolve-branch proof]",
    "ask" if CAP_ALIAS_MADE else "allow", "agent-model-cap" if CAP_ALIAS_MADE else None,
    tool="Write", cwd=NOGIT, file_path=CAP_ALIAS, content=cap_settings(),
    carries=(OPUS,) if CAP_ALIAS_MADE else ())

# THE SYMLINK CASE ABOVE PROVES NOTHING ON THIS ACCOUNT: it holds no SeCreateSymbolicLinkPrivilege,
# `os.symlink` raises `OSError: A required privilege is not held by the client`, `CAP_ALIAS_MADE`
# is False, and the case degrades to an ordinary "allow" that the resolve branch's own removal
# cannot touch. MEASURED: `python hooks/mutate_guard.py` reports the resolved-basename mutant
# SURVIVED, 0 red lines, on exactly this machine.
#
# A TRAILING DOT REACHES THE SAME BRANCH WITHOUT A SYMLINK, on Windows only. NTFS drops a
# trailing dot (or space) from a leaf name at open time, so "settings.json." and "settings.json"
# name the one file already on disk: no second directory entry, no privilege, nothing to create.
# Its basename fails the direct SETTINGS_BASENAMES test the same way the symlink's alias name
# does, and only the resolve (`_resolved`, the same call the symlink case exercises) reads the
# real name back. MEASURED on this machine: `os.path.realpath` of the trailing-dot spelling of an
# existing `settings.json` returns the path without the dot.
#
# POSIX has no such quirk: a trailing dot is an ordinary character in a leaf name there, so the
# spelling names a different, nonexistent file and the case is an honest "allow".
#
# BOTH CASES CARRY THE SAME "[resolve-branch proof]" TAG, and the mutations below require that
# tag, not either case's full name. MEASURED: on this account only the trailing-dot case goes
# red for the resolved-basename mutant (the symlink case degrades to allow, so it never turns
# red at all); on a CI runner that can make a real symlink (Linux, and a privileged Windows
# runner), only the symlink case goes red, since a trailing dot on POSIX names an ordinary,
# different, nonexistent file and never reaches the resolve. A required field pinned to either
# case BY ITS FULL NAME reads as WRONG CAUSE on whichever platform the OTHER case is the one
# that actually fires. The shared tag is what a mutant on this exact branch prints on every
# platform, whichever spelling gets there.
CAP_TRAILING_DOT = slash(os.path.join(PROJ, ".claude", "settings.json."))
add("cap: a trailing-dot spelling resolves to the real settings file and asks [resolve-branch proof]",
    "ask" if os.name == "nt" else "allow", "agent-model-cap" if os.name == "nt" else None,
    tool="Write", cwd=NOGIT, file_path=CAP_TRAILING_DOT, content=cap_settings(),
    carries=(OPUS,) if os.name == "nt" else ())

# A JSON ESCAPE IN THE KEY. The text pattern reads no key here, so the JSON walk is what answers.
CAP_ESCAPED_KEY = '\\u0043LAUDE_CODE_SUBAGENT_MODEL'
add("cap: a JSON-escaped key in the content asks", "ask", "agent-model-cap", tool="Write",
    cwd=NOGIT, file_path=PROJ_LOCAL,
    content='{\n  "env": {\n    "' + CAP_ESCAPED_KEY + '": "' + OPUS + '"\n  }\n}\n',
    carries=(CAP_KEY + " = " + OPUS,))
add("cap: a JSON number value is read, not guessed", "ask", "agent-model-cap", tool="Write",
    cwd=NOGIT, file_path=PROJ_SETTINGS,
    content=json.dumps({"env": {CAP_FORCE: 0}}), carries=(CAP_FORCE + " = 0",))

# THE BARE-KEY PASS is what answers when neither the value pattern nor a JSON parse can. Both cases
# below reach the rule through that pass alone.
add("cap: a value the pattern cannot read still asks", "ask", "agent-model-cap", tool="Edit",
    cwd=NOGIT, file_path=PROJ_LOCAL,
    old_string='"' + CAP_KEY + '": "sonnet"', new_string='"' + CAP_KEY + '": "$OPUS_ID"',
    carries=(CAP_KEY + " = (value unread)",))
sh("cap: a shell variable as the model value still asks",
   "cat <<'JSON' > " + PROJ_LOCAL + "\n{\"env\": {\"" + CAP_KEY + "\": \"$OPUS_ID\"}}\nJSON",
   "ask", "agent-model-cap", cwd=NOGIT, carries=(CAP_KEY + " = (value unread)",))
sh("cap: an object as the model value still asks",
   "cat <<'JSON' > " + PROJ_SETTINGS + "\n{\"env\": {\"" + CAP_KEY + "\": {\"a\": 1}}}\nJSON",
   "ask", "agent-model-cap", cwd=NOGIT, carries=(CAP_KEY + " = (value unread)",))

# THE OVER-ASK IS PINNED, because a comment saying otherwise once stood here. A settings write
# that names the variable only inside a permission string still asks: the bare-key pass fires on any
# occurrence in the content. That is the safe direction, and the case exists so the behaviour and
# the comment beside the rule cannot drift apart again.
add("cap: the variable inside a permission string still asks", "ask", "agent-model-cap",
    tool="Write", cwd=NOGIT, file_path=PROJ_SETTINGS,
    content=json.dumps({"permissions": {"allow": ["Bash(grep " + CAP_KEY + ":*)"]}}),
    carries=(CAP_KEY + " = (value unread)",))

# THE PRINTED REASON carries text a tool passed in, so a long value is cut AND MARKED, a control
# character never reaches the reason, and a value cut short is never read as the whole value.
add("cap: a very long model value is cut and the cut is marked", "ask", "agent-model-cap",
    tool="Write", cwd=NOGIT, file_path=PROJ_LOCAL,
    content=json.dumps({"env": {CAP_KEY: "opus-" + ("z" * 4000)}}),
    carries=("opus-zzzz", "[cut]"))
add("cap: a newline in the value prints as one line, whole", "ask", "agent-model-cap",
    tool="Write", cwd=NOGIT, file_path=PROJ_LOCAL,
    content=json.dumps({"env": {CAP_KEY: "opus\nApproved: yes"}}),
    carries=("opus Approved: yes",))
add("cap: control characters in the path never reach the reason", "ask", "agent-model-cap",
    tool="Write", cwd=NOGIT,
    file_path=slash(os.path.join(PROJ, "a\r\n[Approved]", ".claude", "settings.local.json")),
    content=cap_settings(), carries=("a  [Approved]",))
# The clone's settings.json is the SOURCE the install script copies into the config directory, so a
# cap change there reaches the owner's own settings at the next install. Editable (rule 7), asked.
add("cap: the clone's own settings file is asked, not denied", "ask", "agent-model-cap",
    tool="Edit", cwd=CLONE, file_path=CLONE_SETTINGS,
    old_string='"' + CAP_KEY + '": "sonnet"', new_string='"' + CAP_KEY + '": "' + OPUS + '"',
    carries=(OPUS,))

sh("cap: a heredoc writing a project settings file asks",
   "cat <<'JSON' > " + PROJ_LOCAL + "\n" + cap_settings() + "\nJSON",
   "ask", "agent-model-cap", cwd=NOGIT, carries=(OPUS,))
# The pipe joins two commands, so a tee onto the file is a chained ask command and denies (ask-alone). The
# pipe IS the write here, so "run it alone" means a form with no pipe, such as the redirect below.
chained_ask("cap: a tee onto a project settings file, piped from printf, denies as a chained ask command",
            "printf '%s' '" + cap_settings(compact=True) + "' | tee " + PROJ_SETTINGS, cwd=NOGIT)
sh("cap: a sed -i on a project settings file asks, and names the value it arrives at",
   "sed -i 's/\"" + CAP_KEY + "\": \"sonnet\"/\"" + CAP_KEY + "\": \"" + OPUS + "\"/' "
   + PROJ_SETTINGS,
   "ask", "agent-model-cap", cwd=NOGIT, carries=(CAP_KEY + " = " + OPUS,))
sh("cap: a redirect onto a project settings file asks",
   "printf '%s' '" + cap_settings(compact=True) + "' > " + PROJ_LOCAL,
   "ask", "agent-model-cap", cwd=NOGIT, carries=(OPUS,))
sh("cap: an append onto a project settings file asks",
   "echo '\"" + CAP_FORCE + "\": \"0\"' >> " + PROJ_SETTINGS,
   "ask", "agent-model-cap", cwd=NOGIT, carries=(CAP_FORCE + " = 0",))

# ASK-STEP-HIDDEN (debt ask-step-hidden-in-script). A cap write glued to a `$(`, a backtick or a `(` hides
# its path word from the cap check, so each form asks as the plain redirect does.
HIDDEN_CAP_WRITE = "printf '%s' '" + cap_settings(compact=True) + "' > " + PROJ_LOCAL
sh("ask-step-hidden: control, the plain cap redirect asks",
   HIDDEN_CAP_WRITE, "ask", "agent-model-cap", cwd=NOGIT, carries=(OPUS,))
sh("ask-step-hidden: a cap write in a glued command substitution asks",
   "x=$(" + HIDDEN_CAP_WRITE + ")", "ask", "agent-model-cap", cwd=NOGIT, carries=(OPUS,))
sh("ask-step-hidden: a cap write in glued backticks asks",
   "x=`" + HIDDEN_CAP_WRITE + "`", "ask", "agent-model-cap", cwd=NOGIT, carries=(OPUS,))
sh("ask-step-hidden: a cap write in a bare subshell asks",
   "(" + HIDDEN_CAP_WRITE + ")", "ask", "agent-model-cap", cwd=NOGIT, carries=(OPUS,))
sh("ask-step-hidden: a cap write in a subshell with a leading space asks",
   "( " + HIDDEN_CAP_WRITE + ")", "ask", "agent-model-cap", cwd=NOGIT, carries=(OPUS,))

# A WRITE PIPED INTO A SHELL IS A WRITE. The cap text sits in double quotes and the sed runs under `sh`,
# so it is code. The pipe chains it with the echo, so it denies (ask-alone).
chained_ask("cap shell: a sed -i onto a project settings file that sets the cap, piped to sh, denies as a chained ask command",
   'echo "sed -i s/' + CAP_KEY + '=sonnet/' + CAP_KEY + '=' + OPUS + '/ ' + PROJ_SETTINGS + '" | sh',
   cwd=NOGIT, carries=("agent-model-cap",))

# A COMMENT OPENER OR A LONE QUOTE INSIDE A STRING does not hide the real write after it. The scanner
# must still reach the redirect, and the multi-line quoted string is the multi-line shape of the same
# (rule building-scanner-respects-strings).
chained_ask("cap: a comment opener inside double quotes does not hide a redirect that writes the cap, denies as a chained ask command",
   "echo \"# keep this line\" && printf '%s' '" + cap_settings(compact=True) + "' > " + PROJ_LOCAL,
   cwd=NOGIT, carries=("agent-model-cap",))
sh("cap: a lone apostrophe inside double quotes does not hide a redirect that writes the cap",
   "printf \"it's %s\" '" + cap_settings(compact=True) + "' > " + PROJ_LOCAL,
   "ask", "agent-model-cap", cwd=NOGIT, carries=(OPUS,))
sh("cap: a comment opener in a multi-line quoted string does not hide a redirect that writes the cap",
   "printf '%s\n# keep' '" + cap_settings(compact=True) + "' > " + PROJ_LOCAL,
   "ask", "agent-model-cap", cwd=NOGIT, carries=(OPUS,))

# RULE ORDER. The config directory's own settings keep rule 7's deny, which stands ahead of rule 8,
# so the cap content never turns that wall into a prompt.
add("cap: the config settings stay denied, never asked", "deny", "frozen-path", tool="Write",
    cwd=NOGIT, file_path=CFG_SETTINGS, content=cap_settings())
sh("cap: a heredoc onto the config settings stays denied",
   "cat <<'JSON' > " + CFG_SETTINGS + "\n" + cap_settings() + "\nJSON",
   "deny", "frozen-path", cwd=NOGIT)

# THE OTHER DIRECTION. A settings write that touches neither variable, and a file that only TALKS
# about them, both keep their old answer.
add("cap: a project settings write touching neither variable is allowed", "allow", tool="Write",
    cwd=NOGIT, file_path=PROJ_SETTINGS,
    content=json.dumps({"env": {"TZ": "UTC"}, "permissions": {"allow": ["Bash(ls:*)"]}}, indent=2))
add("cap: prose naming the variable in a README is allowed", "allow", tool="Write", cwd=NOGIT,
    file_path=PROJ_README,
    content="Set " + CAP_KEY + " to sonnet, with " + CAP_FORCE + " at 1, to cap every agent.\n")
add("cap: an ordinary source file naming the variable is allowed", "allow", tool="Edit", cwd=NOGIT,
    file_path=slash(os.path.join(PROJ, "src", "env.py")),
    old_string="x = 1", new_string='CAP = os.environ["' + CAP_KEY + '"]')
add("cap: a Read of a settings file is not a write", "allow", tool="Read", cwd=NOGIT,
    file_path=PROJ_LOCAL)
sh("cap: a grep for the variable in a settings file is not a write",
   "grep -n " + CAP_KEY + " " + PROJ_SETTINGS, "allow", cwd=NOGIT)
sh("cap: reading a settings file into another file is not a write to it",
   "cat " + PROJ_SETTINGS + " > /tmp/copy.json", "allow", cwd=NOGIT)

# THE DATA HALF. A settings write named INSIDE text is not a write: a quoted argument, or text piped into
# a pure printer. A quoted heredoc body fed to an interpreter is read only at its shell spots (see the
# shell-spot rule above), so a body with none allows. Text piped into an interpreter is not a heredoc: the
# interpreter may run it, so a pipe into one fails closed. Incident
# 2026-10-14: a reviewer's probe piped a JSON tool-call sample holding a cap write into
# `python hooks/guard.py`, and the owner was asked to approve a call that wrote nothing. Whether that
# friction is acceptable is the owner's call, not the test's. Each case names the write the way a
# probe would: the path, a redirect, the cap key. The comment opener and the lone apostrophe sit inside the strings.
sh("cap data: a grep naming a cat-write onto a settings file with the cap key allows",
   "grep -n \"cat > " + PROJ_LOCAL + " " + CAP_KEY + "\" docs/notes.md", "allow", cwd=NOGIT)
sh("cap data: an echo naming a tee onto a settings file, piped to wc, allows",
   "echo 'tee " + PROJ_SETTINGS + " " + CAP_KEY + "' | wc -l", "allow", cwd=NOGIT)
chained_ask("cap data: an && inside double quotes naming a cat-write, piped to python, denies as a chained ask command "
   "[cap-ask-fix r1: a pipe into an interpreter fails closed]",
   "echo \"ok && cat > " + PROJ_LOCAL + " " + CAP_KEY + "\" | python hooks/guard.py", cwd=NOGIT,
   carries=("agent-model-cap",))
chained_ask("cap data: a comment opener inside double quotes naming a cat-write, piped to python, denies as a "
   "chained ask command [cap-ask-fix r1: a pipe into an interpreter fails closed]",
   "echo \"# cat > " + PROJ_LOCAL + " " + CAP_KEY + "\" | python hooks/guard.py", cwd=NOGIT,
   carries=("agent-model-cap",))
sh("cap data: a lone apostrophe inside double quotes naming a cat-write, piped to jq, allows",
   "echo \"don't cat > " + PROJ_LOCAL + " " + CAP_KEY + "\" | jq .", "allow", cwd=NOGIT)
chained_ask("cap data: a multi-line quoted string naming a cat-write, piped to python, denies as a chained ask "
   "command [cap-ask-fix r1: a pipe into an interpreter fails closed]",
   "printf '%s' 'a note\ncat > " + PROJ_LOCAL + " " + CAP_KEY + "' | python hooks/guard.py", cwd=NOGIT,
   carries=("agent-model-cap",))
sh("cap data: a heredoc body fed to python stdin naming a cat-write allows "
   "[step agent-model-cap-string-false-alarm: a false-alarm fix, interpreter string data that writes no file "
   "is not the act; incident 2026-11-02 01:16 CST]",
   "python hooks/guard.py <<'PAYLOAD'\n{\"tool_input\": {\"command\": \"cat > " + PROJ_LOCAL + " "
   + CAP_KEY + "\"}}\nPAYLOAD", "allow", cwd=NOGIT)
sh("cap data: a python heredoc that subprocess-runs a cat-write with shell=True asks "
   "[regression pin: passes on main]",
   "python3 - <<'PY'\nimport subprocess; subprocess.run('cat > " + PROJ_LOCAL + " " + CAP_KEY
   + "', shell=True)\nPY", "ask", "agent-model-cap", cwd=NOGIT, carries=(CAP_KEY,))
sh("cap data: a python heredoc that only prints a cat-write allows "
   "[step agent-model-cap-string-false-alarm: a false-alarm fix, interpreter string data that writes no file "
   "is not the act; incident 2026-11-02 01:16 CST]",
   "python3 - <<'PY'\nprint('cat > " + PROJ_LOCAL + " " + CAP_KEY + "')\nPY", "allow", cwd=NOGIT)
sh("cap data: a python heredoc that os.system-runs a cat-write asks [regression pin: passes on main]",
   "python3 - <<'PY'\nimport os; os.system('cat > " + PROJ_LOCAL + " " + CAP_KEY + "')\nPY",
   "ask", "agent-model-cap", cwd=NOGIT, carries=(CAP_KEY,))
chained_ask("cap data: a JSON tool-call sample holding the cap write, piped to python, denies as a chained ask command "
   "[cap-ask-fix r1: a pipe into an interpreter fails closed]",
   "printf '%s' '" + json.dumps({"tool_name": "Bash", "tool_input": {"command": "cat > " + PROJ_LOCAL
   + " <<JSON\n" + cap_settings() + "\nJSON"}}) + "' | python hooks/guard.py", cwd=NOGIT,
   carries=("agent-model-cap",))
chained_ask("cap data: a JSON payload naming a sed -i on a settings file with the cap key, piped to python, "
   "denies as a chained ask command [cap-ask-fix r1: a pipe into an interpreter fails closed]",
   "printf '%s' '" + json.dumps({"tool_input": {"command": "sed -i s/x/y/ " + PROJ_SETTINGS + " "
   + CAP_KEY}}) + "' | python hooks/guard.py", cwd=NOGIT, carries=("agent-model-cap",))

# A quoted project settings path with a space asks. Ask-alone chains the tee, cp and Out-File forms
# with a command, so those deny. The lone Set-Content asks. Rule 8 reads the whole command for the cap
# key, so each write names it on its line. Only the value is pinned.
CAP_SPACED = slash(os.path.join(ROOT, "my proj", ".claude", "settings.json"))
chained_ask("cap: a tee onto a quoted project settings path with a space denies as a chained ask command [r1 red]",
   "printf '%s' '" + cap_settings(compact=True) + "' | tee \"" + CAP_SPACED + "\"",
   cwd=NOGIT, carries=("agent-model-cap",))
chained_ask("cap: a cp onto a quoted project settings path with a space denies as a chained ask command [r1 red]",
   "printf '%s' '" + cap_settings(compact=True) + "' > /tmp/cap.json && cp /tmp/cap.json \""
   + CAP_SPACED + "\"",
   cwd=NOGIT, carries=("agent-model-cap",))
sh("cap: a PowerShell Set-Content onto a quoted project settings path with a space asks [r1 red]",
   "Set-Content -Path \"" + CAP_SPACED + "\" -Value '" + cap_settings(compact=True) + "'",
   "ask", "agent-model-cap", tool="PowerShell", cwd=NOGIT, carries=(OPUS,))
chained_ask("cap: a PowerShell Out-File onto a quoted project settings path with a space denies as a chained ask command [r1 red]",
   "'" + cap_settings(compact=True) + "' | Out-File -FilePath \"" + CAP_SPACED + "\"",
   tool="PowerShell", cwd=NOGIT, carries=("agent-model-cap",))

# COVERAGE. On the cap side too: a comment opener, a multi-line quoted
# string or a lone apostrophe must neither hide a redirect that writes the cap, nor turn quoted text that
# names a write into one.
chained_ask("cap: a /* in double quotes does not hide a redirect that writes the cap [r1 cov], denies as a chained ask command",
   "echo \"/* keep\" && printf '%s' '" + cap_settings(compact=True) + "' > " + PROJ_LOCAL,
   cwd=NOGIT, carries=("agent-model-cap",))
chained_ask("cap: a // in single quotes does not hide a redirect that writes the cap [r1 cov], denies as a chained ask command",
   "echo '// keep' ; printf '%s' '" + cap_settings(compact=True) + "' > " + PROJ_LOCAL,
   cwd=NOGIT, carries=("agent-model-cap",))
sh("cap: a /* in a multi-line quoted string does not hide a redirect that writes the cap [r1 cov]",
   "printf '%s\n/* keep' '" + cap_settings(compact=True) + "' > " + PROJ_LOCAL,
   "ask", "agent-model-cap", cwd=NOGIT, carries=(OPUS,))
chained_ask("cap: a lone apostrophe in text does not hide a redirect that writes the cap [r1 cov], denies as a chained ask command",
   "echo don't ; printf '%s' '" + cap_settings(compact=True) + "' > " + PROJ_LOCAL,
   cwd=NOGIT, carries=("agent-model-cap",))
chained_ask("cap data: a /* in double quotes naming a cat-write, piped to python, denies as a chained ask command "
   "[r1 cov, cap-ask-fix r1: a pipe into an interpreter fails closed]",
   'echo "/* cat > ' + PROJ_LOCAL + ' ' + CAP_KEY + '" | python hooks/guard.py', cwd=NOGIT,
   carries=("agent-model-cap",))
sh("cap data: a // in single quotes naming a tee onto a settings file, piped to jq, allows [r1 cov]",
   "echo '// tee " + PROJ_SETTINGS + " " + CAP_KEY + "' | jq .", "allow", cwd=NOGIT)
chained_ask("cap data: a // in a multi-line quoted string naming a cat-write, piped to python, denies as a chained "
   "ask command [r1 cov, cap-ask-fix r1: a pipe into an interpreter fails closed]",
   "printf 'a note\n// cat > " + PROJ_LOCAL + " " + CAP_KEY + "' | python hooks/guard.py", cwd=NOGIT,
   carries=("agent-model-cap",))

# FAILING OPEN, this rule's own shapes. A content field of the wrong type, an edit list of the
# wrong type, and a payload with no tool name at all: each allows the call.
add("cap: a content field that is not a string allows", "allow", tool="Write", cwd=NOGIT,
    file_path=PROJ_LOCAL, content=3)
add("cap: an edit list that is not a list allows", "allow", tool="MultiEdit", cwd=NOGIT,
    file_path=PROJ_LOCAL, edits="not a list")
add("cap: an edit list holding something other than an object allows", "allow", tool="MultiEdit",
    cwd=NOGIT, file_path=PROJ_LOCAL, edits=[7])
add("cap: a payload with no tool name allows", "allow",
    raw=json.dumps({"tool_input": {"file_path": PROJ_LOCAL, "content": cap_settings()}}))


# The hidden-shell shapes that write the cap ASK. Each names the project local settings file and the cap key.
_CAP_WRITE = CAP_KEY + "=" + OPUS + " > " + PROJ_LOCAL
for _n, _c in (
    ("a git -c alias that runs the write", "git -c alias.w='!echo " + _CAP_WRITE + "' w"),
    ("a git submodule foreach that runs the write", "git submodule foreach 'echo " + _CAP_WRITE + "'"),
    ("an rg --pre that runs the write", "rg --pre 'sh -c \"echo " + _CAP_WRITE + "\"' x f"),
    ("python -W, then an os.system echo",
     "python -W ignore -c \"import os; os.system('echo " + _CAP_WRITE + "')\""),
    ("a process substitution that runs the write", "cat <(sh -c \"echo " + _CAP_WRITE + "\")"),
):
    sh("cap shell: r2, " + _n + ", writes the cap to a project settings file, asks [r2 red]", _c, "ask",
       "agent-model-cap", cwd=NOGIT)
sh("cap shell: r2, a PowerShell iex inside Write-Output sets the cap in a project settings file, asks "
   "[r2 red]",
   "Write-Output (iex \"Set-Content -Path " + PROJ_LOCAL + " -Value " + CAP_KEY + "=" + OPUS + "\")",
   "ask", "agent-model-cap", tool="PowerShell", cwd=NOGIT)
sh("cap shell: r2, a # in a quoted git argument does not hide a cap write run by sh -c, asks [r2 red]",
   "git submodule foreach \"echo '# keep' && echo " + _CAP_WRITE + "\"", "ask", "agent-model-cap",
   cwd=NOGIT)

# The cap key named inside a message flag or a pure printer is data.
# Each names the cap key and a write, and allows, as the incident shapes did.
sh("cap data: r2, a git commit message naming the cap key and a cat-write, allows [r2 pin]",
   VCS + " commit -m \"note: " + CAP_KEY + ", cat > " + PROJ_LOCAL + " is refused\"", "allow", cwd=NOGIT)
sh("cap data: r2, a gh pr create body naming the cap key and a cat-write, allows [r2 pin]",
   "gh pr create --draft --title \"cap note\" --body \"" + CAP_KEY + ", cat > " + PROJ_LOCAL + " is refused\"",
   "allow", cwd=NOGIT)
sh("cap data: r2, an add then a commit naming the cap key and a cat-write, allows [r2 pin]",
   VCS + " add x && " + VCS + " commit -m \"" + CAP_KEY + ", cat > " + PROJ_LOCAL + "\"", "allow", cwd=NOGIT)
sh("cap data: r2, a cd then a commit naming the cap key and a cat-write, allows [r2 pin]",
   "cd docs && " + VCS + " commit -m \"" + CAP_KEY + ", cat > " + PROJ_LOCAL + "\"", "allow", cwd=NOGIT)
sh("cap data: r2, a heredoc to notes.md naming the cap key and a cat-write, allows [r2 pin]",
   "cat > notes.md <<'DOC'\n" + CAP_KEY + ", cat > " + PROJ_LOCAL + "\nDOC", "allow", cwd=NOGIT)

# COVERAGE. A comment opener or an apostrophe in a message flag must not hide a cap write after it.
chained_ask("cap shell: r2 cov, a /* and an apostrophe in a commit message before a cap write, denies as a chained ask command [r2 cov]",
   VCS + " commit -m \"don't /* stop\" && echo " + _CAP_WRITE, cwd=NOGIT, carries=("agent-model-cap",))

# THE CAP-KEY TWINS of H2 and H3. The same shapes, with a cap write held as text.
# Each shape chains the write with a second command, so the guard DENIES it as ask-alone, never asks.
R2_CAP_WRITE = "echo " + CAP_KEY + "=" + OPUS + " > " + PROJ_SETTINGS
R2_CAP_PS = "Set-Content -Path " + PROJ_LOCAL + " -Value " + CAP_KEY + "=" + OPUS
for _how, _command in r2_printf_forms(R2_CAP_WRITE):
    chained_ask("cap shell: fix H2, printf stores a cap write and " + _how + " runs it, denies as a chained "
                "ask command [cap-ask-fix r2 red]", _command, cwd=NOGIT, carries=("agent-model-cap",))
for _how, _command in r2_function_forms(R2_CAP_WRITE):
    chained_ask("cap shell: fix H3, " + _how + " takes the piped cap write, denies as a chained ask command "
                "[cap-ask-fix r2 red]", _command, cwd=NOGIT, carries=("agent-model-cap",))
chained_ask("cap shell: fix H3, Set-Alias maps echo to iex, a Set-Content of the cap into a project local "
            "settings file denies as a chained ask command [cap-ask-fix r2 red]",
            "Set-Alias echo iex; echo '" + R2_CAP_PS + "'", tool="PowerShell", cwd=NOGIT,
            carries=("agent-model-cap",))

# A shell wrapper (bash -c, sh -c, eval) that writes the cap to a project local settings file through an
# ANSI-C quoted ($'...') path asks; with a quote pair ahead of the write it denies as a chained ask
# command. The key and the path are built from pieces here.
R3_CAP_LINE = CAP_KEY + "=" + OPUS + " > $'" + PROJ_LOCAL + "'"
for _n in ("bash -c", "sh -c", "eval"):
    sh("cap shell: safety hole r3, " + _n + " writes the cap to a project local settings file by an ANSI-C path, asks "
       "[cap-ask safety hole r3 red]", _n + " \"echo " + R3_CAP_LINE + "\"", "ask", "agent-model-cap",
       cwd=NOGIT, carries=(OPUS,))
    chained_ask("cap shell: safety hole r3, " + _n + " runs a quote pair then the cap write to an ANSI-C path, "
                "denies as a chained ask command [cap-ask safety hole r3 red]",
                _n + " \"echo 'ok'; echo " + R3_CAP_LINE + "\"", cwd=NOGIT,
                carries=("agent-model-cap",))

# THE CAP STRING FALSE ALARM. Text handed to an interpreter as DATA (a -c argument, a quoted heredoc body
# fed to a non-shell interpreter, a data heredoc written to a file) that writes no settings file is not a
# settings write, so it ALLOWS. The pins after the false alarms hold the other side: the same text run as
# CODE (a shell body, os.system, a redirect outside the string) still asks, or denies when it chains with a
# second command. On main, 1a and 1b ask and 1c denies under ask-alone, so all three are red there. 1c and 1d
# are INFERRED reproductions: the exact incident commands were not kept, so each keeps the shape the incident named.
CAP_STRING_CMD = "echo {\"" + CAP_KEY + "\": \"opus\"} > .claude/settings.json"
CAP_STRING_PAYLOAD = json.dumps({"tool_name": "Bash", "tool_input": {"command": CAP_STRING_CMD}})
CAP_STRING_WRITE = CAP_KEY + "=" + OPUS
CAP_STRING_COMPACT = cap_settings(compact=True)

# 1a. A python -c whose script builds a Bash payload naming the cap write, then runs the guard on it.
sh("cap data: 1a, a python -c building a Bash payload that names a cap write as text allows [cap-string-false-alarm]",
   "python3 -c 'import json,subprocess; p=" + CAP_STRING_PAYLOAD
   + "; subprocess.run([\"python3\",\"hooks/guard.py\"],input=json.dumps(p),text=True)'",
   "allow", cwd=PROJ)

# 1b. A quoted heredoc fed to python3 hooks/guard.py, whose body is a Bash payload naming the cap write.
CAP_STRING_BODY = json.dumps({"tool_name": "Bash", "tool_input": {"command":
                              "echo '{\"env\":{\"" + CAP_KEY + "\":\"opus\"}}' > .claude/settings.json"}})
sh("cap data: 1b, a quoted heredoc fed to python3 hooks/guard.py, whose body names a cap write, allows [cap-string-false-alarm]",
   "python3 hooks/guard.py <<'EOF'\n" + CAP_STRING_BODY + "\nEOF", "allow", cwd=PROJ)

# 1c. INFERRED REPRODUCTION of the cap-string-false-alarm incident. The
# exact body was lost. The shape kept: a data heredoc written to probe.py, a python body holding command
# strings (one a guard call with its own heredoc, one the cap write as text), then `python3 probe.py`.
_CAP_PROBE_PY = ("CMDS = [\n    " + json.dumps("python3 hooks/guard.py <<'EOF2'\n" + CAP_STRING_BODY + "\nEOF2")
                 + ",\n    " + json.dumps("echo '{\"env\":{\"" + CAP_KEY + "\":\"opus\"}}' > .claude/settings.json")
                 + ",\n]\n")
sh("cap data: 1c, inferred reproduction of the 2026-11-03 incident, a data heredoc to probe.py holding a cap write as text, allows [cap-string-false-alarm]",
   "cat > probe.py <<'EOF'\n" + _CAP_PROBE_PY + "EOF\npython3 probe.py", "allow", cwd=PROJ)

# 1d. INFERRED REPRODUCTION of the trial run gd incident: a reviewer's python3 -c
# feeding JSON test payloads to hooks/guard.py, one of them a settings write raising the model to Opus. The
# exact command was not kept. THIS FORM ALLOWS ON MAIN, so it is a pin, not a red case: a Write-tool payload
# carrying the cap as text is data for the guard, and the -c script writes nothing itself. The incident's
# ask therefore came from another form, most likely a payload whose text holds a shell redirect (1a's shape).
_CAP_TRIAL_PAYLOADS = [{"tool_name": "Bash", "tool_input": {"command": "ls"}},
                       {"tool_name": "Write", "tool_input": {"file_path": PROJ_LOCAL, "content": cap_settings()}}]
sh("cap data: 1d pin, a python3 -c feeding a Write-tool payload with the cap as text to the guard allows [cap-string-false-alarm pin: allows on main]",
   "python3 -c 'import json,subprocess; P=" + json.dumps(_CAP_TRIAL_PAYLOADS)
   + "; [subprocess.run([\"python3\",\"hooks/guard.py\"],input=json.dumps(p),text=True) for p in P]'",
   "allow", cwd=NOGIT)

# THE PINS. Each is the same settings write run as CODE, so it still asks, or denies when it chains with a
# second command. 1a and the os.system pin hold the same string: the pin is where the interpreter runs it.
# A HEREDOC BODY IS A SECOND COMMAND to the guard, so the two shell heredoc pins DENY under ask-alone on
# main, not ask. They are pinned at the verdict main gives (deny, ask-alone), so the guard is not changed.
chained_ask("cap pin: a bash heredoc whose body writes the cap into .claude/settings.json denies as a chained ask command [cap-string-false-alarm pin]",
   "bash <<'SH'\necho '" + CAP_STRING_COMPACT + "' > .claude/settings.json\nSH",
   cwd=PROJ, carries=("agent-model-cap",))
chained_ask("cap pin: a sh heredoc whose body writes the cap into .claude/settings.json denies as a chained ask command [cap-string-false-alarm pin]",
   "sh <<'SH'\nprintf '%s' '" + CAP_STRING_COMPACT + "' > .claude/settings.json\nSH",
   cwd=PROJ, carries=("agent-model-cap",))
sh("cap pin: sh -c writing the cap into .claude/settings.json asks [cap-string-false-alarm pin]",
   "sh -c 'echo " + CAP_STRING_WRITE + " > .claude/settings.json'",
   "ask", "agent-model-cap", cwd=PROJ, carries=(CAP_KEY,))
sh("cap pin: a python -c calling os.system on the cap write to .claude/settings.json asks [cap-string-false-alarm pin]",
   "python3 -c 'import os; os.system(\"echo " + CAP_STRING_WRITE + " > .claude/settings.json\")'",
   "ask", "agent-model-cap", cwd=PROJ, carries=(CAP_KEY,))
sh("cap pin: a python heredoc body calling os.system on the cap write to .claude/settings.json asks [cap-string-false-alarm pin]",
   "python3 - <<'PY'\nimport os\nos.system(\"echo " + CAP_STRING_WRITE + " > .claude/settings.json\")\nPY",
   "ask", "agent-model-cap", cwd=PROJ, carries=(CAP_KEY,))
sh("cap pin: python3 -c printing the cap, redirected into .claude/settings.json outside the string, asks [cap-string-false-alarm pin]",
   "python3 -c 'print(\"" + CAP_STRING_WRITE + "\")' > .claude/settings.json",
   "ask", "agent-model-cap", cwd=PROJ, carries=(CAP_KEY,))
sh("cap pin: a cat redirect into .claude/settings.json with the cap in its heredoc body asks [cap-string-false-alarm pin]",
   "cat > .claude/settings.json <<'EOF'\n" + cap_settings() + "\nEOF",
   "ask", "agent-model-cap", cwd=PROJ, carries=(OPUS,))
chained_ask("cap pin: a quoted body written to x.sh, then run by sh x.sh, writing the cap, denies as a chained ask command [cap-string-false-alarm pin]",
   "cat > x.sh <<'SH'\nprintf '%s' '" + CAP_STRING_COMPACT + "' > .claude/settings.json\nSH\nsh x.sh",
   cwd=PROJ, carries=("agent-model-cap",))

# THE CAP THROUGH A SHELL VARIABLE. The settings path sits in `$F`, set by an assignment chained ahead of the
# python -c. Main denies it as a chained ask command (ask-alone), so a cap write does not pass when its path is
# held in a variable.
chained_ask("cap var: a cap write to a settings path held in a shell variable, through os.system in python -c, denies as a chained ask command",
   "F=" + PROJ_SETTINGS + "; python3 -c \"import os; os.system('echo " + CAP_KEY + "=opus >> $F')\"",
   cwd=NOGIT, carries=("agent-model-cap",))

# =========================================================================== 6c. ask alone

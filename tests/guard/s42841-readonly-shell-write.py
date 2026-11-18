# section 42841
FAMILY = "readonly-shell-write"
# A read-only agent's shell write. An agent whose agent_type is in READ_ONLY (hooks/agent_brief.py, the one home of the
# read-only roles, read here by import and never typed) is refused a write in its shell call: a redirect (>, >>, 2>file,
# &>) to a target that is not a null device and not under the calling session's own scratchpad; tee to a file other than
# a null device; touch; mktemp that is not -u. The null device is /dev/null on Bash, and NUL or $null on PowerShell.
# On Bash NUL is a file name, so a redirect to it writes. A > inside [[ ]], (( )) or $(( )) is a comparison, and
# /dev/stdout, /dev/stderr and /dev/tty are streams, so none of those writes a file. The same forms inside an ssh
# remote command are refused too, and no scratchpad exemption applies there, since that path sits on the remote box.
# Why: a read-only audit agent could write files over ssh or in the shell by mistake.
# Decision guard-guards-mistakes-only: the guard stops a write Claude could make by mistake. A call with no agent_id
# is never judged, and a writing role keeps its verdict.

RO_RULE = "readonly-shell-write"
RO_AGENT = "a3e9c0d17b52f4a68"          # an agent's id on the payload, in the shape AGENT_ID accepts (see s07779)
RO_TEMP = os.path.join(ROOT, "tmp")     # the temp folder these cases read (TEMP_DIR), so the scratchpads sit under it
RO_SCRATCH = os.path.join(RO_TEMP, FAKE_SESSION, "scratchpad")         # this session's own scratchpad
RO_OTHER_SCRATCH = os.path.join(RO_TEMP, OTHER_SESSION, "scratchpad")  # another session's scratchpad
# The same two folders as a shell command names them. os.path.join puts backslashes in a Windows path, and the
# tokenizer and bash read a backslash as an escape, so a command carries the forward-slash form (slash, s00442).
# The cwd stays native.
RO_SCRATCH_CMD = slash(RO_SCRATCH)
RO_OTHER_SCRATCH_CMD = slash(RO_OTHER_SCRATCH)
RO_PROBE = "/tmp/ro-probe.txt"          # a write target that is neither a scratchpad nor a null device
RO_WRITE = "echo x > " + RO_PROBE
TEMP_DIR = RO_TEMP


def load_read_only_roles():
    """(sorted READ_ONLY names from hooks/agent_brief.py, None), or ([], the problem) when the home does not load.
    The hook exits 0 at import when its own import fails (fail open), so SystemExit is read as a broken home too."""
    import importlib.util
    try:
        spec = importlib.util.spec_from_file_location("agent_brief_readonly_home", os.path.join(HERE, "agent_brief.py"))
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return sorted(module.READ_ONLY), None
    except (Exception, SystemExit) as exc:
        return [], "agent_brief's READ_ONLY set does not load: %s" % exc


RO_ROLES, RO_ROLES_PROBLEM = load_read_only_roles()


def ro_roles_check():
    """The read-only home loads and names roles. A set that loads empty would drop every role case below without a red."""
    if RO_ROLES_PROBLEM:
        return False, RO_ROLES_PROBLEM
    if not RO_ROLES:
        return False, "agent_brief's READ_ONLY set is empty, so no read-only role is judged"
    return True, "agent_brief's READ_ONLY names %d roles: %s" % (len(RO_ROLES), ", ".join(RO_ROLES))


def ro_refuse(name, command, agent_type="reviewer", tool="Bash", cwd=NOGIT, session=None, agent_id=RO_AGENT):
    """One case: the call is refused under this rule, and the reason names the rule."""
    sh(name, command, "deny", RO_RULE, tool=tool, cwd=cwd, session=session, agent_id=agent_id, agent_type=agent_type)


def ro_allow(name, command, agent_type="reviewer", tool="Bash", cwd=NOGIT, session=None, agent_id=RO_AGENT):
    """One case: the call is allowed, and prints nothing."""
    sh(name, command, "allow", tool=tool, cwd=cwd, session=session, agent_id=agent_id, agent_type=agent_type,
       silent=True)


# ---- A. The shell forms a read-only agent may not write with: a redirect, tee, touch, mktemp.
ro_refuse("readonly-shell-write: a > redirect to a file outside every scratchpad is refused", "echo x > " + RO_PROBE)
ro_refuse("readonly-shell-write: a >> append to a file outside every scratchpad is refused", "echo x >> " + RO_PROBE)
ro_refuse("readonly-shell-write: a 2> stderr redirect to a file is refused", "ls 2> " + RO_PROBE)
ro_refuse("readonly-shell-write: an &> redirect of both streams to a file is refused", "ls &> " + RO_PROBE)
ro_refuse("readonly-shell-write: tee to a file is refused", "ls | tee " + RO_PROBE)
ro_refuse("readonly-shell-write: tee -a to a file is refused", "ls | tee -a " + RO_PROBE)
ro_refuse("readonly-shell-write: touch of a file is refused", "touch " + RO_PROBE)
ro_refuse("readonly-shell-write: mktemp with no template is refused", "mktemp")
ro_refuse("readonly-shell-write: mktemp of a template is refused", "mktemp /tmp/ro-probe.XXXXXX")
ro_refuse("readonly-shell-write: mktemp -d of a template is refused", "mktemp -d /tmp/ro-probe.XXXXXX")
ro_refuse("readonly-shell-write: a relative > redirect from a repository cwd is refused", "echo x > out.txt", cwd=NOGIT)
ro_refuse("readonly-shell-write: a PowerShell > redirect to a file is refused", "Get-ChildItem > " + RO_PROBE,
          tool="PowerShell")

# NUL is a file name on Bash: bash has no NUL device, so the redirect creates a file named NUL (or nul).
ro_refuse("readonly-shell-write: a Bash 2>NUL redirect makes a file named NUL, so it is refused", "ls 2>NUL")
ro_refuse("readonly-shell-write: a Bash > nul redirect makes a file named nul, so it is refused", "ls > nul")
ro_refuse("readonly-shell-write: a Bash >NUL redirect with no space makes a file named NUL, so it is refused",
          "ls >NUL")

# A block device is a disk, not a null device. A real redirect after a comparison still writes.
ro_refuse("readonly-shell-write: a redirect to a block device, /dev/sda, is refused", "echo x > /dev/sda")
ro_refuse("readonly-shell-write: a redirect after a [[ ]] test is refused", "[[ a == b ]] && echo y > out.txt")
ro_refuse("readonly-shell-write: a redirect after $(( )) arithmetic is refused", "echo $((1+1)) > out.txt")
# A [[ or (( inside quotes is text, and the redirect after the quote still writes.
ro_refuse("readonly-shell-write: a [[ inside double quotes does not hide a redirect after it", 'echo "[[" > out.txt')
ro_refuse("readonly-shell-write: a (( inside single quotes does not hide a redirect after it", "echo '((' > out.txt")

# A write chained after a read is still a write: the deny holds for every segment.
ro_refuse("readonly-shell-write: ls && touch x is refused, the touch is chained", "ls && touch x")
ro_refuse("readonly-shell-write: a read chained with a redirect is refused", "cat f && echo y > " + RO_PROBE)

# String-aware: a comment opener or a lone quote inside text does not hide a live redirect.
ro_refuse("readonly-shell-write: a comment opener inside double quotes does not hide a redirect after the quote",
          'echo "# note" > ' + RO_PROBE)
ro_refuse("readonly-shell-write: a multi-line quoted string with a comment opener does not hide a redirect after it",
          'echo "one\n# two" > ' + RO_PROBE)
ro_refuse("readonly-shell-write: a lone apostrophe inside quotes does not hide a redirect after it",
          'echo "don\'t" > ' + RO_PROBE)
ro_refuse("readonly-shell-write: a quoted hash on one line does not hide a redirect on the next line",
          'grep "#" f\nls > ' + RO_PROBE)
ro_refuse("readonly-shell-write: a heredoc header's redirect is refused, and the body is text",
          "cat <<'EOF' > " + RO_PROBE + "\nbody line\nEOF")
ro_refuse("readonly-shell-write: a lone apostrophe in a heredoc body does not hide the header's redirect",
          "cat > " + RO_PROBE + " <<'EOF'\nDon't\nEOF")

# Another session's scratchpad is not this session's own: the exemption names the calling session only.
ro_refuse("readonly-shell-write: a redirect into another session's scratchpad is refused",
          "echo x > " + RO_OTHER_SCRATCH_CMD + "/ro-other.txt", session=FAKE_SESSION)

# ---- A2. A subshell, a command substitution, or arithmetic that runs commands: a write inside is a write of the call.
# Why: a group ( ) runs its text as commands, so a redirect or touch in it writes a file even when the outer call reads.
ro_refuse("readonly-shell-write: a touch after a cd inside a subshell is refused", "(cd /tmp && touch f)")
ro_refuse("readonly-shell-write: a redirect inside a subshell is refused", "(echo hi > out.txt)")
ro_refuse("readonly-shell-write: a redirect after a cd inside a subshell is refused", "(cd /tmp; echo hi > out.txt)")
ro_refuse("readonly-shell-write: a touch inside a bare subshell is refused", "(touch f)")
ro_refuse("readonly-shell-write: a touch in a subshell chained after a read subshell is refused", "(ls) && (touch f)")
ro_refuse("readonly-shell-write: a redirect inside a subshell with spaces in the parentheses is refused",
          "( echo hi > out.txt )")
# Why: a backquote or $( ) runs its text as a command, so a write in it is a write of the call.
ro_refuse("readonly-shell-write: a touch in a backquote command substitution is refused", "echo `(touch f)`")
# Why: a $(( )) that is not arithmetic runs its text as a command, so the writes in it count.
ro_refuse("readonly-shell-write: a subshell inside $(( )) within double quotes, with a touch, is refused",
          'echo "$((touch f); (touch g))"')
# Why: a [[ that does not start a command is an ordinary word, so a > after it, with no ]], is a redirect.
ro_refuse("readonly-shell-write: a > after an unclosed [[ argument is a redirect, so it is refused",
          "echo [[ x > out.txt")
# Why: a # or a lone quote inside a string does not end the string, so a redirect after it in a subshell still writes.
ro_refuse("readonly-shell-write: a # in a string inside a subshell does not hide a redirect after it",
          '(echo "# x" > out.txt)')
ro_refuse("readonly-shell-write: a # on a second line of a string inside a subshell does not hide a redirect",
          '(echo "one\n# two" > out.txt)')
ro_refuse("readonly-shell-write: a lone apostrophe in a string inside a subshell does not hide a redirect",
          '(echo "don\'t" > out.txt)')
# Why: a subshell of reads writes nothing, so it stays allowed.
ro_allow("readonly-shell-write: a read-only subshell is allowed", "(ls)")
ro_allow("readonly-shell-write: a read-only subshell after a cd is allowed", "(cd /tmp && ls)")
# Why: text that only looks like a subshell, inside quotes, is an argument, so it writes nothing.
ro_allow("readonly-shell-write: a subshell's text in double quotes is an argument, allowed", 'echo "(touch f)"')
ro_allow("readonly-shell-write: a subshell's text inside single quotes to grep is an argument, allowed",
         "grep '(echo hi > out.txt)' f")

# ---- B. Over ssh: the same forms, inside the remote command. No scratchpad exemption applies there.
ro_refuse("readonly-shell-write: an ssh remote command's > redirect to a file is refused", "ssh host 'cat x > /tmp/y'")
ro_refuse("readonly-shell-write: an ssh remote command's >> append to a file is refused", "ssh host 'cat x >> /tmp/y'")
ro_refuse("readonly-shell-write: an ssh remote command's touch is refused", 'ssh host "touch /tmp/z"')
ro_refuse("readonly-shell-write: an ssh remote command's mktemp is refused", "ssh host mktemp")
ro_refuse("readonly-shell-write: an ssh remote command's tee to a file is refused", "ssh host 'ls | tee /tmp/y'")
ro_refuse("readonly-shell-write: an ssh touch of this session's scratchpad path is refused, the path is remote",
          'ssh host "touch %s/x"' % RO_SCRATCH_CMD, session=FAKE_SESSION)

# ---- C. Every read-only role in agent_brief.READ_ONLY is judged, whatever its case or plugin prefix.
for _role in (RO_ROLES or ["reviewer"]):   # a broken home still gets one case, which goes red
    ro_refuse("readonly-shell-write: read-only role %s, a redirect to a file, is refused" % _role, RO_WRITE,
              agent_type=_role)
ro_refuse("readonly-shell-write: a plugin-prefixed read-only role (x:reviewer) is refused", RO_WRITE,
          agent_type="x:reviewer")
ro_refuse("readonly-shell-write: a read-only role in upper case (REVIEWER) is refused", RO_WRITE, agent_type="REVIEWER")
ro_refuse("readonly-shell-write: a read-only role in lower case (explore) is refused", RO_WRITE, agent_type="explore")

# ---- D. Allowed for a read-only agent: reads, the null devices, and text that only looks like a write.
ro_allow("readonly-shell-write: a read-only agent's ls is allowed", "ls")
ro_allow("readonly-shell-write: a read-only agent's cat of a file is allowed", "cat f")
ro_allow("readonly-shell-write: a read-only agent's grep of a file is allowed", "grep -n needle notes.txt")
ro_allow("readonly-shell-write: a read-only agent's ssh read of a remote file is allowed",
         "ssh host 'cat /etc/os-release'")
ro_allow("readonly-shell-write: 2>&1 merges a stream and writes no file", "ls 2>&1")
ro_allow("readonly-shell-write: >/dev/null discards to the null device", "ls >/dev/null")
ro_allow("readonly-shell-write: 2>/dev/null discards to the null device", "ls 2>/dev/null")
ro_allow("readonly-shell-write: both streams to the null device are allowed", "ls > /dev/null 2>&1")
ro_allow("readonly-shell-write: tee to /dev/null writes no file", "ls | tee /dev/null")
ro_allow("readonly-shell-write: mktemp -u prints a name and creates nothing", "mktemp -u /tmp/ro-probe.XXXXXX")
ro_allow("readonly-shell-write: PowerShell 2>$null is the null device, allowed", "Get-ChildItem 2>$null",
         tool="PowerShell")
ro_allow("readonly-shell-write: PowerShell ls 2>$null is the null device, allowed", "ls 2>$null", tool="PowerShell")
ro_allow("readonly-shell-write: PowerShell ls 2>NUL is the null device, allowed", "ls 2>NUL", tool="PowerShell")

ro_allow("readonly-shell-write: a > inside double quotes is text, allowed", 'echo "a > b"')
ro_allow("readonly-shell-write: a > inside single quotes is text, allowed", "grep '>' f")
ro_allow("readonly-shell-write: a hash inside quotes is text, allowed", 'grep "# x" f')
ro_allow("readonly-shell-write: a redirect after a comment opener is inside the comment, allowed",
         "echo hi # > " + RO_PROBE)
ro_allow("readonly-shell-write: the word tee as a grep argument is text, allowed", "grep tee notes.txt")
ro_allow("readonly-shell-write: the word touch as a grep argument is text, allowed", "grep -n touch notes.txt")
ro_allow("readonly-shell-write: a > in a heredoc body is text, allowed", "cat <<'EOF'\nif a > b\nEOF")
ro_allow("readonly-shell-write: a lone apostrophe and a > in a heredoc body is text, allowed",
         "cat <<'EOF'\nDon't > here\nEOF")
ro_allow("readonly-shell-write: a write command named in a heredoc body is text, allowed",
         "cat <<'EOF'\ntouch " + RO_PROBE + "\nEOF")
ro_allow("readonly-shell-write: a comment opener in a heredoc body is text, allowed",
         "cat <<'EOF'\n# note > x\nEOF")
ro_allow("readonly-shell-write: a double-quoted string over two lines with a line starting > is text, allowed",
         'echo "first\n> second"')

# A > that a shell reads as a comparison, or that goes to a stream or the terminal, writes no file.
ro_allow("readonly-shell-write: a > comparison inside $(( )) arithmetic is not a redirect, allowed", "echo $((3 > 2))")
ro_allow("readonly-shell-write: a > string comparison inside [[ ]] is not a redirect, allowed",
         '[[ "a" > "b" ]] && echo y')
ro_allow("readonly-shell-write: a > comparison inside (( )) is not a redirect, allowed", "(( 3 > 2 )) && echo y")
ro_allow("readonly-shell-write: a > comparison inside [[ ]] after a command is not a redirect, allowed",
         "[[ 3 > 2 ]] && echo y")
ro_allow("readonly-shell-write: a > comparison with spaces inside $(( )) is not a redirect, allowed", "echo $(( 3 > 2 ))")
ro_allow("readonly-shell-write: a > in a ternary inside an assignment's $(( )) is not a redirect, allowed",
         "x=$(( a > b ? 1 : 0 ))")
ro_allow("readonly-shell-write: a redirect to /dev/stderr is a stream, allowed", "echo x > /dev/stderr")
ro_allow("readonly-shell-write: a redirect to /dev/stdout with no space is a stream, allowed", "echo x >/dev/stdout")
ro_allow("readonly-shell-write: a redirect to /dev/tty is the terminal, not a file, allowed", "echo x > /dev/tty")

# ---- E. Allowed for a read-only agent: writes into its own scratchpad, the session that owns it.
ro_allow("readonly-shell-write: a read-only agent's redirect into its own scratchpad is allowed",
         "echo x > " + RO_SCRATCH_CMD + "/ro-own.txt", session=FAKE_SESSION)
ro_allow("readonly-shell-write: a tee into its own scratchpad is allowed",
         "ls | tee " + RO_SCRATCH_CMD + "/ro-own-tee.txt", session=FAKE_SESSION)
ro_allow("readonly-shell-write: touch of a file in its own scratchpad is allowed",
         "touch " + RO_SCRATCH_CMD + "/ro-own-touch.txt", session=FAKE_SESSION)
ro_allow("readonly-shell-write: mktemp of a template in its own scratchpad is allowed",
         "mktemp " + RO_SCRATCH_CMD + "/ro-own.XXXXXX", session=FAKE_SESSION)
ro_allow("readonly-shell-write: a relative redirect from a cwd inside its own scratchpad is allowed",
         "echo x > out.txt", cwd=os.path.join(RO_SCRATCH, "notes"), session=FAKE_SESSION)

# ---- F. Not judged: a writing role, the orchestrator, and a call that names no read-only role.
ro_allow("readonly-shell-write: a builder's redirect to a file is allowed", RO_WRITE, agent_type="builder")
ro_allow("readonly-shell-write: a test-author's touch of a file is allowed", "touch " + RO_PROBE,
         agent_type="test-author")
ro_allow("readonly-shell-write: a builder's ssh touch is allowed", 'ssh host "touch /tmp/z"', agent_type="builder")
sh("readonly-shell-write: an orchestrator call with no agent is judged by no read-only rule, a redirect is allowed",
   RO_WRITE, "allow", silent=True)
ro_allow("readonly-shell-write: a call with a read-only agent_type and no agent_id is not judged", RO_WRITE,
         agent_id=None)
ro_allow("readonly-shell-write: a call with an agent_id and no agent_type is not judged", RO_WRITE,
         agent_type=None)


# ---- G. The owner override: a timed override reaches a read-only agent until it ends, a one-act override does not.
RO_ROLES_LABEL = "readonly-shell-write: agent_brief's READ_ONLY set loads and names its roles"
RO_TIMED_LABEL = "readonly-shell-write: a timed override lifts a read-only agent's write until it ends"
RO_ONCE_LABEL = "readonly-shell-write: a one-act override does not lift a read-only agent's write"


def ro_ov_call(config, session, seconds):
    """A read-only reviewer's redirect to a file, at OV_T0 + seconds."""
    return ov_call("Bash", {"command": RO_WRITE}, NOGIT, config, session, seconds, agent_id=RO_AGENT,
                   agent_type="reviewer")


def ro_timed_override_check():
    config, session = ov_config("ro-timed"), "ov-ro-timed"
    ok, why = ov_story([("agent, no override", lambda: ro_ov_call(config, session, 0), "deny", RO_RULE)])
    if not ok:
        return False, why
    note = ov_type(config, session, "override 15m")
    ok, why = ov_story([
        ("agent, first call", lambda: ro_ov_call(config, session, 60), "allow", RO_RULE),
        ("agent, second call", lambda: ro_ov_call(config, session, 120), "allow", RO_RULE),
        ("agent at the end instant", lambda: ro_ov_call(config, session, OV_TIMED_SECONDS), "deny", RO_RULE),
    ], note)
    if not ok:
        return False, why
    return True, "a read-only agent is allowed under a timed override until it ends"


def ro_once_override_check():
    config, session = ov_config("ro-once"), "ov-ro-once"
    ok, why = ov_story([("agent, no override", lambda: ro_ov_call(config, session, 0), "deny", RO_RULE)])
    if not ok:
        return False, why
    note = ov_type(config, session, "override")
    ok, why = ov_story([
        ("agent under a one-act override", lambda: ro_ov_call(config, session, 60), "deny", RO_RULE),
        ("agent, the one-act override is still unspent", lambda: ro_ov_call(config, session, 120), "deny", RO_RULE),
    ], note)
    if not ok:
        return False, why
    return True, "a read-only agent stays refused under a one-act override"


# LOG_CHECKS_EXTRA joined LOG_CHECKS in section 40805, so these checks join LOG_CHECKS here, as section 42840 does.
for _label, _check in ((RO_ROLES_LABEL, ro_roles_check),
                       (RO_TIMED_LABEL, ro_timed_override_check),
                       (RO_ONCE_LABEL, ro_once_override_check)):
    LOG_FAMILY[_label] = FAMILY
    LOG_CHECKS = LOG_CHECKS + ((_label, _check),)
FIXTURELESS_CHECKS.add(ro_roles_check)

TEMP_DIR = None   # back to the system temp, as the sections before this one leave it

# section 43732
FAMILY = "compaction-audit"
# The remedy the refusal prints (decision precompact-handoff, item 16; debt audit-remedy-is-refused). While the audit
# is owed, compaction-audit refuses every Bash call except a disk cleanup, so the one command the refusal tells the
# session to run, `python3 "<hooks>/precompact_handoff.py" --audit-brief --handoff "<handoff>"`, is refused by the rule
# it serves. These cases hold an allowance for that exact command. Each command is read from the refusal text the guard
# returns (the backticked command after "print the brief with"), never typed here, so a drift in the printed text fails
# a case instead of hiding behind a copy. Controls stay refused: another Bash command, the same script with other flags,
# the command chained or piped, and a script of the same name in another folder. With no audit owed, nothing is refused.
# The printed script spelled relative to the hooks folder is refused (RA_RELATIVE_CASES); the other spellings of the
# command are refused one form per case (RA_FORM_CASES), and the printed form stays allowed from the hooks folder and
# through a symlinked config folder.
# The helpers are the compaction-audit ones of section 43700 (ca_copy, ca_config, ca_owed, ca_call) and the verdict
# helpers of sections 35642 (_decision) and 36421 (ov_want). Nothing here copies them.
import shlex

RA_RULE = "compaction-audit"
# The command the refusal prints: the backticked text after "print the brief with".
RA_REMEDY_RE = re.compile(r"print the brief with `([^`]*)`")
# A hash-suffixed install folder, as the pinned install folder the refusal printed for a real session.
RA_HASHED_FOLDER = "claude-settings-live-9835a926ec53"


def ra_refusal_command(folder, cfg):
    """The owed state, then the remedy command the compaction-audit refusal prints, read from that refusal.
    -> (command, why). The call before it must be refused by compaction-audit: the scope is checked first."""
    flag, why = ca_owed(folder, cfg)
    if why:
        return "", why
    refused = _decision(ca_call(folder, cfg, "Bash", CA_BASH))
    why = ov_want(refused[0], refused[1], "deny", RA_RULE)
    if why:
        return "", "setup: the Bash call before the remedy was not refused by compaction-audit: %s" % why
    found = RA_REMEDY_RE.search(refused[1])
    if not found or "--audit-brief" not in found.group(1):
        return "", "setup: the refusal prints no remedy command with --audit-brief: %s" % refused[1][:160]
    return found.group(1), ""


def ra_script_of(command):
    """The script path the printed command runs: its second word, read with the shell's own quoting rules."""
    words = shlex.split(command)
    return words[1] if len(words) > 1 else ""


def ra_must_allow(folder, cfg, command, label):
    """The printed command is allowed while the audit is owed, and an allowed remedy clears nothing: the next Bash
    call is still refused by compaction-audit. -> (ok, why)."""
    run = _decision(ca_call(folder, cfg, "Bash", {"command": command}))
    why = ov_want(run[0], run[1], "allow", RA_RULE)
    if why:
        return False, "%s: the remedy the refusal prints was refused, not allowed: %s" % (label, why)
    after = _decision(ca_call(folder, cfg, "Bash", CA_BASH))
    why = ov_want(after[0], after[1], "deny", RA_RULE)
    if why:
        return False, "%s: after the allowed remedy the audit was no longer owed: %s" % (label, why)
    return True, "%s: the remedy the refusal prints is allowed, and the audit stays owed" % label


def ra_exact_check():
    """RED on the old code. The command the refusal prints, in the folder the guard runs from, quotes included."""
    folder = ca_copy("intact", drop_layout=False)
    cfg = ca_config("remedy-exact-cfg", None)
    command, why = ra_refusal_command(folder, cfg)
    if why:
        return False, why
    return ra_must_allow(folder, cfg, command, "exact printed form")


def ra_hashed_check():
    """RED on the old code. The same printed command, its script in a hash-suffixed install folder."""
    folder = ca_copy(RA_HASHED_FOLDER, drop_layout=False)
    cfg = ca_config("remedy-hashed-cfg", None)
    command, why = ra_refusal_command(folder, cfg)
    if why:
        return False, why
    return ra_must_allow(folder, cfg, command, "hash-suffixed install folder")


def ra_unquoted_check():
    """RED on the old code. The printed command with its shell quotes removed. The words must read back the same, so a
    path with a space is a setup fault, not a verdict."""
    folder = ca_copy("intact", drop_layout=False)
    cfg = ca_config("remedy-unquoted-cfg", None)
    command, why = ra_refusal_command(folder, cfg)
    if why:
        return False, why
    words = shlex.split(command)
    bare = " ".join(words)
    if shlex.split(bare) != words:
        return False, "setup: the printed command has a word that quotes cannot drop, so no bare form exists"
    return ra_must_allow(folder, cfg, bare, "unquoted form")


def ra_control_refused(folder, cfg, command, label):
    """GREEN control: compaction-audit refuses the call while the audit is owed. -> (ok, why)."""
    run = _decision(ca_call(folder, cfg, "Bash", {"command": command}))
    why = ov_want(run[0], run[1], "deny", RA_RULE)
    if why:
        return False, "control (%s): not refused by compaction-audit: %s" % (label, why)
    return True, "control (%s): refused by compaction-audit while the audit is owed" % label


def ra_controls_check():
    """GREEN controls, all refused while the audit is owed: another Bash command; the same script with other flags; the
    printed command with an extra flag; the command chained or piped; a script of the same name in another folder."""
    folder = ca_copy("intact", drop_layout=False)
    cfg = ca_config("remedy-controls-cfg", None)
    command, why = ra_refusal_command(folder, cfg)
    if why:
        return False, why
    script = ra_script_of(command)
    if not script or script not in command:
        return False, "setup: the printed command names no script path to vary"
    # A copy of the same file name in a folder that is not the guard's own hooks folder.
    elsewhere_dir = os.path.join(ROOT, "remedy-elsewhere")
    os.makedirs(elsewhere_dir, exist_ok=True)
    elsewhere = os.path.join(elsewhere_dir, os.path.basename(script))
    shutil.copy(script, elsewhere)
    leak = os.path.join(ROOT, "remedy-leak.txt")
    cases = (
        ("another Bash command", CA_BASH["command"]),
        ("the script with another mode flag", 'python3 "%s" --session-end' % script),
        ("the printed command with an extra flag", command + " --session-end"),
        ("the printed command chained with &&", command + " && echo done"),
        ("the printed command chained with ;", command + "; echo done"),
        ("the printed command piped into a write", command + ' | tee "%s"' % leak),
        ("a same-name script in another folder", command.replace(script, elsewhere, 1)),
    )
    for label, text in cases:
        ok, why = ra_control_refused(folder, cfg, text, label)
        if not ok:
            return False, why
    return True, "controls: every other form stays refused by compaction-audit while the audit is owed"


def ra_no_audit_check():
    """GREEN control: with no audit owed, the printed command and an ordinary Bash call both pass, as on main."""
    folder = ca_copy("intact", drop_layout=False)
    owed_cfg = ca_config("remedy-noowed-source-cfg", None)
    command, why = ra_refusal_command(folder, owed_cfg)
    if why:
        return False, why
    cfg = ca_config("remedy-noowed-cfg", None)
    run = _decision(ca_call(folder, cfg, "Bash", {"command": command}))
    why = ov_want(run[0], run[1], "allow", RA_RULE)
    if why:
        return False, "control (no audit owed): the printed command was refused: %s" % why
    ordinary = _decision(ca_call(folder, cfg, "Bash", CA_BASH))
    why = ov_want(ordinary[0], ordinary[1], "allow", RA_RULE)
    if why:
        return False, "control (no audit owed): an ordinary Bash call was refused: %s" % why
    return True, "control (no audit owed): the printed command and an ordinary Bash call both pass"


RA_CHECKS = (
    ("compaction-audit: the remedy the refusal prints (exact, quotes included) is allowed while the audit is owed",
     ra_exact_check),
    ("compaction-audit: the remedy the refusal prints, script in a hash-suffixed install folder, is allowed while owed",
     ra_hashed_check),
    ("compaction-audit: the remedy the refusal prints, with its quotes removed, is allowed while the audit is owed",
     ra_unquoted_check),
    ("compaction-audit: control, other Bash, other flags, chained, piped and a same-name script elsewhere stay refused",
     ra_controls_check),
    ("compaction-audit: control, with no audit owed the printed remedy and an ordinary Bash call pass",
     ra_no_audit_check),
)
# The printed script spelled relative to the hooks folder. The guard resolves a relative script path against its own
# working folder, and a session runs the call from the hooks folder, so each spelling names the helper there. The guard
# must refuse it while the audit is owed: only the printed absolute spelling is allowed. One case per spelling.


def ra_crashes(cfg):
    """How many guard-crash lines the config folder's guard.log holds. A crash fails open, so a crashed call reads as an
    allow; a count that rises during one call says the call crashed."""
    try:
        with open(os.path.join(cfg, "guard.log"), encoding="utf-8") as handle:
            return sum(1 for line in handle if "guard-crash" in line)
    except OSError:
        return 0


def ra_run(folder, cfg, command, where=None):
    """One Bash call through the copy's guard, run from `where` (None: the suite's default). -> (decision, reason,
    crashed)."""
    before = ra_crashes(cfg)
    run = _decision(ca_call(folder, cfg, "Bash", {"command": command}, where))
    return run[0], run[1], ra_crashes(cfg) > before


def ra_swap(command, old, new):
    """The printed command with one text swapped for another. The text must sit in the printed command exactly once,
    so a drift in the printed form is a setup fault rather than a verdict. -> (text, why)."""
    if command.count(old) != 1:
        return "", "setup: %r is not in the printed command exactly once" % old
    return command.replace(old, new), ""


def ra_relative_check(slug, dot, label):
    """RED on the old code. The printed command with its script written relative to the hooks folder, run from that
    folder: the payload's cwd and the guard process's working folder are both the hooks folder. The guard must refuse
    it while the audit is owed."""
    folder = ca_copy("intact", drop_layout=False)
    cfg = ca_config("remedy-%s-cfg" % slug, None)
    command, why = ra_refusal_command(folder, cfg)
    if why:
        return False, why
    script = ra_script_of(command)
    hooks = os.path.dirname(script)
    written = ("./" if dot else "") + os.path.basename(script)
    # Scope first: the relative spelling must name the printed helper from the hooks folder, or the case tests
    # another file.
    if os.path.realpath(os.path.join(hooks, written)) != os.path.realpath(script):
        return False, "setup: %r does not name the printed helper from the hooks folder" % written
    relative, why = ra_swap(command, '"%s"' % script, '"%s"' % written)
    if why:
        return False, why
    decision, reason, crashed = ra_run(folder, cfg, relative, hooks)
    if crashed:
        return False, "%s: the guard crashed on the relative remedy, so the call was not judged: %s" % (
            label, ca_crash_line(cfg))
    why = ov_want(decision, reason, "deny", RA_RULE)
    if why:
        return False, "%s: the relative remedy was allowed while the audit is owed, want refused: %s" % (label, why)
    return True, "%s: refused by compaction-audit while the audit is owed" % label


def ra_allowed_checked(folder, cfg, command, label, where=None):
    """GREEN control: the printed remedy is allowed from `where`, with no crash, and the audit stays owed after it.
    -> (ok, why)."""
    decision, reason, crashed = ra_run(folder, cfg, command, where)
    if crashed:
        return False, "%s: the guard crashed on the printed remedy, so the call was not judged: %s" % (
            label, ca_crash_line(cfg))
    why = ov_want(decision, reason, "allow", RA_RULE)
    if why:
        return False, "%s: the remedy the refusal prints was refused, not allowed: %s" % (label, why)
    decision, reason, _ = ra_run(folder, cfg, CA_BASH["command"])
    why = ov_want(decision, reason, "deny", RA_RULE)
    if why:
        return False, "%s: after the allowed remedy the audit was no longer owed: %s" % (label, why)
    return True, "%s: the remedy the refusal prints is allowed, and the audit stays owed" % label


def ra_hooks_allowed_check():
    """GREEN control, the pin beside the red spellings: the printed absolute command, run from the hooks folder, stays
    allowed while the audit is owed. A fix that refuses by folder, not by spelling, fails here."""
    folder = ca_copy("intact", drop_layout=False)
    cfg = ca_config("remedy-hooks-cwd-cfg", None)
    command, why = ra_refusal_command(folder, cfg)
    if why:
        return False, why
    script = ra_script_of(command)
    return ra_allowed_checked(folder, cfg, command, "control (printed absolute form from the hooks folder)",
                              os.path.dirname(script))


def ra_form_check(slug, derive, label):
    """GREEN control: one variant of the printed command, derived from it by `derive(command, cfg, script, handoff)`,
    is refused by compaction-audit while the audit is owed. Each variant is one case, so a failure names one form."""
    folder = ca_copy("intact", drop_layout=False)
    cfg = ca_config("remedy-%s-cfg" % slug, None)
    command, why = ra_refusal_command(folder, cfg)
    if why:
        return False, why
    script = ra_script_of(command)
    handoff = shlex.split(command)[-1]
    variant, why = derive(command, cfg, script, handoff)
    if why:
        return False, why
    decision, reason, crashed = ra_run(folder, cfg, variant)
    if crashed:
        return False, "%s: the guard crashed on the variant, so it was not judged: %s" % (label, ca_crash_line(cfg))
    why = ov_want(decision, reason, "deny", RA_RULE)
    if why:
        return False, "%s: not refused by compaction-audit while the audit is owed: %s" % (label, why)
    return True, "%s: refused by compaction-audit while the audit is owed" % label


def ra_flags_swapped(command, cfg, script, handoff):
    """The flags in the other order: --handoff first, --audit-brief last."""
    swapped, why = ra_swap(command, " --audit-brief --handoff ", " --handoff ")
    if why:
        return "", why
    return swapped + " --audit-brief", ""


def ra_other_session_handoff(command, cfg, script, handoff):
    """The same command, its handoff argument another session's handoff path."""
    other = os.path.join(cfg, "handoffs", OTHER_SESSION + ".md")
    write(other, CA_HANDOFF)
    return ra_swap(command, '"%s"' % handoff, '"%s"' % other)


def ra_newline_then_command(command, cfg, script, handoff):
    """The printed command, then a newline and another command."""
    return command + "\necho done", ""


def ra_substituted_handoff(command, cfg, script, handoff):
    """The handoff argument wrapped in a command substitution."""
    return ra_swap(command, '"%s"' % handoff, '"$(echo %s)"' % handoff)


def ra_env_prefix(command, cfg, script, handoff):
    """The printed command behind an environment assignment."""
    return "PYTHONDONTWRITEBYTECODE=1 " + command, ""


def ra_python_c(command, cfg, script, handoff):
    """The helper run through python3 -c, the script path in the code text."""
    return ra_swap(command, 'python3 "%s"' % script, 'python3 -c "exec(open(\'%s\').read())"' % script)


def ra_symlink_to_other_script(command, cfg, script, handoff):
    """The printed script replaced by a symlink in another folder, named as the script is, that points at another
    script. The guard judges the link's real path, so it is not the helper."""
    elsewhere = os.path.join(ROOT, "remedy-symlink-elsewhere")
    os.makedirs(elsewhere, exist_ok=True)
    other = os.path.join(elsewhere, "other-script.py")
    write(other, "# another script, not the audit helper\n")
    link = os.path.join(elsewhere, os.path.basename(script))
    if not os.path.lexists(link):
        os.symlink(other, link)
    return ra_swap(command, '"%s"' % script, '"%s"' % link)


RA_FORM_CASES = (
    ("compaction-audit: control, the printed remedy with its flags in the other order stays refused while owed",
     "flags-swapped", ra_flags_swapped),
    ("compaction-audit: control, the printed remedy with another session's handoff path stays refused while owed",
     "other-session", ra_other_session_handoff),
    ("compaction-audit: control, the printed remedy then a newline and another command stays refused while owed",
     "newline", ra_newline_then_command),
    ("compaction-audit: control, the printed remedy with a command substitution in the handoff argument stays refused",
     "substitution", ra_substituted_handoff),
    ("compaction-audit: control, the printed remedy behind an env prefix stays refused while the audit is owed",
     "env-prefix", ra_env_prefix),
    ("compaction-audit: control, the helper run through python3 -c stays refused while the audit is owed",
     "python-c", ra_python_c),
)


def ra_symlinked_config_check():
    """GREEN control: the printed remedy, its config folder reached through a symlink, stays allowed while the audit is
    owed. The refusal prints the handoff path as the session passes it, so the link's spelling is the one allowed."""
    folder = ca_copy("intact", drop_layout=False)
    real = ca_config("remedy-linked-real-cfg", None)
    link = os.path.join(ROOT, "compaction-audit-cfg", "remedy-linked-cfg-link")
    os.symlink(real, link, target_is_directory=True)
    command, why = ra_refusal_command(folder, link)
    if why:
        return False, why
    return ra_allowed_checked(folder, link, command,
                              "control (printed remedy, config folder reached through a symlink)")


RA_RELATIVE_CASES = (
    ("compaction-audit: the printed remedy, script as the file name alone, run from the hooks folder, is refused",
     "relative-name", False),
    ("compaction-audit: the printed remedy, script as ./ and the file name, run from the hooks folder, is refused",
     "relative-dot", True),
)
RA_NEW_CHECKS = tuple(
    (label, (lambda slug=slug, dot=dot, label=label: ra_relative_check(slug, dot, label)))
    for label, slug, dot in RA_RELATIVE_CASES
) + (
    ("compaction-audit: control, the printed absolute remedy run from the hooks folder stays allowed while owed",
     ra_hooks_allowed_check),
)
RA_NEW_CHECKS = RA_NEW_CHECKS + tuple(
    (label, (lambda slug=slug, derive=derive, label=label: ra_form_check(slug, derive, label)))
    for label, slug, derive in RA_FORM_CASES
)
if LINKS_MADE:   # the symlink cases need the privilege s00442 probes at import, and skip where it is missing
    RA_NEW_CHECKS = RA_NEW_CHECKS + (
        ("compaction-audit: control, the symlink in another folder pointing at another script stays refused while owed",
         lambda: ra_form_check("symlink-other", ra_symlink_to_other_script,
                               "compaction-audit: control, the symlink in another folder pointing at another script "
                               "stays refused while owed")),
        ("compaction-audit: control, the printed remedy with its config folder reached through a symlink stays allowed",
         ra_symlinked_config_check),
    )
RA_CHECKS = RA_CHECKS + RA_NEW_CHECKS

LOG_CHECKS = LOG_CHECKS + RA_CHECKS
for _label, _check in RA_CHECKS:
    LOG_FAMILY[_label] = FAMILY

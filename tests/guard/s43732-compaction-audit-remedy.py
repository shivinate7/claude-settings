# section 43732
FAMILY = "compaction-audit"
# The remedy the refusal prints (decision precompact-handoff, item 16; debt audit-remedy-is-refused). While the audit
# is owed, compaction-audit refuses every Bash call except a disk cleanup, so the one command the refusal tells the
# session to run, `python3 "<hooks>/precompact_handoff.py" --audit-brief --handoff "<handoff>"`, is refused by the rule
# it serves. These cases hold an allowance for that exact command. Each command is read from the refusal text the guard
# returns (the backticked command after "print the brief with"), never typed here, so a drift in the printed text fails
# a case instead of hiding behind a copy. Controls stay refused: another Bash command, the same script with other flags,
# the command chained or piped, and a script of the same name in another folder. With no audit owed, nothing is refused.
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
LOG_CHECKS = LOG_CHECKS + RA_CHECKS
for _label, _check in RA_CHECKS:
    LOG_FAMILY[_label] = FAMILY

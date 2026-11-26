# section 43732
FAMILY = "compaction-audit"
# While the audit is owed, compaction-audit allows the one remedy command it prints: guard.audit_helper_hit compares the
# call's command with reread_check.audit_helper_command, as exact text. The same call written another way runs the same
# file with the same arguments, so the rule should judge it the same: the spellings below must be allowed. The other
# spellings name another file, another session, or more than the helper, and stay refused.
# Each command is read from the refusal text the guard returns (the backticked command after "print the brief with"),
# never typed here, so a drift in the printed text fails a case. The helpers are the compaction-audit ones of section
# 43700 (ca_copy, ca_config, ca_owed, ca_call, CA_BASH, CA_HANDOFF, ca_crash_line) and the verdict helpers of sections
# 35642 (_decision) and 36421 (ov_want). A spelling that must pass is a RED case on main, which allows only the exact
# text. A spelling that must stay refused, and the exact text itself, are GREEN pins.
import shlex

AR_RULE = "compaction-audit"
AR_REMEDY_RE = re.compile(r"print the brief with `([^`]*)`")
AR_LINKS = os.path.join(ROOT, "ar-links")       # the symlinks a spelling reaches the helper through
AR_LEAK = os.path.join(ROOT, "ar-leak.txt")     # the file a piped spelling would write, if it ran


def ar_crashes(cfg):
    """How many guard-crash lines the config folder's guard.log holds. A crash fails open, so a crashed call reads as an
    allow; a count that rises during one call says the call crashed."""
    try:
        with open(os.path.join(cfg, "guard.log"), encoding="utf-8") as handle:
            return sum(1 for line in handle if "guard-crash" in line)
    except OSError:
        return 0


def ar_judge(folder, cfg, command, where=None):
    """One Bash call through the copy's guard, run from `where` (None: the suite's folder). -> (decision, reason, crashed)."""
    before = ar_crashes(cfg)
    run = _decision(ca_call(folder, cfg, "Bash", {"command": command}, where))
    return run[0], run[1], ar_crashes(cfg) > before


def ar_words(command):
    """The words of a command, read with the shell's own quoting rules."""
    return shlex.split(command)


def ar_setup(name):
    """The copy, the config folder and the printed remedy, with the audit owed. -> (folder, cfg, command, why). The Bash
    call before the remedy is judged first, so the remedy is read from the compaction-audit refusal and nothing else."""
    folder = ca_copy("intact", drop_layout=False)
    cfg = ca_config("ar-%s-cfg" % name, None)
    _, why = ca_owed(folder, cfg)
    if why:
        return folder, cfg, "", why
    decision, reason, _ = ar_judge(folder, cfg, CA_BASH["command"])
    why = ov_want(decision, reason, "deny", AR_RULE)
    if why:
        return folder, cfg, "", "setup: the Bash call before the remedy was not refused by compaction-audit: %s" % why
    found = AR_REMEDY_RE.search(reason)
    if not found or "--audit-brief" not in found.group(1):
        return folder, cfg, "", "setup: the refusal prints no remedy command with --audit-brief: %s" % reason[:160]
    command = found.group(1)
    words = ar_words(command)
    if len(words) != 5 or words[0] != "python3" or words[2:4] != ["--audit-brief", "--handoff"]:
        return folder, cfg, "", ("setup: the printed command is not `python3 <script> --audit-brief --handoff <handoff>`: %s"
                                 % command[:160])
    return folder, cfg, command, ""


def ar_same_file(spelled, script):
    """Scope: the spelling reaches the printed helper, so a case that varies the spelling tests that spelling and not
    another file."""
    return os.path.realpath(spelled) == os.path.realpath(script)


def ar_link(path, target):
    """A symlink at `path` to `target`, made once. A folder target makes a directory link."""
    if not os.path.lexists(path):
        os.makedirs(os.path.dirname(path), exist_ok=True)
        os.symlink(target, path, target_is_directory=os.path.isdir(target))
    return path


def ar_swap(command, old, new):
    """The printed command with one text swapped for another. The text must sit in the printed command exactly once, so
    a drift in the printed form is a setup fault rather than a verdict. -> (text, where, why)."""
    if command.count(old) != 1:
        return "", None, "setup: %r is not in the printed command exactly once" % old
    return command.replace(old, new), None, ""


def ar_exact(folder, cfg, command):
    """The printed command as the refusal prints it: the control the rest are measured against."""
    return command, None, ""


def ar_exact_from_hooks(folder, cfg, command):
    """The printed absolute command, run from the hooks folder: the spelling is the one allowed, whatever the folder."""
    return command, os.path.dirname(ar_words(command)[1]), ""


def ar_unquoted(folder, cfg, command):
    """The printed command with its shell quotes removed. The words must read back the same, so a path with a space is a
    setup fault, not a verdict."""
    words = ar_words(command)
    bare = " ".join(words)
    if ar_words(bare) != words:
        return "", None, "setup: the printed command has a word that quotes cannot drop, so no bare form exists"
    return bare, None, ""


def ar_single_quoted(folder, cfg, command):
    """The script and the handoff path in single quotes, the interpreter and the flags bare."""
    words = ar_words(command)
    if "'" in words[1] or "'" in words[4]:
        return "", None, "setup: the printed script or handoff holds a single quote, so no single-quoted form exists"
    text = "%s '%s' %s %s '%s'" % (words[0], words[1], words[2], words[3], words[4])
    if ar_words(text) != words:
        return "", None, "setup: the single-quoted form does not read back as the printed words"
    return text, None, ""


def ar_hooks_link(folder, cfg, command):
    """The printed script spelled through a symlink to its hooks folder: the same file, reached by another path."""
    words = ar_words(command)
    script = words[1]
    link = ar_link(os.path.join(AR_LINKS, "hooks-link"), os.path.dirname(script))
    spelled = os.path.join(link, os.path.basename(script))
    if not ar_same_file(spelled, script):
        return "", None, "setup: %r is not the printed helper through the hooks link" % spelled
    return '%s "%s" %s %s "%s"' % (words[0], spelled, words[2], words[3], words[4]), None, ""


def ar_install_link(folder, cfg, command):
    """The printed script spelled through a symlink to the install folder that holds its hooks folder."""
    words = ar_words(command)
    script = words[1]
    root = os.path.dirname(os.path.dirname(script))
    link = ar_link(os.path.join(AR_LINKS, "install-link"), root)
    spelled = os.path.join(link, os.path.relpath(script, root))
    if not ar_same_file(spelled, script):
        return "", None, "setup: %r is not the printed helper through the install link" % spelled
    return '%s "%s" %s %s "%s"' % (words[0], spelled, words[2], words[3], words[4]), None, ""


def ar_from_hooks(command, prefix):
    """The printed script written relative to the hooks folder (`prefix` then its file name), run from that folder: the
    payload's cwd and the guard process's working folder are both the hooks folder."""
    words = ar_words(command)
    hooks = os.path.dirname(words[1])
    written = prefix + os.path.basename(words[1])
    if not ar_same_file(os.path.join(hooks, written), words[1]):
        return "", None, "setup: %r does not name the printed helper from the hooks folder" % written
    return '%s %s %s %s "%s"' % (words[0], written, words[2], words[3], words[4]), hooks, ""


def ar_relative_bare(folder, cfg, command):
    return ar_from_hooks(command, "")


def ar_relative_dot(folder, cfg, command):
    return ar_from_hooks(command, "./")


def ar_python_bin(folder, cfg, command):
    """The printed command run through `python`, not `python3`."""
    return ar_swap(command, 'python3 "', 'python "')


def ar_other_session(folder, cfg, command):
    """The printed command, its handoff argument another session's handoff path."""
    other = os.path.join(cfg, "handoffs", OTHER_SESSION + ".md")
    write(other, CA_HANDOFF)
    return ar_swap(command, '"%s"' % ar_words(command)[4], '"%s"' % other)


def ar_extra_flag(folder, cfg, command):
    """The printed command with one more mode flag after the handoff path."""
    return command + " --session-end", None, ""


def ar_swapped_flags(folder, cfg, command):
    """The printed command with --handoff ahead of --audit-brief."""
    swapped, _, why = ar_swap(command, " --audit-brief --handoff ", " --handoff ")
    if why:
        return "", None, why
    return swapped + " --audit-brief", None, ""


def ar_and_chain(folder, cfg, command):
    return command + " && echo done", None, ""


def ar_semi_chain(folder, cfg, command):
    return command + "; echo done", None, ""


def ar_pipe(folder, cfg, command):
    return command + ' | tee "%s"' % AR_LEAK, None, ""


def ar_substitution(folder, cfg, command):
    """The printed command with the handoff argument wrapped in a command substitution."""
    handoff = ar_words(command)[4]
    return ar_swap(command, '"%s"' % handoff, '"$(echo %s)"' % handoff)


def ar_env_prefix(folder, cfg, command):
    return "PYTHONDONTWRITEBYTECODE=1 " + command, None, ""


def ar_symlink_other(folder, cfg, command):
    """The printed script replaced by a symlink, named as the script is, in another folder, that points at another
    script. The guard judges the link's real path, so the call is not the helper."""
    words = ar_words(command)
    other = os.path.join(ROOT, "ar-elsewhere", "other-script.py")
    write(other, "# another script, not the audit helper\n")
    link = ar_link(os.path.join(ROOT, "ar-elsewhere", os.path.basename(words[1])), other)
    return '%s "%s" %s %s "%s"' % (words[0], link, words[2], words[3], words[4]), None, ""


def ar_pass_check(name, spell):
    """The remedy written as `spell` writes it is allowed while the audit is owed, and the ordinary call after it is
    refused, so the audit stays owed. -> (ok, why). The message starts with the spelling's name: one cause per line."""
    folder, cfg, command, why = ar_setup(name)
    if why:
        return False, "%s: %s" % (name, why)
    spelled, where, why = spell(folder, cfg, command)
    if why:
        return False, "%s: %s" % (name, why)
    decision, reason, crashed = ar_judge(folder, cfg, spelled, where)
    if crashed:
        return False, "%s: the guard crashed on the remedy, so the call was not judged: %s" % (name, ca_crash_line(cfg))
    why = ov_want(decision, reason, "allow", AR_RULE)
    if why:
        return False, "%s: the remedy the refusal prints was refused, want allowed while owed: %s" % (name, why)
    decision, reason, _ = ar_judge(folder, cfg, CA_BASH["command"])
    why = ov_want(decision, reason, "deny", AR_RULE)
    if why:
        return False, "%s: after the allowed remedy the ordinary call was allowed, so the audit is no longer owed: %s" % (
            name, why)
    return True, "%s: the remedy is allowed while the audit is owed, and the ordinary call after it is refused" % name


def ar_refused_check(name, spell):
    """The command written as `spell` writes it is refused by compaction-audit while the audit is owed. -> (ok, why)."""
    folder, cfg, command, why = ar_setup(name)
    if why:
        return False, "%s: %s" % (name, why)
    spelled, where, why = spell(folder, cfg, command)
    if why:
        return False, "%s: %s" % (name, why)
    decision, reason, crashed = ar_judge(folder, cfg, spelled, where)
    if crashed:
        return False, "%s: the guard crashed on the variant, so it was not judged: %s" % (name, ca_crash_line(cfg))
    why = ov_want(decision, reason, "deny", AR_RULE)
    if why:
        return False, "%s: not refused by compaction-audit while the audit is owed: %s" % (name, why)
    return True, "%s: refused by compaction-audit while the audit is owed" % name


# Each spelling of the printed remedy that the rule must allow while the audit is owed. A case fails when its spelling is refused.
AR_PASS_CASES = (
    ("compaction-audit: the printed remedy with its quotes removed is allowed while the audit is owed",
     "unquoted", ar_unquoted),
    ("compaction-audit: the printed remedy with its script and handoff in single quotes is allowed while the audit is owed",
     "single-quoted", ar_single_quoted),
)
AR_PASS_LINK_CASES = (
    ("compaction-audit: the printed remedy, script spelled through a symlinked hooks folder, is allowed while owed",
     "hooks-link", ar_hooks_link),
    ("compaction-audit: the printed remedy, script spelled through a symlinked install folder, is allowed while owed",
     "install-link", ar_install_link),
)
# GREEN pins: the exact text, and the printed absolute text run from the hooks folder, stay allowed on main.
AR_ANCHOR_CASES = (
    ("compaction-audit: control, the printed remedy's exact text is allowed while the audit is owed",
     "exact", ar_exact),
    ("compaction-audit: control, the printed absolute remedy run from the hooks folder stays allowed while owed",
     "exact-from-hooks", ar_exact_from_hooks),
)
# GREEN pins: each spelling that names another file, another session, or more than the helper stays refused on main.
AR_REFUSED_CASES = (
    ("compaction-audit: control, the script as a bare file name run from the hooks folder stays refused while owed",
     "relative-bare", ar_relative_bare),
    ("compaction-audit: control, the script as ./ and a file name run from the hooks folder stays refused while owed",
     "relative-dot", ar_relative_dot),
    ("compaction-audit: control, the remedy run through python, not python3, stays refused while the audit is owed",
     "python-bin", ar_python_bin),
    ("compaction-audit: control, the remedy with another session's handoff stays refused while the audit is owed",
     "other-session", ar_other_session),
    ("compaction-audit: control, the remedy with an extra flag stays refused while the audit is owed",
     "extra-flag", ar_extra_flag),
    ("compaction-audit: control, the remedy with its flags swapped stays refused while the audit is owed",
     "swapped-flags", ar_swapped_flags),
    ("compaction-audit: control, the remedy chained with && stays refused while the audit is owed",
     "and-chain", ar_and_chain),
    ("compaction-audit: control, the remedy chained with ; stays refused while the audit is owed",
     "semi-chain", ar_semi_chain),
    ("compaction-audit: control, the remedy piped into a write stays refused while the audit is owed",
     "pipe", ar_pipe),
    ("compaction-audit: control, the remedy with a command substitution in its handoff stays refused while owed",
     "substitution", ar_substitution),
    ("compaction-audit: control, the remedy behind an environment prefix stays refused while the audit is owed",
     "env-prefix", ar_env_prefix),
)
AR_REFUSED_LINK_CASES = (
    ("compaction-audit: control, a symlink named as the helper, in another folder, to another script stays refused",
     "symlink-other", ar_symlink_other),
)
NO_LINK_FOR_AR = "this host gives no symlink, so the symlink spelling of the remedy does not run here"


AR_CHECKS = (
    tuple((label, (lambda slug=slug, spell=spell: ar_pass_check(slug, spell))) for label, slug, spell in AR_ANCHOR_CASES)
    + tuple((label, (lambda slug=slug, spell=spell: ar_pass_check(slug, spell))) for label, slug, spell in AR_PASS_CASES)
    + tuple((label, (lambda slug=slug, spell=spell: ar_refused_check(slug, spell)))
            for label, slug, spell in AR_REFUSED_CASES)
)
if LINKS_MADE:   # the symlink cases need the privilege s00442 probes at import, and skip where it is missing
    AR_CHECKS = AR_CHECKS + tuple(
        (label, (lambda slug=slug, spell=spell: ar_pass_check(slug, spell))) for label, slug, spell in AR_PASS_LINK_CASES
    ) + tuple(
        (label, (lambda slug=slug, spell=spell: ar_refused_check(slug, spell))) for label, slug, spell in AR_REFUSED_LINK_CASES
    )
else:
    for _label, _slug, _spell in AR_PASS_LINK_CASES + AR_REFUSED_LINK_CASES:
        skip_case(_label, NO_LINK_FOR_AR)

LOG_CHECKS = LOG_CHECKS + AR_CHECKS
for _label, _check in AR_CHECKS:
    LOG_FAMILY[_label] = FAMILY

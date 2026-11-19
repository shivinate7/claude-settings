# section 43700
FAMILY = "compaction-audit"
# main() clears the audit flag once judge() returns for an Audit: spawn. A crash in a later rule ends judge() another
# way: main() logs guard-crash and fails open, so the spawn runs and the flag stays. Every later call is then refused
# with "the handoff audit is still owed". The crash these cases hold: a spawn in a repo with a pointer checkout reaches
# guard_core.layout_module() through role_model_check, and a lint folder with no lint/layout.py raises there.
CA_SID = "5d1e8c4a-0000-4000-8000-00000000a0a1"   # the main session in these cases
CA_AUDIT = {"description": "audit", "subagent_type": "Explore", "model": "sonnet",
            "prompt": "Audit: check the handoff against the repo."}
CA_NOT_AUDIT = {"description": "review", "subagent_type": "Explore", "model": "sonnet",
                "prompt": "Review the diff."}
CA_BUILDER_AUDIT = {"description": "audit", "subagent_type": "builder", "model": "sonnet",
                    "prompt": "Audit: check the handoff against the repo."}
CA_BASH = {"command": "echo hi"}
CA_HANDOFF = "# Handoff\n"


def ca_copy(name, drop_layout):
    """A copy of the guard's hooks folder and of lint/, under ROOT. The guard reads lint/layout.py from the lint folder
    beside its hooks folder (guard_core.layout_module). `drop_layout` leaves that one file out. Built once per name."""
    root = os.path.join(ROOT, "compaction-audit", name)
    guard_copy = os.path.join(root, "hooks", "guard.py")
    if not os.path.isfile(guard_copy):
        os.makedirs(os.path.join(root, "hooks"), exist_ok=True)
        for path in mutate_shared.module_files(os.path.dirname(GUARD)):
            shutil.copy(path, os.path.join(root, "hooks"))
        shutil.copy(GUARD, guard_copy)
        shutil.copytree(os.path.join(REPO, "lint"), os.path.join(root, "lint"),
                        ignore=shutil.ignore_patterns("__pycache__"))
        if drop_layout:
            os.remove(os.path.join(root, "lint", "layout.py"))
    return root


def ca_config(name, pointer_root):
    """A config folder under ROOT with the session's handoff. Its CLAUDE.md points at `pointer_root` when one is given:
    the pointer checkout that role_model_one reads (guard_pointer.pointer_checkout)."""
    cfg = os.path.join(ROOT, "compaction-audit-cfg", name)
    write(os.path.join(cfg, "handoffs", CA_SID + ".md"), CA_HANDOFF)
    if pointer_root:
        write(os.path.join(cfg, "CLAUDE.md"), "@%s/CLAUDE.md\n" % pointer_root)
    return cfg


def ca_env(cfg):
    env = dict(os.environ)
    for name in ("CLAUDE_CODE_REMOTE", "PYTHONPATH", "CLAUDE_CODE_SESSION_ID"):
        env.pop(name, None)
    env["CLAUDE_CONFIG_DIR"] = cfg
    env["CLAUDE_GUARD_ROOT_PID"] = str(os.getpid())
    return env


def ca_hook(folder, mode, payload, cfg):
    """One run of the copy's reread_check.py in `mode`."""
    return subprocess.run([sys.executable, os.path.join(folder, "hooks", "reread_check.py"), mode],
                          input=json.dumps(payload), capture_output=True, text=True, env=ca_env(cfg), timeout=120)


def ca_call(folder, cfg, tool, tool_input):
    """One call through the copy's guard.py, from a folder that is not a git tree, in session CA_SID."""
    payload = {"tool_name": tool, "tool_input": tool_input, "cwd": NOGIT, "session_id": CA_SID}
    return subprocess.run([sys.executable, os.path.join(folder, "hooks", "guard.py")], input=json.dumps(payload),
                          capture_output=True, text=True, env=ca_env(cfg), timeout=120)


def ca_owed(folder, cfg):
    """PostCompact sets the flags, and a Read of the handoff clears the reread flag, so the audit is owed. Returns the
    audit flag's path, or '' with why when the flags do not read that way (a setup fault)."""
    handoff = os.path.join(cfg, "handoffs", CA_SID + ".md")
    post = ca_hook(folder, "--post-compact", {"session_id": CA_SID}, cfg)
    read = ca_hook(folder, "--pre-read", {"session_id": CA_SID, "tool_name": "Read",
                                          "tool_input": {"file_path": handoff}}, cfg)
    with hu_config(cfg):
        flag = ph.audit_flag_path(CA_SID)   # the one home of the flag paths (precompact_handoff)
    if post.returncode != 0 or read.returncode != 0:
        return "", "setup: reread_check exited %d and %d" % (post.returncode, read.returncode)
    if not os.path.isfile(flag):
        return "", "setup: the audit flag was not set by PostCompact"
    return flag, ""


def ca_crash_line(cfg):
    """The last guard-crash line of the config folder's guard.log, or ''. Evidence for a failure message only."""
    try:
        with open(os.path.join(cfg, "guard.log"), encoding="utf-8") as handle:
            lines = [line for line in handle.read().splitlines() if "guard-crash" in line]
    except OSError:
        return ""
    return lines[-1][-160:] if lines else ""


def ca_crash_clears_check():
    """RED on the old code. A pointer checkout whose lint folder lacks layout.py. The Audit: spawn is let through (the
    crash fails open), so the flag must clear, and the next call must be allowed. The old code keeps the flag."""
    folder = ca_copy("nolayout", drop_layout=True)
    cfg = ca_config("nolayout-pointer", folder)
    flag, why = ca_owed(folder, cfg)
    if why:
        return False, why
    spawn = _decision(ca_call(folder, cfg, "Agent", CA_AUDIT))
    why = ov_want(spawn[0], spawn[1], "allow", "compaction-audit")
    if why:
        return False, "the valid Audit: spawn was not let through: %s" % why
    after = _decision(ca_call(folder, cfg, "Bash", CA_BASH))
    why = ov_want(after[0], after[1], "allow", "compaction-audit")
    if why:
        return False, ("after the Audit: spawn the audit flag stayed, so the next call is refused: %s. Crash: %s"
                       % (why, ca_crash_line(cfg)))
    if os.path.isfile(flag):
        return False, "the next call was allowed, but the audit flag file is still on disk"
    return True, "the Audit: spawn is let through, the flag clears and the next call is allowed"


def ca_control_check(name, drop_layout, pointer, label):
    """A green control: the Audit: spawn clears the flag and the next call is allowed, in a copy of the named shape."""
    folder = ca_copy(name, drop_layout=drop_layout)
    cfg = ca_config(name + "-cfg", folder if pointer else None)
    flag, why = ca_owed(folder, cfg)
    if why:
        return False, why
    spawn = _decision(ca_call(folder, cfg, "Agent", CA_AUDIT))
    why = ov_want(spawn[0], spawn[1], "allow", "compaction-audit")
    if why:
        return False, "control (%s): the Audit: spawn was not let through: %s" % (label, why)
    after = _decision(ca_call(folder, cfg, "Bash", CA_BASH))
    why = ov_want(after[0], after[1], "allow", "compaction-audit")
    if why:
        return False, "control (%s): the next call was refused after the Audit: spawn: %s" % (label, why)
    if os.path.isfile(flag):
        return False, "control (%s): the audit flag file is still on disk" % label
    return True, "control (%s): the Audit: spawn clears the flag and the next call is allowed" % label


def ca_refused_clears_nothing_check():
    """A spawn with no Audit: first line is refused by compaction-audit and clears nothing: the flag stays, and the
    next call is refused. Lint/layout.py is missing, so the crash path is present and must not weaken this refusal."""
    folder = ca_copy("nolayout", drop_layout=True)
    cfg = ca_config("nolayout-pointer-b", folder)
    flag, why = ca_owed(folder, cfg)
    if why:
        return False, why
    spawn = _decision(ca_call(folder, cfg, "Agent", CA_NOT_AUDIT))
    why = ov_want(spawn[0], spawn[1], "deny", "compaction-audit")
    if why:
        return False, "a spawn with no Audit: first line was not refused: %s" % why
    if not os.path.isfile(flag):
        return False, "a spawn with no Audit: first line cleared the audit flag"
    after = _decision(ca_call(folder, cfg, "Bash", CA_BASH))
    why = ov_want(after[0], after[1], "deny", "compaction-audit")
    if why:
        return False, "the call after a refused spawn was not refused: %s" % why
    return True, "a spawn with no Audit: first line is refused by compaction-audit and the flag stays"


def ca_later_refusal_check():
    """An Audit: spawn that a later rule refuses (a builder spawn with no Prior work line) clears nothing: the spawn did
    not run, so the flag stays and the next call is refused. Refusal on the intact copy, with no pointer checkout."""
    folder = ca_copy("intact", drop_layout=False)
    cfg = ca_config("intact-cfg", None)
    flag, why = ca_owed(folder, cfg)
    if why:
        return False, why
    spawn = _decision(ca_call(folder, cfg, "Agent", CA_BUILDER_AUDIT))
    why = ov_want(spawn[0], spawn[1], "deny", "spawn-searches-existing-builds")
    if why:
        return False, "the builder Audit: spawn was not refused by its later rule: %s" % why
    if not os.path.isfile(flag):
        return False, "a refused Audit: spawn cleared the audit flag"
    after = _decision(ca_call(folder, cfg, "Bash", CA_BASH))
    why = ov_want(after[0], after[1], "deny", "compaction-audit")
    if why:
        return False, "the call after a refused Audit: spawn was not refused: %s" % why
    return True, "an Audit: spawn that a later rule refuses clears nothing; the next call is refused"


# LOG_CHECKS_EXTRA joined at section 40805, so this section joins LOG_CHECKS directly, and sets each label's family
# on LOG_FAMILY (as sections 43400 and 43421 do).
CA_CHECKS = (
    ("compaction-audit: an Audit: spawn that a later rule's crash lets through clears the flag, so the next call is allowed",
     ca_crash_clears_check),
    ("compaction-audit: control, the same Audit: spawn with lint/layout.py present clears the flag",
     lambda: ca_control_check("intact", False, True, "layout present, pointer checkout")),
    ("compaction-audit: control, with no pointer checkout the Audit: spawn clears the flag with lint/layout.py missing",
     lambda: ca_control_check("nolayout-nopointer", True, False, "layout missing, no pointer")),
    ("compaction-audit: a spawn with no Audit: first line is refused and clears nothing, with lint/layout.py missing",
     ca_refused_clears_nothing_check),
    ("compaction-audit: an Audit: spawn that a later rule refuses clears nothing, and the next call is refused",
     ca_later_refusal_check),
)
LOG_CHECKS = LOG_CHECKS + CA_CHECKS
for _label, _check in CA_CHECKS:
    LOG_FAMILY[_label] = FAMILY

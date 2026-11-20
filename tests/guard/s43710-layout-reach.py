# section 43710
FAMILY = "layout-reach"
# guard_core.layout_module() finds lint/layout.py from the folder of guard_core.py: realpath(__file__)/../lint. An
# installed guard loads guard_core from its install's guard.d/<id> set (guard.py, _set_dir_for), so the lookup runs
# from that set and reaches guard.d/lint, which does not exist. A guard_core loaded from the hooks folder reaches the
# install's lint/. Every rule that reads lint/ through the layout then fails open in an installed guard.
LR_INSTALL = "20261119000000000001"   # a stand-in install id, stamped into the copies as INSTALL_ID
LR_CASE_SID = "5d1e8c4a-0000-4000-8000-00000000b0b2"
LR_AUDIT = {"description": "audit", "subagent_type": "Explore", "model": "sonnet",
            "prompt": "Audit: check the handoff against the repo."}
LR_PLACEHOLDER = '# INSTALL_ID = "uninstalled"'


def lr_install():
    """One install under ROOT, laid out as the installer lands it: installs/<id>/hooks with guard.py stamped, the
    guard.d/<id> set beside it (every module, stamped), and lint/ beside hooks/. Returns (install folder, '') or
    ('', why) when the stamp placeholder is missing from the repo's guard.py (a setup fault)."""
    base = os.path.join(ROOT, "layout-reach", "installs", LR_INSTALL)
    hooks = os.path.join(base, "hooks")
    install_line = 'INSTALL_ID = "%s"' % LR_INSTALL
    if not os.path.isfile(os.path.join(hooks, "guard.py")):
        modules = mutate_shared.module_files(os.path.dirname(GUARD))
        set_dir = os.path.join(hooks, "guard.d", LR_INSTALL)
        os.makedirs(set_dir, exist_ok=True)
        for path in modules:
            with open(path, encoding="utf-8") as handle:
                text = handle.read()
            stamped = text.replace(LR_PLACEHOLDER, install_line, 1)
            for folder in (hooks, set_dir):
                write(os.path.join(folder, os.path.basename(path)), stamped)
        if not os.path.isfile(os.path.join(hooks, "guard.py")) or install_line not in open(
                os.path.join(hooks, "guard.py"), encoding="utf-8").read():
            return "", "setup: the repo's guard.py has no `%s` line to stamp" % LR_PLACEHOLDER
        shutil.copytree(os.path.join(REPO, "lint"), os.path.join(base, "lint"),
                        ignore=shutil.ignore_patterns("__pycache__"))
    return base, ""


def lr_child(code, arg):
    """One python child, `code` with `arg` as its argv[1]. Its stdout is the verdict."""
    return subprocess.run([sys.executable, "-c", code, arg], capture_output=True, text=True, timeout=120,
                          env=dict(os.environ, CLAUDE_CONFIG_DIR=os.path.join(ROOT, "layout-reach", "cfg")))


LR_LAYOUT_PROBE = (
    "import sys\n"
    "sys.path.insert(0, sys.argv[1])\n"
    "try:\n"
    "    import guard_core\n"
    "    print(guard_core.layout_module().__name__)\n"
    "except Exception as e:\n"
    "    print('FAILED', type(e).__name__, e)\n")


def lr_guard_set_check():
    """RED on the old code. guard_core loaded from the install's guard.d set must reach lint/layout.py. It does not:
    the lookup runs from guard.d/<id>, so lint is searched at guard.d/lint."""
    base, why = lr_install()
    if why:
        return False, why
    out = lr_child(LR_LAYOUT_PROBE, os.path.join(base, "hooks", "guard.d", LR_INSTALL)).stdout.strip()
    if out != "layout":
        return False, ("layout_module, loaded from the install's guard.d set, cannot reach lint/layout.py: %s"
                       % out[:160])
    return True, "layout_module, loaded from the install's guard.d set, reaches lint/layout.py"


def lr_hooks_control_check():
    """A green control: guard_core loaded from the install's hooks folder reaches lint/layout.py, as the repo copy does."""
    base, why = lr_install()
    if why:
        return False, why
    out = lr_child(LR_LAYOUT_PROBE, os.path.join(base, "hooks")).stdout.strip()
    if out != "layout":
        return False, "control: layout_module, loaded from the hooks folder, did not reach lint/layout.py: %s" % out[:160]
    return True, "control: layout_module, loaded from the hooks folder, reaches lint/layout.py"


def lr_agent_brief_control_check():
    """A green control: agent_brief run from an installed hooks folder reads lint/ through its own path, so it prints no
    `note rules not read` line on stderr."""
    base, why = lr_install()
    if why:
        return False, why
    run = subprocess.run([sys.executable, os.path.join(base, "hooks", "agent_brief.py")],
                         input=json.dumps({"agent_type": "Explore", "cwd": NOGIT}), capture_output=True, text=True,
                         timeout=120, env=dict(os.environ, CLAUDE_CONFIG_DIR=os.path.join(ROOT, "layout-reach", "cfg")))
    if "note rules not read" in run.stderr:
        return False, "control: agent_brief from the installed hooks folder did not read lint/: %s" % run.stderr.strip()[:160]
    return True, "control: agent_brief from the installed hooks folder reads lint/, with no stderr line"


def lr_installed_audit_check():
    """RED on the old code, end to end. An installed guard with a pointer checkout: an Audit: spawn after compaction must
    clear the audit flag, so the next call is allowed. The lint lookup from guard.d fails in role_model_one, the spawn
    fails open, and the flag stays."""
    base, why = lr_install()
    if why:
        return False, why
    hooks = os.path.join(base, "hooks")
    cfg = os.path.join(ROOT, "layout-reach", "cfg-audit")
    write(os.path.join(cfg, "handoffs", LR_CASE_SID + ".md"), "# Handoff\n")
    write(os.path.join(cfg, "CLAUDE.md"), "@%s/CLAUDE.md\n" % base)   # the pointer checkout is the install folder
    env = dict(os.environ, CLAUDE_CONFIG_DIR=cfg, CLAUDE_GUARD_ROOT_PID=str(os.getpid()))
    for name in ("CLAUDE_CODE_REMOTE", "PYTHONPATH", "CLAUDE_CODE_SESSION_ID"):
        env.pop(name, None)
    handoff = os.path.join(cfg, "handoffs", LR_CASE_SID + ".md")

    def hook(mode, payload):
        return subprocess.run([sys.executable, os.path.join(hooks, "reread_check.py"), mode], input=json.dumps(payload),
                              capture_output=True, text=True, env=env, timeout=120)

    def call(tool, tool_input):
        payload = {"tool_name": tool, "tool_input": tool_input, "cwd": NOGIT, "session_id": LR_CASE_SID}
        return subprocess.run([sys.executable, os.path.join(hooks, "guard.py")], input=json.dumps(payload),
                              capture_output=True, text=True, env=env, timeout=120)

    hook("--post-compact", {"session_id": LR_CASE_SID})
    hook("--pre-read", {"session_id": LR_CASE_SID, "tool_name": "Read", "tool_input": {"file_path": handoff}})
    with hu_config(cfg):
        flag = ph.audit_flag_path(LR_CASE_SID)
    if not os.path.isfile(flag):
        return False, "setup: the audit flag was not set by PostCompact"
    spawn = _decision(call("Agent", LR_AUDIT))
    why = ov_want(spawn[0], spawn[1], "allow", "compaction-audit")
    if why:
        return False, "the valid Audit: spawn was not let through: %s" % why
    after = _decision(call("Bash", {"command": "echo hi"}))
    why = ov_want(after[0], after[1], "allow", "compaction-audit")
    if why:
        return False, ("after an Audit: spawn from the installed guard the audit flag stayed, so the next call is "
                       "refused: %s" % why)
    return True, "an Audit: spawn from the installed guard clears the flag, and the next call is allowed"


LR_CHECKS = (
    ("layout-reach: layout_module, loaded from the install's guard.d set, reaches lint/layout.py", lr_guard_set_check),
    ("layout-reach: an Audit: spawn from an installed guard clears the audit flag with a pointer checkout",
     lr_installed_audit_check),
    ("layout-reach: control, layout_module loaded from the install's hooks folder reaches lint/layout.py",
     lr_hooks_control_check),
    ("layout-reach: control, agent_brief from an installed hooks folder reads lint/ with no stderr line",
     lr_agent_brief_control_check),
)
LOG_CHECKS = LOG_CHECKS + LR_CHECKS
for _label, _check in LR_CHECKS:
    LOG_FAMILY[_label] = FAMILY

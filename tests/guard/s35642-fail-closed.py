# section 35642
FAMILY = "fail-closed"


def _guard_siblings(folder):
    """The guard_* modules in `folder`, by name: every guard_*.py, so a new module cannot be missed.
    Test files start with test_, so they are never listed. _guard_copy copies these and every other module in the folder."""
    return sorted(e[:-3] for e in os.listdir(folder) if e.startswith("guard_") and e.endswith(".py"))


FAILCLOSED_MODULES = tuple(_guard_siblings(os.path.dirname(GUARD)))
FAILCLOSED_REMEDY = ("install.sh", "install.ps1")
FAILCLOSED_CALL = "ls"                # harmless: a refusal can only come from the missing module
FAILCLOSED_CONTROL = "pkill -f node"  # an intact copy denies it, so its exit code is the deny's
FAILCLOSED_CHECKS = []

GUARD_CRASH = "guard-crash"           # the reason word of the wait-then-refuse refusal (decision install-hooks-whole)


def _guard_copy(name, drop):
    """A scratch folder with a copy of guard.py and every other module in its folder
    (mutate_shared.module_files), but for `drop`."""
    source = os.path.dirname(GUARD)
    folder = os.path.join(ROOT, "failclosed", name)
    os.makedirs(folder, exist_ok=True)
    for path in mutate_shared.module_files(source):
        if os.path.basename(path) not in ("guard.py", drop):
            shutil.copy(path, folder)
    shutil.copy(GUARD, os.path.join(folder, "guard.py"))
    return folder



def _copy_env(name, pythonpath=None):
    """The environment of one copy's run, with a config folder of its own. PYTHONPATH is unset unless
    `pythonpath` names a folder, so a case's sitecustomize.py is the one a run loads. No -I, so the script's
    own folder is on the path."""
    cfg = os.path.join(ROOT, "failclosed-cfg", name)
    os.makedirs(cfg, exist_ok=True)
    env = dict(os.environ)
    env.pop("CLAUDE_CODE_REMOTE", None)
    env.pop("PYTHONPATH", None)
    env.pop("CLAUDE_CODE_SESSION_ID", None)
    env["CLAUDE_CONFIG_DIR"] = cfg
    env["CLAUDE_GUARD_ROOT_PID"] = str(os.getpid())
    if pythonpath:
        env["PYTHONPATH"] = pythonpath
    return env


def _run_copy(folder, command, name, pythonpath=None):
    """One Bash call through the copy's guard.py, with a config folder of its own. The script's own folder
    is on the path, so the sibling imports resolve there."""
    payload = json.dumps({"tool_name": "Bash", "tool_input": {"command": command}, "cwd": NOGIT})
    return subprocess.run([sys.executable, os.path.join(folder, "guard.py")], input=payload,
                          capture_output=True, text=True, env=_copy_env(name, pythonpath), timeout=120)


def _decision(run):
    """(decision, reason) of one guard run. An empty stdout is an allow."""
    out = run.stdout.strip()
    if not out:
        return "allow", ""
    try:
        block = json.loads(out)["hookSpecificOutput"]
        return block["permissionDecision"], block["permissionDecisionReason"]
    except Exception:
        return "unparsable", out[:120]


def _intact_allows_a_plain_call():
    run = _run_copy(_guard_copy("intact-call", None), FAILCLOSED_CALL, "intact-call")
    decision, reason = _decision(run)
    if decision != "allow" or run.returncode != 0:
        return False, "an intact copy gave %r, exit %d: %r" % (decision, run.returncode, reason[:90])
    return True, "an intact copy allows the plain call, exit 0"


def fail_closed_case(module):
    """A copy with `module` deleted refuses a plain Bash call. The intact copy's deny for the control
    call sets the exit code the refusal must match, and the reason names the reinstall step and no
    file: not the module, not its folder, and no forbidden target."""
    drop = module + ".py"

    def check():
        if not os.path.exists(os.path.join(os.path.dirname(GUARD), drop)):
            return False, "%s is not beside guard.py, so the case cannot delete it" % drop
        control = _run_copy(_guard_copy(module + "-intact", None), FAILCLOSED_CONTROL,
                            module + "-intact")
        if _decision(control)[0] != "deny":
            return False, "the intact copy did not deny the control call: %r" % (_decision(control),)
        folder = _guard_copy(module, drop)
        run = _run_copy(folder, FAILCLOSED_CALL, module)
        decision, reason = _decision(run)
        if decision != "deny":   # one cause per message: a call that was not refused has no reason to judge
            return False, "the call is %r with %s missing, want deny" % (decision, drop)
        problems = []
        if run.returncode != control.returncode:
            problems.append("exit %d, the other denies exit %d" % (run.returncode, control.returncode))
        if not any(step in reason for step in FAILCLOSED_REMEDY):
            problems.append("the reason names no reinstall step: %r" % reason[:90])
        for leak in (drop, module, folder, slash(folder)):
            if leak in reason:
                problems.append("the reason names %r" % leak)
        named = names_the_target(reason)
        if named:
            problems.append("the reason names the forbidden target %r" % named)
        if problems:
            return False, "; ".join(problems)
        return True, "refused with exit %d; the reason names the reinstall step and no file" % (
            run.returncode)
    return check


# A refusal case for each sibling module on disk, one per module the guard loads.
for _module in FAILCLOSED_MODULES:
    _check = fail_closed_case(_module)
    FAILCLOSED_CHECKS.append(_check)
    LOG_CHECKS_EXTRA.append(("audit-high fail-closed: a copy missing %s refuses a Bash call"
                             % _module, _check))
# guard_core.py imports git_reads.py, which is no guard_* sibling, so FAILCLOSED_MODULES does not hold it.
_check = fail_closed_case("git_reads")
FAILCLOSED_CHECKS.append(_check)
LOG_CHECKS_EXTRA.append(("audit-high fail-closed: a copy missing git_reads refuses a Bash call", _check))

# guard_kill.py imports proc_env.py at its top level, for its session-tag read. proc_env.py is no guard_*
# sibling, so FAILCLOSED_MODULES does not hold it either. A copy without it refuses as guard-crash, never
# judges the call with the read missing (decision install-hooks-whole).
pr2015__check = fail_closed_case("proc_env")
FAILCLOSED_CHECKS.append(pr2015__check)
LOG_CHECKS_EXTRA.append(("install-hooks-whole fail-closed: a copy missing proc_env (guard_kill's session-tag read) "
                         "refuses a Bash call as guard-crash", pr2015__check))
for _label, _check in (
    ("audit-high fail-closed: an intact copy allows a plain Bash call", _intact_allows_a_plain_call),
):
    FAILCLOSED_CHECKS.append(_check)
    LOG_CHECKS_EXTRA.append((_label, _check))


# A Python without _ctypes fails `import ctypes`. proc_env.py imports ctypes inside its one read, not at the
# top (decision install-hooks-whole), so a copy that a no-_ctypes Python loads still judges a plain call.
# A top-level import there would refuse every call as guard-crash.
NO_CTYPES_SHIM = os.path.join(ROOT, "noctypes-shim")  # a folder whose sitecustomize.py drops ctypes
NO_CTYPES_SOURCE = "import sys\nsys.modules['ctypes'] = None\n"
NO_CTYPES_LABEL = "install-hooks-whole fail-closed: with ctypes blocked a copy loads and allows a plain Bash call"
NO_CTYPES_WINDOWS = "a Windows CPython always ships _ctypes, so the blocked import is a POSIX build case"


def no_ctypes_case():
    """With ctypes blocked in the guard's interpreter, a copy loads and judges a plain Bash call: allow, exit 0,
    never the guard-crash refusal. The shim's reach is probed first, so a shim that never blocks ctypes cannot
    pass. The control call must be denied by a rule, not by the crash path."""
    def check():
        write(os.path.join(NO_CTYPES_SHIM, "sitecustomize.py"), NO_CTYPES_SOURCE)
        probe = subprocess.run([sys.executable, "-c", "import ctypes"], capture_output=True, text=True,
                               env=_copy_env("no-ctypes-probe", NO_CTYPES_SHIM), timeout=120)
        if probe.returncode == 0 or not any(word in probe.stderr for word in ("ImportError", "ModuleNotFoundError")):
            return False, "the shim did not block ctypes in the guard's interpreter: exit %d, stderr %r" % (
                probe.returncode, probe.stderr[-90:])
        folder = _guard_copy("no-ctypes", None)
        run = _run_copy(folder, FAILCLOSED_CALL, "no-ctypes", pythonpath=NO_CTYPES_SHIM)
        decision, reason = _decision(run)
        if decision == "deny" and GUARD_CRASH in reason:
            return False, "refused as guard-crash: the copy did not load with ctypes blocked"
        if decision != "allow":
            return False, "with ctypes blocked the plain call is %r, want allow: %r" % (decision, reason[:90])
        if run.returncode != 0:
            return False, "with ctypes blocked the plain call exits %d, want 0" % run.returncode
        control = _run_copy(folder, FAILCLOSED_CONTROL, "no-ctypes-control", pythonpath=NO_CTYPES_SHIM)
        control_decision, control_reason = _decision(control)
        if control_decision != "deny" or GUARD_CRASH in control_reason:
            return False, "with ctypes blocked the control call is %r, want a rule's deny" % (
                (control_decision, control_reason[:90]),)
        return True, "with ctypes blocked the plain call is allowed, exit 0, and the control is denied by a rule"
    return check


if os.name == "nt":
    skip_case(NO_CTYPES_LABEL, NO_CTYPES_WINDOWS)
else:
    LOG_CHECKS_EXTRA.append((NO_CTYPES_LABEL, no_ctypes_case()))


def _guard_family_constant(path):
    """The module list the guard loads, ("guard_core",) + _FAMILY_MODULES, read from `path` with the
    language's own parser. Matching text would read a comment or a string as a module name."""
    with open(path, encoding="utf-8") as handle:
        tree = ast.parse(handle.read(), filename=path)
    for node in tree.body:
        if isinstance(node, ast.Assign) and any(
                isinstance(t, ast.Name) and t.id == "_FAMILY_MODULES" for t in node.targets):
            return ("guard_core",) + tuple(ast.literal_eval(node.value))
    raise ValueError("no _FAMILY_MODULES assignment in %s" % path)


def _list_names_every_sibling():
    """FAILCLOSED_MODULES must match the module list the guard itself loads, read from GUARD. A module
    the guard loads that the list omits, or a name the list holds that the guard never loads, goes red."""
    expected = _guard_family_constant(GUARD)
    if sorted(FAILCLOSED_MODULES) != sorted(expected):
        lacks = sorted(set(expected) - set(FAILCLOSED_MODULES))
        extra = sorted(set(FAILCLOSED_MODULES) - set(expected))
        return False, "the list lacks %s and holds extra %s against the guard's own constant" % (
            lacks, extra)
    return True, "the list matches the guard's own %d-module constant" % len(expected)


LOG_CHECKS_EXTRA.append(("audit-high fail-closed list: FAILCLOSED_MODULES matches the guard's own constant",
                         _list_names_every_sibling))


def _constant_drop_goes_red():
    """Drop guard_wsl from a copy of the guard's own module constant, the one the guard loads. The list
    check must go red on that copy. The copy is a scratch folder under ROOT, and GUARD is swapped only
    for the call, then restored."""
    global GUARD
    folder = _guard_copy("constant-drop", None)
    path = os.path.join(folder, "guard.py")
    with open(path, encoding="utf-8") as handle:
        text = handle.read()
    needle = '"guard_mask_script", "guard_wsl")'
    if text.count(needle) != 1:
        return False, "the guard's constant no longer reads %s once, so the drop cannot be made" % needle
    with open(path, "w", encoding="utf-8") as handle:
        handle.write(text.replace(needle, '"guard_mask_script")'))
    saved, GUARD = GUARD, path
    try:
        ok, note = _list_names_every_sibling()
    finally:
        GUARD = saved
    if ok:
        return False, "the list check stays green with guard_wsl dropped from the guard's constant"
    return True, "red on the copy with guard_wsl dropped: %s" % note


LOG_CHECKS_EXTRA.append(("audit-high fail-closed list: a guard constant without guard_wsl turns the list red",
                         _constant_drop_goes_red))


def _fake_sibling_is_picked_up():
    """The helper that builds FAILCLOSED_MODULES lists a new guard_* file and skips a test_* file. The
    fixture is a scratch folder under ROOT, never the hooks folder, and nothing in it is imported."""
    folder = os.path.join(ROOT, "failclosed-glob")
    os.makedirs(folder, exist_ok=True)
    for name in ("guard_zzfake.py", "test_guard_zzfake.py"):
        with open(os.path.join(folder, name), "w", encoding="utf-8") as handle:
            handle.write("# fixture only, never imported\n")
    got = _guard_siblings(folder)
    if got != ["guard_zzfake"]:
        return False, "the helper lists %r for a folder with one guard_ file and one test_ file" % (got,)
    return True, "the helper lists guard_zzfake and not test_guard_zzfake in a scratch folder"


LOG_CHECKS_EXTRA.append(("audit-high fail-closed list: a new guard_* file is picked up by the helper",
                         _fake_sibling_is_picked_up))


# --------------------------------------------------------------------------- reload-stamp
#
# Owner ruling 2026-10-14 (install-atomic, arbiter 03:41). The installer writes each hook file to a
# temp name and renames it into place, and stamps every installed hook file with one install-id
# constant. The guard compares the stamps of the modules it loads. On an import or load failure, or
# a stamp mismatch, it waits briefly and reloads. After the wait it refuses the call as guard-crash,
# and never allows it. Each case runs two ways. The damage is fixed during the wait, and the call is
# allowed. Or the damage stays, and the call is refused.
#
# The contract the cases hold the guard to: each hook file holds a module-level line
# INSTALL_ID = "<id>", and the cases put that line at the top of every copy, as an install does.
#
# Timing. The damage is fixed RELOAD_DELAY_S after the guard starts. The fix is one rename, so the
# guard reads the old damaged file or the whole new one, never half of one. A guard that does not
# wait finishes on its first load, well inside that delay, and so is caught refusing or allowing
# before the fix lands.


# ---- The install stamp. An installer swaps each module's exact placeholder line for INSTALL_ID = "<id>". Every
# module the guard loads must carry that line, or an installed copy leaves it unstamped, and the guard refuses every
# call as guard-crash (decision install-hooks-whole, the stamp check of guard.py).
PLACEHOLDER_LINE = '# INSTALL_ID = "uninstalled"'


def _every_loaded_module_carries_the_placeholder():
    """guard.py and each module of its load list hold the placeholder line, so an install stamps every one."""
    folder = os.path.dirname(GUARD)
    names = ("guard",) + _guard_family_constant(GUARD)
    bare = []
    for name in names:
        try:
            with open(os.path.join(folder, name + ".py"), encoding="utf-8") as handle:
                lines = [line.strip() for line in handle]
        except OSError:
            lines = []
        if PLACEHOLDER_LINE not in lines:
            bare.append(name)
    if bare:
        return False, "no placeholder line in %s: an installed copy leaves them unstamped" % ", ".join(sorted(bare))
    return True, "guard.py and the %d modules it loads each carry the placeholder line" % (len(names) - 1)


def _stamped_copy(name, install_id):
    """A copy of guard.py and its modules as an install lays them down: each exact placeholder line is swapped for
    INSTALL_ID = "<id>", and a file with no placeholder line is copied as it is."""
    folder = _guard_copy(name, None)
    for entry in sorted(os.listdir(folder)):
        if not entry.endswith(".py"):
            continue
        path = os.path.join(folder, entry)
        with open(path, encoding="utf-8") as handle:
            lines = handle.read().split("\n")
        lines = ['INSTALL_ID = "%s"' % install_id if line.strip() == PLACEHOLDER_LINE else line for line in lines]
        with open(path, "w", encoding="utf-8") as handle:
            handle.write("\n".join(lines))
    return folder


def stamped_install_check():
    """A stamped copy allows the plain call. Any module the stamp missed makes the guard refuse it as guard-crash."""
    run = _run_copy(_stamped_copy("stamped-install", "stampedtest"), FAILCLOSED_CALL, "stamped-install")
    decision, reason = _decision(run)
    if GUARD_CRASH in run.stdout:
        return False, "a stamped copy refuses the plain call as guard-crash: a module without the placeholder line stays unstamped"
    if decision != "allow" or run.returncode != 0:
        return False, "a stamped copy gave %r, exit %d: %r" % (decision, run.returncode, reason[:90])
    return True, "a stamped copy allows the plain call, exit 0"


LOG_CHECKS_EXTRA.append(("install-stamp: every module the guard loads carries the placeholder line",
                         _every_loaded_module_carries_the_placeholder))
LOG_CHECKS_EXTRA.append(("install-stamp: a stamped copy allows the plain call, not guard-crash",
                         stamped_install_check))

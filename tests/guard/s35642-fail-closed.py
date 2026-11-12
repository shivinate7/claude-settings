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


def _run_copy(folder, command, name):
    """One Bash call through the copy's guard.py, with a config folder of its own. No -I, and no
    PYTHONPATH, so the script's own folder is on the path and the sibling imports resolve there."""
    cfg = os.path.join(ROOT, "failclosed-cfg", name)
    os.makedirs(cfg, exist_ok=True)
    env = dict(os.environ)
    env.pop("CLAUDE_CODE_REMOTE", None)
    env.pop("PYTHONPATH", None)
    env.pop("CLAUDE_CODE_SESSION_ID", None)
    env["CLAUDE_CONFIG_DIR"] = cfg
    env["CLAUDE_GUARD_ROOT_PID"] = str(os.getpid())
    payload = json.dumps({"tool_name": "Bash", "tool_input": {"command": command}, "cwd": NOGIT})
    return subprocess.run([sys.executable, os.path.join(folder, "guard.py")], input=payload,
                          capture_output=True, text=True, env=env, timeout=120)


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
        problems = []
        if decision != "deny":
            problems.append("the call is %r with %s missing, want deny" % (decision, drop))
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
for _label, _check in (
    ("audit-high fail-closed: an intact copy allows a plain Bash call", _intact_allows_a_plain_call),
):
    FAILCLOSED_CHECKS.append(_check)
    LOG_CHECKS_EXTRA.append((_label, _check))


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

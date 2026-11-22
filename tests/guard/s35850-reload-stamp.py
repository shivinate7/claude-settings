# section 35850
FAMILY = "reload-stamp"
RELOAD_DELAY_S = 1.0
INSTALL_ID = "3f1a9c2e-5b7d-4e8f-9a0b-1c2d3e4f5a6b"
STALE_INSTALL_ID = "0d9e8f7a-6b5c-4d3e-8f2a-1b0c9d8e7f6a"
RELOAD_CORE = "guard_core.py"
RELOAD_CONTROL = []   # the intact copy's (decision, exit), read once, for the refusal's exit code


def _stamp_line(install_id):
    return 'INSTALL_ID = "%s"\n' % install_id


def _put_whole(path, text):
    """Writes a file the way the installer does: a temp name, then one rename over the old name."""
    temp = path + ".put-tmp"
    with open(temp, "w", encoding="utf-8", newline="\n") as handle:
        handle.write(text)
    os.replace(temp, path)


def _reload_copy_stamped(name, first_line_for):
    """A scratch folder with a copy of guard.py and every guard_* sibling. first_line_for(entry) is
    the line put at the top of that file, or None for a file with no INSTALL_ID line. Returns
    (folder, good): good maps each file name to the text an install leaves."""
    source = os.path.dirname(GUARD)
    folder = os.path.join(ROOT, "reload", name)
    shutil.rmtree(folder, ignore_errors=True)
    os.makedirs(folder)
    sources = [("guard.py", GUARD)] + [
        (entry, os.path.join(source, entry)) for entry in sorted(os.listdir(source))
        if entry.startswith("guard_") and entry.endswith(".py")]
    good = {}
    for entry, src in sources:
        with open(src, encoding="utf-8") as handle:
            good[entry] = (first_line_for(entry) or "") + handle.read()
        _put_whole(os.path.join(folder, entry), good[entry])
    for path in mutate_shared.module_files(source):  # shared_names.py, git_reads.py and the rest, unstamped
        if os.path.basename(path) not in good:
            shutil.copy(path, folder)
    return folder, good


def _reload_copy(name, install_id):
    """A scratch folder with a copy of guard.py and every guard_* sibling, each stamped with
    install_id. Returns (folder, good): good maps each file name to the text an install leaves."""
    return _reload_copy_stamped(name, lambda entry: _stamp_line(install_id))


def _truncated(text):
    """The first part of text that does not compile: a write cut short, not an empty file."""
    cut = len(text) // 2
    while cut < len(text):
        try:
            compile(text[:cut], RELOAD_CORE, "exec")
        except SyntaxError:
            return text[:cut]
        cut += 7
    raise RuntimeError("no cut of %s fails to compile" % RELOAD_CORE)


def _damage_truncated(folder, good):
    _put_whole(os.path.join(folder, RELOAD_CORE), _truncated(good[RELOAD_CORE]))
    return [RELOAD_CORE]


def _damage_stamp(folder, good):
    stale = good[RELOAD_CORE].replace(_stamp_line(INSTALL_ID), _stamp_line(STALE_INSTALL_ID), 1)
    _put_whole(os.path.join(folder, RELOAD_CORE), stale)
    return [RELOAD_CORE]


def _fix_with(folder, good, names):
    """The fix: each named file put back whole, the way the installer puts it."""
    def fix():
        for entry in names:
            _put_whole(os.path.join(folder, entry), good[entry])
    return fix



def _reload_cfg(name):
    """The CLAUDE_CONFIG_DIR of the copy `name`: one folder each."""
    return os.path.join(ROOT, "reload-cfg", name)


def _reload_run(folder, name, fix=None, command=None, delay=RELOAD_DELAY_S, session=None):
    """One Bash call through the copy's guard.py. fix, when given, runs once, delay seconds after the
    guard starts. session, when given, is the payload's session_id. Returns (run, fixed): fixed is True
    when fix ran, which is before the guard ended only if the guard waited."""
    cfg = _reload_cfg(name)
    os.makedirs(cfg, exist_ok=True)
    env = dict(os.environ)
    env.pop("CLAUDE_CODE_REMOTE", None)
    env.pop("PYTHONPATH", None)
    env.pop("CLAUDE_CODE_SESSION_ID", None)
    env["CLAUDE_CONFIG_DIR"] = cfg
    env["CLAUDE_GUARD_ROOT_PID"] = str(os.getpid())
    body = {"tool_name": "Bash", "tool_input": {"command": command or FAILCLOSED_CALL}, "cwd": NOGIT}
    if session:
        body["session_id"] = session
    payload = json.dumps(body)
    fixed = threading.Event()

    def land():
        fix()
        fixed.set()
    timer = threading.Timer(delay, land) if fix else None
    if timer:
        timer.daemon = True
        timer.start()
    try:
        run = subprocess.run([sys.executable, os.path.join(folder, "guard.py")], input=payload,
                             capture_output=True, text=True, env=env, timeout=120)
    finally:
        if timer:
            timer.cancel()
            timer.join()
    return run, fixed.is_set()


def _reload_control():
    """(decision, exit) of an intact copy's deny. A refusal from a damaged copy must match it."""
    if not RELOAD_CONTROL:
        folder, _good = _reload_copy("control", INSTALL_ID)
        run, _fixed = _reload_run(folder, "control", command=FAILCLOSED_CONTROL)
        RELOAD_CONTROL.append((_decision(run)[0], run.returncode))
    return RELOAD_CONTROL[0]


def reload_fixed_case(name, damage):
    """The damage is fixed during the wait. The guard waits, reloads the whole file, and allows."""
    def check():
        folder, good = _reload_copy(name, INSTALL_ID)
        names = damage(folder, good)
        run, fixed = _reload_run(folder, name, _fix_with(folder, good, names))
        decision, reason = _decision(run)
        if not fixed:
            return False, ("the guard finished with %r before the fix landed, so it never waited "
                           "to reload: %r" % (decision, reason[:90]))
        if decision != "allow" or run.returncode != 0:
            return False, ("the damage was fixed during the wait, but the call is %r, exit %d, "
                           "want allow: %r" % (decision, run.returncode, reason[:90]))
        return True, "waited, reloaded the whole file, and allowed the call, exit 0"
    return check


def reload_stuck_case(name, damage):
    """The damage stays. The guard waits, then refuses as guard-crash with the intact copy's exit
    code. It never allows the call."""
    def check():
        folder, good = _reload_copy(name, INSTALL_ID)
        damage(folder, good)
        run, _fixed = _reload_run(folder, name)
        decision, reason = _decision(run)
        control_decision, control_exit = _reload_control()
        problems = []
        if control_decision != "deny":
            problems.append("the intact copy did not deny the control call: %r" % control_decision)
        if decision != "deny":
            problems.append("the call is %r with the damage never fixed, want deny" % decision)
        if "guard-crash" not in reason:
            problems.append("the reason is not guard-crash: %r" % reason[:90])
        if run.returncode != control_exit:
            problems.append("exit %d, the intact copy's deny exits %d" % (run.returncode, control_exit))
        if problems:
            return False, "; ".join(problems)
        return True, "refused as guard-crash with exit %d, and never allowed" % run.returncode
    return check


RELOAD_CHECKS = (
    ("reload-stamp: a truncated guard_core.py fixed during the wait is reloaded, and the call allowed",
     reload_fixed_case("truncated-fixed", _damage_truncated)),
    ("reload-stamp: a truncated guard_core.py never fixed is refused as guard-crash, never allowed",
     reload_stuck_case("truncated-stuck", _damage_truncated)),
    ("reload-stamp: a stamp mismatch fixed during the wait is reloaded, and the call allowed",
     reload_fixed_case("stamp-fixed", _damage_stamp)),
    ("reload-stamp: a stamp mismatch never fixed is refused as guard-crash, never allowed",
     reload_stuck_case("stamp-stuck", _damage_stamp)),
)
for _label, _check in RELOAD_CHECKS:
    LOG_CHECKS_EXTRA.append((_label, _check))



# A flat module (no INSTALL_ID line) is an older copy, or missing, when the guard first loads it. Its whole file
# lands LATE_LAND_S after the guard starts, and the guard waits and reloads. A module that loaded stays in
# sys.modules until the retry pops it, so each case needs its module popped: reread_check and proc_env cache
# an older copy, and precompact_handoff caches an older copy that reread_check reuses on the retry.
LATE_LAND_S = 1.5


def _source_text(module):
    with open(os.path.join(os.path.dirname(GUARD), module), encoding="utf-8") as handle:
        return handle.read()


def late_land_case(module, older_text):
    """`module` is in the copy as older_text, or missing for None. Its source file lands whole LATE_LAND_S
    after the guard starts. The guard waits, reloads it, and allows the call."""
    def check():
        name = "late-" + module[:-3]
        folder, _good = _reload_copy(name, INSTALL_ID)
        target = os.path.join(folder, module)
        if older_text is None:
            os.remove(target)
        else:
            _put_whole(target, older_text)
        run, fixed = _reload_run(folder, name, _fix_with(folder, {module: _source_text(module)}, [module]),
                                 delay=LATE_LAND_S)
        decision, reason = _decision(run)
        if not fixed:
            return False, ("the guard finished with %r before %s landed, so it never waited to reload: %r"
                           % (decision, module, reason[:90]))
        if decision != "allow" or run.returncode != 0:
            return False, ("%s landed late, but the call is %r, exit %d, want allow: %r"
                           % (module, decision, run.returncode, reason[:90]))
        return True, "%s landed late, the guard waited and reloaded it, and the call is allowed, exit 0" % module
    return check


def late_land_stale_ph_case():
    """A stale precompact_handoff loads first and stays in sys.modules until the retry pops it. guard_core
    carries a stale stamp, so the first load fails the install-id check, after reread_check has imported
    precompact_handoff. Both fresh files land LATE_LAND_S after the guard starts, precompact_handoff first.
    The reload must read the fresh one: a session with the re-read flag set is refused handoff-unread. The
    stale copy names its flag file elsewhere, so reused, it finds no flag and the call is allowed."""
    def check():
        name = "late-stale-ph"
        fresh = _source_text("precompact_handoff.py")
        stale = fresh.replace('"%s.reread"', '"%s.reread-old"', 1)
        if stale == fresh:
            raise RuntimeError("precompact_handoff.py has no flag path literal to age")
        # Control first: an intact copy with the flag set refuses, so the miss below is the stale copy's.
        control = name + "-control"
        control_folder, _good = _reload_copy(control, INSTALL_ID)
        hu_files(_reload_cfg(control), flag=True, handoff=True)
        control_run, _fixed = _reload_run(control_folder, control, session=HU_SID)
        control_decision, control_reason = _decision(control_run)
        if control_decision != "deny" or "(handoff unread)" not in control_reason \
                or hu_paths(_reload_cfg(control), HU_SID)[0] not in control_reason:
            return False, ("control: an intact copy with the flag set is %r, want deny naming the handoff: %r"
                           % (control_decision, control_reason[:90]))
        folder, good = _reload_copy(name, INSTALL_ID)
        _put_whole(os.path.join(folder, "precompact_handoff.py"), stale)
        _damage_stamp(folder, good)   # glossary-ok: the INSTALL_ID stamp of guard_core, not a Verified line. Its stamp is stale: the first load fails the install-id check
        fix = _fix_with(folder, {"precompact_handoff.py": fresh, RELOAD_CORE: good[RELOAD_CORE]},
                        ["precompact_handoff.py", RELOAD_CORE])   # ph first, so a reload that sees matching ids sees fresh ph
        hu_files(_reload_cfg(name), flag=True, handoff=True)
        run, fixed = _reload_run(folder, name, fix, session=HU_SID, delay=LATE_LAND_S)
        decision, reason = _decision(run)
        if not fixed:
            return False, ("the guard finished with %r before precompact_handoff landed, so it never waited to reload: %r"
                           % (decision, reason[:90]))
        if decision != "deny" or "(handoff unread)" not in reason:
            return False, ("after the reload the flagged call is %r, want deny: the stale precompact_handoff was reused"
                           % decision)
        return True, ("precompact_handoff landed late, the guard reloaded the fresh one, and the flagged call "
                      "is refused handoff-unread")
    return check


LATE_LAND_CHECKS = (
    ("late-land: reread_check.py, an older copy with no ph name, lands late: the call is allowed",
     late_land_case("reread_check.py", '"""An older copy: no ph name yet."""\n')),
    ("late-land: precompact_handoff.py missing until it lands late: reread_check reloads ph, the call is allowed",
     late_land_case("precompact_handoff.py", None)),
    ("late-land: proc_env.py, an older copy with no holds_session_tag name, lands late: the call is allowed",
     late_land_case("proc_env.py", '"""An older copy: no holds_session_tag name yet."""\n')),
    ("late-land: a stale precompact_handoff loads first, the reload picks up the fresh one: a flagged call is refused",
     late_land_stale_ph_case()),
)
for _label, pr2015__check in LATE_LAND_CHECKS:
    LOG_CHECKS_EXTRA.append((_label, pr2015__check))
    FIXTURELESS_CHECKS.add(pr2015__check)  # builds only its copy and reads no lazy fixture


def reload_crash_stamp_case():
    """reload-stamp: when guard_core stays broken, guard.py's fallback writer logs one guard-crash line, and
    its time (field 0) carries the colon UTC offset. The run is reload_stuck_case's run, with no fix."""
    name = "crash-stamp"
    folder, good = _reload_copy(name, INSTALL_ID)
    _damage_truncated(folder, good)
    cfg = os.path.join(ROOT, "reload-cfg", name)
    shutil.rmtree(cfg, ignore_errors=True)
    run, _fixed = _reload_run(folder, name)
    path = os.path.join(cfg, "guard.log")
    if not os.path.exists(path):
        return False, "the broken guard wrote no guard.log line (exit %d)" % run.returncode
    with open(path, encoding="utf-8") as handle:
        rows = [line.split("\t") for line in handle.read().splitlines() if line.strip()]
    crash = [fields for fields in rows if len(fields) > 3 and fields[2:4] == ["crash", "guard-crash"]]
    if len(crash) != 1:
        return False, "want one crash guard-crash line, found %d in %r" % (len(crash), rows)
    return _stamp_verdict(crash[0][0])


LOG_CHECKS_EXTRA.append(("reload-stamp: the fallback writer's crash line carries the colon UTC offset",
                         reload_crash_stamp_case))
# guard.py stamped and guard_core.py with no INSTALL_ID line at all is a mixed set, not a match: the
# guard must wait and reload it like any other mismatch, and refuse it when it never clears. The
# repo's own set, every file on the commented placeholder, is a match, and is allowed at once.
def _damage_core_unstamped(folder, good):
    """guard_core.py loses its INSTALL_ID line and keeps the rest. guard.py keeps its id."""
    _put_whole(os.path.join(folder, RELOAD_CORE), good[RELOAD_CORE].split("\n", 1)[1])
    return [RELOAD_CORE]


def reload_placeholder_case():
    """Every file carries the commented placeholder, as the repo does. The guard must match, and
    allow the call with no wait."""
    def check():
        folder, _good = _reload_copy_stamped("placeholder-set", lambda entry: '# INSTALL_ID = "uninstalled"\n')
        run, _fixed = _reload_run(folder, "placeholder-set")
        decision, reason = _decision(run)
        if decision != "allow" or run.returncode != 0:
            return False, "an all-placeholder set is %r, exit %d, want allow: %r" % (
                decision, run.returncode, reason[:90])
        return True, "an all-placeholder set matches, and the call is allowed, exit 0"
    return check


RELOAD_STAMP_CHECKS = (
    ("reload-stamp: guard.py stamped and guard_core.py with no INSTALL_ID line, fixed during the wait: reloaded and allowed",
     reload_fixed_case("nostamp-fixed", _damage_core_unstamped)),
    ("reload-stamp: guard.py stamped and guard_core.py with no INSTALL_ID line, never fixed: refused as guard-crash, never allowed",
     reload_stuck_case("nostamp-stuck", _damage_core_unstamped)),
    ("reload-stamp: an all-placeholder set (the repo run) matches, and the call is allowed",
     reload_placeholder_case()),
)
for _label, _check in RELOAD_STAMP_CHECKS:
    LOG_CHECKS_EXTRA.append((_label, _check))

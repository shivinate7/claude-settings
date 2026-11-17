# section 37949
FAMILY = "handoff-unread"
HU_RULE = "handoff-unread"
HU_SID = "3c6e1f2a-0000-4000-8000-00000000c0de"   # the main session in these cases
HU_AGENT = "a7f3c9e10b2d4e58"                     # an agent's id on the payload
HU_TEXT = "# Handoff\n"
READ_CHECK = os.environ.get("READ_CHECK_UNDER_TEST") or os.path.join(HERE, "reread_check.py")
HU_BOTH = os.path.join(ROOT, "hu-both")                  # the flag is set and the handoff is present
HU_FLAG_ONLY = os.path.join(ROOT, "hu-flag-only")        # the flag is set and the handoff is missing
HU_HANDOFF_ONLY = os.path.join(ROOT, "hu-handoff-only")  # the handoff is present and the flag is absent


@contextlib.contextmanager
def hu_config(config):
    """CLAUDE_CONFIG_DIR is `config` for the block, as the guard and the hooks read it."""
    saved = os.environ.get("CLAUDE_CONFIG_DIR")
    os.environ["CLAUDE_CONFIG_DIR"] = config
    try:
        yield
    finally:
        if saved is None:
            os.environ.pop("CLAUDE_CONFIG_DIR", None)
        else:
            os.environ["CLAUDE_CONFIG_DIR"] = saved


def hu_paths(config, session):
    """(handoff, flag) under `config`, from precompact_handoff, the one home of both paths."""
    with hu_config(config):
        return ph.handoff_path(session), ph.reread_flag_path(session)


def hu_files(config, flag, handoff):
    """Write the flag and the handoff under `config`, or leave out whichever is False."""
    handoff_file, flag_file = hu_paths(config, HU_SID)
    if handoff:
        write(handoff_file, HU_TEXT)
    if flag:
        write(flag_file, "1")


def _build_hu_both():
    hu_files(HU_BOTH, flag=True, handoff=True)


def _build_hu_flag_only():
    hu_files(HU_FLAG_ONLY, flag=True, handoff=False)


def _build_hu_handoff_only():
    hu_files(HU_HANDOFF_ONLY, flag=False, handoff=True)


lazy_fixture([HU_BOTH], _build_hu_both)
lazy_fixture([HU_FLAG_ONLY], _build_hu_flag_only)
lazy_fixture([HU_HANDOFF_ONLY], _build_hu_handoff_only)
HU_HANDOFF, HU_FLAG = hu_paths(HU_BOTH, HU_SID)

# The refusal names the handoff and says to Read it, for each tool the guard judges. The handoff check
# runs before every other rule, so each refusal below is this rule's.
for _tool, _input in (
        ("Bash", {"command": "echo hi"}),
        ("Edit", {"file_path": os.path.join(NOGIT, "notes.md"), "old_string": "a", "new_string": "b"}),
        ("Write", {"file_path": os.path.join(NOGIT, "notes.md"), "content": "x"}),
        ("Agent", {"description": "look", "prompt": "read the repo"})):
    add("handoff-unread: after compaction, %s is refused while the handoff is unread" % _tool,
        "deny", HU_RULE, tool=_tool, cwd=NOGIT, session=HU_SID, config=HU_BOTH,
        carries=((HU_HANDOFF, slash(HU_HANDOFF)), "Read"), **_input)
add("handoff-unread: a payload that carries agent_id is allowed while the handoff is unread",
    "allow", cwd=NOGIT, session=HU_SID, config=HU_BOTH, agent_id=HU_AGENT, silent=True, command="echo hi")
add("handoff-unread: a call is allowed when the flag is absent, though the handoff is present",
    "allow", cwd=NOGIT, session=HU_SID, config=HU_HANDOFF_ONLY, silent=True, command="echo hi")
add("handoff-unread: a call is allowed when the flag is set and the handoff is missing",
    "allow", cwd=NOGIT, session=HU_SID, config=HU_FLAG_ONLY, silent=True, command="echo hi")


def hu_call(tool, tool_input, config, session, agent_id=None):
    """One guard call, built as decide() builds a case: the config folder, the session and the payload."""
    return decide({"raw": None, "tool": tool, "tool_input": tool_input, "cwd": NOGIT,
                   "session": session, "env_path": None, "config": config, "agent_id": agent_id})


def hu_hook(mode, payload, config):
    """One run of hooks/reread_check.py in `mode`, with `config` as its config folder."""
    env = dict(os.environ)
    env.pop("CLAUDE_CODE_SESSION_ID", None)
    env["CLAUDE_CONFIG_DIR"] = config
    return subprocess.run([sys.executable, READ_CHECK, mode], input=json.dumps(payload),
                          capture_output=True, text=True, env=env, timeout=120)


def hu_cycle_check():
    """PostCompact sets the flag, the guard refuses a Bash call, a Read of the handoff clears the flag,
    the handoff audit's Audit: spawn clears the audit flag that PostCompact also set, and the same Bash
    call is then allowed."""
    cfg = os.path.join(ROOT, "hu-cycle")
    handoff, flag = hu_paths(cfg, HU_SID)
    write(handoff, HU_TEXT)
    post = hu_hook("--post-compact", {"session_id": HU_SID}, cfg)
    if post.returncode != 0 or not os.path.isfile(flag):
        return False, "PostCompact did not set the flag (exit %d)" % post.returncode
    bash = {"command": "echo hi"}
    audit = {"description": "audit", "subagent_type": "Explore", "model": "sonnet",
             "prompt": "Audit: check the handoff against the repo."}
    ok, why = ov_story([("after compaction, before the read",
                         lambda: hu_call("Bash", bash, cfg, HU_SID), "deny", HU_RULE)])
    if not ok:
        return False, why
    read = hu_hook("--pre-read", {"session_id": HU_SID, "tool_name": "Read",
                                  "tool_input": {"file_path": handoff}}, cfg)
    if read.returncode != 0 or os.path.isfile(flag):
        return False, "a Read of the handoff left the flag set (exit %d)" % read.returncode
    ok, why = ov_story([("after the read, the Audit: spawn",
                         lambda: hu_call("Agent", audit, cfg, HU_SID), "allow", None)])
    if not ok:
        return False, why
    ok, why = ov_story([("after the Audit: spawn", lambda: hu_call("Bash", bash, cfg, HU_SID), "allow", None)])
    if not ok:
        return False, why
    return True, "PostCompact sets the flag, Bash is refused, a Read of the handoff clears it, Bash is allowed"


def hu_cost_check():
    """With the flag absent, unread_handoff makes one existence check, on the flag. It writes nothing and
    starts no process. Every existence check and write is counted in-process, around the one call."""
    import builtins
    try:
        mod = _hu_reread()
    except (Exception, SystemExit) as e:
        return False, "reread_check does not load: %s" % e
    cfg = os.path.join(ROOT, "hu-cost")
    handoff, flag = hu_paths(cfg, HU_SID)
    write(handoff, HU_TEXT)   # the handoff is present, so only the flag can decide the answer
    seen = {"exists": [], "writes": [], "starts": []}
    real_open = builtins.open
    real_popen = subprocess.Popen

    def counting(bucket, name, real):
        def wrapper(*args, **kwargs):
            seen[bucket].append((name, args[0] if args else None))
            return real(*args, **kwargs)
        return wrapper

    def counted_open(file, mode="r", *args, **kwargs):
        if any(c in str(mode) for c in "wax+"):
            seen["writes"].append(("open", (file, mode)))
        return real_open(file, mode, *args, **kwargs)

    class CountingPopen(real_popen):
        def __init__(self, *args, **kwargs):
            seen["starts"].append(args[0] if args else None)
            super().__init__(*args, **kwargs)

    patches =[(os.path, n, counting("exists", "os.path." + n, getattr(os.path, n)))
               for n in ("isfile", "exists", "lexists", "isdir")]
    patches += [(os, n, counting("writes", "os." + n, getattr(os, n)))
                for n in ("remove", "unlink", "rename", "replace", "makedirs", "mkdir", "rmdir", "utime")]
    saved = [(owner, name, getattr(owner, name)) for owner, name, _ in patches]
    try:
        for owner, name, replacement in patches:
            setattr(owner, name, replacement)
        builtins.open = counted_open
        subprocess.Popen = CountingPopen
        with hu_config(cfg):
            result = mod.unread_handoff({"session_id": HU_SID})
    except Exception as e:
        return False, "unread_handoff raised %s" % e
    finally:
        for owner, name, real in saved:
            setattr(owner, name, real)
        builtins.open = real_open
        subprocess.Popen = real_popen
    if result != "":
        return False, "unread_handoff gave %r with the flag absent, want an empty string" % (result,)
    checks = seen["exists"]
    if len(checks) != 1:
        return False, "%d existence checks, want exactly 1: %r" % (len(checks), [c[0] for c in checks])
    name, target = checks[0]
    if os.path.normcase(os.path.normpath(str(target))) != os.path.normcase(os.path.normpath(flag)):
        return False, "the one check was %s on %r, not the flag" % (name, target)
    if seen["writes"] or seen["starts"]:
        return False, "%d writes and %d process starts, want none: %r" % (
            len(seen["writes"]), len(seen["starts"]), seen["writes"] or seen["starts"])
    return True, "one existence check (%s) on the flag, no write, no process start" % name


def hu_copy_check():
    """With reread_check.py missing beside guard.py, the guard fails open: a call that an intact copy refuses
    for the unread handoff is allowed. The intact copy is the control, so the fixture is shown to bite.
    `echo hi` is allowed by every rule, so a copy that crashes and allows everything passes it too. So the
    dropped copy must also refuse a call another rule denies: an Agent spawn on Haiku, which the model floor refuses."""
    cfg = os.path.join(ROOT, "hu-copy")
    hu_files(cfg, flag=True, handoff=True)
    intact = _guard_copy("hu-intact", None)
    dropped = _guard_copy("hu-no-reread", "reread_check.py")
    control = _hu_copy_run(intact, cfg)
    why = ov_want(*_decision(control), "deny", HU_RULE)
    if why:
        return False, "the intact copy, the control: %s" % why
    run = _hu_copy_run(dropped, cfg)
    decision, reason = _decision(run)
    if run.returncode != 0 or decision != "allow" or reason:
        return False, "without reread_check.py the call is %r (exit %d), want a silent allow" % (
            decision, run.returncode)
    spawn = _hu_copy_run(dropped, cfg, "Agent", {"prompt": "do it", "model": "haiku"})
    why = ov_want(*_decision(spawn), "deny", "agent-model-floor")
    if why:
        return False, "without reread_check.py a Haiku spawn is not refused: %s (exit %d)" % (
            why, spawn.returncode)
    return True, ("reread_check.py missing: the call is allowed, exit 0, and a Haiku spawn is refused by the "
                  "model floor; the intact copy refuses the call")


def _hu_copy_run(folder, config, tool="Bash", tool_input=None):
    """One call through a copy's guard.py, with `config` as its config folder and the session on the payload.
    The call is `echo hi` in Bash unless `tool` and `tool_input` name another call."""
    if tool_input is None:
        tool_input = {"command": "echo hi"}
    env = dict(os.environ)
    env.pop("CLAUDE_CODE_REMOTE", None)
    env.pop("PYTHONPATH", None)
    env.pop("CLAUDE_CODE_SESSION_ID", None)
    env["CLAUDE_CONFIG_DIR"] = config
    env["CLAUDE_GUARD_ROOT_PID"] = str(os.getpid())
    payload = json.dumps({"tool_name": tool, "tool_input": tool_input, "cwd": NOGIT,
                          "session_id": HU_SID})
    return subprocess.run([sys.executable, os.path.join(folder, "guard.py")], input=payload,
                          capture_output=True, text=True, env=env, timeout=120)


def hu_override_check():
    """An owner override lifts the unread-handoff refusal once, then the refusal stands again. The rule is
    not in never_lifted, so an override reaches it."""
    config = ov_config("handoff-unread-once")
    hu_files(config, flag=True, handoff=True)
    bash = {"command": "echo hi"}

    def call(seconds):
        return lambda: ov_call("Bash", bash, NOGIT, config, HU_SID, seconds)

    ok, why = ov_story([("with no override", call(0), "deny", HU_RULE)])
    if not ok:
        return False, why
    note = ov_type(config, HU_SID, "override")
    ok, why = ov_story([("first call", call(60), "allow", None),
                        ("second call, override spent", call(120), "deny", HU_RULE)], note)
    if not ok:
        return False, why
    return True, "refused with no override, allowed once after `override`, then refused again"


def _hu_reread():
    """hooks/reread_check.py loaded as a module of its own, from READ_CHECK."""
    import importlib.util
    spec = importlib.util.spec_from_file_location("reread_check_under_test", READ_CHECK)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _hu_unread(mod, config, payload):
    with hu_config(config):
        return mod.unread_handoff(payload)


def hu_contract_check():
    """unread_handoff returns the handoff path only for a non-empty str session id, with no agent_id, the
    flag set and the handoff present. Every other payload gives '' and never raises."""
    for config in (HU_BOTH, HU_FLAG_ONLY, HU_HANDOFF_ONLY):
        materialize(config)
    try:
        mod = _hu_reread()
    except (Exception, SystemExit) as e:
        return False, "reread_check does not load: %s" % e
    rows = (
        ("the flag set and the handoff present", HU_BOTH, {"session_id": HU_SID}, HU_HANDOFF),
        ("an agent_id on the payload", HU_BOTH, {"session_id": HU_SID, "agent_id": HU_AGENT}, ""),
        ("the flag absent", HU_HANDOFF_ONLY, {"session_id": HU_SID}, ""),
        ("the handoff missing", HU_FLAG_ONLY, {"session_id": HU_SID}, ""),
    )
    bad = (None, [], "text", {}, {"session_id": None}, {"session_id": ""}, {"session_id": 7},
           {"session_id": ["a"]})
    problems = []
    for label, config, payload, want in rows:
        try:
            got = _hu_unread(mod, config, payload)
        except Exception as e:
            problems.append("%s raised %s" % (label, e))
            continue
        if got != want:
            problems.append("%s gave %r, want %r" % (label, got, want))
    for payload in bad:
        try:
            got = _hu_unread(mod, HU_BOTH, payload)
        except Exception as e:
            problems.append("payload %r raised %s" % (payload, e))
            continue
        if got != "":
            problems.append("payload %r gave %r, want an empty string" % (payload, got))
    if problems:
        return False, "; ".join(problems[:3])
    return True, "the path comes back only when every condition holds; a bad payload gives '' and never raises"


def hu_import_check():
    """Importing reread_check never ends the process, even when its sibling precompact_handoff cannot
    import. The copy stands alone in its folder, so the sibling import fails."""
    folder = os.path.join(ROOT, "hu-import")
    os.makedirs(folder, exist_ok=True)
    shutil.copy(READ_CHECK, os.path.join(folder, "reread_check.py"))
    code = ("import sys\n"
            "sys.path.insert(0, sys.argv[1])\n"
            "import reread_check\n"
            "print('imported')\n")
    run = subprocess.run([sys.executable, "-I", "-c", code, folder], capture_output=True, text=True,
                         timeout=120)
    if run.returncode != 0 or "imported" not in run.stdout:
        return False, "exit %d, stdout %r: the import ended the process before the next line" % (
            run.returncode, run.stdout.strip()[:60])
    return True, "reread_check imports with no sibling precompact_handoff, and the process goes on"


for _label, _check in (
    ("handoff-unread: PostCompact sets the flag, Bash is refused, a Read of the handoff clears it, Bash is allowed",
     hu_cycle_check),
    ("handoff-unread: unread_handoff makes one existence check, on the flag, with no write or process start",
     hu_cost_check),
    ("handoff-unread: a guard copy without reread_check.py fails open, and the intact copy refuses",
     hu_copy_check),
    ("handoff-unread: an owner override lifts the refusal once, and the spent override refuses again",
     hu_override_check),
    ("handoff-unread: unread_handoff returns the path only when every condition holds, and never raises",
     hu_contract_check),
    ("handoff-unread: importing reread_check does not end the process when precompact_handoff cannot import",
     hu_import_check),
):
    LOG_CHECKS_EXTRA.append((_label, _check))


# =========================================================================== handoff-sections
# A write that leaves a session's handoff without a section that the prompt's step 4 marker names is refused,
# and the reason names the missing sections. The marker is read at run time from the installed prompt (the
# config folder's hooks/precompact_handoff_prompt.md). No code copies its list: a name the marker adds is
# required, and a name it drops is not. The rule fails open: a prompt with no marker, or one that cannot be
# read, refuses nothing. Cost: a call it allows writes no file and starts no process; a refusal writes its
# guard.log line and nothing else.

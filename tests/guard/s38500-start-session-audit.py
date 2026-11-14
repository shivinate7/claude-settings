# section 38500
FAMILY = "start-session-audit"
# ---- The start-session audit (roadmap step start-session-not-pretooluse). settings.json does not route start_session to
# PreToolUse: a PreToolUse matcher that covers it makes the desktop app show the "Allow Claude to start the session?"
# card on every start, even in Bypass (anthropics/claude-code#103832). The start checks run after the call instead.
# The one PostToolUse command that settings.json names for start_session runs the floor (guard.floor_hit) and the
# handoff-unread read. A bad start prints PostToolUse additionalContext that tells the calling session to stop the new
# session with interrupt_session or archive_session. A start that passes prints nothing.
# Each case runs the hook file that command names, as the harness runs it: the payload on stdin, the config folder in
# CLAUDE_CONFIG_DIR. A case first reads the wiring, so a missing audit fails on that named cause, never on a crash.

AUDIT_TOOL = "mcp__ccd_session__start_session"
AUDIT_STOP_LINE = ("interrupt_session", "archive_session")
AUDIT_SETTINGS = os.path.join(REPO, "settings.json")


def post_tool_covers(matcher, tool):
    """True when a settings.json matcher covers `tool`, read as the harness reads one: an absent or empty matcher and
    "*" cover every tool, and any other matcher is a regex that matches the whole name or a part of it. The PreToolUse
    form lives in lint/test_settings_matcher.py, a separate runner, so this copy reads the PostToolUse entries here."""
    if matcher in (None, "", "*"):
        return True
    return re.fullmatch(matcher, tool) is not None or re.search(matcher, tool) is not None


def audit_commands():
    """The command of each PostToolUse command hook whose matcher covers the start tool, read from settings.json."""
    with open(AUDIT_SETTINGS, encoding="utf-8") as handle:
        entries = json.load(handle)["hooks"].get("PostToolUse", [])
    commands = []
    for entry in entries:
        if post_tool_covers(entry.get("matcher"), AUDIT_TOOL):
            commands += [h.get("command", "") for h in entry.get("hooks", []) if h.get("type") == "command"]
    return commands


def audit_hook_file():
    """(path, "") for the one hook file the PostToolUse command for the start tool runs, else (None, the reason)."""
    commands = audit_commands()
    if len(commands) != 1:
        return None, "%d PostToolUse command(s) cover %s in settings.json, want one" % (len(commands), AUDIT_TOOL)
    named = re.search(r"hooks/([A-Za-z0-9_.-]+\.py)", commands[0])
    if not named:
        return None, "the PostToolUse command for %s names no hooks/<file>.py" % AUDIT_TOOL
    return os.path.join(REPO, "hooks", named.group(1)), ""


def audit_run(payload, state):
    """(stdout, "") from the audit hook file on one payload, with `state` as the config folder, else ("", the reason)."""
    path, reason = audit_hook_file()
    if path is None:
        return "", reason
    env = dict(os.environ)
    env.pop("CLAUDE_CODE_REMOTE", None)
    env.pop("CLAUDE_CODE_SESSION_ID", None)
    env["CLAUDE_CONFIG_DIR"] = state
    result = subprocess.run([sys.executable, path], input=json.dumps(payload), capture_output=True, text=True,
                            env=env, timeout=60)
    if result.returncode != 0:
        return "", "the audit exited %d: %s" % (result.returncode, result.stderr.strip()[-120:])
    return result.stdout, ""


def audit_start(model, state):
    """Run the audit on a start_session call that names `model`; a None model leaves the field out."""
    tool_input = {"initiation": "user_asked", "prompt": "x"}
    if model is not None:
        tool_input["model"] = model
    return audit_run({"hook_event_name": "PostToolUse", "session_id": HU_SID, "cwd": ROOT,
                      "tool_name": AUDIT_TOOL, "tool_input": tool_input, "tool_response": "session started"}, state)


def audit_context(stdout):
    """(additionalContext, "") for the PostToolUse JSON the audit printed, ("", "") for silence, else ("", the reason)."""
    if not stdout.strip():
        return "", ""
    try:
        out = json.loads(stdout)
    except ValueError:
        return "", "the audit printed text that is not JSON: %r" % stdout.strip()[:80]
    spec = out.get("hookSpecificOutput") if isinstance(out, dict) else None
    if not isinstance(spec, dict) or spec.get("hookEventName") != "PostToolUse" \
            or not isinstance(spec.get("additionalContext"), str):
        return "", "the audit's JSON has no PostToolUse hookSpecificOutput.additionalContext"
    return spec["additionalContext"], ""


def audit_folder(name):
    folder = os.path.join(ROOT, "audit-" + name)
    os.makedirs(folder, exist_ok=True)
    return folder


def audit_expect(model, folder, setup, flagged, fragments=()):
    """(ok, note) for one audit run. `setup(folder)` writes the handoff state first. A flagged start must print
    additionalContext that holds each fragment; an unflagged start must print nothing."""
    if setup is not None:
        setup(folder)
    stdout, reason = audit_start(model, folder)
    if reason:
        return False, reason
    context, reason = audit_context(stdout)
    if reason:
        return False, reason
    if not flagged:
        return (not context), ("silent" if not context else "printed context: %s" % context[:80])
    if not context:
        return False, "the audit printed nothing for a start it should flag"
    missing = [fragment for fragment in fragments if fragment not in context]
    if missing:
        return False, "the audit's context lacks %r" % missing[0]
    return True, "flagged, with the stop line"


def audit_wired_once():
    """settings.json has one PostToolUse command for the start tool: the audit is wired, and only once."""
    count = len(audit_commands())
    if count == 1:
        return True, "one PostToolUse command covers %s" % AUDIT_TOOL
    return False, "%d PostToolUse command(s) cover %s in settings.json, want one" % (count, AUDIT_TOOL)


def audit_haiku_flagged():
    return audit_expect("haiku", audit_folder("haiku"), None, True, ("haiku",) + AUDIT_STOP_LINE)


def audit_full_haiku_id_flagged():
    return audit_expect("claude-haiku-5-5", audit_folder("haiku-id"), None, True, AUDIT_STOP_LINE)


def audit_sonnet_silent():
    return audit_expect("sonnet", audit_folder("sonnet"), None, False)


def audit_no_model_silent():
    # The empty state: a start that names no model is not below the floor, so the audit stays silent.
    return audit_expect(None, audit_folder("no-model"), None, False)


def audit_unread_handoff_flagged():
    return audit_expect("sonnet", audit_folder("unread"), lambda folder: hu_files(folder, True, True), True,
                        ("handoff",) + AUDIT_STOP_LINE)


def audit_flag_without_handoff_silent():
    # The guard's own unread case needs both files (HU_BOTH), so a flag with no handoff is read, not unread.
    return audit_expect("sonnet", audit_folder("flag-only"), lambda folder: hu_files(folder, True, False), False)


def audit_handoff_without_flag_silent():
    return audit_expect("sonnet", audit_folder("handoff-only"), lambda folder: hu_files(folder, False, True), False)


def guard_module():
    import importlib.util
    spec = importlib.util.spec_from_file_location("guard_for_audit_floor", GUARD)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def audit_matches_floor_hit():
    # The audit reuses guard.floor_hit: for each model, it flags a start exactly when floor_hit names a model below the floor.
    guard = guard_module()
    folder = audit_folder("floor-parity")
    for model in ("haiku", "claude-haiku-5-5", "Claude-HAIKU-4-5", "sonnet", "opus", None):
        want = bool(model is not None and guard.floor_hit(AUDIT_TOOL, {"model": model}))
        ok, note = audit_expect(model, folder, None, want)
        if not ok:
            return False, "model %r: %s" % (model, note)
    return True, "the audit and floor_hit agree on every model"


def floor_hit_flags_haiku_start():
    # A control that passes on the old code: the floor the audit reuses already names haiku for a start.
    verdict = guard_module().floor_hit(AUDIT_TOOL, {"model": "haiku"})
    return verdict == "haiku", "floor_hit names %r for a haiku start" % verdict


for _label, _check in (
        ("the one PostToolUse command is wired, once", audit_wired_once),
        ("a haiku start is flagged, with the stop line", audit_haiku_flagged),
        ("the full haiku model id is flagged too", audit_full_haiku_id_flagged),
        ("a sonnet start is silent", audit_sonnet_silent),
        ("a start with no model is silent", audit_no_model_silent),
        ("a start with an unread handoff is flagged, with the stop line", audit_unread_handoff_flagged),
        ("a flag with no handoff file is silent", audit_flag_without_handoff_silent),
        ("a handoff with no flag is silent", audit_handoff_without_flag_silent),
        ("the audit flags each model guard.floor_hit flags", audit_matches_floor_hit),
        ("control: guard.floor_hit names a haiku start", floor_hit_flags_haiku_start)):
    LOG_CHECKS_EXTRA.append(("start-session: " + _label, _check))
    FIXTURELESS_CHECKS.add(_check)

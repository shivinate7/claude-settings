# section 38500
FAMILY = "start-session-audit"
# ---- The start-session audit (roadmap step start-session-not-pretooluse). settings.json does not route start_session to
# PreToolUse: a PreToolUse matcher that covers it makes the desktop app show the "Allow Claude to start the session?"
# card on every start, even in Bypass (anthropics/claude-code#103832). The start checks run after the call instead.
# The one PostToolUse command that settings.json names for start_session runs the handoff-unread read and flags no
# model: a Haiku start prints nothing, by the owner's ruling of 2026-11-18 19:03 CST (no guard on the model floor),
# because a started session cannot read the owner's word. A bad start prints PostToolUse additionalContext that tells
# the calling session to stop the new session with interrupt_session or archive_session. A start that passes prints
# nothing. A silence case also runs the same start with an unread handoff, so a dead hook cannot pass as silent.
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


def audit_wrapper_blocking(module):
    """A `-c` wrapper that makes `import <module>` fail, as a broken module file would: sys.modules holds None for it,
    so the import raises. The hook file runs as __main__ after it, with the same stdin."""
    return ("import sys, runpy; sys.modules[%r] = None; sys.argv = sys.argv[1:]; "
            "runpy.run_path(sys.argv[0], run_name='__main__')" % module)


def audit_text(stdin_text, state, wrapper=None):
    """(stdout, "") from the audit hook file on one stdin text, with `state` as the config folder, else ("", the reason).
    A nonzero exit is a reason too, so a crash never reads as silence."""
    path, reason = audit_hook_file()
    if path is None:
        return "", reason
    env = dict(os.environ)
    env.pop("CLAUDE_CODE_REMOTE", None)
    env.pop("CLAUDE_CODE_SESSION_ID", None)
    env["CLAUDE_CONFIG_DIR"] = state
    command = [sys.executable, path] if wrapper is None else [sys.executable, "-c", wrapper, path]
    result = subprocess.run(command, input=stdin_text, capture_output=True, text=True, env=env, timeout=60)
    if result.returncode != 0:
        return "", "the audit exited %d: %s" % (result.returncode, result.stderr.strip()[-120:])
    return result.stdout, ""


def audit_run(payload, state):
    return audit_text(json.dumps(payload), state)


def audit_payload(model, response="session started"):
    """The PostToolUse payload of a start_session call that names `model`, with `response` as its tool_response; a None
    model leaves the field out."""
    tool_input = {"initiation": "user_asked", "prompt": "x"}
    if model is not None:
        tool_input["model"] = model
    return {"hook_event_name": "PostToolUse", "session_id": HU_SID, "cwd": ROOT,
            "tool_name": AUDIT_TOOL, "tool_input": tool_input, "tool_response": response}


def audit_start(model, state, response="session started"):
    return audit_run(audit_payload(model, response), state)


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


def audit_expect(model, folder, setup, flagged, fragments=(), response="session started", absent=()):
    """(ok, note) for one audit run. `setup(folder)` writes the handoff state first. A flagged start must print
    additionalContext that holds each fragment and none of `absent`; an unflagged start must print nothing."""
    if setup is not None:
        setup(folder)
    stdout, reason = audit_start(model, folder, response)
    if reason:
        return False, reason
    context, reason = audit_context(stdout)
    if reason:
        return False, reason
    if not flagged:
        return (not context), ("silent" if not context else "printed context: %s" % context[:80])
    if not context:
        return False, "the audit printed nothing for a start it should flag"
    named = [fragment for fragment in absent if fragment in context]
    if named:
        return False, "the audit names %r as the new session" % named[0]
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


def audit_silent_then_flagged(model, name):
    """(ok, note) for one model: the same start is flagged with the stop line when the handoff is unread, and silent
    when it is read. The flag comes first, so a silence cannot pass from a hook that is dead."""
    ok, note = audit_expect(model, audit_folder(name + "-unread"), lambda folder: hu_files(folder, True, True), True,
                            AUDIT_STOP_LINE)
    if not ok:
        return False, "the unread handoff: " + note
    ok, note = audit_expect(model, audit_folder(name + "-read"), lambda folder: hu_files(folder, False, True), False)
    if not ok:
        return False, "the read handoff: " + note
    return True, "flagged with the stop line on an unread handoff, silent on a read one"


def audit_haiku_silent():
    return audit_silent_then_flagged("haiku", "haiku")


def audit_full_haiku_id_silent():
    return audit_silent_then_flagged("claude-haiku-5-5", "haiku-id")


def audit_sonnet_silent():
    return audit_expect("sonnet", audit_folder("sonnet"), None, False)


def audit_no_model_silent():
    # The empty state: a start that names no model has no model to flag, so the audit stays silent.
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


def audit_flags_no_model():
    # No spelling of a model is a reason to flag, the floor's own words included. An unread handoff flags each one.
    for index, model in enumerate(("haiku", "claude-haiku-5-5", "Claude-HAIKU-4-5", "sonnet", "opus", None)):
        ok, note = audit_silent_then_flagged(model, "model-%d" % index)
        if not ok:
            return False, "model %r: %s" % (model, note)
    return True, "no model is flagged; an unread handoff flags each one"


def floor_hit_flags_haiku_start():
    # A control: guard.floor_hit still names haiku for a start. The audit does not reuse it, so the audit's silence on a
    # Haiku start is its own choice, not a floor that has gone missing.
    verdict = guard_module().floor_hit(AUDIT_TOOL, {"model": "haiku"})
    return verdict == "haiku", "floor_hit names %r for a haiku start" % verdict


# The new session's id, named the way the session-board test's start result names it ("session_x started").
AUDIT_SESSION_ID = "session_x"
AUDIT_ID_TEXT = [{"type": "text", "text": AUDIT_SESSION_ID + " started"}]


def audit_text_silent(stdin_text, folder, wrapper=None):
    """(ok, note) for one raw stdin: silent and exit 0 is the pass. A nonzero exit is a reason, never silence."""
    stdout, reason = audit_text(stdin_text, folder, wrapper)
    if reason:
        return False, reason
    return (not stdout.strip()), ("silent, exit 0" if not stdout.strip() else "printed: %s" % stdout[:80])


def unread_handoff_setup(folder):
    """The flag and the handoff are both set, so the start is flagged on the unread handoff, never on its model."""
    hu_files(folder, True, True)


def audit_names_id_text():
    return audit_expect("sonnet", audit_folder("id-text"), unread_handoff_setup, True, (AUDIT_SESSION_ID,),
                        response=AUDIT_SESSION_ID + " started")


def audit_names_id_content_list():
    return audit_expect("sonnet", audit_folder("id-list"), unread_handoff_setup, True, (AUDIT_SESSION_ID,),
                        response=AUDIT_ID_TEXT)


def audit_names_id_content_dict():
    return audit_expect("sonnet", audit_folder("id-dict"), unread_handoff_setup, True, (AUDIT_SESSION_ID,),
                        response={"content": AUDIT_ID_TEXT})


def audit_names_id_result_dict():
    return audit_expect("sonnet", audit_folder("id-result"), unread_handoff_setup, True, (AUDIT_SESSION_ID,),
                        response={"result": {"content": AUDIT_ID_TEXT}})


def audit_no_id_says_unread():
    # The start result names no session id: the start still flags, and the flag says the id is unread.
    return audit_expect("sonnet", audit_folder("id-none"), unread_handoff_setup, True, ("id is unread",),
                        response={"content": [{"type": "text", "text": "done"}]})


def audit_field_text_no_id_unread():
    # The text holds a JSON field, not an id: the flag must not name the field as the session.
    return audit_expect("sonnet", audit_folder("field-text"), unread_handoff_setup, True, ("(id is unread)",),
                        response='{"session_id":"local_x"}', absent=("(session_id)",))


def audit_word_session_start_no_id_unread():
    # A word that starts with session_ is not an id either.
    return audit_expect("sonnet", audit_folder("word-start"), unread_handoff_setup, True, ("(id is unread)",),
                        response="session_start returned", absent=("(session_start)",))


def audit_field_text_names_real_id():
    # A field name before a real id: the flag names the id that follows, never the field.
    return audit_expect("sonnet", audit_folder("field-real-id"), unread_handoff_setup, True, ("(session_abc)",),
                        response='{"session_id":"session_abc"}', absent=("(session_id)",))


def audit_plain_text_real_id_control():
    # Control: a real id in plain text is still named.
    return audit_expect("sonnet", audit_folder("plain-real-id"), unread_handoff_setup, True, ("(session_abc)",),
                        response="session_abc started")


def audit_bad_json_silent_exit0():
    return audit_text_silent("{not json", audit_folder("bad-json"))


def audit_json_list_silent_exit0():
    return audit_text_silent("[1, 2]", audit_folder("json-list"))


def audit_gate_silent(name, response):
    """(ok, note): a start whose response is not a started session is silent, though its handoff is unread. The same
    handoff flags a started response first, so the silence comes from the response gate and not from a dead hook."""
    ok, note = audit_expect("sonnet", audit_folder(name + "-started"), unread_handoff_setup, True, AUDIT_STOP_LINE,
                            response=AUDIT_SESSION_ID + " started")
    if not ok:
        return False, "the started response: " + note
    ok, note = audit_expect("sonnet", audit_folder(name), unread_handoff_setup, False, response=response)
    if not ok:
        return False, "the response that is not a start: " + note
    return True, "silent on an unread handoff when the response is not a started session"


def audit_number_response_silent():
    # A tool_response that is neither text, a content list nor a dict cannot be read, so the audit says nothing.
    return audit_gate_silent("num-response", 42)


def audit_import_failure_silent_exit0():
    # The handoff read cannot import. The audit says nothing and exits 0, as it does for any read it cannot make. The
    # same unread handoff flags when the read imports, so the silence comes from the failed import.
    ok, note = audit_expect("sonnet", audit_folder("import-ok"), unread_handoff_setup, True, AUDIT_STOP_LINE)
    if not ok:
        return False, "the read imports: " + note
    folder = audit_folder("import-fail")
    unread_handoff_setup(folder)
    ok, note = audit_text_silent(json.dumps(audit_payload("sonnet")), folder,
                                 wrapper=audit_wrapper_blocking("reread_check"))
    if not ok:
        return False, "the read does not import: " + note
    return True, "silent, exit 0, when the handoff read cannot import"


def audit_is_error_silent():
    return audit_gate_silent("is-error",
                             {"is_error": True, "content": [{"type": "text", "text": "no such repo"}]})


def audit_isError_silent():
    return audit_gate_silent("isError", {"isError": True, "result": "no such repo"})


def audit_refused_silent():
    return audit_gate_silent("deny", {"deny": "refused"})


for _label, _check in (
        ("the one PostToolUse command is wired, once", audit_wired_once),
        ("a haiku start is silent on a read handoff, and flagged with the stop line on an unread one", audit_haiku_silent),
        ("the full haiku model id is silent on a read handoff, and flagged on an unread one",
         audit_full_haiku_id_silent),
        ("a sonnet start is silent", audit_sonnet_silent),
        ("a start with no model is silent", audit_no_model_silent),
        ("a start with an unread handoff is flagged, with the stop line", audit_unread_handoff_flagged),
        ("a flag with no handoff file is silent", audit_flag_without_handoff_silent),
        ("a handoff with no flag is silent", audit_handoff_without_flag_silent),
        ("no model is flagged: an unread handoff flags each one, a read handoff flags none", audit_flags_no_model),
        ("control: guard.floor_hit still names a haiku start, which the audit does not use", floor_hit_flags_haiku_start),
        ("the flag names the new session's id from a text response", audit_names_id_text),
        ("the flag names the id from a content-list response", audit_names_id_content_list),
        ("the flag names the id from a content dict response", audit_names_id_content_dict),
        ("the flag names the id from a result dict response", audit_names_id_result_dict),
        ("a start with no readable id still flags, saying the id is unread", audit_no_id_says_unread),
        ("fail open: bad JSON on stdin is silent, exit 0", audit_bad_json_silent_exit0),
        ("fail open: a JSON list on stdin is silent, exit 0", audit_json_list_silent_exit0),
        ("fail open: a number tool_response is silent, exit 0, on an unread handoff", audit_number_response_silent),
        ("fail open: a handoff read that cannot import is silent, exit 0", audit_import_failure_silent_exit0),
        ("an errored start (is_error) on an unread handoff prints nothing", audit_is_error_silent),
        ("an errored start (isError) on an unread handoff prints nothing", audit_isError_silent),
        ("a denied start on an unread handoff prints nothing", audit_refused_silent),
        ("the flag does not name a JSON field as the session, and says the id is unread",
         audit_field_text_no_id_unread),
        ("the flag does not name the word session_start as the session, and says the id is unread",
         audit_word_session_start_no_id_unread),
        ("the flag names the real id after a field name, not the field", audit_field_text_names_real_id),
        ("control: a real id in plain text is still named", audit_plain_text_real_id_control)):
    LOG_CHECKS_EXTRA.append(("start-session: " + _label, _check))
    FIXTURELESS_CHECKS.add(_check)

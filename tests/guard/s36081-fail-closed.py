# section 36081
FAMILY = "fail-closed"  # the family the cases below had before this section
FAMILIES["session-log"] = "the session id column of guard.log"


# --------------------------------------------------------------------------- session-log
#
# guard.log gets ONE column for the hook's session_id, LAST, after the matched text. The five
# columns before it keep their index, so a reader that splits by tab reads what it read before.
# The id comes from the hook input alone; the environment is never read. A missing, empty,
# non-string or blank id writes SESSION_LOG_PLACEHOLDER. A control character is stripped, and the
# id is capped at 64 characters. The writer never raises, and a log that cannot land never changes
# the verdict.

SESSION_LOG_ID = "9f2c4e1a-7b3d-4c8e-9a10-5d6e7f8a9b0c"
SESSION_LOG_ENV_ID = "1a2b3c4d-5e6f-4a7b-8c9d-0e1f2a3b4c5d"
SESSION_LOG_PLACEHOLDER = "-"
SESSION_LOG_ABSENT = object()  # a payload with no session_id key at all
SESSION_LOG_DENY = {"tool_name": "Bash", "tool_input": {"command": "pkill -f node"}}


def _session_log_run(folder, body, extra_env=None):
    """Run the guard once on a raw payload string, with CLAUDE_CONFIG_DIR set to `folder`."""
    env = dict(os.environ)
    env.pop("CLAUDE_CODE_REMOTE", None)
    env["CLAUDE_CONFIG_DIR"] = folder
    env.pop("CLAUDE_CODE_SESSION_ID", None)
    env.update(extra_env or {})
    return subprocess.run([sys.executable, GUARD], input=body, capture_output=True, text=True,
                          env=env, timeout=60)


def _session_log_rows(folder):
    """Return the lines of folder's guard.log, or None when no file exists. The text is read the
    way the report reads it: universal newlines, so CRLF comes back as LF."""
    path = os.path.join(folder, "guard.log")
    if not os.path.exists(path):
        return None
    with open(path, encoding="utf-8") as handle:
        text = handle.read()
    if text.endswith("\n"):
        text = text[:-1]
    return text.split("\n")


def _session_log_payload(session):
    """The deny payload, carrying `session` as its session_id. SESSION_LOG_ABSENT means no key."""
    body = dict(SESSION_LOG_DENY, cwd=ROOT)
    if session is not SESSION_LOG_ABSENT:
        body["session_id"] = session
    return json.dumps(body)


def _session_log_fresh(name):
    folder = os.path.join(ROOT, name)
    shutil.rmtree(folder, ignore_errors=True)
    os.makedirs(folder)
    return folder


def session_log_each_decision_case():
    """session-log: every decision line ends in the hook's session_id.

    Three calls under one session id: a deny (a machine-wide kill), an allow that writes nothing
    (git status), and a noted line (a project config edit). The two decision lines must each have
    six tab fields, and the sixth must be the id.
    """
    folder = _session_log_fresh("sessionlog-each")
    bodies = [
        dict(SESSION_LOG_DENY, cwd=ROOT, session_id=SESSION_LOG_ID),
        {"tool_name": "Bash", "tool_input": {"command": VCS + " status"}, "cwd": ROOT,
         "session_id": SESSION_LOG_ID},
        {"tool_name": "Edit", "tool_input": {"file_path": PROJ_SETTINGS}, "cwd": ROOT,
         "session_id": SESSION_LOG_ID},
    ]
    for body in bodies:
        run = _session_log_run(folder, json.dumps(body))
        if run.returncode != 0:
            return False, "guard exited %d" % run.returncode
    rows = _session_log_rows(folder)
    if rows is None:
        return False, "no guard.log was written"
    if len(rows) != 2:
        return False, "expected two lines (one deny, one noted), found %d" % len(rows)
    for row in rows:
        fields = row.split("\t")
        if len(fields) != 6:
            return False, "expected six tab fields, found %d: %r" % (len(fields), row)
        if fields[5] != SESSION_LOG_ID:
            return False, "the last field is %r, want the hook's session_id" % fields[5]
    return True, "a deny and a noted line, each ending in the hook's session_id"


# (label, session_id as the hook sends it, the last field the log must hold)
SESSION_LOG_COLUMN_CASES = (
    ("no session_id key", SESSION_LOG_ABSENT, SESSION_LOG_PLACEHOLDER),
    ("empty string", "", SESSION_LOG_PLACEHOLDER),
    ("integer", 12345, SESSION_LOG_PLACEHOLDER),
    ("list", ["x"], SESSION_LOG_PLACEHOLDER),
    ("null", None, SESSION_LOG_PLACEHOLDER),
    ("tab inside", "abc\tdef", "abcdef"),
    ("newline inside", "ghi\njkl", "ghijkl"),
    ("only control characters", "\t\r\n", SESSION_LOG_PLACEHOLDER),
    ("exactly 64 characters", "t" * 64, "t" * 64),
    ("300 characters", "s" * 300, "s" * 64),
)


def session_log_column_case():
    """session-log: the column is the placeholder, or the id with control characters stripped and
    capped at 64. Each case is one deny: the deny must still print, and exactly one six-field line
    must land, never a second line and never a line broken by the id.
    """
    for index, (label, session, want) in enumerate(SESSION_LOG_COLUMN_CASES):
        folder = _session_log_fresh("sessionlog-col-%d" % index)
        run = _session_log_run(folder, _session_log_payload(session))
        if run.returncode != 0:
            return False, "%s: guard exited %d" % (label, run.returncode)
        if not run.stdout.strip():
            return False, "%s: the deny was not printed" % label
        rows = _session_log_rows(folder)
        if rows is None or len(rows) != 1:
            return False, "%s: expected one line, found %s" % (
                label, "none" if rows is None else len(rows))
        fields = rows[0].split("\t")
        if len(fields) != 6:
            return False, "%s: expected six tab fields, found %d: %r" % (label, len(fields), rows[0])
        if fields[5] != want:
            return False, "%s: the last field is %r, want %r" % (label, fields[5], want)
    return True, "%d session values: placeholder, or stripped and capped, one line each" % (
        len(SESSION_LOG_COLUMN_CASES))


def session_log_env_case():
    """session-log: the column comes from the hook input only. A payload with no session_id writes
    the placeholder even when the environment names a session, because an environment value can
    belong to a parent session.
    """
    folder = _session_log_fresh("sessionlog-env")
    run = _session_log_run(folder, _session_log_payload(SESSION_LOG_ABSENT),
                           extra_env={"CLAUDE_CODE_SESSION_ID": SESSION_LOG_ENV_ID})
    if not run.stdout.strip():
        return False, "the deny was not printed"
    rows = _session_log_rows(folder)
    if rows is None or len(rows) != 1:
        return False, "expected one line, found %s" % ("none" if rows is None else len(rows))
    fields = rows[0].split("\t")
    if len(fields) != 6 or fields[5] != SESSION_LOG_PLACEHOLDER:
        return False, "the last field is %r, want the placeholder %r" % (
            fields[-1], SESSION_LOG_PLACEHOLDER)
    return True, "the placeholder, not the environment's session id"


def session_log_writer_case():
    """session-log: the writer, called as today with no session argument, writes one six-field line
    that ends in the placeholder. The config folder is patched on sys.modules["guard_core"], the
    module the writer reads it from. guard.py only re-exports the name, so a patch on guard would
    never reach the writer.
    """
    if HERE not in sys.path:
        sys.path.insert(0, HERE)
    import guard_core  # noqa: F401  (imported for its sys.modules entry)
    core = sys.modules["guard_core"]
    folder = _session_log_fresh("sessionlog-writer")
    saved = core.config_dir
    core.config_dir = lambda: folder
    try:
        core.record("Bash", "deny", "shared-tree", "git stash")
    finally:
        core.config_dir = saved
    rows = _session_log_rows(folder)
    if rows is None or len(rows) != 1:
        return False, "expected one line, found %s" % ("none" if rows is None else len(rows))
    fields = rows[0].split("\t")
    if len(fields) != 6 or fields[5] != SESSION_LOG_PLACEHOLDER:
        return False, "expected six fields ending in the placeholder, got %r" % rows[0]
    return True, "one six-field line, ending in the placeholder"


def session_log_unwritable_case():
    """session-log: a log that cannot be written never raises from the writer and never changes a
    verdict. The writer is run with a config_dir that raises, then the guard runs with a config
    folder that is a file, so every write fails. The deny still prints, and the exit is 0.
    """
    if HERE not in sys.path:
        sys.path.insert(0, HERE)
    import guard_core  # noqa: F401  (imported for its sys.modules entry)
    core = sys.modules["guard_core"]

    def unreadable_folder():
        raise OSError("no config folder")

    saved = core.config_dir
    core.config_dir = unreadable_folder
    try:
        core.record("Bash", "deny", "shared-tree", "git stash")
    except Exception as exc:  # the writer must swallow this, never pass it up
        return False, "record raised %s when the config folder was unreadable" % type(exc).__name__
    finally:
        core.config_dir = saved
    blocker = os.path.join(ROOT, "sessionlog-blocker")
    with open(blocker, "w", encoding="utf-8") as handle:
        handle.write("a file, not a folder\n")
    run = _session_log_run(blocker, _session_log_payload(SESSION_LOG_ID))
    if run.returncode != 0:
        return False, "guard exited %d" % run.returncode
    if not run.stdout.strip():
        return False, "the deny was not printed: a log failure changed the verdict"
    try:
        decision = json.loads(run.stdout)["hookSpecificOutput"]["permissionDecision"]
    except (ValueError, KeyError, TypeError):
        return False, "the output is not a PreToolUse answer: %r" % run.stdout[:120]
    if decision != "deny":
        return False, "the verdict is %r, want deny" % decision
    return True, "a raising config_dir is swallowed, and a file in its place still denies"


LOG_CHECKS_EXTRA.append(("session-log: every decision line ends in the hook's session_id",
                         session_log_each_decision_case))
LOG_CHECKS_EXTRA.append(("session-log: the column is the placeholder, or the id stripped and "
                         "capped at 64", session_log_column_case))
LOG_CHECKS_EXTRA.append(("session-log: the environment's session id is never read",
                         session_log_env_case))
LOG_CHECKS_EXTRA.append(("session-log: the writer with no session argument writes a six-field "
                         "line", session_log_writer_case))
LOG_CHECKS_EXTRA.append(("session-log: an unwritable log never raises and never changes the "
                         "verdict", session_log_unwritable_case))


# The time in field 0 of a written line: ISO 8601 with a colon UTC offset, as guard_core.record() writes it.
STAMP_SHAPE = r"\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d[+-]\d\d:\d\d"


def _stamp_verdict(stamp):
    """(ok, message) for one written time: the colon shape, this machine's own offset, and the current instant."""
    if not re.fullmatch(STAMP_SHAPE, stamp):
        return False, "field 0 is %r, want ISO 8601 with a colon offset, like 2026-11-01T16:55:00-06:00" % stamp
    parsed = datetime.fromisoformat(stamp)
    local = datetime.now().astimezone().utcoffset()
    if parsed.utcoffset() != local:
        return False, "field 0 is %r with offset %s, want this machine's %s" % (stamp, parsed.utcoffset(), local)
    if abs(datetime.now(timezone.utc) - parsed) > timedelta(minutes=5):
        return False, "field 0 is %r, which is not the current time" % stamp
    return True, "field 0 is %s, with this machine's offset and the current time" % stamp


def session_log_stamp_offset_case():
    """session-log: record() writes field 0 with its UTC offset, as ISO 8601 with a colon. The writer is
    called in process as session_log_writer_case calls it, so the one line it writes is read back here.
    """
    if HERE not in sys.path:
        sys.path.insert(0, HERE)
    import guard_core  # noqa: F401  (imported for its sys.modules entry)
    core = sys.modules["guard_core"]
    folder = _session_log_fresh("sessionlog-stamp")
    saved = core.config_dir
    core.config_dir = lambda: folder
    try:
        core.record("Bash", "deny", "shared-tree", "git stash")
    finally:
        core.config_dir = saved
    rows = _session_log_rows(folder)
    if rows is None or len(rows) != 1:
        return False, "expected one line, found %s" % ("none" if rows is None else len(rows))
    return _stamp_verdict(rows[0].split("\t")[0])


def crash_log_stamp_case():
    """session-log: the crash line the judge's exception writes through record() carries the colon UTC
    offset in field 0. The run is the one crash_log_case makes, through the shared step.
    """
    folder = os.path.join(ROOT, "crashstamp")
    os.makedirs(folder, exist_ok=True)
    path = os.path.join(folder, "guard.log")
    if os.path.exists(path):
        os.remove(path)
    _crash_judge_run(folder)
    if not os.path.exists(path):
        return False, "no crash line was logged"
    with open(path, encoding="utf-8") as handle:
        fields = handle.read().strip().split("\t")
    if len(fields) < 4 or fields[2:4] != ["crash", "guard-crash"]:
        return False, "unexpected crash line: %r" % fields
    return _stamp_verdict(fields[0])


LOG_CHECKS_EXTRA.append(("session-log: record() writes its time with a colon UTC offset",
                         session_log_stamp_offset_case))
LOG_CHECKS_EXTRA.append(("session-log: a guard crash line's time carries the colon UTC offset",
                         crash_log_stamp_case))


# A guard_core that lacks set_log_session is covered by the stale-core case below: that case drops
# this name too, and its call site (guard.py main) fails the same way.
def session_log_stale_core_case():
    """session-log: a stale guard_core that lacks BOTH set_log_session and _log_session still
    judges. The verdict and the exit match a run with both names, and the deny line has five fields:
    no session cell, so it reads as unknown session. The comments that say the line ends in the
    placeholder (hooks/guard.py main, hooks/config_watch.py sweep) are wrong for this case.
    """
    payload = _session_log_payload(SESSION_LOG_ID)
    runs = []
    for label, drop in (("with", ()), ("without", ("set_log_session", "_log_session"))):
        folder = _session_log_fresh("sessionlog-stalecore-" + label)
        code = ("import io, sys, importlib.util as u\n"
                "spec = u.spec_from_file_location('g', %r)\n"
                "g = u.module_from_spec(spec)\n"
                "spec.loader.exec_module(g)\n" % GUARD
                + "".join("del sys.modules['guard_core'].%s\n" % name for name in drop)
                + "sys.stdin = io.StringIO(%r)\n"
                  "g.main()\n" % payload)
        env = dict(os.environ)
        env["CLAUDE_CONFIG_DIR"] = folder
        env.pop("CLAUDE_CODE_SESSION_ID", None)
        run = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True,
                             env=env, timeout=60)
        runs.append((run, _session_log_rows(folder)))
    (with_run, _), (without_run, without_rows) = runs
    if without_run.returncode != with_run.returncode:
        return False, "exit %d without the two names, %d with them" % (
            without_run.returncode, with_run.returncode)
    if "Traceback" in without_run.stderr:
        return False, "a traceback without the two names: %r" % without_run.stderr.strip()[-160:]
    if not without_run.stdout.strip():
        return False, "the deny was not printed without the two names"
    if without_run.stdout != with_run.stdout:
        return False, "the verdict changed without the two names"
    if without_rows is None or len(without_rows) != 1:
        return False, "expected one line without the two names, found %s" % (
            "none" if without_rows is None else len(without_rows))
    fields = without_rows[0].split("\t")
    if len(fields) != 5 or fields[2:4] != ["deny", "machine-wide-kill"]:
        return False, "the line without the two names is %r, want five fields, a deny" % (
            without_rows[0])
    return True, "same verdict and exit, and the line has five fields (unknown session)"


LOG_CHECKS_EXTRA.append(("session-log: a stale guard_core lacking both names still judges, and "
                         "its line has five fields", session_log_stale_core_case))


# --------------------------------------------------------------------------- the owner override

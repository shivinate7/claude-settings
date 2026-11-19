# section 43700
FAMILY = "note-form-at-write"
#
# The old notes file takes deletes only (decision notes-merge-union, one file per note; the old notes file is frozen).
# lint/check_record_slugs.py refuses an added line at hand-in. This family catches the same write at write time, so the
# author learns it before the commit. The first form is log-only: a new guard logs before it refuses. So the write is
# allowed, prints nothing, and writes one `noted` line under RULE, whose text carries the checker's own remedy.
#
# Nothing here copies a path or a remedy. The old file is the one layout names (lint/layout.py, kind debt-notes, read as
# `candidates`). The remedy is read back from the checker's printed refusal, by PROBE below, which also proves the
# checker counts the old file as frozen before any red case relies on it.
#
# Red cases: a write that adds a line, by Write, Edit or MultiEdit, into an empty file, a one-line file and a 200-line
# file. Each adds one line, so each writes one noted line. A replace_all Edit adds two lines and still writes one noted
# line: the guard logs only the first line it adds. Controls: a delete, a blank line, a reorder,
# a new note file and a debt record. Each passes silently, and writes no noted line for RULE.

import layout as lint_layout  # noqa: E402  the one home of where each kind lives (lint/layout.py)

RULE = "note-form-at-write"  # the rule the guard logs under, and the family of these cases
OLD_NOTES = lint_layout.candidates(REPO, "debt-notes")[-1]  # the old notes file, as the checker names it
NOTE_DIR = lint_layout.path(REPO, "notes")  # the note folder a new note file goes in
DEBT_DIR = lint_layout.path(REPO, "debts")  # the debt folder, which holds the old notes file and no note
BASE_LINES = "- nt-base: base note\n- nt-other: other note\n"
FULL_LINES = "".join("- nt-full-%03d: note %d\n" % (n, n) for n in range(200))  # the full-size state
STATES = {"one": BASE_LINES, "empty": "", "full": FULL_LINES}  # the old file's text in each fixture repo
PROBE_LINE = "- nt-probe: remedy probe"  # short, so the checker prints the whole line in its refusal
FAIL_PREFIX = "check_record_slugs: FAIL: "  # the start of every refusal line the checker prints
GIT_LOCATION = ("GIT_DIR", "GIT_WORK_TREE", "GIT_INDEX_FILE")  # the caller's git location, stripped for a fixture git
CALLER_VARS = GIT_LOCATION + ("CLAUDE_CODE_REMOTE", "CLAUDE_CODE_SESSION_ID", "CS_SESSION_ROLE",
                              "CLAUDE_CODE_REMOTE_SESSION_ID", "CLAUDE_PROJECT_DIR")


@contextlib.contextmanager
def git_clean_env():
    """The caller's git location variables removed for the block, and the environment restored after it."""
    with mock.patch.dict(os.environ):
        for name in GIT_LOCATION:
            os.environ.pop(name, None)
        yield


def notes_repo(state):
    """The fixture repo whose old notes file holds STATES[state], committed. Built on first use."""
    path = os.path.join(ROOT, "noteform", state)
    if not os.path.isdir(os.path.join(path, ".git")):
        with git_clean_env():
            make_repo(path, {OLD_NOTES: STATES[state]})
    return path


_PROBE = []  # the probe's (remedy, problem), read once


def remedy_probe():
    """(remedy, problem): the remedy lint/check_record_slugs.py prints when a line is added to the old notes file.

    The checker reads its own ROOT, so the probe patches that one name to a fixture whose HEAD adds PROBE_LINE to the
    old file over origin/main. The refusal for that line ends in `: ` and the first CLIP characters of the line. The
    remedy is the text between the prefix and that tail, so it is the checker's own text, not a copy."""
    if not _PROBE:
        _PROBE.append(_read_remedy())
    return _PROBE[0]


def _read_remedy():
    import check_record_slugs as checker  # the lint folder is on sys.path (hooks/test_guard.py inserts it)
    repo = os.path.join(ROOT, "noteform", "remedy")
    with git_clean_env():
        make_repo(repo, {OLD_NOTES: BASE_LINES})
        base = run_vcs(repo, "rev-parse", "HEAD").stdout.strip()
        if not base:
            return None, "the probe fixture has no base commit"
        run_vcs(repo, "update-ref", "refs/remotes/origin/main", base)
        write(os.path.join(repo, OLD_NOTES), BASE_LINES + PROBE_LINE + "\n")
        run_vcs(repo, "add", "-A")
        run_vcs(repo, *IDENT, "commit", "-q", "-m", "probe")
        printed = io.StringIO()
        with mock.patch.object(checker, "ROOT", repo), contextlib.redirect_stdout(printed):
            checker.main([])
    tail = ": " + PROBE_LINE[:checker.CLIP]
    hits = [line for line in printed.getvalue().splitlines() if line.startswith(FAIL_PREFIX) and line.endswith(tail)]
    if len(hits) != 1:
        return None, ("the checker printed %d refusal lines for the probe line, want 1; it printed %r"
                      % (len(hits), printed.getvalue()[:160]))
    return hits[0][len(FAIL_PREFIX):-len(tail)], ""


def guard_write(repo, tool, tool_input):
    """One guard run on one write call judged in `repo`, with a config folder of its own. Returns (exit code, stdout,
    the guard.log rows the run wrote)."""
    folder = os.path.join(ROOT, "noteform", "logs", uuid.uuid4().hex)
    os.makedirs(folder)
    env = dict(os.environ)
    for name in CALLER_VARS:
        env.pop(name, None)
    env["CLAUDE_CONFIG_DIR"] = folder
    env["CLAUDE_GUARD_ROOT_PID"] = str(os.getpid())  # the suite stands in for `claude`
    body = {"tool_name": tool, "tool_input": tool_input, "cwd": repo}
    done = subprocess.run([sys.executable, GUARD], input=json.dumps(body), capture_output=True, text=True,
                          env=env, timeout=120)
    path = os.path.join(folder, "guard.log")
    text = open(path, encoding="utf-8").read() if os.path.exists(path) else ""
    return done.returncode, done.stdout.strip(), [line.split("\t") for line in text.splitlines() if line.strip()]


def old_file(repo):
    return os.path.join(repo, OLD_NOTES)


def note_check(label, state, tool, tool_input, adds):
    """Register one log check: the guard judges one write in fixture `state`. `tool_input` takes the repo and returns the
    input. When `adds` is true the write adds one line to the old notes file, so the guard logs one noted line for RULE
    that carries the checker's remedy. Otherwise it logs no noted line for RULE. Either way the call is allowed silently."""
    def check():
        remedy = ""
        if adds:
            remedy, problem = remedy_probe()
            if remedy is None:
                return False, problem
        repo = notes_repo(state)
        code, out, rows = guard_write(repo, tool, tool_input(repo))
        if code != 0:
            return False, "the guard exited %d, want 0" % code
        crashed = [row for row in rows if len(row) > 2 and row[2] == "crash"]
        if crashed:
            return False, "the guard crashed: %s" % crashed[0][3]
        if out:
            return False, "want a silent allow, got %r" % out[:80]
        noted = [row for row in rows if len(row) > 3 and row[2] == "noted" and row[3] == RULE]
        if not adds:
            if noted:
                return False, "want no noted/%s line, found %d" % (RULE, len(noted))
            return True, "a silent allow, and no noted/%s line" % RULE
        if len(noted) != 1:
            return False, "want one noted/%s line, found %d" % (RULE, len(noted))
        if remedy not in "\t".join(noted[0]):
            return False, "the noted line does not carry the checker's remedy"
        return True, "one noted/%s line with the checker's remedy, and a silent allow" % RULE
    NOTE_LOG_CHECKS.append((label, check))


def probe_check():
    remedy, problem = remedy_probe()
    if remedy is None:
        return False, problem
    return True, "the checker counts the old file as frozen, and prints its remedy for a line added to it"


NOTE_LOG_CHECKS = []  # (label, check), joined into LOG_CHECKS below: LOG_CHECKS_EXTRA was joined by section 40805
NOTE_LOG_CHECKS.append(("note-form-at-write: the checker prints its new-note remedy for a line added to the old notes file",
                        probe_check))

# Red: each write adds one line to the old notes file, so each logs one noted line and refuses nothing.
note_check("note-form-at-write: a Write that adds one note line to the old notes file is logged noted, not refused",
           "one", "Write",
           lambda repo: {"file_path": old_file(repo), "content": BASE_LINES + "- nt-new-one: a new note\n"}, adds=True)
note_check("note-form-at-write: an Edit that adds a note line after the last line is logged noted, not refused",
           "one", "Edit",
           lambda repo: {"file_path": old_file(repo), "old_string": "- nt-other: other note\n",
                         "new_string": "- nt-other: other note\n- nt-new-two: a new note\n"}, adds=True)
note_check("note-form-at-write: an Edit that rewords a note in place is logged noted, not refused",
           "one", "Edit",
           lambda repo: {"file_path": old_file(repo), "old_string": "- nt-base: base note\n",
                         "new_string": "- nt-base: base note, reworded\n"}, adds=True)
note_check("note-form-at-write: an Edit with replace_all that adds two note lines is logged noted once, not refused",
           "one", "Edit",
           lambda repo: {"file_path": old_file(repo), "old_string": "- nt-other: other note\n",
                         "new_string": "- nt-other: other note\n- nt-replace-one: a new note\n- nt-replace-two: a new note\n",
                         "replace_all": True}, adds=True)
note_check("note-form-at-write: a MultiEdit that adds a note line to the old notes file is logged noted, not refused",
           "one", "MultiEdit",
           lambda repo: {"file_path": old_file(repo), "edits": [
               {"old_string": "- nt-other: other note\n",
                "new_string": "- nt-other: other note\n- nt-new-three: a new note\n"}]}, adds=True)
note_check("note-form-at-write: a Write into an empty old notes file is logged noted, not refused",
           "empty", "Write",
           lambda repo: {"file_path": old_file(repo), "content": "- nt-first: the first note\n"}, adds=True)
note_check("note-form-at-write: a Write that adds one line to a 200-note file is logged noted once, not refused",
           "full", "Write",
           lambda repo: {"file_path": old_file(repo), "content": FULL_LINES + "- nt-full-200: a new note\n"}, adds=True)
note_check("note-form-at-write: a Write that adds a line of prose to the old notes file is logged noted, not refused",
           "one", "Write",
           lambda repo: {"file_path": old_file(repo), "content": BASE_LINES + "A sentence that is no note.\n"}, adds=True)

# Controls: none of these adds a line to the old notes file, so each passes silently and logs no noted line for RULE.
note_check("note-form-at-write: an Edit that deletes a note line from the old notes file passes silently",
           "one", "Edit",
           lambda repo: {"file_path": old_file(repo), "old_string": "- nt-other: other note\n", "new_string": ""},
           adds=False)
note_check("note-form-at-write: a Write that adds a new note file under the note folder passes silently",
           "one", "Write",
           lambda repo: {"file_path": os.path.join(repo, NOTE_DIR, "nt-new-five.md"),
                         "content": "- nt-new-five: a note in its own file\n"}, adds=False)
note_check("note-form-at-write: a Write that adds only a blank line to the old notes file passes silently",
           "one", "Write",
           lambda repo: {"file_path": old_file(repo), "content": BASE_LINES + "\n"}, adds=False)
note_check("note-form-at-write: a Write that reorders the lines of the old notes file passes silently",
           "one", "Write",
           lambda repo: {"file_path": old_file(repo), "content": "- nt-other: other note\n- nt-base: base note\n"},
           adds=False)
note_check("note-form-at-write: a Write to a debt record, not the old notes file, passes silently",
           "one", "Write",
           lambda repo: {"file_path": os.path.join(repo, DEBT_DIR, "nt-debt-record.md"),
                         "content": "- nt-debt-line: a note-shaped line in a debt record\n"}, adds=False)

LOG_FAMILY.update({label: _family(label) for label, _check in NOTE_LOG_CHECKS})  # GUARD_FAMILY selects by it
LOG_CHECKS = LOG_CHECKS + tuple(NOTE_LOG_CHECKS)

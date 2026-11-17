# section 43501
FAMILY = "brief-ids-in-roster"  # the role-word brief cases, and the decision record checks at the end of this section

# ---- Session roster at start (decision brief-ids-in-roster, which holds the ruling and its time). Three parts:
# 1. A brief to a standing session (triage, batch runner) whose first line is a role-word line (`Brief:`,
#    `Triage brief:`, `Batch runner brief:`) is read by the bare-id check, as a Grant or Lane brief is. The quote escape
#    is unchanged.
# 2. A send_message whose target session_id is not in the roster for the sender's repo is refused (rule
#    target-id-in-roster). The roster is the record rows (the Standing sessions rows of CLAUDE.md on the roadmap ref),
#    plus the ids the sender's own transcript shows from list_sessions, get_session and create_session results tagged
#    with the sender's cs-repo. A lane's id on a lane notes line is no row, so it is not in the roster.
# 3. The decision record holds the owner's words, the ruling's time, the SessionStart roster and the target check.
#
# The fixtures are section 43300's roster repos (roster_repo, ROSTER_REPO, ROSTER_FULL, ROSTER_EMPTY, ROSTER_UNREADABLE)
# and section 13406's transcript helpers (role_use, role_result, role_record, role_call, role_wrapped). Each transcript
# case runs as a sender whose own record carries the cs-repo tag of the roster repo's origin, so the origin and the record
# agree. Every case that is not a log check is judged by the real guard as a child run (decide), so a deny that is
# missing shows as "expected deny, got allow", an assert, and never as a crash.

# ---- Part 1: a standing session's brief, opened by a role word, is read for a bare id.
roster_send("brief-ids-in-roster: a Triage brief to the triage session that names a wrong id is refused", "deny",
            "Triage brief: step brief-ids-from-roster.\nWake the triage session as " + ROSTER_WRONG + ".",
            target=ROSTER_TRIAGE, bad=ROSTER_WRONG)
roster_send("brief-ids-in-roster: a Batch runner brief to batch runner 10 that names its roster id is refused", "deny",
            "Batch runner brief: step brief-ids-from-roster.\nRunner 10 is " + ROSTER_RUNNER + ".",
            target=ROSTER_RUNNER, bad=ROSTER_RUNNER)
roster_send("brief-ids-in-roster: a Brief line to batch runner 10 that names a wrong id is refused", "deny",
            "Brief: step brief-ids-from-roster.\nRunner 10 is " + ROSTER_WRONG + ".",
            target=ROSTER_RUNNER, bad=ROSTER_WRONG)
roster_send("brief-ids-in-roster: a bold Triage brief line, with a wrong id on a later line, is refused", "deny",
            "**Triage brief:** step brief-ids-from-roster.\nWake " + ROSTER_WRONG,
            target=ROSTER_TRIAGE, bad=ROSTER_WRONG)
# The Grant and Lane brief readers stay as they are: a Grant brief to triage with a wrong id is still refused.
roster_send("brief-ids-in-roster: a Grant and Task message to triage that names a wrong id is still refused", "deny",
            GRANT_TASK + "Triage is " + ROSTER_WRONG + ".", target=ROSTER_TRIAGE, bad=ROSTER_WRONG)
# Green controls: a role-word brief that names a role and a slug, or a quoted wrong id, passes.
roster_send("brief-ids-in-roster: a Triage brief that names only a role and a slug is allowed", "allow",
            "Triage brief: step brief-ids-from-roster.\nAsk the batch runner 10 for the coordinator's ruling.",
            target=ROSTER_TRIAGE)
roster_send("brief-ids-in-roster: a Triage brief whose wrong id sits in backticks is allowed", "allow",
            "Triage brief: step brief-ids-from-roster.\nWrong id: `" + ROSTER_WRONG + "`.", target=ROSTER_TRIAGE)
roster_send("brief-ids-in-roster: a Batch runner brief whose wrong id sits in double quotes is allowed", "allow",
            'Batch runner brief: step brief-ids-from-roster.\nWrong id: "' + ROSTER_WRONG + '".', target=ROSTER_RUNNER)

# ---- Part 2: the target check. A send_message whose target id is not in the sender's roster is refused.
FAMILY = "target-id-in-roster"
TARGET_RULE = "target-id-in-roster"
TGT_SELF = "session_ROSTERSELF01"  # the sender: its own record carries the cs-repo tag of the roster repo's origin
TGT_SELF_ENV = {"CLAUDE_CODE_REMOTE_SESSION_ID": "cse_ROSTERSELF01"}
TGT_REPO_TAG = "cs-repo:" + "/".join(LANE_ORIGINS[LANE_REPO].split("/")[-2:])  # the tag of ROSTER_REPO's origin
TGT_OTHER_TAG = "cs-repo:example-org/other-repo"  # a repo the sender is not in
TGT_NEAR_LANE = ROSTER_LANE[:-1] + "8"  # the lane's id with its last character changed (ROSTER_LANE ends in 9)
TGT_MESSAGE = "Status: PR 12 merged."  # no lane opener, so no brief rule reads it
TGT_DIR = os.path.join(ROOT, "targetrec")
TGT_RECORD_ROWS = (ROSTER_COORD, ROSTER_TRIAGE, ROSTER_RUNNER)  # the three record rows of ROSTER_REPO


def tgt_path(name):
    return os.path.join(TGT_DIR, name + ".jsonl")


def tgt_list(tool_id, rows, wrapped=True):
    """A list_sessions result in the ccr.data shape: its rows, each with an id and its tags. `wrapped` returns it as
    another session's text comes back, inside the untrusted wrapper, and False returns the bare JSON."""
    body = json.dumps({"ccr": {"data": [{"id": sid, "session_status": "SESSION_STATUS_RUNNING", "tags": tags}
                                        for sid, tags in rows], "has_more": False}})
    return [role_use(tool_id, LIST_SESSIONS), role_result(tool_id, role_wrapped(body) if wrapped else body)]


def tgt_get(tool_id, sid, tags):
    """A get_session result for another session, `sid`, whose record carries `tags`."""
    return [role_use(tool_id, GET_SESSION, {"session_id": sid}),
            role_result(tool_id, role_wrapped(role_record(tags, sid, "a lane")))]


def tgt_create(tool_id, tags, sid):
    """A create_session call with `tags`, and its result naming the new session `sid`."""
    return [role_use(tool_id, CREATE_SESSION, {"tags": tags}), role_result(tool_id, json.dumps({"id": sid}))]


TGT_OWN = role_call("own", ["cs-build:coordinator", TGT_REPO_TAG], session=TGT_SELF, title="the sender")
TGT_LINES = {
    "own-only": TGT_OWN,
    "list-same": TGT_OWN + tgt_list("l1", [(ROSTER_LANE, ["cs-build:lane", TGT_REPO_TAG])]),
    "list-same-bare": TGT_OWN + tgt_list("l1", [(ROSTER_LANE, ["cs-build:lane", TGT_REPO_TAG])], wrapped=False),
    "list-other": TGT_OWN + tgt_list("l1", [(ROSTER_LANE, ["cs-build:lane", TGT_OTHER_TAG])]),
    "get-same": TGT_OWN + tgt_get("g1", ROSTER_LANE, ["cs-build:lane", TGT_REPO_TAG]),
    "create-same": TGT_OWN + tgt_create("c1", ["cs-build:lane", TGT_REPO_TAG], ROSTER_LANE),
    "create-other": TGT_OWN + tgt_create("c1", ["cs-build:lane", TGT_OTHER_TAG], ROSTER_LANE),
}
TGT_PARENT = "session_PARENT01"  # the parent_session_id that role_record writes into every own record


def write_tgt_transcripts():
    os.makedirs(TGT_DIR, exist_ok=True)
    for name, lines in TGT_LINES.items():
        write(tgt_path(name), "\n".join(lines) + "\n")


lazy_fixture([tgt_path(name) for name in TGT_LINES], write_tgt_transcripts)


def tgt_send(name, expected, target, transcript=None, cwd=ROSTER_REPO, env=None, carries=(), lacks=()):
    """A send_message to `target`, judged by the target check. A deny names its rule and prints `carries`, and
    never `lacks`. An allow must print nothing."""
    base = dict(tool=ROSTER_SEND, cwd=cwd, session_id=target, message=TGT_MESSAGE, transcript=transcript, env=env)
    if expected == "deny":
        add(name, "deny", rule=TARGET_RULE, carries=carries, lacks=lacks, **base)
    else:
        add(name, "allow", silent=True, **base)


# Deny. The record rows are always in the roster, so a refusal with a record of rows prints them.
tgt_send("target-id-in-roster: a target one character off a record row is refused, and the refusal prints the rows",
         "deny", ROSTER_NEAR, carries=TGT_RECORD_ROWS, lacks=(ROSTER_NEAR,))
tgt_send("target-id-in-roster: a target in no source is refused while the sender's transcript is readable", "deny",
         ROSTER_WRONG, transcript=tgt_path("own-only"), env=TGT_SELF_ENV, carries=TGT_RECORD_ROWS, lacks=(ROSTER_WRONG,))
tgt_send("target-id-in-roster: a lane id that sits only on a lane notes line is refused", "deny", ROSTER_LANE,
         carries=TGT_RECORD_ROWS, lacks=(ROSTER_LANE,))
tgt_send("target-id-in-roster: a lane id seen only on a list row tagged with another repo is refused", "deny",
         ROSTER_LANE, transcript=tgt_path("list-other"), env=TGT_SELF_ENV, carries=TGT_RECORD_ROWS, lacks=(ROSTER_LANE,))
tgt_send("target-id-in-roster: a target one character off a listed id is refused", "deny", TGT_NEAR_LANE,
         transcript=tgt_path("list-same"), env=TGT_SELF_ENV, carries=TGT_RECORD_ROWS, lacks=(TGT_NEAR_LANE,))
# Full size: the five rows of the full roster are all printed, and a wrong id beside them is refused.
tgt_send("target-id-in-roster: a wrong id beside the full roster's five rows is refused, and all five rows print", "deny",
         ROSTER_WRONG, cwd=ROSTER_FULL, carries=tuple(FULL_IDS), lacks=(ROSTER_WRONG,))
# Empty: the section holds only the template's placeholders, so a runner id names no row.
tgt_send("target-id-in-roster: a runner id is refused against an empty roster that holds placeholders only", "deny",
         ROSTER_RUNNER, cwd=ROSTER_EMPTY)

# Allow. A record row passes with no transcript; a lane seen in any of the three transcript results passes.
tgt_send("target-id-in-roster: a target that is a record row is allowed", "allow", ROSTER_RUNNER)
tgt_send("target-id-in-roster: the full roster's fifth row is allowed", "allow", ROSTER_ARBITER, cwd=ROSTER_FULL)
tgt_send("target-id-in-roster: a lane seen on a list row tagged with the sender's repo is allowed", "allow", ROSTER_LANE,
         transcript=tgt_path("list-same"), env=TGT_SELF_ENV)
tgt_send("target-id-in-roster: a lane seen on a bare list row tagged with the sender's repo is allowed", "allow", ROSTER_LANE,
         transcript=tgt_path("list-same-bare"), env=TGT_SELF_ENV)
tgt_send("target-id-in-roster: a lane seen on a get_session record tagged with the sender's repo is allowed", "allow",
         ROSTER_LANE, transcript=tgt_path("get-same"), env=TGT_SELF_ENV)
tgt_send("target-id-in-roster: a lane seen on a create_session result tagged with the sender's repo is allowed", "allow",
         ROSTER_LANE, transcript=tgt_path("create-same"), env=TGT_SELF_ENV)
# The parent. The alias and the id the sender's own get_session names as its parent pass, with no list read.
tgt_send("target-id-in-roster: the parent alias @parent is allowed", "allow", "@parent", cwd=ROSTER_REPO)
tgt_send("target-id-in-roster: the parent alias parent is allowed", "allow", "parent", cwd=ROSTER_REPO)
tgt_send("target-id-in-roster: the parent id that the sender's own get_session names is allowed", "allow", TGT_PARENT,
         transcript=tgt_path("own-only"), env=TGT_SELF_ENV)
# A lane the sender created passes whatever cs-repo tag it carries: the create_session result is the sender's own sighting.
tgt_send("target-id-in-roster: a lane the sender created, tagged with another repo's cs-repo, is allowed", "allow",
         ROSTER_LANE, transcript=tgt_path("create-other"), env=TGT_SELF_ENV)

# Fail open: neither source can be read. The send is allowed, and one stderr line says the roster is unknown. decide
# drops a run's stderr, so this check runs the guard through a wrapper that writes its stderr to a file, and reads it.
TGT_WRAP_DIR = os.path.join(ROOT, "targetwrap")
TGT_WRAP = os.path.join(TGT_WRAP_DIR, "guard_stderr.py")
TGT_WRAP_SOURCE = (
    "import os, subprocess, sys\n"
    "run = subprocess.run([sys.executable, os.environ['TGT_GUARD']], input=sys.stdin.read(),\n"
    "                     capture_output=True, text=True)\n"
    "with open(os.environ['TGT_STDERR'], 'w', encoding='utf-8') as handle:\n"
    "    handle.write(run.stderr)\n"
    "sys.stdout.write(run.stdout)\n"
    "sys.exit(run.returncode)\n")


def build_tgt_wrap():
    write(TGT_WRAP, TGT_WRAP_SOURCE)


lazy_fixture([TGT_WRAP], build_tgt_wrap)


def tgt_stderr_check():
    """The roadmap ref is unreadable and the transcript is a folder: the send is allowed, and stderr holds one line
    that says the roster is unknown. Unknown, never clear."""
    stderr_file = os.path.join(TGT_WRAP_DIR, "unreadable.stderr")
    got, reason = decide({
        "raw": None, "tool": ROSTER_SEND, "cwd": ROSTER_UNREADABLE, "session": None, "env_path": None,
        "config": None, "agent_id": None, "agent_type": None, "temp": None, "load": None,
        "transcript": role_path("unreadable"), "guard": TGT_WRAP,
        "env": {"TGT_GUARD": GUARD, "TGT_STDERR": stderr_file},
        "tool_input": {"session_id": ROSTER_WRONG, "message": TGT_MESSAGE},
    })
    if got != "allow":
        return False, "expected allow with neither source readable, got %s (%s)" % (got, reason[:70])
    if reason:
        return False, "the allow printed %r on stdout, want nothing" % reason[:70]
    if not os.path.exists(stderr_file):
        return False, "the guard run wrote no stderr file"
    with open(stderr_file, encoding="utf-8") as handle:
        lines = [line for line in handle.read().splitlines() if line.strip()]
    if len(lines) != 1:
        return False, "expected one stderr line, found %d" % len(lines)
    if "unknown" not in lines[0].lower():
        return False, "the stderr line does not say unknown: %r" % lines[0][:120]
    return True, "allowed with neither source readable, and one stderr line that says unknown"


def tgt_override_check():
    """The owner types `override`: one refusal of the target check is lifted once, then it is refused again (decision
    owner-override). The story runs on one fixed clock, so no real time is read."""
    config, session = ov_config("target-roster"), "ov-target-roster"

    def call(seconds):
        return lambda: ov_call(ROSTER_SEND, {"session_id": ROSTER_NEAR, "message": TGT_MESSAGE}, ROSTER_REPO,
                               config, session, seconds)

    ok, why = ov_story([("with no override", call(0), "deny", TARGET_RULE)])
    if not ok:
        return False, why
    note = ov_type(config, session, "override")
    ok, why = ov_story([("first call, under the override", call(60), "allow", TARGET_RULE),
                        ("second call, override spent", call(120), "deny", TARGET_RULE)], note)
    if not ok:
        return False, why
    return True, "%s refused, allowed once under the override, then refused again" % ROSTER_NEAR


# LOG_CHECKS_EXTRA joined LOG_CHECKS in section 40805, so these log checks join LOG_CHECKS here, with their family set.
TGT_STDERR_LABEL = "target-id-in-roster: neither source readable allows the send and prints one stderr line that says unknown"
TGT_OVERRIDE_LABEL = "target-id-in-roster: an owner override lifts one refusal, once"
LOG_FAMILY[TGT_STDERR_LABEL] = FAMILY
LOG_FAMILY[TGT_OVERRIDE_LABEL] = FAMILY
LOG_CHECKS = LOG_CHECKS + ((TGT_STDERR_LABEL, tgt_stderr_check), (TGT_OVERRIDE_LABEL, tgt_override_check))

# ---- Part 3: the decision record. It holds the owner's words, the ruling's time, the SessionStart roster and the target
# check. Each check names one line of the record, so a failure names one missing part.
FAMILY = "brief-ids-in-roster"
TGT_RECORD = os.path.join(REPO, "docs", "decisions", "brief-ids-in-roster.md")


def tgt_record_check(needle):
    def check():
        with open(TGT_RECORD, encoding="utf-8") as handle:
            text = handle.read()
        if needle in text:
            return True, "the record holds %r" % needle
        return False, "the record does not hold %r" % needle
    return check


RECORD_CHECKS = (
    ("brief-ids-in-roster record: holds the owner's words of 2026-11-15",
     "yeah i lean towards wanting both as both is kinda vlaid"),
    ("brief-ids-in-roster record: names the ruling time 2026-11-15 13:30 CST", "2026-11-15 13:30 CST"),
    ("brief-ids-in-roster record: names the SessionStart roster", "SessionStart roster"),
    ("brief-ids-in-roster record: names the target-id-in-roster check", "target-id-in-roster"))
for _label, _needle in RECORD_CHECKS:
    LOG_FAMILY[_label] = FAMILY
LOG_CHECKS = LOG_CHECKS + tuple((_label, tgt_record_check(_needle)) for _label, _needle in RECORD_CHECKS)

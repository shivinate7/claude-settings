# section 43502
FAMILY = "fg-bash-while-bg"
#
# A foreground Bash call that can run long is refused while background work runs in this session. The owner's
# decision fg-bash-while-bg, verbatim: "refuse only commands that can run long, such as tests, lint, merges,
# builds and installs, or anything asking a time limit over 60 s. Quick reads stay in the foreground."
#
# Background work is a background command or a background agent of this session, read from the session's own
# transcript (the payload's transcript_path). A background command is one started with run_in_background, or one
# that its own timeout moved to the background. A background agent is one launched async. Each keeps running until
# its terminal task notice arrives, or a TaskStop call stops it. A call is foreground when run_in_background is
# absent or false. Its limit is the tool input's `timeout`, in milliseconds.
#
# The refusal names the rule and says: refused in the foreground while background work runs; rerun it with
# run_in_background and it is allowed. The transcripts are fixed records with fixed stamps, so no clock is read.

FG_RULE = "fg-bash-while-bg"
FG_CARRIES = ("refused in the foreground while background work runs", "run_in_background")
FG_CWD = NOGIT  # an ordinary folder, not a git tree, as the other Bash cases use
FG_DIR = os.path.join(ROOT, "fg-bash-while-bg")
FG_OUT = os.path.join(FG_DIR, "job.output")  # the output file a launch names
FG_LAUNCHED = "2026-11-16T13:00:00.000Z"
FG_LATER = "2026-11-16T13:05:00.000Z"


def fg_path(name):
    return os.path.join(FG_DIR, name + ".jsonl")


def fg_use(call_id, name, tool_input):
    """An assistant record that calls a tool."""
    return {"type": "assistant", "timestamp": FG_LAUNCHED, "message": {"role": "assistant", "content": [
        {"type": "tool_use", "id": call_id, "name": name, "input": tool_input}]}}


def fg_result(call_id, text, tur, stamp=FG_LATER):
    """The user record that answers a call, with its structured toolUseResult."""
    return {"type": "user", "timestamp": stamp, "message": {"role": "user", "content": [
        {"type": "tool_result", "tool_use_id": call_id, "content": text, "is_error": False}]},
        "toolUseResult": tur}


def fg_bash(call_id, command, background=False):
    """A Bash call. background sets run_in_background, as the harness records it."""
    tool_input = {"command": command, "description": "fg-bash-while-bg test"}
    if background:
        tool_input["run_in_background"] = True
    return fg_use(call_id, "Bash", tool_input)


def fg_plain(call_id, command):
    """A foreground call that ends with no background id."""
    return [fg_bash(call_id, command),
            fg_result(call_id, "notes.txt", {"stdout": "notes.txt", "stderr": "", "interrupted": False})]


def fg_launch(call_id, job_id, moved=False):
    """A shell that runs in the background. moved: the call's own timeout moved it there, and the result says so."""
    tur = {"stdout": "", "stderr": "", "interrupted": False, "backgroundTaskId": job_id}
    if moved:
        tur["timedOutAfterMs"] = 120000
        text = ("Command did not complete within its 120s timeout and was moved to the background (ID: %s). "
                "Output is being written to: %s. You will be notified when it finishes." % (job_id, FG_OUT))
    else:
        text = "Command running in background with ID: %s. Output is being written to: %s" % (job_id, FG_OUT)
    return fg_result(call_id, text, tur)


def fg_notice(job_id, status):
    """The completion notice of a background task, as the transcript holds it: a user message with a string."""
    text = ("<task-notification>\n<task-id>%s</task-id>\n<tool-use-id>toolu_%s</tool-use-id>\n"
            "<output-file>%s</output-file>\n<status>%s</status>\n"
            "<summary>fg-bash-while-bg test</summary>\n</task-notification>" % (job_id, job_id, FG_OUT, status))
    return {"type": "user", "timestamp": FG_LATER, "message": {"role": "user", "content": text}}


def fg_stop(call_id, job_id):
    """A TaskStop call that stops the task job_id, and its result."""
    body = {"message": "Successfully stopped task: %s (sleep 600)" % job_id, "task_id": job_id,
            "task_type": "local_bash", "command": "sleep 600"}
    return [fg_use(call_id, "TaskStop", {"task_id": job_id}),
            fg_result(call_id, json.dumps(body), {"message": body["message"], "task_id": job_id})]


def fg_agent(call_id, agent_id):
    """A background agent launched async, and its launch result."""
    tur = {"isAsync": True, "status": "async_launched", "agentId": agent_id, "outputFile": FG_OUT}
    return [fg_use(call_id, "Agent", {"description": "fg-bash-while-bg test", "prompt": "fg-bash-while-bg test",
                                      "subagent_type": "general-purpose", "run_in_background": True}),
            fg_result(call_id, "Async agent launched successfully.\nagentId: %s" % agent_id, tur)]


# One transcript per state of this session's work. Each is a fixture, built once when a case names its path.
FG_LINES = {
    "idle": fg_plain("idle1", "ls -la"),
    "bg-running": [fg_bash("bg1", "sleep 600", background=True), fg_launch("bg1", "bgjob1")],
    "bg-moved": [fg_bash("mv1", "sleep 600"), fg_launch("mv1", "mvjob1", moved=True)],
    "bg-done": [fg_bash("done1", "sleep 600", background=True), fg_launch("done1", "donejob1"),
                fg_notice("donejob1", "completed")],
    "bg-stopped": [fg_bash("stop1", "sleep 600", background=True), fg_launch("stop1", "stopjob1")]
                  + fg_stop("stop2", "stopjob1"),
    "agent-running": fg_agent("agent1", "agentrun1"),
    "agent-done": fg_agent("agent2", "agentdone1") + [fg_notice("agentdone1", "completed")],
}


def write_fg_transcripts():
    for name, records in FG_LINES.items():
        write(fg_path(name), "\n".join(json.dumps(record) for record in records) + "\n")


lazy_fixture([fg_path(name) for name in FG_LINES], write_fg_transcripts)


def fg_refuse(name, command, transcript, **fields):
    """A foreground call the rule refuses: the reason names the rule and says to rerun it with run_in_background."""
    add(name, "deny", rule=FG_RULE, carries=FG_CARRIES, cwd=FG_CWD, transcript=transcript, command=command,
        **fields)


def fg_allow(name, command, transcript, silent=False, **fields):
    """A call the rule lets through. silent: the allow must print nothing."""
    add(name, "allow", cwd=FG_CWD, transcript=transcript, command=command, silent=silent, **fields)


# The long forms. A foreground run of each is refused while background work runs. The lane lint's bound comes from
# section 6590, the one home of it. A backgrounded lane lint needs a limit above that bound (rule check-timeout).
# A foreground lane lint is refused by check-timeout at any limit, with or without background work, so the
# foreground allow cases below leave it out.
FG_LONG = (
    ("verdict", "verdict python3 hooks/test_guard.py"),
    ("merge --lane-lint", CHECK_TIMEOUT_LINT),
    ("merge N --confirm", "merge 3270 --confirm"),
    ("pytest", "pytest hooks/test_stall_watch.py"),
    ("npm test", "npm test"),
    ("npm run build", "npm run build"),
    ("npm run lint", "npm run lint"),
    ("make", "make check"),
    ("xcodebuild", "xcodebuild -scheme Degen build"),
    ("pip install", "pip install -r requirements.txt"),
    ("npm install", "npm install"),
)
# The roster additions of decision fg-bash-while-bg, and the shapes the roster must read through: a grouped command and a
# wrapper (`timeout`, `nice`, `ionice`). The three loops below run each form in every state that FG_LONG forms run in.
FG_LONG_ROSTER = (
    ("grouped npm test", "(npm test)"),
    ("grouped pytest", "(pytest)"),
    ("grouped cd and npm test", "(cd x && npm test)"),
    ("timeout 120 npm test", "timeout 120 npm test"),
    ("nice and ionice pytest", "nice -n 19 ionice -c3 pytest"),
    ("ruff check", "ruff check ."),
    ("pre-commit run", "pre-commit run --all-files"),
    ("black --check", "black --check ."),
    ("rspec", "rspec spec/"),
    ("deno test", "deno test"),
    ("docker build", "docker build -t app ."),
    ("git clone", "git clone https://example.invalid/repo.git"),
)
FG_LONG_ALL = FG_LONG + FG_LONG_ROSTER
FG_LONG_LIMIT = {"merge --lane-lint": {"timeout": CHECK_TIMEOUT_MS}}
FG_LONG_FOREGROUND_ALLOWED = tuple(item for item in FG_LONG_ALL if item[0] not in FG_LONG_LIMIT)
FG_QUICK = (
    ("git status", "git status"),
    ("cat", "cat notes.txt"),
    ("grep", "grep -n needle notes.txt"),
    ("ls", "ls -la"),
    ("now-central", "~/.claude/bin/now-central"),
)

# DENY: a foreground long form while a background command runs.
for fg_label, fg_command in FG_LONG_ALL:
    fg_refuse("fg-bash-while-bg: a foreground %s is refused while a background command runs" % fg_label,
            fg_command, fg_path("bg-running"))
fg_refuse("fg-bash-while-bg: a foreground pytest is refused while a command its timeout moved to the background runs",
        "pytest hooks/test_stall_watch.py", fg_path("bg-moved"))
fg_refuse("fg-bash-while-bg: a foreground npm test with run_in_background false is refused while a background command runs",
        "npm test", fg_path("bg-running"), run_in_background=False)
# DENY: a foreground long form while a background agent runs.
fg_refuse("fg-bash-while-bg: a foreground verdict is refused while a background agent runs",
        "verdict python3 hooks/test_guard.py", fg_path("agent-running"))
fg_refuse("fg-bash-while-bg: a foreground npm test is refused while a background agent runs",
        "npm test", fg_path("agent-running"))
fg_refuse("fg-bash-while-bg: a foreground pytest is refused while a background agent runs",
        "pytest hooks/test_stall_watch.py", fg_path("agent-running"))
# DENY: any foreground call whose time limit is over 60000 ms, even a quick read, while a background command runs.
fg_refuse("fg-bash-while-bg: a foreground ls with a 60001 ms limit is refused while a background command runs",
        "ls -la", fg_path("bg-running"), timeout=60001)
fg_refuse("fg-bash-while-bg: a foreground git status with a 120000 ms limit is refused while a background command runs",
        "git status", fg_path("bg-running"), timeout=120000)
fg_refuse("fg-bash-while-bg: a foreground cat with the 600000 ms foreground maximum is refused while a background command runs",
        "cat notes.txt", fg_path("bg-running"), timeout=600000)

# ALLOW: the same long forms with run_in_background true while a background command runs.
for fg_label, fg_command in FG_LONG_ALL:
    fg_allow("fg-bash-while-bg: a %s with run_in_background true is allowed while a background command runs" % fg_label,
             fg_command, fg_path("bg-running"), run_in_background=True, **FG_LONG_LIMIT.get(fg_label, {}))

# ALLOW: a long form in the foreground with no background work: an idle session, and work that has ended.
for fg_label, fg_command in FG_LONG_FOREGROUND_ALLOWED:
    fg_allow("fg-bash-while-bg: a foreground %s is allowed with no background work" % fg_label,
             fg_command, fg_path("idle"))
fg_allow("fg-bash-while-bg: npm test is allowed once its background command has its completion notice",
         "npm test", fg_path("bg-done"))
fg_allow("fg-bash-while-bg: npm test is allowed once TaskStop has stopped its background command",
         "npm test", fg_path("bg-stopped"))
fg_allow("fg-bash-while-bg: npm test is allowed once its background agent has its completion notice",
         "npm test", fg_path("agent-done"))
fg_allow("fg-bash-while-bg: a foreground ls with a 120000 ms limit is allowed with no background work",
         "ls -la", fg_path("idle"), timeout=120000)

# ALLOW: quick reads in the foreground while background work runs.
for fg_label, fg_command in FG_QUICK:
    fg_allow("fg-bash-while-bg: a quick read, %s, is allowed in the foreground while a background command runs" % fg_label,
             fg_command, fg_path("bg-running"), silent=True)
fg_allow("fg-bash-while-bg: a quick read, git status, is allowed in the foreground while a background agent runs",
         "git status", fg_path("agent-running"), silent=True)
fg_allow("fg-bash-while-bg: a quick read with a 60000 ms limit, the boundary, is allowed in the foreground while background work runs",
         "ls -la", fg_path("bg-running"), timeout=60000, silent=True)
fg_allow("fg-bash-while-bg: a quick read with a 120000 ms limit under run_in_background is allowed while background work runs",
         "ls -la", fg_path("bg-running"), run_in_background=True, timeout=120000)

# ALLOW: a version or help read, and a git network call, stay in the foreground while background work runs. A version
# or help flag runs no test, lint or build. A git fetch or push is a network call, not a long run.
FG_NOT_LONG = (
    ("pytest --version", "pytest --version", True),
    ("tsc -v", "tsc -v", True),
    ("make --help", "make --help", True),
    ("mypy --version", "mypy --version", True),
    ("git fetch", "git fetch origin", False),
    ("git push", "git push origin HEAD:example-branch", False),
)
for fg_label, fg_command, fg_silent in FG_NOT_LONG:
    fg_allow("fg-bash-while-bg: a %s is allowed in the foreground while a background command runs" % fg_label,
             fg_command, fg_path("bg-running"), silent=fg_silent)

# SHAPES. A test tool's verbose flag runs its tests, so `pytest -v` and `flake8 -v` are long. A dry run, a help flag and
# a `command -v` lookup run nothing, so they stay quick. A flag that takes a value, such as `npm -w web test`, does not
# end the command: the test or build script after it still counts. A test file named by a plain word, `test.py`, counts.
FG_SHAPE_LONG = (
    "pytest -v", "flake8 -v", "pytest -v tests", "python3 test.py", "python3 tests/run.py", "bash test.sh",
    "./test.sh", "node test.js", "node --test", "bash tests/run.sh", "npm --prefix web test", "npm -w web test",
    "pnpm --filter x build", "yarn --cwd web test",
)
for fg_command in FG_SHAPE_LONG:
    fg_refuse("fg-bash-while-bg: a foreground %s is refused while a background command runs" % fg_command,
              fg_command, fg_path("bg-running"))
FG_SHAPE_QUICK = (
    "command -v pytest", "command -v make", "xcodebuild -version", "xcodebuild -showsdks", "make -n", "pytest -h",
)
for fg_command in FG_SHAPE_QUICK:
    fg_allow("fg-bash-while-bg: a foreground %s is allowed in the foreground while a background command runs" % fg_command,
             fg_command, fg_path("bg-running"), silent=True)

# AGENT AND TRANSCRIPT PINS. A call from an agent is not judged: its payload carries agent_id and agent_type, and the
# transcript is its parent's. The bg-running transcript holds a background command, so only the agent fields exempt
# this call.
fg_allow("fg-bash-while-bg: a foreground npm test from an agent, with agent_id and agent_type, is not judged while a background command runs",
         "npm test", fg_path("bg-running"), agent_id="agentpin1", agent_type="general-purpose")
fg_allow("fg-bash-while-bg: a foreground npm test from an agent, with agent_type and no agent_id, is not judged while a background command runs",
         "npm test", fg_path("bg-running"), agent_type="general-purpose")
# A missing transcript allows: the rule fails open. A payload with no transcript_path at all allows the same way.
fg_allow("fg-bash-while-bg: a foreground npm test is allowed when its transcript file is missing",
         "npm test", fg_path("missing"))
fg_allow("fg-bash-while-bg: a foreground npm test is allowed when the payload names no transcript",
         "npm test", None)

# POWERSHELL PINS. The PowerShell tool is judged the same as Bash: a long form with no background flag is refused
# while background work runs, and the same form with run_in_background is allowed.
fg_refuse("fg-bash-while-bg: a foreground Invoke-Pester on the PowerShell tool is refused while a background command runs",
          "Invoke-Pester -Path tests", fg_path("bg-running"), tool="PowerShell")
fg_refuse("fg-bash-while-bg: a foreground npm test on the PowerShell tool is refused while a background command runs",
          "npm test", fg_path("bg-running"), tool="PowerShell")
fg_allow("fg-bash-while-bg: a foreground Invoke-Pester on the PowerShell tool is allowed with no background work",
         "Invoke-Pester -Path tests", fg_path("idle"), tool="PowerShell")
fg_allow("fg-bash-while-bg: an Invoke-Pester on the PowerShell tool with run_in_background true is allowed while background work runs",
         "Invoke-Pester -Path tests", fg_path("bg-running"), run_in_background=True, tool="PowerShell")

# SCOPE. Each transcript holds the state its name says, so a case that branches on that state reads what it means.
# A fixture that lost its launch or its notice would turn a deny red for the wrong reason, so each state is checked
# on its own: the needles it must hold, and the ones its state must not hold.
def fg_scope_check(name, holds, lacks):
    def check():
        with open(fg_path(name), encoding="utf-8") as handle:
            text = handle.read()
        for needle in holds:
            if needle not in text:
                return False, "the %s transcript does not hold %r" % (name, needle)
        for needle in lacks:
            if needle in text:
                return False, "the %s transcript holds %r, which its state must not" % (name, needle)
        return True, "the %s transcript holds its state" % name
    return check


FG_SCOPE = (
    ("idle", "no background work", ("notes.txt",), ('"backgroundTaskId"', '"async_launched"', "<task-notification>")),
    ("bg-running", "a background command with no notice", ('"backgroundTaskId": "bgjob1"',),
     ("<task-notification>", "Successfully stopped")),
    ("bg-moved", "a command its timeout moved to the background", ('"timedOutAfterMs": 120000',
                                                                  "moved to the background"),
     ("<task-notification>",)),
    ("bg-done", "a background command with a completion notice", ('"backgroundTaskId": "donejob1"',
                                                                  "<status>completed</status>"), ()),
    ("bg-stopped", "a background command stopped by TaskStop", ('"backgroundTaskId": "stopjob1"',
                                                                 "Successfully stopped task: stopjob1"),
     ("<task-notification>",)),
    ("agent-running", "a background agent with no notice", ('"status": "async_launched"',
                                                             '"agentId": "agentrun1"'),
     ("<task-notification>",)),
    ("agent-done", "a background agent with a completion notice", ('"agentId": "agentdone1"',
                                                                   "<status>completed</status>"), ()),
)


def fg_absent_check(name):
    """The file a missing-transcript case names must not exist, or that case reads a transcript after all."""
    def check():
        if os.path.exists(fg_path(name)):
            return False, "the %s transcript exists, so the missing-transcript case reads a file that is there" % name
        return True, "the %s transcript is absent, as the missing-transcript case needs" % name
    return check


FG_SCOPE_CHECKS = tuple(
    ("fg-bash-while-bg scope: the %s transcript holds %s" % (name, state),
     fg_scope_check(name, holds, lacks))
    for name, state, holds, lacks in FG_SCOPE) + (
    ("fg-bash-while-bg scope: the missing transcript file is absent", fg_absent_check("missing")),)
for _fg_label, _fg_check in FG_SCOPE_CHECKS:
    LOG_FAMILY[_fg_label] = FAMILY
LOG_CHECKS = LOG_CHECKS + FG_SCOPE_CHECKS

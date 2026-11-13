# section 30130
FAMILY = "rule9"  # the cases after this section keep rule 9's family

# ---- Cost. The rule starts two git processes for a lane create_session: the origin/main blob read, then remote get-url
# when that blob names no repo (step guards-read-origin-main-config, the ruled bound of github_repo). It starts none for any
# other call. The probe counts each child process the judge starts (CountingPopen and the os seams). A child whose
# argv starts with git is one of the rule's reads of the repo.
def lane_cost_run(body):
    """(children, decision, reason, probe error) of one judge run on `body`, judged in the probe with its own folders."""
    os.makedirs(LB_DIR, exist_ok=True)
    run = tempfile.mkdtemp(dir=LB_DIR)
    try:
        side_file = os.path.join(run, "probe.json")
        cfg = os.path.join(run, "cfg")
        os.makedirs(cfg)
        env = dict(os.environ)
        env["CLAUDE_CONFIG_DIR"] = cfg
        env.pop("CLAUDE_CODE_SESSION_ID", None)
        env["CLAUDE_GUARD_ROOT_PID"] = str(os.getpid())
        spec = {"mode": "judge", "reading": LB_NORMAL}
        done = subprocess.run([sys.executable, "-c", LB_PROBE, GUARD, side_file, json.dumps(spec)],
                              input=json.dumps(body), capture_output=True, text=True, env=env, timeout=120)
        try:
            with open(side_file, "r", encoding="utf-8") as handle:
                side = json.load(handle)
        except Exception:
            return [], "", "", "the probe wrote nothing: " + done.stderr.strip()[-160:]
        decision, reason = read_decision(done.stdout)
        return side.get("children", []), decision, reason, side.get("probe_error", "")
    finally:
        shutil.rmtree(run, ignore_errors=True)


def is_git_child(child):
    return child.lstrip("[").lstrip("'\"").startswith("git")


def lane_cost_check(label, body, want_git, want_decision):
    def check():
        children, decision, _reason, error = lane_cost_run(body)
        if error:
            return False, "the probe failed: " + error
        git = [c for c in children if is_git_child(c)]
        if len(git) != want_git:
            return False, "%d git process(es), want %d: %s" % (len(git), want_git, (git or children)[:3])
        if decision != want_decision:
            return False, "decided %s, want %s" % (decision, want_decision)
        return True, "%d git process(es), decided %s" % (len(git), decision)
    LOG_CHECKS_EXTRA.append((label, check))


lane_cost_check("lane-repo-tag: a lane create_session starts two git processes, the origin/main blob read then remote get-url",
                {"tool_name": LANE_TOOL, "session_id": "lane-cost-lane", "cwd": LANE_REPO,
                 "tool_input": {"prompt": LANE_PROMPT, "effort": LANE_EFFORT_FIELD, "tags": OWN_LANE_TAGS,
                                "model": "sonnet", "source_url": LANE_SOURCE_URL}}, 2, "allow")
lane_cost_check("lane-repo-tag: a non-lane create_session starts no git process",
                {"tool_name": LANE_TOOL, "session_id": "lane-cost-triage", "cwd": LANE_REPO,
                 "tool_input": {"prompt": "/effort medium", "tags": ["cs-build:triage"]}}, 0, "allow")
lane_cost_check("lane-repo-tag: a Read call starts no git process",
                {"tool_name": "Read", "session_id": "lane-cost-read", "cwd": LANE_REPO,
                 "tool_input": {"file_path": os.path.join(LANE_REPO, "README.md")}}, 0, "allow")


# ---- Lane start settings. A create_session that tags a lane names the model the lane starts on and the repo it
# starts from (`source_url`). A lane call with no model, or no source_url, or either as an empty or blank string or as
# a value that is not text (null, a number, a list), is denied.
# A lane call with both passes. A call with no lane tag is never judged by this rule. Each lane case below carries
# the grant line, effort medium and the origin repo tag, so the other lane rules pass it and only this rule decides it.
add("lane-start-settings: lane tag with no model is denied", "deny", "lane-start-settings",
    tool=LANE_TOOL, cwd=LANE_REPO, prompt=LANE_PROMPT, effort=LANE_EFFORT_FIELD, tags=OWN_LANE_TAGS, source_url=LANE_SOURCE_URL)
add("lane-start-settings: lane tag with no source_url is denied", "deny", "lane-start-settings",
    tool=LANE_TOOL, cwd=LANE_REPO, prompt=LANE_PROMPT, effort=LANE_EFFORT_FIELD, tags=OWN_LANE_TAGS, model="sonnet")
add("lane-start-settings: lane tag with neither model nor source_url is denied", "deny", "lane-start-settings",
    tool=LANE_TOOL, cwd=LANE_REPO, prompt=LANE_PROMPT, effort=LANE_EFFORT_FIELD, tags=OWN_LANE_TAGS)
add("lane-start-settings: lane tag with an empty model is denied", "deny", "lane-start-settings",
    tool=LANE_TOOL, cwd=LANE_REPO, prompt=LANE_PROMPT, effort=LANE_EFFORT_FIELD, tags=OWN_LANE_TAGS,
    model="", source_url=LANE_SOURCE_URL)
add("lane-start-settings: lane tag with an empty source_url is denied", "deny", "lane-start-settings",
    tool=LANE_TOOL, cwd=LANE_REPO, prompt=LANE_PROMPT, effort=LANE_EFFORT_FIELD, tags=OWN_LANE_TAGS,
    model="sonnet", source_url="")
add("lane-start-settings: lane tag with an empty model and an empty source_url is denied", "deny",
    "lane-start-settings", tool=LANE_TOOL, cwd=LANE_REPO, prompt=LANE_PROMPT, effort=LANE_EFFORT_FIELD, tags=OWN_LANE_TAGS,
    model="", source_url="")
add("lane-start-settings: lane tag with a whitespace-only model is denied", "deny", "lane-start-settings",
    tool=LANE_TOOL, cwd=LANE_REPO, prompt=LANE_PROMPT, effort=LANE_EFFORT_FIELD, tags=OWN_LANE_TAGS,
    model="   ", source_url=LANE_SOURCE_URL)
add("lane-start-settings: lane tag with a whitespace-only source_url is denied", "deny", "lane-start-settings",
    tool=LANE_TOOL, cwd=LANE_REPO, prompt=LANE_PROMPT, effort=LANE_EFFORT_FIELD, tags=OWN_LANE_TAGS,
    model="sonnet", source_url=" \t\n ")
add("lane-start-settings: lane tag with a non-text model (null) is denied", "deny", "lane-start-settings",
    tool=LANE_TOOL, cwd=LANE_REPO, prompt=LANE_PROMPT, effort=LANE_EFFORT_FIELD, tags=OWN_LANE_TAGS,
    model=None, source_url=LANE_SOURCE_URL)
add("lane-start-settings: lane tag with a non-text model (number) is denied", "deny", "lane-start-settings",
    tool=LANE_TOOL, cwd=LANE_REPO, prompt=LANE_PROMPT, effort=LANE_EFFORT_FIELD, tags=OWN_LANE_TAGS,
    model=5, source_url=LANE_SOURCE_URL)
add("lane-start-settings: lane tag with a non-text model (list) is denied", "deny", "lane-start-settings",
    tool=LANE_TOOL, cwd=LANE_REPO, prompt=LANE_PROMPT, effort=LANE_EFFORT_FIELD, tags=OWN_LANE_TAGS,
    model=["x"], source_url=LANE_SOURCE_URL)
add("lane-start-settings: lane tag with a non-text source_url (null) is denied", "deny", "lane-start-settings",
    tool=LANE_TOOL, cwd=LANE_REPO, prompt=LANE_PROMPT, effort=LANE_EFFORT_FIELD, tags=OWN_LANE_TAGS,
    model="sonnet", source_url=None)
add("lane-start-settings: lane tag with a non-text source_url (number) is denied", "deny", "lane-start-settings",
    tool=LANE_TOOL, cwd=LANE_REPO, prompt=LANE_PROMPT, effort=LANE_EFFORT_FIELD, tags=OWN_LANE_TAGS,
    model="sonnet", source_url=5)
add("lane-start-settings: lane tag with a non-text source_url (list) is denied", "deny", "lane-start-settings",
    tool=LANE_TOOL, cwd=LANE_REPO, prompt=LANE_PROMPT, effort=LANE_EFFORT_FIELD, tags=OWN_LANE_TAGS,
    model="sonnet", source_url=["x"])
add("lane-start-settings: lane tag with a no-break-space-only model is denied", "deny", "lane-start-settings",
    tool=LANE_TOOL, cwd=LANE_REPO, prompt=LANE_PROMPT, effort=LANE_EFFORT_FIELD, tags=OWN_LANE_TAGS,
    model="\u00a0", source_url=LANE_SOURCE_URL)
add("lane-start-settings: lane tag with a no-break-space-only source_url is denied", "deny", "lane-start-settings",
    tool=LANE_TOOL, cwd=LANE_REPO, prompt=LANE_PROMPT, effort=LANE_EFFORT_FIELD, tags=OWN_LANE_TAGS,
    model="sonnet", source_url="\u00a0")
add("lane-start-settings: upper-case lane tag with no model is denied", "deny", "lane-start-settings",
    tool=LANE_TOOL, cwd=LANE_REPO, prompt=LANE_PROMPT, effort=LANE_EFFORT_FIELD,
    tags=["CS-BUILD:LANE", "cs-repo:shivinate7/claude-settings"], source_url=LANE_SOURCE_URL)
add("lane-start-settings: lane tag among several tags with no source_url is denied", "deny", "lane-start-settings",
    tool=LANE_TOOL, cwd=LANE_REPO, prompt=LANE_PROMPT, effort=LANE_EFFORT_FIELD,
    tags=["cs-repo:shivinate7/claude-settings", "cs-step:lane-start-settings", "cs-build:lane"], model="sonnet")
add("lane-start-settings: a denied lane with no source_url names source_url in its reason", "deny",
    "lane-start-settings", tool=LANE_TOOL, cwd=LANE_REPO, prompt=LANE_PROMPT, effort=LANE_EFFORT_FIELD, tags=OWN_LANE_TAGS,
    model="sonnet", carries="source_url")
add("lane-start-settings: a denied lane with no model names model in its reason", "deny",
    "lane-start-settings", tool=LANE_TOOL, cwd=LANE_REPO, prompt=LANE_PROMPT, effort=LANE_EFFORT_FIELD, tags=OWN_LANE_TAGS,
    source_url=LANE_SOURCE_URL, carries="model")
add("lane-start-settings: lane tag with a model and a source_url is allowed", "allow",
    tool=LANE_TOOL, cwd=LANE_REPO, prompt=LANE_PROMPT, effort=LANE_EFFORT_FIELD, tags=OWN_LANE_TAGS,
    model="sonnet", source_url=LANE_SOURCE_URL)
add("lane-start-settings: lane tag among several tags with a model and a source_url is allowed", "allow",
    tool=LANE_TOOL, cwd=LANE_REPO, prompt=LANE_PROMPT, effort=LANE_EFFORT_FIELD,
    tags=["cs-repo:shivinate7/claude-settings", "cs-step:lane-start-settings", "cs-build:lane"],
    model="sonnet", source_url=LANE_SOURCE_URL)
add("lane-start-settings: coordinator call with no model and no source_url is allowed", "allow",
    tool=LANE_TOOL, tags=["cs-build:coordinator"], prompt="do the task")
add("lane-start-settings: triage call with no model and no source_url is allowed", "allow",
    tool=LANE_TOOL, tags=["cs-build:triage"], prompt="do the task")
add("lane-start-settings: batch-runner call with no model and no source_url is allowed", "allow",
    tool=LANE_TOOL, tags=["cs-build:batch-runner"], prompt="do the task")

# ---- The floor's remedy for a lane start. A lane create_session below the floor is refused, and its reason must not
# tell the caller to name no model: with no model, rule lane-start-settings refuses the lane again. The reason names
# `model sonnet` and `source_url`, the lane's two required inputs. An Agent or Task spawn, a start_session, and a
# create_session with no lane tag keep the no-model remedy, so a builder cannot drop it for everyone.
LANE_FLOOR_LACKS = ("name no model", "let the default apply")
add("floor lane: a lane create_session on haiku is denied with the lane remedy, not the no-model one", "deny",
    "agent-model-floor", tool=LANE_TOOL, cwd=LANE_REPO, prompt=LANE_PROMPT, effort=LANE_EFFORT_FIELD, tags=OWN_LANE_TAGS,
    model="haiku", source_url=LANE_SOURCE_URL, carries="model sonnet", lacks=LANE_FLOOR_LACKS)
add("floor lane: a lane refused below the floor names source_url in its reason", "deny",
    "agent-model-floor", tool=LANE_TOOL, cwd=LANE_REPO, prompt=LANE_PROMPT, effort=LANE_EFFORT_FIELD, tags=OWN_LANE_TAGS,
    model="haiku", source_url=LANE_SOURCE_URL, carries="source_url")
add("floor lane: an upper-case lane tag on haiku gets the lane remedy", "deny", "agent-model-floor",
    tool=LANE_TOOL, cwd=LANE_REPO, prompt=LANE_PROMPT, effort=LANE_EFFORT_FIELD,
    tags=["CS-BUILD:LANE", "cs-repo:shivinate7/claude-settings"],
    model="haiku", source_url=LANE_SOURCE_URL, carries="model sonnet", lacks=LANE_FLOOR_LACKS)
add("floor lane: a lane tag given as one string on haiku gets the lane remedy", "deny", "agent-model-floor",
    tool=LANE_TOOL, cwd=LANE_REPO, prompt=LANE_PROMPT, effort=LANE_EFFORT_FIELD, tags="cs-build:lane",
    model="haiku", source_url=LANE_SOURCE_URL, carries="model sonnet", lacks=LANE_FLOOR_LACKS)
add("floor lane: a lane start on the remedy's inputs, model sonnet, source_url, the repo tag, the grant line and "
    "effort medium, is allowed", "allow", tool=LANE_TOOL, cwd=LANE_REPO, prompt=LANE_PROMPT, effort=LANE_EFFORT_FIELD, tags=OWN_LANE_TAGS,
    model="sonnet", source_url=LANE_SOURCE_URL)
# Controls: the no-model remedy holds wherever no lane is. These pass on the old code and must keep passing.
for _name, _call in (
        ("Agent", dict(tool="Agent", prompt="do it", model="haiku")),
        ("Task", dict(tool="Task", prompt="do it", model="haiku")),
        ("start_session", dict(tool="mcp__ccd_session__start_session", initiation="user_asked", prompt="x",
                               model="haiku")),
        ("create_session with no tags", dict(tool=CREATE_SESSION_CALL, prompt="x", model="haiku")),
        ("create_session with a triage tag", dict(tool=CREATE_SESSION_CALL, prompt="x", model="haiku",
                                                  tags=["cs-build:triage"]))):
    add("floor remedy: %s on haiku keeps the no-model remedy" % _name, "deny", "agent-model-floor",
        carries="let the default apply", **_call)

# ---- Rule 9, Workflow script. A role named in a string or label is no role;
# a quoted key is still a key; a haiku named in a string or comment is no model.
add("floor: Workflow role spoofed in the prompt string is denied", "deny", "agent-model-floor",
    tool="Workflow", script="await agent(\"use agentType: 'reviewer'\", {model:\"haiku\"})")
add("floor: Workflow role spoofed in the label is denied", "deny", "agent-model-floor",
    tool="Workflow",
    script="await agent(\"x\", {model:\"haiku\", label:\"agentType: 'reviewer'\"})")
add("floor: Workflow quoted model key with haiku is denied", "deny", "agent-model-floor",
    tool="Workflow", script="await agent(\"x\", {\"model\":\"haiku\"})")
add("floor: Workflow prompt text naming a haiku model on a sonnet agent is allowed", "allow",
    tool="Workflow", script="await agent(\"set model: 'haiku' in file\", {model:\"sonnet\"})")
add("floor: Workflow commented-out haiku agent call is allowed", "allow",
    tool="Workflow", script="// agent({model:\"haiku\"})\nawait agent(\"x\", {model:\"sonnet\"})")

# ---- Rule 9, template literals. Code inside a `${...}` is code: a quote there opens no string, and
# a haiku named in a template's own text is no model. Each expected deny lists a haiku spawn that
# a desynced scan would hide.
add("floor: Workflow haiku after a quote inside a template interpolation is denied", "deny",
    "agent-model-floor", tool="Workflow",
    script=r"""x = `${"`"}`;
x = 'a\"';
agent({model: `haiku`});""")
for _shape in (
        r'agent(`fix ${x ? "a" : "b"}`, {model: "haiku"})',
        'const q = `a ${`b ${c}`} d`;\nagent({prompt: q, model: "haiku"})',
        r'agent(`p ${obj["k"]}`, {model: "haiku"})',
        r'agent(`p ${ {a:1}.a }`, {model: "haiku"})'):
    add("floor: Workflow haiku after template shape %r is denied" % _shape[:40], "deny",
        "agent-model-floor", tool="Workflow", script=_shape)
add("floor: Workflow haiku named only in template text is not a model", "allow",
    tool="Workflow", script='agent(`set {model: "haiku"} in the file`, {model: "sonnet"})')
add("floor: Workflow agent call written inside template text is not a spawn", "allow",
    tool="Workflow", script='agent(`agent({model: "haiku"})`, {model: "sonnet"})')
# An interpolation is code, and a haiku value built inside it is still a model. An object literal
# inside `${}` is an expression, never the call's options.
add("floor: Workflow model from a template interpolation of 'haiku' is denied", "deny",
    "agent-model-floor", tool="Workflow", script="await agent(\"x\", {model: `${'haiku'}`})")
add("floor: Workflow model from a template with an interpolated haiku suffix is denied", "deny",
    "agent-model-floor", tool="Workflow", script="await agent(\"x\", {model: `${fam}-haiku`})")
add("floor: Workflow object literal inside a template interpolation is not call options", "allow",
    tool="Workflow", script='agent(`x ${ {model:"haiku"}.model }`, {model:"sonnet"})')

# F1. A regex literal inside a template interpolation holds a quote or a backtick. It is code, so it
# opens no string, and the haiku spawn after it must still deny.
add("floor: Workflow haiku after a regex with a quote inside a template interpolation is denied",
    "deny", "agent-model-floor", tool="Workflow",
    script=r"""x = `${ s.replace(/"/g, '') }`;
agent("x", {model: "haiku"})""")
add("floor: Workflow haiku after a regex with a backtick inside a template interpolation is denied",
    "deny", "agent-model-floor", tool="Workflow",
    script=r"""x = `${ s.replace(/`/g, '') }`;
agent("x", {model: "haiku"})""")

# A `/` after `++` or `--` is division, not a regex literal, so the string after it is still
# lexed and the haiku spawn after it must deny.
add("floor: Workflow haiku after i++ divided, then a path string, is denied", "deny",
    "agent-model-floor", tool="Workflow",
    script='i++ / 2; s = "a/b"; agent("x", {model: "haiku"})')
add("floor: Workflow haiku after i-- divided, then a path string, is denied", "deny",
    "agent-model-floor", tool="Workflow",
    script='i-- / 2; s = "a/b"; agent("x", {model: "haiku"})')

FORBIDDEN_IN_A_REASON = (ENV, ROOT, slash(ROOT),"settings.json", "CLAUDE.md", "guard.py",
                         ".claude", "app.log", "sleep", "haiku", VCS + " checkout", VCS + " switch")

# ONE RULE MAY NAME ITS SUBJECT, and only the fragments listed beside it. Rule 8 asks rather than
# refuses, and the ask exists to tell an approver what is being turned on and where, so the settings
# path is the point of the message. The exemption is keyed by RULE, never by case, so a new case
# cannot widen it, and a fragment left off this list, `CLAUDE.md` or `guard.py`, stays forbidden in
# rule 8's reason too.
REASON_MAY_NAME = {
    "agent-model-cap": (ROOT, slash(ROOT), "settings.json", ".claude"),
    # The refusal names the handoff the session must read: under the config folder, which is ROOT here
    # and ~/.claude in a session. That path is the remedy, so the rule may name its folder.
    "handoff-unread": (ROOT, slash(ROOT), ".claude"),
    # The refusal names the now-central helper a session reads the time from, ~/.claude/bin/now-central. That path
    # is the remedy, so the rule may name its folder, as handoff-unread does. The other fragments stay forbidden.
    "message-time-matches-clock": (".claude",),
    # The two-worktrees-one-branch remedy names `git switch -c <new-branch> <start>`: a branch of the
    # caller's own. The forbidden target is the held branch's checkout, not that create form. The check
    # matches a fragment as text, so this one entry permits `git switch` as a whole in this rule's reason.
    TWO_RULE: (VCS + " switch",),
    # The refusal names the missing sections and may name the handoff it judges: under the config folder.
    "handoff-sections": (ROOT, slash(ROOT), ".claude"),
    # The refusal names the premises it refuses and their Source tokens, and may name the handoff it judges, under the
    # config folder, as handoff-sections does.
    "handoff-checked-stamp": (ROOT, slash(ROOT), ".claude"),
}


def playwright_remedy_case():
    """The playwright refusal names the real check and points nowhere else.

    The remedy must name the stale `__dirlock` and `pgrep -f playwright`, the two checks that
    find the real cause. `pgrep -f` prints pids only. The `-fl` form prints full process arguments,
    which the process-args rule refuses, so the remedy must never name it. The remedy must not name
    the variable it refused, nor any path to set instead.
    """
    got, reason = decide({
        "raw": None, "tool": "Bash", "cwd": NOGIT, "session": None,
        "env_path": None,
        "tool_input": {"command": "PLAYWRIGHT_BROWSERS_PATH=/tmp/x npx playwright install chromium"},
    })
    if got != "deny":
        return False, "expected deny, got %s" % got
    if "pgrep -fl playwright" in reason:
        return False, "the remedy still names the refused form 'pgrep -fl playwright'"
    missing = [f for f in ("__dirlock", "pgrep -f playwright") if f not in reason]
    if missing:
        return False, "the remedy does not name %r: %s" % (missing[0], reason[:90])
    named = [f for f in ("PLAYWRIGHT_BROWSERS_PATH", "/tmp", "scratch", "C:\\") if f in reason]
    if named:
        return False, "the remedy names %r, a forbidden target or another path" % named[0]
    return True, "refused, and the remedy names the stale __dirlock and pgrep -f playwright"


def powershell_backslash_case():
    """Under PowerShell a backslash is a path separator, so tokenizing keeps it. Under Bash it is
    an escape, so it goes. The same text reads two ways, and the tool decides which."""
    guard = _load_guard_module()
    text = "cd C:\\repo; git commit -F C:\\tmp\\msg.txt"
    try:
        guard.POWERSHELL_CALL[0] = True
        ps = guard.segment_tokens(text)
        guard.POWERSHELL_CALL[0] = False
        sh_tokens = guard.segment_tokens(text)
    finally:
        guard.POWERSHELL_CALL[0] = False
    if ps != ["cd", "C:\\repo;", "git", "commit", "-F", "C:\\tmp\\msg.txt"]:
        return False, "PowerShell tokens lost a backslash: %r" % (ps,)
    if sh_tokens != ["cd", "C:repo;", "git", "commit", "-F", "C:tmpmsg.txt"]:
        return False, "Bash tokens changed: %r" % (sh_tokens,)
    return True, "PowerShell keeps backslashes, Bash eats them as an escape"


def wsl_script_tag_keeps_backslash_case():
    """segment_tokens reads a PowerShellScript's own tag, not only POWERSHELL_CALL, so a pwsh -c
    script keeps its backslashes with no PowerShell tool in play. Dropping that arm (guard_core
    318) makes shlex eat `C:\\tmp` to `C:tmp`. Lane swn-pwsh-escape, review round 2, item 3."""
    guard = _load_guard_module()
    script_type = getattr(sys.modules["guard_core"], "PowerShellScript", None)
    if script_type is None:   # a tree with no script tag fails this check, and does not crash the run
        return False, "guard_core has no PowerShellScript tag"
    guard.POWERSHELL_CALL[0] = False
    try:
        tokens = guard.segment_tokens(script_type(r"cd C:\repo; git commit -F C:\tmp\msg.txt"))
    finally:
        guard.POWERSHELL_CALL[0] = False
    if tokens != ["cd", "C:\\repo;", "git", "commit", "-F", "C:\\tmp\\msg.txt"]:
        return False, "a PowerShell script tag lost a backslash: %r" % (tokens,)
    return True, "a PowerShell script tag keeps its backslashes with no PowerShell tool"


def wsl_split_tag_keeps_backslash_case():
    """split_segments wraps each segment of a PowerShell script in the script's tag (guard_core
    180). Without that wrap the first segment reads with Bash rules: `C:\\x` loses its backslash.
    Lane swn-pwsh-escape, review round 2, item 3."""
    guard = _load_guard_module()
    script_type = getattr(sys.modules["guard_core"], "PowerShellScript", None)
    if script_type is None:   # a tree with no script tag fails this check, and does not crash the run
        return False, "guard_core has no PowerShellScript tag"
    guard.POWERSHELL_CALL[0] = False
    try:
        segments = guard.split_segments(script_type(r"cd C:\x; echo y"))
        tokens = guard.segment_tokens(segments[0]) if segments else None
    finally:
        guard.POWERSHELL_CALL[0] = False
    if tokens != ["cd", "C:\\x"]:
        return False, "a split segment lost its PowerShell tag: %r" % (tokens,)
    return True, "a split segment keeps the PowerShell tag its script had"


def merge_tool_missing_case():
    """A merge guard that cannot load the merge tool is unknown, and denies.

    The guard is copied into a folder with no `merge/` beside it, under a config directory whose
    rules file points nowhere, so neither place the tool is looked for holds it.
    """
    folder = os.path.join(ROOT, "nomergetool")
    os.makedirs(os.path.join(folder, "cfg"), exist_ok=True)
    copy = os.path.join(folder, "hooks", "guard.py")
    os.makedirs(os.path.dirname(copy), exist_ok=True)
    # The whole guard family beside GUARD (guard.py and its guard_* siblings), so the copy finds
    # guard_core.py. mutate_shared.guard_tree copies from the real hooks/, not from GUARD's folder.
    copy_guard_family(os.path.dirname(copy))
    env = dict(os.environ)
    env.pop("CLAUDE_CODE_REMOTE", None)
    env["CLAUDE_CONFIG_DIR"] = os.path.join(folder, "cfg")
    env["PATH"] = GHMAIN + os.pathsep + PY_PATH
    result = subprocess.run(
        [sys.executable, copy],
        input=json.dumps({"tool_name": "Bash", "tool_input": {"command": "gh pr merge 12"},
                          "cwd": NOGIT}),
        capture_output=True, text=True, env=env, timeout=60)
    if "merge-checks" not in result.stdout or "could not be loaded" not in result.stdout:
        return False, "expected a deny that names the unloadable tool, got %r" % result.stdout[:120]
    # The same copy cannot read the record folders either. The cite rule stands down, and the log says so.
    result = subprocess.run(
        [sys.executable, copy],
        input=json.dumps({"tool_name": "Bash", "cwd": NOGIT, "tool_input": {
            "command": VCS + ' commit -m "cites decisions/one-shared-record-stamp.md"'}}),
        capture_output=True, text=True, env=env, timeout=60)
    if "permissionDecision" in result.stdout:
        return False, "an unread folder list must not deny, got %r" % result.stdout[:120]
    try:
        with open(os.path.join(folder, "cfg", "guard.log"), encoding="utf-8") as handle:
            logged = "cite-by-id: record folders unread" in handle.read()
    except OSError:
        logged = False
    if not logged:
        return False, "an unread folder list must be logged as unread"
    return True, "deny, the tool could not be loaded; the unread folder list is logged, not denied"


def merge_import_exits_case():
    """A merge tool that exits at import (its records generator will not load) is unknown, and denies.

    merge/merge.py calls sys.exit when lint/hook_catalog.py will not load, so the exit is a
    SystemExit, not an Exception. merge_module() catches only Exception, so the exit escapes the
    guard: the guard exits 1, prints no decision, and `gh pr merge` is allowed. This copy has the
    real merge tool and no generator beside it. GHPEND is on PATH, a head with a check pending: a
    fix that loads the tool lazily then denies as pending, and a fix that catches the exit denies
    as unknown. A green gh would let a lazy-load fix allow the merge, so it is not used.
    """
    folder = os.path.join(ROOT, "mergeexit")
    hooks = os.path.join(folder, "hooks")
    for sub in (hooks, os.path.join(folder, "merge"), os.path.join(folder, "lint"), os.path.join(folder, "cfg")):
        os.makedirs(sub, exist_ok=True)
    copy_guard_family(hooks)
    # Read at run time, so a fix to the real tool is the one this case judges.
    shutil.copy(os.path.join(HERE, "..", "merge", "merge.py"), os.path.join(folder, "merge", "merge.py"))
    env = dict(os.environ)
    env.pop("CLAUDE_CODE_REMOTE", None)
    env.pop("PYTHONPATH", None)
    env["CLAUDE_CONFIG_DIR"] = os.path.join(folder, "cfg")
    env["PATH"] = GHPEND + os.pathsep + PY_PATH
    result = subprocess.run(
        [sys.executable, os.path.join(hooks, "guard.py")],
        input=json.dumps({"tool_name": "Bash", "tool_input": {"command": "gh pr merge 12"},
                          "cwd": NOGIT}),
        capture_output=True, text=True, env=env, timeout=60)
    where = "exit %d, stdout %r, stderr %r" % (result.returncode, result.stdout[:120], result.stderr[:200])
    try:
        decision = json.loads(result.stdout)["hookSpecificOutput"]
    except (ValueError, KeyError, TypeError):
        return False, "no decision printed, so the merge is allowed (" + where + ")"
    reason = str(decision.get("permissionDecisionReason", ""))
    if decision.get("permissionDecision") != "deny" or not reason.startswith("merge-checks:"):
        return False, "expected a merge-checks deny, got " + where
    if "unknown" not in reason and "pending" not in reason:
        return False, "expected unknown or pending in the reason, got " + reason[:160]
    return True, "a merge tool that exits at import denies the merge: " + reason[:80]


def guard_merge_read_timeout():
    """MERGE_READ_TIMEOUT of the guard under test, parsed from the guard_merge.py beside it (an import
    would run the module). None when the file or the assignment is not there or is not a plain number."""
    path = os.path.join(os.path.dirname(os.path.realpath(GUARD)), "guard_merge.py")
    try:
        with open(path, encoding="utf-8") as handle:
            tree = ast.parse(handle.read())
    except (OSError, SyntaxError, ValueError):
        return None
    for node in tree.body:
        if (isinstance(node, ast.Assign) and any(isinstance(t, ast.Name) and t.id == "MERGE_READ_TIMEOUT" for t in node.targets)
                and isinstance(node.value, ast.Constant) and isinstance(node.value.value, (int, float))
                and not isinstance(node.value.value, bool)):
            return float(node.value.value)
    return None


def merge_hang_timeout_case():
    """A `gh` that never answers must still end in a deny, and that deny must not depend on the
    hook's 60s budget being outlived first.

    The "denies as unknown" half holds on every OS: THAT is the subject (git-wait-for-required-
    checks), and this is pinned everywhere.

    The wall-time half -- the read must finish well inside the 60s hook budget -- is bounded in two
    parts. The read ends within MERGE_READ_TIMEOUT (read from the guard under test) plus
    HANG_MARGIN_S, so a read that outlives its own budget fails. And that budget plus its margin
    stays under HANG_CEILING_S, on every OS, so a bound that follows the constant cannot bless a
    budget that nears the hook's 60s. The first part is asserted on POSIX only. On
    Windows, GHHANG is a `.cmd` fake, and subprocess.run's kill on timeout only reaches the
    cmd.exe it directly spawned, never the
    ping it wraps for the wait -- Windows hands that ping an inherited duplicate of the real
    captured pipe regardless of its own `>nul 2>&1` redirection, so communicate() blocks until
    ping's FULL configured wait elapses, not until the kill. That is a fixture artifact of
    faking `gh` as a batch file on this one platform, not a fact about guard.py or merge.py: a
    real `gh.exe` is a single process, killed cleanly (confirmed directly against `ping.exe`
    itself: a bare, unwrapped call is killed at the nominal timeout, not its full duration). No
    `.cmd` fake can be killed on time here, so there is nothing truthful left to assert for wall
    time on Windows; skip it there, loudly, rather than fake a shorter wait or a looser bound.
    """
    budget = guard_merge_read_timeout()
    if budget is None:
        return False, "MERGE_READ_TIMEOUT cannot be read as a number from the guard_merge.py beside the guard under test"
    bound = budget + HANG_MARGIN_S
    if bound > HANG_CEILING_S:   # no run: a read budget this long is not inside the hook's 60s, whatever the fake does
        return False, ("MERGE_READ_TIMEOUT %gs plus %gs of margin is over %gs: a hung gh could outlive the hook's 60s budget"
                       % (budget, HANG_MARGIN_S, HANG_CEILING_S))
    started = time.time()
    got, reason = decide({
        "raw": None, "tool": "Bash", "cwd": NOGIT, "session": None,
        "env_path": GHHANG + os.pathsep + PY_PATH, "config": MERGECFG,
        "tool_input": {"command": "gh pr merge 12 --squash"},
    })
    elapsed = time.time() - started
    problems = []
    if got != "deny":
        problems.append("expected deny, got %s" % got)
    elif "could not run" not in reason:
        problems.append("expected the could-not-run reason, got %r" % reason[:120])
    if os.name != "nt" and elapsed >= bound:
        problems.append("the judgement took %.1fs, at or past the %gs bound (MERGE_READ_TIMEOUT %gs plus %gs)"
                        % (elapsed, bound, budget, HANG_MARGIN_S))
    if problems:
        return False, "; ".join(problems)
    note = ("denied as unknown in %.1fs; the wall-time bound is skipped on Windows, a `.cmd` "
            "fake gh cannot be killed on time here (see this case's docstring)" % elapsed
            if os.name == "nt" else
            "denied as unknown in %.1fs, inside the %gs bound and the 60s hook budget" % (elapsed, bound))
    return True, note


def carried(fragment, reason):
    """True when the reason holds the fragment. A tuple is any-of: one of its options is enough."""
    options = fragment if isinstance(fragment, tuple) else (fragment,)
    return any(option in reason for option in options)


def names_the_target(reason, rule=None):
    """Return the first forbidden fragment the printed reason carries, else ''.

    A fragment listed for the case's RULE in `REASON_MAY_NAME` is permitted. Every other fragment
    is forbidden, whatever the rule.
    """
    permitted = REASON_MAY_NAME.get(rule or "", ())
    for fragment in FORBIDDEN_IN_A_REASON:
        if fragment and fragment not in permitted and fragment in reason:
            return fragment
    return ""


def stack_reason_hygiene_case():
    """CLAUDE.md: "A refusal's printed remedy never names the forbidden target."

    The stack refusal is the one message an agent reads after the harness worktree reminder tells
    it to use the very commands this rule forbids. The message must therefore point somewhere
    else. It may name the two reads, `git stash list` and `git stash show`, because both stay
    allowed. It may not name the action it just refused.
    """
    forbidden = ("pop", "apply", "drop", "clear", "branch")
    problems = []
    for action in forbidden:
        command = VCS + " stash " + action
        if action == "branch":
            command += " lane"
        got, reason = decide({
            "raw": None, "tool": "Bash", "cwd": SUBJSTASH, "session": None,
            "env_path": None, "tool_input": {"command": command},
        })
        if got != "deny":
            problems.append("%s: expected deny, got %s" % (action, got))
            continue
        named = [word for word in forbidden if "stash " + word in reason]
        if named:
            problems.append("%s: the reason names the forbidden action %r" % (action, named[0]))
        for read in ("git stash list", "git stash show"):
            if read not in reason:
                problems.append("%s: the reason does not point at %r" % (action, read))
    if problems:
        return False, "; ".join(problems)
    return True, "five refusals, none naming its own action, all pointing at the two reads"


def log_env_case():
    """A refused environment file reaches the log, although it never reaches the reason.

    The reason is generic on purpose, so the log is the only place a person can still read WHICH
    file fired. A guard that hid both would refuse and explain nothing.
    """
    folder = os.path.join(ROOT, "envlog")
    os.makedirs(folder, exist_ok=True)
    path = os.path.join(folder, "guard.log")
    if os.path.exists(path):
        os.remove(path)
    env = dict(os.environ)
    env.pop("CLAUDE_CODE_REMOTE", None)
    env["CLAUDE_CONFIG_DIR"] = folder
    result = subprocess.run(
        [sys.executable, GUARD],
        input=json.dumps({"tool_name": "Write",
                          "tool_input": {"file_path": "C:/repo/" + ENV},
                          "cwd": "C:/repo"}),
        capture_output=True, text=True, env=env, timeout=60,
    )
    if ENV in result.stdout:
        return False, "the printed output names the file"
    if not os.path.exists(path):
        return False, "no log file was written"
    with open(path, encoding="utf-8") as handle:
        lines = [line for line in handle.read().splitlines() if line.strip()]
    # The matched text is field 4. The last field is the session id, not the matched text.
    fields = lines[0].split("\t") if len(lines) == 1 else []
    if len(fields) != 6 or ENV not in fields[4]:
        return False, "the log line does not carry the path in its matched field"
    return True, "generic on stdout, named in the log"


def _load_guard_module():
    """Import GUARD (respecting GUARD_UNDER_TEST) as a module, for a direct unit check.

    Every other case in this file drives the guard as a subprocess, one JSON object on
    stdin. `split_segments` has no JSON-shaped entry point of its own, so this loads the
    file under test directly, the same way `python3 -c "import guard; guard.split_segments(...)"`
    in the defect report does.
    """
    import importlib.util
    # guard.py imports guard_core and the guard_<family> modules by name, and guard_core imports
    # git_reads. A cached one would carry an earlier load's patches or copy into this one, so drop
    # every guard_* module and git_reads: each load gets modules of its own, as each load always
    # got its own module. The liveness cases patch git_reads and never restore it.
    for name in [n for n in sys.modules if n in ("guard_core", "git_reads") or n.startswith("guard_")]:
        sys.modules.pop(name, None)
    spec = importlib.util.spec_from_file_location("guard_under_test", GUARD)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def split_segments_comment_case():
    """A `#` is a comment only where the shell would read it as one.

    MEASURED regression, 2026-09-19: without the comment rule, the `'` in
    `# the driver's shape` opens a quote that runs to end of text, and everything after it
    — including `while true; do sleep 5; done` — collapses into one segment. Rule 1 never
    sees the real command. `guard-shell-selftest.sh`'s runaway-driver fixture went from
    refused to ALLOWED the moment a per-line reader was swapped in ahead of this fix.

    `fix#3` and `'#300'` must stay non-comments: a `#` after a letter, or inside quotes, is
    an ordinary character.
    """
    guard = _load_guard_module()
    problems = []

    got = guard.split_segments("# the driver's shape\nwhile true; do sleep 5; done")
    want = ["", "while true", " do sleep 5", " done"]
    if got != want:
        problems.append("apostrophe-in-comment: got %r want %r" % (got, want))
    if len(got) < 2:
        problems.append(
            "apostrophe-in-comment collapsed to one segment: got %r" % (got,))

    got = guard.split_segments("echo fix#3; ls")
    want = ["echo fix#3", " ls"]
    if got != want:
        problems.append("fix#3 (no quotes): got %r want %r" % (got, want))

    got = guard.split_segments("echo '#300'; ls")
    want = ["echo '#300'", " ls"]
    if got != want:
        problems.append("quoted hash '#300': got %r want %r" % (got, want))

    # A comment at index 0, and one after each of `;`, `|`, `&`, `(`.
    for prefix, sep in (
        ("", ""),
        ("true;", ";"),
        ("true|", "|"),
        ("true&", "&"),
        ("(", "("),
    ):
        cmd = prefix + "# comment after %r" % sep
        got = guard.split_segments(cmd)
        joined = "".join(got)
        if "comment after" in joined:
            problems.append("comment after %r was not dropped: %r" % (sep, got))

    return (not problems), "; ".join(problems) if problems else "comment rule holds"


def process_start_ms_case():
    """`_process_start_ms` must tell apart three outcomes: alive, CONFIRMED dead, and
    unreadable. A regression that folds unreadable back into dead would let a live session's
    worktree look removable, the defect this whole PR fixes.

    The alive check runs on every platform: it only compares against `_real_process_start_ms`,
    which itself has a Windows arm. The dead and unreadable sub-cases below are POSIX-only
    TECHNIQUES, not POSIX-only outcomes: a just-exited pid is reused fast enough on Windows that
    it reads back alive, and faking a broken `ps` on PATH does nothing there, since the Windows
    arm never calls `ps`. Both are skipped on non-POSIX. The Windows arm's own correctness is
    proven separately and deterministically by `process_start_ms_windows_case`, which stubs
    `ctypes.windll` instead of depending on real OS timing.
    """
    guard = _load_guard_module()
    problems = []

    self_pid = os.getpid()
    want_alive = _real_process_start_ms(self_pid)
    got_alive = guard._process_start_ms(self_pid)
    if not isinstance(got_alive, int) or isinstance(got_alive, bool):
        problems.append("alive: did not return an int: %r" % (got_alive,))
    # lstart (boot time) and etime (uptime) each floor to whole seconds on different clocks, so a fresh child can differ by over 2 s; an hour is 3600000 ms.
    elif abs(got_alive - want_alive) > 5000:
        problems.append("alive: got %r want near %r" % (got_alive, want_alive))

    if os.name == "nt":  # the alive read still runs and can fail; the split it names does not run here
        if problems:
            return False, "; ".join(problems)
        return SKIP, (
            "alive read matches; the dead-pid and ps-faking arms are POSIX-only; "
            "the Windows arm is proven separately by process_start_ms_windows_case"
        )

    # A process this test starts and waits on is CONFIRMED dead the moment `wait()` returns.
    finished = subprocess.Popen([sys.executable, "-c", "pass"])
    finished.wait()
    dead_pid = finished.pid
    got_dead = guard._process_start_ms(dead_pid)
    if got_dead is not None:
        problems.append("dead: got %r want None" % (got_dead,))

    # Unreadable, arm 1: `ps` answers with a nonzero exit code that is NOT 1. That is a read
    # failure, never a death, and must not collapse to the same `None` a confirmed-dead pid gets.
    fake_dir = tempfile.mkdtemp(prefix="fake-ps-bad-exit-")
    old_path = os.environ.get("PATH", "")
    try:
        fake_ps = os.path.join(fake_dir, "ps")
        write(fake_ps, "#!/bin/sh\nexit 2\n")
        os.chmod(fake_ps, 0o755)
        os.environ["PATH"] = fake_dir + os.pathsep + old_path
        got_bad_exit = guard._process_start_ms(self_pid)
    finally:
        os.environ["PATH"] = old_path
        shutil.rmtree(fake_dir, ignore_errors=True)
    if got_bad_exit is not guard.PROCESS_START_UNREADABLE:
        problems.append(
            "unreadable (bad exit code): got %r want PROCESS_START_UNREADABLE" % (got_bad_exit,))

    # Unreadable, arm 2: no `ps` on PATH at all, so the exec itself fails.
    empty_dir = tempfile.mkdtemp(prefix="fake-ps-missing-")
    try:
        os.environ["PATH"] = empty_dir
        got_missing = guard._process_start_ms(self_pid)
    finally:
        os.environ["PATH"] = old_path
        shutil.rmtree(empty_dir, ignore_errors=True)
    if got_missing is not guard.PROCESS_START_UNREADABLE:
        problems.append(
            "unreadable (ps missing): got %r want PROCESS_START_UNREADABLE" % (got_missing,))

    return (not problems), "; ".join(problems) if problems else "alive/dead/unreadable read apart"


# The repeated hour of a fall-back night in America/Chicago: 01:00 to 02:00 happens twice. These are the
# two 01:30s. Both render as the same `ps` text, so the read alone decides which instant it gets.
REPEATED_HOUR_CDT_MS = int(datetime(2026, 11, 1, 6, 30, tzinfo=timezone.utc).timestamp()) * 1000
REPEATED_HOUR_CST_MS = int(datetime(2026, 11, 1, 7, 30, tzinfo=timezone.utc).timestamp()) * 1000

FAKE_PS_BODY = '''import time
EPOCH = @EPOCH@
DAYS = ("Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun")
MONTHS = ("Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec")
t = time.localtime(EPOCH)  # in the zone of the TZ this process was started with
# ps pads the day to two columns with a space, so the 1st prints as " 1", as real ps does.
print("%s %s %2d %02d:%02d:%02d %d" % (DAYS[t.tm_wday], MONTHS[t.tm_mon - 1], t.tm_mday,
                                       t.tm_hour, t.tm_min, t.tm_sec, t.tm_year))
'''


def in_chicago_with_fake_ps(epoch_ms, action):
    """Run `action()` with TZ=America/Chicago in this process and its children, with a fake `ps`
    first on PATH. The fake answers any `-o lstart=` read with EPOCH_MS, rendered in the zone of
    the environment it is started with. It is a real child process, not a patch, so a read that
    hands ps its own `env` changes what ps prints, and the case sees that read's zone.
    POSIX only: the Windows arm never runs `ps`, so callers skip there.
    """
    folder = tempfile.mkdtemp(prefix="fake-ps-chicago-", dir=ROOT)
    script = os.path.join(folder, "ps")
    write(script, "#!%s\n" % sys.executable
          + FAKE_PS_BODY.replace("@EPOCH@", str(epoch_ms // 1000)))
    os.chmod(script, 0o755)
    old_tz, old_path = os.environ.get("TZ"), os.environ.get("PATH", "")
    os.environ["TZ"] = "America/Chicago"
    os.environ["PATH"] = folder + os.pathsep + old_path
    time.tzset()
    try:
        return action()
    finally:
        os.environ["PATH"] = old_path
        if old_tz is None:
            os.environ.pop("TZ", None)
        else:
            os.environ["TZ"] = old_tz
        time.tzset()


def _repeated_hour_read_case(epoch_ms, label):
    """`_process_start_ms` must return the instant a process started at LABEL, not an hour off."""
    if os.name == "nt" or not hasattr(time, "tzset"):
        return SKIP, "the fake ps is POSIX-only; the Windows arm reads the kernel's FILETIME"
    guard = _load_guard_module()
    got = in_chicago_with_fake_ps(epoch_ms, lambda: guard._process_start_ms(4242))
    if got != epoch_ms:
        gap = got - epoch_ms if isinstance(got, int) and not isinstance(got, bool) else "n/a"
        return False, "%s: got %r want %r (got minus want: %s ms)" % (label, got, epoch_ms, gap)
    return True, "%s reads as its own instant" % label


def process_start_ms_repeated_hour_cdt_case():
    """The first 01:30 in Chicago (06:30 UTC, CDT). With TZ set to Chicago, the zone-free
    `lstart=` text plus `time.mktime` can land on the other 01:30."""
    return _repeated_hour_read_case(REPEATED_HOUR_CDT_MS, "01:30 CDT (06:30 UTC)")


def process_start_ms_repeated_hour_cst_case():
    """The second 01:30 in Chicago (07:30 UTC, CST). The pair of cases catches a read that is
    wrong in either direction, whichever instant `mktime` picks for the ambiguous text."""
    return _repeated_hour_read_case(REPEATED_HOUR_CST_MS, "01:30 CST (07:30 UTC)")


def _fake_kernel32(open_process_result, get_last_error=0, get_process_times_ok=True,
                    creation_high=0, creation_low=0):
    """A stand-in for `ctypes.windll.kernel32`, built the same way `make_blind_git` stands in
    for a real `git`: the real target (Windows) is unavailable on this machine, so the CALL
    SURFACE is stubbed instead, which still drives the Windows arm's own branching logic."""
    closed = []

    class Kernel32:
        def OpenProcess(self, access, inherit, pid):
            return open_process_result

        def GetProcessTimes(self, handle, creation_ref, exit_ref, kernel_ref, user_ref):
            if not get_process_times_ok:
                return 0
            import ctypes
            import ctypes.wintypes
            ptr = ctypes.cast(creation_ref, ctypes.POINTER(ctypes.wintypes.FILETIME))
            ptr.contents.dwHighDateTime = creation_high
            ptr.contents.dwLowDateTime = creation_low
            return 1

        def CloseHandle(self, handle):
            closed.append(handle)
            return 1

    class Windll:
        kernel32 = Kernel32()

    return Windll(), closed, (lambda: get_last_error)


def process_start_ms_windows_case():
    """Drive `_process_start_ms_windows`'s own branches with a stubbed `ctypes.windll`, since
    this machine has no real kernel32. A NULL handle with error 87 (no such process) reads as
    CONFIRMED dead. A NULL handle with error 5 (access denied) reads as unreadable, never as
    dead. A valid handle's FILETIME converts to the same epoch millisecond the formula in the
    code names.
    """
    import ctypes

    guard = _load_guard_module()
    problems = []
    real_windll = getattr(ctypes, "windll", None)
    real_get_last_error = getattr(ctypes, "GetLastError", None)

    def run(open_result, error, times_ok=True, high=0, low=0):
        fake_windll, closed, get_last_error = _fake_kernel32(
            open_result, error, times_ok, high, low)
        ctypes.windll = fake_windll
        ctypes.GetLastError = get_last_error
        try:
            return guard._process_start_ms_windows(4321), closed
        finally:
            if real_windll is None:
                del ctypes.windll
            else:
                ctypes.windll = real_windll
            if real_get_last_error is None:
                del ctypes.GetLastError
            else:
                ctypes.GetLastError = real_get_last_error

    # error 87, ERROR_INVALID_PARAMETER: no such process at all -> CONFIRMED dead.
    got, closed = run(open_result=0, error=87)
    if got is not None:
        problems.append("windows dead (error 87): got %r want None" % (got,))
    if closed:
        problems.append("windows dead (error 87): CloseHandle called on a NULL handle")

    # error 5, ERROR_ACCESS_DENIED: the process exists, but this read cannot see into it.
    got, closed = run(open_result=0, error=5)
    if got is not guard.PROCESS_START_UNREADABLE:
        problems.append(
            "windows access-denied (error 5): got %r want PROCESS_START_UNREADABLE" % (got,))

    # A valid handle: 10,000 100ns ticks past the epoch-zero FILETIME (1601-01-01 UTC) is one
    # millisecond past that same instant, so this converts to epoch millisecond 1.
    ticks = 11644473600000 * 10000 + 10000
    high = (ticks >> 32) & 0xFFFFFFFF
    low = ticks & 0xFFFFFFFF
    got, closed = run(open_result=99, error=0, times_ok=True, high=high, low=low)
    if got != 1:
        problems.append("windows alive: FILETIME converted to %r want %r" % (got, 1))
    if not closed:
        problems.append("windows alive: CloseHandle was never called on the valid handle")

    return (not problems), "; ".join(problems) if problems else "windows arm splits dead/unreadable/alive"


def session_is_live_case():
    """`session_is_live` must carry `_process_start_ms`'s three states through as True, False,
    and None, never coercing the unreadable third state into False. The module's own
    `_process_start_ms` is stubbed here so this case proves `session_is_live`'s own wiring, not
    a real process's real state.
    """
    guard = _load_guard_module()
    problems = []
    record = {"pid": 4321, "startedAt": 1_000_000}

    sys.modules["git_reads"]._process_start_ms = lambda pid: 1_000_000
    live = guard.session_is_live(record)
    if live is not True:
        problems.append("live: got %r want True" % (live,))

    sys.modules["git_reads"]._process_start_ms = lambda pid: None
    dead = guard.session_is_live(record)
    if dead is not False:
        problems.append("dead: got %r want False" % (dead,))

    sys.modules["git_reads"]._process_start_ms = lambda pid: guard.PROCESS_START_UNREADABLE
    try:
        unreadable = guard.session_is_live(record)
    except Exception as e:
        problems.append(
            "unreadable: session_is_live raised %r instead of answering None (not False)" % (e,))
    else:
        if unreadable is not None:
            problems.append("unreadable: got %r want None (not False)" % (unreadable,))

    return (not problems), "; ".join(problems) if problems else "session_is_live carries all three states"


def _repeated_hour_session_case(epoch_ms, label):
    """A session record whose `startedAt` is the process's true start, read in Chicago through
    the fake ps, must be live. An hour-off read lands outside the 60 s tolerance: None, or False."""
    if os.name == "nt" or not hasattr(time, "tzset"):
        return SKIP, "the fake ps is POSIX-only; the Windows arm reads the kernel's FILETIME"
    guard = _load_guard_module()
    record = {"pid": 4242, "startedAt": epoch_ms}
    got = in_chicago_with_fake_ps(epoch_ms, lambda: guard.session_is_live(record))
    if got is not True:
        return False, "%s: session_is_live got %r want True" % (label, got)
    return True, "%s: session_is_live says True" % label


def session_is_live_repeated_hour_cdt_case():
    """A session started at 01:30 CDT is live when its record holds that instant."""
    return _repeated_hour_session_case(REPEATED_HOUR_CDT_MS, "01:30 CDT (06:30 UTC)")


def session_is_live_repeated_hour_cst_case():
    """A session started at 01:30 CST is live when its record holds that instant."""
    return _repeated_hour_session_case(REPEATED_HOUR_CST_MS, "01:30 CST (07:30 UTC)")


def worktree_live_session_unreadable_case():
    """`worktree_live_session` must answer None, not False, when a record's cwd sits under
    TARGET but that record's own liveness read is unreadable, and no OTHER record under TARGET
    is confirmed live. Returning False here would make an unreadable-but-maybe-live session's
    worktree look removable to `worktree_remove_subject` and `janitor/sweep.py`'s
    `decide_worktree`, both of which already keep on None.
    """
    guard = _load_guard_module()
    problems = []
    target = tempfile.mkdtemp(prefix="wt-live-unreadable-")
    try:
        sys.modules["git_reads"].session_records = lambda: [{"pid": 1, "startedAt": 1, "cwd": target}]
        sys.modules["git_reads"].session_is_live = lambda record: None
        got = guard.worktree_live_session(target)
        if got is not None:
            problems.append(
                "unreadable record under target: got %r want None, not False" % (got,))
    finally:
        shutil.rmtree(target, ignore_errors=True)

    return (not problems), "; ".join(problems) if problems else "unreadable record propagates as None"


def worktree_live_session_two_spellings_case():
    """A live session's cwd and TARGET can name one physical directory in two strings that
    `os.path.normcase(os.path.realpath(...))` never makes equal. MEASURED by hand on this
    machine: mapping drive `T:` to `\\\\localhost\\c$` left `os.path.realpath` naming the UNC
    path for one spelling and the local `C:\\...` path for the other -- they never compared
    equal as strings -- while `os.stat` gave both the identical `(st_dev, st_ino)`. That is the
    exact split a Windows `subst` drive or a mapped network drive can produce against the
    worktree path `janitor/sweep.py` hands the sweep.

    This case does not depend on that mapped drive existing on whatever machine runs the
    suite (loopback SMB sharing is not guaranteed on every CI image), so it simulates the same
    split at the `_path_identity` seam instead: two genuinely different temp directories stand
    in for the two spellings, and `_path_identity` is stubbed to answer as if they were one
    file. That proves `worktree_live_session` FOLDS a matching identity into "under target" and
    returns True for a live session there. It does NOT re-prove that `os.stat` truly agrees
    across every real subst/mapped-drive pair on every Windows build -- that half was checked
    against the real mapped drive above, not by this automated case.
    """
    guard = _load_guard_module()
    problems = []
    target = tempfile.mkdtemp(prefix="wt-live-target-")
    other_spelling = tempfile.mkdtemp(prefix="wt-live-other-spelling-")
    real_identity = guard._path_identity
    try:
        sys.modules["git_reads"].session_records = lambda: [{"pid": 1, "startedAt": 1, "cwd": other_spelling}]
        sys.modules["git_reads"].session_is_live = lambda record: True
        target_resolved = os.path.realpath(target)
        other_resolved = os.path.realpath(other_spelling)
        shared = ("same-underlying-file",)

        def fake_identity(path):
            if path in (target_resolved, other_resolved):
                return shared
            return real_identity(path)

        sys.modules["git_reads"]._path_identity = fake_identity
        got = guard.worktree_live_session(target)
        if got is not True:
            problems.append(
                "two spellings, one identity, live session: got %r want True" % (got,))
    finally:
        sys.modules["git_reads"]._path_identity = real_identity
        shutil.rmtree(target, ignore_errors=True)
        shutil.rmtree(other_spelling, ignore_errors=True)

    return (not problems), "; ".join(problems) if problems else "matching identity is under target"


def worktree_live_session_path_unresolvable_case():
    """When the string spellings differ AND the identity fallback itself cannot tell (target's
    own identity is unreadable), the record must count as unresolvable, never as "not under
    target." Folding it into "not under" would let a live session's worktree, reached through a
    spelling `realpath` never collapses, look removable. Keep is the safe direction, so the
    answer must be None, not False.
    """
    guard = _load_guard_module()
    problems = []
    target = tempfile.mkdtemp(prefix="wt-live-target-unresolvable-")
    other_spelling = tempfile.mkdtemp(prefix="wt-live-other-unresolvable-")
    real_identity = guard._path_identity
    try:
        sys.modules["git_reads"].session_records = lambda: [{"pid": 1, "startedAt": 1, "cwd": other_spelling}]
        sys.modules["git_reads"].session_is_live = lambda record: True  # must not even matter: identity is unresolvable
        sys.modules["git_reads"]._path_identity = lambda path: None
        got = guard.worktree_live_session(target)
        if got is not None:
            problems.append(
                "identity unresolvable, differing spellings: got %r want None, not False" % (got,))
    finally:
        sys.modules["git_reads"]._path_identity = real_identity
        shutil.rmtree(target, ignore_errors=True)
        shutil.rmtree(other_spelling, ignore_errors=True)

    return (not problems), "; ".join(problems) if problems else "unresolvable identity propagates as None"


def session_is_live_backwards_clock_step_case():
    """A backwards clock step landing between the two ORIGINAL measurements (the kernel's own
    process-creation FILETIME, fixed forever once recorded, and the record's `startedAt`,
    written 1.7-3.2s later by `Date.now()`) can leave `actual` (read now) more than the
    tolerance AHEAD of `started`. That is also the recycled-pid signature (a new process at
    this pid, created well after the old record's startedAt) -- the two are indistinguishable
    from this reading alone. `session_is_live` must answer None (cannot tell), never False
    (confirmed dead), for that direction, because a confident False here is exactly what let a
    genuinely live, clock-glitched session get reaped. The opposite direction (`started` far
    AHEAD of `actual`, which no legitimate same-process reading ever produces, since `started`
    is always written strictly after `actual`) stays a confident False, unchanged.
    """
    guard = _load_guard_module()
    problems = []
    record = {"pid": 4321, "startedAt": 1_000_000}

    # actual is 5 minutes AFTER started: the ambiguous, must-not-be-confident-False direction.
    sys.modules["git_reads"]._process_start_ms = lambda pid: 1_000_000 + 300_000
    implied_backwards = guard.session_is_live(record)
    if implied_backwards is not None:
        problems.append(
            "actual far ahead of started (implies a backwards step): got %r want None" % (
                implied_backwards,))

    # actual is 5 minutes BEFORE started: never produced by the same live process, stays False.
    sys.modules["git_reads"]._process_start_ms = lambda pid: 1_000_000 - 300_000
    still_dead = guard.session_is_live(record)
    if still_dead is not False:
        problems.append(
            "actual far behind started: got %r want False (unchanged)" % (still_dead,))

    # within tolerance, either side: unaffected by the fix.
    sys.modules["git_reads"]._process_start_ms = lambda pid: 1_000_000 + 2_000
    within = guard.session_is_live(record)
    if within is not True:
        problems.append("within tolerance: got %r want True (unaffected)" % (within,))

    return (not problems), "; ".join(problems) if problems else "backwards-step direction reads unreadable"


def _decide_full(tool, cwd, agent_id=None, process_cwd=None, session=None, temp=None, **tool_input):
    """`decide`, but for a hand-built payload naming every key `decide` reads by index.

    `process_cwd` sets the GUARD PROCESS's own cwd, distinct from the payload `cwd` above: a
    relative `file_path` must resolve against the payload `cwd`, never against wherever the
    guard subprocess happens to run from. `session` is the payload's session_id. `temp` is the
    temp folder the guard run reads as its own (see TEMP_DIR), or None for the system temp.
    """
    return decide({
        "raw": None, "tool": tool, "cwd": cwd, "session": session, "env_path": None,
        "config": None, "agent_id": agent_id, "process_cwd": process_cwd, "temp": temp,
        "tool_input": tool_input,
    })


def worktree_home_case():
    """Rule 0, `worktree-home`: decisions/an-agent-outside-its-home-tree-must-stop.md.

    Builds one real primary checkout and one real linked worktree at
    `<primary>/.claude/worktrees/agent-<id>`, the shape the harness names. Runs the sequence a
    real session would, in order, against that ONE on-disk record: no agent_id, no worktree yet,
    the first call that records the home, a later call outside it, an edit outside it, an edit
    outside the clone entirely, a read outside it, and the home folder removed outright.
    """
    agent_id = "wthomeagent1"
    other_agent = "wthomeagent2"  # never given a worktree: a non-isolated agent
    primary = os.path.join(ROOT, "wthome_primary")
    worktree = os.path.join(primary, ".claude", "worktrees", "agent-" + agent_id)
    inside_clone_outside_home = os.path.join(primary, "src", "app.py")
    outside_clone = os.path.join(ROOT, "wthome_scratch", "note.txt")

    make_repo(primary, {"src/app.py": "print(1)\n"})
    run_vcs(primary, "worktree", "add", "-q", worktree, "-b", "worktree-agent-" + agent_id)
    os.makedirs(os.path.dirname(outside_clone), exist_ok=True)
    write(outside_clone, "hi\n")

    problems = []

    def check(label, expect, tool, cwd, agent=None, process_cwd=None, **tool_input):
        got, reason = _decide_full(tool, cwd, agent_id=agent, process_cwd=process_cwd,
                                    **tool_input)
        if got != expect:
            problems.append("%s: expected %s, got %s (%s)" % (label, expect, got, reason[:120]))

    # The orchestrator carries no agent_id, even from a cwd shaped like an agent worktree.
    check("orchestrator", "allow", "Bash", worktree, command="echo hi")

    # A non-isolated agent: an agent_id, a cwd that never matches the worktree shape, and no
    # record yet. Allowed, and nothing gets recorded for a cwd that names no worktree.
    check("non-isolated agent", "allow", "Bash", primary, agent=other_agent, command="echo hi")

    # An isolated agent's first call, from inside its own worktree: records the home and allows.
    check("isolated agent in home", "allow", "Bash", worktree, agent=agent_id, command="echo hi")

    record_path = os.path.join(primary, ".git", "agent-homes", agent_id)
    if not os.path.isfile(record_path):
        problems.append("no home record was written at %r" % record_path)

    # Same agent, cwd now the primary checkout: outside its recorded home.
    check("cwd in primary checkout", "deny", "Bash", primary, agent=agent_id, command="echo hi")

    # An Edit outside the recorded home, but still inside the same clone: refused.
    check("edit outside home inside clone", "deny", "Edit", worktree, agent=agent_id,
          file_path=inside_clone_outside_home, old_string="a", new_string="b")

    # An Edit to a path outside the clone entirely (a scratchpad file): allowed.
    check("edit outside the clone", "allow", "Edit", worktree, agent=agent_id,
          file_path=outside_clone, old_string="a", new_string="b")

    # Read outside home: always allowed, so a stranded agent can still read and report.
    check("read outside home", "allow", "Read", primary, agent=agent_id,
          file_path=inside_clone_outside_home)

    # A RELATIVE file_path must resolve against the PAYLOAD's own cwd (the worktree), never
    # against wherever the guard PROCESS happens to run from. Run the guard from the primary
    # checkout while the payload's own cwd is the worktree: the target is inside home either
    # way it resolves, so it must allow. Before the fix, the process cwd won the join, and
    # "src/app.py" read as primary/src/app.py: inside the clone, outside home, wrongly denied.
    check("relative edit target resolves against payload cwd, not process cwd", "allow",
          "Edit", worktree, agent=agent_id, process_cwd=primary,
          file_path="src/app.py", old_string="a", new_string="b")

    # The harness removes the worktree folder AND its branch together. The record must survive
    # in the clone's common git directory: a later call from the primary checkout still refuses.
    shutil.rmtree(worktree, ignore_errors=True)
    check("home folder removed", "deny", "Bash", primary, agent=agent_id, command="echo hi")

    # An unreadable state -- no git at all -- is unknown, never a hit: allow.
    check("unreadable state", "allow", "Bash", NOGIT, agent="wthomeagent3", command="echo hi")

    if problems:
        return False, "; ".join(problems)
    return True, "orchestrator, no-record, home, outside-home, removed-home, unreadable all correct"


def _cross_checkout_fixture(name, lanes=("lane-a", "lane-b"), origin=None):
    """A primary checkout with two nested worktrees, `.claude/worktrees/lane-a` and `lane-b`, the
    shape the harness makes, and a scratch folder outside the clone. Returns the four paths. `lanes`
    names the two worktrees; an agent case passes `agent-<id>` names, the shape its home takes. `origin`,
    when given, is the primary's `origin` remote, which a separate-clone case needs to name the same repo."""
    primary = os.path.join(ROOT, name + "_primary")
    lane_a = os.path.join(primary, ".claude", "worktrees", lanes[0])
    lane_b = os.path.join(primary, ".claude", "worktrees", lanes[1])
    scratch = os.path.join(ROOT, name + "_scratch")
    if not os.path.isdir(lane_b):
        make_repo(primary, {"src/app.py": "print(1)\n"})
        if origin:
            run_vcs(primary, "remote", "add", "origin", origin)
        run_vcs(primary, "worktree", "add", "-q", lane_a, "-b", name + "-" + lanes[0])
        run_vcs(primary, "worktree", "add", "-q", lane_b, "-b", name + "-" + lanes[1])
        os.makedirs(scratch, exist_ok=True)
    return primary, lane_a, lane_b, scratch


def worktree_home_cross_checkout_case():
    """Rule 0, `other-checkout`, beside `worktree-home`: any session, agent or not, may not write
    into a checkout of its clone other than the one its cwd stands in. A target in no checkout of
    the clone is allowed. A nested worktree belongs to itself, not to the primary that holds it.
    Why: docs/decisions/an-agent-outside-its-home-tree-must-stop.md."""
    primary, lane_a, lane_b, scratch = _cross_checkout_fixture("xco")
    in_a = os.path.join(lane_a, "src", "app.py")
    in_b = os.path.join(lane_b, "src", "app.py")
    in_primary = os.path.join(primary, "src", "app.py")
    problems = []

    def check(label, expect, tool, cwd, **tool_input):
        got, reason = _decide_full(tool, cwd, **tool_input)
        if got != expect:
            problems.append("%s: expected %s, got %s (%s)" % (label, expect, got, reason[:120]))
        elif expect == "deny" and ("other-checkout" not in reason or primary in reason):
            problems.append("%s: the refusal must name other-checkout and no path: %s" % (
                label, reason[:160]))

    # First: a top-level session (no agent_id) in one worktree writes into its sibling.
    check("top-level Write into a sibling worktree", "deny", "Write", lane_a,
          file_path=in_b, content="x")
    check("primary Write into a nested worktree", "deny", "Write", primary,
          file_path=in_b, content="x")
    check("worktree Edit into the primary's own files", "deny", "Edit", lane_a,
          file_path=in_primary, old_string="1", new_string="2")
    check("worktree MultiEdit into the primary's own files", "deny", "MultiEdit", lane_b,
          file_path=in_primary, edits=[{"old_string": "1", "new_string": "2"}])
    check("relative climb out of the worktree into its sibling", "deny", "Write", lane_a,
          file_path=os.path.join("..", "lane-b", "src", "app.py"), content="x")
    check("Write to a folder in no checkout", "allow", "Write", lane_a,
          file_path=os.path.join(scratch, "note.md"), content="x")
    check("Write within its own worktree", "allow", "Write", lane_a, file_path=in_a, content="x")
    check("primary Write into its own files", "allow", "Write", primary,
          file_path=in_primary, content="x")
    check("primary Write of a new file under .claude", "allow", "Write", primary,
          file_path=os.path.join(primary, ".claude", "notes.md"), content="x")
    check("Read of a sibling worktree", "allow", "Read", lane_a, file_path=in_b)
    check("unreadable git state at the cwd", "allow", "Write", NOGIT, file_path=in_b, content="x")
    # The shell form: the write targets the guard already extracts for frozen paths.
    check("shell redirect into a sibling worktree", "deny", "Bash", lane_a,
          command="echo x > " + slash(in_b))
    check("shell cp into the primary's files", "deny", "Bash", lane_a,
          command="cp src/app.py " + slash(in_primary))
    check("shell read of a sibling worktree", "allow", "Bash", lane_a,
          command="cat " + slash(in_b))
    check("shell git read of a sibling worktree", "allow", "Bash", primary,
          command=VCS + " -C " + slash(lane_b) + " log --oneline -1")
    check("shell redirect within its own worktree", "allow", "Bash", lane_a,
          command="echo x > " + slash(os.path.join(lane_a, "src", "new.txt")))
    check("shell redirect to a folder in no checkout", "allow", "Bash", lane_a,
          command="echo x > " + slash(os.path.join(scratch, "out.txt")))
    # A leading cd moves the folder a relative target resolves against.
    check("shell cd into a sibling, then a relative write", "deny", "Bash", primary,
          command="cd " + slash(lane_b) + " && echo x > a.txt")
    check("shell cd out of the clone, then a relative write", "allow", "Bash", lane_a,
          command="cd " + slash(scratch) + " && echo x > a.txt")
    # The clone's common git directory belongs to no one checkout.
    exclude = os.path.join(primary, ".git", "info", "exclude")
    check("worktree Write into the common git directory", "allow", "Write", lane_a,
          file_path=exclude, content="x")
    check("shell append into the common git directory", "allow", "Bash", lane_b,
          command="echo x >> " + slash(exclude))
    # A whole worktree removed by hand: refused, and the remedy names the proper tool.
    got, reason = _decide_full("Bash", primary, command="rm -rf .claude/worktrees/lane-b")
    if got != "deny" or "other-checkout" not in reason or "git worktree remove" not in reason \
            or "lane-b" in reason:
        problems.append("rm -rf of a worktree: want deny naming git worktree remove and no path, "
                        "got %s (%s)" % (got, reason[:160]))
    if problems:
        return False, "; ".join(problems)
    return True, "sibling, nested, primary, shell and outside-clone writes judged; reads pass"


def worktree_home_cross_checkout_copy_case():
    """Rule 0, `other-checkout`, the false alarms on a copy, beside
    `worktree_home_cross_checkout_case`. A copy reads its SOURCE, so a source in another checkout
    is a read; only the target is a write. An interpreter runs its body as code: a write it makes through
    os.system, subprocess, a copy call, or open() is judged. A substitution in an unquoted heredoc and
    a bash body are judged too. Why:
    docs/decisions/an-agent-outside-its-home-tree-must-stop.md.
    """
    primary, lane_a, lane_b, scratch = _cross_checkout_fixture("xcocp")
    write(os.path.join(lane_b, "bin", "ci-job"), "#!/bin/sh\n")
    write(os.path.join(lane_b, "x"), "x\n")
    write(os.path.join(lane_b, "y"), "y\n")
    other = slash(lane_b)
    problems = []

    def check(label, expect, tool, cwd, **tool_input):
        got, reason = _decide_full(tool, cwd, **tool_input)
        if got != expect:
            problems.append("%s: expected %s, got %s (%s)" % (label, expect, got, reason[:120]))
        elif expect == "deny" and ("other-checkout" not in reason or primary in reason):
            problems.append("%s: the refusal must name other-checkout and no path: %s" % (
                label, reason[:160]))

    # A copy reads its source: the source may sit in another checkout. Only the target is judged.
    check("for-loop copy of another checkout's file into its own", "allow", "Bash", lane_a,
          command='B=%s; for f in bin/ci-job; do cp "$B/$f" "$f"; done' % other)
    check("copy from another checkout, inside a loop body", "allow", "Bash", lane_a,
          command='for f in a; do cp "%s/bin/ci-job" bin/ci-job; done' % other)
    check("copy from another checkout into an unresolved quoted target", "allow", "Bash", lane_a,
          command='cp "%s/x" "$f"' % other)
    # Controls: each write into another checkout stays refused.
    check("control: copy into another checkout's file, quoted target", "deny", "Bash", lane_a,
          command='B=%s; cp bin/x "$B/bin/ci-job"' % other)
    check("control: copy into another checkout inside a loop", "deny", "Bash", lane_a,
          command='B=%s; for f in a; do cp a "$B/$f"; done' % other)
    check("control: move out of another checkout", "deny", "Bash", lane_a,
          command="mv %s/x ./x" % other)
    check("control: move out of another checkout inside a loop", "deny", "Bash", lane_a,
          command='B=%s; for f in a; do mv "$B/$f" "$f"; done' % other)
    check("control: unquoted heredoc whose substitution copies into another checkout", "deny",
          "Bash", lane_a, command='python3 - <<EOF\nx="$(cp a %s/y)"\nEOF' % other)
    check("control: quoted heredoc whose interpreter copies into another checkout", "deny",
          "Bash", lane_a,
          command="python3 - <<'PY'\nimport shutil; shutil.copy('a', '%s/x')\nPY" % other)
    check("control: bash heredoc body that copies into another checkout", "deny", "Bash", lane_a,
          command="bash <<'EOF'\ncp a %s/x\nEOF" % other)
    # A quoted heredoc whose interpreter writes a file in another checkout.
    check("quoted heredoc whose interpreter opens a file in another checkout", "deny", "Bash",
          lane_a, command="python3 - <<'PY'\nopen('%s/x','w').write('1')\nPY" % other)
    # Interpreter bodies that run a write through another call: the body stays in the shell scan.
    check("python os.system runs a copy into another checkout", "deny", "Bash", lane_a,
          command="python3 - <<'PY'\nimport os; os.system('cp a %s/x')\nPY" % other)
    check("python os.system runs an echo redirect into another checkout", "deny", "Bash", lane_a,
          command="python3 - <<'PY'\nimport os; os.system('echo 1 > %s/x')\nPY" % other)
    check("python subprocess.run lists a copy into another checkout", "deny", "Bash", lane_a,
          command="python3 - <<'PY'\nimport subprocess; subprocess.run(['cp','a','%s/x'])\nPY" % other)
    check("python from-import copy into another checkout", "deny", "Bash", lane_a,
          command="python3 - <<'PY'\nfrom shutil import copy; copy('a','%s/x')\nPY" % other)

    if problems:
        return False, "; ".join(problems)
    return True, "copy sources in another checkout pass; writes refused"


def _stand_in_git(tag):
    """A stand-in `git` first on PATH. It appends each call's arguments to its log, then runs the real git.
    Returns (log, PATH) for a case to pass the guard, or (None, None) when no git is on PATH."""
    real = shutil.which(VCS)
    if not real:
        return None, None
    folder = os.path.join(ROOT, tag + "_bin")
    log = os.path.join(ROOT, tag + "_spawns.log")
    stand_in = os.path.join(folder, VCS)
    write(stand_in, "#!/bin/sh\nprintf '%%s\\n' \"$*\" >> '%s'\nexec '%s' \"$@\"\n" % (log, real))
    os.chmod(stand_in, 0o755)
    return log, folder + os.pathsep + os.environ.get("PATH", "")


def worktree_home_scratchpad_case():
    """Rule 0, `other-checkout`, for a session's own scratchpad. A linked worktree under
    `<temp>/<slug>/<session_id>/scratchpad/` belongs to that session, so its top-level calls may
    write into it from the primary checkout. The same layout under another session's scratchpad, an
    agent call, a call with no session id, a symlink out of the scratchpad, and a `..` path that
    climbs into another checkout stay refused. Labels 1 to 10 name the forms; a failure names its label.
    Why: docs/decisions/an-agent-outside-its-home-tree-must-stop.md (other-checkout)."""
    if os.name == "nt":
        return SKIP, "skipped: a symlink needs a privilege Windows does not grant here"
    primary, _lane_a, lane_b, _scratch = _cross_checkout_fixture("xcoscratch")
    for needed in (os.path.join(primary, ".git"), os.path.join(lane_b, ".git")):
        if not os.path.exists(needed):
            sys.exit("fixture setup failed in worktree_home_scratchpad_case: %r is missing" % needed)
    # The temp folder the guard reads for these calls. It sits in the run folder, so teardown removes it.
    scratch_tmp = os.path.join(ROOT, "xcoscratch_tmp")
    session, other_session = "scratch-sid-0001", "scratch-sid-0002"
    slug, other_slug = "-home-user-claude-settings", "-home-user-compass-dc"
    made = []   # the worktrees this case adds, removed at the end

    def scratch_worktree(slug_name, sid, branch):
        path = os.path.join(scratch_tmp, slug_name, sid, "scratchpad", "wt-notes")
        os.makedirs(os.path.dirname(path), exist_ok=True)
        added = run_vcs(primary, "worktree", "add", "-q", path, "-b", branch)
        if added.returncode != 0 or not os.path.isfile(os.path.join(path, ".git")):
            sys.exit("fixture setup failed in worktree_home_scratchpad_case: git worktree add %r "
                     "failed. stderr: %s" % (path, added.stderr.strip()))
        made.append(path)
        return path

    def climb(start, target):
        """A path that begins inside `start`, climbs out with `..`, and lands on `target`."""
        return os.path.join(start, os.path.relpath(target, start))

    problems = []

    def check(label, expect, tool, cwd, sid=session, agent=None, **tool_input):
        got, reason = _decide_full(tool, cwd, agent_id=agent, session=sid, temp=scratch_tmp,
                                   **tool_input)
        if got != expect:
            problems.append("%s: expected %s, got %s (%s)" % (label, expect, got, reason[:120]))
        elif expect == "deny" and ("other-checkout" not in reason or primary in reason
                                   or scratch_tmp in reason):
            problems.append("%s: the refusal must name other-checkout and no path: %s" % (
                label, reason[:160]))

    try:
        wt_main = scratch_worktree(slug, session, "scratch-notes-main")
        wt_resume = scratch_worktree(other_slug, session, "scratch-notes-resume")
        wt_other = scratch_worktree(slug, other_session, "scratch-notes-other")
        pad = os.path.dirname(wt_main)   # this session's scratchpad, beside its worktree
        link_primary = os.path.join(pad, "to-primary")
        link_lane_b = os.path.join(pad, "to-lane-b")
        os.symlink(primary, link_primary)
        os.symlink(lane_b, link_lane_b)
        brief = os.path.join(pad, "trial", "brief.md")   # a file in the scratchpad, in no checkout
        write(brief, "brief\n")
        bash_echo = "cd %s && echo x > a.txt" % slash(wt_main)

        # 1. Incident 2, exact form. `git add` and `git commit` name no write target, so the exact
        # form is an allow pin. 1b is the red form: a redirect is the write the rule reads.
        check("1a incident 2 git add and commit", "allow", "Bash", primary,
              command="cd %s && git add a.txt && git commit -m x" % slash(wt_main))
        check("1b cd into own scratchpad worktree, then a redirect", "allow", "Bash", primary,
              command=bash_echo)
        # 2. Write and Edit into a file in the own scratchpad worktree.
        check("2a Write into own scratchpad worktree", "allow", "Write", primary,
              file_path=os.path.join(wt_main, "a.txt"), content="x")
        check("2b Edit into own scratchpad worktree", "allow", "Edit", primary,
              file_path=os.path.join(wt_main, "a.txt"), old_string="x", new_string="y")
        # 3. Incident 3: a heredoc written into the own scratchpad worktree.
        check("3 cd into own scratchpad worktree, then a heredoc", "allow", "Bash", primary,
              command="cd %s && cat > f.md <<'EOF'\nx\nEOF" % slash(wt_main))
        # 4. Resume: the same session id, under a second project slug.
        check("4a Write into a worktree under a second slug, same session", "allow", "Write",
              primary, file_path=os.path.join(wt_resume, "a.txt"), content="x")
        check("4b redirect into a worktree under a second slug, same session", "allow", "Bash",
              primary, command="cd %s && echo x > a.txt" % slash(wt_resume))
        # 5. Another session's scratchpad, with the payload carrying this session's id.
        check("5a Write into another session's scratchpad worktree", "deny", "Write", primary,
              file_path=os.path.join(wt_other, "a.txt"), content="x")
        check("5b redirect into another session's scratchpad worktree", "deny", "Bash", primary,
              command="cd %s && echo x > a.txt" % slash(wt_other))
        # 6. The same redirect from an agent that carries this session's id.
        check("6a agent redirect into own scratchpad worktree", "deny", "Bash", primary,
              agent="scratch-agent-1", command=bash_echo)
        check("6b agent Write into own scratchpad worktree", "deny", "Write", primary,
              agent="scratch-agent-1", file_path=os.path.join(wt_main, "a.txt"), content="x")
        # 7. A cd into the own worktree, then a cd into a sibling worktree: the sibling is the target.
        check("7 cd into own worktree, then cd into a sibling, then a redirect", "deny", "Bash",
              primary, command="cd %s && cd %s && echo x > a.txt" % (slash(wt_main), slash(lane_b)))
        # 8. A `..` path that begins inside the own worktree and resolves into another checkout.
        check("8a Write climbing out of own worktree into the primary", "deny", "Write", wt_main,
              file_path=climb(wt_main, os.path.join(primary, "src", "app.py")), content="x")
        check("8b Write climbing out of own worktree into a sibling", "deny", "Write", primary,
              file_path=climb(wt_main, os.path.join(lane_b, "src", "app.py")), content="x")
        check("8c redirect climbing out of own worktree into a sibling", "deny", "Bash", primary,
              command="echo x > " + slash(climb(wt_main, os.path.join(lane_b, "src", "app.py"))))
        # 9. A symlink in the own scratchpad, not a worktree, pointing into another checkout. The
        # lexical path is inside the scratchpad, so only the resolved path tells it apart.
        check("9a Write through a symlink in own scratchpad into the primary", "deny", "Write",
              wt_main, file_path=os.path.join(link_primary, "src", "app.py"), content="x")
        check("9b Write through a symlink in own scratchpad into a sibling", "deny", "Write",
              primary, file_path=os.path.join(link_lane_b, "src", "app.py"), content="x")
        # 10. No session id: the scratchpad layout alone grants nothing.
        check("10a sessionless Write into own scratchpad worktree", "deny", "Write", primary,
              sid=None, file_path=os.path.join(wt_main, "a.txt"), content="x")
        check("10b sessionless redirect into own scratchpad worktree", "deny", "Bash", primary,
              sid=None, command=bash_echo)

        # a. Incident 2's shape, top-level. A leading variable names the own worktree, and the
        # branch, mkdir, cp, add and commit run inside it, then the shell returns to the primary.
        def incident_2(worktree):
            return ('W=%s; cd "$W" && git branch --show-current && mkdir -p docs/plans/trial-briefs'
                    ' && cp %s docs/plans/trial-briefs/q.md && git add docs/plans/trial-briefs/q.md'
                    ' && git commit -m "x" 2>&1 | tail -2; git rev-parse --short HEAD; cd %s'
                    % (slash(worktree), slash(brief), slash(primary)))

        check("a incident 2's shape: variable names own scratchpad worktree, cp and commit in it",
              "allow", "Bash", primary, command=incident_2(wt_main))
        # b. The same shape with the variable naming another session's worktree: refused.
        check("b the same shape, variable names another session's worktree", "deny", "Bash",
              primary, command=incident_2(wt_other))
        # c. Incident 4: an absolute cp into the own worktree, with no cd, then the same cp
        # followed by git -C add and commit in that worktree.
        cp_into_main = "cp %s %s" % (slash(brief), slash(os.path.join(wt_main, "docs", "q.md")))
        check("c1 incident 4: absolute cp into own scratchpad worktree, no cd", "allow", "Bash",
              primary, command=cp_into_main)
        check("c2 incident 4: the cp, then git -C add and commit in that worktree", "allow", "Bash",
              primary, command=cp_into_main + " && git -C %s add docs/q.md && git -C %s commit -m x"
              % (slash(wt_main), slash(wt_main)))
    finally:
        for path in made:
            if os.path.exists(path):
                run_vcs(primary, "worktree", "remove", "--force", path)
        shutil.rmtree(scratch_tmp, ignore_errors=True)
    if problems:
        return False, "; ".join(problems)
    return True, ("1-10: own-scratchpad writes allowed; another session's, agent's, sessionless, "
                  "symlinked and climbing writes refused")


def worktree_home_cross_checkout_cost_case():
    """other-checkout's stated cost: one `git worktree list` per write call and per `cd` into another
    checkout; none for a Read, a Grep, a shell call that writes no file (a `2>&1` or `/dev/null`
    redirect included), a git verb that stays in its own checkout (`commit`, `checkout -b`, `stash list`),
    a `cd` within its own checkout, or a write from a cwd with no `.git` at or above it. A `git -C` into a
    separate clone spends its one list. A python heredoc that prints spends none; one that opens a
    file in another checkout spends one. A stand-in git on PATH logs each spawn."""
    if os.name == "nt":
        return SKIP, "skipped: a stand-in git is not reached through CreateProcess"
    primary, lane_a, lane_b, scratch = _cross_checkout_fixture("xcocost")
    log, path = _stand_in_git("xcocost")
    if path is None:
        return False, "no git on PATH"
    problems = []
    for label, tool, cwd, tool_input, want_all, want_list, *pin in (
        ("Read", "Read", lane_a, {"file_path": os.path.join(lane_b, "src", "app.py")}, 0, 0),
        ("Grep", "Grep", lane_a, {"pattern": "x", "path": lane_b}, 0, 0),
        ("shell ls", "Bash", lane_a, {"command": "ls " + slash(lane_b)}, None, 0),
        ("shell quiet redirects", "Bash", lane_a,
         {"command": "ls " + slash(lane_b) + " 2>&1 >/dev/null"}, None, 0),
        ("shell cd into its own root, then ls", "Bash", lane_a,
         {"command": "cd " + slash(lane_a) + " && ls"}, None, 0),
        ("shell cd into a sibling checkout", "Bash", lane_a,
         {"command": "cd " + slash(lane_b)}, None, 1),
        ("shell cd out of the clone, then ls", "Bash", lane_a,
         {"command": "cd " + slash(scratch) + " && ls"}, None, 0),
        ("Write into its own checkout", "Write", lane_a,
         {"file_path": os.path.join(lane_a, "n.txt"), "content": "x"}, None, 1),
        ("Write from a cwd in no repository", "Write", NOGIT,
         {"file_path": os.path.join(lane_b, "n.txt"), "content": "x"}, None, 0),
        # A separate clone's origin is read from its config file: the act adds no spawn to the one list.
        ("Write into a separate clone", "Write", lane_a,
         {"file_path": os.path.join(XCL_SEP, "note.txt"), "content": "x"}, None, 1),
        ("shell cd into a separate clone", "Bash", lane_a,
         {"command": "cd " + slash(XCL_SEP)}, None, 1),
        ("Read of a separate clone", "Read", lane_a,
         {"file_path": os.path.join(XCL_SEP, "src", "app.py")}, 0, 0),
        # A plain own checkout: its git verbs that change only its own files spawn no list. CLAUDE_PROJECT_DIR
        # names the clone, as a session's does, so the row reads the same way in a real session.
        # A commit also meets the other rules' own git reads (8 spawns on the old code), so its total is
        # not counted: only the list is. checkout -b and stash list spend the list alone, so their total is 0.
        ("shell git commit in its own checkout", "Bash", lane_a,
         {"command": VCS + " commit -m x"}, None, 0, {"CLAUDE_PROJECT_DIR": primary}),
        ("shell git checkout -b in its own checkout", "Bash", lane_a,
         {"command": VCS + " checkout -b x"}, 0, 0, {"CLAUDE_PROJECT_DIR": primary}),
        ("shell git stash list in its own checkout", "Bash", lane_a,
         {"command": VCS + " stash list"}, 0, 0, {"CLAUDE_PROJECT_DIR": primary}),
        ("shell git status in its own checkout", "Bash", lane_a,
         {"command": VCS + " status"}, 0, 0, {"CLAUDE_PROJECT_DIR": primary}),
        ("shell git -C a separate clone commit", "Bash", lane_a,
         {"command": VCS + " -C " + slash(XCL_SEP) + " commit -m x"}, None, 1, {"CLAUDE_PROJECT_DIR": primary}),
        ("shell python heredoc that prints, from its own checkout", "Bash", lane_a,
         {"command": "python3 - <<'PY'\nprint(1)\nPY"}, None, 0),
        ("shell python heredoc that opens a file in another checkout", "Bash", lane_a,
         {"command": "python3 - <<'PY'\nopen('" + slash(lane_b) + "/x','w')\nPY"}, None, 1),
    ):
        if os.path.exists(log):
            os.remove(log)
        decide({"raw": None, "tool": tool, "cwd": cwd, "session": None, "env_path": path,
                "config": None, "agent_id": None, "tool_input": tool_input,
                "temp": os.path.join(ROOT, "tmp"),  # a separate clone must sit outside the temp folder
                "env": pin[0] if pin else None})
        spawns = open(log, encoding="utf-8").read().splitlines() if os.path.exists(log) else []
        listed = sum(1 for line in spawns if "worktree list" in line)
        if (want_all is not None and len(spawns) != want_all) or listed != want_list:
            problems.append("%s: %d git spawn(s), %d worktree list, want %s and %d" % (
                label, len(spawns), listed, "any" if want_all is None else want_all, want_list))
    if problems:
        return False, "; ".join(problems)
    return True, ("Read, Grep, quiet shell, own-checkout git verbs and no-repo writes spawn no worktree list; "
                  "a write, a cd or a git -C into a separate clone spawns one list, and a read of one spawns none")


def worktree_home_cross_checkout_override_case():
    """other-checkout is liftable: the owner may mean a write into another checkout. worktree-home,
    the agent-home part, stays unliftable (ov_drift_acts)."""
    primary, lane_a, lane_b, _ = _cross_checkout_fixture("xcoov")
    config = ov_config("cross-checkout")
    session = "ov-cross-checkout"
    call = lambda s: ov_call("Write", {"file_path": os.path.join(lane_b, "src", "app.py"),
                                       "content": "x"}, lane_a, config, session, s)
    problem = ov_want(*call(0), "deny", "other-checkout")
    if problem:
        return False, "before the override: " + problem
    note = ov_type(config, session, "override 15m", 30)
    ok, why = ov_story([("under a timed override", lambda: call(60), "allow", "other-checkout")], note)
    return ok, why or "refused before the override, lifted under it"


# other-checkout's `cd` act. A `cd` into another checkout would let a build or a write run past the
# write scan, so the act refuses the `cd` before that scan reads the command.
CD_AGENT_HOME = "xcoagenta1"     # an agent id, whose worktree is the recorded home
CD_AGENT_SIBLING = "xcoagentb2"  # a second agent id, whose worktree sits beside that home
CD_REFUSE_FORMS = (
    "cd TARGET",
    "cd TARGET && npm run build",
    "cd TARGET && make up",
    "cd TARGET && npm install",
    "cd TARGET && touch x",
    "cd TARGET && mkdir d",
)


def _other_checkout_problems(label, got, reason, paths):
    """An other-checkout refusal names the rule and none of `paths`. Any other verdict is a problem."""
    if got != "deny":
        return ["%s: want deny, got %s (%s)" % (label, got, reason[:120])]
    problems = []
    if "other-checkout" not in reason:
        problems.append("%s: the refusal does not name other-checkout: %s" % (label, reason[:160]))
    for text in paths:
        if text in reason:
            problems.append("%s: the refusal names %r" % (label, text))
    return problems


def worktree_home_cd_into_other_checkout_case():
    """Rule 0, other-checkout, the `cd` act: a Bash `cd` into another checkout of the clone is
    refused, bare or chained to a build, a write or a folder made. It is judged from the primary and
    from a lane, into a lane or into the primary, and the refusal names no path.
    Decision: an-agent-outside-its-home-tree-must-stop."""
    primary, lane_a, lane_b, _ = _cross_checkout_fixture("xcocd")
    problems = []
    for cwd, target in ((primary, lane_b), (lane_a, lane_b), (lane_a, primary)):
        for form in CD_REFUSE_FORMS:
            command = form.replace("TARGET", slash(target))
            label = "%s from %s" % (command, os.path.relpath(cwd, ROOT))
            got, reason = _decide_full("Bash", cwd, command=command)
            problems += _other_checkout_problems(label, got, reason,
                                                 (ROOT, slash(ROOT), target, slash(target)))
    if problems:
        return False, "; ".join(problems)
    return True, "every cd into another checkout is refused, bare or chained, and names no path"


def _remedy_problems(label, got, reason):
    """The other-checkout remedy names OTHER_CHECKOUT_ENTER_SHAPE, and no `cd` or `env -C` route.
    A verdict other than deny is one problem, and the remedy is not read."""
    if got != "deny":
        return ["%s: want deny, got %s (%s)" % (label, got, reason[:120])]
    problems = []
    if OTHER_CHECKOUT_ENTER_SHAPE not in reason:
        problems.append("%s: the remedy does not say %r: %s" % (
            label, OTHER_CHECKOUT_ENTER_SHAPE, reason[:160]))
    if "`cd`" in reason:
        problems.append("%s: the remedy names `cd`: %s" % (label, reason[:160]))
    if "env -C" in reason:
        problems.append("%s: the remedy names env -C: %s" % (label, reason[:160]))
    return problems


def worktree_home_other_checkout_remedy_case():
    """Rule 0, `other-checkout`, the remedy on both refusals: a write into a sibling checkout, and a
    `cd` into one, each name the EnterWorktree call with `path` set to the checkout, and neither names
    `cd` or `env -C` as a route. A refusal must not name the route it refused, or the agent takes that route."""
    primary, lane_a, lane_b, _ = _cross_checkout_fixture("xcocd")
    in_b = os.path.join(lane_b, "src", "app.py")
    problems = []
    got, reason = _decide_full("Write", lane_a, file_path=in_b, content="x")
    problems += _remedy_problems("write into a sibling checkout", got, reason)
    got, reason = _decide_full("Bash", lane_a, command="cd " + slash(lane_b))
    problems += _remedy_problems("cd into a sibling checkout", got, reason)
    if problems:
        return False, "; ".join(problems)
    return True, "the write and the cd refusals name the EnterWorktree call with path, and no cd or env -C route"


def worktree_home_cd_parse_forms_case():
    """Rule 0, other-checkout, the `cd` act's parse: a relative climb, a subshell and a PowerShell
    `Set-Location` each move into another checkout, and each is refused."""
    primary, lane_a, lane_b, _ = _cross_checkout_fixture("xcocdparse")
    rows = (
        ("Bash", lane_a, "cd ../lane-b && ls", lane_b),
        ("Bash", lane_a, "(cd %s && make)" % slash(lane_b), lane_b),
        ("Bash", primary, "(cd %s && make)" % slash(lane_b), lane_b),
        ("PowerShell", lane_a, "Set-Location %s" % slash(lane_b), lane_b),
        ("PowerShell", primary, "Set-Location %s" % slash(lane_b), lane_b),
        ("PowerShell", lane_b, "Set-Location %s" % slash(primary), primary),
    )
    problems = []
    for tool, cwd, command, target in rows:
        got, reason = _decide_full(tool, cwd, command=command)
        label = "%s %r from %s" % (tool, command, os.path.relpath(cwd, ROOT))
        problems += _other_checkout_problems(label, got, reason,
                                             (ROOT, slash(ROOT), target, slash(target)))
    if problems:
        return False, "; ".join(problems)
    return True, "a relative climb, a subshell and a PowerShell Set-Location into another checkout are refused"


def worktree_home_cd_variable_climb_case():
    """Rule 0, other-checkout, the `cd` act with a variable folder: a relative cd made from the folder a
    variable names is judged from that folder, as from the literal folder. From lane-a, `cd "$R" && cd
    ../lane-b` moves into lane-b and is refused, as `cd <lane-a> && cd ../lane-b` is."""
    primary, lane_a, lane_b, _ = _cross_checkout_fixture("xcocdvar")
    problems = []
    rows = (
        ("the literal folder", "cd %s && cd ../lane-b && ls" % slash(lane_a)),
        ("a variable folder", 'R=%s; cd "$R" && cd ../lane-b && ls' % slash(lane_a)),
    )
    for label, command in rows:
        got, reason = _decide_full("Bash", lane_a, command=command)
        problems += _other_checkout_problems(label, got, reason,
                                             (ROOT, slash(ROOT), lane_b, slash(lane_b)))
    if problems:
        return False, "; ".join(problems)
    return True, "a relative cd from a variable folder into another checkout is refused, as from a literal one"


def worktree_home_cd_agent_sibling_case():
    """Rule 0, other-checkout, the `cd` act for an agent in its own worktree: a `cd` into a sibling
    agent's tree, bare or chained, is refused, and so is a folder whose name only starts with the
    agent's own id. The agent's own red-run folder is the one exemption (worktree_home_cd_exempt_case)."""
    primary, home, sibling, _ = _cross_checkout_fixture(
        "xcoagent", lanes=("agent-" + CD_AGENT_HOME, "agent-" + CD_AGENT_SIBLING))
    prefix_trap = sh_add_lane(primary, "agent-" + CD_AGENT_HOME + "b-red")[0]
    problems = []
    got, reason = _decide_full("Bash", home, agent_id=CD_AGENT_HOME, command="echo hi")
    if got != "allow":
        problems.append("the recording call: want allow, got %s (%s)" % (got, reason[:120]))
    if not os.path.isfile(os.path.join(primary, ".git", "agent-homes", CD_AGENT_HOME)):
        problems.append("the recording call wrote no home record")
    for target in (sibling, prefix_trap):
        for form in ("cd TARGET", "cd TARGET && make"):
            command = form.replace("TARGET", slash(target))
            got, reason = _decide_full("Bash", home, agent_id=CD_AGENT_HOME, command=command)
            problems += _other_checkout_problems(command, got, reason,
                                                 (ROOT, slash(ROOT), target, slash(target)))
    if problems:
        return False, "; ".join(problems)
    return True, "an agent's cd into a sibling agent tree, or a prefix-named folder, is refused"


def worktree_home_cd_allowed_case():
    """Rule 0, other-checkout, the `cd` act passes a cd that is not into another checkout: the cwd's
    own root or subfolder, a folder outside the clone, and the clone's own `.git`, which no one
    checkout owns."""
    primary, lane_a, lane_b, scratch = _cross_checkout_fixture("xcocdok")
    rows = (
        (lane_a, "cd %s && ls" % slash(lane_a)),
        (lane_a, "cd %s && make" % slash(os.path.join(lane_a, "src"))),
        (primary, "cd %s && ls" % slash(primary)),
        (lane_a, "cd %s && touch x" % slash(scratch)),
        (lane_a, "cd %s && ls" % slash(os.path.join(primary, ".git"))),
    )
    problems = []
    for cwd, command in rows:
        _expect_call(problems, "%s from %s" % (command, os.path.relpath(cwd, ROOT)), "allow",
                     "Bash", cwd, None, command)
    if problems:
        return False, "; ".join(problems)
    return True, "own root, own subfolder, a scratch folder and the clone's .git pass"


def worktree_home_cd_exempt_case():
    """Rule 0, other-checkout, its exemptions, each a cd and nothing else: an agent's `cd` into its
    recorded home from outside it (the recovery step); an agent's `cd` into its own red-run folder,
    `agent-<its id>-red`, chained to a test run; and a top-level session's `cd` into its own recorded
    worktree from the primary checkout."""
    primary, home, _, _ = _cross_checkout_fixture(
        "xcoexempt", lanes=("agent-" + CD_AGENT_HOME, "agent-" + CD_AGENT_SIBLING))
    red = sh_add_lane(primary, "agent-" + CD_AGENT_HOME + "-red")[0]
    session_lane = sh_add_lane(primary, "lane-session")[0]
    session = sh_session()
    problems = []
    got, reason = _decide_full("Bash", home, agent_id=CD_AGENT_HOME, command="echo hi")
    if got != "allow":
        problems.append("the agent's recording call: want allow, got %s (%s)" % (got, reason[:120]))
    if not os.path.isfile(os.path.join(primary, ".git", "agent-homes", CD_AGENT_HOME)):
        problems.append("the agent's recording call wrote no home record")
    got, reason = _decide_full("Bash", session_lane, session=session, command="echo hi")
    if got != "allow":
        problems.append("the session's recording call: want allow, got %s (%s)" % (got, reason[:120]))
    if not sh_holds(primary, session, session_lane):
        problems.append("the session's recording call wrote no session record naming the lane")
    _expect_call(problems, "agent cd into its recorded home from primary", "allow", "Bash",
                 primary, CD_AGENT_HOME, "cd " + slash(home))
    _expect_call(problems, "agent cd into its red-run folder, chained to a test run", "allow",
                 "Bash", home, CD_AGENT_HOME, "cd %s && python3 x.py" % slash(red))
    got, reason = _decide_full("Bash", primary, session=session, command="cd " + slash(session_lane))
    if got != "allow":
        problems.append("session cd into its recorded home from primary: want allow, got %s (%s)"
                        % (got, reason[:120]))
    if problems:
        return False, "; ".join(problems)
    return True, "the recorded home, the own red-run folder and the session's recorded home pass"


def worktree_home_red_write_case():
    """Rule 0, other-checkout, the write act's exemption for the caller's own red-run folder: an
    agent's writes into `agent-<its id>-red` pass from its home, as a `cd` chained to a write, a `cp`,
    a Write and an Edit. The same four writes into a sibling agent's red-run folder, into a folder
    whose name only starts with the agent's id, into the primary, or from a call with no agent_id are
    refused. A test-author writes its tests in its red-run folder, so the write act must match the
    cd act that worktree_home_cd_exempt_case already allows."""
    primary, home, _, _ = _cross_checkout_fixture(
        "xcored", lanes=("agent-" + CD_AGENT_HOME, "agent-" + CD_AGENT_SIBLING))
    red = sh_add_lane(primary, "agent-" + CD_AGENT_HOME + "-red")[0]
    sibling_red = sh_add_lane(primary, "agent-" + CD_AGENT_SIBLING + "-red")[0]
    prefix_trap = sh_add_lane(primary, "agent-" + CD_AGENT_HOME + "b-red")[0]
    write(os.path.join(home, "t.py"), "print(1)\n")
    problems = []
    got, reason = _decide_full("Bash", home, agent_id=CD_AGENT_HOME, command="echo hi")
    if got != "allow":
        problems.append("the agent's recording call: want allow, got %s (%s)" % (got, reason[:120]))
    if not os.path.isfile(os.path.join(primary, ".git", "agent-homes", CD_AGENT_HOME)):
        problems.append("the agent's recording call wrote no home record")

    def writes_into(folder):
        """(tool, tool input) for the four writes into FOLDER: a chained cd, a cp, a Write and an Edit."""
        return (
            ("Bash", {"command": "cd %s && echo x > f" % slash(folder)}),
            ("Bash", {"command": "cp t.py %s/" % slash(folder)}),
            ("Write", {"file_path": os.path.join(folder, "f"), "content": "x"}),
            ("Edit", {"file_path": os.path.join(folder, "f"), "old_string": "1", "new_string": "2"}),
        )

    def label(tool, tool_input):
        return "%s %r" % (tool, tool_input.get("command") or tool_input["file_path"])

    for tool, tool_input in writes_into(red):
        got, reason = _decide_full(tool, home, agent_id=CD_AGENT_HOME, **tool_input)
        if got != "allow":
            problems.append("%s into the agent's own red-run folder: want allow, got %s (%s)"
                            % (label(tool, tool_input), got, reason[:120]))
    for target in (sibling_red, prefix_trap, primary):
        for tool, tool_input in writes_into(target):
            got, reason = _decide_full(tool, home, agent_id=CD_AGENT_HOME, **tool_input)
            if got != "deny" or any(text in reason for text in (ROOT, slash(ROOT), target, slash(target))):
                problems.append("%s: want deny naming no path, got %s (%s)"
                                % (label(tool, tool_input), got, reason[:120]))
    for tool, tool_input in writes_into(red):
        got, reason = _decide_full(tool, home, **tool_input)
        problems += _other_checkout_problems("no agent_id: " + label(tool, tool_input), got, reason,
                                             (ROOT, slash(ROOT), red, slash(red)))
    if problems:
        return False, "; ".join(problems)
    return True, "an agent's writes into its own red-run folder pass; the same writes elsewhere are refused"


def worktree_home_red_root_case():
    """Rule 0, other-checkout, the folder root of the caller's own red-run folder: a write may land
    inside it, never remove or move it. `rm -rf` of the folder, with or without a trailing slash, a
    `cd` into it chained to `rm -rf .`, `mv` of it and a Write on its path are refused. A `cp` into
    it, a `cd` into it chained to a `cp`, and a Write inside it pass. Decision:
    an-agent-outside-its-home-tree-must-stop."""
    primary, home, _, _ = _cross_checkout_fixture(
        "xcoredroot", lanes=("agent-" + CD_AGENT_HOME, "agent-" + CD_AGENT_SIBLING))
    red = sh_add_lane(primary, "agent-" + CD_AGENT_HOME + "-red")[0]
    write(os.path.join(home, "t.py"), "print(1)\n")
    got, reason = _decide_full("Bash", home, agent_id=CD_AGENT_HOME, command="echo hi")
    if got != "allow" or not os.path.isfile(os.path.join(primary, ".git", "agent-homes", CD_AGENT_HOME)):
        return False, ("the agent's recording call: want allow and a home record, got %s (%s)"
                       % (got, reason[:120]))
    paths = (ROOT, slash(ROOT), red, slash(red))
    problems = []
    for label, tool, tool_input in (
        ("rm -rf <red>", "Bash", {"command": "rm -rf %s" % slash(red)}),
        ("rm -rf <red>/", "Bash", {"command": "rm -rf %s/" % slash(red)}),
        ("cd <red> && rm -rf .", "Bash", {"command": "cd %s && rm -rf ." % slash(red)}),
        ("mv <red> x", "Bash", {"command": "mv %s x" % slash(red)}),
        ("Write on <red>", "Write", {"file_path": red, "content": "x"}),
    ):
        got, reason = _decide_full(tool, home, agent_id=CD_AGENT_HOME, **tool_input)
        if tool == "Bash":
            problems += _other_checkout_problems(label, got, reason, paths)
        elif got != "deny" or any(text in reason for text in paths):
            problems.append("%s: want deny naming no path, got %s (%s)" % (label, got, reason[:120]))
    for label, tool, tool_input in (
        ("cp t.py <red>/", "Bash", {"command": "cp t.py %s/" % slash(red)}),
        ("cd <red> && cp x .", "Bash", {"command": "cd %s && cp x ." % slash(red)}),
        ("Write inside <red>", "Write", {"file_path": os.path.join(red, "f"), "content": "x"}),
    ):
        got, reason = _decide_full(tool, home, agent_id=CD_AGENT_HOME, **tool_input)
        if got != "allow":
            problems.append("%s: want allow, got %s (%s)" % (label, got, reason[:120]))
    if problems:
        return False, "; ".join(problems)
    return True, "the red-run folder's root is refused to rm, mv and a Write; a cp into it and a write inside it pass"


def worktree_home_red_nested_case():
    """Rule 0, other-checkout, the red-run folder is the primary's alone: a folder named
    `agent-<its id>-red` under another linked worktree's `.claude/worktrees/` belongs to that
    worktree, so a `cd` into it, a shell write into it and a Write into it are refused. Decision:
    an-agent-outside-its-home-tree-must-stop."""
    primary, home, lane_b, _ = _cross_checkout_fixture(
        "xcorednest", lanes=("agent-" + CD_AGENT_HOME, "lane-b"))
    nested = os.path.join(lane_b, ".claude", "worktrees", "agent-" + CD_AGENT_HOME + "-red")
    os.makedirs(nested, exist_ok=True)
    got, reason = _decide_full("Bash", home, agent_id=CD_AGENT_HOME, command="echo hi")
    if got != "allow" or not os.path.isfile(os.path.join(primary, ".git", "agent-homes", CD_AGENT_HOME)):
        return False, ("the agent's recording call: want allow and a home record, got %s (%s)"
                       % (got, reason[:120]))
    paths = (ROOT, slash(ROOT), nested, slash(nested), lane_b, slash(lane_b))
    problems = []
    for label, tool, tool_input in (
        ("cd <nested>", "Bash", {"command": "cd %s" % slash(nested)}),
        ("echo x > <nested>/f", "Bash", {"command": "echo x > %s/f" % slash(nested)}),
        ("Write <nested>/f", "Write", {"file_path": os.path.join(nested, "f"), "content": "x"}),
    ):
        got, reason = _decide_full(tool, home, agent_id=CD_AGENT_HOME, **tool_input)
        if tool == "Bash":
            problems += _other_checkout_problems(label, got, reason, paths)
        elif got != "deny" or any(text in reason for text in paths):
            problems.append("%s: want deny naming no path, got %s (%s)" % (label, got, reason[:120]))
    if problems:
        return False, "; ".join(problems)
    return True, "a red-run folder nested under another linked worktree is refused to a cd, a shell write and a Write"


RED_CASE_OFF_WINDOWS = ("Windows folds path case, so another spelling of the red-run folder is that "
                        "folder only there; on POSIX it is another folder, so this case does not run")


def worktree_home_red_case_fold_case():
    """Rule 0, other-checkout, the write act's exemption on Windows: the caller's own red-run folder
    spelled in other letters of case is the same folder, so a Write into it and a `cd` into it
    chained to a write pass. Decision: an-agent-outside-its-home-tree-must-stop."""
    if os.name != "nt":
        return SKIP, RED_CASE_OFF_WINDOWS
    primary, home, _, _ = _cross_checkout_fixture(
        "xcorecase", lanes=("agent-" + CD_AGENT_HOME, "agent-" + CD_AGENT_SIBLING))
    sh_add_lane(primary, "agent-" + CD_AGENT_HOME + "-red")
    upper = os.path.join(primary, ".claude", "worktrees", "AGENT-" + CD_AGENT_HOME.upper() + "-RED")
    got, reason = _decide_full("Bash", home, agent_id=CD_AGENT_HOME, command="echo hi")
    if got != "allow" or not os.path.isfile(os.path.join(primary, ".git", "agent-homes", CD_AGENT_HOME)):
        return False, ("the agent's recording call: want allow and a home record, got %s (%s)"
                       % (got, reason[:120]))
    problems = []
    for label, tool, tool_input in (
        ("Write into the upper-case red-run folder", "Write",
         {"file_path": os.path.join(upper, "f"), "content": "x"}),
        ("cd into the upper-case red-run folder chained to a write", "Bash",
         {"command": "cd %s && echo x > f" % slash(upper)}),
    ):
        got, reason = _decide_full(tool, home, agent_id=CD_AGENT_HOME, **tool_input)
        if got != "allow":
            problems.append("%s: want allow, got %s (%s)" % (label, got, reason[:120]))
    if problems:
        return False, "; ".join(problems)
    return True, "a write into the red-run folder spelled in other letters of case passes"


# Text is not a move: a `cd` in a comment, in quotes or in a heredoc body is never run. A real `cd`
# after one of those still is, and a comment opener or a lone quote inside a string must not hide it.
CD_TEXT_ALLOW = (
    'echo "cd TARGET && npm run build"',
    "# cd TARGET\nls",
    "ls # cd TARGET",
    "cat <<EOF\ncd TARGET && make\nEOF\nls",
    'echo "line one\ncd TARGET && make\nend"',
    'echo "Don\'t" ; ls',
)
CD_TEXT_REFUSE = (
    'echo "# note" && cd TARGET && make',
    'echo "a // b" ; cd TARGET && make',
    'echo "/*" ; cd TARGET && make',
    'echo "Don\'t" ; cd TARGET && make',
    "# note\ncd TARGET && make",
    "cat <<EOF\ncd TARGET\nEOF\ncd TARGET && make",
    'echo "line one\n"\ncd TARGET && make',
)


def worktree_home_cd_text_case():
    """Rule 0, other-checkout, the `cd` act reads a cd as text when it sits in a comment, in quotes or
    in a heredoc body, and reads a real cd after any of those as a move."""
    primary, lane_a, lane_b, _ = _cross_checkout_fixture("xcotext")
    problems = []
    for template in CD_TEXT_ALLOW:
        command = template.replace("TARGET", slash(lane_b))
        _expect_call(problems, repr(command), "allow", "Bash", lane_a, None, command)
    for template in CD_TEXT_REFUSE:
        command = template.replace("TARGET", slash(lane_b))
        got, reason = _decide_full("Bash", lane_a, command=command)
        problems += _other_checkout_problems(repr(command), got, reason,
                                             (ROOT, slash(ROOT), lane_b, slash(lane_b)))
    if problems:
        return False, "; ".join(problems)
    return True, "a cd in a comment, a quote or a heredoc body passes; a real cd after one is refused"


def worktree_home_cd_override_case():
    """Rule 0, other-checkout, the `cd` act is liftable, like the write act: under a timed owner
    override a bare cd into another checkout passes, because the owner may mean the cd."""
    primary, lane_a, lane_b, _ = _cross_checkout_fixture("xcocdov")
    config = ov_config("cross-checkout-cd")
    session = "ov-cross-checkout-cd"
    call = lambda s: ov_call("Bash", {"command": "cd " + slash(lane_b)}, lane_a, config, session, s)
    problem = ov_want(*call(0), "deny", "other-checkout")
    if problem:
        return False, "before the override: " + problem
    note = ov_type(config, session, "override 15m", 30)
    ok, why = ov_story([("under a timed override", lambda: call(60), "allow", "other-checkout")], note)
    return ok, why or "refused before the override, lifted under it"


def worktree_home_cd_then_write_case():
    """Rule 0, other-checkout, the write scan follows a leading cd. A cd that the cd act passes (into
    the cwd's own root, here its `src` folder) moves the folder a later relative write resolves
    against, so the write lands in another checkout only from there, and the guard refuses it. The
    control writes the same text with no cd from the primary, which lands outside the clone.
    Kills the mutant "other-checkout: a shell target ignores a leading cd"."""
    primary, lane_a, lane_b, _ = _cross_checkout_fixture("xcowrite")
    own_src = os.path.join(primary, "src")
    # From `src` this names lane-b's file. From the primary checkout it names a folder outside the clone.
    relative = slash(os.path.relpath(os.path.join(lane_b, "a.txt"), own_src))
    problems = []
    got, reason = _decide_full("Bash", primary, command="cd " + slash(own_src) + " && echo x > " + relative)
    problems += _other_checkout_problems("cd into its own src, then a relative write into lane-b", got,
                                         reason, (ROOT, slash(ROOT), lane_b, slash(lane_b)))
    _expect_call(problems, "the same relative write with no cd, from the primary", "allow", "Bash",
                 primary, None, "echo x > " + relative)
    if problems:
        return False, "; ".join(problems)
    return True, "a relative write into another checkout, resolved from the cd's folder, is refused"


def worktree_home_cd_after_untracked_case():
    """Rule 0, other-checkout, a later absolute cd is judged where it lands. After a move whose folder
    the guard cannot tell (`-`, and `"$HOME"` on the current code), or after a cd to a folder that is
    missing, an absolute cd into another checkout is still refused. A cd whose target is missing makes
    the folder unknown again, so a relative cd after it is not judged. That is a declared limit, and it
    keeps ordinary work from a worktree root (a folder made, entered and left) allowed. From a lane."""
    primary, lane_a, lane_b, _ = _cross_checkout_fixture("xcountracked")
    ghost = os.path.join(lane_a, "ghost")  # a folder that does not exist, so its cd fails
    deny = (
        'cd "$HOME" && cd TARGET && make',
        "cd - ; cd TARGET",
        "cd GHOST ; cd TARGET",
    )
    allow = (
        # Declared limit: after a missing-target cd the folder is unknown, so this relative cd is not judged.
        "cd GHOST ; cd ../lane-b && make",
        # Ordinary work from the worktree root, with each folder missing when its cd is checked.
        "mkdir -p newdir && cd newdir && touch a && cd ..",
        "mkdir -p x; cd x; cd ..",
        "cd newdir; cd ..",
    )
    problems = []
    for template in deny:
        command = template.replace("TARGET", slash(lane_b)).replace("GHOST", slash(ghost))
        got, reason = _decide_full("Bash", lane_a, command=command)
        problems += _other_checkout_problems(command, got, reason,
                                             (ROOT, slash(ROOT), lane_b, slash(lane_b)))
    for template in allow:
        command = template.replace("GHOST", slash(ghost))
        _expect_call(problems, command, "allow", "Bash", lane_a, None, command)
    if problems:
        return False, "; ".join(problems)
    return True, "an absolute cd after an untracked move or a missing folder is refused; ordinary work allows"


def worktree_home_pushd_case():
    """Rule 0, other-checkout, `pushd` is a move, as `cd` is. From a lane, a `pushd` into another checkout
    is refused, bare or chained, and a `pushd` within the cwd's own checkout or into a folder outside the
    clone passes."""
    primary, lane_a, lane_b, scratch = _cross_checkout_fixture("xcopush")
    deny = (
        "pushd " + slash(lane_b),
        "pushd " + slash(lane_b) + " && make",
        "pushd ../lane-b >/dev/null && make",
    )
    allow = (
        "pushd " + slash(os.path.join(lane_a, "src")) + " && make",
        "pushd " + slash(scratch),
        # `-n` suppresses the change of directory: the stack only, so it moves nothing.
        "pushd -n " + slash(lane_b),
        "pushd -n ../lane-b",
    )
    problems = []
    for command in deny:
        got, reason = _decide_full("Bash", lane_a, command=command)
        problems += _other_checkout_problems(command, got, reason,
                                             (ROOT, slash(ROOT), lane_b, slash(lane_b)))
    for command in allow:
        _expect_call(problems, command, "allow", "Bash", lane_a, None, command)
    if problems:
        return False, "; ".join(problems)
    return True, "pushd into another checkout is refused; pushd within the own checkout or outside the clone passes"


def worktree_home_later_field_case():
    """Rule 0 judges EVERY path field of a write call, not only the first (PR #306 review gap).

    A call whose first field is inside the recorded home and whose later field is outside it must
    be refused as worktree-home. A home loop that reads only the first field lets it through.
    """
    agent_id = "wthomefield1"
    primary = os.path.join(ROOT, "wthomefield_primary")
    worktree = os.path.join(primary, ".claude", "worktrees", "agent-" + agent_id)
    make_repo(primary, {"src/app.py": "print(1)\n", "src/other.py": "print(2)\n"})
    run_vcs(primary, "worktree", "add", "-q", worktree, "-b", "worktree-agent-" + agent_id)
    inside = os.path.join(worktree, "src", "app.py")
    outside = os.path.join(primary, "src", "other.py")

    problems = []
    # The first call from inside the worktree records the home.
    got, reason = _decide_full("Bash", worktree, agent_id=agent_id, command="echo hi")
    if got != "allow":
        problems.append("recording call: expected allow, got %s (%s)" % (got, reason[:120]))
    # First field inside the home, second field in the primary checkout: refused.
    got, reason = _decide_full("Edit", worktree, agent_id=agent_id, file_path=inside,
                               path=outside, old_string="a", new_string="b")
    if got != "deny" or "worktree-home" not in reason:
        problems.append("inside then outside: expected deny worktree-home, got %s (%s)" % (
            got, reason[:120]))
    # Control: two fields both inside the home stay allowed.
    got, reason = _decide_full("Edit", worktree, agent_id=agent_id, file_path=inside,
                               path=inside, old_string="a", new_string="b")
    if got != "allow":
        problems.append("inside then inside: expected allow, got %s (%s)" % (got, reason[:120]))

    if problems:
        return False, "; ".join(problems)
    return True, "a later field outside the home is refused; two fields inside stay allowed"


def _posix_form(path):
    """The `/c/Users/...` spelling of a Windows path, as Git Bash and the Bash tool print it.
    A path with no drive letter has no other spelling, so it comes back as itself."""
    drive, rest = os.path.splitdrive(path)
    if not drive:
        return slash(path)
    return "/" + drive[0].lower() + slash(rest)


def _home_fixture(agent_id):
    """One primary checkout, one linked worktree of it for `agent_id`, and that agent's first call
    from inside the worktree, which records the home. Returns (primary, worktree, problems)."""
    primary = os.path.join(ROOT, "wthome_" + agent_id + "_primary")
    worktree = os.path.join(primary, ".claude", "worktrees", "agent-" + agent_id)
    make_repo(primary, {"src/app.py": "print(1)\n"})
    run_vcs(primary, "worktree", "add", "-q", worktree, "-b", "worktree-agent-" + agent_id)
    got, reason = _decide_full("Bash", worktree, agent_id=agent_id, command="echo hi")
    problems = []
    if got != "allow":
        problems.append("recording call: expected allow, got %s (%s)" % (got, reason[:120]))
    return primary, worktree, problems


def _expect_call(problems, label, expect, tool, cwd, agent_id, command, rule=None):
    """Run one call. A problem is recorded unless it gets `expect`, and a deny must name `rule`."""
    got, reason = _decide_full(tool, cwd, agent_id=agent_id, command=command)
    if got != expect:
        problems.append("%s: expected %s, got %s (%s)" % (label, expect, got, reason[:120]))
    elif rule and rule not in reason:
        problems.append("%s: the deny does not name %s (%s)" % (label, rule, reason[:120]))


# (shell, command template): the lone command that moves into a directory.
MOVE_STEPS = (("Bash", "cd %s"), ("PowerShell", "Set-Location %s"))


def worktree_home_lone_cd_case():
    """Rule 0: a lone `cd` (Bash) or `Set-Location` (PowerShell) into the recorded home is allowed,
    from a cwd outside that home, with the home written as a Windows or a POSIX path.

    Without this, a stray `Set-Location` leaves the PowerShell cwd outside the home, and every later
    call is refused, including the one that would move it back.
    """
    agent_id = "wthomelone1"
    primary, worktree, problems = _home_fixture(agent_id)
    for shell, template in MOVE_STEPS:
        for home in (worktree, _posix_form(worktree)):
            _expect_call(problems, "%s into %s from outside" % (shell, home), "allow", shell,
                         primary, agent_id, template % home)
    if problems:
        return False, "; ".join(problems)
    return True, "a lone cd or Set-Location into the home is allowed in both path forms"


def worktree_home_chained_case():
    """Rule 0: a `cd` or `Set-Location` into the home that has another command chained after it is
    still refused, from a cwd outside the home. The lone-step allowance must not reach a chain."""
    agent_id = "wthomechain1"
    primary, worktree, problems = _home_fixture(agent_id)
    chained = (("Bash", "cd %s; git push"), ("PowerShell", "Set-Location %s; rm x"))
    for shell, template in chained:
        for home in (worktree, _posix_form(worktree)):
            _expect_call(problems, "%s chained into %s from outside" % (shell, home), "deny",
                         shell, primary, agent_id, template % home, rule="worktree-home")
    if problems:
        return False, "; ".join(problems)
    return True, "a chained command after a move into the home is refused, in both path forms"


def worktree_home_posix_cwd_case():
    """Rule 0: a cwd given in POSIX form, `/c/Users/...`, names the same folder as the Windows
    home the agent recorded. Inside that home it is allowed. The same form outside it is refused,
    so the spelling alone never decides which side a cwd is on."""
    agent_id = "wthomeposix1"
    primary, worktree, problems = _home_fixture(agent_id)
    _expect_call(problems, "POSIX cwd inside the home", "allow", "Bash", _posix_form(worktree),
                 agent_id, "echo hi")
    # An allow alone cannot show the cwd was READ as inside: an unreadable home also allows. An
    # Edit to the primary checkout from that cwd is refused only once the home is known.
    got, reason = _decide_full("Edit", _posix_form(worktree), agent_id=agent_id,
                               file_path=os.path.join(primary, "src", "app.py"),
                               old_string="a", new_string="b")
    if got != "deny" or "worktree-home" not in reason:
        problems.append("POSIX cwd inside the home, Edit outside it: expected deny worktree-home, "
                        "got %s (%s)" % (got, reason[:120]))
    _expect_call(problems, "POSIX cwd outside the home", "deny", "Bash", _posix_form(primary),
                 agent_id, "echo hi", rule="worktree-home")
    if problems:
        return False, "; ".join(problems)
    return True, "a /c/ cwd inside the home is allowed; the same form outside is refused"


def worktree_home_cd_out_case():
    """Rule 0: a `cd` or `Set-Location` from a cwd outside the home, to a path outside the home, is
    still refused. The target is a folder in the primary checkout, or the home's own name with a
    suffix, which shares its text but is not inside it."""
    agent_id = "wthomeout1"
    primary, worktree, problems = _home_fixture(agent_id)
    targets = (os.path.join(primary, "src"), worktree + "-sibling")
    for shell, template in MOVE_STEPS:
        for target in targets:
            for form in (target, _posix_form(target)):
                _expect_call(problems, "%s to %s from outside" % (shell, form), "deny", shell,
                             primary, agent_id, template % form, rule="worktree-home")
    if problems:
        return False, "; ".join(problems)
    return True, "a cd or Set-Location outside the home, or to its suffixed sibling, is refused"


# A lone move into the home is allowed only when its raw command holds no separator. A backslash
# before a quote hides the separator from the splitter, which reads the quote as an opener, while
# the shell still runs the step after it. These cases cover that gap, and the plain separators.
QUOTED_MOVES = (
    ("Bash", 'cd %s\\";git push\\"'),
    ("Bash", "cd %s\\';git push\\'"),
    ("Bash", 'cd %s\\"\ngit push\\"'),
    ("Bash", 'cd %s\\"\rgit push\\"'),
    ("PowerShell", 'Set-Location %s\\";git push\\"'),
    ("PowerShell", "Set-Location %s\\';git push\\'"),
)
PLAIN_MOVES = (
    ("Bash", "cd %s;git push"), ("Bash", "cd %s&git push"), ("Bash", "cd %s|git push"),
    ("Bash", "cd %s\ngit push"), ("Bash", "cd %s\rgit push"),
    ("PowerShell", "Set-Location %s;git push"), ("PowerShell", "Set-Location %s\ngit push"),
)


def worktree_home_quoted_move_case():
    """Rule 0: a lone move into the recorded home is refused when its raw command holds a `;`, `&`,
    `|`, CR or LF, quote or no quote, from a cwd outside the home, in both path forms."""
    agent_id = "wthomequote1"
    primary, worktree, problems = _home_fixture(agent_id)
    for shell, template in QUOTED_MOVES + PLAIN_MOVES:
        for home in (worktree, _posix_form(worktree)):
            _expect_call(problems, "%s %r into %s from outside" % (shell, template, home), "deny",
                         shell, primary, agent_id, template % home, rule="worktree-home")
    if problems:
        return False, "; ".join(problems)
    return True, "a move whose raw command holds a separator is refused, quoted or not"


# Bash has no `sl`, `chdir` or `set-location`: those are PowerShell names. In Bash the call moves
# nothing, so it is no recovery step, and a call to one from outside the home is refused.
BASH_NOT_MOVES = ("sl", "chdir", "set-location")


def worktree_home_bash_alias_case():
    """Rule 0: `sl`, `chdir` and `set-location` are not moves in Bash, so a Bash call to one with the
    recorded home as its argument is refused from a cwd outside the home, in both path forms."""
    agent_id = "wthomealias1"
    primary, worktree, problems = _home_fixture(agent_id)
    for word in BASH_NOT_MOVES:
        for home in (worktree, _posix_form(worktree)):
            _expect_call(problems, "Bash %s into %s from outside" % (word, home), "deny", "Bash",
                         primary, agent_id, "%s %s" % (word, home), rule="worktree-home")
    if problems:
        return False, "; ".join(problems)
    return True, "sl, chdir and set-location are refused from outside the home in Bash"


# Rule 0 reads a Git Bash `/c/` cwd in drive form before every other rule runs (guard.py judge()).
# Each case below pins the verdict a `/c/` cwd gets for one rule that reads cwd. Off Windows, `/c/` is a
# real folder and the spelling has no meaning, so the cases do not run there.
C_FORM_OFF_WINDOWS = "a /c/ cwd is read only on Windows, where Git Bash spells the drive that way"


def _c_form_fixture(name):
    """A clean checkout under ROOT, with one source file and one test file. Returns its path."""
    primary = os.path.join(ROOT, "cform_" + name)
    make_repo(primary, {"src/app.py": "print(1)\n", "tests/test_app.py": "x\n"})
    return primary


def _c_form_decide(tool, cwd, agent_type=None, agent_id=None, command=None, **tool_input):
    """decide() for one call whose cwd is the `/c/` spelling. An agent names both agent fields."""
    if command is not None:
        tool_input["command"] = command
    return decide({"raw": None, "tool": tool, "cwd": cwd, "session": None, "env_path": None,
                   "config": None, "agent_id": agent_id, "agent_type": agent_type,
                   "process_cwd": None, "tool_input": tool_input})


def worktree_home_cwd_merge_case():
    """Pins the merge rule (judge(), merge_check) for a `/c/` cwd: main denies a merge whose head it
    cannot settle, and the merge rule must still deny it from that spelling."""
    if os.name != "nt":
        return SKIP, C_FORM_OFF_WINDOWS
    primary = _c_form_fixture("merge")
    got, reason = _c_form_decide("mcp__github__merge_pull_request", _posix_form(primary),
                                 pullNumber=1)
    if got != "deny" or "merge-checks" not in reason:
        return False, "/c/ cwd, merge: expected deny merge-checks (main), got %s (%s)" % (
            got, reason[:120])
    return True, "a /c/ cwd gives the merge rule the verdict main gives: deny merge-checks"


def worktree_home_cwd_shared_tree_case():
    """Pins the shared-tree rule (judge_shell) for a `/c/` cwd: on main a hard reset from that
    spelling is denied, because the checkout's state cannot be read from it. A clean checkout read
    in drive form allows the reset, so a red here means the lane changed that verdict."""
    if os.name != "nt":
        return SKIP, C_FORM_OFF_WINDOWS
    primary = _c_form_fixture("shared")
    got, reason = _c_form_decide("Bash", _posix_form(primary), command="git reset --hard")
    if got != "deny" or "shared-tree" not in reason:
        return False, "/c/ cwd, clean checkout, git reset --hard: expected deny shared-tree (main), " \
                      "got %s (%s)" % (got, reason[:120])
    return True, "a /c/ cwd gives the shared-tree rule the verdict main gives: deny shared-tree"


def worktree_home_cwd_builder_case():
    """Pins the builder test-edit rule (role_write_hit) for a `/c/` cwd: a builder's write to a test
    file is denied, and a write to product code is allowed."""
    if os.name != "nt":
        return SKIP, C_FORM_OFF_WINDOWS
    primary = _c_form_fixture("builder")
    cwd = _posix_form(primary)
    problems = []
    got, reason = _c_form_decide("Write", cwd, agent_type="builder", agent_id="wthomecwd1",
                                 file_path="tests/test_app.py", content="x")
    if got != "deny" or "builder-test-edit" not in reason:
        problems.append("builder write to a test file: expected deny builder-test-edit, got %s (%s)"
                        % (got, reason[:120]))
    got, reason = _c_form_decide("Write", cwd, agent_type="builder", agent_id="wthomecwd1",
                                 file_path="src/app.py", content="x")
    if got != "allow":
        problems.append("builder write to product code: expected allow, got %s (%s)"
                        % (got, reason[:120]))
    if problems:
        return False, "; ".join(problems)
    return True, "a /c/ cwd gives the builder test-edit rule the verdict main gives"


def worktree_home_cwd_frozen_case():
    """Pins the frozen-path rule (is_frozen) for a `/c/` cwd. Main allows a relative write to the
    global CLAUDE.md from that spelling, because the relative path does not resolve there. A red
    here means the lane changed that verdict: it denies the same write from the drive form."""
    if os.name != "nt":
        return SKIP, C_FORM_OFF_WINDOWS
    os.makedirs(CFG, exist_ok=True)
    got, reason = _c_form_decide("Write", _posix_form(CFG), file_path="CLAUDE.md", content="x")
    if got != "allow":
        return False, "/c/ cwd, relative CLAUDE.md write: expected allow (main), got %s (%s)" % (
            got, reason[:120])
    return True, "a /c/ cwd gives the frozen-path rule the verdict main gives: allow"


def worktree_home_cwd_config_case():
    """Pins the config-edit rule (is_project_config) for a `/c/` cwd: a project's own settings write
    is allowed, and it is only logged. The verdict must not change with the spelling."""
    if os.name != "nt":
        return SKIP, C_FORM_OFF_WINDOWS
    primary = _c_form_fixture("config")
    got, reason = _c_form_decide("Write", _posix_form(primary),
                                 file_path=".claude/settings.local.json", content="{}")
    if got != "allow":
        return False, "/c/ cwd, project settings write: expected allow, got %s (%s)" % (
            got, reason[:120])
    return True, "a /c/ cwd gives the config-edit rule the verdict main gives: allow"


def worktree_home_cwd_cap_case():
    """Pins the agent cap rule (is_settings_file) for a `/c/` cwd: a settings write that sets the
    cap asks. The basename decides this one, so the case pins the verdict, not the cwd read."""
    if os.name != "nt":
        return SKIP, C_FORM_OFF_WINDOWS
    primary = _c_form_fixture("cap")
    got, reason = _c_form_decide("Write", _posix_form(primary), file_path="settings.json",
                                 content=CAP_LINE)
    if got != "ask" or "agent-model-cap" not in reason:
        return False, "/c/ cwd, settings write with the cap: expected ask agent-model-cap, " \
                      "got %s (%s)" % (got, reason[:120])
    return True, "a /c/ cwd gives the agent cap rule the verdict main gives: ask"


# The builder cases below run off Windows. They read a `/c/` cwd through the loaded guard's own
# `_expanded`, with only the drive map changed: `/c/` reads under the run folder, and a relative
# target is joined onto the cwd as given, so a `/c/` cwd stays raw in that join, as on Windows.
# os.name reads as Windows for the one call. On Windows the real drive reader runs in the case
# above.
C_FORM_ON_WINDOWS = "on Windows the real drive reader runs, in the builder case above"


def _slash_c_expanded(real, root):
    """The guard's `_expanded`, with a `/c/` path read under `root`. Every other path, and the join
    of a relative path onto its cwd, goes to the real reader as given."""
    def expanded(path, cwd):
        bare = path.strip("'\"")
        if bare.startswith("/c/"):
            bare = os.path.join(root, bare[3:])
        return real(bare, cwd)
    return expanded


def _slash_c_builder_hit(name, target):
    """role_write_hit for a builder write to `target`, from a `/c/` cwd in the repository that
    `_c_form_fixture(name)` builds. Returns the hit: non-empty when the write is refused."""
    primary = _c_form_fixture(name)
    cwd = "/c/" + os.path.basename(primary)
    guard = _load_guard_module()
    real_expanded, real_name = guard._expanded, os.name
    guard._expanded = _slash_c_expanded(real_expanded, ROOT)
    os.name = "nt"
    try:
        return guard.role_write_hit("builder", {"content": "x"}, target, cwd, "")
    finally:
        os.name = real_name
        guard._expanded = real_expanded


def worktree_home_cwd_builder_refuse_case():
    """A builder's write to a test file, from a `/c/` cwd in a repository, is refused. The probe and
    the target both read the cwd in drive form. Read raw, the target counts as outside every
    checkout and the write is allowed (decision builders-cannot-edit-tests)."""
    if os.name == "nt":
        return SKIP, C_FORM_ON_WINDOWS
    if not _slash_c_builder_hit("builder-deny", "tests/test_app.py"):
        return False, "/c/ cwd in a repository, builder write to tests/test_app.py: " \
                      "expected refuse, got allow"
    return True, "a builder write to a test file from a /c/ cwd in a repository is refused"


def worktree_home_cwd_builder_src_case():
    """A builder's write to product code, from the same `/c/` cwd, is allowed. The drive read must
    not widen the test rule to product paths (decision builders-cannot-edit-tests)."""
    if os.name == "nt":
        return SKIP, C_FORM_ON_WINDOWS
    if _slash_c_builder_hit("builder-src", "src/app.py"):
        return False, "/c/ cwd in a repository, builder write to src/app.py: " \
                      "expected allow, got deny"
    return True, "a builder write to product code from a /c/ cwd in a repository is allowed"


def worktree_home_cwd_builder_scratch_case():
    """A builder's write to a path in no repository, from a `/c/` cwd in one, is allowed. The target
    is outside every checkout, so no test rule reaches it (decision builders-cannot-edit-tests)."""
    if os.name == "nt":
        return SKIP, C_FORM_ON_WINDOWS
    if _slash_c_builder_hit("builder-scratch", "/c/scratch-out/probe.py"):
        return False, "/c/ cwd in a repository, builder write to /c/scratch-out/probe.py: " \
                      "expected allow, got deny"
    return True, "a builder write to a path in no repository from a /c/ cwd is allowed"


# Each builds its own repository and calls no lazy fixture, so a filtered run skips that build.
FIXTURELESS_CHECKS.update((
    worktree_home_cwd_builder_refuse_case, worktree_home_cwd_builder_src_case,
    worktree_home_cwd_builder_scratch_case))


# ------------------------------------------------------------------ other-checkout: a separate clone
#
# The separate-clone act. A path in another clone of this repo is another checkout too, though no
# `git worktree add` made it. The clone is found by a stat walk up from the path, never by a guess at
# its name, and its origin is read from its config file, so the act spawns no git. Two clones are the
# same repo when their origins name the same owner and repo, in any URL form. A clone with no origin, or
# an unreadable config, is unknown and passes. A folder in the temp folder, a different repo, a nested
# repo inside the own checkout and a plain folder with no `.git` all pass. With CLAUDE_PROJECT_DIR naming
# the home clone, a cwd stranded in a separate clone refuses its writes. Decision:
# docs/decisions/an-agent-outside-its-home-tree-must-stop.md (other-checkout).
#
# Each row is its own case, so a failure names one cause. A refusal row is red on a guard that lets the
# act through.

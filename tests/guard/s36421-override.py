# section 36421
FAMILY = "override"
#
# The owner types `override` as a whole prompt, and the guard lets the next refused act through (a
# one-act override). `override 15m` or `override 3h` lets every refused act through until the override ends
# (a timed override, no cap, the owner picks the length). hooks/local_time.py grants the override with
# override.grant(session_id, prompt, now). refuse() in guard_core.py spends it with
# override.take(session_id, agent_id, rule, now). The override file is
# <config dir>/state/override/<session_id>.json, {"kind": "once" or "timed", "until": ISO-8601}.
#
# What an override does: it covers only the session that typed it. An agent's call spends only a timed
# override. A valid override makes the guard print nothing, so the normal permission flow runs, and it logs
# one line with decision `override` and the rule it lifted. What no override does: lift frozen-path,
# git-env-set, or a kill of pid 0, 1 or -1, or count an unreadable override file as an override.
#
# A one-act override is state that a call uses up, so each case is a story over several guard calls on
# one fixed clock (LOCAL_TIME_NOW). A single-call `sh` case cannot show "allowed once, then refused
# again", so each story runs as a log check. Every story first makes the call with no override and wants
# the refusal, so a fixture that refuses nothing cannot turn a story green.

OV_T0 = datetime(2026, 10, 18, 18, 0, tzinfo=timezone.utc)  # the clock when an override is typed
OV_ONCE_SECONDS = 10 * 60   # a one-act override that nothing uses ends after this long
OV_TIMED_SECONDS = 15 * 60  # the length of the timed override these stories type: `override 15m`
OV_AGENT = "a0f1e2d3c4b5a6978"  # an agent's id on the payload, in the shape AGENT_ID accepts
OV_KILL = "kill $(pgrep -f override-target)"  # refused with no `ps` read, so it runs on Windows too


def ov_clock(seconds):
    """LOCAL_TIME_NOW for a call made `seconds` after OV_T0."""
    return (OV_T0 + timedelta(seconds=seconds)).isoformat()


def ov_config(name):
    """A config directory of its own, so one story's overrides and log never reach another's."""
    folder = os.path.join(ROOT, "ovcfg", name)
    os.makedirs(folder, exist_ok=True)
    return folder


def ov_pass_path(config, session):
    return os.path.join(config, "state", "override", session + ".json")


# Exit 3 means the module cannot be imported. Any other failure is the module's own.
OV_GRANT_CHILD = (
    "import sys\n"
    "from datetime import datetime\n"
    "sys.path.insert(0, sys.argv[1])\n"
    "try:\n"
    "    import override\n"
    "except ImportError as e:\n"
    "    print('import failed: %s' % e, file=sys.stderr)\n"
    "    sys.exit(3)\n"
    "override.grant(sys.argv[2], sys.argv[3], datetime.fromisoformat(sys.argv[4]))\n"
)


def ov_write_pass(config, session, prompt, seconds):
    """The override file as the design documents it, for a story that runs while override.py does
    not import. The story then still reaches the guard and fails there, for the right reason."""
    path = ov_pass_path(config, session)
    said = prompt.strip().lower()
    if said == "override off":
        if os.path.exists(path):
            os.remove(path)
        return
    named = re.fullmatch(r"override (\d+)([mh]?)", said)
    if named:
        kind, length = "timed", int(named.group(1)) * (3600 if named.group(2) == "h" else 60)
    else:
        kind, length = "once", OV_ONCE_SECONDS
    write(path, json.dumps({"kind": kind, "until": ov_clock(seconds + length)}))


def ov_type(config, session, prompt, seconds=0):
    """The owner types `prompt` at OV_T0 + seconds: override.grant runs in a child that reads
    `config` as its config directory. Returns '' when the module ran, else a note for the story's
    failure line: the import failed (the override was written by hand), or the module raised."""
    env = dict(os.environ)
    env["CLAUDE_CONFIG_DIR"] = config
    env["LOCAL_TIME_NOW"] = ov_clock(seconds)
    run = subprocess.run(
        [sys.executable, "-c", OV_GRANT_CHILD, os.path.dirname(GUARD), session, prompt,
         ov_clock(seconds)], capture_output=True, text=True, env=env, timeout=60)
    if run.returncode == 0:
        return ""
    if run.returncode == 3:
        ov_write_pass(config, session, prompt, seconds)
        return "override.py does not import (%s); the override was written by hand" % (
            run.stderr.strip()[-90:])
    return "override.grant raised: %s" % run.stderr.strip()[-120:]


def ov_call(tool, tool_input, cwd, config, session, seconds, agent_id=None, agent_type=None,
            temp=None, env=None, load=None, env_path=None, transcript=None):
    """One guard call at OV_T0 + seconds. Returns (decision, reason). `temp` is the folder the guard
    reads as the system temp: a git write under it is a throwaway, and silent-write skips it. `env`
    adds variables to this one guard run. `load` is the machine reading a start call meets
    (LB_NORMAL when None). `env_path` is the PATH of this one guard run (None keeps the runner's).
    `transcript` is the payload's transcript_path (None sends none), for a rule that reads the session's record."""
    fixed = {"LOCAL_TIME_NOW": ov_clock(seconds)}
    fixed.update(env or {})
    return decide({
        "raw": None, "tool": tool, "cwd": cwd, "session": session, "env_path": env_path,
        "config": config, "agent_id": agent_id, "agent_type": agent_type, "temp": temp,
        "env": fixed, "tool_input": tool_input, "load": load, "transcript": transcript,
    })


def ov_kill(config, session, seconds, agent_id=None):
    """The `kill $(pgrep ...)` call: refused by machine-wide-kill with no override, in any directory."""
    return ov_call("Bash", {"command": OV_KILL}, NOGIT, config, session, seconds, agent_id)


def ov_want(got, reason, want, rule):
    """'' when (got, reason) is the verdict wanted. An allow must print nothing. A refusal must name
    its rule; a tuple of rules lists the ones that may name it. Else why not."""
    if got != want:
        return "got %s (%s), want %s" % (got, reason[:70], want)
    if want == "allow" and reason:
        return "the allow printed %r, want nothing" % reason[:70]
    names = (rule,) if isinstance(rule, str) else rule
    if want != "allow" and not any(name in reason for name in names):
        return "the refusal does not name rule %r: %s" % (rule, reason[:70])
    return ""


def ov_story(steps, note=""):
    """Run (label, call, want, rule) steps in order. Returns (False, why) at the first miss, else
    (True, ''). The note says how the override was typed, so a failure line shows a hand-written override."""
    for label, call, want, rule in steps:
        problem = ov_want(*call(), want, rule)
        if problem:
            return False, "%s: %s%s" % (label, problem, ("; " + note) if note else "")
    return True, ""


# The refusals the owner named; each one is refused when no override exists. (key, what it is, command,
# cwd, decision, rule, a config directory whose sessions/ folder the story copies in.) The
# live-session act needs the session record that names this runner's own pid.
OV_ACTS = (
    ("branch-unpushed", "a branch delete of a branch whose only copy is local",
     VCS + " branch -D unmerged-work", BRANCHREPO, "deny", "shared-tree", None),
    ("worktree-live", "a worktree remove under a live session",
     VCS + " worktree remove " + slash(WTLIVE), WTMAIN, "deny", "shared-tree", WTLIVECFG),
    ("worktree-work", "a worktree remove of a tree with uncommitted and untracked work",
     VCS + " worktree remove " + slash(WTDIRTY), WTMAIN, "deny", "shared-tree", None),
    ("worktree-locked", "a worktree remove of a locked tree",
     VCS + " worktree remove " + slash(WTLOCKED), WTMAIN, "deny", "shared-tree", None),
    ("checkout-path", "a checkout of a path over uncommitted work",
     VCS + " checkout -- f.txt", SUBJDIRTY, "deny", "shared-tree", None),
    ("stash-help", "a stash call that reads as a push",
     VCS + " stash --help -h", SUBJDIRTY, "deny", "shared-tree", None),
    ("kill-pgrep", "a kill of a pid list that pgrep made",
     OV_KILL, NOGIT, "deny", "machine-wide-kill", None),
    ("kill-foreign", "a kill of a pid this session did not start",
     "kill %d" % FOREIGN, NOGIT, "deny", "machine-wide-kill", None),
    ("ask-linked-discard", "a hard reset in a linked worktree, which asks",
     VCS + " reset --hard", GITWT, "ask", "shared-tree", None),
    # The asks of rulings 206 a and 207 a are lifted by an owner override like any ask. The refusal of rule
    # push-agent-branch is lifted the same way, as any refusal is.
    ("push-stray", "a non-forced push that lands on a stray branch",
     VCS + " push origin HEAD", PUSHSTRAY, "ask", PUSH_STRAY_RULE, None),
    ("push-main", "a non-forced push of main",
     VCS + " push origin main", PUSHMAIN, "ask", PUSH_MAIN_RULE, None),
    ("push-agent", "a non-forced push of an agent-worktree branch name",
     VCS + " push origin HEAD", PUSHAGENT, "deny", PUSH_AGENT_RULE, None),
    # The owner's refused wait for a clock time, from the main session (no agent id, so a once override reaches it).
    ("wait-until-clock-loop", "a foreground loop that waits for a clock time",
     WAIT_UNTIL_CLOCK_LOOP, NOGIT, "deny", "waiter", None),
)


def ov_act_check(act, timed):
    """A one-act override lets the act through once, then it is refused again. A timed override lets it through
    every time until the override ends, and the call at the end instant is refused."""
    key, _, command, cwd, refused, rule, sessions_from = act
    kind = "timed" if timed else "once"

    def check():
        config, session = ov_config("%s-%s" % (kind, key)), "ov-%s-%s" % (kind, key)
        if sessions_from:
            materialize(sessions_from)
            shutil.copytree(os.path.join(sessions_from, "sessions"),
                            os.path.join(config, "sessions"), dirs_exist_ok=True)

        def call(seconds):
            return lambda: ov_call("Bash", {"command": command}, cwd, config, session, seconds)

        ok, why = ov_story([("with no override", call(0), refused, rule)])
        if not ok:
            return False, why
        note = ov_type(config, session, "override 15m" if timed else "override")
        if timed:
            steps = [("first call", call(60), "allow", rule),
                     ("call just before the end", call(OV_TIMED_SECONDS - 1), "allow", rule),
                     ("call at the end instant", call(OV_TIMED_SECONDS), refused, rule)]
        else:
            steps = [("first call", call(60), "allow", rule),
                     ("second call, override spent", call(120), refused, rule)]
        ok, why = ov_story(steps, note)
        if not ok:
            return False, why
        return True, "%s with no override, then allowed %s" % (refused, "until the end" if timed else "once")
    return check


for _act in OV_ACTS:
    for _is_timed in (False, True):
        _label = ("override: a timed override lets through %s until it ends" if _is_timed
                  else "override: a one-act override lets through %s once, then it is refused again") % _act[1]
        if _act[0] == "kill-foreign" and os.name == "nt":
            skip_case(_label, NO_PS)
        else:
            LOG_CHECKS_EXTRA.append((_label, ov_act_check(_act, _is_timed)))


# A refusal ends with the line an owner types to lift it (step c80 of decision owner-override), or
# says that no override lifts it. The line is read through hooks/override.py, its one home, so these
# checks pin that the refusal carries it, not its exact wording. The typed words are pinned too.
try:
    import override as _override_home
except ImportError:
    _override_home = None
OV_NO_OVERRIDE_PHRASE = "no override"  # stable words of the vetoed sentence, for a path that cannot import override


def ov_home(name):
    """override.<name>, or None while the name is missing (the check then fails on its own line)."""
    return getattr(_override_home, name, None)


def ov_offer_check(kind):
    """A liftable refusal ends with the override line: the main session names `override` and `override 15m`,
    an agent's call names `override 15m`, and the Opus spawn refusal names `opus 2h`."""
    def check():
        config, session = ov_config("offer-" + kind), "ov-offer-" + kind
        if kind == "opus":
            got, reason = ov_call("Agent", dict(OV_OPUS_SPAWN), NOGIT, config, session, 0)
            want, rule, words = "deny", "agent-model-cap", ("opus 2h",)
            expected = ov_home("offer")
            expected = expected(rule, spawn_role="general-purpose") if expected else None
        else:
            agent = OV_AGENT if kind == "agent" else None
            got, reason = ov_kill(config, session, 0, agent)
            want, rule, words = "deny", "machine-wide-kill", ("override 15m",)
            expected = ov_home("offer")
            expected = expected(rule, agent_id=agent) if expected else None
        if got != want:
            return False, "got %s (%s), want %s" % (got, reason[:70], want)
        for word in words:
            if word not in reason:
                return False, "the refusal does not name %r: %s" % (word, reason[-120:])
        if kind == "main" and reason.count("override") < 2:
            return False, "the main session's refusal names one override word, want `override` and `override 15m`"
        if not expected:
            return False, "override.offer is missing, so the line cannot be read from its home"
        if not reason.rstrip().endswith(expected.strip()):
            return False, "the override line is not last: %s" % reason[-120:]
        return True, "the refusal ends with the %s override line" % kind
    return check


def ov_vetoed_check(label, call):
    """A refusal no override lifts ends with override.NO_OVERRIDE and offers no typed word."""
    def check():
        config, session = ov_config("veto-" + label), "ov-veto-" + label
        got, reason = call(config, session)
        if got != "deny":
            return False, "got %s (%s), want deny" % (got, reason[:70])
        constant = ov_home("NO_OVERRIDE")
        if not constant:
            return False, "override.NO_OVERRIDE is missing"
        if constant.strip() not in reason:
            return False, "the refusal lacks the no-override line: %s" % reason[-120:]
        if "override 15m" in reason:
            return False, "the refusal offers an override that cannot lift it: %s" % reason[-120:]
        return True, "the refusal says that no override lifts it"
    return check


for _kind in ("main", "agent", "opus"):
    LOG_CHECKS_EXTRA.append(("override: a refusal an override lifts ends with the %s override line" % _kind,
                             ov_offer_check(_kind)))
LOG_CHECKS_EXTRA.append((
    "override: a kill of pid 1 ends with the no-override line",
    ov_vetoed_check("kill-init", lambda config, session: ov_call(
        "Bash", {"command": "kill 1"}, NOGIT, config, session, 0))))
LOG_CHECKS_EXTRA.append((
    "override: a write of the config settings ends with the no-override line",
    ov_vetoed_check("frozen", lambda config, session: ov_call(
        "Write", {"file_path": slash(os.path.join(config, "settings.json")), "content": "{}"}, NOGIT,
        config, session, 0))))


def ov_fail_closed_says_no_override():
    """The deny for a missing sibling module cannot check the acts no override lifts, so no override lifts
    it. That path imports no other module, so the sentence sits inline in guard.py."""
    drop = "guard_kill"
    run = _run_copy(_guard_copy("no-override-" + drop, drop + ".py"), FAILCLOSED_CALL, "no-override-" + drop)
    decision, reason = _decision(run)
    if decision != "deny":
        return False, "the call is %r with %s missing, want deny" % (decision, drop)
    if OV_NO_OVERRIDE_PHRASE not in reason.lower():
        return False, "the reason does not say that no override lifts it: %r" % reason[-120:]
    return True, "the missing-module deny says that no override lifts it"


LOG_CHECKS_EXTRA.append(("override: a missing-module deny says that no override lifts it",
                         ov_fail_closed_says_no_override))


# pkill and killall are refused by guard_kill through refuse(), which an override lifts. The settings.json
# deny entries for them are checked before the hook runs, so no override reached them.
OV_ACTS_BY_NAME = (
    ("pkill-name", "a pkill by name", "pkill node", NOGIT, "deny", "machine-wide-kill", None),
    ("killall-name", "a killall by name", "killall node", NOGIT, "deny", "machine-wide-kill", None),
)
for _act in OV_ACTS_BY_NAME:
    LOG_CHECKS_EXTRA.append(("override: a one-act override lets through %s once, then it is refused again" % _act[1],
                             ov_act_check(_act, False)))


def settings_denies_no_name_kill():
    """settings.json holds no deny entry for pkill or killall: such an entry refuses before the hook
    runs, so an owner override cannot lift it."""
    with open(os.path.join(REPO, "settings.json"), encoding="utf-8") as handle:
        deny = json.load(handle).get("permissions", {}).get("deny", [])
    held = [entry for entry in deny if re.match(r"Bash\((pkill|killall)\b", entry)]
    if held:
        return False, "the deny list still holds %s" % held
    return True, "no deny entry for pkill or killall"


LOG_CHECKS_EXTRA.append(("override: settings.json denies neither pkill nor killall", settings_denies_no_name_kill))


# The refusal of an Opus spawn above its row is liftable (an override lifts it like any other refusal of
# agent-model-cap), while the same rule's ask on a settings write stays outside every override (ov_role_acts
# and ov_cap_shell_acts below). Each story first wants the refusal with no override.
OV_OPUS_SPAWN = {"prompt": "Review the diff for typos.", "model": "opus",
                 "subagent_type": "general-purpose"}


def ov_opus_spawn_check(timed):
    """A one-act override lets an Opus spawn through once, then it is refused again. A timed override lets it through
    every time until the override ends, and the call at the end instant is refused."""
    kind = "timed" if timed else "once"
    rule = "agent-model-cap"

    def check():
        config, session = ov_config("opus-spawn-" + kind), "ov-opus-spawn-" + kind

        def call(seconds):
            return lambda: ov_call("Agent", dict(OV_OPUS_SPAWN), NOGIT, config, session, seconds)

        ok, why = ov_story([("with no override", call(0), "deny", rule)])
        if not ok:
            return False, why
        note = ov_type(config, session, "override 15m" if timed else "override")
        if timed:
            steps = [("first spawn", call(60), "allow", rule),
                     ("spawn just before the end", call(OV_TIMED_SECONDS - 1), "allow", rule),
                     ("spawn at the end instant", call(OV_TIMED_SECONDS), "deny", rule)]
        else:
            steps = [("first spawn", call(60), "allow", rule),
                     ("second spawn, override spent", call(120), "deny", rule)]
        ok, why = ov_story(steps, note)
        if not ok:
            return False, why
        return True, "an Opus spawn was refused with no override, then went through %s" % (
            "until the end" if timed else "once")
    return check


for _is_timed in (False, True):
    LOG_CHECKS_EXTRA.append(
        ("override: a timed override lets an Opus spawn through until it ends" if _is_timed
         else "override: a one-act override lets an Opus spawn through once, then it is refused again",
         ov_opus_spawn_check(_is_timed)))


# THE OPUS OVERRIDE (decision owner-override). `opus <n>[m|h]` lifts only the Opus spawn ask of
# agent-model-cap, for the typing session and its agents, until it ends. `opus <role> <n>[m|h]`
# lifts it only for spawns of that role. Every other refusal and ask stands.
OP_SECONDS = 2 * 3600  # the length of the override these stories type: `opus 2h`
OP_BUILDER = {"prompt": "Round 1 of 3. Start the fix.", "model": "opus", "subagent_type": "builder"}
OP_REVIEWER = {"prompt": "Round 3 of 3. Re-check the diff.", "model": "claude-opus-5-5",
               "subagent_type": "reviewer"}


def op_pass_path(config, session):
    return os.path.join(config, "state", "override", "opus", session + ".json")


def op_spawn(config, session, seconds, spawn=None, agent_id=None, cwd=NOGIT, env=None):
    return ov_call("Agent", dict(spawn or OV_OPUS_SPAWN), cwd, config, session, seconds, agent_id,
                   env=env)


def op_timed_check():
    """`opus 2h`: an Opus spawn is refused with no override, then goes through for the session and its agents
    until the override ends, and is refused again at the end instant."""
    config, session, rule = ov_config("opus-timed"), "op-timed", "agent-model-cap"
    ok, why = ov_story([("with no override", lambda: op_spawn(config, session, 0), "deny", rule)])
    if not ok:
        return False, why
    note = ov_type(config, session, "opus 2h")
    ok, why = ov_story([
        ("first spawn", lambda: op_spawn(config, session, 60), "allow", rule),
        ("an agent's spawn", lambda: op_spawn(config, session, 120, agent_id=OV_AGENT), "allow", rule),
        ("second spawn", lambda: op_spawn(config, session, 180), "allow", rule),
        ("spawn just before the end", lambda: op_spawn(config, session, OP_SECONDS - 1), "allow", rule),
        ("spawn at the end instant", lambda: op_spawn(config, session, OP_SECONDS), "deny", rule),
    ], note)
    if not ok:
        return False, why
    return True, "refused with no override, went through for the session and an agent until the end"


def op_minutes_check():
    """`opus 15m` is fifteen minutes, and `opus off` ends the override at once."""
    config, session, rule = ov_config("opus-minutes"), "op-minutes", "agent-model-cap"
    note = ov_type(config, session, "opus 15m")
    ok, why = ov_story([
        ("spawn just before the end", lambda: op_spawn(config, session, OV_TIMED_SECONDS - 1), "allow", rule),
        ("spawn at the end instant", lambda: op_spawn(config, session, OV_TIMED_SECONDS), "deny", rule),
    ], note)
    if not ok:
        return False, why
    note = ov_type(config, session, "OPUS 2H", OV_TIMED_SECONDS + 60) or note
    ok, why = ov_story([("after `OPUS 2H`", lambda: op_spawn(config, session, OV_TIMED_SECONDS + 90),
                         "allow", rule)], note)
    if not ok:
        return False, why
    note = ov_type(config, session, "opus off", OV_TIMED_SECONDS + 120) or note
    ok, why = ov_story([("after `opus off`", lambda: op_spawn(config, session, OV_TIMED_SECONDS + 150),
                         "deny", rule)], note)
    if not ok:
        return False, why
    return True, "15 minutes to the second, any case, and `opus off` ended it"


def op_role_check():
    """`opus builders 2h` lifts only builder spawns. A spawn of any other role is still refused."""
    config, session, rule = ov_config("opus-role"), "op-role", "agent-model-cap"
    ok, why = ov_story([("a builder with no override", lambda: op_spawn(config, session, 0, OP_BUILDER),
                         "deny", rule)])
    if not ok:
        return False, why
    note = ov_type(config, session, "opus builders 2h")
    ok, why = ov_story([
        ("a builder", lambda: op_spawn(config, session, 60, OP_BUILDER), "allow", rule),
        ("an agent's builder", lambda: op_spawn(config, session, 90, OP_BUILDER, OV_AGENT), "allow", rule),
        ("a general-purpose spawn", lambda: op_spawn(config, session, 120), "deny", rule),
        ("a reviewer", lambda: op_spawn(config, session, 150, OP_REVIEWER), "deny", rule),
        ("a spawn with no role", lambda: op_spawn(config, session, 180, {"prompt": "x", "model": "opus"}),
         "deny", rule),
    ], note)
    if not ok:
        return False, why
    note = ov_type(config, session, "opus reviewer 2h", 240) or note
    ok, why = ov_story([
        ("a reviewer after `opus reviewer 2h`", lambda: op_spawn(config, session, 270, OP_REVIEWER),
         "allow", rule),
        ("a builder after the new override replaced the old", lambda: op_spawn(config, session, 300, OP_BUILDER),
         "deny", rule),
    ], note)
    if not ok:
        return False, why
    return True, "the role override lifted only its own role, plural or singular"


# Each prompt is ambiguous or not the word, so it grants nothing: the spawn is still refused.
OP_NOT_THE_WORD = (
    "opus 2",                 # a bare number may name a model, so the unit is required
    "opus 4.5",
    "opus 2h please",
    "opus builders",
    "opus bogus 2h",
    "opus builders reviewers 2h",
    "opus off 2h",
    "opus plan 2h",           # Plan already runs Opus by standing grant
    "use opus 2h",
    "opus2h",
    "opuses 2h",
    "hi\nopus 2h",
    "opus 2h\nand the rest",
)


def op_not_the_word_check():
    config, rule = ov_config("opus-not-word"), "agent-model-cap"
    for n, prompt in enumerate(OP_NOT_THE_WORD):
        session = "op-not-word-%d" % n
        note = ov_type(config, session, prompt)
        problem = ov_want(*op_spawn(config, session, 60), "deny", rule)
        if problem:
            return False, "after %r: %s; %s" % (prompt, problem, note or "typed")
        if os.path.exists(op_pass_path(config, session)):
            return False, "%r wrote an Opus override file" % prompt
    return True, "%d prompts granted nothing" % len(OP_NOT_THE_WORD)


def op_scope_check():
    """An Opus override covers only the session that typed it."""
    config, rule = ov_config("opus-scope"), "agent-model-cap"
    note = ov_type(config, "op-scope-a", "opus 2h")
    ok, why = ov_story([
        ("another session", lambda: op_spawn(config, "op-scope-b", 60), "deny", rule),
        ("no session id", lambda: op_spawn(config, None, 90), "deny", rule),
        ("the typing session", lambda: op_spawn(config, "op-scope-a", 120), "allow", rule),
    ], note)
    if not ok:
        return False, why
    return True, "another session and an unnamed one were refused, the typing session went through"


def op_other_acts(config, session):
    """Refusals an Opus override never lifts: every rule but the Opus spawn ask, the settings-write ask of
    the same rule included."""
    lifted_by_override = tuple(OvAct(label, "Bash", {"command": command}, rule, want, cwd=cwd)
                               for label, command, cwd, want, rule in (
        ("a kill of a pgrep list", OV_KILL, NOGIT, "deny", "machine-wide-kill"),
        ("a branch delete of a branch whose only copy is local", VCS + " branch -D unmerged-work",
         BRANCHREPO, "deny", "shared-tree"),
        ("a hard reset in a linked worktree", VCS + " reset --hard", GITWT, "ask", "shared-tree"),
    ))
    return lifted_by_override + ov_role_acts(config, session) + ov_frozen_acts(config, session) + (
        ("a Write of the Opus override file", "Write",
         {"file_path": slash(op_pass_path(config, session)), "content": "{}"}, "frozen-path"),
        ("a cp onto the Opus override file", "Bash",
         {"command": "cp /tmp/x.json " + slash(op_pass_path(config, session))}, "frozen-path"),
    )


def op_lifts_nothing_else_check():
    """Under `opus 2h` every other refusal and ask stands, and a typed `override` is not spent by an
    Opus spawn the Opus override already lifts."""
    config, session = ov_config("opus-only"), "op-only"
    acts = [OvAct(*act) for act in op_other_acts(config, session)]
    for act in acts:
        problem = ov_want(*ov_act_call(act, config, session, 0), act.want, act.first or act.rule)
        if problem:
            return False, "%s with no override: %s" % (act.label, problem)
    note = ov_type(config, session, "opus 2h")
    for act in acts:
        problem = ov_want(*ov_act_call(act, config, session, 60), act.want, act.rule)
        if problem:
            return False, "%s under an Opus override: %s; %s" % (act.label, problem, note or "typed")
    note = ov_type(config, session, "override", 120) or note
    ok, why = ov_story([
        ("an Opus spawn beside a one-act override", lambda: op_spawn(config, session, 150), "allow",
         "agent-model-cap"),
        ("a kill, the one-act override still unspent", lambda: ov_kill(config, session, 180), "allow",
         "machine-wide-kill"),
        ("a second kill, the override spent", lambda: ov_kill(config, session, 210), "deny",
         "machine-wide-kill"),
        ("an Opus spawn, the Opus override still there", lambda: op_spawn(config, session, 240), "allow",
         "agent-model-cap"),
    ], note)
    if not ok:
        return False, why
    return True, "%d other refusals stood under an Opus override; it left a typed override unspent" % len(acts)


def op_corrupt_check():
    """An Opus override file the guard cannot read, or one of another shape, is no override."""
    config, rule = ov_config("opus-corrupt"), "agent-model-cap"
    later = ov_clock(OP_SECONDS)
    for name, body in (
            ("text", "not json {"), ("empty", ""), ("list", "[]"),
            ("no-until", '{"kind": "opus"}'),
            ("timed-kind", '{"kind": "timed", "until": "%s"}' % later),
            ("naive-until", '{"kind": "opus", "until": "2099-01-01T00:00:00"}'),
            ("number-role", '{"kind": "opus", "until": "%s", "role": 7}' % later)):
        session = "op-corrupt-" + name
        write(op_pass_path(config, session), body)
        problem = ov_want(*op_spawn(config, session, 60), "deny", rule)
        if problem:
            return False, "a %s Opus override file: %s" % (name, problem)
    return True, "seven unreadable or misshapen Opus override files, each refused"


def op_log_check():
    """The grant writes one log line naming the override, and each lifted spawn writes one line whose
    decision cell says `opus-override` and whose rule cell says agent-model-cap."""
    config, session = ov_config("opus-log"), "op-log-session"
    log = os.path.join(config, "guard.log")
    note = ov_type(config, session, "opus builders 2h")
    try:
        with open(log, encoding="utf-8") as handle:
            granted = [l for l in handle.read().splitlines() if l.strip()]
    except OSError:
        granted = []
    if len(granted) != 1 or "\topus-grant\tagent-model-cap\t" not in granted[0] or "builder" not in granted[0]:
        return False, "the grant wrote %r, want one opus-grant line naming builder; %s" % (granted, note or "typed")
    os.remove(log)
    problem = ov_want(*op_spawn(config, session, 60, OP_BUILDER), "allow", "agent-model-cap")
    if problem:
        return False, "the lifted spawn: %s; %s" % (problem, note or "typed")
    with open(log, encoding="utf-8") as handle:
        lines = [l for l in handle.read().splitlines() if l.strip()]
    fields = lines[0].split("\t") if len(lines) == 1 else []
    if len(fields) != 6 or fields[2:4] != ["opus-override", "agent-model-cap"] or fields[5] != session:
        return False, "the lift wrote %r, want one opus-override + agent-model-cap line" % lines
    os.remove(log)
    note = ov_type(config, session, "opus off", 90) or note
    with open(log, encoding="utf-8") as handle:
        ended = [l for l in handle.read().splitlines() if l.strip()]
    if len(ended) != 1 or "\topus-off\t" not in ended[0]:
        return False, "`opus off` wrote %r, want one opus-off line" % ended
    return True, "one line each for the grant, the lift and the end"


for _label, _check in (
    ("opus override: `opus 2h` lets an Opus spawn through, an agent's too, until it ends", op_timed_check),
    ("opus override: `opus 15m` lasts fifteen minutes and `opus off` ends it", op_minutes_check),
    ("opus override: `opus builders 2h` lifts only builder spawns", op_role_check),
    ("opus override: an ambiguous prompt grants nothing", op_not_the_word_check),
    ("opus override: it covers only the session that typed it", op_scope_check),
    ("opus override: every other refusal and ask stands under it", op_lifts_nothing_else_check),
    ("opus override: an unreadable or misshapen override file is no override", op_corrupt_check),
    ("opus override: the grant, each lift and the end each write one log line", op_log_check),
):
    LOG_CHECKS_EXTRA.append((_label, _check))


# THE STEP GRANT (lane opus-grant-on-step: the lift of rule agent-model-cap that reads the lane's roadmap
# step). An Opus spawn that no typed override lifts is read against the owner's grant on the lane's step:
# the step record on the local `origin/roadmap` ref, read from the call's cwd. Each case builds a real
# repository whose `origin/roadmap` ref holds the step records, so no case mocks the reader. The lane's
# id comes from the environment, not from the payload's session id, so the payload names another id.
GS_LANE = "a1b2c3"  # the lane: its step names it as session_<this>
GS_ENV = {"CLAUDE_CODE_REMOTE_SESSION_ID": "cse_" + GS_LANE}  # the environment names it as cse_<this>
GS_STEP = "step-a"  # the step bound to this lane
GS_AT = "2026-10-17T10:00:00-05:00"  # a grant time before the clock these cases run at
GS_SONNET = {"prompt": "Round 2 of 3. Review the diff.", "model": "sonnet", "subagent_type": "reviewer"}
GS_WIZARD = {"prompt": "Round 1 of 3. Start the fix.", "model": "claude-opus-5-5", "subagent_type": "wizard"}
GS_BAD = ("roadmap/data/steps/%s.json" % GS_STEP,  # a bound record cut short: it does not parse
          '{"id": "%s", "lane": "session_%s", "status": ' % (GS_STEP, GS_LANE))


def gs_step(step_id, lane, status="in_progress", grants=()):
    """One step record as the roadmap holds it: its path and its JSON text. `lane` is the bare lane id;
    the record names it session_<lane>, as the roadmap does."""
    body = {"id": step_id, "title": "Step " + step_id, "status": status, "lane": "session_" + lane,
            "grants": list(grants)}
    return "roadmap/data/steps/%s.json" % step_id, json.dumps(body, indent=2) + "\n"


def gs_grant(role="reviewer", drop_role=False):
    """A grant as triage writes it: role None covers every Opus spawn. drop_role leaves the key out."""
    grant = {"words": "opus 2h" if role is None else "opus %s 2h" % role, "at": GS_AT, "role": role,
             "by": "triage"}
    if drop_role:
        del grant["role"]
    return grant


def gs_repo(name, files, ref=True):
    """A checkout under this run's folder, holding `files` on main. With `ref`, its commit is also
    refs/remotes/origin/roadmap, the one ref the guard reads."""
    where = os.path.join(ROOT, "grant", name)
    make_repo(where, dict(files))
    if ref:
        made = run_vcs(where, "update-ref", "refs/remotes/origin/roadmap", "HEAD")
        if made.returncode != 0:
            sys.exit("fixture setup failed in gs_repo: update-ref in %r. stderr: %s"
                     % (where, made.stderr.strip()))
    return where


def gs_read(path):
    try:
        with open(path, encoding="utf-8", errors="replace") as handle:
            return handle.read()
    except OSError:
        return ""


def gs_log_lines(config):
    return [line for line in gs_read(os.path.join(config, "guard.log")).splitlines() if line.strip()]


def gs_spawn(config, session, repo, spawn, seconds=60, env=GS_ENV):
    """The lane's call: a spawn from inside `repo`, with the lane's environment."""
    return op_spawn(config, session, seconds, spawn, cwd=repo, env=env)


def gs_verdict_check(name, files, spawn, want, ref=True):
    """A check: the lane's spawn, judged in the repository `name` holds `files` gives `want`."""
    def check():
        repo = gs_repo(name, files, ref)
        config, session = ov_config("grant-" + name), "gs-payload-" + name
        problem = ov_want(*gs_spawn(config, session, repo, spawn), want, "agent-model-cap")
        return (not problem), (problem or "%s, as wanted" % want)
    return check


def gs_lift_check():
    """A reviewer spawn on the lane's step, which grants reviewers, is allowed. guard.log gets one
    step-grant line that names the step and ends in the payload's session id."""
    repo = gs_repo("lift", dict([gs_step(GS_STEP, GS_LANE, grants=[gs_grant("reviewer")])]))
    config, session = ov_config("grant-lift"), "gs-payload-lift"
    problem = ov_want(*gs_spawn(config, session, repo, OP_REVIEWER), "allow", "agent-model-cap")
    if problem:
        return False, problem
    lifts = [line.split("\t") for line in gs_log_lines(config) if "\tstep-grant\t" in line]
    fields = lifts[0] if len(lifts) == 1 else []
    if (len(fields) != 6 or fields[3] != "agent-model-cap" or GS_STEP not in fields[4]
            or fields[5] != session):
        return False, ("guard.log wrote %r, want one step-grant line for agent-model-cap that names %s"
                       % (["\t".join(f) for f in lifts], GS_STEP))
    return True, "allowed on the lane's own grant; one step-grant line names the step"


def gs_unread_log_check():
    """A bound step the guard cannot parse is refused, and guard.log gets a step-grant-unread line for it."""
    repo = gs_repo("unread-log", dict([GS_BAD]))
    config, session = ov_config("grant-unread-log"), "gs-payload-unread-log"
    problem = ov_want(*gs_spawn(config, session, repo, OP_REVIEWER), "deny", "agent-model-cap")
    if problem:
        return False, problem
    if not [line for line in gs_log_lines(config) if "\tstep-grant-unread\t" in line]:
        return False, "guard.log has no step-grant-unread line for the bound step"
    return True, "refused, and the unreadable bound step is logged as step-grant-unread"


def gs_cost_check():
    """A Sonnet spawn runs no git call that names the roadmap. GIT_TRACE makes each git process write its
    argv, and the guard's git children inherit it. A control runs first, through the guard itself: a hard
    reset in a linked worktree makes the guard read git state, so its trace must be written. Only then
    does an empty roadmap trace on the Sonnet spawn mean something."""
    repo = gs_repo("cost", dict([gs_step(GS_STEP, GS_LANE, grants=[gs_grant(None)])]))
    config, session = ov_config("grant-cost"), "gs-payload-cost"
    control, traced = os.path.join(ROOT, "grant", "control.trace"), os.path.join(ROOT, "grant", "cost.trace")
    ov_call("Bash", {"command": VCS + " reset --hard"}, GITWT, ov_config("grant-cost-control"),
            "gs-control", 0, env={"GIT_TRACE": control})
    if not gs_read(control).strip():
        return False, "the guard's own git call wrote no trace, so an empty roadmap trace would prove nothing"
    problem = ov_want(*gs_spawn(config, session, repo, GS_SONNET, env=dict(GS_ENV, GIT_TRACE=traced)),
                      "allow", "agent-model-cap")
    if problem:
        return False, "the Sonnet spawn: " + problem
    named = [line for line in gs_read(traced).splitlines() if "origin/roadmap" in line or "roadmap/data" in line]
    if named:
        return False, "a git call names the roadmap on a Sonnet spawn: %s" % named[0][:120]
    return True, "a Sonnet spawn was allowed, and no git call the guard made named the roadmap"


def gs_runner_id_check():
    """The runner's own lane id would bind a case that sets none to a lane. The runner drops it, so a reviewer
    spawn on a step bound to that id, with a reviewer grant, is still refused. The id is set in this process only,
    and restored after the call."""
    repo = gs_repo("runner-id", dict([gs_step(GS_STEP, GS_LANE, grants=[gs_grant("reviewer")])]))
    config, session = ov_config("grant-runner-id"), "gs-payload-runner-id"
    saved = os.environ.get("CLAUDE_CODE_REMOTE_SESSION_ID")
    os.environ["CLAUDE_CODE_REMOTE_SESSION_ID"] = "cse_" + GS_LANE
    try:
        problem = ov_want(*gs_spawn(config, session, repo, OP_REVIEWER, env=None), "deny", "agent-model-cap")
    finally:
        if saved is None:
            os.environ.pop("CLAUDE_CODE_REMOTE_SESSION_ID", None)
        else:
            os.environ["CLAUDE_CODE_REMOTE_SESSION_ID"] = saved
    return (not problem), (problem or "refused: the runner's own lane id did not reach the case")


# Each refusal case below has a control: the same fixture with its one defect repaired, which must be allowed.
# A control that is refused would mean the reader never ran, so the refusal case would pass for the wrong reason.
GS_CHECKS = (
    ("step grant: a reviewer spawn on the lane's step is allowed by a grant for reviewers, and logged",
     gs_lift_check),
    ("step grant: a step with no grant refuses an Opus spawn",
     gs_verdict_check("no-grant", dict([gs_step(GS_STEP, GS_LANE)]), OP_REVIEWER, "deny")),
    ("step grant: control for no grant, the step with a reviewer grant is allowed",
     gs_verdict_check("ctl-no-grant", dict([gs_step(GS_STEP, GS_LANE, grants=[gs_grant("reviewer")])]),
                      OP_REVIEWER, "allow")),
    ("step grant: a grant on another lane's step does not lift this lane's Opus spawn",
     gs_verdict_check("other-step", dict([gs_step(GS_STEP, GS_LANE),
                                          gs_step("step-b", "zz9y8x", grants=[gs_grant(None)])]),
                      OP_REVIEWER, "deny")),
    ("step grant: control for another lane's step, this lane's own step with a grant is allowed",
     gs_verdict_check("ctl-other-step", dict([gs_step(GS_STEP, GS_LANE, grants=[gs_grant("reviewer")]),
                                              gs_step("step-b", "zz9y8x", grants=[gs_grant(None)])]),
                      OP_REVIEWER, "allow")),
    ("step grant: a grant for builders does not lift a reviewer spawn",
     gs_verdict_check("builder-grant", dict([gs_step(GS_STEP, GS_LANE, grants=[gs_grant("builder")])]),
                      OP_REVIEWER, "deny")),
    ("step grant: control for a builder grant, a reviewer grant for a reviewer is allowed",
     gs_verdict_check("ctl-builder-grant", dict([gs_step(GS_STEP, GS_LANE, grants=[gs_grant("reviewer")])]),
                      OP_REVIEWER, "allow")),
    ("step grant: a bound step that cannot be parsed refuses an Opus spawn",
     gs_verdict_check("bad-json", dict([GS_BAD]), OP_REVIEWER, "deny")),
    ("step grant: control for an unparseable step, the same step parsed with a reviewer grant is allowed",
     gs_verdict_check("ctl-bad-json", dict([gs_step(GS_STEP, GS_LANE, grants=[gs_grant("reviewer")])]),
                      OP_REVIEWER, "allow")),
    ("step grant: a grant with an unknown role refuses, even for a spawn of that role",
     gs_verdict_check("unknown-role", dict([gs_step(GS_STEP, GS_LANE, grants=[gs_grant("wizard")])]),
                      GS_WIZARD, "deny")),
    ("step grant: control for an unknown role, a reviewer grant for a reviewer is allowed",
     gs_verdict_check("ctl-unknown-role", dict([gs_step(GS_STEP, GS_LANE, grants=[gs_grant("reviewer")])]),
                      OP_REVIEWER, "allow")),
    ("step grant: a grant with no role key refuses an Opus spawn",
     gs_verdict_check("no-role-key", dict([gs_step(GS_STEP, GS_LANE,
                                                   grants=[gs_grant("reviewer", drop_role=True)])]),
                      OP_REVIEWER, "deny")),
    ("step grant: control for no role key, the same grant with its role is allowed",
     gs_verdict_check("ctl-no-role-key", dict([gs_step(GS_STEP, GS_LANE, grants=[gs_grant("reviewer")])]),
                      OP_REVIEWER, "allow")),
    ("step grant: a grant with role null allows a builder spawn",
     gs_verdict_check("null-role", dict([gs_step(GS_STEP, GS_LANE, grants=[gs_grant(None)])]),
                      OP_BUILDER, "allow")),
    ("step grant: a step with status done refuses an Opus spawn, even with a grant",
     gs_verdict_check("done", dict([gs_step(GS_STEP, GS_LANE, status="done", grants=[gs_grant(None)])]),
                      OP_REVIEWER, "deny")),
    ("step grant: control for done, the same step not done is allowed",
     gs_verdict_check("ctl-done", dict([gs_step(GS_STEP, GS_LANE, grants=[gs_grant(None)])]),
                      OP_REVIEWER, "allow")),
    ("step grant: a repository with no origin/roadmap ref refuses an Opus spawn",
     gs_verdict_check("no-ref", dict([gs_step(GS_STEP, GS_LANE, grants=[gs_grant(None)])]),
                      OP_REVIEWER, "deny", ref=False)),
    ("step grant: control for no ref, the same step on the ref is allowed",
     gs_verdict_check("ctl-no-ref", dict([gs_step(GS_STEP, GS_LANE, grants=[gs_grant(None)])]),
                      OP_REVIEWER, "allow")),
    ("step grant: two steps bound to this lane refuse an Opus spawn, even with a grant on one",
     gs_verdict_check("two-steps", dict([gs_step(GS_STEP, GS_LANE, grants=[gs_grant(None)]),
                                         gs_step("step-c", GS_LANE)]),
                      OP_REVIEWER, "deny")),
    ("step grant: control for two steps, one step bound to this lane with the grant is allowed",
     gs_verdict_check("ctl-two-steps", dict([gs_step(GS_STEP, GS_LANE, grants=[gs_grant(None)])]),
                      OP_REVIEWER, "allow")),
    ("step grant: a Sonnet spawn runs no git call that names the roadmap", gs_cost_check),
    ("step grant: an unparseable bound step is logged as step-grant-unread", gs_unread_log_check),
    ("step grant: the runner's own lane id does not reach a case that sets none", gs_runner_id_check),
)
for _label, _check in GS_CHECKS:
    LOG_CHECKS_EXTRA.append((_label, _check))
    FIXTURELESS_CHECKS.add(_check)


# THE LOAD BRAKE ON A LIFTED OPUS SPAWN. A lifted Opus spawn ask exits in refuse(), so unless rule 9c, the
# machine-load brake, runs first, a full machine would not refuse a spawn that a grant or an override lifted.
# The brake applies to every lane start, lifted or not. LB_ALL_HIGH is a full machine: memory and disk both
# over the full line, and the case's `load` key is that reading.
def gl_check(name, tool_input, config_name, session_name, typed=None, grant=None, load=None, want="deny"):
    """One start call on a machine with the given reading. `grant` is the step's grant list, when the
    lane is bound to a step; `typed` is an owner prompt typed before the call. Returns the verdict wanted."""
    config, session = ov_config(config_name), session_name
    if grant is not None:
        repo = gs_repo(name, dict([gs_step(GS_STEP, GS_LANE, grants=grant)]))
        cwd, env = repo, GS_ENV
    else:
        cwd, env = NOGIT, None
    note = ov_type(config, session, typed) if typed else ""
    problem = ov_want(*ov_call("Agent", dict(tool_input), cwd, config, session, 60, env=env, load=load),
                      want, "load-brake" if want == "deny" else "agent-model-cap")
    return (not problem), (problem or ("%s, as wanted" % want)) + ("; " + note if note and problem else "")


def gl_step_grant_full_check():
    return gl_check("load-grant", OP_BUILDER, "load-grant", "gl-payload-grant",
                    grant=[gs_grant(None)], load=LB_ALL_HIGH)


def gl_typed_override_full_check():
    return gl_check("load-typed", OP_BUILDER, "load-typed", "gl-payload-typed",
                    typed="opus 2h", load=LB_ALL_HIGH)


def gl_step_grant_normal_check():
    return gl_check("load-normal", OP_BUILDER, "load-normal", "gl-payload-normal",
                    grant=[gs_grant(None)], want="allow")


def gl_sonnet_full_check():
    return gl_check("load-sonnet", GS_SONNET, "load-sonnet", "gl-payload-sonnet", load=LB_ALL_HIGH)


GL_CHECKS = (
    ("lift and load brake: a step grant lifts an Opus spawn, and a full machine still denies it",
     gl_step_grant_full_check),
    ("lift and load brake: a typed opus 2h lifts an Opus spawn, and a full machine still denies it",
     gl_typed_override_full_check),
    ("lift and load brake: control, the same step grant on a normal machine lets the spawn through",
     gl_step_grant_normal_check),
    ("lift and load brake: control, a Sonnet spawn on a full machine is denied by the load brake",
     gl_sonnet_full_check),
)
for _label, _check in GL_CHECKS:
    LOG_CHECKS_EXTRA.append((_label, _check))
    FIXTURELESS_CHECKS.add(_check)


def ov_once_expiry_check():
    """A one-act override that nothing uses ends after 10 minutes: it works just before, and not at the end."""
    config = ov_config("once-expiry")
    note = ""
    for session, seconds, want in (("ov-expiry-before", OV_ONCE_SECONDS - 1, "allow"),
                                   ("ov-expiry-at-end", OV_ONCE_SECONDS, "deny")):
        note = ov_type(config, session, "override") or note
        problem = ov_want(*ov_kill(config, session, seconds), want, "machine-wide-kill")
        if problem:
            return False, "call at +%ds: %s; %s" % (seconds, problem, note or "the override was typed")
    return True, "allowed at +599 s, refused at +600 s"


def ov_corrupt_check():
    """An override file the guard cannot read is no override: the call is refused, never allowed. Garbage text
    also logs `override-unread`, so the owner can see why the override did nothing."""
    config = ov_config("corrupt")
    for name, body in (
            ("text", b"not json {"), ("empty", b""), ("list", b"[]"), ("no-until", b'{"kind": "timed"}'),
            ("bad-kind", b'{"kind": "forever", "until": "2099-01-01T00:00:00+00:00"}')):
        session = "ov-corrupt-" + name
        path = ov_pass_path(config, session)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "wb") as handle:
            handle.write(body)
        problem = ov_want(*ov_kill(config, session, 60), "deny", "machine-wide-kill")
        if problem:
            return False, "a %s override file: %s" % (name, problem)
        if name == "text":
            with open(os.path.join(config, "guard.log"), encoding="utf-8") as handle:
                mine = [l for l in handle.read().splitlines() if l.endswith("\t" + session)]
            if not any("override-unread" in l for l in mine):
                return False, "a text override file logged no override-unread line: %r" % mine
    return True, "five unreadable override files, each refused; garbage text logged override-unread"


def ov_scope_check():
    """An override covers only the session that typed it. Another session's call, and a call that names no
    session, are refused. The typing session's override is still there afterwards."""
    config = ov_config("scope")
    for kind, prompt in (("timed", "override 15m"), ("once", "override")):
        session = "ov-scope-a-" + kind
        note = ov_type(config, session, prompt)
        steps = [("another session", lambda: ov_kill(config, "ov-scope-b-" + kind, 60), "deny"),
                 ("no session id", lambda: ov_kill(config, None, 90), "deny"),
                 ("the typing session", lambda: ov_kill(config, session, 120), "allow")]
        for label, call, want in steps:
            problem = ov_want(*call(), want, "machine-wide-kill")
            if problem:
                return False, "a %s override, %s: %s; %s" % (kind, label, problem, note or "typed")
    return True, "both kinds: another session and an unnamed one refused, the typing session allowed"


def ov_parallel_check(workers=6, rounds=5):
    """Calls that run together on one one-act override: exactly one is allowed, and the rest are refused.
    How often this case catches a check-then-delete race is unmeasured: the guard processes start
    tens of milliseconds apart, and the race window is far shorter."""
    config = ov_config("parallel")
    problem = ov_want(*ov_kill(config, "ov-parallel-warm", 0), "deny", "machine-wide-kill")
    if problem:
        return False, "with no override: " + problem  # also builds every lazy fixture before the threads start
    for n in range(rounds):
        session = "ov-parallel-%d" % n
        note = ov_type(config, session, "override")
        verdicts = [None] * workers
        start = threading.Barrier(workers)

        def worker(i):
            start.wait()
            verdicts[i] = ov_kill(config, session, 60)[0]
        threads = [threading.Thread(target=worker, args=(i,)) for i in range(workers)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()
        if verdicts.count("allow") != 1 or verdicts.count("deny") != workers - 1:
            return False, "round %d: %d calls raced for one override, verdicts %r, want one allow; %s" % (
                n, workers, verdicts, note or "typed")
    return True, "%d rounds of %d racing calls, one allow each" % (rounds, workers)


OV_TAKE_CHILD = (
    "import sys\n"
    "from datetime import datetime\n"
    "sys.path.insert(0, sys.argv[1])\n"
    "import override\n"
    "print(override.take(sys.argv[2], None, datetime.fromisoformat(sys.argv[3])))\n"
)


def ov_take_race_check(workers=6, rounds=30):
    """Processes that call take() on one one-act override at once: exactly one gets it. A Windows rename
    acts on an open handle, so a rename claim let two racers win (2 of 40 rounds, run 40296652083)."""
    config = ov_config("take-race")
    env = dict(os.environ, CLAUDE_CONFIG_DIR=config)
    for n in range(rounds):
        session = "ov-take-race-%d" % n
        note = ov_type(config, session, "override")
        got = [None] * workers
        start = threading.Barrier(workers)

        def worker(i):
            start.wait()
            run = subprocess.run([sys.executable, "-c", OV_TAKE_CHILD, os.path.dirname(GUARD), session,
                                  ov_clock(60)], capture_output=True, text=True, env=env, timeout=60)
            got[i] = run.stdout.strip() if run.returncode == 0 else "error: " + run.stderr.strip()[-80:]
        threads = [threading.Thread(target=worker, args=(i,)) for i in range(workers)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()
        if got.count("override") != 1 or got.count("None") != workers - 1:
            return False, "round %d: %d processes raced take(), results %r, want one override; %s" % (
                n, workers, got, note or "typed")
    return True, "%d rounds of %d racing take() calls, one winner each" % (rounds, workers)


def ov_late_reader_check():
    """A call that read the override before another call spent it is refused. Its bytes come back as the
    override file here, which is what it sees. A new `override` typed at the same instant still lifts one act."""
    config, session = ov_config("late-reader"), "ov-late-reader"
    rule = "machine-wide-kill"
    note = ov_type(config, session, "override")
    path = ov_pass_path(config, session)
    try:
        with open(path, "rb") as handle:
            seen = handle.read()
    except OSError as error:
        return False, "no override file after `override`: %s; %s" % (error, note or "typed")
    ok, why = ov_story([("the first call", lambda: ov_kill(config, session, 60), "allow", rule)], note)
    if not ok:
        return False, why
    with open(path, "wb") as handle:
        handle.write(seen)
    ok, why = ov_story([("a call that read the override before it was spent",
                         lambda: ov_kill(config, session, 90), "deny", rule)], note)
    if not ok:
        return False, why
    os.remove(path)
    note = ov_type(config, session, "override") or note
    ok, why = ov_story([("a new override typed at the same instant",
                         lambda: ov_kill(config, session, 120), "allow", rule)], note)
    if not ok:
        return False, why
    return True, "the spent override stayed spent for a late reader, and a new override lifted one act"


def ov_agent_once_check():
    """An agent's call never spends a one-act override, and the override stays for the orchestrator's next call."""
    config, session = ov_config("agent-once"), "ov-agent-once"
    rule = "machine-wide-kill"
    ok, why = ov_story([("agent, no override", lambda: ov_kill(config, session, 0, OV_AGENT),
                         "deny", rule)])
    if not ok:
        return False, why
    note = ov_type(config, session, "override")
    ok, why = ov_story([
        ("agent under a one-act override", lambda: ov_kill(config, session, 60, OV_AGENT), "deny", rule),
        ("orchestrator, override unspent", lambda: ov_kill(config, session, 120), "allow", rule),
        ("orchestrator, override spent", lambda: ov_kill(config, session, 180), "deny", rule)], note)
    if not ok:
        return False, why
    return True, "the agent was refused and left the override; the orchestrator used it once"


def ov_agent_timed_check():
    """A timed override reaches the owner's agents as well as the session itself, until it ends."""
    config, session = ov_config("agent-timed"), "ov-agent-timed"
    rule = "machine-wide-kill"
    ok, why = ov_story([("agent, no override", lambda: ov_kill(config, session, 0, OV_AGENT),
                         "deny", rule)])
    if not ok:
        return False, why
    note = ov_type(config, session, "override 15m")
    ok, why = ov_story([
        ("agent, first call", lambda: ov_kill(config, session, 60, OV_AGENT), "allow", rule),
        ("agent, second call", lambda: ov_kill(config, session, 120, OV_AGENT), "allow", rule),
        ("orchestrator", lambda: ov_kill(config, session, 180), "allow", rule),
        ("agent at the end instant",
         lambda: ov_kill(config, session, OV_TIMED_SECONDS, OV_AGENT), "deny", rule)], note)
    if not ok:
        return False, why
    return True, "an agent is allowed under a timed override until it ends"


def ov_frozen_acts(config, session):
    """frozen-path and git-env-set refusals. The override file itself is frozen: a session that could
    write it could grant itself an override."""
    pass_file = slash(ov_pass_path(config, session))
    return (
        ("a Write of a config hook", "Write",
         {"file_path": slash(os.path.join(config, "hooks", "guard.py")), "content": "x"},
         "frozen-path"),
        ("a Write of the override file", "Write", {"file_path": pass_file, "content": "{}"},
         "frozen-path"),
        ("a cp onto the override file", "Bash", {"command": "cp /tmp/x.json " + pass_file},
         "frozen-path"),
        ("a command that sets GIT_DIR", "Bash",
         {"command": "export GIT_DIR=/x; python -m pytest"}, "git-env-set"),
    )


def ov_kill_all_acts(config, session):
    """A kill of pid 0 (the process group), 1 (init) or -1 (every process) can end the owner's whole
    machine session. No override covers it, so an override that lifts `kill $(pgrep ...)` still refuses these."""
    return tuple((label, "Bash", {"command": command}, "machine-wide-kill") for label, command in (
        ("a kill of pid 0", "kill 0"),
        ("a kill of pid 1", "kill 1"),
        ("a kill of pid -1", "kill -9 -- -1"),
        ("a kill of pid -1 with a named signal", "kill -TERM -1"),
    ))


# One act of an exclusion story. `rule` names the refusal (a tuple lists the rules that may name it
# under an override); `first` names the refusal with no override, when the first rule to fire is another
# one. `want` is the decision: an ask for agent-model-cap, else a deny.
OvAct = namedtuple("OvAct", "label tool tool_input rule want first cwd agent_id agent_type temp",
                   defaults=("deny", None, NOGIT, None, None, None))


def ov_act_call(act, config, session, seconds):
    return ov_call(act.tool, act.tool_input, act.cwd, config, session, seconds, act.agent_id,
                   act.agent_type, act.temp)


def ov_drift_acts(config, session):
    """An agent that left its own worktree: worktree-home, rule 0, refuses every call it makes, and
    no override lifts it (owner, 18:37 CDT). Each act is refused as worktree-home under a timed override, with
    or without another refusal in the same command. An override that lifted rule 0 would free the agent."""
    primary = os.path.join(ROOT, "ovdrift_primary")
    worktree = os.path.join(primary, ".claude", "worktrees", "agent-" + OV_AGENT)
    if not os.path.isdir(worktree):
        make_repo(primary, {"src/app.py": "print(1)\n"})
        run_vcs(primary, "worktree", "add", "-q", worktree, "-b", "worktree-agent-" + OV_AGENT)
    ov_call("Bash", {"command": "echo hi"}, worktree, config, session, 0, OV_AGENT)  # records the home
    hook = slash(os.path.join(config, "hooks", "guard.py"))
    shell = tuple(OvAct(label, "Bash", {"command": command}, "worktree-home", cwd=primary,
                        agent_id=OV_AGENT)
                  for label, command in (
        ("a drifted agent's write onto a config hook", "echo x > " + hook),
        ("a drifted agent's kill of pid 0", "kill 0"),
        ("a drifted agent's command that sets GIT_DIR", "GIT_DIR=/x git status"),
        ("a drifted agent's echo", "echo hi"),
        ("a drifted agent's kill of a pgrep list", "kill $(pgrep x)"),
    ))
    # The cwd is the home; the target is the primary checkout, outside it.
    write_out = OvAct("an agent's Write into the primary checkout from inside its worktree", "Write",
                      {"file_path": os.path.join(primary, "src", "app.py"), "content": "x"},
                      "worktree-home", cwd=worktree, agent_id=OV_AGENT)
    return shell + (write_out,)


def ov_cap_shell_acts(config, session):
    """The shell form of agent-model-cap: a write of the cap variable into the project settings
    file by echo, printf or a heredoc. It asks with no override, and no override lifts it, as for a Write."""
    line = CAP_KEY + "=opus"
    return tuple(OvAct(label, "Bash", {"command": command}, "agent-model-cap", "ask")
                 for label, command in (
        ("an echo of the cap variable into the project settings file",
         "echo " + line + " > " + PROJ_SETTINGS),
        ("a printf of the cap variable into the project settings file",
         "printf '%s\\n' " + line + " > " + PROJ_SETTINGS),
        ("a heredoc of the cap variable into the project settings file",
         "cat <<'EOF' > " + PROJ_SETTINGS + "\n" + line + "\nEOF"),
    ))


def ov_chain_acts(config, session):
    """A refusal no override lifts, in one command with a refusal an override does lift. Reaching the lifted
    one must not end the judging before the other, and the one-act override stays unspent."""
    hook = "echo x > " + slash(os.path.join(config, "hooks", "guard.py"))
    silent = VCS + " commit -m x >/dev/null 2>&1; "
    # The guard reads ROOT/tmp as the system temp, so the NOGIT cwd is no throwaway and a silenced
    # commit there is refused by silent-write.
    temp = os.path.join(ROOT, "tmp")
    return tuple(OvAct(label, "Bash", {"command": command}, rules, first=first, temp=where)
                 for label, command, rules, first, where in (
        ("a write onto a config hook", hook, "frozen-path", None, None),
        ("a pkill, then a write onto a config hook", "pkill -f foo; " + hook,
         ("machine-wide-kill", "frozen-path"), "machine-wide-kill", None),
        ("a write onto a config hook, then a pkill", hook + "; pkill -f foo",
         ("machine-wide-kill", "frozen-path"), None, None),
        ("a silent commit, then a kill of pid 0", silent + "kill 0",
         ("silent-write", "machine-wide-kill"), "silent-write", temp),
        ("a silent commit, then a kill of pid -1", silent + "kill -9 -1",
         ("silent-write", "machine-wide-kill"), "silent-write", temp),
    ))


def ov_role_acts(config, session):
    """The model and role guards stay outside every override, as frozen paths do: an override that lifted them
    would let an agent pick its own model or edit the tests it is judged by."""
    return (
        OvAct("a settings write that lifts the agent model cap", "Write",
              {"file_path": PROJ_LOCAL, "content": cap_settings()}, "agent-model-cap", "ask"),
        OvAct("a spawn on the Haiku model", "Agent",
              {"prompt": "do it", "model": "haiku"}, "agent-model-floor"),
        OvAct("a builder's third round on Sonnet", "Agent",
              {"prompt": "Round 3 of 3. Finish the fix.", "model": "sonnet",
               "subagent_type": "builder"}, "roles-third-round-steps-up"),
        OvAct("a builder's edit of a test file", "Edit",
              {"file_path": "src/test_app.py", "new_string": "x = 1"}, "builder-test-edit",
              agent_id="bld1", agent_type="builder"),
        OvAct("a test-author's edit of product code", "Edit",
              {"file_path": "src/app.py", "new_string": "x = 1"}, "test-author-scope",
              cwd=GITMAIN, agent_id="auth1", agent_type="test-author"),
        OvAct("a record-writer's edit of a Python file", "Edit",
              {"file_path": "hooks/guard.py", "new_string": "x"}, "record-writer-scope",
              agent_id="rw1", agent_type="record-writer"),
    )


def ov_builder_diff_acts(config, session):
    """A builder's test change at commit, after a reset to the lane tip, as the incident does. builder-diff is
    a role guard, so no override lifts it."""
    materialize(_bd_inc)
    return (OvAct("a builder's commit of a test change after a reset to the lane tip", "Bash",
                  {"command": COMMIT}, BDIFF, cwd=_bd_inc, agent_id="bld1", agent_type="builder"),)


def ov_exclusion_check(timed, make_acts, what):
    """The acts `make_acts` lists stay refused under either kind of override. A refusal the override does
    not lift does not spend it, so the next lifted act still goes through."""
    kind = "timed" if timed else "once"

    def check():
        config, session = ov_config("%s-%s" % (what, kind)), "ov-%s-%s" % (what, kind)
        acts = [OvAct(*act) for act in make_acts(config, session)]
        for act in acts:
            problem = ov_want(*ov_act_call(act, config, session, 0), act.want, act.first or act.rule)
            if problem:
                return False, "%s with no override: %s" % (act.label, problem)
        note = ov_type(config, session, "override 15m" if timed else "override")
        for act in acts:
            problem = ov_want(*ov_act_call(act, config, session, 60), act.want, act.rule)
            if problem:
                return False, "%s under a %s override: %s; %s" % (act.label, kind, problem, note or "typed")
        problem = ov_want(*ov_kill(config, session, 120), "allow", "machine-wide-kill")
        if problem:
            return False, "a lifted act after the excluded refusals: %s; %s" % (problem, note or "typed")
        return True, "%d excluded refusals stayed; the override was still there for a lifted act" % len(acts)
    return check


def ov_off_check():
    """`override off` ends an override at once, whichever kind it was."""
    config = ov_config("off")
    for kind, prompt, spend_first in (("timed", "override 15m", True), ("once", "override", False)):
        session = "ov-off-" + kind
        note = ov_type(config, session, prompt)
        if spend_first:  # a timed override survives a use; a one-act override would not
            problem = ov_want(*ov_kill(config, session, 30), "allow", "machine-wide-kill")
            if problem:
                return False, "%s override, before off: %s; %s" % (kind, problem, note or "typed")
        note = ov_type(config, session, "override off", 60) or note
        problem = ov_want(*ov_kill(config, session, 90), "deny", "machine-wide-kill")
        if problem:
            return False, "%s override, after `override off`: %s; %s" % (kind, problem, note or "typed")
    return True, "both kinds refused after `override off`"


def ov_log_check():
    """A lifted act writes one log line: the decision cell says `override`, the rule cell names the rule
    that was lifted, and the last cell is the session. lint/guard_log_report.py reads that shape."""
    config, session = ov_config("log"), "ov-log-session"
    note = ov_type(config, session, "override 15m")
    log = os.path.join(config, "guard.log")
    if os.path.exists(log):
        os.remove(log)
    problem = ov_want(*ov_kill(config, session, 60), "allow", "machine-wide-kill")
    if problem:
        return False, "the passed call: %s; %s" % (problem, note or "typed")
    if not os.path.exists(log):
        return False, "the passed call wrote no log line"
    with open(log, encoding="utf-8") as handle:
        lines = [l for l in handle.read().splitlines() if l.strip()]
    if len(lines) != 1:
        return False, "expected one line for the passed call, found %d: %r" % (len(lines), lines)
    fields = lines[0].split("\t")
    if len(fields) != 6 or fields[2:4] != ["override", "machine-wide-kill"] or fields[5] != session:
        return False, "the line does not read override + machine-wide-kill + the session: %r" % lines[0]
    return True, "one line: decision override, rule machine-wide-kill"


def ov_no_module_check():
    """A guard copy that cannot import override never allows on an override. An import error inside
    the refusal path would otherwise reach the guard's crash handler, which fails open."""
    config, session = ov_config("no-module"), "ov-no-module"
    note = ov_type(config, session, "override 15m")
    folder = _guard_copy("ov-no-module", "override.py")
    if os.path.exists(os.path.join(folder, "override.py")):
        return False, "the scratch copy holds override.py, so the case proves nothing"
    env = dict(os.environ)
    env.pop("CLAUDE_CODE_REMOTE", None)
    env.pop("PYTHONPATH", None)
    env.pop("CLAUDE_CODE_SESSION_ID", None)
    env.update(CLAUDE_CONFIG_DIR=config, CLAUDE_GUARD_ROOT_PID=str(os.getpid()),
               LOCAL_TIME_NOW=ov_clock(60))
    payload = json.dumps({"tool_name": "Bash", "tool_input": {"command": OV_KILL}, "cwd": NOGIT,
                          "session_id": session})
    run = subprocess.run([sys.executable, os.path.join(folder, "guard.py")], input=payload,
                         capture_output=True, text=True, env=env, timeout=120)
    got = _decision(run)[0]
    if got != "deny":
        return False, "a copy with no override.py gave %s under an override, want deny; %s" % (
            got, note or "typed")
    return True, "a copy with no override.py refuses the call"


for _label, _check in (
    ("override: a one-act override that nothing uses ends after 10 minutes", ov_once_expiry_check),
    ("override: an unreadable override file is no override, and garbage text logs override-unread",
     ov_corrupt_check),
    ("override: an override covers only the session that typed it", ov_scope_check),
    ("override: two calls racing for one one-act override, exactly one gets it", ov_parallel_check),
    ("override: processes racing take() for one one-act override, exactly one gets it",
     ov_take_race_check),
    ("override: a call that read a one-act override before it was spent is refused", ov_late_reader_check),
    ("override: an agent never spends a one-act override", ov_agent_once_check),
    ("override: a timed override reaches an agent until it ends", ov_agent_timed_check),
    ("override: frozen-path and git-env-set stay refused under a one-act override",
     ov_exclusion_check(False, ov_frozen_acts, "frozen")),
    ("override: frozen-path and git-env-set stay refused under a timed override",
     ov_exclusion_check(True, ov_frozen_acts, "frozen")),
    ("override: a kill of pid 0, 1 or -1 stays refused under a one-act override",
     ov_exclusion_check(False, ov_kill_all_acts, "killall")),
    ("override: a kill of pid 0, 1 or -1 stays refused under a timed override",
     ov_exclusion_check(True, ov_kill_all_acts, "killall")),
    # A one-act override never reaches an agent (ov_agent_once_check), so the drifted agent has
    # a timed story only.
    ("override: a drifted agent stays refused as worktree-home under a timed override",
     ov_exclusion_check(True, ov_drift_acts, "drift")),
    ("override: a refusal no override lifts stays when chained with one an override lifts, one-act override",
     ov_exclusion_check(False, ov_chain_acts, "chain")),
    ("override: a refusal no override lifts stays when chained with one an override lifts, timed override",
     ov_exclusion_check(True, ov_chain_acts, "chain")),
    ("override: the model and role guards stay refused under a one-act override",
     ov_exclusion_check(False, ov_role_acts, "role")),
    ("override: the model and role guards stay refused under a timed override",
     ov_exclusion_check(True, ov_role_acts, "role")),
    ("override: a builder's test change stays refused under a one-act override",
     ov_exclusion_check(False, ov_builder_diff_acts, "bdiff")),
    ("override: a builder's test change stays refused under a timed override",
     ov_exclusion_check(True, ov_builder_diff_acts, "bdiff")),
    ("override: a shell write of the agent model cap stays asked under a one-act override",
     ov_exclusion_check(False, ov_cap_shell_acts, "capshell")),
    ("override: a shell write of the agent model cap stays asked under a timed override",
     ov_exclusion_check(True, ov_cap_shell_acts, "capshell")),
    ("override: `override off` ends an override at once", ov_off_check),
    ("override: a lifted act writes one log line naming override and its rule", ov_log_check),
    ("override: a guard copy that cannot import override never allows on an override",
     ov_no_module_check),
):
    LOG_CHECKS_EXTRA.append((_label, _check))


# The prompt grammar (decision owner-override, the orchestrator's call on the keyword grammar). A
# punctuation mark after the word, with a space or the end of the prompt after it, separates it from its
# reason or its length: `override, yes` is a one-act override and `override, 15m` a timed one. A mark run
# into a word (`override.py`, `override-15m`) belongs to that word and grants nothing. A word after a
# length or after `off` grants nothing. `override, off` is covered by ov_grammar_off_mark_check.
# Each row is one prompt, typed in a session of its own at OV_T0. The grant it leaves is "once", "timed"
# (with minutes) or None for no file. A one-act grant logs its reason, when it has one.
OV_GRANT_ROWS = (
    ("override, yes", "once", None, "yes"),
    ("Override. go", "once", None, "go"),
    ("override! yes", "once", None, "yes"),
    ("override; reason", "once", None, "reason"),
    ("override - reason", "once", None, "reason"),
    ("override, 15m", "timed", 15, None),
    ("override", "once", None, None),
    ("override.", "once", None, None),
    ("override: reason", "once", None, "reason"),
    ("override yes", "once", None, "yes"),
    ("override 15m", "timed", 15, None),
    ("override: 15m", "timed", 15, None),
    ("overrides", None, None, None),
    ("override15m", None, None, None),
    ("override 15m please", None, None, None),
    ("override, 15m please", None, None, None),
    ("please override", None, None, None),
    ("override.py is broken", None, None, None),
    ("override-able", None, None, None),
    ("override-based approach", None, None, None),
    ("override-15m", None, None, None),
    ("override.15m", None, None, None),
)


def ov_grant_of(config, session):
    """What the session's override file holds: (kind, until), or (None, None) for no file. A file that
    does not parse reads as ("unreadable", None)."""
    path = ov_pass_path(config, session)
    if not os.path.exists(path):
        return None, None
    try:
        with open(path, encoding="utf-8") as handle:
            data = json.load(handle)
        return data["kind"], datetime.fromisoformat(data["until"])
    except (OSError, ValueError, KeyError, TypeError):
        return "unreadable", None


def ov_reason_logged(config, session, reason):
    """True when guard.log holds the reason line of this session's one-act override."""
    try:
        with open(os.path.join(config, "guard.log"), encoding="utf-8") as handle:
            lines = handle.read().splitlines()
    except OSError:
        return False
    return any(len(f) == 6 and f[2] == "override-reason" and f[5] == session and reason in f[4]
               for f in (line.split("\t") for line in lines))


def ov_grant_phrase(kind, minutes):
    """The grant a prompt leaves, in words: for a case label and for its pass line."""
    if kind == "once":
        return "a one-act override"
    if kind == "timed":
        return "a timed override of %d minutes" % minutes
    return "nothing"


def ov_grant_label(prompt, kind, minutes):
    return "override grammar: `%s` grants %s" % (prompt, ov_grant_phrase(kind, minutes))


def ov_grant_check(session, prompt, kind, minutes, reason):
    """The owner types `prompt` at OV_T0 in `session`. The override file it leaves is `kind`, lasting
    `minutes` when timed, or no file for None. ov_type writes the file by hand when override.py does not
    import, so any note from it fails the case."""
    config = ov_config("grant")

    def check():
        note = ov_type(config, session, prompt)
        if note:
            return False, note
        got, until = ov_grant_of(config, session)
        if got != kind:
            return False, "left %s, want %s" % (got or "no file", kind or "no file")
        length = OV_ONCE_SECONDS if kind == "once" else minutes * 60 if kind == "timed" else None
        if length is not None and until != OV_T0 + timedelta(seconds=length):
            return False, "ends at %s, want %s" % (until, OV_T0 + timedelta(seconds=length))
        if reason and not ov_reason_logged(config, session, reason):
            return False, "no override-reason line in guard.log holds %r" % reason
        return True, ov_grant_phrase(kind, minutes)
    return check


def ov_grammar_lift_check():
    """`override, yes` is a one-act override: it lifts the next refused act once, then the act is refused."""
    config, session, rule = ov_config("grant"), "ov-grant-lift", "machine-wide-kill"
    ok, why = ov_story([("with no override", lambda: ov_kill(config, session, 0), "deny", rule)])
    if not ok:
        return False, why
    note = ov_type(config, session, "override, yes")
    if note:
        return False, note
    ok, why = ov_story([
        ("first kill", lambda: ov_kill(config, session, 60), "allow", rule),
        ("second kill, override spent", lambda: ov_kill(config, session, 120), "deny", rule),
    ])
    if not ok:
        return False, why
    return True, "one kill lifted, then the kill was refused again"


def ov_grammar_off_check():
    """`override off` removes the session's one-act override and leaves no file."""
    config, session = ov_config("grant"), "ov-grant-off"
    note = ov_type(config, session, "override")
    if note:
        return False, note
    if ov_grant_of(config, session)[0] != "once":
        return False, "`override` left no one-act override"
    note = ov_type(config, session, "override off", 60)
    if note:
        return False, note
    if os.path.exists(ov_pass_path(config, session)):
        return False, "`override off` left the override file"
    return True, "`override off` removed the one-act override"


def ov_grammar_off_mark_check():
    """`override, off` is `override off`: the mark is dropped, so it ends an active timed override at
    once. With no override before it, it leaves no file. The kill is the proof the override was live."""
    config, rule = ov_config("grant"), "machine-wide-kill"
    bare = "ov-grant-off-none"
    note = ov_type(config, bare, "override, off")
    if note:
        return False, note
    if os.path.exists(ov_pass_path(config, bare)):
        return False, "`override, off` left a file with no override before it"
    session = "ov-grant-off-timed"
    note = ov_type(config, session, "override 15m")
    if note:
        return False, note
    got, until = ov_grant_of(config, session)
    if got != "timed" or until != OV_T0 + timedelta(seconds=OV_TIMED_SECONDS):
        return False, "`override 15m` left %s, want a timed override of 15 minutes" % (got or "no file")
    ok, why = ov_story([
        ("kill under the timed override", lambda: ov_kill(config, session, 60), "allow", rule),
    ])
    if not ok:
        return False, why
    note = ov_type(config, session, "override, off", 120)
    if note:
        return False, note
    if os.path.exists(ov_pass_path(config, session)):
        return False, "`override, off` left the timed override file"
    ok, why = ov_story([("kill after `override, off`", lambda: ov_kill(config, session, 180), "deny", rule)])
    if not ok:
        return False, why
    return True, "`override, off` ended the timed override, and left no file with none"


for _n, (_prompt, _kind, _minutes, _reason) in enumerate(OV_GRANT_ROWS):
    _check = ov_grant_check("ov-grant-%d" % _n, _prompt, _kind, _minutes, _reason)
    FIXTURELESS_CHECKS.add(_check)
    LOG_CHECKS_EXTRA.append((ov_grant_label(_prompt, _kind, _minutes), _check))
for _label, _check in (
    ("override grammar: `override off` removes the one-act override", ov_grammar_off_check),
    ("override grammar: `override, off` ends a timed override, and leaves no file with none",
     ov_grammar_off_mark_check),
    ("override grammar: `override, yes` lifts one kill, then the kill is refused again", ov_grammar_lift_check),
):
    FIXTURELESS_CHECKS.add(_check)
    LOG_CHECKS_EXTRA.append((_label, _check))


# =========================================================================== handoff-unread
# After compaction, the guard refuses each call it judges until the session reads its handoff. The flag
# is set at PostCompact and cleared by a Read of the handoff (hooks/reread_check.py). Its Stop mode
# refuses only at the end of a turn, so a turn could run before the read; this refusal is the PreToolUse
# half of that check (the precompact-handoff decision, item 9).

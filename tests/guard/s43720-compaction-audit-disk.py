# section 43720
FAMILY = "compaction-audit"
# The audit owes one Audit: spawn. The load brake refuses that spawn at a full disk (free under the smaller of 5% of the
# disk and 5 GB), so a session on a full disk could neither spawn the audit nor run the shell call that frees the disk:
# a deadlock. These cases hold the exemption: while the audit is owed
# AND the brake refuses the audit spawn for disk, compaction-audit lets through each disk-cleanup shell call (the janitor
# sweep, or rm -rf of an absolute /tmp path). Every other shell call stays refused. The cleanup clears nothing: the audit
# stays owed. A disk that is not full, or memory that is full, changes nothing: a sweep frees disk, not memory.
# The helpers are the compaction-audit ones of section 43700 (ca_copy, ca_config, ca_owed, ca_env) and the load-brake
# probe of section 39497 (LB_PROBE, which patches read_load). Nothing here copies them.
SWEEP_ROOT = REPO
CD_SWEEP = "python3 ~/.claude/janitor/sweep.py --root %s --attended --fast" % SWEEP_ROOT
CD_SWEEP_CONFIRM = CD_SWEEP + " --confirm"
CD_RM_TMP = "rm -rf /tmp/claude-disk-cleanup/run-1"
CD_RM_OTHER = "rm -rf /home/user/keep-me"
CD_RM_MIXED = CD_RM_TMP + " /home/user/keep-me"
# The sweep without --fast is not the cleanup: only the attended fast preview (and its --confirm) is.
CD_SWEEP_NOFAST = "python3 ~/.claude/janitor/sweep.py --root %s --attended" % SWEEP_ROOT
CD_SWEEP_NOFAST_CONFIRM = CD_SWEEP_NOFAST + " --confirm"
# rm -Rf is rm -rf: the same recursive force delete, so it is the same cleanup.
CD_RM_CAPITAL_R = "rm -Rf /tmp/claude-disk-cleanup/run-1"
# A /tmp path spelled with a trailing slash is /tmp itself, which is not a cleanup target.
CD_RM_TMP_ROOT = "rm -rf /tmp//"
# Shell chaining, expansion and traversal. Each form stays refused: the shell runs more than the one path it names.
CD_RM_SEMI = "rm -rf /tmp/claude-disk-cleanup/run-1;rm -rf /tmp/claude-disk-cleanup/run-2"
CD_RM_AND = "rm -rf /tmp/claude-disk-cleanup/run-1&&rm -rf /tmp/claude-disk-cleanup/run-2"
CD_RM_DOLLAR = "rm -rf /tmp/claude-disk-cleanup/$RUN"
CD_RM_GLOB = "rm -rf /tmp/*"
CD_RM_TILDE = "rm -rf /tmp/~/claude-disk-cleanup"
CD_RM_DOTDOT = "rm -rf /tmp/../home/user/keep-me"
# Pipes, redirects, substitution and a newline. A joined | or > makes one word, so only the character set refuses it.
# A spaced | or 2>&1 makes its own word, which the /tmp path check refuses too. So does a space inside a backtick or
# $( ), and a newline: each splits off a word that is no /tmp path. The path check refuses those, not the character
# set. The joined backtick, newline and < forms below have no such split: only the character set refuses them.
CD_RM_PIPE_SPACED = "rm -rf /tmp/a | sh"
CD_RM_PIPE = "rm -rf /tmp/a|sh"
CD_RM_REDIRECT = "rm -rf /tmp/a>/home/user/.bashrc"
CD_RM_FD_REDIRECT = "rm -rf /tmp/a 2>&1"
CD_RM_BACKTICK = "rm -rf /tmp/claude-disk-cleanup/`echo run-1`"
CD_RM_SUBST = "rm -rf $(echo /tmp/a)"
CD_RM_NEWLINE = "rm -rf /tmp/claude-disk-cleanup/run-1\nrm -rf /tmp/claude-disk-cleanup/run-2"
CD_RM_BACKTICK_JOINED = "rm -rf /tmp/a`id`"
CD_RM_NEWLINE_JOINED = "rm -rf /tmp/a\n/tmp/b"
CD_RM_LT_JOINED = "rm -rf /tmp/a</etc/x"
CD_ORDINARY = "echo hi"
# The readings. The brake's floors: busy under the smaller of 10% of the disk and 15 GB, full under the smaller of 5%
# and 5 GB. CD_FULL is a full disk. CD_BUSY is under the busy floor, over the full one.
CD_FULL = {"memory_pct": 40.0, "disk_free_gb": 3.3, "disk_total_gb": 926.0}
CD_BUSY = {"memory_pct": 40.0, "disk_free_gb": 7.0, "disk_total_gb": 100.0}
CD_FINE = {"memory_pct": 40.0, "disk_free_gb": 500.0, "disk_total_gb": 926.0}
CD_MEMORY_FULL = {"memory_pct": 96.0, "disk_free_gb": 500.0, "disk_total_gb": 926.0}


def cd_owed(name):
    """The audit owed: PostCompact sets the flags and the handoff's Read clears the reread flag, as ca_owed does.
    -> (folder, cfg, flag, why)."""
    folder = ca_copy("intact", drop_layout=False)
    cfg = ca_config(name + "-cfg", None)
    flag, why = ca_owed(folder, cfg)
    return folder, cfg, flag, why


def cd_run(folder, cfg, spec, tool, tool_input, tag):
    """One call through the copy's guard, under LB_PROBE, with read_load answering spec["reading"]. The probe's temp
    folder sits in the config folder, and the remote-session id is stripped, so a lane-session read cannot change the
    count. -> (run, side, why); run is None when the probe did not finish."""
    side_file = os.path.join(cfg, "probe-%s.json" % tag)
    temp = os.path.join(cfg, "tmp")
    os.makedirs(temp, exist_ok=True)
    env = ca_env(cfg)
    env.pop("CLAUDE_CODE_REMOTE_SESSION_ID", None)
    for name in ("TMPDIR", "TEMP", "TMP"):
        env[name] = temp
    body = {"tool_name": tool, "tool_input": tool_input, "cwd": NOGIT, "session_id": CA_SID}
    run = subprocess.run([sys.executable, "-c", LB_PROBE, os.path.join(folder, "hooks", "guard.py"), side_file,
                          json.dumps(spec)],
                         input=json.dumps(body), capture_output=True, text=True, env=env,
                         cwd=os.path.join(folder, "hooks"), timeout=120)
    if run.returncode != 0:
        return None, {}, "the probe exited %d: %s" % (run.returncode, run.stderr.strip()[-160:])
    try:
        with open(side_file, encoding="utf-8") as handle:
            side = json.load(handle)
    except (OSError, ValueError) as exc:
        return None, {}, "the probe wrote no readable side file: %s" % exc
    if side.get("probe_error"):
        return None, side, "the probe failed: " + side["probe_error"]
    return run, side, ""


def cd_brake(folder, cfg, reading):
    """What the load brake says of the audit spawn under `reading`: (reason, matched). The probe's hit mode judges the
    call and runs nothing, so no audit flag moves. -> (pair, why)."""
    run, side, why = cd_run(folder, cfg, {"mode": "hit", "reading": reading}, "Agent", CA_AUDIT, "brake")
    if why:
        return None, why
    hit = side.get("hit")
    if not isinstance(hit, list) or len(hit) != 2:
        return None, "the probe gave no load_hit pair: %r" % (hit,)
    return hit, ""


def cd_setup(name, reading, want):
    """The owed state, and a check that `reading` is the one the case names. The brake's verdict on the audit spawn
    under it must be `want`: "disk" (refused for disk), "memory" (refused for memory) or "pass" (let through).
    -> (folder, cfg, flag, why)."""
    folder, cfg, flag, why = cd_owed(name)
    if why:
        return None, None, None, why
    hit, why = cd_brake(folder, cfg, reading)
    if why:
        return None, None, None, "setup: " + why
    reason, matched = hit
    if want == "pass":
        ok = not reason
    elif want == "disk":
        ok = bool(reason) and "disk" in matched and "memory" not in matched
    else:
        ok = bool(reason) and "memory" in matched and "disk" not in matched
    if not ok:
        return None, None, None, ("setup: under this reading the load brake gives the audit spawn %r, want %s"
                                  % (matched or "no refusal", want))
    return folder, cfg, flag, ""


def cd_bash(folder, cfg, reading, command, tag):
    """One Bash call under `reading`. -> (decision, reason, side, why)."""
    run, side, why = cd_run(folder, cfg, {"mode": "main", "reading": reading}, "Bash", {"command": command}, tag)
    if why:
        return None, "", side, why
    decision, reason = _decision(run)
    return decision, reason, side, ""


def cd_allowed_check(name, reading, command, tag):
    """A disk cleanup call while the audit is owed and the disk is full: the call is allowed, with nothing printed."""
    folder, cfg, flag, why = cd_setup(name, reading, "disk")
    if why:
        return False, why
    decision, reason, _side, why = cd_bash(folder, cfg, reading, command, tag)
    if why:
        return False, why
    problem = ov_want(decision, reason, "allow", "compaction-audit")
    if problem:
        return False, ("the disk cleanup call %r was not allowed while the audit is owed and the disk is full: %s"
                       % (command[:60], problem))
    return True, "compaction-audit lets the disk cleanup call %r through while the audit is owed and the disk is full" % command[:60]


def cd_refused_check(name, reading, want, command, tag):
    """A Bash call that is not a disk cleanup, or a call under a reading that does not free disk: compaction-audit
    refuses it. `want` is the brake's verdict on the audit spawn that the case holds (see cd_setup)."""
    folder, cfg, flag, why = cd_setup(name, reading, want)
    if why:
        return False, why
    decision, reason, _side, why = cd_bash(folder, cfg, reading, command, tag)
    if why:
        return False, why
    problem = ov_want(decision, reason, "deny", "compaction-audit")
    if problem:
        return False, "the call %r was not refused by compaction-audit: %s" % (command[:60], problem)
    return True, "compaction-audit refuses the call %r while the audit is owed" % command[:60]


def cd_after_check():
    """After the disk cleanup call, the audit is still owed: an ordinary Bash call is still refused."""
    folder, cfg, flag, why = cd_setup("disk-after", CD_FULL, "disk")
    if why:
        return False, why
    _decision1, _reason1, _side1, why = cd_bash(folder, cfg, CD_FULL, CD_SWEEP, "cleanup")
    if why:
        return False, why
    decision, reason, _side2, why = cd_bash(folder, cfg, CD_FULL, CD_ORDINARY, "ordinary")
    if why:
        return False, why
    problem = ov_want(decision, reason, "deny", "compaction-audit")
    if problem:
        return False, "after the disk cleanup call, an ordinary Bash call was not refused by compaction-audit: %s" % problem
    return True, "after the disk cleanup call the audit stays owed: an ordinary Bash call is still refused"


def cd_quiet_check():
    """No audit owed: a Bash call under a full disk is allowed as before, and reads no load."""
    folder = ca_copy("intact", drop_layout=False)
    cfg = ca_config("disk-none-cfg", None)
    decision, reason, side, why = cd_bash(folder, cfg, CD_FULL, CD_SWEEP, "none")
    if why:
        return False, why
    problem = ov_want(decision, reason, "allow", "compaction-audit")
    if problem:
        return False, "with no audit owed, the sweep call was not allowed: %s" % problem
    reads = side.get("reads")
    if reads != 0:
        return False, "with no audit owed, a Bash call read the load %r times, want 0" % (reads,)
    return True, "with no audit owed, a Bash call is allowed and reads no load"


# LOG_CHECKS_EXTRA joined at section 40805, so this section joins LOG_CHECKS directly, as section 43700 does.
CD_CHECKS = (
    ("compaction-audit: an owed audit with a full disk lets the sweep preview through, as the disk cleanup",
     lambda: cd_allowed_check("disk-preview", CD_FULL, CD_SWEEP, "preview")),
    ("compaction-audit: an owed audit with a full disk lets the sweep --confirm through, as the disk cleanup",
     lambda: cd_allowed_check("disk-confirm", CD_FULL, CD_SWEEP_CONFIRM, "confirm")),
    ("compaction-audit: an owed audit with a full disk lets an rm -rf of an absolute /tmp path through",
     lambda: cd_allowed_check("disk-rm-tmp", CD_FULL, CD_RM_TMP, "rmtmp")),
    ("compaction-audit: after the disk cleanup call the audit stays owed, so an ordinary Bash call is still refused",
     cd_after_check),
    ("compaction-audit: an owed audit with a full disk refuses an rm -rf of a path outside /tmp",
     lambda: cd_refused_check("disk-rm-other", CD_FULL, "disk", CD_RM_OTHER, "rmother")),
    ("compaction-audit: an owed audit with a full disk refuses an rm -rf that mixes a /tmp path and another path",
     lambda: cd_refused_check("disk-rm-mixed", CD_FULL, "disk", CD_RM_MIXED, "rmmixed")),
    ("compaction-audit: an owed audit with a full disk lets an rm -Rf of an absolute /tmp path through",
     lambda: cd_allowed_check("disk-rm-capital", CD_FULL, CD_RM_CAPITAL_R, "rmcap")),
    ("compaction-audit: an owed audit with a full disk refuses the sweep without --fast, with --confirm",
     lambda: cd_refused_check("disk-nofast-confirm", CD_FULL, "disk", CD_SWEEP_NOFAST_CONFIRM, "nofastconfirm")),
    ("compaction-audit: an owed audit with a full disk refuses the sweep with --attended alone, without --fast",
     lambda: cd_refused_check("disk-nofast", CD_FULL, "disk", CD_SWEEP_NOFAST, "nofast")),
    ("compaction-audit: an owed audit with a full disk refuses an rm -rf of /tmp itself, written as /tmp//",
     lambda: cd_refused_check("disk-rm-root", CD_FULL, "disk", CD_RM_TMP_ROOT, "rmroot")),
    ("compaction-audit: an owed audit with a full disk refuses an rm -rf chained with ; to a second rm",
     lambda: cd_refused_check("disk-rm-semi", CD_FULL, "disk", CD_RM_SEMI, "rmsemi")),
    ("compaction-audit: an owed audit with a full disk refuses an rm -rf chained with && to a second rm",
     lambda: cd_refused_check("disk-rm-and", CD_FULL, "disk", CD_RM_AND, "rmand")),
    ("compaction-audit: an owed audit with a full disk refuses an rm -rf of a path with a $ expansion",
     lambda: cd_refused_check("disk-rm-dollar", CD_FULL, "disk", CD_RM_DOLLAR, "rmdollar")),
    ("compaction-audit: an owed audit with a full disk refuses an rm -rf of a glob under /tmp",
     lambda: cd_refused_check("disk-rm-glob", CD_FULL, "disk", CD_RM_GLOB, "rmglob")),
    ("compaction-audit: an owed audit with a full disk refuses an rm -rf of a path with a ~ in it",
     lambda: cd_refused_check("disk-rm-tilde", CD_FULL, "disk", CD_RM_TILDE, "rmtilde")),
    ("compaction-audit: an owed audit with a full disk refuses an rm -rf of a path that climbs out with ..",
     lambda: cd_refused_check("disk-rm-dotdot", CD_FULL, "disk", CD_RM_DOTDOT, "rmdotdot")),
    ("compaction-audit: an owed audit with a full disk refuses an rm -rf of a /tmp path piped to sh, with spaces around |",
     lambda: cd_refused_check("disk-rm-pipe-spaced", CD_FULL, "disk", CD_RM_PIPE_SPACED, "rmpipesp")),
    ("compaction-audit: an owed audit with a full disk refuses an rm -rf of a /tmp path piped to sh, with no spaces",
     lambda: cd_refused_check("disk-rm-pipe", CD_FULL, "disk", CD_RM_PIPE, "rmpipe")),
    ("compaction-audit: an owed audit with a full disk refuses an rm -rf of a /tmp path redirected to a file outside /tmp",
     lambda: cd_refused_check("disk-rm-redirect", CD_FULL, "disk", CD_RM_REDIRECT, "rmredir")),
    ("compaction-audit: an owed audit with a full disk refuses an rm -rf of a /tmp path with 2>&1 after it",
     lambda: cd_refused_check("disk-rm-fd", CD_FULL, "disk", CD_RM_FD_REDIRECT, "rmfd")),
    ("compaction-audit: an owed audit with a full disk refuses an rm -rf whose backtick holds a space, so one word is no /tmp path",
     lambda: cd_refused_check("disk-rm-backtick", CD_FULL, "disk", CD_RM_BACKTICK, "rmbacktick")),
    ("compaction-audit: an owed audit with a full disk refuses an rm -rf whose $( ) holds a space, so one word is no /tmp path",
     lambda: cd_refused_check("disk-rm-subst", CD_FULL, "disk", CD_RM_SUBST, "rmsubst")),
    ("compaction-audit: an owed audit with a full disk refuses two rm -rf calls split by a newline, so one word is no /tmp path",
     lambda: cd_refused_check("disk-rm-newline", CD_FULL, "disk", CD_RM_NEWLINE, "rmnewline")),
    ("compaction-audit: an owed audit with a full disk refuses an rm -rf whose joined backtick only the character set catches",
     lambda: cd_refused_check("disk-rm-backtick-joined", CD_FULL, "disk", CD_RM_BACKTICK_JOINED, "rmbtjoin")),
    ("compaction-audit: an owed audit with a full disk refuses a newline that joins two /tmp paths, only the character set catches",
     lambda: cd_refused_check("disk-rm-newline-joined", CD_FULL, "disk", CD_RM_NEWLINE_JOINED, "rmnljoin")),
    ("compaction-audit: an owed audit with a full disk refuses an rm -rf whose joined < only the character set catches",
     lambda: cd_refused_check("disk-rm-lt-joined", CD_FULL, "disk", CD_RM_LT_JOINED, "rmltjoin")),
    ("compaction-audit: an owed audit with a disk that is busy but not full refuses the sweep (the spawn passes busy)",
     lambda: cd_refused_check("disk-busy", CD_BUSY, "pass", CD_SWEEP, "busy")),
    ("compaction-audit: an owed audit with a fine disk refuses the sweep, so nothing changes",
     lambda: cd_refused_check("disk-fine", CD_FINE, "pass", CD_SWEEP, "fine")),
    ("compaction-audit: an owed audit with memory full and a fine disk refuses the sweep (the brake refuses for memory)",
     lambda: cd_refused_check("disk-memory", CD_MEMORY_FULL, "memory", CD_SWEEP, "memory")),
    ("compaction-audit: with no audit owed, a Bash call under a full disk is allowed and reads no load",
     cd_quiet_check),
)
FIXTURELESS_CHECKS.update(check for _label, check in CD_CHECKS)   # each builds its own folders, no lazy fixture
LOG_CHECKS = LOG_CHECKS + CD_CHECKS
for _label, _check in CD_CHECKS:
    LOG_FAMILY[_label] = FAMILY

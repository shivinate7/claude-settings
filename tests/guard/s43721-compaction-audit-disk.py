# section 43721
FAMILY = "compaction-audit"
# The audit owes one Audit: spawn. The load brake refuses that spawn at a full disk (free under the smaller of 5% of the
# disk and 5 GB), so a session on a full disk could neither spawn the audit nor run the shell call that frees the disk:
# a deadlock. These cases hold the exemption: while the audit is owed
# AND the brake refuses the audit spawn for disk, compaction-audit lets through each disk-cleanup shell call (the janitor
# sweep, or rm -rf of an absolute /tmp path). Every other shell call stays refused. The cleanup clears nothing: the audit
# stays owed. A disk that is not full, or memory that is full, changes nothing: a sweep frees disk, not memory.
# The helpers are the compaction-audit ones of section 43700 (ca_copy, ca_config, ca_owed, ca_env) and the load-brake
# probe of section 39497 (LB_PROBE, which patches read_load). Nothing here copies them.
# Double-quoted: bash strips an unquoted backslash, so a Windows REPO (D:\a\...) must arrive whole.
SWEEP_ROOT = '"%s"' % REPO
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
# The Windows sweep roots, as bash passes them to the sweep. Inside double quotes bash keeps each backslash, so a
# quoted drive path arrives whole. An unquoted backslash is stripped (D:\a\repo arrives as D:arepo), so it cannot work.
# A forward slash survives both ways, quoted or not.
CD_WIN_DQ_BS = r'"D:\a\repo"'
CD_WIN_DQ_FWD = '"D:/a/repo"'
CD_WIN_UQ_FWD = "D:/a/repo"
CD_WIN_UQ_BS = r"D:\a\repo"


def cd_sweep_root(root, confirm=False):
    """The attended fast sweep on `root`, spelled as the disk cleanup names it, with --confirm when `confirm`."""
    return "python3 ~/.claude/janitor/sweep.py --root %s --attended --fast%s" % (root, " --confirm" if confirm else "")


def cd_owed(name):
    """The audit owed: PostCompact sets the flags and the handoff's Read clears the reread flag, as ca_owed does.
    -> (folder, cfg, flag, why)."""
    folder = ca_copy("intact", drop_layout=False)
    cfg = ca_config(name + "-cfg", None)
    flag, why = ca_owed(folder, cfg)
    return folder, cfg, flag, why


def cd_run(folder, cfg, spec, tool, tool_input, tag, remote=False):
    """One call through the copy's guard, under LB_PROBE, with read_load answering spec["reading"]. The probe's temp
    folder sits in the config folder, and the remote-session id is stripped, so a lane-session read cannot change the
    count. remote=True runs it as a cloud session (CLAUDE_CODE_REMOTE=true). -> (run, side, why); run is None when
    the probe did not finish."""
    side_file = os.path.join(cfg, "probe-%s.json" % tag)
    temp = os.path.join(cfg, "tmp")
    os.makedirs(temp, exist_ok=True)
    env = ca_env(cfg)
    env.pop("CLAUDE_CODE_REMOTE_SESSION_ID", None)
    if remote:
        env["CLAUDE_CODE_REMOTE"] = "true"
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


def cd_brake(folder, cfg, reading, remote=False, tool_input=CA_AUDIT):
    """What the load brake says of the audit spawn under `reading`: (reason, matched). The probe's hit mode judges the
    call and runs nothing, so no audit flag moves. -> (pair, why)."""
    run, side, why = cd_run(folder, cfg, {"mode": "hit", "reading": reading}, "Agent", tool_input, "brake", remote)
    if why:
        return None, why
    hit = side.get("hit")
    if not isinstance(hit, list) or len(hit) != 2:
        return None, "the probe gave no load_hit pair: %r" % (hit,)
    return hit, ""


def cd_setup(name, reading, want, tool_input=CA_AUDIT):
    """The owed state, and a check that `reading` is the one the case names. The brake's verdict on the spawn
    `tool_input` under it must be `want`: "disk" (refused for disk), "memory" (refused for memory), "both" (refused
    for memory and for disk) or "pass" (let through). -> (folder, cfg, flag, why)."""
    folder, cfg, flag, why = cd_owed(name)
    if why:
        return None, None, None, why
    hit, why = cd_brake(folder, cfg, reading, tool_input=tool_input)
    if why:
        return None, None, None, "setup: " + why
    reason, matched = hit
    if want == "pass":
        ok = not reason
    elif want == "disk":
        ok = bool(reason) and "disk" in matched and "memory" not in matched
    elif want == "both":
        ok = bool(reason) and "disk" in matched and "memory" in matched
    else:
        ok = bool(reason) and "memory" in matched and "disk" not in matched
    if not ok:
        return None, None, None, ("setup: under this reading the load brake gives the audit spawn %r, want %s"
                                  % (matched or "no refusal", want))
    return folder, cfg, flag, ""


def cd_call(folder, cfg, reading, tool, tool_input, tag, remote=False):
    """One call of any tool through the copy's whole guard under `reading`, as the main session. -> (decision, reason,
    side, why). The one home of a guarded call in this section: cd_bash is the Bash form of it."""
    run, side, why = cd_run(folder, cfg, {"mode": "main", "reading": reading}, tool, tool_input, tag, remote)
    if why:
        return None, "", side, why
    decision, reason = _decision(run)
    return decision, reason, side, ""


def cd_bash(folder, cfg, reading, command, tag):
    """One Bash call under `reading`. -> (decision, reason, side, why)."""
    return cd_call(folder, cfg, reading, "Bash", {"command": command}, tag)


# THE AUDIT SPAWN AT A FULL MEMORY. A pending audit must be able to clear when memory is over 95%: its spawn is the one
# call that clears it, and a recovery control must not depend on the state it recovers (verification-recovery-independent-of-state).
# The spawn is judged by the whole guard, so these cases hold wherever the exemption is placed.
def cd_spawn_allowed_check(name, reading, label):
    """The Audit: spawn while the audit is owed, as the whole guard judges it under `reading`: allowed."""
    folder, cfg, _flag, why = cd_owed(name)
    if why:
        return False, why
    decision, reason, _side, why = cd_call(folder, cfg, reading, "Agent", CA_AUDIT, name)
    if why:
        return False, why
    problem = ov_want(decision, reason, "allow", "compaction-audit")
    if problem:
        return False, "the Audit: spawn was not allowed while the audit is owed, %s: %s" % (label, problem)
    return True, "the Audit: spawn is allowed while the audit is owed, %s" % label


def cd_spawn_clears_check(name, reading, label):
    """The Audit: spawn under `reading` clears the audit flag, so the audit is no longer owed."""
    folder, cfg, flag, why = cd_owed(name)
    if why:
        return False, why
    decision, reason, _side, why = cd_call(folder, cfg, reading, "Agent", CA_AUDIT, name)
    if why:
        return False, why
    if os.path.isfile(flag):
        return False, "the audit flag is still set after the Audit: spawn, %s (decision %s: %s)" % (
            label, decision, reason[:70])
    return True, "the Audit: spawn clears the audit flag, %s" % label


def cd_spawn_then_bash_check(name, reading, label):
    """After the Audit: spawn passes under `reading`, an ordinary Bash call is allowed: the owed audit no longer holds
    the session, so the call that frees memory can run."""
    folder, cfg, _flag, why = cd_owed(name)
    if why:
        return False, why
    _decision1, _reason1, _side1, why = cd_call(folder, cfg, reading, "Agent", CA_AUDIT, name)
    if why:
        return False, why
    decision, reason, _side2, why = cd_bash(folder, cfg, reading, CD_ORDINARY, name + "-after")
    if why:
        return False, why
    problem = ov_want(decision, reason, "allow", "compaction-audit")
    if problem:
        return False, "after the Audit: spawn, an ordinary Bash call was not allowed, %s: %s" % (label, problem)
    return True, "after the Audit: spawn, an ordinary Bash call is allowed, %s" % label


# THE AUDIT SPAWN AT A FULL DISK AND AT A BUSY MEMORY (decision machine-load-brake). The owed audit's own Audit: spawn is
# refused at a full disk: the cleanup frees the disk first, and the spawn is not the cleanup. A busy memory refusal of a
# background spawn stands: the memory exemption is for Full memory only.
CA_AUDIT_BG = dict(CA_AUDIT, run_in_background=True)
CD_BOTH = {"memory_pct": 96.0, "disk_free_gb": 3.0, "disk_total_gb": 926.0}
CD_BUSY_MEMORY = {"memory_pct": 90.0, "disk_free_gb": 500.0, "disk_total_gb": 926.0}


def cd_spawn_refused_check(name, reading, want, tool_input, label):
    """The owed audit's Audit: spawn under `reading` is refused by load-brake, and the refusal leaves the audit owed.
    `want` is the brake's verdict the case holds (see cd_setup)."""
    folder, cfg, flag, why = cd_setup(name, reading, want, tool_input)
    if why:
        return False, why
    decision, reason, _side, why = cd_call(folder, cfg, reading, "Agent", tool_input, name)
    if why:
        return False, why
    problem = ov_want(decision, reason, "deny", "load-brake")
    if problem:
        return False, "the Audit: spawn was not refused by load-brake, %s: %s" % (label, problem)
    if not os.path.isfile(flag):
        return False, "the refused Audit: spawn cleared the audit flag, %s" % label
    return True, "the Audit: spawn is refused by load-brake and the audit stays owed, %s" % label


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


def cd_remedy_check():
    """The cloud disk-full refusal names the sweep, and its --root is double-quoted, so a Windows shell passes a drive
    root whole. Read through the load brake's own hit, as a cloud session at a full disk."""
    folder = ca_copy("intact", drop_layout=False)
    cfg = ca_config("disk-remedy-cfg", None)
    hit, why = cd_brake(folder, cfg, CD_FULL, remote=True)
    if why:
        return False, why
    reason, matched = hit
    if "disk" not in matched:
        return False, "as a cloud session at a full disk, the load brake did not refuse the Agent start for disk: %r" % (matched,)
    if "sweep.py" not in reason:
        return False, "the cloud disk-full refusal names no sweep command, so it shows no --root to quote"
    if not re.search(r'--root "[^"\s]+"', reason):
        return False, "the cloud disk-full refusal shows the sweep --root unquoted, which a Windows shell strips"
    return True, "the cloud disk-full refusal shows the sweep with a double-quoted --root"


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
    ("compaction-audit: an owed audit with a full disk lets the sweep preview through on a double-quoted backslash drive root",
     lambda: cd_allowed_check("win-dq-bs-preview", CD_FULL, cd_sweep_root(CD_WIN_DQ_BS), "wdqbs")),
    ("compaction-audit: an owed audit with a full disk lets the sweep --confirm through on a double-quoted backslash drive root",
     lambda: cd_allowed_check("win-dq-bs-confirm", CD_FULL, cd_sweep_root(CD_WIN_DQ_BS, True), "wdqbsc")),
    ("compaction-audit: an owed audit with a full disk lets the sweep preview through on a double-quoted forward-slash drive root",
     lambda: cd_allowed_check("win-dq-fwd-preview", CD_FULL, cd_sweep_root(CD_WIN_DQ_FWD), "wdqfwd")),
    ("compaction-audit: an owed audit with a full disk lets the sweep --confirm through on a double-quoted forward-slash drive root",
     lambda: cd_allowed_check("win-dq-fwd-confirm", CD_FULL, cd_sweep_root(CD_WIN_DQ_FWD, True), "wdqfwdc")),
    ("compaction-audit: an owed audit with a full disk lets the sweep preview through on an unquoted forward-slash drive root",
     lambda: cd_allowed_check("win-uq-fwd-preview", CD_FULL, cd_sweep_root(CD_WIN_UQ_FWD), "wuqfwd")),
    ("compaction-audit: an owed audit with a full disk lets the sweep --confirm through on an unquoted forward-slash drive root",
     lambda: cd_allowed_check("win-uq-fwd-confirm", CD_FULL, cd_sweep_root(CD_WIN_UQ_FWD, True), "wuqfwdc")),
    ("compaction-audit: an owed audit with a full disk refuses the sweep preview on an unquoted backslash drive root, which bash strips",
     lambda: cd_refused_check("win-uq-bs-preview", CD_FULL, "disk", cd_sweep_root(CD_WIN_UQ_BS), "wuqbs")),
    ("compaction-audit: an owed audit with a full disk refuses the sweep --confirm on an unquoted backslash drive root, which bash strips",
     lambda: cd_refused_check("win-uq-bs-confirm", CD_FULL, "disk", cd_sweep_root(CD_WIN_UQ_BS, True), "wuqbsc")),
    ("compaction-audit: an owed audit with a full disk refuses the sweep on a double-quoted backslash drive root with a $( ) inside",
     lambda: cd_refused_check("win-dq-bs-subst", CD_FULL, "disk", cd_sweep_root(r'"D:\a\$(id)"'), "wdqsub")),
    ("compaction-audit: an owed audit with a full disk refuses the sweep on a double-quoted backslash drive root chained with ;",
     lambda: cd_refused_check("win-dq-bs-semi", CD_FULL, "disk",
                              cd_sweep_root(CD_WIN_DQ_BS) + ";rm -rf /tmp/claude-disk-cleanup/run-2", "wdqsemi")),
    ("compaction-audit: the cloud disk-full refusal shows the sweep with a double-quoted --root, so a Windows shell keeps its backslashes",
     cd_remedy_check),
    ("compaction-audit: an owed audit at memory over 95% and a fine disk lets the Audit: spawn through",
     lambda: cd_spawn_allowed_check("spawn-mem-allowed", CD_MEMORY_FULL, "at memory 96% and a fine disk")),
    ("compaction-audit: an Audit: spawn that passes at memory over 95% clears the audit flag",
     lambda: cd_spawn_clears_check("spawn-mem-clears", CD_MEMORY_FULL, "at memory 96% and a fine disk")),
    ("compaction-audit: after an Audit: spawn that passes at memory over 95%, an ordinary Bash call is allowed",
     lambda: cd_spawn_then_bash_check("spawn-mem-bash", CD_MEMORY_FULL, "at memory 96% and a fine disk")),
    ("compaction-audit: control, an owed audit at memory 40% lets the Audit: spawn through and clears the flag",
     lambda: cd_spawn_clears_check("spawn-fine", CD_FINE, "at memory 40% and a fine disk")),
    ("compaction-audit: an owed Audit: spawn at a full disk is refused by load-brake, and the audit stays owed",
     lambda: cd_spawn_refused_check("spawn-disk", CD_FULL, "disk", CA_AUDIT, "at memory 40% and a full disk")),
    ("compaction-audit: an owed Audit: spawn at a full memory and a full disk is refused by load-brake, and the audit stays owed",
     lambda: cd_spawn_refused_check("spawn-both", CD_BOTH, "both", CA_AUDIT, "at memory 96% and a full disk")),
    ("compaction-audit: an owed Audit: spawn at a busy memory with run_in_background true is refused by load-brake, as on main",
     lambda: cd_spawn_refused_check("spawn-busy-bg", CD_BUSY_MEMORY, "memory", CA_AUDIT_BG,
                                    "at memory 90% busy, run_in_background true")),
)
FIXTURELESS_CHECKS.update(check for _label, check in CD_CHECKS)   # each builds its own folders, no lazy fixture
LOG_CHECKS = LOG_CHECKS + CD_CHECKS
for _label, _check in CD_CHECKS:
    LOG_FAMILY[_label] = FAMILY

# section 8728
FAMILY = "push-delete"

# Rule archive-push-gates-delete. A delete of a remote branch that follows an archive push of that branch runs
# only when `&&` joins them, so the push's own exit status gates it. A `;`, a bare newline, `||`, or a pipe on the push
# hides or breaks that status, so each is refused. A line break after `&&` is still that join: the shell reads
# the next line as the rest of the chain, and a backslash-newline is one too. An archive push from `HEAD` or `@`
# pairs `<name>` and `<name>` without a `-N` suffix, for `archive/<name>`. An archive push from an explicit branch (`feat-2`, `origin/feat`)
# pairs only that branch, minus `origin/`. `${b}` and `$b` are one name. An empty archive name pairs nothing and
# must not crash the guard: a crash fails open for the whole command, so a gate after it never runs.
ARCHIVE_GATE_RULE = "archive-push-gates-delete"
ARCHIVE_GATE_REMEDY = "&&"
ARCHIVE_GATE_PUSH = VCS + " push origin HEAD:archive/feat"
ARCHIVE_GATE_REF_PUSH = VCS + " push origin feat:refs/heads/archive/feat"
ARCHIVE_GATE_DELETE = VCS + " push --delete origin feat"
ARCHIVE_GATE_COLON_DELETE = VCS + " push origin :feat"
ARCHIVE_EMPTY_NAME = VCS + " push origin HEAD:archive/ ; " + VCS + " push origin --delete feat"


def archive_gate_refused(name, command):
    """One refusal: the delete after the archive push is not gated by `&&`, so the deny names the rule and `&&`."""
    sh("push: " + name, command, "deny", ARCHIVE_GATE_RULE, cwd=PUSHFEAT, carries=ARCHIVE_GATE_REMEDY)


def archive_gate_allowed(name, command):
    """One control: an allow that must print nothing."""
    sh("push: " + name, command, "allow", cwd=PUSHFEAT, silent=True)


archive_gate_refused("archive push, then --delete joined by ; is refused",
                     ARCHIVE_GATE_PUSH + "; " + ARCHIVE_GATE_DELETE)
archive_gate_refused("archive push, then :feat joined by ; is refused",
                     ARCHIVE_GATE_PUSH + "; " + ARCHIVE_GATE_COLON_DELETE)
archive_gate_refused("archive push piped to tail, then --delete joined by ; is refused",
                     ARCHIVE_GATE_PUSH + " | tail; " + ARCHIVE_GATE_DELETE)
archive_gate_refused("archive push piped to tail, then --delete joined by && is refused: && gates tail's status",
                     ARCHIVE_GATE_PUSH + " | tail && " + ARCHIVE_GATE_DELETE)
archive_gate_refused("archive push, then --delete joined by || is refused",
                     ARCHIVE_GATE_PUSH + " || " + ARCHIVE_GATE_DELETE)
archive_gate_refused("archive push on one line, --delete on the next line is refused",
                     ARCHIVE_GATE_REF_PUSH + "\n" + ARCHIVE_GATE_DELETE)
archive_gate_refused("archive push, &&, echo, then --delete joined by ; is refused: the ; after the gate counts",
                     ARCHIVE_GATE_PUSH + " && echo done; " + ARCHIVE_GATE_DELETE)
archive_gate_refused("archive push, ;, echo, then --delete joined by && is refused: the ; before the echo counts",
                     ARCHIVE_GATE_PUSH + "; echo done && " + ARCHIVE_GATE_DELETE)
archive_gate_refused("archive push, ;, a quoted apostrophe, then --delete is refused",
                     ARCHIVE_GATE_PUSH + '; echo "don\'t"; ' + ARCHIVE_GATE_DELETE)
archive_gate_refused("archive push, ;, a quoted hash, then --delete is refused",
                     ARCHIVE_GATE_PUSH + '; echo "# x"; ' + ARCHIVE_GATE_DELETE)
archive_gate_refused("loop body: archive push piped to tail, then --delete joined by ; is refused",
                     "for _ in 1; do " + ARCHIVE_GATE_PUSH + " | tail -1; " + ARCHIVE_GATE_DELETE + "; done")
archive_gate_refused("loop: archive push to ${b}, then --delete of $b joined by ; is refused: ${b} and $b are one name",
                     'for b in a; do ' + VCS + ' push origin "${b}:refs/heads/archive/${b}" 2>&1 | tail -1; '
                     + VCS + ' push origin --delete "$b"; done')
archive_gate_refused("archive push to the taken name archive/feat-2, then --delete feat joined by ; is refused",
                     VCS + " push origin HEAD:refs/heads/archive/feat-2 | tail -1; " + ARCHIVE_GATE_DELETE)
archive_gate_refused("archive push from origin/feat to the taken name archive/feat-2, then --delete feat is refused",
                     VCS + " push origin origin/feat:refs/heads/archive/feat-2 | tail -1; " + ARCHIVE_GATE_DELETE)
archive_gate_refused("incident loop: origin/$b archive push piped to tail, then --delete of $b after ; is refused",
                     'for b in a; do ' + VCS + ' push origin "origin/$b:refs/heads/archive/$b" 2>&1 | tail -1; '
                     + VCS + ' push origin --delete $b; done')

archive_gate_allowed("archive push, then --delete joined by && is allowed",
                     ARCHIVE_GATE_PUSH + " && " + ARCHIVE_GATE_DELETE)
archive_gate_allowed("archive push, then :feat joined by && is allowed",
                     ARCHIVE_GATE_REF_PUSH + " && " + ARCHIVE_GATE_COLON_DELETE)
archive_gate_allowed("archive push, && echo with a quoted ;, then --delete is allowed: the quoted ; is text",
                     ARCHIVE_GATE_PUSH + ' && echo "a; b" && ' + ARCHIVE_GATE_DELETE)
archive_gate_allowed("loop body: archive push, then --delete joined by && is allowed",
                     "for _ in 1; do " + ARCHIVE_GATE_PUSH + " && " + ARCHIVE_GATE_DELETE + "; done")
archive_gate_allowed("archive push to archive/feat with 2>&1, then --delete joined by && is allowed",
                     VCS + " push origin HEAD:archive/feat 2>&1 && " + ARCHIVE_GATE_DELETE)
archive_gate_allowed("archive push to the taken name archive/feat-2 with 2>&1, then --delete joined by && is allowed",
                     VCS + " push origin HEAD:archive/feat-2 2>&1 && " + ARCHIVE_GATE_DELETE)
archive_gate_allowed("a delete with no archive push before it is allowed",
                     ARCHIVE_GATE_DELETE)
archive_gate_allowed("a plain push, then --delete joined by ; is allowed: no archive push, so no gate",
                     VCS + " push origin HEAD:lane/x; " + ARCHIVE_GATE_DELETE)

# A line break after `&&` joins the chain as `&&` does: the shell runs the next line as the rest of the chain, so
# the push's status still gates the delete. Each allow is its known-green twin above with the break for the space.
# A backslash-newline is one command to the shell, so it is a control. A bare newline, or a `;` before the break,
# has no `&&` in front of it, so it is refused.
archive_gate_allowed("archive push, && at the line end, then --delete on the next line is allowed",
                     ARCHIVE_GATE_PUSH + " &&\n" + ARCHIVE_GATE_DELETE)
archive_gate_allowed("archive push to archive/feat with 2>&1 and && at the line end, then --delete on the next line is allowed",
                     VCS + " push origin HEAD:archive/feat 2>&1 &&\n" + ARCHIVE_GATE_DELETE)
archive_gate_allowed("archive push, && and a backslash-newline, then --delete on the next line is allowed",
                     ARCHIVE_GATE_PUSH + " && \\\n" + ARCHIVE_GATE_DELETE)
archive_gate_refused("archive push, then a bare newline, then --delete is refused: no && joins them",
                     ARCHIVE_GATE_PUSH + "\n" + ARCHIVE_GATE_DELETE)
archive_gate_refused("archive push, ; at the line end, then --delete on the next line is refused",
                     ARCHIVE_GATE_PUSH + " ;\n" + ARCHIVE_GATE_DELETE)

# Explicit source, and an empty archive name. An explicit source is the branch pushed, so the taken name
# `archive/feat-2` pairs only `feat-2`, and `feat` is free. An empty name (`HEAD:archive/`) pairs nothing. A crash
# in the pairing fails open for the whole command and allows silently, as a plain delete does, so a verdict alone
# cannot show it: the deny after the empty name shows the gate that the crash would skip, and the log check reads
# the crash line.
archive_gate_allowed("archive push to an empty name, then --delete feat joined by ; is allowed",
                     ARCHIVE_EMPTY_NAME)
archive_gate_refused("archive push to an empty name, then archive/feat, then --delete feat joined by ; is refused",
                     VCS + " push origin HEAD:archive/ ; " + VCS + " push origin HEAD:archive/feat ; "
                     + VCS + " push origin --delete feat")
archive_gate_allowed("archive push feat-2 to archive/feat-2 joined by &&, then --delete feat joined by ; is allowed",
                     VCS + " push origin feat-2:archive/feat-2 && " + VCS + " push origin --delete feat-2; "
                     + VCS + " push origin --delete feat")
archive_gate_refused("archive push from origin/feat to archive/feat-2, then --delete feat joined by ; is refused",
                     VCS + " push origin origin/feat:archive/feat-2 ; " + VCS + " push origin --delete feat")
archive_gate_allowed("archive push from origin/feat to archive/feat-2, then --delete feat-2 joined by ; is allowed",
                     VCS + " push origin origin/feat:archive/feat-2 ; " + VCS + " push origin --delete feat-2")
archive_gate_refused("archive push from @ to archive/feat-2, then --delete feat joined by ; is refused",
                     VCS + " push origin @:archive/feat-2 ; " + VCS + " push origin --delete feat")


def _archive_run(folder, command):
    """decide() on one Bash command from PUSHFEAT, with the guard's config, and so its guard.log, in folder."""
    return decide({"raw": None, "tool": "Bash", "tool_input": {"command": command}, "cwd": PUSHFEAT,
                   "session": None, "env_path": None, "config": folder, "agent_id": None,
                   "transcript": None, "agent_type": None, "event": None, "stop_active": False,
                   "no_root": False, "env": None, "temp": TEMP_DIR, "max_seconds": None, "guard": None})


def archive_empty_name_log_case():
    """The empty archive name writes no `crash` line. A refusal lands in the folder's guard.log first, so the
    log is the one the run writes (scope); then the empty-name command is a silent allow with no crash row."""
    folder = os.path.join(ROOT, "archive-empty-name")
    os.makedirs(folder, exist_ok=True)
    path = os.path.join(folder, "guard.log")
    if os.path.exists(path):
        os.remove(path)
    marker, _ = _archive_run(folder, "pkill -f node")   # a deny: one logged line
    rows = _session_log_rows(folder) or []
    if marker != "deny" or not rows or rows[0].split("\t")[2:3] != ["deny"]:
        return False, "scope: the refusal marker did not land in the folder's guard.log"
    got, reason = _archive_run(folder, ARCHIVE_EMPTY_NAME)
    if got != "allow" or reason:
        return False, "expected a silent allow, got %s %r" % (got, reason[:80])
    crashes = [row for row in _session_log_rows(folder) or []
               if row.split("\t")[2:4] == ["crash", "guard-crash"]]
    if crashes:
        error = " ".join(crashes[0].split("\t")[4:])
        return False, "the guard crashed on the empty archive name: %s" % error[:120]
    return True, "a silent allow and no crash line"


# Registered in section 35537, the first push-delete section after LOG_CHECKS_EXTRA exists (section 21304).

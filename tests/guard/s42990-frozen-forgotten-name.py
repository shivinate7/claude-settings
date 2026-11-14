# section 42990
FAMILY = "frozen"
#
# A name the command sets to a value the guard cannot read (`D=$(mktemp -d)`, a backtick form, `D=(a b)`) is kept as
# None. An unquoted redirect target that takes a default word over that name, with no IFS in the table, reaches `known`
# in hooks/guard_frozen.py, which runs `_TWO_WORDS.search(None)`: a TypeError. The guard fails open, so the call is
# allowed, and the only sign is a `crash` line in the guard.log of that run. An allow case that reads the verdict alone
# passes on that crash, so each case here reads the log too. The crash line is named first.
#
# The RED cases expect allow: a name the guard cannot read keeps its default word as written, per decision
# frozen-path-resolves-shell-vars.
#
# CONTROLS. Each passes on the old commit. A quoted target, or a name with a known value, takes no crash path. A write
# to the config folder, literal or through a known value of the word, is refused, so WORD_DIR is frozen.

WORD_DIR = os.path.join(ROOT, "fz-word")   # the config folder of the word cases: the word names it, so it is frozen


def _fz_run(folder, command, env=None):
    """One guard run on `command`, with `folder` as its config folder and guard.log. Returns (decision, reason, the
    guard.log rows of the run, the error of each crash line of the run)."""
    os.makedirs(folder, exist_ok=True)
    if os.path.exists(os.path.join(folder, "guard.log")):
        os.remove(os.path.join(folder, "guard.log"))
    decision, reason = decide({"raw": None, "tool": "Bash", "cwd": NOGIT, "session": None, "env_path": None,
                               "config": folder, "env": env, "tool_input": {"command": command}})
    rows = [line.split("\t") for line in _guard_log_lines(folder)]
    crashes = [row[4] if len(row) > 4 else "" for row in rows if row[2:4] == ["crash", "guard-crash"]]
    return decision, reason or "", rows, crashes


FORGOTTEN_CHECKS = []   # (label, check) of this section, joined to LOG_CHECKS below


def _fz_check(label, folder, command, want, rule=None, env=None):
    """Add one log check: a guard run on `command` under `folder`. The run's guard.log must hold a `rule` line when
    `rule` is given, which shows the check reads the log the guard writes. Then a crash line fails the check, named as
    the crash. Then the verdict must be `want`."""
    def check():
        decision, reason, rows, crashes = _fz_run(folder, command, env)
        if rule and not any(len(row) > 3 and row[3] == rule for row in rows):
            return False, "no %s line in the guard.log of the run" % rule
        if crashes:
            return False, "guard crashed: %s" % crashes[0]
        if decision != want:
            return False, "want %s, got %s: %s" % (want, decision, reason[:120])
        return True, "%s, and no crash line" % decision
    FORGOTTEN_CHECKS.append((label, check))


# RED. A default word over a name the command set to a value the guard cannot read. Each crashes on the old commit.
_fz_check("frozen: forgotten name: D=$(mktemp -d), an unquoted write to ${D:-/tmp/w}/f is allowed, no crash",
          os.path.join(ROOT, "fz-dollar"), 'D=$(mktemp -d); echo x > ${D:-/tmp/w}/f', "allow")
_fz_check("frozen: forgotten name: D set by backticks, an unquoted write to ${D:-/tmp/w}/f is allowed, no crash",
          os.path.join(ROOT, "fz-backtick"), 'D=`mktemp -d`; echo x > ${D:-/tmp/w}/f', "allow")
_fz_check("frozen: forgotten name: D=(a b), an unquoted write to ${D:-/tmp/w}/f is allowed, no crash",
          os.path.join(ROOT, "fz-array"), 'D=(a b); echo x > ${D:-/tmp/w}/f', "allow")
_fz_check("frozen: forgotten name: D=$(mktemp -d), an unquoted append to ${D:?}/f is allowed, no crash",
          os.path.join(ROOT, "fz-append"), 'D=$(mktemp -d); echo x >> ${D:?}/f', "allow")

# CONTROLS. Each passes on the old commit, and each differs from a red case by the one thing that makes the crash.
_fz_check("frozen: forgotten name control: D=$(mktemp -d), a quoted write to ${D:-/tmp/w}/f is allowed, no crash",
          os.path.join(ROOT, "fz-quoted"), 'D=$(mktemp -d); echo x > "${D:-/tmp/w}/f"', "allow")
_fz_check("frozen: known name control: D=/tmp/d, an unquoted write to ${D:-/tmp/w}/f is allowed, no crash",
          os.path.join(ROOT, "fz-known"), 'D=/tmp/d; echo x > ${D:-/tmp/w}/f', "allow")
_fz_check("frozen: forgotten name control: the config folder's hooks/guard.py written literally is refused, "
          "with a frozen-path line",
          WORD_DIR, 'printf x > "%s/hooks/guard.py"' % WORD_DIR, "deny", rule="frozen-path")
_fz_check("frozen: known name control: D set to the config folder, a write to ${D:-/tmp/w}/hooks/guard.py is refused, "
          "with a frozen-path line",
          WORD_DIR, 'D=%s; echo x > ${D:-/tmp/w}/hooks/guard.py' % WORD_DIR, "deny", rule="frozen-path")

# LOG_CHECKS_EXTRA joined LOG_CHECKS in section 40805, so these checks join LOG_CHECKS here, as section 42841 does.
for _label, _check in FORGOTTEN_CHECKS:
    LOG_FAMILY[_label] = FAMILY
    LOG_CHECKS = LOG_CHECKS + ((_label, _check),)

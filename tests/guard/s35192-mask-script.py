# section 35192
FAMILY = "mask-script"
FAMILIES["mask-script"] = "mask_script lexemes"

# The timing cases guard mask_script. Its earlier regex form could take each backslash after an
# unclosed quote as one `.` or as half of a `\\.` pair, so the paths grew like Fibonacci. Measured
# on that form: 30 backslashes 0.1 s, 38 about 4.9 s, 40 about 12.9 s. The child gets a 1 s limit,
# so a slow scan fails its case and never blocks the suite.
MASK_HANG_BACKSLASHES = 40
MASK_HANG_LIMIT_S = 1
MASK_PIN_LIMIT_S = 10

# Normal scripts with escaped quotes. Each one is well closed: its last quote is not escaped. The
# expected masks are the guard's own output today, so a change to any of them is a behavior change.
MASK_PINS = (
    (r'const a = "a\"b";', "const a = \x000\x00;", [r'a\"b']),
    (r"say('it\'s');", "say(\x000\x00);", [r"it\'s"]),
    (r'const t = `a\`b`;', "const t = \x000\x00;", [r'a\`b']),
    (r'const p = "a\\";', "const p = \x000\x00;", [r'a\\']),
    ('x = 1; // say "hi"\ny = 2;', "x = 1;  \ny = 2;", []),
    ('/* \'q\' */ z = "ok";', "  z = \x000\x00;", ["ok"]),
    ('f("a", \'b\')', "f(\x000\x00, \x001\x00)", ["a", "b"]),
    ('s = "line1\nline2";', "s = \x000\x00;", ["line1\nline2"]),
    ("// don't\nf('x')", " \nf(\x000\x00)", ["x"]),
    ('/* say "hi" */ f(\'x\')', "  f(\x000\x00)", ["x"]),
)

# A quote left open, then 64 KB of escaped quotes. The lexeme must stay linear on this shape.
MASK_LONG_SCRIPT = '"' + '\\"' * 32768


def mask_child(scripts, limit):
    """Run guard.mask_script on each script in a child process. Return (answers, note).

    The whole child run has `limit` seconds. A run that outlives it returns (None, note), which
    fails its case and never blocks the suite.
    """
    code = ("import json, importlib.util as u\n"
            "s = u.spec_from_file_location('g', %r)\n"
            "g = u.module_from_spec(s)\n"
            "s.loader.exec_module(g)\n"
            "print(json.dumps([list(g.mask_script(x)) for x in %r]))\n" % (GUARD, list(scripts)))
    try:
        # The program goes on stdin, not in argv: Windows caps argv at 32 KB (WinError 206),
        # and a 64 KB case script alone makes the command line about 98 KB.
        got = subprocess.run([sys.executable, "-"], input=code, capture_output=True, text=True,
                             timeout=limit)
    except subprocess.TimeoutExpired:
        return None, "mask_script did not return within %d s" % limit
    if got.returncode != 0:
        return None, "child exited %d: %s" % (got.returncode, got.stderr.strip()[-160:])
    return json.loads(got.stdout), "returned"


def mask_hang_case(quote, name):
    script = quote + "\\" * MASK_HANG_BACKSLASHES

    def check():
        answers, note = mask_child([script], MASK_HANG_LIMIT_S)
        if answers is None:
            return False, note
        if answers != [[script, []]]:
            return False, "an unclosed %s quote was masked: %r" % (name, answers)
        return True, "unclosed %s quote, %d backslashes, returned within %d s" % (
            name, MASK_HANG_BACKSLASHES, MASK_HANG_LIMIT_S)

    return check


def mask_pin_case():
    want = [[text, strings] for _, text, strings in MASK_PINS]
    answers, note = mask_child([script for script, _, _ in MASK_PINS], MASK_PIN_LIMIT_S)
    if answers is None:
        return False, note
    for (script, _, _), got, exp in zip(MASK_PINS, answers, want):
        if got != exp:
            return False, "%r masked to %r, want %r" % (script, got, exp)
    return True, "%d normal scripts with escaped quotes masked as pinned" % len(want)


def mask_long_case():
    answers, note = mask_child([MASK_LONG_SCRIPT], MASK_HANG_LIMIT_S)
    if answers is None:
        return False, note
    if answers != [[MASK_LONG_SCRIPT, []]]:
        return False, "an unclosed quote over 64 KB was masked"
    return True, "unclosed quote then 64 KB of escaped quotes returned within 1 s"


LOG_CHECKS_EXTRA.append(("rm-var: the taint spellings name the literal path at the assigned-value "
                         "reader, never ${NAME:?}", rm_var_taint_reader_case))
LOG_CHECKS_EXTRA.append(("mask_script: unclosed double quote then 64 KB of escaped quotes "
                         "returns within 1 s", mask_long_case))
# F2, a memory bound. A 64 KB script of deeply nested closed templates must scan within 200 MB. The
# child sets RLIMIT_AS where the platform accepts it. macOS refuses that call (ValueError), so there
# the child's peak RSS is the bound. Non-posix hosts skip the case with a note: no resource module.
MASK_MEM_LIMIT_BYTES = 200 * 1024 * 1024
MASK_MEM_SCRIPT = "`${" * 13000 + "1" + "}`" * 13000  # 65001 bytes, every template closed


def mask_memory_case():
    try:
        import resource  # noqa: F401  posix only
    except ImportError:
        return SKIP, "skipped: no resource module on this host, RLIMIT_AS not checked"
    code = ("import json, resource, importlib.util as u\n"
            "try:\n"
            "    resource.setrlimit(resource.RLIMIT_AS, (%d, %d))\n"
            "    limit = 'RLIMIT_AS'\n"
            "except (ValueError, OSError):\n"
            "    limit = 'peak RSS'\n"
            "s = u.spec_from_file_location('g', %r)\n"
            "g = u.module_from_spec(s)\n"
            "s.loader.exec_module(g)\n"
            "g.mask_script(%r)\n"
            "rss = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss\n"
            "print(json.dumps([limit, rss]))\n"
            % (MASK_MEM_LIMIT_BYTES, MASK_MEM_LIMIT_BYTES, GUARD, MASK_MEM_SCRIPT))
    try:
        got = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True,
                             timeout=60)
    except subprocess.TimeoutExpired:
        return False, "mask_script on the nested templates did not finish within 60 s"
    if got.returncode != 0:
        return False, "mask_script failed under the memory bound: %s" % got.stderr.strip()[-160:]
    limit, rss = json.loads(got.stdout)
    # ru_maxrss is bytes on darwin and kilobytes elsewhere.
    peak = rss if sys.platform == "darwin" else rss * 1024
    if peak > MASK_MEM_LIMIT_BYTES:
        return False, "peak %d MB, over the %d MB bound (%s)" % (
            peak // (1024 * 1024), MASK_MEM_LIMIT_BYTES // (1024 * 1024), limit)
    return True, "64 KB of nested templates scanned, peak under %d MB (%s)" % (
        MASK_MEM_LIMIT_BYTES // (1024 * 1024), limit)


LOG_CHECKS_EXTRA.append(("mask_script: 64 KB of nested closed templates stays under 200 MB",
                         mask_memory_case))
for quote, name in (('"', "double"), ("'", "single"), ("`", "backtick")):
    LOG_CHECKS_EXTRA.append(("mask_script: unclosed %s quote then backslashes returns within 1 s"
                             % name, mask_hang_case(quote, name)))
LOG_CHECKS_EXTRA.append(("mask_script: normal scripts with escaped quotes keep their masks",
                         mask_pin_case))


# Time bound (decision rm-on-a-variable-needs-a-guard): 2000 unclosed $( spans must be
# judged in under 2 s. The case goes through add(), so it has the same shape as every other case,
# then it is taken back out of CASES so the main loop does not judge it twice. The timer wraps the
# same decide() call the main loop uses.
RM_VAR_SLOW_CMD = 'a=$(' * 2000 + '; rm -rf "${a:?}"/x'
_slow_at = len(CASES)
add("rm-var: 2000 unclosed $( spans are judged in under 2 s", "deny", cwd=NOGIT,
    command=RM_VAR_SLOW_CMD)
RM_VAR_SLOW_CASE = CASES[_slow_at]
del CASES[_slow_at:]


def rm_var_slow_case():
    start = time.monotonic()
    decide(RM_VAR_SLOW_CASE)
    took = time.monotonic() - start
    if took >= 2.0:
        return False, "judged in %.2f s, not under 2 s" % took
    return True, "judged in %.2f s, under 2 s" % took


LOG_CHECKS_EXTRA.append(("rm-var: 2000 unclosed $( spans are judged in under 2 s",
                         rm_var_slow_case))


# In-process timing. guard.judge runs in this process and only its CPU time is read,
# so the reading is the guard's own work. A hook subprocess's CPU time is not this process's, so no
# subprocess is timed here. judge answers by printing one JSON block and exiting, so stdout is
# captured and SystemExit is caught. The guard's log goes under CLAUDE_CONFIG_DIR, pointed at the
# fixture config for the call and then restored.
def judge_in_process(command, cwd):
    """Return (decision, reason, CPU seconds) for one Bash call judged in this process."""
    materialize(cwd)
    guard = _load_guard_module()
    payload = {"tool_name": "Bash", "tool_input": {"command": command}, "cwd": cwd}
    printed = io.StringIO()
    saved = os.environ.get("CLAUDE_CONFIG_DIR")
    os.environ["CLAUDE_CONFIG_DIR"] = CFG
    try:
        started = time.process_time()
        try:
            with contextlib.redirect_stdout(printed):
                guard.judge(payload)
        except SystemExit:
            pass
        took = time.process_time() - started
    finally:
        if saved is None:
            os.environ.pop("CLAUDE_CONFIG_DIR", None)
        else:
            os.environ["CLAUDE_CONFIG_DIR"] = saved
    text = printed.getvalue().strip()
    if not text:
        return "allow", "", took
    block = json.loads(text)["hookSpecificOutput"]
    return block["permissionDecision"], block["permissionDecisionReason"], took


# Ratio bounds for the timing cases. The speed bound exists because the guard must finish inside its
# hook timeout (60 s, settings.json; decision guard-hooks-fail-closed). One
# wall-clock case stays live. An absolute bound flaked on busy
# runners, so each big case is judged in this process next to a small case of the same shape, one
# eighth of its size. Linear work takes about the scaled baseline, a ratio of 1. The quadratic
# slowdown takes about 8. The big case passes when its ratio stays under RM_VAR_K = 3, the geometric
# mean of 1 and 8, rounded up, which leaves a margin of about 2.7 on each side.
#
# Windows CPU time moves in 15.625 ms ticks, so a baseline of a few ticks reads off by 25% or more.
# So each side is tick_safe_mean: the mean of runs that together span RM_VAR_FLOOR seconds of CPU.
RM_VAR_K = 3
RM_VAR_REPEATS = 3
RM_VAR_FLOOR = 0.4       # CPU seconds one batch must span (25 ticks)
RM_VAR_BATCH_CAP = 100   # runs in one batch for a judge call; a clock that never moves ends as a FAIL


def tick_safe_mean(run_once, cap):
    """Return (ok, mean CPU per run, text). run_once() returns (ok, CPU seconds, text) for one run.

    Runs repeat until RM_VAR_FLOOR CPU seconds have passed, then the mean is returned. Too little CPU
    in `cap` runs is a named FAIL, so a clock that never moves never divides by zero.
    """
    total, runs = 0.0, 0
    while total < RM_VAR_FLOOR and runs < cap:
        ok, took, text = run_once()
        if not ok:
            return False, 0.0, text
        total += took
        runs += 1
    if total < RM_VAR_FLOOR:
        return False, 0.0, ("baseline spans %.3f s CPU in %d runs, under the %.2f s floor"
                            % (total, runs, RM_VAR_FLOOR))
    return True, total / runs, ""


def rm_var_batch(cmd, must, cwd=NOGIT, want="deny", cap=RM_VAR_BATCH_CAP):
    """Return tick_safe_mean of judging cmd in cwd. Every run must give `want` with a reason holding `must`.

    The reason is the rule name, so an empty `must` checks the verdict alone. `cap` bounds the runs.
    """
    def run_once():
        got, reason, took = judge_in_process(cmd, cwd)
        if got != want or must not in reason:
            return False, 0.0, "judged %s, not the expected %s" % (got, want)
        return True, took, ""
    return tick_safe_mean(run_once, cap)


def rm_var_ratio(make, small_n, big_n, must="rm-var-unguarded", cwd=NOGIT, want="deny",
                 cap=RM_VAR_BATCH_CAP):
    """Return (ok, text) for make(big_n) against make(small_n) scaled by big_n / small_n, judged in cwd.

    Every run must give the verdict `want`, so a case whose command is an allow passes want="allow".
    `cap` bounds the runs in each small batch.
    """
    small, big = [], []
    for _ in range(RM_VAR_REPEATS):
        ok, mean, text = rm_var_batch(make(small_n), must, cwd, want, cap)
        if not ok:
            return False, "small n=%d: %s" % (small_n, text)
        small.append(mean)
        got, reason, took = judge_in_process(make(big_n), cwd)
        if got != want or must not in reason:
            return False, "big n=%d judged %s, not the expected %s" % (big_n, got, want)
        big.append(took)
    size = big_n / small_n
    base = sum(small) / len(small)   # each batch mean is positive: it spans RM_VAR_FLOOR
    ratio = min(big) / (size * base)
    return ratio < RM_VAR_K, ("CPU ratio %.2f to the %dx-scaled baseline, bound %d (big %.2f s, "
                              "small mean %.3f s)" % (ratio, size, RM_VAR_K, min(big), base))


# Timing case: 4000 names, each bound to /tmp/a and then deleted through a glob under that name,
# are the rm-var refusal, and their CPU grows linearly. Each flagged delete re-reads the rest of the
# command for later bindings, so a re-read per delete grows as the square of the segments. The name
# must differ per segment: a repeated name has more than 64 values and is refused before that
# re-read, so it never reaches the slow path. A `$D/x` target is not in the flagged shape.
def rm_var_linear_cmd(n):
    return "".join("D%d=/tmp/a; rm -rf $D%d/*; " % (k, k) for k in range(n))


def rm_var_linear_case():
    return rm_var_ratio(rm_var_linear_cmd, 500, 4000)


LOG_CHECKS_EXTRA.append(("rm-var: 4000 bindings and 4000 flagged deletes scale linearly in CPU",
                         rm_var_linear_case))


# The 64000-binding limit: one delete after 64000 bindings, judged in CPU time of judge, whose
# split is cached once for a command of many repeated segments. The verdict is refused, and only the
# growth of the time is the point.
def rm_var_64000_cmd(n):
    return "A=x;" * n + " rm -rf $A/"


def rm_var_64000_case():
    return rm_var_ratio(rm_var_64000_cmd, 8000, 64000)


LOG_CHECKS_EXTRA.append(("rm-var: 64000 bindings before a delete scale linearly in CPU",
                         rm_var_64000_case))


# 4000 assignments and 4000 targets, with a bare pwd that taints every name, are denied. Judged in
# CPU, not the wall clock of a hook subprocess, which carries startup cost and runner load.
def rm_var_wide_cmd(n):
    return ("".join("D%d=/tmp/a%d; " % (k, k) for k in range(n))
            + "P=$(pwd); rm -rf " + " ".join('"$D%d"/*' % k for k in range(n)))


def rm_var_wide_case():
    return rm_var_ratio(rm_var_wide_cmd, 500, 4000, must="")


LOG_CHECKS_EXTRA.append(("rm-var: 4000 assignments and 4000 targets with pwd scale linearly in CPU",
                         rm_var_wide_case))


# The argv join reads each gap between quote pairs with ARGV_GAP. A run of spaces that ends in a
# non-gap character backtracks as the square of its length. The push is forced at both sizes, so the
# verdict stays deny and only the CPU ratio can fail. The label names no rm-var, so the family is set
# to push-delete for this one append and restored after it.
def argv_gap_cmd(n):
    return ('deno eval "new Deno.Command(\\"' + VCS + '\\", {args: [\\"push\\", \\"-f\\"' + " " * n
            + 'x, \\"origin\\", \\"x\\"]}).outputSync()"')


def argv_gap_case():
    return rm_var_ratio(argv_gap_cmd, 6000, 48000, must="", cwd=PUSHFEAT)


# A run of deno eval flags before a nested quote. Each `--a` has two parses in the flag pattern, one with
# `--` and one with `-`, so a failed match tries every split and its CPU doubles per flag. The command
# names no push, so it allows, and the ratio compares allow runs. The small side is 14 flags, about 4 ms a
# judge, so the default cap of 100 runs ends short of RM_VAR_FLOOR. The cap here is 1000.
def argv_flag_gap_cmd(n):
    return "deno eval " + "--a " * n + 'x "a \\"b\\""'


def argv_flag_gap_case():
    return rm_var_ratio(argv_flag_gap_cmd, 14, 20, must="", cwd=PUSHFEAT, want="allow", cap=1000)


_section_family = FAMILY

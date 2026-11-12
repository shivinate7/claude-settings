# section 43100
FAMILY = "slow-words"  # the family of the cases after this section

# --------------------------------------------------------------------------- the slow words
#
# The guard reads each word of a shell call as a possible path and resolves it with realpath, and
# realpath lstat-s every component of the path it resolves. A call of thousands of words therefore
# costs thousands of lstat calls, and a slow machine runs past the hook's time limit. The bound
# here is a cost bound, not a time bound: lstat calls per word, on average. A word may cost at most
# LSTAT_PER_WORD lstat calls. That covers the word's own leaf and a little more. The fixed allowance
# covers the guard's own reads, which do not grow with the words.
#
# Cases: 1, an in-process count on `_resolved` for SLOW_WORDS distinct relative words against one
# folder. 2a, the verdict of the full run, a green control. 2b, the lstat count of the full run,
# under a wrapper that counts os.lstat in the guard's own process. 3, verdict controls for `is_frozen`
# on symlinks, `.` and `..` leaves and missing leaves. Each control is green today and must stay green.

SLOW_WORDS = 2000       # distinct relative words in the in-process read (case 1)
SLOW_RUN_WORDS = 6000   # words in the full guard run (cases 2a and 2b)
LSTAT_PER_WORD = 3      # the bound: lstat calls per word, on average
LSTAT_FIXED = 500       # the bound's allowance for the guard's own reads
SLOW_ROOT = os.path.join(ROOT, "slow-words")
SLOW_BULK = os.path.join(SLOW_ROOT, "bulk")        # an empty folder: every word is a missing leaf
SLOW_PROJ = os.path.join(SLOW_ROOT, "proj")        # a project folder that holds the two links below
SLOW_CFG = os.path.join(SLOW_ROOT, "cfg")          # a config folder with one frozen file under hooks/
SLOW_GUARD_FILE = os.path.join(SLOW_CFG, "hooks", "guard.py")
SLOW_HOOKS_DIR = os.path.join(SLOW_CFG, "hooks")
SLOW_LEAF_LINK = os.path.join(SLOW_PROJ, "leaf-link")   # a symlink to SLOW_GUARD_FILE
SLOW_DIR_LINK = os.path.join(SLOW_PROJ, "hooks-link")   # a symlink to SLOW_HOOKS_DIR
SLOW_ECHO = "echo " + " ".join("word%d" % n for n in range(SLOW_RUN_WORDS))
NOT_LSTAT_PATH = "Windows resolves a path with one call, not one lstat per component, so this count does not measure the path reads here"
NO_TEMP = {"TMPDIR": None, "TEMP": None, "TMP": None}  # the full run reads the default temp folder
os.makedirs(SLOW_BULK, exist_ok=True)


def slow_fixtures():
    """Build the config folder and the two links once. False where this platform makes no symlink."""
    os.makedirs(SLOW_PROJ, exist_ok=True)
    os.makedirs(SLOW_HOOKS_DIR, exist_ok=True)
    if not os.path.exists(SLOW_GUARD_FILE):
        with open(SLOW_GUARD_FILE, "w", encoding="utf-8") as handle:
            handle.write("# a frozen file, read as text only\n")
    for link, target in ((SLOW_LEAF_LINK, SLOW_GUARD_FILE), (SLOW_DIR_LINK, SLOW_HOOKS_DIR)):
        if os.path.lexists(link):
            continue
        try:
            os.symlink(target, link, target_is_directory=os.path.isdir(target))
        except OSError:
            return False
    return True


def lstat_calls(run):
    """The number of os.lstat calls that `run()` makes, counted by wrapping os.lstat for that call only."""
    real = os.lstat
    count = [0]

    def counting(path, *args, **kwargs):
        count[0] += 1
        return real(path, *args, **kwargs)

    os.lstat = counting
    try:
        run()
    finally:
        os.lstat = real
    return count[0]


def join_log_check(label, check):
    """Join one log check to LOG_CHECKS. LOG_CHECKS_EXTRA joined in section 40805, before this section, so
    a check appended to it here would never run. This section joins LOG_CHECKS itself, as the late sections do.
    """
    global LOG_CHECKS
    LOG_FAMILY[label] = FAMILY
    LOG_CHECKS = LOG_CHECKS + ((label, check),)
    FIXTURELESS_CHECKS.add(check)


_SLOW_MODULES = []


def slow_modules():
    """(guard_core, guard_frozen) of the guard under test, loaded once for the checks of this section."""
    if not _SLOW_MODULES:
        _load_guard_module()
        _SLOW_MODULES.append((sys.modules.get("guard_core"), sys.modules.get("guard_frozen")))
    return _SLOW_MODULES[0]


# ---- case 1: the path read of one word, in process

def resolved_lstat_bound_check():
    """`_resolved` on SLOW_WORDS distinct relative words against one folder makes at most LSTAT_PER_WORD
    lstat calls per word, on average. Each word is a missing leaf in an empty folder, so the count is the
    cost of the path reads and nothing else.
    """
    if os.name == "nt":
        return SKIP, NOT_LSTAT_PATH
    core, _ = slow_modules()
    if not hasattr(core, "_resolved"):
        return False, "guard_core has no _resolved to read the words with"
    words = ["w%04d" % n for n in range(SLOW_WORDS)]
    calls = lstat_calls(lambda: [core._resolved(word, SLOW_BULK) for word in words])
    per_word = calls / float(SLOW_WORDS)
    if per_word > LSTAT_PER_WORD:
        return False, ("_resolved made %d lstat calls on %d words, %.1f per word, over the bound of %d per word"
                       % (calls, SLOW_WORDS, per_word, LSTAT_PER_WORD))
    return True, "_resolved made %.1f lstat calls per word, at most %d" % (per_word, LSTAT_PER_WORD)


join_log_check("slow words: _resolved makes at most 3 lstat calls per word on 2000 words",
               resolved_lstat_bound_check)


# ---- cases 2a and 2b: the full guard run on SLOW_RUN_WORDS words

sh("slow words: a 6000-word echo is allowed and prints nothing", SLOW_ECHO, "allow",
   cwd=SLOW_BULK, env=NO_TEMP, silent=True)

# The wrapper counts os.lstat in the guard's own process. It runs the guard file as __main__, so the
# guard reads stdin and sets its exit code as it does under Claude Code. The count goes to stderr.
SLOW_BOOT = """
import os, runpy, sys
guard = sys.argv[1]
calls = [0]
real = os.lstat
def counting(path, *args, **kwargs):
    calls[0] += 1
    return real(path, *args, **kwargs)
os.lstat = counting
sys.path.insert(0, os.path.dirname(guard))
sys.argv = [guard]
try:
    runpy.run_path(guard, run_name="__main__")
finally:
    sys.stderr.write("SLOW_LSTAT=%d\\n" % calls[0])
"""

_SLOW_RUN = []


def slow_full_run():
    """The guard run on the SLOW_RUN_WORDS-word echo, run once for case 2b."""
    if not _SLOW_RUN:
        payload = json.dumps({"tool_name": "Bash", "tool_input": {"command": SLOW_ECHO}, "cwd": SLOW_BULK})
        env = dict(os.environ, CLAUDE_CONFIG_DIR=CFG, CLAUDE_GUARD_ROOT_PID=str(os.getpid()))
        for name in ("TMPDIR", "TEMP", "TMP", "CLAUDE_CODE_REMOTE", "CLAUDE_CODE_SESSION_ID",
                     "CLAUDE_CODE_REMOTE_SESSION_ID", "CLAUDE_PROJECT_DIR"):
            env.pop(name, None)
        _SLOW_RUN.append(subprocess.run([sys.executable, "-c", SLOW_BOOT, GUARD], input=payload,
                                        capture_output=True, text=True, env=env, timeout=120))
    return _SLOW_RUN[0]


def slow_full_run_lstat_check():
    """The guard run on the SLOW_RUN_WORDS-word echo makes at most LSTAT_PER_WORD lstat calls per word,
    on average, plus LSTAT_FIXED for the guard's own reads.
    """
    if os.name == "nt":
        return SKIP, NOT_LSTAT_PATH
    done = slow_full_run()
    if done.returncode != 0:
        return False, "the guard exited %d on the echo: %s" % (done.returncode, done.stderr.strip()[-120:])
    found = re.search(r"^SLOW_LSTAT=(\d+)$", done.stderr, re.M)
    if not found:
        return False, "the lstat wrapper printed no count"
    calls = int(found.group(1))
    bound = LSTAT_PER_WORD * SLOW_RUN_WORDS + LSTAT_FIXED
    if calls > bound:
        return False, ("the %d-word echo made %d lstat calls, over the bound of %d"
                       % (SLOW_RUN_WORDS, calls, bound))
    return True, "the %d-word echo made %d lstat calls, within the bound of %d" % (SLOW_RUN_WORDS, calls, bound)


join_log_check("slow words: the 6000-word echo makes at most 3 lstat calls per word",
               slow_full_run_lstat_check)


# ---- case 3: verdict controls for `is_frozen`. Each one is green on the commit this section was written
# against, and each must stay green. The verdict is read through a config folder that this section builds.

def frozen_control(word, base, want, why):
    """A log check: `is_frozen(word, base)` is `want`, as it reads now. `why` names the reading the verdict rests on."""
    def check():
        if not slow_fixtures():
            return SKIP, "a symlink needs a privilege this platform does not hold, so this check does not run here"
        core, frozen = slow_modules()
        if frozen is None or core is None:
            return False, "guard_frozen or guard_core is not loaded"
        saved = core.config_dir
        core.config_dir = lambda: SLOW_CFG
        try:
            got = frozen.is_frozen(word, base)
        finally:
            core.config_dir = saved
        if got != want:
            return False, "is_frozen(%r) is %s, want %s: %s" % (word, got, want, why)
        return True, "is_frozen(%r) is %s: %s" % (word, want, why)

    join_log_check("slow words: is_frozen(%r) stays %s" % (word, want), check)


frozen_control("leaf-link", SLOW_PROJ, True,
               "a symlink leaf that points into the config folder is frozen, through the resolved reading")
frozen_control("hooks-link/guard.py", SLOW_PROJ, True,
               "a relative word through a symlinked folder reaches the frozen file")
frozen_control("hooks-link", SLOW_PROJ, False,
               "a word that is itself a symlink to a folder is that folder, and the folder is not frozen; its files are")
frozen_control("guard.py/.", SLOW_HOOKS_DIR, True,
               "a `.` leaf names the file itself")
frozen_control("guard.py/..", SLOW_HOOKS_DIR, False,
               "a `..` leaf names the folder above, which is not frozen")
frozen_control("no-such-file.py", SLOW_HOOKS_DIR, True,
               "a missing leaf under a frozen folder is frozen: the literal reading needs no file")
frozen_control("no-such.py", SLOW_PROJ, False,
               "a missing leaf outside the config folder is not frozen")

FAMILY = "misc"  # back to the default for any section below

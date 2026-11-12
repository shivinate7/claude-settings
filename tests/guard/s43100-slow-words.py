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
# on symlinks, `.` and `..` leaves and missing leaves. 4, `real_path` against `os.path.realpath` on the
# same words: green controls, a cache control, and a NUL leaf, which main reads as an error. 5, the
# lstat count of a shell call of CP_SOURCES `cp -s` link sources. 6, a Windows junction leaf, Windows
# only. Each control is green today and must stay green. Cases 4's NUL leaf and 5 are red today.

SLOW_WORDS = 2000       # distinct relative words in the in-process read (case 1)
SLOW_RUN_WORDS = 6000   # words in the full guard run (cases 2a and 2b)
CP_SOURCES = 1000       # `cp -s` link sources in one shell call (case 5)
LSTAT_PER_WORD = 3      # the bound: lstat calls per word, on average (per link source in case 5)
LSTAT_FIXED = 500       # the bound's allowance for the guard's own reads
SLOW_ROOT = os.path.join(ROOT, "slow-words")
SLOW_BULK = os.path.join(SLOW_ROOT, "bulk")        # an empty folder: every word is a missing leaf
SLOW_PROJ = os.path.join(SLOW_ROOT, "proj")        # a project folder that holds the links below
SLOW_CFG = os.path.join(SLOW_ROOT, "cfg")          # a config folder with one frozen file under hooks/
SLOW_GUARD_FILE = os.path.join(SLOW_CFG, "hooks", "guard.py")
SLOW_HOOKS_DIR = os.path.join(SLOW_CFG, "hooks")
SLOW_SUB_DIR = os.path.join(SLOW_HOOKS_DIR, "sub")      # a folder under the frozen hooks folder
SLOW_LEAF_LINK = os.path.join(SLOW_PROJ, "leaf-link")   # a symlink to SLOW_GUARD_FILE
SLOW_DIR_LINK = os.path.join(SLOW_PROJ, "hooks-link")   # a symlink to SLOW_HOOKS_DIR
SLOW_DANGLING = os.path.join(SLOW_PROJ, "dangling-link")  # a symlink to a path that is not there
SLOW_LOOP_A = os.path.join(SLOW_PROJ, "loop-a")         # a symlink loop: loop-a -> loop-b -> loop-a
SLOW_LOOP_B = os.path.join(SLOW_PROJ, "loop-b")
SLOW_JUNCTION = os.path.join(SLOW_PROJ, "junction-sub")  # a Windows junction to SLOW_SUB_DIR (case 6)
SLOW_ECHO = "echo " + " ".join("word%d" % n for n in range(SLOW_RUN_WORDS))
SLOW_CP = "; ".join("cp -s src%d dst%d" % (n, n) for n in range(CP_SOURCES))
NOT_LSTAT_PATH = "Windows resolves a path with one call, not one lstat per component, so this count does not measure the path reads here"
NO_LINK = "a symlink needs a privilege this platform does not hold, so this check does not run here"
NUL_LEAF = "guard.py\x00x"  # a NUL in a leaf: main's realpath raises ValueError on it
NO_TEMP = {"TMPDIR": None, "TEMP": None, "TMP": None}  # the full run reads the default temp folder
os.makedirs(SLOW_BULK, exist_ok=True)


def slow_fixtures():
    """Build the config folder and the links once. False where this platform makes no symlink."""
    os.makedirs(SLOW_PROJ, exist_ok=True)
    os.makedirs(SLOW_HOOKS_DIR, exist_ok=True)
    if not os.path.exists(SLOW_GUARD_FILE):
        with open(SLOW_GUARD_FILE, "w", encoding="utf-8") as handle:
            handle.write("# a frozen file, read as text only\n")
    links = ((SLOW_LEAF_LINK, SLOW_GUARD_FILE), (SLOW_DIR_LINK, SLOW_HOOKS_DIR),
             (SLOW_DANGLING, os.path.join(SLOW_ROOT, "missing")),
             (SLOW_LOOP_A, SLOW_LOOP_B), (SLOW_LOOP_B, SLOW_LOOP_A))
    for link, target in links:
        if os.path.lexists(link):
            continue
        try:
            os.symlink(target, link, target_is_directory=os.path.isdir(target))
        except OSError:
            return False
    return True


def remove_link(path):
    """Remove a link this section made: a directory link on Windows goes with rmdir, any other with unlink."""
    try:
        os.unlink(path)
    except OSError:
        os.rmdir(path)


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


def frozen_under_cfg(word, base):
    """`is_frozen(word, base)` with the config folder set to SLOW_CFG, which the controls read it with. The
    folder is restored after the read."""
    core, frozen = slow_modules()
    saved = core.config_dir
    core.config_dir = lambda: SLOW_CFG
    try:
        return frozen.is_frozen(word, base)
    finally:
        core.config_dir = saved


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

_SLOW_RUNS = {}


def guard_lstat_run(key, command, cwd):
    """The guard run on one shell call, under the lstat wrapper. Each key runs once; a check reads the result."""
    if key not in _SLOW_RUNS:
        payload = json.dumps({"tool_name": "Bash", "tool_input": {"command": command}, "cwd": cwd})
        env = dict(os.environ, CLAUDE_CONFIG_DIR=CFG, CLAUDE_GUARD_ROOT_PID=str(os.getpid()))
        for name in ("TMPDIR", "TEMP", "TMP", "CLAUDE_CODE_REMOTE", "CLAUDE_CODE_SESSION_ID",
                     "CLAUDE_CODE_REMOTE_SESSION_ID", "CLAUDE_PROJECT_DIR"):
            env.pop(name, None)
        _SLOW_RUNS[key] = subprocess.run([sys.executable, "-c", SLOW_BOOT, GUARD], input=payload,
                                         capture_output=True, text=True, env=env, timeout=120)
    return _SLOW_RUNS[key]


def lstat_bound_check(key, command, cwd, units, what):
    """The guard run on `command` makes at most LSTAT_PER_WORD lstat calls per unit, plus LSTAT_FIXED for the
    guard's own reads. `units` is what the command carries (words, or link sources); `what` names it in a message.
    """
    if os.name == "nt":
        return SKIP, NOT_LSTAT_PATH
    done = guard_lstat_run(key, command, cwd)
    if done.returncode != 0:
        return False, "the guard exited %d on the %s: %s" % (done.returncode, what, done.stderr.strip()[-120:])
    if done.stdout.strip():  # an allow prints nothing, so any output is a decision on the call
        return False, "the guard decided the %s, where an allow prints nothing: %s" % (what, done.stdout.strip()[:120])
    found = re.search(r"^SLOW_LSTAT=(\d+)$", done.stderr, re.M)
    if not found:
        return False, "the lstat wrapper printed no count"
    calls = int(found.group(1))
    bound = LSTAT_PER_WORD * units + LSTAT_FIXED
    if calls > bound:
        return False, "the %s made %d lstat calls, over the bound of %d" % (what, calls, bound)
    return True, "the %s made %d lstat calls, within the bound of %d" % (what, calls, bound)


def slow_full_run_lstat_check():
    """The guard run on the SLOW_RUN_WORDS-word echo makes at most LSTAT_PER_WORD lstat calls per word."""
    return lstat_bound_check("echo", SLOW_ECHO, SLOW_BULK, SLOW_RUN_WORDS, "%d-word echo" % SLOW_RUN_WORDS)


join_log_check("slow words: the 6000-word echo makes at most 3 lstat calls per word",
               slow_full_run_lstat_check)


# ---- case 3: verdict controls for `is_frozen`. Each one is green on the commit this section was written
# against, and each must stay green. The verdict is read through a config folder that this section builds.

def frozen_control(word, base, want, why):
    """A log check: `is_frozen(word, base)` is `want`, as it reads now. `why` names the reading the verdict rests on."""
    def check():
        if not slow_fixtures():
            return SKIP, NO_LINK
        core, frozen = slow_modules()
        if frozen is None or core is None:
            return False, "guard_frozen or guard_core is not loaded"
        got = frozen_under_cfg(word, base)
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


# ---- case 4: `real_path` against `os.path.realpath`. The controls are green on this branch: each pins a
# verdict the fast path keeps. The cache control and the NUL leaf are the same kind of check, the NUL leaf
# red until `real_path` reads it as main's realpath does.

def real_path_control(label, path, link, why):
    """A log check: `real_path(path)` is the normcase of `os.path.realpath(path)`. `link` is the link that
    `path` reads through, and it must be a link, so the check probes the case its label names."""
    def check():
        if not slow_fixtures():
            return SKIP, NO_LINK
        core = slow_modules()[0]
        if not os.path.islink(link):
            return False, "%s is not a link, so the fixture does not reach the case: %s" % (link, why)
        if not hasattr(core, "real_path"):
            return False, "guard_core has no real_path to read the word with"
        got = os.path.normcase(core.real_path(path))
        want = os.path.normcase(os.path.realpath(path))
        if got != want:
            return False, "real_path(%r) is %r, want realpath's %r: %s" % (path, got, want, why)
        return True, "real_path(%r) is realpath's %r: %s" % (path, want, why)

    join_log_check("slow words: real_path of %s is realpath's" % label, check)


real_path_control("a trailing-slash folder link", os.path.join(SLOW_DIR_LINK, ""), SLOW_DIR_LINK,
                  "a trailing slash leaves an empty leaf, so the full realpath reads it")
real_path_control("a dangling link", SLOW_DANGLING, SLOW_DANGLING,
                  "a link to a path that is not there reads as that path")
real_path_control("a symlink loop", SLOW_LOOP_A, SLOW_LOOP_A,
                  "a loop of links reads as realpath reads it, with no error")
real_path_control("a dot leaf under a link", os.path.join(SLOW_DIR_LINK, "."), SLOW_DIR_LINK,
                  "a `.` leaf takes the full realpath, so the link is followed")
real_path_control("a dotdot leaf under a link", os.path.join(SLOW_DIR_LINK, ".."), SLOW_DIR_LINK,
                  "a `..` leaf climbs from the folder the link resolves to")
real_path_control("a file under a linked folder", os.path.join(SLOW_DIR_LINK, "guard.py"), SLOW_DIR_LINK,
                  "a symlinked folder part resolves once, and the plain leaf joins it")
real_path_control("a symlink leaf", SLOW_LEAF_LINK, SLOW_LEAF_LINK,
                  "a symlink leaf takes the full realpath")


def remember_then_swap_check():
    """A log check: after `clear_real_cache()`, a folder swapped for a link reads as the link's target. Before
    the clear, the cache still holds the folder it read first, so the clear is what changes the answer."""
    if not slow_fixtures():
        return SKIP, NO_LINK
    core = slow_modules()[0]
    if not hasattr(core, "real_path") or not hasattr(core, "clear_real_cache"):
        return False, "guard_core has no real_path or clear_real_cache to read the folder with"
    base = os.path.join(SLOW_ROOT, "cache")
    folder = os.path.join(base, "swapped")  # a real folder, swapped below for a link to `moved`
    moved = os.path.join(base, "moved")
    probe = os.path.join(base, "probe-link")
    os.makedirs(folder, exist_ok=True)
    os.makedirs(moved, exist_ok=True)
    if os.path.islink(folder) or not os.path.isdir(folder):
        return False, "%s is not an ordinary folder before the swap, so the case does not probe one" % folder
    try:
        os.symlink(moved, probe, target_is_directory=True)
    except OSError:
        return SKIP, NO_LINK
    remove_link(probe)
    core.clear_real_cache()
    word = os.path.join(folder, "leaf.py")
    before = os.path.realpath(folder)
    try:
        core.real_path(word)  # reads the folder once, so the cache holds it
        os.rmdir(folder)
        os.symlink(moved, folder, target_is_directory=True)
        if not os.path.islink(folder):
            return False, "%s did not become a link, so the swap did not happen" % folder
        held = core.real_path(word)
        if os.path.normcase(held) != os.path.normcase(os.path.join(before, "leaf.py")):
            return False, ("without clear_real_cache, real_path(%r) is %r, not the folder the cache held (%r)"
                           % (word, held, os.path.join(before, "leaf.py")))
        core.clear_real_cache()
        got = os.path.normcase(core.real_path(word))
        want = os.path.normcase(os.path.realpath(word))
        if got != want:
            return False, "after clear_real_cache, real_path(%r) is %r, want realpath's %r" % (word, got, want)
        return True, "after clear_real_cache, real_path(%r) is realpath's %r" % (word, want)
    finally:
        core.clear_real_cache()
        if os.path.islink(folder):
            remove_link(folder)


join_log_check("slow words: a folder swapped for a link reads as the link's target after clear_real_cache",
               remember_then_swap_check)


def nul_outcome(read, path):
    """What `read(path)` gives: its value, or the name of the error it raised."""
    try:
        return ("value", os.path.normcase(read(path)))
    except Exception as error:  # the outcome is the error, whichever it is
        return ("raises", type(error).__name__)


def real_path_nul_check():
    """A log check: `real_path` of a NUL leaf gives what `os.path.realpath` gives, which is ValueError on main.
    The NUL leaf is not a path a link can be read through."""
    if not slow_fixtures():
        return SKIP, NO_LINK
    core = slow_modules()[0]
    if not hasattr(core, "real_path"):
        return False, "guard_core has no real_path to read the word with"
    path = os.path.join(SLOW_DIR_LINK, NUL_LEAF)
    want = nul_outcome(os.path.realpath, path)
    got = nul_outcome(core.real_path, path)
    if got != want:
        return False, "real_path of a NUL leaf gives %s, want %s, which is realpath's outcome on main" % (got, want)
    return True, "real_path of a NUL leaf gives %s, as realpath does" % (want,)


join_log_check("slow words: real_path of a NUL leaf gives realpath's outcome, an error", real_path_nul_check)


def frozen_nul_check():
    """A log check: `is_frozen` of a NUL leaf under a link into the config folder is False, as it is on main.
    Main's realpath raises ValueError on the NUL, and `is_frozen` reads that error as not frozen."""
    if not slow_fixtures():
        return SKIP, NO_LINK
    got = frozen_under_cfg(os.path.join("hooks-link", NUL_LEAF), SLOW_PROJ)
    if got:
        return False, "is_frozen of a NUL leaf under a link into the config folder is True, want False as on main"
    return True, "is_frozen of a NUL leaf under a link into the config folder is False, as on main"


join_log_check("slow words: is_frozen of a NUL leaf under a link into the config folder stays False",
               frozen_nul_check)


# ---- case 5: the lstat count of many link sources in one shell call. Each `cp -s` source is judged for a
# frozen link, and the bound is per source. Red until the per-source reads are cached, not per call.

def cp_sources_lstat_check():
    """The guard run on CP_SOURCES `cp -s` link sources makes at most LSTAT_PER_WORD lstat calls per source,
    plus LSTAT_FIXED for the guard's own reads."""
    return lstat_bound_check("cp", SLOW_CP, SLOW_BULK, CP_SOURCES, "%d-source cp chain" % CP_SOURCES)


join_log_check("slow words: 1000 cp link sources make at most 3 lstat calls per source",
               cp_sources_lstat_check)


# ---- case 6: a Windows junction leaf. A junction is a Windows link: ntpath.islink is False for it, so a
# read that does not call realpath on the leaf does not follow it. This check runs on Windows only, and it
# was written on Linux, so it has never run.

def junction_leaf_check():
    """A log check, Windows only: a junction leaf that names a folder under the frozen hooks folder is frozen,
    as it is on main. Unrun where it was written."""
    if os.name != "nt":
        return SKIP, "a junction is a Windows link: this control runs on Windows only, and was not run where it was written"
    os.makedirs(SLOW_SUB_DIR, exist_ok=True)
    if not os.path.lexists(SLOW_JUNCTION):
        made = subprocess.run(["cmd", "/c", "mklink", "/J", SLOW_JUNCTION, SLOW_SUB_DIR],
                              capture_output=True, text=True)
        if made.returncode != 0:
            return False, "mklink /J did not make the junction: %s" % (made.stdout + made.stderr).strip()[-120:]
    try:
        isjunction = getattr(os.path, "isjunction", None)
        if isjunction is not None and not isjunction(SLOW_JUNCTION):
            return False, "%s is not a junction, so the case does not probe one" % SLOW_JUNCTION
        got = frozen_under_cfg(os.path.basename(SLOW_JUNCTION), SLOW_PROJ)
    finally:
        try:
            os.rmdir(SLOW_JUNCTION)  # removes the junction, not the folder it names
        except OSError:
            pass
    if not got:
        return False, "is_frozen of a junction leaf into the frozen hooks folder is False, want True, as on main"
    return True, "is_frozen of a junction leaf into the frozen hooks folder is True, as on main"


join_log_check("slow words: is_frozen of a junction leaf into the frozen hooks folder stays True (Windows only)",
               junction_leaf_check)

FAMILY = "misc"  # back to the default for any section below

# section 39498
# The fixtureless set, checked fresh. A member of FIXTURELESS_CHECKS skips the full fixture build, so it must
# read no lazy fixture that only that build makes. This check holds each member to that. Each member runs in its
# own fresh process with only the fixtures its case names built, and must give the result it gives in one process
# with every lazy fixture built first. A member that differs reads a fixture the fresh process did not build, and
# goes red. Only a run of the fixtureless family selects this check, so only that run pays for it.

FRESH_CHILD = r'''
import importlib.util, json, os, shutil, sys
path, mode = sys.argv[1], sys.argv[2]
spec = importlib.util.spec_from_file_location("tg_fresh", path)
tg = importlib.util.module_from_spec(spec)
sys.path.insert(0, os.path.dirname(path))
spec.loader.exec_module(tg)
members = [m for m in tg.FIXTURELESS_CHECKS if m.__name__ != "fixtureless_fresh_check"]


def run(member):
    try:
        ok = member()[0]
    except Exception as err:
        return "raised " + type(err).__name__
    return repr(ok)


if mode == "all":
    tg.materialize_all()
    out = [run(m) for m in members]
else:
    out = [run(members[int(sys.argv[3])])]
print("FRESH " + json.dumps(out))
for orphan in tg.ORPHAN_PIDS:
    try:
        os.kill(orphan, 15)
    except OSError:
        pass
tg.OWNED.kill()
shutil.rmtree(tg.ROOT, ignore_errors=True)
'''

FRESH_DROP_ENV = ("GUARD_FAMILY", "GUARD_TESTS", "MUTATE_ONLY", "GUARD_SHARD", "GUARD_TIMING")
FRESH_WORKERS = 4  # named children run side by side; each one is its own process and its own run folder
CHILD_CAP = 300  # seconds: a named child past this gave no result, and its member is red
ALL_CAP = 900  # seconds: the all-built child builds every lazy fixture first


def fixtureless_fresh_check():
    """Each member gives the same outcome in a fresh process with only its named fixtures built as it gives with
    every lazy fixture built. A member that differs reads an unbuilt fixture. Only the outcome is compared: a note
    can carry live numbers, such as disk or memory, that differ between any two processes."""
    import concurrent.futures
    members = [m for m in FIXTURELESS_CHECKS if m.__name__ != "fixtureless_fresh_check"]
    env = {k: v for k, v in os.environ.items() if k not in FRESH_DROP_ENV}
    target = os.path.join(HERE, "test_guard.py")

    folder = os.path.join(ROOT, "fresh")
    os.makedirs(folder, exist_ok=True)

    def child(*args, cap):
        # Output goes to a file in this run's folder, not a pipe: a child's own background process inherits
        # a pipe and would hold the read until it exits, so the wait would run to the cap.
        name = os.path.join(folder, "-".join(args) + ".out")
        with open(name, "w", encoding="utf-8") as out:
            try:
                subprocess.run([sys.executable, "-c", FRESH_CHILD, target] + list(args),
                               stdout=out, stderr=subprocess.STDOUT, env=env, timeout=cap)
            except subprocess.TimeoutExpired:
                return None
        with open(name, encoding="utf-8") as text:
            lines = [line for line in text.read().splitlines() if line.startswith("FRESH ")]
        return json.loads(lines[-1][len("FRESH "):]) if lines else None

    every = child("all", cap=ALL_CAP)
    if every is None or len(every) != len(members):
        return False, "fixtureless: the all-built child gave no result for each of the %d members" % len(members)
    with concurrent.futures.ThreadPoolExecutor(max_workers=FRESH_WORKERS) as pool:
        fresh = list(pool.map(lambda i: child("named", str(i), cap=CHILD_CAP), range(len(members))))
    differ = []
    for i, got in enumerate(fresh):
        if got is None or got[0] != every[i]:
            differ.append(i)
    if not differ:
        return True, "%d members give the same outcome fresh, with only their named fixtures built, as with every fixture built" % len(members)
    i = differ[0]
    member = members[i]
    got = fresh[i][0] if fresh[i] else "no result"
    return False, "fixtureless: %d of %d members differ; first, %s (%s:%d), gives %s fresh but %s with every fixture built: it reads an unbuilt fixture" % (
        len(differ), len(members), member.__qualname__, os.path.basename(member.__code__.co_filename),
        member.__code__.co_firstlineno, got, every[i])


LOG_CHECKS_EXTRA.append(("fixtureless: each member gives the result it gives with every fixture built, fresh with only its named fixtures built", fixtureless_fresh_check))
LOG_FAMILY["fixtureless: each member gives the result it gives with every fixture built, fresh with only its named fixtures built"] = "fixtureless"
FIXTURELESS_CHECKS.add(fixtureless_fresh_check)

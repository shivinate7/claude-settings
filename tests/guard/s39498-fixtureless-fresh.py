# section 39498
# The fixtureless set, checked fresh. A member of FIXTURELESS_CHECKS skips the full fixture build, so it must
# read no lazy fixture that only that build makes. This check holds each member to that. A member must give the
# outcome it gives in one process with every lazy fixture built first, and the same outcome in a fresh child where
# only the lazy fixtures it names are built. The named set is the lazy builders its run calls, which the all-built
# child records per member. Members with the same named set share one fresh child, since each builds exactly that
# set. A member that differs reads a fixture its fresh child did not build, and goes red. The check is opt-in: only
# a run that names its family selects it (OPT_IN in hooks/test_guard.py).

FRESH_CHILD = r'''
import importlib.util, json, os, shutil, sys
path, mode = sys.argv[1], sys.argv[2]
spec = importlib.util.spec_from_file_location("tg_fresh", path)
tg = importlib.util.module_from_spec(spec)
sys.path.insert(0, os.path.dirname(path))
spec.loader.exec_module(tg)
members = [m for m in tg.FIXTURELESS_CHECKS if m.__name__ != "fixtureless_fresh_check"]
built = []  # while a member runs in the all-built child: the position in LAZY of each lazy builder it calls


def recorded(position, once):
    def call():
        built.append(position)
        once()
    return call


def run(member):
    try:
        ok = member()[0]
    except Exception as err:
        return "raised " + type(err).__name__
    return repr(ok)


if mode == "all":
    for position, key in enumerate(list(tg.LAZY)):
        tg.LAZY[key] = recorded(position, tg.LAZY[key])
    tg.materialize_all()
    out = []
    for m in members:
        del built[:]
        result = run(m)
        out.append([result, sorted(set(built))])
elif mode == "batch":
    out = [run(members[int(i)]) for i in sys.argv[3].split(",")]
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
FRESH_WORKERS = 4  # batch children run side by side; each one is its own process and its own run folder
BATCH_CAP = 600  # seconds: a batch child past this gave no result, and its members are red
ALL_CAP = 900  # seconds: the all-built child builds every lazy fixture first


def fixtureless_fresh_check():
    """Each member gives the same outcome in a fresh child with only its named fixtures built as it gives with
    every lazy fixture built. A member that differs reads an unbuilt fixture. Only the outcome is compared: a note
    can carry live numbers, such as disk or memory, that differ between any two processes."""
    import concurrent.futures
    members = [m for m in FIXTURELESS_CHECKS if m.__name__ != "fixtureless_fresh_check"]
    env = {k: v for k, v in os.environ.items() if k not in FRESH_DROP_ENV}
    target = os.path.join(HERE, "test_guard.py")
    folder = os.path.join(ROOT, "fresh")
    os.makedirs(folder, exist_ok=True)

    def child(name, argv, cap):
        # Output goes to a file in this run's folder, not a pipe: a child's own background process inherits
        # a pipe and would hold the read until it exits, so the wait would run to the cap.
        out_path = os.path.join(folder, name + ".out")
        with open(out_path, "w", encoding="utf-8") as out:
            try:
                subprocess.run([sys.executable, "-c", FRESH_CHILD, target] + argv,
                               stdout=out, stderr=subprocess.STDOUT, env=env, timeout=cap)
            except subprocess.TimeoutExpired:
                return None
        with open(out_path, encoding="utf-8") as text:
            lines = [line for line in text.read().splitlines() if line.startswith("FRESH ")]
        return json.loads(lines[-1][len("FRESH "):]) if lines else None

    every = child("all", ["all"], ALL_CAP)
    if every is None or len(every) != len(members):
        return False, "fixtureless: the all-built child gave no result for each of the %d members" % len(members)
    by_named = {}
    for i, (outcome, named) in enumerate(every):
        by_named.setdefault(tuple(named), []).append(i)
    batches = list(by_named.values())

    def run_batch(k):
        return child("batch-%d" % k, ["batch", ",".join(str(i) for i in batches[k])], BATCH_CAP)

    with concurrent.futures.ThreadPoolExecutor(max_workers=FRESH_WORKERS) as pool:
        results = list(pool.map(run_batch, range(len(batches))))
    fresh = [None] * len(members)
    for idxs, got in zip(batches, results):
        for pos, i in enumerate(idxs):
            if got is not None and pos < len(got):
                fresh[i] = got[pos]
    differ = [i for i in range(len(members)) if fresh[i] is None or fresh[i] != every[i][0]]
    if not differ:
        return True, "%d members give the same outcome fresh, with only their named fixtures built, as with every fixture built; %d fresh children" % (
            len(members), len(batches))
    i = differ[0]
    member = members[i]
    got = fresh[i] if fresh[i] is not None else "no result"
    return False, "fixtureless: %d of %d members differ; first, %s (%s:%d), gives %s fresh but %s with every fixture built: it reads an unbuilt fixture" % (
        len(differ), len(members), member.__qualname__, os.path.basename(member.__code__.co_filename),
        member.__code__.co_firstlineno, got, every[i][0])


LOG_CHECKS_EXTRA.append(("fixtureless: each member gives the result it gives with every fixture built, fresh with only its named fixtures built", fixtureless_fresh_check))
LOG_FAMILY["fixtureless: each member gives the result it gives with every fixture built, fresh with only its named fixtures built"] = "fixtureless"
FIXTURELESS_CHECKS.add(fixtureless_fresh_check)

"""Temporary probe for c62 (one-act pass race on Windows). Not for main."""
import os, subprocess, sys, threading
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import test_guard as tg

ROUNDS = int(os.environ.get("C62_ROUNDS", "40"))
WORKERS = 6
TAKE_CHILD = (
    "import sys\nsys.path.insert(0, sys.argv[1])\nimport override_pass\n"
    "from datetime import datetime\n"
    "print(override_pass.take(sys.argv[2], None, datetime.fromisoformat(sys.argv[3])))\n")


def log_lines(config, session):
    try:
        with open(os.path.join(config, "guard.log"), encoding="utf-8") as h:
            return [l.rstrip("\n") for l in h if l.rstrip("\n").endswith("\t" + session)]
    except OSError as e:
        return ["log unread: %r" % e]


def race(fn):
    out = [None] * WORKERS
    start = threading.Barrier(WORKERS)

    def w(i):
        start.wait()
        out[i] = fn()
    ts = [threading.Thread(target=w, args=(i,)) for i in range(WORKERS)]
    for t in ts: t.start()
    for t in ts: t.join()
    return out


def main():
    config = tg.ov_config("c62probe")
    print("warm:", tg.ov_kill(config, "c62-warm", 0)[0])
    bad_guard = 0
    for n in range(ROUNDS):
        s = "c62-guard-%d" % n
        tg.ov_type(config, s, "override")
        v = race(lambda: tg.ov_kill(config, s, 60))
        verdicts = [x[0] for x in v]
        if verdicts.count("allow") != 1:
            bad_guard += 1
            print("GUARD round %d: %r" % (n, verdicts))
            for line in log_lines(config, s):
                print("   log:", line)
    bad_take = 0
    env = dict(os.environ, CLAUDE_CONFIG_DIR=config)
    for n in range(ROUNDS):
        s = "c62-take-%d" % n
        tg.ov_type(config, s, "override")
        def one():
            r = subprocess.run([sys.executable, "-c", TAKE_CHILD, tg.HERE, s, tg.ov_clock(60)],
                               capture_output=True, text=True, env=env, timeout=60)
            return (r.stdout.strip() or "") + (("ERR " + r.stderr.strip()[-200:]) if r.returncode else "")
        v = race(one)
        if v.count("override") != 1:
            bad_take += 1
            print("TAKE round %d: %r" % (n, v))
    print("C62 RESULT: guard double/zero allow in %d of %d rounds; bare take in %d of %d rounds"
          % (bad_guard, ROUNDS, bad_take, ROUNDS))


main()

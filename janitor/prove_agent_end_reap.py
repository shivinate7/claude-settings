#!/usr/bin/env python3
"""End-to-end proof for janitor/agent_end_reap.py. Stdlib only. Exit 0 on PASS, 1 on FAIL.

    python janitor/prove_agent_end_reap.py          # fire the reaper (the fix)
    python janitor/prove_agent_end_reap.py --old    # fire only the cleanup that existed before
                                                    # it, sweep.py --confirm. Expect FAIL (red).

Builds a throwaway repo with two agent worktrees, `.claude/worktrees/agent-<A>` and
`agent-<B>`. Starts one server in each, and one in the primary checkout, with the shape
MEASURED to outlive the agent on Windows (PR #144): `server &` then `echo started`, in one
bash call that then exits. Fires a SubagentStop payload for agent A only. PASS needs the
server in A gone, and the servers in B and in the primary checkout alive.

Stops every process it started by pid, in a `finally`, whatever the verdict.
"""
import json
import os
import shutil
import socket
import subprocess
import sys
import tempfile
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(HERE), "hooks"))
sys.path.insert(0, HERE)
import agent_end_reap  # noqa: E402
import sweep  # noqa: E402

VCS = "g" + "it"
IDENT = ["-c", "user.email=reap-proof@example.invalid", "-c", "user.name=reap-proof"]


def git_bash():
    """Git's own bash.exe by full path on Windows. See
    decisions/bare-bash-on-windows-can-resolve-to-the-wsl-stub.md."""
    if os.name != "nt":
        return shutil.which("bash") or "bash"
    for var in ("ProgramFiles", "ProgramW6432", "ProgramFiles(x86)"):
        candidate = os.path.join(os.environ.get(var) or "", "Git", "bin", "bash.exe")
        if os.path.isfile(candidate):
            return candidate
    sys.exit("proof setup failed: Git bash.exe not found")


def vcs(where, *args):
    answer = subprocess.run([VCS, "-C", where, *IDENT, *args], capture_output=True, text=True,
                            timeout=20)
    if answer.returncode != 0:
        sys.exit("proof setup failed: %s %s: %s" % (VCS, " ".join(args), answer.stderr.strip()))


def free_port():
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        return probe.getsockname()[1]


def start_leaking_server(cwd, port):
    """The measured leak shape: a background job, then another line, then the shell exits."""
    python = sys.executable.replace("\\", "/")
    script = ('"%s" -m http.server %d --bind 127.0.0.1 >/dev/null 2>&1 </dev/null &\n'
              "echo started" % (python, port))
    subprocess.run([git_bash(), "-c", script], cwd=cwd, capture_output=True, timeout=20)
    deadline = time.time() + 15
    while time.time() < deadline:  # bounded readiness read for a fixture this file started
        for entry in sweep.list_listeners() or []:
            if entry["port"] == port:
                return entry["pid"]
        time.sleep(0.3)
    return None


def listening(port):
    return any(e["port"] == port for e in sweep.list_listeners() or [])


def main(argv):
    old = "--old" in argv
    root = tempfile.mkdtemp(prefix="reap_proof_")
    primary = os.path.join(root, "repo")
    config = os.path.join(root, "cfg")  # an empty config dir: no session record, a clean log
    os.makedirs(primary)
    vcs(primary, "init", "-q", "-b", "main", ".")
    with open(os.path.join(primary, "f.txt"), "w") as handle:
        handle.write("x\n")
    vcs(primary, "add", "-A")
    vcs(primary, "commit", "-q", "-m", "first")
    id_a, id_b = "proofaaaa1111", "proofbbbb2222"
    wt_a = os.path.join(primary, ".claude", "worktrees", "agent-" + id_a)
    wt_b = os.path.join(primary, ".claude", "worktrees", "agent-" + id_b)
    vcs(primary, "worktree", "add", "-q", wt_a, "-b", "lane-a")
    vcs(primary, "worktree", "add", "-q", wt_b, "-b", "lane-b")

    started = []  # every pid this proof started, server and stub alike, for the finally
    servers = {}
    ok = True
    try:
        for name, cwd in (("agent A", wt_a), ("agent B", wt_b), ("primary", primary)):
            port = free_port()
            pid = start_leaking_server(cwd, port)
            if pid is None:
                sys.exit("proof setup failed: %s server on %d never listened" % (name, port))
            stub = agent_end_reap.parent_pid(pid)
            started += [pid] + ([stub] if stub else [])
            servers[name] = (pid, port)
            print("started %-8s pid %s port %s parent %s orphan-read %s"
                  % (name, pid, port, stub, sweep.is_orphan(pid)))

        env = dict(os.environ, CLAUDE_CONFIG_DIR=config)
        if old:
            print("firing: sweep.py --confirm on the primary checkout (the cleanup before this fix)")
            subprocess.run([sys.executable, os.path.join(HERE, "sweep.py"), primary, "--confirm"],
                           env=env, capture_output=True, text=True, timeout=120)
        else:
            payload = {"hook_event_name": "SubagentStop", "agent_id": id_a, "cwd": wt_a,
                       "session_id": "proof"}
            print("firing: agent_end_reap.py with SubagentStop for agent-%s" % id_a)
            subprocess.run([sys.executable, os.path.join(HERE, "agent_end_reap.py")],
                           input=json.dumps(payload), env=env, capture_output=True, text=True,
                           timeout=120)
            with open(os.path.join(config, "state", "agent-end-payloads.jsonl")) as handle:
                record = json.loads(handle.readlines()[-1])
            for decision in record.get("decisions") or []:
                print("  reaper: pid %s %s %s" % (decision["pid"], decision["action"],
                                                  decision["reason"]))
        time.sleep(sweep.LISTENER_GRACE_PERIOD_SECONDS)

        for name, want_alive in (("agent A", False), ("agent B", True), ("primary", True)):
            pid, port = servers[name]
            alive = listening(port)
            verdict = "PASS" if alive == want_alive else "FAIL"
            ok = ok and verdict == "PASS"
            print("%s %-8s port %s %s (want %s)" % (verdict, name, port,
                                                   "alive" if alive else "gone",
                                                   "alive" if want_alive else "gone"))
    finally:
        for pid in started:
            if sweep.pid_alive(pid):
                sweep.send_signal(pid)
        time.sleep(1)
        left = [pid for pid in started if sweep.pid_alive(pid)]
        print("cleanup: stopped %d started pids by pid, %d still alive %s"
              % (len(started), len(left), left))
        shutil.rmtree(root, ignore_errors=True)
    print("PROOF", "PASS" if ok else "FAIL")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))

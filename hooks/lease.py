#!/usr/bin/env python3
"""lease: the one home of a named lease held in git. Take it, give it back, or lift it.

Usage:
  lease take NAME [--holder ID] [--roster TEXT] [--repo-dir D] [--remote R]
  lease give NAME [--holder ID] [--repo-dir D] [--remote R]
  lease lift NAME [--repo-dir D] [--remote R]
  lease show NAME [--repo-dir D] [--remote R]

A lease is the ref refs/heads/lease/NAME on the remote. Its record is a commit with an empty tree whose message lines are
`lease NAME`, `holder:`, `repo:`, `taken:` and `roster:`. A lease has no expiry: it ends when the holder gives it back or
the owner lifts it. A released record carries the line `expires: 0`. A give back and a lift push such a record and never
delete the ref: the cloud git proxy refuses a ref delete and every push outside refs/heads. A ref the owner deleted by hand
reads as free.

take    one force-with-lease push that names the sha it expects (empty when the ref is absent), so one of two takes at once
        loses. The holder taking again is `own` and pushes nothing. Another holder's live lease is `held`.
give    the holder's release. `not-holder` for anyone else, `free` when no live lease is there.
lift    the owner's release. It reads only the ref's sha, never the commit message, so a corrupt record can still be lifted.
show    prints the state and the holder.

Holder: --holder, else holder_id() of the caller's environment (`session_X` for the cloud id `cse_X`, else
CLAUDE_CODE_SESSION_ID). A caller with no id cannot take or give back.
Exit codes: 0 done (take: taken or own; give: given or free; lift: lifted or free; show), 1 refused (held, not-holder),
2 UNKNOWN (a read or push that failed or ran past its time) or a bad argument. A read that fails is UNKNOWN, never free.
Cost: holds() and read() start git for `ls-remote`, one `fetch` of the ref and one `log` on a sha not seen before in this
process; a sha seen before costs the `ls-remote` alone. A commit never changes, so the sha-to-record cache is safe. The ref's own sha is
never cached. No timer, no process left running, no file written beside the repo's own objects.
"""
import argparse
import os
import re
import subprocess
import sys
import time
from collections import namedtuple

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _nowindow  # noqa: E402  the one home of a no-window child start (hooks/_nowindow.py)

READ_BUDGET_S = 10  # all the git calls of one read, together: a read past it is UNKNOWN, so a guard never hangs on a dead remote
PUSH_TIMEOUT_S = 30
REF_PREFIX = "refs/heads/lease/"
CLOUD_ENV = "CLAUDE_CODE_REMOTE_SESSION_ID"
LOCAL_ENV = "CLAUDE_CODE_SESSION_ID"
CLOUD_PREFIX = "cse_"
HOLDER_MAX = 200
GIT_ENV = {"GIT_TERMINAL_PROMPT": "0"}  # a credential prompt would hang until the time runs out
GIT_IDENT = ["-c", "user.name=lease", "-c", "user.email=lease@localhost"]

Record = namedtuple("Record", "sha fields released")
Taken = namedtuple("Taken", "status holder output")  # status: taken, own or held


class Unknown(Exception):
    """A read or push that failed, ran past its time, or returned what this module cannot read. It refuses; it never reads as free."""


_records = {}  # (repo, sha) -> the record's message: a commit never changes


def ref_of(name):
    return REF_PREFIX + name


def holder_id(env, payload_session_id=None):
    """The caller's holder id: `session_X` for a cloud id `cse_X`, else the local session id, else the hook payload's. None when none is set."""
    cloud = env.get(CLOUD_ENV) or ""
    if cloud.startswith(CLOUD_PREFIX) and len(cloud) > len(CLOUD_PREFIX):
        return "session_" + cloud[len(CLOUD_PREFIX):]
    return env.get(LOCAL_ENV) or payload_session_id or None


def _git(repo, args, timeout, input=None):
    """One git child, through the no-window wrapper, with a time limit. -> (code, stdout, stderr). A start that fails or runs past `timeout` is Unknown."""
    if timeout <= 0:
        raise Unknown("the time for reading the lease ran out")
    try:
        done = _nowindow.run(["git", *args], cwd=repo, input=input, capture_output=True, text=True, encoding="utf-8",
                             errors="replace", timeout=timeout, env=dict(os.environ, **GIT_ENV))
    except subprocess.TimeoutExpired:
        raise Unknown("git %s ran past %.0fs" % (args[0], timeout)) from None
    except OSError as err:
        raise Unknown("git did not start: %s" % err) from None
    return done.returncode, done.stdout.strip(), done.stderr.strip()


def _tip(repo, remote, name, deadline):
    """The ref's sha on the remote, or '' when the ref is absent. A failed read is Unknown."""
    ref = ref_of(name)
    code, out, err = _git(repo, ["ls-remote", remote, ref], deadline - time.monotonic())
    if code:
        raise Unknown("cannot read %s on %s: %s" % (ref, remote, err or out))
    for line in out.splitlines():
        sha, _, found = line.partition("\t")
        if found == ref:  # ls-remote matches a pattern by its tail: only this exact ref counts
            return sha
    return ""


def _parse(sha, message):
    fields = {}
    for line in message.splitlines()[1:]:
        m = re.fullmatch(r"([a-z]+): (.*)", line)
        if m:
            fields.setdefault(m.group(1), m.group(2))
    return Record(sha, fields, fields.get("expires") == "0")


def read(repo, remote, name, budget_s=READ_BUDGET_S):
    """The lease's Record(sha, fields, released), or None when the ref is absent. Raises Unknown when the read fails or runs past budget_s."""
    deadline = time.monotonic() + budget_s
    sha = _tip(repo, remote, name, deadline)
    if not sha:
        return None
    key = (os.path.realpath(repo), sha)
    if key not in _records:
        ref = ref_of(name)
        code, out, err = _git(repo, ["fetch", "-q", "--no-write-fetch-head", remote, ref], deadline - time.monotonic())
        if code:
            raise Unknown("cannot fetch %s from %s: %s" % (ref, remote, err or out))
        code, out, err = _git(repo, ["log", "-1", "--format=%B", sha], deadline - time.monotonic())
        if code:  # the ref moved between the two reads: the sha read first is not there
            raise Unknown("the lease moved while it was read (%s): %s" % (sha[:12], err or out))
        _records[key] = out
    return _parse(sha, _records[key])


def holds(repo, remote, name, holder, budget_s=READ_BUDGET_S):
    """True only when the lease is live and its holder line is `holder`. Raises Unknown on a failed read."""
    record = read(repo, remote, name, budget_s)
    return bool(holder) and record is not None and not record.released and record.fields.get("holder") == holder


def _line(text):
    """One capped line: untrusted text cannot add a `holder:` or `expires:` line."""
    return " ".join(str(text).split())[:HOLDER_MAX]


def _push_record(repo, remote, name, expected, message):
    """Make a record commit with `message` and push it, naming `expected` as the sha the ref must still hold (empty: the ref must be absent).
    -> (code, push output). The output of the push is kept for the caller."""
    ref = ref_of(name)
    deadline = time.monotonic() + PUSH_TIMEOUT_S
    code, tree, err = _git(repo, ["mktree"], PUSH_TIMEOUT_S, input="")
    if code:
        raise Unknown("cannot make the lease tree: " + err)
    code, sha, err = _git(repo, [*GIT_IDENT, "commit-tree", tree, "-m", message], deadline - time.monotonic())
    if code:
        raise Unknown("cannot make the lease commit: " + err)
    code, out, err = _git(repo, ["push", "-q", "--force-with-lease=%s:%s" % (ref, expected), remote, "%s:%s" % (sha, ref)],
                          deadline - time.monotonic())
    return code, (out + "\n" + err).strip()


def _released_message(name, how):
    return "lease %s\nexpires: 0\nreleased: %s\nby: %s" % (name, int(time.time()), how)


def _taken_message(repo, remote, name, holder, roster):
    code, url, _ = _git(repo, ["config", "--get", "remote.%s.url" % remote], PUSH_TIMEOUT_S)
    lines = ["lease " + name, "holder: " + _line(holder), "repo: " + _line(url if code == 0 and url else remote),
             "taken: " + time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())]
    if roster:
        lines.append("roster: " + _line(roster))
    return "\n".join(lines)


def take(repo, remote, name, holder, roster=None):
    """Take the lease. -> Taken(status, holder, output): `taken`, `own` (the holder took it before; nothing pushed) or `held` (another holder's live lease).
    The push names the sha it read, so of two takes at once one loses and reads held. Raises Unknown."""
    if not holder:
        raise Unknown("no holder id: the caller has no session id")
    message = _taken_message(repo, remote, name, holder, roster)
    for _ in range(3):
        record = read(repo, remote, name)
        if record is not None and not record.released:
            who = record.fields.get("holder", "unknown")
            return Taken("own" if who == holder else "held", who, "")
        code, out = _push_record(repo, remote, name, record.sha if record else "", message)
        if not code:
            return Taken("taken", holder, out)
        now = read(repo, remote, name)  # a moved ref is another take; an unmoved ref is a push the remote refused
        if (now.sha if now else "") == (record.sha if record else ""):
            raise Unknown("the remote refused the push that takes lease %s: %s" % (name, out))
    raise Unknown("lease %s kept changing while it was taken" % name)


def give(repo, remote, name, holder):
    """The holder gives the lease back. -> `given`, `not-holder` or `free` (no live lease). Raises Unknown."""
    record = read(repo, remote, name)
    if record is None or record.released:
        return "free"
    if not holder or record.fields.get("holder") != holder:
        return "not-holder"
    code, out = _push_record(repo, remote, name, record.sha, _released_message(name, "give"))
    if not code:
        return "given"
    now = read(repo, remote, name)
    if now is None or now.sha != record.sha:
        return "not-holder"  # the lease changed under this give back: it is no longer this holder's to give
    raise Unknown("the remote refused the push that gives back lease %s: %s" % (name, out))


def lift(repo, remote, name):
    """The owner lifts the lease whoever holds it, even a record whose message is junk. -> `lifted` or `free` (no ref). Raises Unknown.
    It reads only the ref's sha."""
    for _ in range(3):
        sha = _tip(repo, remote, name, time.monotonic() + READ_BUDGET_S)
        if not sha:
            return "free"
        code, out = _push_record(repo, remote, name, sha, _released_message(name, "lift"))
        if not code:
            return "lifted"
        if _tip(repo, remote, name, time.monotonic() + READ_BUDGET_S) == sha:
            raise Unknown("the remote refused the push that lifts lease %s: %s" % (name, out))
    raise Unknown("lease %s kept changing while it was lifted" % name)


def _show(record, name):
    if record is None:
        return "lease %s is free" % name
    if record.released:
        return "lease %s is free (given back or lifted)" % name
    f = record.fields
    return "lease %s is held by %s (taken %s, repo %s%s)" % (name, f.get("holder", "unknown"), f.get("taken", "?"), f.get("repo", "?"),
                                                            ", roster " + f["roster"] if "roster" in f else "")


class OneLineParser(argparse.ArgumentParser):
    """A bad argument prints one usage line on stderr and exits 2."""

    def error(self, message):
        print("usage: lease take|give NAME [--holder ID] [--roster TEXT] | lift NAME | show NAME [--repo-dir D] [--remote R]; "
              + message.replace("\n", " "), file=sys.stderr)
        sys.exit(2)


def main(argv=None):
    p = OneLineParser(prog="lease", description="The one lease: take, give back or lift a named lease held in git.")
    p.add_argument("verb", choices=("take", "give", "lift", "show"))
    p.add_argument("name")
    p.add_argument("--holder")
    p.add_argument("--roster")
    p.add_argument("--repo-dir", default=os.getcwd())
    p.add_argument("--remote", default="origin")
    args = p.parse_args(argv)
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]*", args.name):
        p.error("NAME is letters, digits, dot, dash and underscore only")
    holder = args.holder or holder_id(os.environ)
    try:
        if args.verb == "show":
            print(_show(read(args.repo_dir, args.remote, args.name), args.name))
            return 0
        if args.verb == "lift":
            print("lease %s: %s" % (args.name, lift(args.repo_dir, args.remote, args.name)))
            return 0
        if not holder:
            print("lease: UNKNOWN: no holder id; pass --holder, or run in a session that has CLAUDE_CODE_SESSION_ID", file=sys.stderr)
            return 2
        if args.verb == "give":
            status = give(args.repo_dir, args.remote, args.name, holder)
            print("lease %s: %s" % (args.name, status))
            return 1 if status == "not-holder" else 0
        got = take(args.repo_dir, args.remote, args.name, holder, args.roster)
        if got.output:
            print(got.output, file=sys.stderr)
        if got.status == "held":
            print("lease %s is held by %s; ask the owner to lift it (lease lift %s)" % (args.name, got.holder, args.name), file=sys.stderr)
            return 1
        print("lease %s: %s by %s" % (args.name, got.status, got.holder))
        return 0
    except Unknown as err:
        print("lease: UNKNOWN: %s" % err, file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())

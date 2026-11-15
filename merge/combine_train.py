#!/usr/bin/env python3
"""The dry combine train (roadmap step combine-train-tool): fold the queued batches behind the frozen ones, in dry rounds, and print per-batch numbers.

  python3 merge/combine_train.py (--queue FILE | --from-rest [--repo OWNER/NAME]) --root DIR [--lint]

Standalone. merge.py never imports it, so it changes no merge verdict. It never runs `git push`, `gh pr ready`, `gh pr merge` or creates a pull request.
Its writes are git objects (`git merge-tree`, `git commit-tree`) in the checkout DIR and one temporary worktree per batch, removed at the end.

The queue file's schema is this tool's own: skills/project-ops/scripts/check_runner_state.py, which the runner-queue step names as its home, is not in
the repo, so there is no reader to reuse. The shape is
                   {"prs": [{"number": N, "head": SHA}, ...] in priority order,
                   "batches": [{"name": B, "state": "in-ci" | "next-in-line" | "queued", "members": [N, ...]}, ...]}.
Every batch name and every rule below is a reading of the decision text in docs/decisions/session-tiers.md ("Rolling combine train"), which
is not built as a rule. The header line names the readings:
  (a) an in-ci or next-in-line batch is frozen: it prints as it is, and no fold touches it. The queued batches behind them fold into one batch.
  (b) a fold pairs adjacent tips, 8 to 4 to 2 to 1. A pair whose merge conflicts leaves its later side by name with its conflicting paths; a later side
      that holds several members retries them one by one, so only the clashing member leaves.
  (c) dry rounds ignore a move of main (the newest main joins at the final build, which is not this tool's).
  (d) the fast checks run once per round, on the round's leading tip, and once for a batch that needs no round. A later round's tips hold the
      earlier ones, so the last round checks the whole batch. Their home is merge.readyChecks in .github/stamp.json on origin/main, run through
      one `bin/ci-job JOB --step NAME ... --base origin/main` per job (merge.ready_job_groups, merge.ci_job_run). The tool re-implements none of them.
  (e) with --lint, one `bin/ci-job checks --lint` run on each folded batch's final tree.
  (f) before any pairing, each queued member is merge-tested against origin/main in DIR. A member that clashes with main leaves by name with its
      paths and `(clash with main)`. A merge with main is no pair tried, and a main clash is not in the clash rate's numerator.

--from-rest reads the queue from GitHub instead of a file, through merge.Host (the one home of the REST reads; this tool adds no REST client):
Host.pages("pulls", fields={"state": "open"}) for the open pulls, then Host.head_read(n) for each ready one (a draft is not in the queue).
  (g) the queue order is the PR number, ascending: REST holds no priority, and an owner's priority list is not read here.
  (h) the state of a ready PR is its CI reading. Every `pending` PR is the in-ci batch (one batch, frozen). The first `green` PR in order is the
      next-in-line batch (one PR, frozen). The other `green` PRs are the one queued batch that folds. A `red` PR is not queued and prints
      `left out #N: red (<name>)`. An `unknown` PR prints `unknown (<why>)`, is not queued, and makes the exit code 2.
Each queued PR's head sha is the REST read's. One `git fetch origin refs/pull/N/head ...` brings the heads into DIR; a head that is still missing after the
fetch (or a failed fetch) is unknown for that PR, never a pass. --repo defaults to the origin of DIR; an origin that is no URL leaves the repo to `gh` run in DIR.
The run prints the queue it read (one line per PR with its state) before the batches, and a last `wall seconds` line from the injected clock. Reads only: every REST call is a GET.
The clash rate is the members a pair clash left out, over the pairs tried (a group merge and each retry of its members are each a pair).
A number the tool did not measure prints `unknown` or `n/a (reason)`, never 0 and never a guess.
Exit: 0 ok, 1 a member left out or a check failed, 2 something unknown or a run that could not start (a git that is not on PATH included).
Cost: per fold, one `git merge-tree` start per member (against main) and per pair tried and one `git commit-tree` start per merge; per round, one ci-job run per job of the checks when they have a home;
with --lint, one more ci-job run per batch. One temporary worktree per batch. Nothing is logged or left running.
Cost of --from-rest on top: the gh reads (one pulls list, then per ready PR the pr, check, status and run reads of head_read), one git fetch, no write, no file, no process kept.
"""
import argparse
import json
import os
import re
import shutil
import sys
import tempfile
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import merge  # noqa: E402  the git wrapper (merge.merge_tree) and the one ci-job run (merge.ci_job_run); merge.CI_JOB is its tool path
import _nowindow  # noqa: E402  the one home of a child start with no console window (hooks/_nowindow.py); merge.py puts hooks/ on sys.path

BASE = "origin/main"
STATES = ("in-ci", "next-in-line", "queued")
FROZEN = ("in-ci", "next-in-line")
NO_HOME = "unknown (fast-checks-before-ready not landed)"
HEADER_CORE = ("combine-train: dry run, no push, no gh pr ready or merge. Readings used: (a) in-ci and next-in-line batches are frozen and the queued "
               "batches behind them fold into one; (b) a clashing member leaves by name; (c) dry rounds ignore a move of main; "
               "(d) the fast checks run once per round on its leading tip; (e) --lint runs once on a folded batch's final tree; "
               "(f) each member is merge-tested against origin/main first, and a clash with main leaves by name.")
HEADER = HEADER_CORE + " Queue schema: the tool's own."
REST_HEADER = (HEADER_CORE + " Readings (g) and (h), the queue read from GitHub, reads only: (g) the queue order is the PR number, ascending, because REST holds no priority "
               "and an owner's priority list is not read here; (h) the state of a ready PR is its CI reading: pending is the in-ci batch, the first green "
               "is the next-in-line batch, the other green ones are the queued batch that folds, red is left out by name, unknown is not queued.")


class QueueError(Exception):
    pass


def git(root, *args):
    """-> (exit code, stdout, stderr) of one git call in `root`. The identity and signing are pinned so `commit-tree` needs no user config."""
    cmd = ["git", "-C", root, "-c", "user.name=combine-train", "-c", "user.email=combine-train@invalid", "-c", "commit.gpgsign=false", *args]
    r = _nowindow.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace")  # an OSError (no git on PATH) goes to main
    return r.returncode, r.stdout.strip(), r.stderr.strip()


def read_queue(path):
    """-> (heads {number: sha}, batches [(name, state, [members])]). A queue that cannot be read or has the wrong shape raises QueueError, naming the file."""
    try:
        with open(path, encoding="utf-8") as f:
            doc = json.load(f)
    except (OSError, ValueError) as e:
        raise QueueError(f"the queue file {path} cannot be read: {e}")
    try:
        heads = {int(p["number"]): str(p["head"]) for p in doc["prs"]}
        batches = []
        for b in doc["batches"]:
            if b["state"] not in STATES:
                raise QueueError(f"the queue file {path}: batch {b['name']} has the state {b['state']!r}, not one of {', '.join(STATES)}")
            batches.append((str(b["name"]), b["state"], [int(m) for m in b["members"]]))
    except (KeyError, TypeError, ValueError) as e:
        raise QueueError(f"the queue file {path} has the wrong shape ({type(e).__name__}: {e}); it needs prs [number, head] and batches [name, state, members]")
    seen = {}
    for name, _state, members in batches:
        for m in members:
            if m in seen:
                raise QueueError(f"the queue file {path}: PR #{m} is a member of batch {seen[m]} and batch {name}")
            seen[m] = name
    return heads, batches


def ready_steps(root):
    """-> (steps, why). steps: merge.readyChecks of .github/stamp.json on origin/main, or None with `why` (the unknown line to print)."""
    code, out, err = git(root, "show", f"{BASE}:.github/stamp.json")
    if code:
        return None, f"unknown (.github/stamp.json on {BASE} cannot be read: {err or out})"
    try:
        steps = json.loads(out).get("merge", {}).get("readyChecks")
    except (ValueError, AttributeError) as e:
        return None, f"unknown (.github/stamp.json on {BASE} is not readable JSON: {e})"
    if not steps:
        return None, NO_HOME
    return list(steps), None


def minutes(seconds):
    m = seconds / 60.0
    return "<0.01" if 0 < m < 0.005 else f"{m:.2f}"


def tag(members):
    return " ".join(f"#{n}" for n in members)


class Tip:
    """One side of a pair: a commit and the members it holds, in order."""

    def __init__(self, commit, members):
        self.commit, self.members = commit, members


class Fold:
    """The dry fold of one batch: its tips, what left, the merge counts, and its round and check lines."""

    def __init__(self, root, heads, members, clock):
        self.root, self.heads, self.clock = root, heads, clock
        self.tips = [Tip(heads[m], [m]) for m in members]
        self.left = []        # (member, "clash" | "unknown", detail)
        self.tried = 0        # pairs tried: every merge of two tips, never a merge with main
        self.clashed = 0      # members a pair clash left out
        self.rounds = 0
        self.seconds = 0.0
        self.lines = []       # round and check lines, in order
        self.unknown = False
        self.failed = False

    def merge_pair(self, a, b_members, b_commit):
        """Merge tip `a` with `b_commit` (holding `b_members`). -> the new Tip, or None with the members left out recorded."""
        state, tree, files = merge.merge_tree(self.root, a.commit, b_commit)
        if state == "unknown":
            return None, state, files
        self.tried += 1
        if state == "conflict":
            return None, state, files
        code, out, err = git(self.root, "commit-tree", tree, "-p", a.commit, "-p", b_commit, "-m", f"dry fold of {tag(a.members + b_members)}")
        if code:
            return None, "unknown", [f"git commit-tree failed: {err or out}"]
        return Tip(out, a.members + b_members), state, []

    def leave(self, members, state, files, against, pair=True):
        """Record `members` as left out. `against` is the text after "clash with"; `pair` is false for a clash with main, which the clash rate leaves out."""
        for m in members:
            if state == "conflict":
                self.clashed += pair
                self.left.append((m, "clash", f"{', '.join(files) or '(no file name read)'} (clash with {against})"))
            else:
                self.left.append((m, "unknown", f"{' '.join(files)}"))
                self.unknown = True

    def pair(self, a, b):
        """Fold tip `b` onto tip `a`. -> the tip that continues. A later side that holds several members and clashes retries its members one by one."""
        tip, state, files = self.merge_pair(a, b.members, b.commit)
        if tip:
            return tip
        if state == "conflict" and len(b.members) > 1:
            for m in b.members:
                tip, st, fl = self.merge_pair(a, [m], self.heads[m])
                if tip:
                    a = tip
                else:
                    self.leave([m], st, fl, tag(a.members))
            return a
        self.leave(b.members, state, files, tag(a.members))
        return a

    def test_main(self):
        """Reading (f): merge-test each member's head against BASE, and drop the member that clashes (or cannot be tested) before any pairing."""
        kept = []
        for tip in self.tips:
            state, _tree, files = merge.merge_tree(self.root, BASE, tip.commit)
            if state == "clean":
                kept.append(tip)
            else:
                self.leave(tip.members, state, files, "main", pair=False)
        self.tips = kept

    def round(self, check):
        """One round: pair adjacent tips, carry an odd one over, then run `check(tip, label)` on the leading tip."""
        start = self.clock()
        before = self.tried, self.clashed
        slot = len(self.lines)
        self.lines.append("")  # the round's own line goes before its check lines, once its minutes are known
        out = []
        for i in range(0, len(self.tips) - 1, 2):
            out.append(self.pair(self.tips[i], self.tips[i + 1]))
        if len(self.tips) % 2:
            out.append(self.tips[-1])
        self.tips = out
        self.rounds += 1
        check(self.tips[0], f"round {self.rounds}")
        took = self.clock() - start
        self.seconds += took
        self.lines[slot] = f"round {self.rounds}: {self.tried - before[0]} pairs tried, {self.clashed - before[1]} clashed, {minutes(took)} minutes"


class Checks:
    """The fast checks of one batch, run in one temporary worktree that moves to each tip."""

    def __init__(self, root, steps, why, fold):
        self.root, self.steps, self.why, self.fold = root, steps, why, fold
        self.wt = None
        self.stopped = False  # after an unknown, no further ci-job run for this batch

    def at(self, commit):
        """-> the worktree path with `commit` checked out, or None with the failure recorded as unknown."""
        if self.wt is None:
            path = tempfile.mkdtemp(prefix="combine-train-")
            code, out, err = git(self.root, "worktree", "add", "-q", "--detach", path, commit)
            if code:
                shutil.rmtree(path, ignore_errors=True)
                self.fold.unknown = True
                self.fold.lines.append(f"unknown: no temporary worktree for {commit[:9]}: {err or out}")
                return None
            self.wt = path
            return path
        code, out, err = git(self.wt, "checkout", "-q", "--detach", commit)
        if code:
            self.fold.unknown = True
            self.fold.lines.append(f"unknown: the temporary worktree could not move to {commit[:9]}: {err or out}")
            return None
        return self.wt

    def close(self):
        if self.wt:
            git(self.root, "worktree", "remove", "--force", self.wt)
            shutil.rmtree(self.wt, ignore_errors=True)
            git(self.root, "worktree", "prune")
            self.wt = None

    def run(self, tip, label):
        """Run the fast checks on `tip`, one ci-job run per job (merge.ready_job_groups), and add one line for them to the fold's lines (printed after the round lines)."""
        f = self.fold
        if self.steps is None:
            if not self.stopped:
                f.lines.append(f"{label}: fast checks {self.why}")
                self.stopped = True
                f.unknown = True
            return
        if self.stopped:
            return
        wt = self.at(tip.commit)
        if wt is None:
            self.stopped = True
            return
        states, lines, log = [], [], []
        for job, group in merge.ready_job_groups(self.steps).items():
            args = [job, "--pinned", *[a for _, bare in group for a in ("--step", bare)], "--base", BASE]
            job_state, job_lines, job_log, _ = merge.ci_job_run(wt, *args)
            states.append(job_state)
            lines += job_lines
            log += job_log
        state = "fail" if "fail" in states else "unknown" if "unknown" in states else "pass"
        where = f"{label}, leading tip {tag(tip.members)}"
        if state == "pass":
            f.lines.append(f"{where}: fast checks ok" + (f" (skipped: {', '.join(lines)})" if lines else ""))
        elif state == "fail":
            f.failed = True
            f.lines.append(f"{where}: fast checks FAIL")
            f.lines.extend("  " + l for l in lines + log)
        else:
            f.unknown = True
            self.stopped = True
            f.lines.append(f"{where}: fast checks unknown, no further run for this batch")
            f.lines.extend("  " + l for l in lines + log)

    def lint(self, tip):
        """One `ci-job checks --lint` on the final tree. -> the lint minutes line value."""
        f = self.fold
        wt = self.at(tip.commit)
        if wt is None:
            return "unknown (no worktree)"
        start = f.clock()
        state, lines, log, _ = merge.ci_job_run(wt, "checks", "--lint", "--base", BASE)
        took = f.clock() - start
        if state == "pass":
            return minutes(took)
        if state == "fail":
            f.failed = True
            f.lines.append("lint FAIL")
        else:
            f.unknown = True
            f.lines.append("lint unknown")
        f.lines.extend("  " + l for l in lines + log)
        return f"{minutes(took)} (lint FAIL)" if state == "fail" else "unknown"


def fold_batch(name, members, heads, steps, why, lint, clock, root):
    """Fold one queued batch. -> (the printed block as lines, left out count, failed, unknown)."""
    fold = Fold(root, heads, members, clock)
    checks = Checks(root, steps, why, fold)
    lint_value = "n/a (not run)"
    try:
        fold.test_main()
        if len(fold.tips) == 1:
            checks.run(fold.tips[0], "no round")
        while len(fold.tips) > 1:
            fold.round(checks.run)
        if lint and fold.tips:
            lint_value = checks.lint(fold.tips[0])
    finally:
        checks.close()
    kept = tag(fold.tips[0].members) if fold.tips else "(none)"
    lines = [f"batch {name} (queued, folded): {kept}"]
    lines.extend(fold.lines)
    for m, kind, detail in fold.left:
        lines.append(f"left out #{m}: {detail}" if kind == "clash" else f"left out #{m}: unknown ({detail})")
    lines.append(f"members in: {len(members)}")
    lines.append(f"members left out: {len(fold.left)}")
    lines.append(f"clash rate: {fold.clashed}/{fold.tried}" if fold.tried else "clash rate: n/a (no pair tried)")
    lines.append(f"dry rounds: {fold.rounds}")
    lines.append(f"dry-round minutes: {minutes(fold.seconds)}" if fold.rounds else "dry-round minutes: n/a (no round run)")
    lines.append(f"lint minutes: {lint_value}")
    lines.append("CI minutes: n/a (dry run)")
    return lines, len(fold.left), fold.failed, fold.unknown


def plain_block(name, state, members, why):
    """The block of a batch that is not folded (`why`: "frozen", or "empty" for a queued batch with no member), with its numbers named as not measured."""
    return [f"batch {name} ({state}, {why}): {tag(members)}",
            f"members in: {len(members)}", "members left out: 0", f"clash rate: n/a ({why}, no fold)",
            f"dry rounds: n/a ({why})", f"dry-round minutes: n/a ({why})", "lint minutes: n/a (not run)", "CI minutes: n/a (dry run)"]


def main(argv, clock=None):
    clock = clock or time.monotonic
    p = argparse.ArgumentParser(prog="combine_train.py", description="The dry combine train: fold the queued batches behind the frozen ones.")
    p.add_argument("--queue", help="the queue JSON file")
    p.add_argument("--root", required=True, help="a checkout of the repo that holds the PR heads")
    p.add_argument("--lint", action="store_true", help="run `ci-job checks --lint` once on each folded batch's final tree")
    p.add_argument("--from-rest", action="store_true", help="read the queue from GitHub REST (reads only) instead of --queue FILE")
    p.add_argument("--repo", help="OWNER/NAME for --from-rest; default: the origin of --root")
    args = p.parse_args(argv)
    if args.from_rest and args.queue:
        print("unknown: --from-rest and --queue cannot be given together; give one of them")
        return 2
    if not args.from_rest and not args.queue:
        print("unknown: no queue given; give --queue FILE or --from-rest")
        return 2
    try:
        if args.from_rest:
            return run_rest(args, clock)
        try:
            heads, batches = read_queue(args.queue)
        except QueueError as e:
            print(f"unknown: {e}")
            return 2
        return run(args, heads, batches, clock)
    except OSError as e:  # a program that cannot start, in practice git missing from PATH
        print(f"unknown: a program cannot start ({e.filename or 'git'}: {e.strerror or e}); the dry fold needs git on PATH")
        return 2


def run(args, heads, batches, clock):
    """The queue is read: print the header, then one block per batch. -> the exit code."""
    print(HEADER)
    queued = [(n, m) for n, st, m in batches if st == "queued"]
    folded = [m for _n, ms in queued for m in ms]
    steps, why = ready_steps(args.root) if folded else (None, None)
    left = failed = unknown = False
    printed_fold = False
    for name, state, members in batches:
        if state in FROZEN:
            print("\n".join(plain_block(name, state, members, "frozen")))
        elif not printed_fold:  # every queued batch folds into the one batch printed at the first queued place
            printed_fold = True
            fname = "+".join(n for n, _m in queued)
            gone = [m for m in folded if m not in heads]
            if gone:
                print(f"batch {fname} (queued, folded): unknown (the queue file's prs hold no head for {tag(gone)})")
                unknown = True
            elif not folded:
                print("\n".join(plain_block(fname, "queued", [], "empty")))
            else:
                lines, out, bad, unk = fold_batch(fname, folded, heads, steps, why, args.lint, clock, args.root)
                print("\n".join(lines))
                left, failed, unknown = left or out > 0, failed or bad, unknown or unk
    return 2 if unknown else 1 if left or failed else 0


def origin_repo(root):
    """-> OWNER/NAME read from the origin URL of `root`, or None for an origin that is no URL (a path), which leaves the repo to `gh` run in `root`."""
    code, out, _err = git(root, "remote", "get-url", "origin")
    m = None if code else re.match(r"^(?:[a-z][a-z0-9+.-]*://[^/]+/|[^/@]+@[^/:]+:)(?:.*/)?([^/]+)/([^/]+?)(?:\.git)?/?$", out)
    return f"{m.group(1)}/{m.group(2)}" if m else None


def fetch_heads(root, members, heads):
    """One `git fetch` of refs/pull/N/head for every member. -> {member: why} for each member whose head is not in `root` afterwards (all of them on a failed fetch)."""
    code, out, err = git(root, "fetch", "--quiet", "--no-tags", "--no-write-fetch-head", "origin", *[f"refs/pull/{m}/head" for m in members])
    first = (err or out or "no output").splitlines()[0]
    missing = {}
    for m in members:
        if code:
            missing[m] = f"git fetch of refs/pull/{m}/head failed: {first}"
        elif git(root, "cat-file", "-e", f"{heads[m]}^{{commit}}")[0]:
            missing[m] = f"the head {heads[m][:9]} is not in the checkout after the fetch"
    return missing


def read_rest(host):
    """-> (lines, in_ci, next_in_line, queued, heads, left_red, unknown): the queue read from GitHub, in PR order (reading g), by CI reading (h).
    `lines` is one line per open PR with its state; `left_red` is [(n, name)]; `unknown` is True when a ready PR could not be read."""
    rows = sorted(host.pages("pulls", fields={"state": "open"}), key=lambda r: int(r["number"]))
    state, heads, left_red, unknown = {}, {}, [], False
    in_ci, green = [], []
    for row in rows:
        n = int(row["number"])
        if row.get("draft"):
            state[n] = "draft, not queued"
            continue
        heads[n] = str(row["head"]["sha"])
        verdict, detail = host.head_read(n)
        if verdict == "pending":
            in_ci.append(n)
            state[n] = "pending, in the in-ci batch"
        elif verdict == "green":
            green.append(n)
        elif verdict == "red":
            left_red.append((n, detail))
            state[n] = "red, not queued"
        else:
            unknown = True
            state[n] = f"unknown ({detail or 'no reason given'}), not queued"
    nxt, queued = green[:1], green[1:]
    for n in nxt:
        state[n] = "green, the next-in-line batch"
    for n in queued:
        state[n] = "green, in the queued batch"
    return [f"queue #{n}: {state[n]}" for n in sorted(state)], in_ci, nxt, queued, heads, left_red, unknown


def run_rest(args, clock):
    """--from-rest: read the queue from GitHub through merge.Host, print it, then the batches as run() does. -> the exit code."""
    start = clock()
    print(REST_HEADER)
    host = merge.Host(repo=args.repo or origin_repo(args.root), cwd=args.root)
    try:
        lines, in_ci, nxt, queued, heads, left_red, unknown = read_rest(host)
    except Exception as e:  # a failed read (merge.Stop) or a reply that is no pull list: the queue is unknown, never empty
        print(f"unknown: the open pulls could not be read from GitHub: {e}")
        return 2
    print("\n".join(lines))
    for n, name in left_red:
        print(f"left out #{n}: red ({name})")
    left = bool(left_red)
    failed = False
    for name, members in (("in-ci", in_ci), ("next-in-line", nxt)):
        if members:
            print("\n".join(plain_block(name, name, members, "frozen")))
    if queued:
        missing = fetch_heads(args.root, queued, heads)
        for n, why in missing.items():
            print(f"left out #{n}: unknown ({why})")
        unknown = unknown or bool(missing)
        folded = [m for m in queued if m not in missing]
        if folded:
            steps, why = ready_steps(args.root)
            block, out, bad, unk = fold_batch("queued", folded, heads, steps, why, args.lint, clock, args.root)
            print("\n".join(block))
            left, failed, unknown = left or out > 0, bad, unknown or unk
    try:
        wall = f"{float(clock()) - float(start):.2f}"
    except (TypeError, ValueError):
        wall = "unknown (the clock gave no number)"
    print(f"wall seconds: {wall}")
    return 2 if unknown else 1 if left or failed else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))

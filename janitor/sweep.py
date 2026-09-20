#!/usr/bin/env python3
"""The machine-wide janitor sweep.

Governed by plans/janitor-build-plan.md. Reaps local branches that hold no unique work and
removes git worktrees that no session still uses, across every repository the sweep is pointed
at, or discovers.

WHY THIS IMPORTS hooks/guard.py INSTEAD OF WRITING ITS OWN COPY: hooks/guard.py's PreToolUse
rule 1 (`branch_delete_subject`, `worktree_remove_subject`, `resolve_default_base`,
`session_is_live`, the three `branch_*` tests, `worktree_locked`, `porcelain`) already answers
almost every question this sweep asks, is already exercised by hooks/test_guard.py, and a
second copy of that logic is the one outcome this build must avoid (plan, "the one outcome to
avoid"). This module therefore calls guard's own primitives directly for every decision that
holds a safety property (dirty/locked/live/ancestor/cherry/remote-contains), and keeps its own
code only for orchestration (which repositories, which branches, which order, the preview
report, the tombstone, and the 90-day purge) that guard has no reason to know about. Nothing
here re-derives a keep-or-reap boolean by a path of its own; every boolean comes from guard.

Preview is the default. Nothing is deleted until `--confirm` is passed. The sweep never touches
a remote and never stops a running program.

Usage:
    python3 janitor/sweep.py [ROOT ...]                 # preview a sweep of the named roots
    python3 janitor/sweep.py --discover DIR              # preview a sweep of DIR's own checkouts
    python3 janitor/sweep.py ROOT --confirm              # actually reap
    python3 janitor/sweep.py --purge                     # preview which tombstones are past 90 days
    python3 janitor/sweep.py --purge --confirm           # actually drop tombstones past 90 days

With no ROOT and no `--discover`, the sweep discovers under `~/Developer` when that directory
exists, else under the current directory. Discovery lists a directory's immediate children whose
`.git` is a DIRECTORY (an ordinary checkout), never a FILE (a linked worktree of some other
checkout): a linked worktree's branches already belong to its primary checkout's sweep, and
sweeping it a second time as its own "repository" would apply the keep rule against the wrong
tree entirely.
"""
import argparse
import json
import os
import sys
import time
from collections import Counter

HERE = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(REPO_ROOT, "hooks"))
import guard  # noqa: E402

OPTOUT_FILENAME = os.path.join(".claude", "janitor.json")
DEFAULT_PROTECTED_PREFIXES = ("backup/",)
TOMBSTONE_REF_PREFIX = "refs/janitor/reaped/"
TOMBSTONE_TTL_MS = 90 * 24 * 60 * 60 * 1000  # git's own reflog-retention number; see the plan


# ------------------------------------------------------------------ discovery


def default_discover_root() -> str:
    developer = os.path.expanduser("~/Developer")
    if os.path.isdir(developer):
        return developer
    return os.getcwd()


def discover_repos(root: str):
    """Return ROOT's immediate children that are ordinary checkouts (`.git` a directory).

    A linked worktree's `.git` is a FILE naming its own admin directory, so it never matches
    here; only a primary checkout does. Sorted for a stable, readable report.
    """
    if not root or not os.path.isdir(root):
        return []
    found = []
    for name in sorted(os.listdir(root)):
        path = os.path.join(root, name)
        if os.path.isdir(os.path.join(path, ".git")):
            found.append(path)
    return found


# ------------------------------------------------------------------ the opt-out file
#
# `.claude/janitor.json`, inside the repository, read as DATA (json.load) and never executed.
# Absent means swept, with the default protected prefix `backup/` alone. `"sweep": false` opts
# the whole repository out. `"protectedPrefixes"` adds more prefixes beside `backup/`.
#
# A present file that cannot be parsed is an UNREADABLE subject, same direction as refusal 7: the
# sweep does not know what this repository asked for, so it reaps nothing here rather than guess
# that an unreadable "no" meant "yes".


def load_optout(root: str):
    """Return (sweep_enabled, protected_prefixes, ok).

    ok is False when the file exists but could not be read as one JSON object, or when a key it
    DOES hold is not shaped the way that key means: a `sweep` value that is not a boolean, or a
    `protectedPrefixes` value that is not a list of strings. In every one of those cases the
    caller refuses the whole repository rather than trust a default.

    A key that is ABSENT is different: an absent key states nothing, and the owner's choice was
    auto-on, so the default still applies. But a key that IS present and malformed states a
    wish the sweep cannot read. Guessing at that wish is the one error that costs work: guess
    wrong on `sweep` and a repository that opted out gets swept and loses branches; guess wrong
    on `protectedPrefixes` and a repository silently protects nothing. Refusing the repository
    costs one rerun after the owner fixes the file. Guessing costs branches that do not come
    back.
    """
    path = os.path.join(root, OPTOUT_FILENAME)
    if not os.path.isfile(path):
        return True, DEFAULT_PROTECTED_PREFIXES, True
    try:
        with open(path, "r", encoding="utf-8") as handle:
            data = json.load(handle)
    except Exception:
        return False, (), False
    if not isinstance(data, dict):
        return False, (), False
    if "sweep" in data and not isinstance(data["sweep"], bool):
        return False, (), False
    sweep_enabled = data.get("sweep", True)
    if "protectedPrefixes" in data:
        extra = data["protectedPrefixes"]
        if not isinstance(extra, list) or not all(isinstance(item, str) for item in extra):
            return False, (), False
    else:
        extra = []
    prefixes = list(DEFAULT_PROTECTED_PREFIXES)
    for item in extra:
        if item:
            prefixes.append(item)
    return sweep_enabled, tuple(prefixes), True


# ------------------------------------------------------------------ reading a repository's state


def list_local_branches(where: str):
    """Return every local branch's short name, or None when the read failed."""
    answer = guard._git(where, "for-each-ref", "--format=%(refname:short)", "refs/heads")
    if answer is None or answer.returncode != 0:
        return None
    return [line.strip() for line in answer.stdout.splitlines() if line.strip()]


def _short_branch_ref(ref: str) -> str:
    prefix = "refs/heads/"
    return ref[len(prefix):] if ref.startswith(prefix) else ref


def parse_worktree_list(where: str):
    """Return every registered worktree of `where`'s clone as a dict, or None when unreadable.

    Same block shape guard.worktree_locked already parses (`--porcelain`, blocks separated by a
    blank line); this reads the whole listing instead of one target, because the sweep needs the
    full set: which branch each worktree holds (for the checked-out refusal) and which path to
    decide on next.
    """
    answer = guard._git(where, "worktree", "list", "--porcelain")
    if answer is None or answer.returncode != 0:
        return None
    entries = []
    for block in answer.stdout.split("\n\n"):
        lines = block.splitlines()
        if not lines or not lines[0].startswith("worktree "):
            continue
        entry = {
            "path": lines[0][len("worktree "):].strip(),
            "branch": None,
            "bare": False,
            "detached": False,
            "locked_reason": None,
        }
        for line in lines[1:]:
            if line.startswith("branch "):
                entry["branch"] = _short_branch_ref(line[len("branch "):].strip())
            elif line == "bare":
                entry["bare"] = True
            elif line == "detached":
                entry["detached"] = True
            elif line == "locked" or line.startswith("locked "):
                entry["locked_reason"] = line[len("locked"):].strip() or "locked"
        entries.append(entry)
    return entries


# ------------------------------------------------------------------ the branch keep rule
#
# The REAP-OR-KEEP boolean is guard.branch_is_empty(where, base, branch) alone, unchanged:
# ancestor, then cherry-empty, then remote-contains, any one passing proves the work survives the
# branch, None (any test could not be read) means keep. This function decides nothing that
# function did not already decide; the refusals ahead of it (default branch, protected prefix,
# checked out) and the label after it (which of the three tests passed) are the only things added
# here, and neither can turn a keep into a reap or a reap into a keep.


def decide_branch(where: str, base: str, branch: str, protected_prefixes, checked_out_branches):
    """Return one decision dict: {"name", "action": "reap"|"keep", "reason"}."""
    if branch in ("main", "master"):
        return {"name": branch, "action": "keep", "reason": "default-branch"}
    for prefix in protected_prefixes:
        if branch.startswith(prefix):
            return {"name": branch, "action": "keep", "reason": "protected-prefix:" + prefix}
    if branch in checked_out_branches:
        return {"name": branch, "action": "keep", "reason": "checked-out"}
    empty = guard.branch_is_empty(where, base, branch)
    if empty is None:
        return {"name": branch, "action": "keep", "reason": "unreadable-subject"}
    if empty is False:
        return {"name": branch, "action": "keep", "reason": "only-copy"}
    return {"name": branch, "action": "reap", "reason": _branch_reap_label(where, base, branch)}


def _branch_reap_label(where: str, base: str, branch: str) -> str:
    """Cosmetic only: guard.branch_is_empty above already decided REAP. This re-reads the same
    three tests, in the same order, purely to name which one passed in the preview line. A bug
    here can only mislabel a reap; it cannot turn a keep into a reap, because the boolean already
    came from guard.branch_is_empty and this function's return value never feeds back into it."""
    if guard.branch_is_ancestor(where, base, branch):
        return "ancestor"
    if guard.branch_cherry_empty(where, base, branch):
        return "cherry-empty"
    return "on-remote"


# ------------------------------------------------------------------ the worktree keep rule
#
# Same shape: every boolean (dirty, locked, live) is guard's own primitive
# (guard.porcelain, guard.worktree_locked, guard.worktree_live_session), read in the same order
# guard.worktree_remove_subject already uses. This function adds only the "which one refused"
# label. The "never touch the primary checkout" exclusion is NOT here: it is decided in
# `sweep_repo`, before `decide_worktree` is ever called, by `_is_primary_checkout` below. See
# that function's docstring for why comparing against the ROOT argument (an earlier version of
# this file did that, and only that) is not enough.


def _is_primary_checkout(entry_path: str):
    """True when `entry_path` IS the repository's one primary checkout, False for a linked
    worktree, None when the read failed.

    THE DEFECT THIS REPLACES: an earlier version of this file compared each worktree entry's
    real path against the `root` argument `sweep_repo` was called with, and skipped only that
    one match. That is correct ONLY when `root` already names the primary checkout. Call
    `sweep_repo` with a LINKED WORKTREE's own path instead (`session_end_sweep.py`'s whole job
    is to prevent that, by resolving to the primary checkout first, but `sweep.py` itself must
    not depend on every caller doing that correctly) and the actual primary checkout stops
    matching `root`, stops being excluded, and gets evaluated by `decide_worktree` like any
    other worktree -- `REAP removable` when it happens to be clean, unlocked, and not live. A
    reviewer measured exactly that against a real fixture: `git worktree remove` on the primary
    tree then failed only because GIT ITSELF refuses to remove a main working tree that way --
    a refusal this program does not control and must not lean on (CLAUDE.md,
    "verification-recovery-not-gated-on-own-state"; a guard that depends on someone else's
    refusal fails the day that refusal changes).

    THE FIX: ask git which path is primary, independent of what `root` was. Every worktree of
    one clone shares exactly one git directory (`--git-common-dir`); the primary checkout is
    the one worktree whose OWN git directory (`--git-dir`) equals that shared one. A linked
    worktree's own git directory is instead a subdirectory of the shared one
    (`<common>/worktrees/<name>`), so the two never match there. This is the same read
    `hooks/guard.py.is_worktree` already makes and `hooks/test_guard.py` already exercises, run
    here per-entry so it answers correctly no matter which worktree `sweep_repo` was pointed at.
    """
    answer = guard._git(entry_path, "rev-parse", "--git-dir", "--git-common-dir")
    if answer is None or answer.returncode != 0:
        return None
    lines = answer.stdout.splitlines()
    if len(lines) < 2:
        return None
    try:
        own = os.path.normcase(os.path.realpath(os.path.join(entry_path, lines[0].strip())))
        common = os.path.normcase(os.path.realpath(os.path.join(entry_path, lines[1].strip())))
    except Exception:
        return None
    return own == common


def decide_worktree(where: str, entry: dict):
    """Return one decision dict: {"path", "action": "reap"|"keep", "reason"}."""
    path = entry["path"]
    dirty = guard.porcelain(path)
    if dirty is None:
        return {"path": path, "action": "keep", "reason": "unreadable-subject"}
    if dirty:
        return {"path": path, "action": "keep", "reason": "dirty"}
    locked = guard.worktree_locked(where, path)
    if locked is None:
        return {"path": path, "action": "keep", "reason": "unreadable-subject"}
    if locked:
        holder = entry.get("locked_reason") or "locked"
        return {"path": path, "action": "keep", "reason": "locked: %s" % holder}
    live = guard.worktree_live_session(path)
    if live is None:
        return {"path": path, "action": "keep", "reason": "unreadable-subject"}
    if live:
        return {"path": path, "action": "keep", "reason": "live-session"}
    return {"path": path, "action": "reap", "reason": "removable"}


# ------------------------------------------------------------------ the tombstone


def default_restore_log_path() -> str:
    return os.path.join(guard.config_dir(), "janitor", "restore-log.jsonl")


def append_restore_log(path: str, repo: str, branch: str, commit: str):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    line = json.dumps({
        "repo": repo, "branch": branch, "commit": commit,
        "time_ms": int(time.time() * 1000),
    })
    with open(path, "a", encoding="utf-8") as handle:
        handle.write(line + "\n")


def reap_branch(root: str, branch: str, decision: dict, restore_log_path: str):
    """Write the tombstone, log it, THEN delete. In that order: a delete that ran before its
    tombstone landed could lose the branch's only pointer to work the log has not recorded yet."""
    tip = guard._git(root, "rev-parse", "refs/heads/" + branch)
    if tip is None or tip.returncode != 0:
        decision["error"] = "could not resolve the branch tip; branch left alone"
        return
    commit = tip.stdout.strip()
    tomb = guard._git(root, "update-ref", TOMBSTONE_REF_PREFIX + branch, commit)
    if tomb is None or tomb.returncode != 0:
        decision["error"] = "tombstone write failed; branch NOT deleted"
        return
    append_restore_log(restore_log_path, root, branch, commit)
    delete = guard._git(root, "branch", "-D", branch)
    if delete is None or delete.returncode != 0:
        decision["error"] = "delete failed after the tombstone landed: %s" % (
            delete.stderr.strip() if delete is not None else "git gave no answer"
        )


def remove_worktree(root: str, path: str, decision: dict):
    answer = guard._git(root, "worktree", "remove", path)
    if answer is None or answer.returncode != 0:
        decision["error"] = "remove failed: %s" % (
            answer.stderr.strip() if answer is not None else "git gave no answer"
        )


# ------------------------------------------------------------------ the purge
#
# Age comes from the restore log's OWN time_ms field, never from the tombstone ref's mtime (an
# mtime changes for reasons unrelated to the reap: a repack, a filesystem touch, a clone).


def read_restore_log(path: str):
    if not os.path.isfile(path):
        return []
    entries = []
    with open(path, "r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            try:
                entries.append(json.loads(line))
            except Exception:
                continue  # one bad line does not make the rest of the log unreadable
    return entries


def purge_tombstones(restore_log_path: str, confirm: bool, now_ms=None):
    """Return one decision dict per log entry: {"repo", "branch", "action": "purge"|"keep",
    "reason"}. With confirm, a "purge" decision also drops that repository's tombstone ref."""
    now_ms = now_ms if now_ms is not None else int(time.time() * 1000)
    decisions = []
    for entry in read_restore_log(restore_log_path):
        repo = entry.get("repo")
        branch = entry.get("branch")
        when = entry.get("time_ms")
        if not isinstance(repo, str) or not repo or not isinstance(branch, str) or not branch \
                or not isinstance(when, (int, float)) or isinstance(when, bool):
            decisions.append({"repo": repo, "branch": branch, "action": "keep",
                               "reason": "unreadable-entry"})
            continue
        age_ms = now_ms - when
        if age_ms < TOMBSTONE_TTL_MS:
            decisions.append({"repo": repo, "branch": branch, "action": "keep",
                               "reason": "not yet 90 days (%d days old)" % (age_ms // 86400000)})
            continue
        decision = {"repo": repo, "branch": branch, "action": "purge",
                     "reason": "past 90 days (%d days old)" % (age_ms // 86400000)}
        decisions.append(decision)
        if confirm:
            dropped = guard._git(repo, "update-ref", "-d", TOMBSTONE_REF_PREFIX + branch)
            if dropped is None or dropped.returncode != 0:
                decision["error"] = "drop failed: %s" % (
                    dropped.stderr.strip() if dropped is not None else "git gave no answer"
                )
    return decisions


# ------------------------------------------------------------------ sweeping one repository


def sweep_repo(root: str, confirm: bool, restore_log_path: str):
    result = {"root": root, "refused": None, "branches": [], "worktrees": []}

    sweep_enabled, protected_prefixes, optout_ok = load_optout(root)
    if not optout_ok:
        result["refused"] = "unreadable-optout"
        return result
    if not sweep_enabled:
        result["refused"] = "opted-out"
        return result

    base = guard.resolve_default_base(root)
    if base is None:
        result["refused"] = "no-default-base"
        return result

    entries = parse_worktree_list(root)
    if entries is None:
        result["refused"] = "unreadable-worktree-list"
        return result

    checked_out_branches = {e["branch"] for e in entries if e.get("branch")}

    branches = list_local_branches(root)
    if branches is None:
        result["refused"] = "unreadable-branch-list"
        return result

    for branch in branches:
        decision = decide_branch(root, base, branch, protected_prefixes, checked_out_branches)
        result["branches"].append(decision)
        if confirm and decision["action"] == "reap":
            reap_branch(root, branch, decision, restore_log_path)

    for entry in entries:
        if entry.get("bare"):
            continue
        is_primary = _is_primary_checkout(entry["path"])
        if is_primary is True:
            continue  # the clone's one primary checkout: no decision is ever recorded against it
        if is_primary is None:
            # Could not tell whether this IS the primary checkout. Rule 7's direction: an
            # unreadable subject means keep, never a guess that it is safe to evaluate.
            result["worktrees"].append(
                {"path": entry["path"], "action": "keep", "reason": "unreadable-subject"}
            )
            continue
        decision = decide_worktree(root, entry)
        result["worktrees"].append(decision)
        if confirm and decision["action"] == "reap":
            remove_worktree(root, entry["path"], decision)

    return result


# ------------------------------------------------------------------ reporting


def print_sweep_report(results, confirm: bool, out=sys.stdout):
    mode = "CONFIRM: reaping for real" if confirm else "PREVIEW: nothing is deleted"
    print("janitor sweep -- %s" % mode, file=out)

    branch_counts = Counter()
    worktree_counts = Counter()
    refused_repos = []

    for result in results:
        print("", file=out)
        print("== %s ==" % result["root"], file=out)
        if result["refused"]:
            refused_repos.append((result["root"], result["refused"]))
            print("  REFUSED: %s -- reaps nothing in this repository" % result["refused"],
                  file=out)
            continue
        if not result["branches"] and not result["worktrees"]:
            print("  nothing to examine", file=out)
        for b in result["branches"]:
            branch_counts[(b["action"], b["reason"].split(":", 1)[0])] += 1
            tag = "REAP" if b["action"] == "reap" else "KEEP"
            line = "  branch    %-4s %-40s %s" % (tag, b["name"], b["reason"])
            if b.get("error"):
                line += "  [ERROR: %s]" % b["error"]
            print(line, file=out)
        for w in result["worktrees"]:
            worktree_counts[(w["action"], w["reason"].split(":", 1)[0])] += 1
            tag = "REAP" if w["action"] == "reap" else "KEEP"
            line = "  worktree  %-4s %-60s %s" % (tag, w["path"], w["reason"])
            if w.get("error"):
                line += "  [ERROR: %s]" % w["error"]
            print(line, file=out)

    print("", file=out)
    print("== summary ==", file=out)
    if refused_repos:
        for repo, reason in refused_repos:
            print("  repository refused: %s (%s)" % (repo, reason), file=out)
    else:
        print("  repositories refused: 0", file=out)
    total_branches = sum(branch_counts.values())
    print("  local branches examined: %d" % total_branches, file=out)
    for (action, reason), n in sorted(branch_counts.items()):
        print("    %-5s %-20s %d" % (action, reason, n), file=out)
    total_worktrees = sum(worktree_counts.values())
    print("  worktrees examined: %d" % total_worktrees, file=out)
    for (action, reason), n in sorted(worktree_counts.items()):
        print("    %-5s %-20s %d" % (action, reason, n), file=out)


def print_purge_report(decisions, confirm: bool, out=sys.stdout):
    mode = "CONFIRM: dropping tombstones for real" if confirm else "PREVIEW: nothing is dropped"
    print("janitor purge -- %s" % mode, file=out)
    counts = Counter()
    for d in decisions:
        counts[d["action"]] += 1
        tag = "PURGE" if d["action"] == "purge" else "KEEP "
        line = "  %s %-30s %-40s %s" % (tag, d.get("repo"), d.get("branch"), d["reason"])
        if d.get("error"):
            line += "  [ERROR: %s]" % d["error"]
        print(line, file=out)
    print("", file=out)
    print("tombstones examined: %d, purge: %d, keep: %d"
          % (len(decisions), counts.get("purge", 0), counts.get("keep", 0)), file=out)


# ------------------------------------------------------------------ CLI


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        description="The machine-wide janitor sweep. Preview by default; --confirm to reap."
    )
    parser.add_argument("roots", nargs="*", help="repository roots to sweep")
    parser.add_argument("--discover", metavar="DIR",
                         help="sweep DIR's own checkouts, used only when no ROOT is given")
    parser.add_argument("--confirm", action="store_true",
                         help="actually delete branches/worktrees or drop tombstones")
    parser.add_argument("--purge", action="store_true",
                         help="purge tombstones past 90 days instead of sweeping")
    parser.add_argument("--restore-log", metavar="PATH",
                         help="override the restore log path (default: under the config dir)")
    args = parser.parse_args(argv)

    restore_log_path = args.restore_log or default_restore_log_path()

    if args.purge:
        decisions = purge_tombstones(restore_log_path, args.confirm)
        print_purge_report(decisions, args.confirm)
        return 0

    roots = [os.path.abspath(r) for r in args.roots]
    if not roots:
        discover_root = args.discover or default_discover_root()
        roots = discover_repos(discover_root)
        if not roots:
            print("janitor: no repositories found under %s" % discover_root, file=sys.stderr)
            return 1

    results = [sweep_repo(root, args.confirm, restore_log_path) for root in roots]
    print_sweep_report(results, args.confirm)
    return 0


if __name__ == "__main__":
    sys.exit(main())

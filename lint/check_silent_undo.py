#!/usr/bin/env python3
"""Fails when a merge or branch silently drops or reverts earlier work. Stdlib and git only.

    python3 lint/check_silent_undo.py [--upstream origin/main] [--head HEAD] [--strict]
    python3 lint/check_silent_undo.py --history [REV] [--window 60]   # audit, always exit 0

Two reads, one verdict. Design: decisions/silent-undo-check-design.md.

  lost lines  A merge commit M (in upstream..head) loses a line one parent added since the
              merge base: the line is absent from every base, M holds fewer copies than that
              parent, no other file of M gained it, it is no run of words re-wrapped inside
              the file, and no line of the same hunk reads 0.9 like it (a resolver's rewrite).
              Catches a conflict taken "ours", and a hand edit of a merge.
  reversal    The result of landing head on upstream puts a file back as it was before an
              earlier first-parent commit of upstream changed it: the exact blob (whole
              file), a -U0 hunk reversed on all but one line, or lines main only added
              that this change removes, even beside an edit. Reads only the commits
              upstream gained after the branch was cut (since the merge base, or since
              the branch's first commit was authored, which a rebase keeps). Catches
              `git revert`, a stale copy, a rebase that took its own side.

Blank lines and whitespace never count. The escape is a trailer in a commit message, one per
path: `Drops-lines: <path> -- <reason>`. A trailer with no reason excuses nothing. Each use prints
`ALLOWED <path>: <reason>`. On a branch it may be on any commit of the branch. In history it is
the commit, plus the branch it merged for a reversal.

A read that cannot run prints UNKNOWN. Exit 0 locally, exit 1 when env CI is set or with
--strict (ruling: unknown in CI is red).
"""
import argparse
import collections
import difflib
import os
import re
import subprocess
import sys

TRAILER = "Drops-lines"
ZERO = "0" * 40
WORD = re.compile(r"[A-Za-z0-9]")


class Unknown(Exception):
    pass


def git(cwd, *a, ok=(0,)):
    r = subprocess.run(["git", "-C", cwd, *a], capture_output=True, text=True, errors="replace")
    if r.returncode not in ok:
        raise Unknown("git %s failed: %s" % (" ".join(a[:3]), r.stderr.strip() or r.returncode))
    return r.returncode, r.stdout


def norm(line):
    return " ".join(line.split())


def counts(text):
    return collections.Counter(n for n in map(norm, text.splitlines()) if n)


def blob(cwd, rev, path):
    rc, out = git(cwd, "show", "%s:%s" % (rev, path), ok=(0, 128))
    return out if rc == 0 else ""


def allowed(cwd, rng):
    """{path: reason} from `Drops-lines: <path> -- <reason>` trailers on any commit of the range
    (a rev or a..b). A trailer with no reason excuses nothing."""
    _, out = git(cwd, "log", "--format=%(trailers:key=" + TRAILER + ",valueonly,unfold)", rng)
    res = {}
    for line in out.splitlines():
        m = re.match(r"\s*(\S.*?)\s+--\s+(\S.*?)\s*$", line)
        if m:
            res[m.group(1)] = m.group(2)
    return res


def judge(items, ok):
    """items: (path, text). -> (texts whose path no trailer excuses, ALLOWED notes for the rest)."""
    bad = [t for p, t in items if p not in ok]
    notes = ["ALLOWED %s: %s" % (p, ok[p]) for p in sorted({p for p, _ in items if p in ok})]
    return bad, notes


def raw_files(cwd, *revs):
    """path -> (old blob, new blob) for `git diff-tree old new`, or `--root new` for one rev."""
    _, out = git(cwd, "diff-tree", "-r", "--no-renames", "-z", "--raw", "--no-abbrev", *revs)
    t = out.split("\0")
    res = {}
    for i in range(0, len(t) - 1, 2):
        bits = t[i].split()
        if len(bits) >= 5:
            res[t[i + 1]] = (bits[2], bits[3])
    return res


# ------------------------------------------------------------------ lost lines


def pool_of(cwd, p, m):
    """Lines M holds more of than parent p, across all files: where a moved line went."""
    _, out = git(cwd, "diff", "-U0", "--no-color", "--no-renames", p, m)
    return counts("\n".join(l[1:] for l in out.splitlines() if l.startswith("+") and not l.startswith("+++")))


TOKEN = re.compile(r"[A-Za-z_]+|\d+(?:\.\d+)?|[<>=!]=?|[-+*/%&|^~]|\S")
NEGATION = re.compile(r"\b(?:not|no|never|none|nor|cannot|without)\b|n't\b", re.I)


def kinds(line):
    """(numbers, operators, negation count) of a line, as sorted lists and a count."""
    toks = TOKEN.findall(line)
    return (sorted(x for x in toks if x[0].isdigit()), sorted(x for x in toks if x[0] in "<>=!-+*/%&|^~"),
            len(NEGATION.findall(line)))


def trailing_only(g, base):
    """True when g is a base line plus trailing tokens or punctuation (` #s`, `,`, `;`)."""
    return any(g.startswith(b) and len(g) > len(b) and not (g[len(b)].isalnum() or g[len(b)] == "_") for c in base for b in c)


def wrapped(line, new):
    """True when line, whole and whitespace-collapsed, is a run of the joined new lines with at
    least 4 words, and the run starts or ends where a new line starts or ends (a re-wrap)."""
    if len(line.split()) < 4:
        return False
    joined, edges, pos = " ".join(new), set(), 0
    for g in new:
        edges |= {pos, pos + len(g)}
        pos += len(g) + 1
    i = joined.find(line)
    while i >= 0:
        if i in edges or i + len(line) in edges:
            return True
        i = joined.find(line, i + 1)
    return False


def rewritten(line, hs, base=(), modified=False):
    """True when the merge rewrote this line inside its hunk, so it is no silent drop. Either the
    whole line is a re-wrapped run of the hunk's new lines (`wrapped`), or a new line reads 0.9
    like it. 0.8 would excuse `A new 1` against `B new 1` (0.86), which is a drop. A line that
    itself changed a base line (`modified`) is a value both sides touched, and 0.8 is enough: a
    resolver who picks a third value for `RULE_FLOOR = 85` and `= 91` wrote `= 94`.
    A new line that equals the base version, or that only adds trailing tokens or punctuation
    to it, is a restore, never a rewrite: A changed `timeout = 30` to 60, and a stale copy put
    `timeout = 30 #s` back. Whatever the ratio, a new line whose operators or negation differ
    from the lost line is a different claim and never excuses it (`x < 5` to `x >= 5`, `do not`
    to `do`). Numbers differ only in the `modified` case, the third value above."""
    num, ops, neg = kinds(line)
    for o, n in hs:
        if line not in o:
            continue
        new = [g for g in n if not any(g in c for c in base) and not trailing_only(g, base)]
        if wrapped(line, new):
            return True
        for g in new:
            gnum, gops, gneg = kinds(g)
            if (gops, gneg) != (ops, neg) or (gnum != num and not modified):
                continue
            if difflib.SequenceMatcher(None, line, g, autojunk=False).ratio() >= (0.8 if modified else 0.9):
                return True
    return False


def lost_lines(cwd, m):
    """[(path, parent, [line])] for merge commit m."""
    _, out = git(cwd, "rev-list", "--parents", "-n", "1", m)
    parents = out.split()[1:]
    if len(parents) < 2:
        return []
    if len(parents) > 2:
        raise Unknown("%s has %d parents; only two-parent merges are read" % (m[:9], len(parents)))
    rc, out = git(cwd, "merge-base", "--all", *parents, ok=(0, 1))
    bases = out.split() if rc == 0 else []
    found = []
    for p in parents:
        pool = pool_of(cwd, p, m)
        paths = set()
        for b in bases:
            paths |= set(raw_files(cwd, b, p))
        for path in sorted(paths):
            text_m = blob(cwd, m, path)
            flat = " ".join(text_m.split())  # a re-wrapped line still reads as a run of this
            in_p, in_m = counts(blob(cwd, p, path)), counts(text_m)
            in_b = [counts(blob(cwd, b, path)) for b in bases]
            lost, hs = [], None
            for l, n in in_p.items():
                if any(l in c for c in in_b):
                    continue
                missing = n - in_m.get(l, 0)
                if missing <= 0 or l in flat:
                    continue
                moved = min(missing, pool[l])
                pool[l] -= moved
                if missing > moved:
                    hs = hunks(cwd, p, m, path) if hs is None else hs
                    mod = any(l in hn and ho for b in bases for ho, hn in hunks(cwd, b, p, path))
                    if not rewritten(l, hs, in_b, mod):
                        lost.append(l)
            if lost:
                found.append((path, p, lost))
    return found


# -------------------------------------------------------------------- reversal

_hunks = {}


def hunks(cwd, old, new, path):
    """-U0 hunks of old->new on path as (old lines, new lines), whitespace-normalized. A hunk
    with no change after normalizing, or with no letter or digit, is dropped."""
    key = (cwd, old, new, path)
    if key not in _hunks:
        _, out = git(cwd, "diff", "-U0", "--no-color", "--no-renames", old, new, "--", path)
        res, cur = [], None
        for l in out.splitlines():
            if l.startswith("@@"):
                cur = ([], [])
                res.append(cur)
            elif cur and l.startswith("-") and not l.startswith("---"):
                cur[0].append(norm(l[1:]))
            elif cur and l.startswith("+") and not l.startswith("+++"):
                cur[1].append(norm(l[1:]))
        keep = []
        for o, n in res:
            o, n = tuple(x for x in o if x), tuple(x for x in n if x)
            if o != n and any(WORD.search(x) for x in o + n):
                keep.append((o, n))
        _hunks[key] = keep
    return _hunks[key]


class Commit:
    def __init__(self, cwd, sha, parent, subject):
        self.cwd, self.sha, self.parent, self.subject = cwd, sha, parent, subject
        self._files = None

    @property
    def files(self):
        if self._files is None:
            self._files = raw_files(self.cwd, *([self.parent] if self.parent else ["--root"]), self.sha)
        return self._files


def first_parent(cwd, rev, limit=0):
    a = ["log", "--first-parent", "--format=%H %P%x02%s"] + (["-n%d" % limit] if limit else []) + [rev]
    _, out = git(cwd, *a)
    res = []
    for line in out.splitlines():
        head, _, subj = line.partition("\x02")
        bits = head.split()
        res.append(Commit(cwd, bits[0], bits[1] if len(bits) > 1 else None, subj))
    return res


def misses(small, big):
    """Fewest lines of `small` that differ from `big`, over every run of `big` as long as `small`."""
    if not small:
        return 0
    if len(small) > len(big):
        return len(small)
    return min(sum(x != y for x, y in zip(small, big[i:])) for i in range(len(big) - len(small) + 1))


def undone(o, n, mine):
    """True when a hunk of `mine` reverses the earlier hunk (o -> n). Exact. Or the earlier hunk,
    whole and line for line, inside a bigger hunk that holds other edits (a stale value put back
    beside an edited neighbour). Or, with 6 lines or more, on all but one line (a re-worded line).
    Lines the earlier commit only added (o empty) count when this change removes them, edit
    beside them or not, unless the hunk re-wrote them."""
    for big_o, big_n in mine:
        if (big_o, big_n) == (n, o):
            return True
        if not o:
            if wrapped(" ".join(n), list(big_n)):
                continue  # the whole block survives, only its line breaks moved
            if n and misses(n, big_o) == 0 and any(not rewritten(l, [(big_o, big_n)]) for l in n):
                return True
            continue
        if misses(o, big_n) + misses(n, big_o) <= (1 if len(o) + len(n) >= 6 else 0):
            return True
    return False


def reversals(cwd, old, new, files, earlier):
    """[(path, how, earlier commit)] where old->new undoes a change an earlier commit made.
    A change with no non-blank difference is no undo, and neither is a removal whose lines
    old->new adds to another file (a move)."""
    found = []
    elsewhere = None
    for path, (a, b) in sorted(files.items()):
        touched = [e for e in earlier if path in e.files]
        mine = hunks(cwd, old, new, path) if touched else []
        for e in touched if mine else []:
            ea, eb = e.files[path]
            whole = ea == b and eb == a and a != b
            theirs = hunks(cwd, e.parent, e.sha, path) if e.parent else []
            if not whole and not any(undone(o, n, mine) for o, n in theirs):
                continue
            if elsewhere is None:
                elsewhere = pool_of(cwd, old, new)
            avail = elsewhere - collections.Counter(l for _, n in mine for l in n)  # gains in other files only
            gone = collections.Counter(l for o, _ in mine for l in o if any(l in n for _, n in theirs))
            if gone and all(avail[l] >= k for l, k in gone.items()):
                continue
            found.append((path, "whole file restored" if whole else "hunk reversed", e))
    return found


def fmt_rev(path, how, e):
    return "%s: %s, undoing %s %s" % (path, how, e.sha[:9], e.subject[:60])


def fmt_lost(m, path, p, lost):
    shown = "".join("\n      - " + l[:120] for l in lost[:3])
    return "%s: merge %s drops %d line(s) that parent %s added%s" % (path, m[:9], len(lost), p[:9], shown)


# ----------------------------------------------------------------------- modes


def resolve_upstream(cwd, upstream):
    if git(cwd, "rev-parse", "--verify", "-q", upstream + "^{commit}", ok=(0, 1))[0] == 0:
        return upstream
    if upstream == "origin/main" and git(cwd, "rev-parse", "--verify", "-q", "main^{commit}", ok=(0, 1))[0] == 0:
        return "main"
    raise Unknown("no %s here, nothing to compare against" % upstream)


def check(cwd, upstream, head):
    """(problem lines, ALLOWED notes); no problems is green. Raises Unknown. Reads only the commits
    upstream gained after the branch was cut: since the merge base, or since the branch's first
    commit was authored (a rebase keeps that date, so a rebased branch still reads them)."""
    if git(cwd, "rev-parse", "--is-shallow-repository")[1].strip() != "false":
        raise Unknown("the history is shallow; fetch with depth 0")
    upstream = resolve_upstream(cwd, upstream)
    h = git(cwd, "rev-parse", head + "^{commit}")[1].strip()
    if git(cwd, "merge-base", "--is-ancestor", h, upstream, ok=(0, 1))[0] == 0:
        return [], []  # at or behind upstream: nothing lands
    ok = allowed(cwd, "%s..%s" % (upstream, h))
    items = []
    for m in git(cwd, "rev-list", "--merges", "%s..%s" % (upstream, h))[1].split():
        items += [(x[0], fmt_lost(m, *x)) for x in lost_lines(cwd, m)]
    rc, out = git(cwd, "merge-tree", "--write-tree", upstream, h, ok=(0, 1))
    if rc == 0:
        old, new = upstream, out.split()[0]
    else:  # a conflict leaves no result to read: the branch's own diff off the merge base
        old, new = git(cwd, "merge-base", upstream, h)[1].strip(), h
    files = raw_files(cwd, old, new)
    base = git(cwd, "merge-base", upstream, h)[1].strip()
    cut = min(int(t) for t in git(cwd, "log", "--format=%at", "%s..%s" % (upstream, h))[1].split())
    n = max(int(git(cwd, "rev-list", "--count", "--first-parent", "%s..%s" % (base, upstream))[1]),
            int(git(cwd, "rev-list", "--count", "--first-parent", "--since=%d" % (cut - 1), upstream)[1]))
    earlier = first_parent(cwd, upstream, n) if n else []
    items += [(x[0], fmt_rev(*x)) for x in reversals(cwd, old, new, files, earlier)]
    bad, notes = judge(items, ok)
    return bad, notes


def history(cwd, rev, window):
    """(commits read, [problem line]) over a rev's first-parent line and every merge in it."""
    if git(cwd, "rev-parse", "--is-shallow-repository")[1].strip() != "false":
        raise Unknown("the history is shallow; fetch with depth 0")
    line = first_parent(cwd, rev)
    out = []
    for m in git(cwd, "rev-list", "--merges", rev)[1].split():
        out += ["%s %s" % (m[:9], t) for t in judge([(x[0], fmt_lost(m, *x)) for x in lost_lines(cwd, m)], allowed(cwd, m + "^!"))[0]]
    for i, c in enumerate(line):
        if not c.parent:
            continue
        files = {p: v for p, v in c.files.items()}
        ok_paths = allowed(cwd, c.sha + "^!")
        _, parents = git(cwd, "rev-list", "--parents", "-n", "1", c.sha)
        if len(parents.split()) > 2:
            ok_paths.update(allowed(cwd, "%s^1..%s^2" % (c.sha, c.sha)))
        found = reversals(cwd, c.parent, c.sha, files, line[i + 1:i + 1 + window] if window else line[i + 1:])
        out += ["%s %s" % (c.sha[:9], t) for t in judge([(x[0], fmt_rev(*x)) for x in found], ok_paths)[0]]
    return len(line), out


def main(argv):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--upstream", default="origin/main")
    ap.add_argument("--head", default="HEAD")
    ap.add_argument("--window", type=int, default=60, help="history mode only")
    ap.add_argument("--strict", action="store_true", help="unknown exits 1 (also when env CI is set)")
    ap.add_argument("--history", nargs="?", const="HEAD", metavar="REV")
    ap.add_argument("--repo", default=os.getcwd())
    a = ap.parse_args(argv)
    try:
        if a.history:
            n, hits = history(a.repo, a.history, a.window)
            print("\n".join(hits))
            print("silent-undo: %d commit(s) read, %d hit(s)." % (n, len(hits)))
            return 0
        problems, notes = check(a.repo, a.upstream, a.head)
    except Unknown as e:
        print("silent-undo: UNKNOWN: %s" % e)
        return 1 if (a.strict or os.environ.get("CI")) else 0
    for n in notes:
        print("silent-undo: " + n)
    for p in problems:
        print("silent-undo: FAIL: " + p)
    if problems:
        print("silent-undo: put the work back, or add the trailer `%s: <path> -- <reason>` to a commit message." % TRAILER)
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))

#!/usr/bin/env python3
"""Fails when a merge or branch silently drops or reverts earlier work. Stdlib and git only.

    python3 lint/check_silent_undo.py [--upstream origin/main] [--head HEAD] [--strict]
    python3 lint/check_silent_undo.py --history [REV] [--window 60]   # audit, always exit 0

Four reads, one verdict. Design: docs/decisions/silent-undo-check-design.md.

  lost lines  A merge commit M (in upstream..head) loses a line one parent added since the
              merge base: the line is absent from every base, M holds fewer copies than that
              parent, no other file of M gained it, it is no run of words re-wrapped inside
              the file, and no line of the same hunk reads 0.9 like it (a resolver's rewrite).
              Catches a conflict taken "ours", and a hand edit of a merge. Only a parent that
              upstream already holds counts: a line the branch alone added is the branch's own.
  reversal    The result of landing head on upstream puts a file back as it was before an
              earlier first-parent commit of upstream changed it: the exact blob (whole
              file), a -U0 hunk reversed on all but one line, or lines main only added
              that this change removes, even beside an edit. Reads only the commits
              upstream gained after the branch was cut: from where the branch's own
              first-parent line left main, up, that commit included. Catches
              `git revert`, a stale copy, and a rebase that took its own side (caught
              when the lost work is the rebase-base commit or later).
  revived     A note the branch deleted is back at head. The notes file merges by union (decision
              notes-merge-union), so a merge of the base can put a deleted note back with no conflict. A note is
              its slug (`- <slug>:` at line start), so a reworded copy counts. Copies are counted per slug. The
              branch's own non-merge commits (upstream..head) are replayed oldest first, each counted from its file
              state and its parent's. A slug is refused when its last count change was a delete and head holds more
              copies than that commit left. A note re-added by a non-merge commit passes, and so does a dedupe that
              keeps a copy. An edit in place changes no count, so it does not keep a note. A Drops-lines trailer
              for the notes path excuses a revived note only when its reason names the slug as `- <slug>`
              (`Drops-lines: docs/debts/notes.md -- the owner retired both - slug-a - slug-b`); every other revival
              stays refused, and the refusal says how to name it. Cost, per run and per
              notes path (lint/layout.py, kind debt-notes): a missing file at head, two git reads (`git show`, then
              `git ls-tree`). A file with no note, one read. A file with a note, two: `git show head:<file>` and one
              `git log` of upstream..head over the file. When that log names a commit, one `git cat-file --batch`
              process more (class Blobs) reads each commit's file and its parent's, one commit at a time, so at most
              two texts are held; each side whose tree lacks the file adds one `git ls-tree`. No process stays running.

  lost sentence  A non-merge commit that rewrites or folds a note drops a clause of the old text that the new text no longer
              holds (measure and threshold: HELD, in the lost-sentence section). A Drops-lines trailer for the notes path
              excuses it only when its reason names the slug as `- <slug>`. A plain retire is no finding. It adds no git
              read: it takes the texts the revived check already reads (revived_notes, its `each` hook).

A file git pairs as renamed (its own 50 percent similarity) is read as the same file: its edits
are the diff of old name to new name, as they would be in place. A file below that stays a delete and an add.

Blank lines and whitespace never count. The escape is a trailer in a commit message, one per
path: `Drops-lines: <path> -- <reason>`. The PR body is read too: the same line in it
excuses its path. A trailer or line with no reason excuses nothing. A deleted debt file is also excused by a
`Retire-run: <slug> -- <run URL>` line in the PR body's last paragraph that the debt-close check
(check_debt_retire.retired) accepts: a green run on the PR head or above, a Retire that holds. It needs a
run reader (run_state); with none, or a read that fails, the finding stays. Only a whole delete is excused, not a rename out of
the debts folder. Only the merge tool passes a PR body and a run reader: the CLI and CI read no body, as with a Drops-lines line
in the body, and CI's way out is a Drops-lines commit trailer. Each use prints
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
import shutil
import subprocess
import sys
import tempfile
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "hooks"))
try:
    import _nowindow  # the one home of a no-window child start (hooks/_nowindow.py)
except ImportError:  # a hook loads this file; a missing helper never stops that hook
    _nowindow = subprocess

TRAILER = "Drops-lines"
ZERO = "0" * 40
WORD = re.compile(r"[A-Za-z0-9]")


class Unknown(Exception):
    pass


def git(cwd, *a, ok=(0,)):
    # literal pathspecs: a path that starts with `:` is a name, never magic. surrogateescape keeps a non-UTF-8 name exact.
    r = _nowindow.run(["git", "-C", cwd, *a], capture_output=True, encoding="utf-8", errors="surrogateescape", env=dict(os.environ, GIT_LITERAL_PATHSPECS="1"))
    if r.returncode not in ok:
        raise Unknown("git %s failed: %s" % (" ".join(a[:3]), r.stderr.strip() or r.returncode))
    return r.returncode, r.stdout


def norm(line):
    return " ".join(line.split())


def counts(text):
    return collections.Counter(n for n in map(norm, text.splitlines()) if n)


def blob(cwd, rev, path):
    rc, out = git(cwd, "show", "%s:%s" % (rev, path), ok=(0, 128))
    return out if rc == 0 else absent(cwd, rev, path)


def absent(cwd, rev, path):
    """"" for a path the rev's tree does not list. A failed read of a listed path is Unknown, never empty text."""
    try:
        path.encode("utf-8")  # a non-UTF-8 name cannot be passed as an argument: the tree cannot be asked
    except UnicodeEncodeError:
        raise Unknown("the read of %s:%s failed, and the name is not UTF-8" % (rev[:9], path.encode("utf-8", "replace").decode()))
    listed = git(cwd, "ls-tree", rev, "--", path)[1].strip()
    # A gitlink is no blob: its text is "". git before 2.46 answers `cat-file --batch` for one whose commit is
    # absent with "missing" (newer git says "submodule"), so the same entry must read as "" here, not Unknown.
    if listed and all(ln.startswith("160000 commit ") and ln.split("\t", 1)[1:] == [path] for ln in listed.splitlines()):
        return ""
    if listed:
        raise Unknown("the read of %s:%s failed, though the tree lists it" % (rev[:9], path))
    return ""


ATTRIBUTION = "Generated with [Claude Code](https://claude.com/claude-code)"
POSTED_BY = re.compile(r"_Generated by \[Claude Code\]\([^()\s]+\)_")  # the GitHub posting tool's footer line, under a --- rule


def last_paragraph(pr_body):
    """The paragraph of a PR body that counts for a key line. The body reads as git reads a message: fenced blocks and
    <!-- --> comments drop out, then only the last paragraph counts, skipping closing paragraphs that hold only the
    Claude Code attribution line or the posting footer (a --- rule, then the Generated-by line, as one paragraph or two)."""
    prose = re.sub(r"^ {0,3}(```|~~~).*?(?:^ {0,3}\1[^\n]*|\Z)", "", pr_body, flags=re.M | re.S)  # an unclosed fence runs to the end
    prose = re.sub(r"<!--.*?(?:-->|\Z)", "", prose, flags=re.S)
    paras = re.split(r"\n[ \t]*\n", prose.replace("\r\n", "\n").strip())
    while len(paras) > 1:
        lines = [n for n in map(norm, paras[-1].splitlines()) if n]
        if lines == ["---", lines[-1]] and POSTED_BY.fullmatch(lines[-1]):
            paras.pop()
        elif len(paras) > 2 and len(lines) == 1 and POSTED_BY.fullmatch(lines[0]) and norm(paras[-2]) == "---":
            del paras[-2:]
        elif norm(paras[-1]).removeprefix("\U0001F916 ") == ATTRIBUTION:
            paras.pop()
        else:
            break
    return paras[-1]


def trailer_reasons(cwd, rng, pr_body=""):
    """{path: [reason, ...]} from every `Drops-lines: <path> -- <reason>` trailer on any commit of the range (a rev or a..b),
    and from such lines in pr_body (its last_paragraph), in the order read. A line with no reason is left out."""
    _, out = git(cwd, "log", "--format=%(trailers:key=" + TRAILER + ",valueonly,unfold)", rng)
    body = re.findall(r"^" + TRAILER + r":(.*)$", last_paragraph(pr_body), re.I | re.M | re.ASCII)
    res = {}
    for line in out.splitlines() + body:
        m = re.match(r"\s*(\S.*?)\s+--\s+(\S.*?)\s*$", line)
        if m:
            res.setdefault(m.group(1), []).append(m.group(2))
    return res


def allowed(cwd, rng, pr_body=""):
    """{path: reason} from `Drops-lines: <path> -- <reason>` trailers on any commit of the range
    (a rev or a..b), and from such lines in pr_body (its last_paragraph). A line with no reason excuses nothing.
    With two trailers for a path, the last one read is the reason shown."""
    return {p: rs[-1] for p, rs in trailer_reasons(cwd, rng, pr_body).items()}


NAMED = re.compile(r"(?:^|\s)-\s+([^\s:]+)")


def named_slugs(reasons):
    """The slugs the reasons of one path's trailers name, each as `- <slug>` after a space or at the start. A slug is read
    as the note form reads it (NOTE: no space, no colon), then trailing `,.;:` drops off, so `- slug,` and `- slug.` name `slug`.
    The match against a note is exact: a prefix of a slug, or a longer slug, names another note."""
    return {m.rstrip(",.;:") for r in reasons for m in NAMED.findall(r)} - {""}


def misplaced(cwd, rng):
    """Hint lines for commits of the range with a line that starts `Drops-lines:` and that git did not read as a trailer
    (it is not in the last paragraph, so it excuses nothing). A hint never excuses a finding."""
    key = re.compile(r"^" + TRAILER + r":", re.I | re.M | re.ASCII)  # git matches the key in ASCII case only: no U+017F for `s`
    try:  # the hint is an extra: a failed read of it never changes the verdict
        # One read and no --grep, which grep.patternType in the repo config would change. git refuses a NUL in a message, so
        # NUL splits each commit into sha, parsed trailers (keys, not values: an empty or folded trailer counts once), body.
        f = git(cwd, "log", "-z", "--no-show-signature", "--format=%H%x00%(trailers:key=" + TRAILER + ",unfold)%x00%B", rng)[1].split("\0")
    except Unknown:
        return []  # ponytail: a failed read gives no hint at all, and no note; the finding and its exit code stand
    return ["%s has a %s: line, read not as a trailer: put it in the last paragraph, with Co-Authored-By." % (sha[:9], TRAILER)
            for sha, got, body in zip(f[0::3], f[1::3], f[2::3])  # a record short of 3 fields (the closing NUL) drops out
            if len(key.findall(body)) > len(key.findall(got))]


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


def renamed(cwd, old, new, files):
    """{old path: (new path, old blob, new blob)} for the files git pairs as renamed between two revs. `files` is
    raw_files(old, new): with no deleted path there is no rename to read, and git is not asked. -M is explicit, so
    diff.renames in a config never moves the verdict; the 50 percent similarity is git's own, a file below it stays
    a delete and an add. A rename entry of `-z --raw` holds two paths, so this read cannot share raw_files' stride."""
    if not any(b == ZERO for _, b in files.values()):
        return {}
    _, out = git(cwd, "diff-tree", "-r", "-M", "-z", "--raw", "--no-abbrev", old, new)
    t, res, i = out.split("\0"), {}, 0
    while i < len(t) - 1:
        bits = t[i].split()
        if len(bits) < 5:
            break  # not a raw entry: the read is out of step, so no pair is better than a wrong one
        if bits[4][0] == "R":
            res[t[i + 1]] = (t[i + 2], bits[2], bits[3])
        i += 3 if bits[4][0] in "RC" else 2
    return res


# ------------------------------------------------------------------ lost lines


def pool_of(cwd, p, m):
    """Lines M holds more of than parent p, across all files: where a moved line went. A renamed file gains only
    its edits, so its surviving lines are no gain elsewhere."""
    _, out = git(cwd, "diff", "-U0", "--no-color", "-M", p, m)
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


def extends(line, g):
    """True when every token of line survives, in order, in g, starts the same way, and g adds no negation, so a line pasted into a comment is not one: the merge
    only added to the line (`subprocess.run(a, b)` became `subprocess.run(a, b, timeout=T)`)."""
    lt, gt = TOKEN.findall(line), TOKEN.findall(g)
    it = iter(gt)
    return bool(lt) and lt[0] == gt[0] and all(tok in it for tok in lt) and len(NEGATION.findall(g)) <= len(NEGATION.findall(line))


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
    from the lost line is a different statement and never excuses it (`x < 5` to `x >= 5`, `do not`
    to `do`). Numbers differ only in the `modified` case, the third value above."""
    num, ops, neg = kinds(line)
    for o, n in hs:
        if line not in o:
            continue
        new = [g for g in n if not any(g in c for c in base) and not trailing_only(g, base)]
        if wrapped(line, new):
            return True
        for g in new:
            if extends(line, g):
                return True
            gnum, gops, gneg = kinds(g)
            if (gops, gneg) != (ops, neg) or (gnum != num and not modified):
                continue
            if difflib.SequenceMatcher(None, line, g, autojunk=False).ratio() >= (0.8 if modified else 0.9):
                return True
    return False


OWN_LOOKUPS = 25  # per file: lost lines checked for a branch-only adder in one `git log -p` read; the rest count as lost


def changed(patch):
    """The normalized added and removed lines of a patch. Headers are skipped by state, never by prefix:
    a line is content only after the first `@@` of its file section, so `++i;` and `-- note` count."""
    res, in_hunk = [], False
    for l in patch.split("\n"):  # not splitlines: a form feed inside a line is no line break
        if l.startswith("diff --git "):
            in_hunk = False
        elif l.startswith("@@"):
            in_hunk = True
        elif in_hunk and l[:1] in ("+", "-"):
            res.append(norm(l[1:]))
    return res


def branch_only_lines(cwd, p, bases, path, lines, refs):
    """The subset of `lines` that only the branch added: for each, the commit that first added it on
    the way to parent p is reachable from none of refs (upstream and the default branch). A read that
    fails, or finds no adding commit, leaves the line out, so it counts. Unknown is never clear.
    One `git log -m -p` per file, read once: a commit is marked by a changed line (added or removed,
    as `-G` read it) that holds the line, whitespace-collapsed. `-m` lets a line that entered through
    a merge's own resolution show up. The oldest marked commit is the real adder: a line from main
    always has main's own commit in the range, older than any merge that carried it."""
    try:
        _, out = git(cwd, "log", "-m", "-p", "-U0", "--no-color", "--no-ext-diff", "--format=%x00%H", p, "--not", *bases, "--", path)
    except Unknown:
        return set()
    commits = []  # (sha, the changed lines of that diff, newline-joined)
    for chunk in out.split("\0")[1:]:  # NUL: a text diff never holds one
        sha, _, body = chunk.partition("\n")
        commits.append((sha.strip(), "\n".join(changed(body))))
    held, res = {}, set()
    for line in lines:
        sha = next((c for c, text in reversed(commits) if line in text), None)
        if sha is None:
            continue
        try:
            if sha not in held:
                held[sha] = all(git(cwd, "merge-base", "--is-ancestor", sha, r, ok=(0, 1))[0] == 1 for r in refs)
        except Unknown:
            held[sha] = False
        if held[sha]:
            res.add(line)
    return res


def branch_only(cwd, p, bases, path, line, refs):
    """True only when the commit that first added `line` on the way to parent p is held by none of refs."""
    return line in branch_only_lines(cwd, p, bases, path, [line], refs)


class Blobs:
    """Blob text by `rev:path` through one `git cat-file --batch` process; "" for a path the tree lacks."""

    def __init__(self, cwd):
        self.cwd = cwd
        try:
            self.proc = _nowindow.Popen(["git", "-C", cwd, "cat-file", "--batch"], stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
        except OSError as e:
            raise Unknown("git cat-file failed: %s" % e)

    def get(self, rev, path):
        if "\n" in path or "\r" in path:  # cat-file reads a line and strips a trailing CR
            return blob(self.cwd, rev, path)
        try:
            self.proc.stdin.write(("%s:%s\n" % (rev, path)).encode("utf-8", "surrogateescape"))
            self.proc.stdin.flush()
            line = self.proc.stdout.readline().rstrip(b"\r\n")
            if line.endswith(b" missing"):  # the reply names the spec, which may hold spaces
                return absent(self.cwd, rev, path)
            head = line.split()
            if len(head) > 1 and head[1] == b"submodule":  # a gitlink is no blob: its text is "" (`git show` cannot read it and exits 128)
                return ""
            if len(head) != 3 or not head[2].isdigit():  # an empty line is EOF: the process died
                raise Unknown("git cat-file gave no usable header for %s:%s: %r" % (rev[:9], path, line[:80]))
            size = int(head[2])
            data = self.proc.stdout.read(size + 1)  # the reply ends with a newline
        except OSError as e:
            raise Unknown("git cat-file failed on %s:%s: %s" % (rev[:9], path, e))
        if len(data) != size + 1:
            raise Unknown("git cat-file ended early on %s:%s" % (rev[:9], path))
        return data[:-1].decode("utf-8", "replace") if head[1] == b"blob" else ""

    def close(self):
        try:
            self.proc.stdin.close()
        except OSError:  # a dead process: the failure was already raised, never mask it here
            pass
        self.proc.stdout.close()
        self.proc.wait()


def lost_lines(cwd, m, refs=()):
    """[(path, parent, [line])] for merge commit m. With refs (upstream, then the default branch),
    a lost line whose adding commit no ref holds is the branch's own work and is skipped. The
    test is per line, not per parent: a parent the branch built on an integration branch can still
    carry main's lines."""
    _, out = git(cwd, "rev-list", "--parents", "-n", "1", m)
    parents = out.split()[1:]
    if len(parents) < 2:
        return []
    if len(parents) > 2:
        raise Unknown("%s has %d parents; only two-parent merges are read" % (m[:9], len(parents)))
    rc, out = git(cwd, "merge-base", "--all", *parents, ok=(0, 1))
    bases = out.split() if rc == 0 else []
    found = []
    blobs = Blobs(cwd)
    try:
        for p in parents:
            found += lost_in_parent(cwd, m, p, bases, refs, blobs)
    finally:
        blobs.close()
    return found


def lost_in_parent(cwd, m, p, bases, refs, blobs):
    """lost_lines for one parent p of merge m; blobs reads every file text."""
    found = []
    pool = pool_of(cwd, p, m)
    paths, from_base = set(), {}
    for b in bases:
        files = raw_files(cwd, b, p)
        paths |= set(files)
        # a path main renamed since the base is read in the base at its old name, or its unchanged lines look added
        from_base[b] = {new: (old, ob, nb) for old, (new, ob, nb) in renamed(cwd, b, p, files).items()}
    changed_pm = raw_files(cwd, p, m)
    paths &= set(changed_pm)  # a path whose blob is the same in p and m loses nothing
    pairs = renamed(cwd, p, m, changed_pm)
    for path in sorted(paths):
        dst = pairs[path][0] if path in pairs else path  # a renamed file is read at its new name
        text_m = blobs.get(m, dst)
        flat = " ".join(text_m.split())  # a re-wrapped line still reads as a run of this
        in_p, in_m = counts(blobs.get(p, path)), counts(text_m)
        in_b = [counts(blobs.get(b, from_base[b][path][0] if path in from_base[b] else path)) for b in bases]
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
                hs = (hunks(cwd, pairs[path][1], pairs[path][2]) if path in pairs else hunks(cwd, p, m, path)) if hs is None else hs
                mod = any(l in hn and ho for b in bases for ho, hn in (hunks(cwd, *from_base[b][path][1:]) if path in from_base[b] else hunks(cwd, b, p, path)))
                if not rewritten(l, hs, in_b, mod):
                    lost.append(l)
        if refs and lost:
            own = branch_only_lines(cwd, p, bases, path, lost[:OWN_LOOKUPS], refs)  # the rest count as lost, unread
            lost = [l for l in lost if l not in own]
        if lost:
            found.append((path, p, lost))
    return found


# -------------------------------------------------------------------- reversal

_hunks = {}


def hunks(cwd, old, new, path=None):
    """-U0 hunks of old->new on path as (old lines, new lines), whitespace-normalized. A hunk
    with no change after normalizing, or with no letter or digit, is dropped. With no path,
    old and new are two blobs: the edits of a renamed file, read across its two names."""
    key = (cwd, old, new, path)
    if key not in _hunks:
        _, out = git(cwd, "diff", "-U0", "--no-color", "--no-renames", old, new, *(() if path is None else ("--", path)))
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


progress = None  # a caller may set a callable(done, total): called before each file of reversals


def reversals(cwd, old, new, files, earlier):
    """[(path, how, earlier commit)] where old->new undoes a change an earlier commit made.
    A change with no non-blank difference is no undo, and neither is a removal whose lines
    old->new adds to another file (a move). A file git pairs as renamed is judged on its edits across the
    rename, as it would be in place; the finding keeps the old path, the one earlier commits name."""
    found = []
    elsewhere = None
    pairs = renamed(cwd, old, new, files)
    for i, (path, (a, b)) in enumerate(sorted(files.items())):
        if progress:
            progress(i + 1, len(files))
        touched = [e for e in earlier if path in e.files]
        dst, b = (pairs[path][0], pairs[path][2]) if path in pairs else (None, b)  # the target is the new blob, not 0000
        mine = (hunks(cwd, a, b) if dst else hunks(cwd, old, new, path)) if touched else []
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
            how = "file deleted" if b == ZERO else "whole file restored" if whole else "hunk reversed"
            found.append((path, how + (" (renamed to %s)" % dst if dst else ""), e))
    return found


def fmt_rev(path, how, e):
    return "%s: %s, undoing %s %s" % (path, how, e.sha[:9], e.subject[:60])


def fmt_lost(m, path, p, lost):
    shown = "".join("\n      - " + l for l in lost)
    return "%s: merge %s drops %d line(s) that parent %s added%s" % (path, m[:9], len(lost), p[:9], shown)


# --------------------------------------------------------------------- revived

NOTE = re.compile(r"^- ([^\s:]+):\s*(.*)$")


def note_bodies(lines):
    """[(slug, text after the slug)] for the note lines among `lines`. A slug is the `- <slug>:` at line start."""
    return [(m.group(1), m.group(2)) for m in map(NOTE.match, lines) if m]


def note_counts(text):
    """slug -> how many note lines carry it."""
    return collections.Counter(slug for slug, _ in note_bodies(text.splitlines()))


class SlugKept(str):
    """A problem line that only a trailer reason naming the note's slug excuses. It prints and compares as its text, and its
    class is the marker trailer_hint reads: the line can hold any text, so the footer never finds one by its words. It rides
    through check's (problems, notes) and the merge tool's memo of that answer unchanged."""


class Revived(SlugKept):
    """A revived note's problem line."""


class LostSentence(SlugKept):
    """A lost sentence's problem line."""


def revived_notes(cwd, upstream, head, named=None, kept=None, each=None):
    """[(notes path, Revived problem line)] for each note the branch lowered and head holds more copies of than it left. Notes are
    counted per slug. The branch's own non-merge commits (upstream..head) are replayed oldest first, each read from its file
    state and its parent's, never from diff lines. A commit that changes a slug's count is that slug's last event so far.
    The slug is refused when its last event lowered the count and head holds more copies than that commit left: a merge
    put a copy back. A last event that raised the count is a deliberate re-add and passes. An edit in place changes no
    count, so it keeps nothing: a sweep edit, such as a mass `Until:` change, would otherwise keep every revived note. A
    note with no `- <slug>:` form has no slug, so the check does not see it. The texts are read one commit at a time, so
    at most two are held at once. `named` is {notes path: slugs its Drops-lines trailers name as `- <slug>`}: a revived slug in
    it is left out, because the trailer excuses that note. The path's other revivals stay. `kept`, a list when given, gets
    (path, slug) for each revival a trailer excused, so the caller can print its ALLOWED line. `each`, when given, is called
    as each(path, sha, before, after, now) for every replayed commit with the texts this replay already read (the file
    at the commit's parent, at the commit, and at head), so the lost-sentence check adds no git read."""
    named = named or {}
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    import layout  # lazy, as retire_excuses loads check_debt_retire
    try:
        paths = layout.candidates(cwd, "debt-notes")
    except layout.LayoutError as e:
        raise Unknown("the notes file is not known: %s" % e)
    found = []
    for path in paths:
        now = blob(cwd, head, path)
        present = note_counts(now)
        if not present:
            continue
        # --full-history: a merge that brought the file back is TREESAME to the base's side, and default history
        # simplification would then drop the branch's own delete commit from the walk.
        _, out = git(cwd, "log", "--no-merges", "--full-history", "--reverse", "--format=%H %P", "%s..%s" % (upstream, head), "--", path)
        commits = [line.split() for line in out.splitlines() if line.strip()]
        if not commits:
            continue
        last = {}  # slug -> (commit, copies it left) for the last commit that lowered the slug's count
        blobs = Blobs(cwd)
        try:
            for sha, *parents in commits:
                before_text = blobs.get(sha + "^", path) if parents else ""  # a root commit has no parent
                after_text = blobs.get(sha, path)
                before, after = note_counts(before_text), note_counts(after_text)
                if each:
                    each(path, sha, before_text, after_text, now)
                for slug in present:
                    if after[slug] < before[slug]:
                        last[slug] = (sha, after[slug])
                    elif after[slug] > before[slug]:
                        last.pop(slug, None)
        finally:
            blobs.close()
        for slug in sorted(last):
            sha, left = last[slug]
            if present[slug] > left and slug in named.get(path, ()):
                if kept is not None:
                    kept.append((path, slug))
            elif present[slug] > left:
                found.append((path, Revived(("%s: note `%s`: head holds %d cop%s, and commit %s left %d. A merge put the extra back, and "
                              "an edit in place does not keep a note. Delete the extra %s to bring the count back to %d. To keep "
                              "it on purpose, delete it in one commit and add it back in a later commit, or keep the revived copy by naming its slug in a %s "
                              "trailer for %s: put `- %s` in the trailer's reason.")
                              % (path, slug, present[slug], "y" if present[slug] == 1 else "ies", sha[:9], left,
                                 "line" if present[slug] - left == 1 else "lines", left, TRAILER, path, slug))))
    return found


# --------------------------------------------------------------------- lost sentence

# Not a revival (a slug's count is the same) and not a lost line (no merge is involved): a non-merge commit rewrites a
# note line, and a clause the old line said is gone from the new one. It reads the texts revived_notes already reads,
# through its `each` hook, so it adds no git read: per run and per notes path, the revived check's own reads and no more.
#
# A removed note line is paired with each added line under the same slug or under a folding slug: an added line whose text
# names the removed slug. A removed line with no such pair is paired by text with an added line under a new slug (a rename):
# one of its clauses, with at least PAIR_WORDS content words and not the `Decision:` tag, is held by the added line at
# PAIR_HELD, the share of a clause that was reworded and not cut. A note retired in an earlier commit of the branch is paired
# the same way with a later commit's new notes. Shared topic words, a shared `Decision:` tag or a shared slug prefix never
# pair (unrelated notes share them). A removed line with no pair is a plain retire and is no finding. The line is cut into clauses at a
# sentence end, `;`, and `and`, `but`, `which`, `though`, `while`, `so`, so a clause that rides on the end of a sentence is
# judged on its own. A fragment of fewer than 3 content words joins its neighbour. A clause is held when at least HELD of its
# content words (stopwords out, a trailing `s` off) are among the content words of the pair, and every number token of it is. A reworded clause keeps most of
# its words (one word in five changed: 0.8). A dropped clause keeps only the words other clauses share with it (0.2 to 0.25
# in the two cases that began this check). 0.5 sits in the gap, so a clause that is reworded, split, merged or reflowed
# passes, and one that lost its point fails. A clause that head's text for the note holds is no finding: a later commit of
# the branch put it back.
HELD = 0.5
PAIR_HELD = 0.75
PAIR_WORDS = 5
GENERIC_SHARE = 0.1
GENERIC_MIN = 20
TAG_CLAUSE = re.compile(r"Decision\b", re.I)
CLAUSE_END = re.compile(r"(?<=[.!?])\s+|;\s*|,?\s+(?:and|but|though|although|which|while|so)\s+", re.I)
FIELD_LABEL = re.compile(r"\b[A-Z][a-z]+:(?:\s+none\b)?")
STOPWORDS = frozenset("a an the and or of to in on for is are was were be been it its this that these those with as at by from "
                      "which who also then so if but though although while when each every any".split())


def content_words(text):
    """The set of a text's words, lower case, without stopwords, without a note's field labels (a capitalised word before a colon,
    as `Fix:`, `Until:`, `Decision:`) and their filler, and without a trailing `s` on a word of 4 or more letters. A label is
    on every note, so it never says that a clause was kept."""
    words = (w.lower() for w in re.findall(r"[A-Za-z0-9]+", FIELD_LABEL.sub(" ", text)))
    return {w[:-1] if len(w) > 3 and w.endswith("s") and not w.endswith("ss") else w for w in words if w not in STOPWORDS}


def clauses(body):
    """The clauses of a note's text, each a string with at least 3 content words (a shorter fragment joins its neighbour)."""
    out, lead = [], ""
    for frag in (f.strip(" ,;") for f in CLAUSE_END.split(body)):
        if not frag:
            continue
        if len(content_words(frag)) < 3:
            if out:
                out[-1] += " " + frag
            else:
                lead = (lead + " " + frag).strip()
        else:
            out.append((lead + " " + frag).strip())
            lead = ""
    return out or ([lead] if lead else [])


def held(clause, words, share=HELD):
    """True when `words` hold at least `share` of the clause's content words and every one of its number tokens."""
    mine = content_words(clause)
    numbers = {w for w in mine if w.isdigit()}
    return not mine or (numbers <= words and len(mine & words) >= share * len(mine))


def names(text, slug):
    """True when `text` names the note `slug`: the slug stands alone, not inside a longer slug."""
    return re.search(r"(?<![\w-])%s(?![\w-])" % re.escape(slug), text) is not None


def renamed_to(body, added, old_slugs):
    """The added notes (slug, text) under a slug not in `old_slugs` that carry a clause of the removed note's `body`: the clause is
    no `Decision:` tag, has at least PAIR_WORDS content words, and the added text holds PAIR_HELD of them."""
    mine = [c for c in clauses(body) if not TAG_CLAUSE.match(c) and len(content_words(c)) >= PAIR_WORDS]
    return [x for x in added if x[0] not in old_slugs and any(held(c, content_words(x[1]), PAIR_HELD) for c in mine)]


def generic_words(now):
    """The content words that at least GENERIC_SHARE of head's note lines hold, when head has at least GENERIC_MIN of them. Such a
    word (`merge`, `read`, `name`) shows up in a line that has nothing to do with the clause, so it never says a clause moved."""
    notes = note_bodies(counts(now).elements())
    if len(notes) < GENERIC_MIN:
        return set()
    seen = collections.Counter(w for _, t in notes for w in content_words(t))
    return {w for w, n in seen.items() if n >= GENERIC_SHARE * len(notes)}


def dropped_in_pair(slug, body, pair, now, moved):
    """[(slug, [fold slugs], clause)] for the clauses of the removed note `body` that no line the branch added for it holds (`moved`,
    a list with the content words of each note line added or changed since the note was removed, so a clause moved into one note
    that is not in the pair still counts as kept; the lines are never pooled, or any clause would be held) and that head's text for the pair's notes lacks too."""
    slugs = {x[0] for x in pair}
    at_head = [t for s, t in note_bodies(counts(now).elements()) if s in slugs | {slug}]
    if not at_head:
        return []  # a later commit retired the note
    new_words, head_words = (set().union(*map(content_words, ts)) for ts in ([t for _, t in pair], at_head))
    generic = generic_words(now)
    return [(slug, sorted(slugs - {slug}), c) for c in clauses(body)
            if not held(c, new_words) and not held(c, head_words) and not any(held(c, w - generic) for w in moved)]


def dropped_clauses(before, after, now, pending=None):
    """[(slug, [fold slugs], clause)] for one commit's file texts (the parent's, the commit's, and head's): each clause of a
    removed note line that the commit's added lines (any note's, not only the pair's) no longer hold, and that head's text
    for the pair's notes does not hold either. See HELD above. `pending`, a list when given, is the removed notes
    [slug, text, words] that earlier commits of the branch left unpaired, `words` being the content words of each note line
    added since: a rename that spans commits pairs a later commit's new notes with them, and a note this commit leaves unpaired
    is added to it."""
    gone = note_bodies((counts(before) - counts(after)).elements())
    added = note_bodies((counts(after) - counts(before)).elements())
    old_slugs = set(note_counts(before))
    here = [content_words(t) for _, t in added]
    found = []
    for entry in list(pending or ()):  # earlier commits' unpaired notes, against this commit's new notes
        slug, body, moved = entry
        moved += here
        pair = renamed_to(body, added, old_slugs)
        if pair:
            pending.remove(entry)
            found += dropped_in_pair(slug, body, pair, now, moved)
    for slug, body in gone:
        pair = [x for x in added if x[0] == slug or names(x[1], slug)] or renamed_to(body, added, old_slugs)
        if pair:
            found += dropped_in_pair(slug, body, pair, now, here)
        elif pending is not None:
            pending.append([slug, body, list(here)])  # a plain retire, unless a later commit adds its rename
    return found


def gather_dropped(lost, path, found):
    """Fold dropped_clauses' answer into lost: {(path, slug): (fold slugs, [clause])}, one entry per note, each clause once."""
    for slug, folded, clause in found:
        slugs, clauses_ = lost.setdefault((path, slug), (set(), []))
        slugs.update(folded)
        if clause not in clauses_:
            clauses_.append(clause)


def lost_sentence_problem(path, slug, folded, dropped):
    return LostSentence(("%s: note `%s` loses %s when a commit rewrites it%s. Put %s back. To drop %s on purpose, name the note in a %s "
            "trailer for %s: put `- %s` in the trailer's reason."
            % (path, slug, "; ".join('"%s"' % c for c in dropped), " (folded into `%s`)" % "`, `".join(folded) if folded else "",
               "it" if len(dropped) == 1 else "them", "it" if len(dropped) == 1 else "them", TRAILER, path, slug)))


# ----------------------------------------------------------------------- modes


def resolve_upstream(cwd, upstream):
    if git(cwd, "rev-parse", "--verify", "-q", upstream + "^{commit}", ok=(0, 1))[0] == 0:
        return upstream
    if upstream == "origin/main" and git(cwd, "rev-parse", "--verify", "-q", "main^{commit}", ok=(0, 1))[0] == 0:
        return "main"
    raise Unknown("no %s here, nothing to compare against" % upstream)


def generated_page(cwd, head, paths, upstream="origin/main", tool=None):
    """(page path, True when head's copy equals what the generator writes for head's tree).
    The generator is the upstream's own lint/hook_catalog.py, never the head's: a head that edits the generator and
    regenerates the page must not pass on its own say. It runs against head's records, as a subprocess, in a checkout of
    upstream. When upstream has none, `tool` is the generator: the merge tool passes its own, the one that rebuilt the
    page. A standalone run passes none. A generator that is missing, fails, or reports a problem makes the page a finding (fail closed).
    A change to the generator itself thus needs a trailer. The generator runs only when `paths`, the paths with a finding, holds its page."""
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    import hook_catalog as gen
    if gen.RECORDS_PAGE not in paths:
        return gen.RECORDS_PAGE, False
    page = blob(cwd, head, gen.RECORDS_PAGE)
    tmp = tempfile.mkdtemp(prefix="undo-gen-")
    base, wt = os.path.join(tmp, "base"), os.path.join(tmp, "wt")
    try:
        git(cwd, "worktree", "add", "-q", "--detach", base, resolve_upstream(cwd, upstream))
        git(cwd, "worktree", "add", "-q", "--detach", wt, head)
        out = os.path.join(wt, *gen.RECORDS_PAGE.split("/"))
        if os.path.exists(out):
            os.remove(out)  # the generator writes nothing for a repo with no records: a stale copy must not stand in
        oracle = os.path.join(base, "lint", "hook_catalog.py")
        if not os.path.isfile(oracle) and tool:
            oracle = tool  # upstream has no generator: the merge tool's own, never the head's
        run = _nowindow.run([sys.executable, "-B", oracle, "--records-only", "--root", wt],
                             cwd=wt, capture_output=True, env=dict(os.environ, PYTHONDONTWRITEBYTECODE="1"))
        if run.returncode != 0 or not os.path.isfile(out):
            return gen.RECORDS_PAGE, False
        with open(out, encoding="utf-8", newline="") as f:
            return gen.RECORDS_PAGE, bool(page) and page == f.read()
    finally:
        for d in (base, wt):
            git(cwd, "worktree", "remove", "--force", d, ok=(0, 128))
        shutil.rmtree(tmp, ignore_errors=True)


def retire_excuses(cwd, upstream, head, pr_body, run_state, paths):
    """{debt path: reason} for deleted debts among `paths` whose `Retire-run` cite the debt-close check accepts (decision
    debt-close-runs-retire). Fails closed: no run reader, an unreadable debt read, or a missing check excuses nothing."""
    if run_state is None:
        return {}
    try:
        sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
        import check_debt_retire  # lazy: it imports this module at its top
        got = check_debt_retire.retired(cwd, upstream, head, pr_body, run_state, isolate=True, paths=paths)
    except Exception:  # ImportError, its Unknown, any failed read: a finding stays
        return {}
    return {p: why for p, why in got.items() if p in paths}


def check(cwd, upstream, head, default=None, tool=None, pr_body="", run_state=None, retire_head=None):
    """(problem lines, ALLOWED notes); no problems is green. Raises Unknown. Reads only the commits
    upstream gained after the branch was cut: from where the branch's own first-parent line left
    main, up, the fork commit included. The window starts at the fork point, never at a commit time (one-second resolution)."""
    if git(cwd, "rev-parse", "--is-shallow-repository")[1].strip() != "false":
        raise Unknown("the history is shallow; fetch with depth 0")
    upstream = resolve_upstream(cwd, upstream)
    h = git(cwd, "rev-parse", head + "^{commit}")[1].strip()
    if git(cwd, "merge-base", "--is-ancestor", h, upstream, ok=(0, 1))[0] == 0:
        return [], []  # at or behind upstream: nothing lands
    reasons = trailer_reasons(cwd, "%s..%s" % (upstream, h), pr_body)
    ok = {p: rs[-1] for p, rs in reasons.items()}
    refs = [upstream] + [r for r in ((default,) if default else ("origin/HEAD", "origin/main", "main")) if r != upstream and git(
        cwd, "rev-parse", "--verify", "-q", r + "^{commit}", ok=(0, 1))[0] == 0][:1]  # the default branch too
    items = []
    for m in git(cwd, "rev-list", "--merges", "%s..%s" % (upstream, h))[1].split():
        items += [(x[0], fmt_lost(m, *x)) for x in lost_lines(cwd, m, refs)]
    # A trailer excuses a notes path's revival only for the slugs it names, so a revival on a trailer's path skips the path judge.
    kept, lost, retired = [], {}, collections.defaultdict(list)
    revived = revived_notes(cwd, upstream, h, {p: named_slugs(rs) for p, rs in reasons.items()}, kept,
                            lambda path, sha, before, after, now: gather_dropped(lost, path, dropped_clauses(before, after, now, retired[path])))
    items += [x for x in revived if x[0] not in ok]
    forced = [x[1] for x in revived if x[0] in ok]
    rc, out = git(cwd, "merge-tree", "--write-tree", upstream, h, ok=(0, 1))
    if rc == 0:
        old, new = upstream, out.split()[0]
    else:  # a conflict leaves no result to read: the branch's own diff off the merge base
        old, new = git(cwd, "merge-base", upstream, h)[1].strip(), h
    files = raw_files(cwd, old, new)
    base = git(cwd, "merge-base", upstream, h)[1].strip()
    own = git(cwd, "rev-list", "--first-parent", "%s..%s" % (upstream, h))[1].split()
    if own:  # the fork point is where the branch's own first-parent line left main, even after it merged main back in
        rc, fork = git(cwd, "merge-base", upstream, own[-1] + "^", ok=(0, 1))
        base = fork.strip() if rc == 0 and fork.strip() else base
    n = int(git(cwd, "rev-list", "--count", "--first-parent", "%s..%s" % (base, upstream))[1]) + 1  # +1: the fork commit
    earlier = first_parent(cwd, upstream, n)
    items += [(x[0], fmt_rev(*x)) for x in reversals(cwd, old, new, files, earlier)]
    page, same = generated_page(cwd, h, {p for p, _ in items if p not in ok}, upstream, tool)
    if same:
        ok = dict(ok, **{page: "the page is the generator's output for the head"})
    open_paths = {p for p, _ in items if p not in ok}
    if open_paths:
        ok = dict(retire_excuses(cwd, upstream, retire_head or h, pr_body, run_state, open_paths), **ok)
    bad, notes = judge(items, ok)
    bad = forced + bad
    for (path, slug), (folded, dropped) in lost.items():  # only a trailer that names the slug excuses a dropped clause, not the path alone
        if slug in named_slugs(reasons.get(path, ())):
            why = next(r for r in reversed(reasons[path]) if slug in named_slugs([r]))
            notes.append("ALLOWED %s: %s (keeps the dropped clause of `%s`)" % (path, why, slug))
        else:
            bad.append(lost_sentence_problem(path, slug, sorted(folded), dropped))
    for path, slug in kept:  # a named revival is an excuse too: one ALLOWED line, with the reason that names the slug
        why = next(r for r in reversed(reasons[path]) if slug in named_slugs([r]))
        notes.append("ALLOWED %s: %s (keeps the revived note `%s`)" % (path, why, slug))
    return bad, notes + (misplaced(cwd, "%s..%s" % (upstream, h)) if bad else [])


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


def trailer_hint(problems):
    """The footer's extra sentence for a refusal that holds a revived note or a lost sentence, for the CLI and the merge tool
    alike: a path-only trailer cannot keep either, only a reason that names its slug can. Empty for any other refusal. Each is
    read by its class (SlugKept, from revived_notes and lost_sentence_problem), never by its text."""
    if any(isinstance(p, SlugKept) for p in problems):
        return "To keep a revived note or a dropped sentence, put `- <slug>` in the trailer's reason."
    return ""


def say(line):
    """The one home for printed output. A non-UTF-8 name holds surrogates, which a strict stream cannot encode:
    write them as backslash escapes, so the finding prints and the exit code holds."""
    enc = getattr(sys.stdout, "encoding", None) or "utf-8"
    print(line.encode(enc, "backslashreplace").decode(enc))


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
            say("\n".join(hits))
            say("silent-undo: %d commit(s) read, %d hit(s)." % (n, len(hits)))
            return 0
        problems, notes = check(a.repo, a.upstream, a.head)
    except Unknown as e:
        say("silent-undo: UNKNOWN: %s" % e)
        return 1 if (a.strict or os.environ.get("CI")) else 0
    for n in notes:
        say("silent-undo: " + n)
    for p in problems:
        say("silent-undo: FAIL: " + p)
    if problems:
        say(" ".join(["silent-undo: put the work back, or add the trailer `%s: <path> -- <reason>` to a commit message." % TRAILER,
                      trailer_hint(problems)]).rstrip())
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))

#!/usr/bin/env python3
"""Fails when a merge or branch silently drops or reverts earlier work. Stdlib and git only.

    python3 lint/check_silent_undo.py [--upstream BASE] [--head HEAD] [--strict] [--pr-body TEXT]   # no BASE: the branch's tracked upstream; its own pushed copy, a gone upstream or none: origin/main
    python3 lint/check_silent_undo.py --history [REV] [--window 60]   # audit, always exit 0

Three reads, one verdict. Design: docs/decisions/silent-undo-check-design.md.

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
              its slug (`- <slug>:` at line start), so a reworded copy counts; a `- ` line with no slug form is its
              whole stripped line. Copies are counted per slug. The
              branch's own non-merge commits (upstream..head) are replayed oldest first, each counted from its file
              state and its parent's. A slug is refused when its last count change was a delete and head holds more
              copies than that commit left. A note re-added by a non-merge commit passes, and so does a dedupe that
              keeps a copy. An edit in place changes no count, so it does not keep a note. Cost, per run and per
              notes path (lint/layout.py, kind debt-notes): a missing file at head, two git reads (`git show`, then
              `git ls-tree`). A file with no note, one read. A file with a note, two: `git show head:<file>` and one
              `git log` of upstream..head over the file. When that log names a commit, one `git cat-file --batch`
              process more (class Blobs) reads each commit's file and its parent's, one commit at a time, so at most
              two texts are held; each side whose tree lacks the file adds one `git ls-tree`. No process stays running.

A file git pairs as renamed (its own 50 percent similarity) is read as the same file: its edits
are the diff of old name to new name, as they would be in place. A file below that stays a delete and an add.

Blank lines and whitespace never count. The escape is a trailer in a commit message, one per
path: `Drops-lines: <path> -- <reason>`. The PR body is read too: the same line in it
excuses its path. A trailer or line with no reason excuses nothing. A deleted debt file is also excused by a
`Retire-run: <slug> -- <run URL>` line in the PR body's last paragraph that the debt-close check
(check_debt_retire.retired) accepts: a green run on the PR head or above, a Retire that holds. It needs a
run reader (run_state); with none, or a read that fails, the finding stays. Only a whole delete is excused, not a rename out of
the debts folder. Only the merge tool passes a run reader, so the CLI never excuses a Retire-run line. The CLI reads the PR body
from `--pr-body <text>`, else from the event file that env GITHUB_EVENT_PATH names (`.pull_request.body`; CI writes it, and
bin/ci-job writes one for a local lint run), so a Drops-lines line in the body counts there as it does at the merge. No path is an
empty body; a path that cannot be read as an event file is UNKNOWN, never an empty body. Each use prints
`ALLOWED <path>: <reason>`. On a branch it may be on any commit of the branch. In history it is
the commit, plus the branch it merged for a reversal.

A read that cannot run prints UNKNOWN. Exit 0 locally, exit 1 when env CI is set or with
--strict, and exit 1 always when the UNKNOWN carries a finding (ruling: unknown in CI is red).
"""
import argparse
import collections
import difflib
import json
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
    problems = ()  # findings the read made before it gave up; only check() sets them
    notes = ()


class Octopus(Unknown):
    """A merge with three or more parents, which lost_lines does not read. check() keeps going past it."""


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
SESSION_URL = re.compile(r"https://claude\.ai/code/session_[A-Za-z0-9_-]+", re.ASCII)  # Claude's closing session line, under the attribution
POSTED_BY = re.compile(r"_Generated by \[Claude Code\]\([^()\s]+\)_")  # the GitHub posting tool's footer line, under a --- rule


# One pass: a comment drops out, but a `<!--` inside a backtick code span (not crossing a blank line) or a one-line
# "double-quoted" string is text, and the span or string is kept whole. The scan is left to right, so a lone quote or
# backtick opens nothing, and an unclosed `<!--` still runs to the end.
_SPAN_OR_COMMENT = re.compile(r"<!--.*?(?:-->|\Z)|(`+)(?!`)(?:(?!\n[ \t]*\n).)*?(?<!`)\1(?!`)|\"[^\"\n]*\"", re.S)


def is_attribution(text):
    return text.removeprefix("\U0001F916 ") == ATTRIBUTION


def last_paragraph(pr_body):
    """The paragraph of a PR body that counts for a key line. The body reads as git reads a message: fenced blocks and
    <!-- --> comments drop out, then only the last paragraph counts, skipping closing paragraphs that hold only the
    Claude Code attribution line, the session URL line after it (its own paragraph or the attribution's next line), or the
    posting footer (a --- rule, then the Generated-by line, as one paragraph or two). A blank or emptied paragraph (what a skipped
    block leaves) is skipped when it is last, and it parts the rule from the Generated-by line."""
    prose = re.sub(r"^ {0,3}(```|~~~).*?(?:^ {0,3}\1[^\n]*|\Z)", "", pr_body, flags=re.M | re.S)  # an unclosed fence runs to the end
    prose = _SPAN_OR_COMMENT.sub(lambda m: "" if m.group().startswith("<!--") else m.group(), prose)
    paras = re.split(r"\n[ \t]*\n", prose.replace("\r\n", "\n").strip())
    while len(paras) > 1:
        if not norm(paras[-1]):  # blank or emptied: skipped, but it stays in the list when it is not last, so it parts the footer's lines
            paras.pop()
            continue
        lines = [n for n in map(norm, paras[-1].splitlines()) if n]
        if lines == ["---", lines[-1]] and POSTED_BY.fullmatch(lines[-1]):
            paras.pop()
        elif len(paras) > 2 and len(lines) == 1 and POSTED_BY.fullmatch(lines[0]) and norm(paras[-2]) == "---":
            del paras[-2:]
        elif is_attribution(" ".join(lines)) or (len(lines) == 2 and is_attribution(lines[0]) and SESSION_URL.fullmatch(lines[1])):
            paras.pop()
        elif len(lines) == 1 and SESSION_URL.fullmatch(lines[0]) and is_attribution(([n for n in map(norm, paras[-2].splitlines()) if n] or [""])[-1]):
            paras.pop()  # the URL's own paragraph: only an attribution ending the paragraph above makes it closing text
        else:
            break
    return paras[-1] if paras else ""


def allowed(cwd, rng, pr_body=""):
    """{path: reason} from `Drops-lines: <path> -- <reason>` trailers on any commit of the range
    (a rev or a..b), and from such lines in pr_body (its last_paragraph). A line with no reason excuses nothing."""
    _, out = git(cwd, "log", "--format=%(trailers:key=" + TRAILER + ",valueonly,unfold)", rng)
    body = re.findall(r"^" + TRAILER + r":(.*)$", last_paragraph(pr_body), re.I | re.M | re.ASCII)
    res = {}
    for line in out.splitlines() + body:
        m = re.match(r"\s*(\S.*?)\s+--\s+(\S.*?)\s*$", line)
        if m:
            res[m.group(1)] = m.group(2)
    return res


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
    One `git log -m -p` per file, read once: a commit is marked by a changed line (added or removed)
    that equals the line, whole-line and whitespace-collapsed: a longer line that only contains it
    does not mark. `-m` lets a line that entered through
    a merge's own resolution show up. The oldest marked commit is the real adder: a line from main
    always has main's own commit in the range, older than any merge that carried it."""
    try:
        _, out = git(cwd, "log", "-m", "-p", "-U0", "--no-color", "--no-ext-diff", "--format=%x00%H", p, "--not", *bases, "--", path)
    except Unknown:
        return set()
    commits = []  # (sha, the set of that diff's normalized changed lines)
    for chunk in out.split("\0")[1:]:  # NUL: a text diff never holds one
        sha, _, body = chunk.partition("\n")
        commits.append((sha.strip(), set(changed(body))))
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
        raise Octopus("%s has %d parents; only two-parent merges are read" % (m[:9], len(parents)))
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


def unrestored(cwd, h, m, found, unspent):
    """lost_lines items of merge m less each line that head h holds again in the same path, at least as often as the parent
    held it. unspent (one dict per check(): (path, line) -> head copies not yet used) lets one head copy clear one loss."""
    if not found:
        return []
    blobs, out = Blobs(cwd), []
    try:
        for path, p, lines in found:
            if not blobs.get(m, path):  # the merge renamed or deleted the path: a head copy at that name restores nothing
                out.append((path, p, lines))
                continue
            in_p, at_h = counts(blobs.get(p, path)), counts(blobs.get(h, path))  # "" for a path the head lacks: nothing restored
            left = []
            for l in lines:
                if unspent.setdefault((path, l), at_h.get(l, 0)) >= in_p.get(l, 0):
                    unspent[(path, l)] -= in_p.get(l, 0)
                else:
                    left.append(l)
            if left:
                out.append((path, p, left))
    finally:
        blobs.close()
    return out


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
            own = branch_only_lines(cwd, p, bases, path, lost, refs)
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

NOTE = re.compile(r"^- ([^\s:]+):")


def note_key(line):
    """The key of a notes line: its slug (`- <slug>:` at line start), else a line that starts with `- ` by its whole stripped
    text, else None. A slug has no whitespace and a whole line starts with `- `, so the two never collide."""
    m = NOTE.match(line)
    if m:
        return m.group(1)
    return line.strip() if line.startswith("- ") and line[2:].strip() else None


def note_counts(text):
    """key -> how many note lines carry it. See note_key."""
    return collections.Counter(k for k in map(note_key, text.splitlines()) if k)


def revived_notes(cwd, upstream, head):
    """[(notes path, problem line)] for each note the branch lowered and head holds more copies of than it left. Notes are
    counted per slug. The branch's own non-merge commits (upstream..head) are replayed oldest first, each read from its file
    state and its parent's, never from diff lines. A commit that changes a slug's count is that slug's last event so far.
    The slug is refused when its last event lowered the count and head holds more copies than that commit left: a merge
    put a copy back. A last event that raised the count is a deliberate re-add and passes. An edit in place changes no
    count, so it keeps nothing: a sweep edit, such as a mass `Until:` change, would otherwise keep every revived note. A
    note that starts with `- ` but has no `- <slug>:` form is keyed by its whole stripped line, so it is counted and replayed
    the same way, and an edit of its text is a new note. The refusal names the whole line. The texts are read one commit at a time, so
    at most two are held at once."""
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    import layout  # lazy, as retire_excuses loads check_debt_retire
    try:
        paths = layout.candidates(cwd, "debt-notes")
    except layout.LayoutError as e:
        raise Unknown("the notes file is not known: %s" % e)
    found = []
    for path in paths:
        present = note_counts(blob(cwd, head, path))
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
                before = note_counts(blobs.get(sha + "^", path)) if parents else collections.Counter()  # a root commit has no parent
                after = note_counts(blobs.get(sha, path))
                for slug in present:
                    if after[slug] < before[slug]:
                        last[slug] = (sha, after[slug])
                    elif after[slug] > before[slug]:
                        last.pop(slug, None)
        finally:
            blobs.close()
        for slug in sorted(last):
            sha, left = last[slug]
            if present[slug] > left:
                found.append((path, "%s: note `%s`: head holds %d cop%s, and commit %s left %d. A merge put the extra back, and "
                              "an edit in place does not keep a note. Delete the extra %s to bring the count back to %d. To keep "
                              "it on purpose, delete it in one commit and add it back in a later commit."
                              % (path, slug, present[slug], "y" if present[slug] == 1 else "ies", sha[:9], left,
                                 "line" if present[slug] - left == 1 else "lines", left)))
    return found


# ----------------------------------------------------------------------- modes


def resolve_upstream(cwd, upstream):
    if git(cwd, "rev-parse", "--verify", "-q", upstream + "^{commit}", ok=(0, 1))[0] == 0:
        return upstream
    if upstream == "origin/main" and git(cwd, "rev-parse", "--verify", "-q", "main^{commit}", ok=(0, 1))[0] == 0:
        return "main"
    raise Unknown("no %s here, nothing to compare against" % upstream)


DEFAULT_BASE = "origin/main"


def default_base(cwd, head):
    """(base, why) for a run with no --upstream: the branch's tracked upstream, so a branch stacked on another is judged
    against the branch it stacks on. The branch's own pushed copy is no base, and gives origin/main. The one rule: the
    upstream is the branch's own copy when branch.<name>.merge names the branch itself (refs/heads/<name>), or when the
    upstream's tip is the branch's tip (a branch pushed under another name, which keeps the old name in that key).
    A gone upstream (the key stays, the remote ref is pruned) and no tracking at all give origin/main too. A branch
    that is ahead of a copy pushed under another name reads as stacked: only the PR's base tells them apart.
    The branch is read by its full name (refs/heads/<name>), so a tag named like it cannot make the name ambiguous;
    `<name>@{upstream}` looks up the branch only, and the upstream comes back as a full ref for the same reason."""
    if head == "HEAD":
        ref = git(cwd, "symbolic-ref", "-q", "HEAD", ok=(0, 1))[1].strip()
    else:
        ref = next((r for r in (head, "refs/heads/" + head) if r.startswith("refs/heads/")
                    and git(cwd, "rev-parse", "--verify", "-q", r + "^{commit}", ok=(0, 1))[0] == 0), "")
    if not ref:
        return DEFAULT_BASE, "no tracked upstream: %s is no branch" % head
    name = ref[len("refs/heads/"):]
    merge = git(cwd, "config", "--get", "branch.%s.merge" % name, ok=(0, 1))[1].strip()
    if not merge:
        return DEFAULT_BASE, "no tracked upstream"
    rc, up = git(cwd, "rev-parse", "--symbolic-full-name", name + "@{upstream}", ok=(0, 128))
    up = up.strip()
    if rc != 0 or not up:
        remote = git(cwd, "config", "--get", "branch.%s.remote" % name, ok=(0, 1))[1].strip()
        kept = merge[len("refs/heads/"):] if merge.startswith("refs/heads/") else merge
        stored = merge if remote == "." else "refs/remotes/%s/%s" % (remote, kept)
        if remote and git(cwd, "rev-parse", "--verify", "-q", stored, ok=(0, 1))[0] != 0:
            return DEFAULT_BASE, "the upstream of %s, %s on %s, is gone" % (name, merge, remote)
        return DEFAULT_BASE, "the upstream of %s cannot be read" % name
    if merge == ref:
        return DEFAULT_BASE, "%s tracks its own pushed copy" % name
    if git(cwd, "rev-parse", ref + "^{commit}")[1] == git(cwd, "rev-parse", up + "^{commit}", ok=(0, 128))[1]:
        return DEFAULT_BASE, "the upstream tip equals the branch tip"
    return up, "the branch's tracked upstream"


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
    """(problem lines, ALLOWED notes); no problems is green. Raises Unknown; for a merge of three or more parents it raises
    only after every other read, with the findings in .problems and .notes. Reads only the commits
    upstream gained after the branch was cut: from where the branch's own first-parent line left
    main, up, the fork commit included. The window starts at the fork point, never at a commit time (one-second resolution)."""
    if git(cwd, "rev-parse", "--is-shallow-repository")[1].strip() != "false":
        raise Unknown("the history is shallow; fetch with depth 0")
    upstream = resolve_upstream(cwd, upstream)
    h = git(cwd, "rev-parse", head + "^{commit}")[1].strip()
    if git(cwd, "merge-base", "--is-ancestor", h, upstream, ok=(0, 1))[0] == 0:
        return [], []  # at or behind upstream: nothing lands
    ok = allowed(cwd, "%s..%s" % (upstream, h), pr_body)
    refs = [upstream] + [r for r in ((default,) if default else ("origin/HEAD", "origin/main", "main")) if r != upstream and git(
        cwd, "rev-parse", "--verify", "-q", r + "^{commit}", ok=(0, 1))[0] == 0][:1]  # the default branch too
    items, octopus, unspent = [], [], {}
    for m in git(cwd, "rev-list", "--merges", "%s..%s" % (upstream, h))[1].split():
        try:
            items += [(x[0], fmt_lost(m, *x)) for x in unrestored(cwd, h, m, lost_lines(cwd, m, refs), unspent)]
        except Octopus as e:  # the other reads still run: their findings must not hide behind this one
            octopus.append(str(e))
    items += revived_notes(cwd, upstream, h)
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
    notes += misplaced(cwd, "%s..%s" % (upstream, h)) if bad else []
    if octopus:
        e = Octopus("; ".join(octopus))
        e.problems, e.notes = bad, notes
        raise e
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


def say(line):
    """The one home for printed output. A non-UTF-8 name holds surrogates, which a strict stream cannot encode:
    write them as backslash escapes, so the finding prints and the exit code holds."""
    enc = getattr(sys.stdout, "encoding", None) or "utf-8"
    print(line.encode(enc, "backslashreplace").decode(enc))


def event_body(environ=None):
    """The pull request body of the event file that GITHUB_EVENT_PATH names, "" when no path is set. Raises Unknown when the file
    cannot be read, is not JSON, or holds no pull request: the body is then unread, never empty."""
    path = (os.environ if environ is None else environ).get("GITHUB_EVENT_PATH")
    if not path:
        return ""
    try:
        with open(path, encoding="utf-8") as f:
            pull = json.load(f).get("pull_request")
        if not isinstance(pull, dict):
            raise ValueError("no pull_request object")
        body = pull.get("body")
        if body is not None and not isinstance(body, str):
            raise ValueError("pull_request.body is not text")
    except (OSError, ValueError, AttributeError) as e:
        raise Unknown("cannot read the pull request body from the event file %s: %s" % (path, e))
    return body or ""


def main(argv):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--upstream", help="the base to compare against; default: the branch's tracked upstream, else origin/main")
    ap.add_argument("--head", default="HEAD")
    ap.add_argument("--window", type=int, default=60, help="history mode only")
    ap.add_argument("--strict", action="store_true", help="unknown exits 1 (also when env CI is set)")
    ap.add_argument("--history", nargs="?", const="HEAD", metavar="REV")
    ap.add_argument("--repo", default=os.getcwd())
    ap.add_argument("--pr-body", default=None, metavar="TEXT", help="the pull request body (default: the event file named by env GITHUB_EVENT_PATH)")
    a = ap.parse_args(argv)
    try:
        if a.upstream is None and not a.history:
            a.upstream, why = default_base(a.repo, a.head)
            used = resolve_upstream(a.repo, a.upstream)  # the ref check() will read: local main when there is no origin
            say("silent-undo: base: %s (%s)" % (re.sub("^refs/(heads|remotes)/", "", used), why))
        if a.history:
            n, hits = history(a.repo, a.history, a.window)
            say("\n".join(hits))
            say("silent-undo: %d commit(s) read, %d hit(s)." % (n, len(hits)))
            return 0
        pr_body = a.pr_body if a.pr_body is not None else event_body()
        problems, notes = check(a.repo, a.upstream, a.head, pr_body=pr_body)
    except Unknown as e:
        for n in e.notes:
            say("silent-undo: " + n)
        for p in e.problems:
            say("silent-undo: FAIL: " + p)
        if e.problems:
            say("silent-undo: put the work back, or add the trailer `%s: <path> -- <reason>` to a commit message." % TRAILER)
        say("silent-undo: UNKNOWN: %s" % e)
        return 1 if (e.problems or a.strict or os.environ.get("CI")) else 0
    for n in notes:
        say("silent-undo: " + n)
    for p in problems:
        say("silent-undo: FAIL: " + p)
    if problems:
        say("silent-undo: put the work back, or add the trailer `%s: <path> -- <reason>` to a commit message." % TRAILER)
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))

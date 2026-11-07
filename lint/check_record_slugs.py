#!/usr/bin/env python3
"""Fails when a record file ADDED against origin/main has a slug over 32 characters.

Records live in the folders lint/layout.json marks as records. The UI crops long file names, so a slug is 32
characters or fewer, not counting `.md`. Existing files are not checked or renamed.

Also fails when a debt file deleted, renamed out of the debt folder, or edited to drop its Feel line against
origin/main was a feel-fix (a line starting `**Feel.**`) with no valid device-trial line (`**Device check.**`, then
simulator or device, then an ISO time with a zone): a fix CI passes can still feel wrong on a device.

    python3 lint/check_record_slugs.py [file ...]
        # files given: check those, skip git
    python3 lint/check_record_slugs.py --tree [--root R]
        # read the tree of R (default: this repo), not a diff; one `path:line CODE id` line per finding

Tree mode reads the decision and debt folders, CLAUDE.md and output-styles/*.md. An id is a slug of a decision, debt or
plan, or a `<!-- rule:x -->` anchor in CLAUDE.md or output-styles/*.md. It fails with:

    GLOSS001  the first cite of an id in a file, a backticked span that is exactly the id, has no short gloss. The
              gloss test is has_gloss in lint/report_guard.py, the one home that the cite-gloss guard also calls.
    DEBT001   a debt has no `**Decision.**` line.
    DEBT002   the Decision line is not a decision slug or `none` exactly: its first slug is not a decision, or `none`
              runs on into prose. A hint line under the findings says so.
    DEBT003   the Decision line names a decision that does not name the debt, by a code span that is exactly the debt's
              slug or by the slug as a whole word in the decision.
    DEBT004   the Decision line says `none` while a decision names the debt.

A cite inside a fenced block, an HTML comment or another code span is not a cite. The decision slug that opens a debt's
Decision line is a cite with or without backticks.

The functions take a repo root, so lint/compliance_probes.py reads a child's records with them.
"""
import datetime
import os
import re
import sys
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "hooks"))
import _nowindow  # noqa: E402  the one home of a no-window child start (hooks/_nowindow.py)
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import layout  # noqa: E402  the one home of where records live (lint/layout.json)
import report_guard  # noqa: E402  the one home of the gloss test, has_gloss (lint/report_guard.py)

MAX = 32
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


class Unknown(Exception):
    """A git read failed, so the added files are not known."""


def record_dirs(root):
    """The record folders of `root` as path prefixes. Raises layout.LayoutError when the layout cannot be read."""
    return tuple(folder + "/" for folder in layout.folders(root, "record"))


def git_names(root, *args):
    r = _nowindow.run(["git", *args], cwd=root, capture_output=True, encoding="utf-8", errors="replace")
    if r.returncode:
        raise Unknown("git %s failed: %s" % (args[0], r.stderr.strip()))
    return [name for name in r.stdout.split("\0") if name]


def changes(root, base="origin/main", head="HEAD"):
    """(added, moved) files of `root` from the merge base of `base` and `head` to `head`, from one process. `moved` holds
    (status, old, new) for each delete, modify and rename; a rename names two paths. -M is explicit, so diff.renames in a
    config never moves the verdict. Raises Unknown when git cannot say."""
    names = git_names(root, "diff", "--name-status", "-z", "-M", f"{base}...{head}")
    added, moved, i = [], [], 0
    while i < len(names):
        status = names[i]
        n = 2 if status[0] in "RC" else 1
        paths = names[i + 1:i + 1 + n]
        i += 1 + n
        if status == "A":
            added.append(paths[0])
        elif status[0] in "DMR":
            moved.append((status[0], paths[0], paths[-1]))
    return added, moved


def added(root):
    """The files `root` adds against its origin/main. Raises Unknown when git cannot say."""
    return changes(root)[0]


def marker(name=None):
    """The regex of a record's marker line: `**Name.**` at column one, or after `- `. With no name, any marker."""
    return re.compile(r"^(?:- )?\*\*" + (re.escape(name) if name else r"[^*]+") + r"\.\*\*")


FEEL = marker("Feel")
DECISION = marker("Decision")
TRIAL = re.compile(r"^(?:- )?\*\*Device check\.\*\*\s*(simulator|device)[,\s]+(\S+)\s*$")


def has_trial(line):
    """True for a device-trial line: the marker, simulator or device, then an ISO time with a zone."""
    m = TRIAL.match(line)
    if not m:
        return False
    try:
        return datetime.datetime.fromisoformat(m.group(2).replace("Z", "+00:00")).tzinfo is not None
    except ValueError:
        return False


def show(root, ref, path):
    r = _nowindow.run(["git", "show", ref + ":" + path], cwd=root, capture_output=True, encoding="utf-8",
                      errors="replace")
    if r.returncode:
        raise Unknown("git show failed: %s" % r.stderr.strip())
    return r.stdout.splitlines()


def debt_file(root):
    """A test of a path: is it a debt file of `root`? The folders are layout.candidates: the first one that exists, then the layout's own.
    A repo that legacy-repos keeps its debts elsewhere has that one folder: the layout's own is not where its debts are.
    The folder's README and notes file sit beside the debts but are not debts: never checked, never shown."""
    kept = layout.unmoved(root).get("debts")
    dirs = tuple(p + "/" for p in ((kept,) if kept else layout.candidates(root, "debts")))
    not_debts = {d + "README.md" for d in dirs} | set(layout.candidates(root, "debt-notes"))
    return lambda f: f.startswith(dirs) and f.endswith(".md") and f not in not_debts


def unchecked_feel_debts(root, moved):
    """[(path, how)] for each debt whose origin/main text has a Feel line and no valid device-trial line, and that
    the branch deletes or renames out of the debt folder ("deleted"), or edits or renames inside it so the Feel
    line is gone ("dropped"). Markers count at line start, with an optional "- ". Raises Unknown when git cannot
    show a file."""
    debt = debt_file(root)
    out = []
    for status, old, new in moved:
        if not debt(old):
            continue
        lines = show(root, "origin/main", old)
        if not any(FEEL.match(l) for l in lines) or any(has_trial(l) for l in lines):
            continue
        if status == "D" or not debt(new):
            out.append((old, "deleted"))
        elif not any(FEEL.match(l) for l in show(root, "HEAD", new)):
            out.append((new, "dropped"))
    return out


def tracked(root):
    return git_names(root, "ls-files", "-z")


def too_long(files, dirs):
    """The record files among `files` whose slug is over MAX characters. Same normpath as
    lint/check_ruling_kind.py, so ./decisions/x.md is judged like decisions/x.md."""
    return [f for f in files if os.path.normpath(f).replace("\\", "/").startswith(dirs)
            and f.endswith(".md") and len(os.path.basename(f.replace("\\", "/"))[:-3]) > MAX]


OUTPUT_STYLES = "output-styles/"  # beside CLAUDE.md, the other file that carries rule anchors
ANCHOR = re.compile(r"<!--\s*rule:([\w.-]+)\s*-->")
SPAN = re.compile(r"(`+)(?!`)((?:[^\n]|\n(?!\s*\n))+?)(?<!`)\1(?!`)")  # a code span; it may run over a line break
FENCE = re.compile(r"^ {0,3}(`{3,}|~{3,})")
SLUG_AT_START = re.compile(r"`([^`\n]+)`|([a-z0-9][a-z0-9-]*)")
GLOSS_WINDOW = 80  # the characters of context on each side of a cite, as the cite-gloss guard reads them


def blank(text):
    """`text` with each character but a line break turned into a space, so offsets and line numbers stay."""
    return re.sub(r"[^\n]", " ", text)


def unfenced(text):
    """`text` with each fenced block and each HTML comment blanked, so a cite in either is no cite."""
    out, fence = [], None
    for line in text.split("\n"):
        m = FENCE.match(line)
        if fence:
            out.append(blank(line))
            if m and m.group(1)[0] == fence[0] and len(m.group(1)) >= len(fence) and not line.strip(fence[0] + " "):
                fence = None
        elif m:
            fence = m.group(1)
            out.append(blank(line))
        else:
            out.append(line)
    return re.sub(r"<!--.*?-->", lambda m: blank(m.group()), "\n".join(out), flags=re.S)


def spans(text):
    """[(start, end, content)] of each code span of `text`, which `unfenced` has already read."""
    return [(m.start(), m.end(), m.group(2)) for m in SPAN.finditer(text)]


def decision_line(clean):
    """(offset, line) of the first Decision line of `clean`, which `unfenced` has already read, else None. The line is
    stripped; the offset is where it starts in `clean`."""
    offset = 0
    for raw in clean.split("\n"):
        line = raw.strip()
        if DECISION.match(line):
            return offset + len(raw) - len(raw.lstrip()), line
        offset += len(raw) + 1
    return None


def bare_decision_cite(clean):
    """[(start, end, slug)] for the slug that opens the Decision line of `clean` when it has no backticks, else []."""
    found = decision_line(clean)
    if not found:
        return []
    offset, line = found
    at = DECISION.match(line).end()
    at += len(line[at:]) - len(line[at:].lstrip())
    m = SLUG_AT_START.match(line, at)
    if not m or not m.group(2):
        return []
    return [(offset + m.start(2), offset + m.end(2), m.group(2))]


def first_cites(text, ids, bare=False):
    """[(line, id, glossed)] for the first cite of each id of `ids` in `text`. A cite is a code span that is exactly
    the id; with `bare`, also the slug that opens the Decision line when it has no backticks. The context for the gloss
    test is the text with every code span blanked, as the cite-gloss guard reads it."""
    clean = unfenced(text)
    found = spans(clean)
    plain = clean
    for start, end, _ in reversed(found):
        plain = plain[:start] + blank(plain[start:end]) + plain[end:]
    if bare:
        found = sorted(found + bare_decision_cite(clean))
    seen, out = set(), []
    for start, end, content in found:
        if content in ids and content not in seen:
            seen.add(content)
            glossed = report_guard.has_gloss(plain[max(0, start - GLOSS_WINDOW):start], plain[end:end + GLOSS_WINDOW])
            out.append((clean.count("\n", 0, start) + 1, content, glossed))
    return out


def read(root, rel):
    with open(os.path.join(root, *rel.split("/")), encoding="utf-8", errors="replace") as f:
        return f.read()


def tree_findings(root):
    """The findings of the tree at `root`, as `path:line CODE id` strings in file order. Raises layout.LayoutError when
    the layout cannot be read and Unknown when the file list cannot be read."""
    folder = {kind: layout.path(root, kind) + "/" for kind in ("decisions", "plans")}  # the layout first: red when unreadable
    is_debt = debt_file(root)
    claude = layout.path(root, "claude-md")
    files = [f for f in tracked(root) if f.endswith(".md")]

    def slugs(prefix):
        return {os.path.basename(f)[:-3]: f for f in files
                if f.startswith(prefix) and "/" not in f[len(prefix):] and not f.endswith("/README.md")}

    decisions, plans = slugs(folder["decisions"]), slugs(folder["plans"])
    debts = {os.path.basename(f)[:-3]: f for f in files if is_debt(f)}
    rule_files = ([claude] if claude in files else []) + \
                 [f for f in files if f.startswith(OUTPUT_STYLES) and "/" not in f[len(OUTPUT_STYLES):]]
    anchors = set()
    for f in rule_files:
        anchors.update(ANCHOR.findall(read(root, f)))
    ids = set(decisions) | set(debts) | set(plans) | anchors

    out, naming = [], {}  # naming: the decisions that name each debt, by a span that is exactly its slug
    scanned = [(f, slug) for slug, f in decisions.items()] + [(f, slug) for slug, f in debts.items()] + \
              [(f, None) for f in rule_files]
    for f, own in scanned:
        for line, ident, glossed in first_cites(read(root, f), ids - {own}, bare=f in debts.values()):
            if not glossed:
                out.append("%s:%d GLOSS001 %s" % (f, line, ident))
    for slug, f in decisions.items():
        clean = unfenced(read(root, f))
        for _, _, content in spans(clean):
            if content in debts:
                naming.setdefault(content, set()).add(slug)
        for debt in debts:
            if re.search(r"(?<![\w-])%s(?![\w-])" % re.escape(debt), clean):
                naming.setdefault(debt, set()).add(slug)
    for slug, f in debts.items():
        lines = [l.strip() for l in unfenced(read(root, f)).split("\n")]
        at = next((i for i, l in enumerate(lines, 1) if DECISION.match(l)), 0)
        if not at:
            out.append("%s:1 DEBT001 %s" % (f, slug))
            continue
        rest = lines[at - 1][DECISION.match(lines[at - 1]).end():].strip()
        if re.fullmatch(r"(?:`none`|none)\.?", rest, re.I):
            if naming.get(slug):
                out.append("%s:%d DEBT004 %s" % (f, at, slug))
            continue
        m = SLUG_AT_START.match(rest)
        named = (m.group(1) or m.group(2)) if m else None
        if named not in decisions:
            out.append("%s:%d DEBT002 %s" % (f, at, named or slug))
        elif named not in naming.get(slug, ()):
            out.append("%s:%d DEBT003 %s" % (f, at, slug))
    return out


def main_tree(args):
    root = ROOT
    if args[:1] == ["--root"] and len(args) == 2:
        root = args[1]
    elif args:
        print("check_record_slugs: FAIL: usage: --tree [--root R]")
        return 1
    try:
        found = tree_findings(root)
    except layout.LayoutError as err:
        print("check_record_slugs: FAIL: " + str(err))
        return 1
    except Unknown as err:
        print("check_record_slugs: UNKNOWN, " + str(err))
        return 1 if os.environ.get("CI") else 0
    for line in found:
        print(line)
    if any(" DEBT002 " in line for line in found):
        print("DEBT002: the Decision line must be a decision slug or `none` exactly, with no prose after `none`.")
    return 1 if found else 0


def main(args):
    if args[:1] == ["--tree"]:
        return main_tree(args[1:])
    unknown = [a for a in args if a.startswith("-")]
    if unknown:  # read as a file name, an unknown option would skip git and check nothing
        print("check_record_slugs: FAIL: unknown option: %s" % " ".join(unknown))
        return 1
    try:
        dirs = record_dirs(ROOT)
    except layout.LayoutError as err:  # a check that cannot read its folders is red, never green
        print("check_record_slugs: FAIL: " + str(err))
        return 1
    try:
        if args:  # files given: git is not read, so the feel-fix check does not run
            files, feel = args, []
        else:
            files, moved = changes(ROOT)
            feel = unchecked_feel_debts(ROOT, moved)
    except layout.LayoutError as err:
        print("check_record_slugs: FAIL: " + str(err))
        return 1
    except Unknown as err:
        print("check_record_slugs: UNKNOWN, " + str(err))
        return 1 if os.environ.get("CI") else 0  # CI exit code is a verdict: unknown is red there
    bad = too_long(files, dirs)
    for f in bad:
        print("check_record_slugs: FAIL: slug over %d characters: %s" % (MAX, f))
    for f, how in feel:
        print("check_record_slugs: FAIL: feel-fix debt %s with no device check: %s"
              % ("deleted" if how == "deleted" else "lost its Feel line", f))
    return 1 if bad or feel else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))

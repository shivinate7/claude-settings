#!/usr/bin/env python3
"""Fails when a change closes a debt without proof that its Retire step holds. Stdlib and git only.

    python3 lint/check_debt_retire.py [--upstream origin/main] [--head HEAD] [--strict]

A debt is closed when its file is deleted, or renamed out of the debts folder (lint/layout.py, kind debts). The
check reads that debt's Retire paragraph from the base and runs what it names. A test must pass on the head and fail
on the debt's birth commit, the newest commit that added the debt file (the start of its current life, if the slug
was closed and added again). A test that passes on the birth commit does not catch the defect.

  runnable  a backticked span that is a test file (test_*.py, *_test.py, *.test.mjs, test_*.mjs, test_*.sh) runs as
            one argv, with no shell, under a timeout, first from the head folder, then from a scratch tree of the
            birth commit with the head's copy of the test laid over it. On the head, non-zero is red, and so is a
            python file that runs no test ("Ran 0 tests", or test_ functions and no __main__ block, exit 0).
            On the birth commit the test must fail: exit 0 is red (the test misses the defect). Python fails there on
            any non-zero exit, unless the output shows a top-level ImportError, ModuleNotFoundError or SyntaxError, or
            unittest errors with no failures (unknown). Node fails there on an assertion error (ERR_ASSERTION); an
            import error is unknown. Bash has no failure or error split, so it fails there on a non-zero exit only
            when the output shows no missing file or command (and the exit is not 126 or 127); otherwise unknown.
            A missing interpreter, a failed start, or a timeout is unknown. A span that names a test file the head does
            not track is red.
  prose     a Retire that names no runnable check holds the close, unless the PR body cites a run:
            `Retire-run: <slug> -- <run URL>`, read as the Drops-lines line of check_silent_undo is. The text after
            ` -- ` that starts with an http(s) URL is a run cite: the run must be green and on the PR head or a commit
            above it, and a note after the URL is ignored.
  reason    an unknown (a check that could not run here) is also cleared by `Retire-run: <slug> -- <reason>`, where the
            reason is any text that does not start with a URL. A red check is never cleared by a cite or a reason,
            and a reason never closes a prose Retire.

Exit 1 on any finding. Design: decision debt-close-runs-retire.
"""
import argparse
import contextlib
import os
import re
import shutil
import subprocess
import sys
import tempfile
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import check_record_slugs as records  # noqa: E402  the one home of the record markers and the changed-files read
import check_silent_undo as undo  # noqa: E402  the one home of the PR body's key-line reading
import layout  # noqa: E402  the one home of where the debts folder is
import _nowindow  # noqa: E402  the one home of a no-window child start (hooks/_nowindow.py; check_record_slugs puts hooks on the path)

Unknown = records.Unknown  # a git read failed, so the closes are not known
CITE = "Retire-run"
TIMEOUT = 600
# Each runnable suffix with the argv that starts it. The check never runs anything else.
INTERPRETERS = {".py": ["python3"], ".mjs": ["node", "--test"], ".sh": ["bash"]}
TEST_NAME = re.compile(r"^(?:test_[^/]+\.(?:py|mjs|sh)|[^/]+_test\.py|[^/]+\.test\.mjs)$")
SPAN = re.compile(r"`([^`\s]+)`")  # no space inside: a lone backtick in prose never swallows the real span after it
CITE_LINE = re.compile(r"\s*(\S+)\s+--\s+(\S.*?)\s*$")
RUN_URL = re.compile(r"https?://\S+")
GLOB = re.compile(r"[*?<>{}\[\]$]")  # a placeholder such as `test_*.py` names no file


class Finding:
    def __init__(self, slug, kind, text):
        self.slug, self.kind, self.text = slug, kind, text

    def __repr__(self):
        return "Finding(%r, %r)" % (self.slug, self.kind)


def retire_text(lines):
    """The Retire paragraph of a debt: its marker line and the lines after it, up to a blank line or the next marker."""
    retire, any_marker = records.marker("Retire"), records.marker()
    out = []
    for line in lines:
        if out and (not line.strip() or any_marker.match(line)):
            break
        if out or retire.match(line):
            out.append(line)
    return " ".join(" ".join(out).split())


def spans(text):
    """The backticked test files of `text`, in order, each once. The head may not track them."""
    found = []
    for s in SPAN.findall(text):
        s = s[2:] if s.startswith("./") else s
        if TEST_NAME.match(os.path.basename(s)) and os.path.splitext(s)[1] in INTERPRETERS and not GLOB.search(s) and s not in found:
            found.append(s)
    return found


def birth_commit(wt, ref, path):
    """The newest commit of `ref` that added `path`, following renames: the start of its current life, when a slug was
    closed and added again. Raises Unknown when git cannot say."""
    added = records.git_names(wt, "log", "-z", "--follow", "--diff-filter=A", "--format=%H", ref, "--", path)
    if not added:
        raise Unknown("no commit that added %s is in the history of %s" % (path, ref))
    return added[0]


@contextlib.contextmanager
def scratch(wt, head):
    """A detached worktree of `head` under the temp dir, removed after: what a Retire test writes stays there and never reaches `wt`.
    A tree that cannot be made yields None, and the test is unknown."""
    tmp = tempfile.mkdtemp(prefix="debt-retire-")
    tree = os.path.join(tmp, "tree")
    try:
        made = _nowindow.run(["git", "-C", wt, "worktree", "add", "-q", "--detach", tree, head], capture_output=True).returncode == 0
        yield tree if made else None
    finally:
        _nowindow.run(["git", "-C", wt, "worktree", "remove", "--force", tree], capture_output=True)
        shutil.rmtree(tmp, ignore_errors=True)


def start(wt, span, timeout):
    """(finished process, None), or (None, (kind, text)) when the test could not run."""
    argv = list(INTERPRETERS[os.path.splitext(span)[1]])
    exe = shutil.which(argv[0])
    if not exe:
        return None, ("unknown", "%s is not on PATH, so %s did not run" % (argv[0], span))
    try:
        return _nowindow.run([exe, *argv[1:], span], cwd=wt, capture_output=True, encoding="utf-8", errors="replace",
                             timeout=timeout, env=dict(os.environ, PYTHONDONTWRITEBYTECODE="1")), None
    except subprocess.TimeoutExpired:
        return None, ("unknown", "%s ran past %d s" % (span, timeout))
    except OSError as e:
        return None, ("unknown", "%s did not start: %s" % (span, e))


def run_span(wt, span, timeout):
    """(kind, text) for one test on the head: red on a non-zero exit, unknown when it could not run, else None."""
    r, bad = start(wt, span, timeout)
    if bad:
        return bad
    if r.returncode:
        tail = " | ".join((r.stdout + r.stderr).strip().splitlines()[-5:])
        return "red", "%s exited %d%s" % (span, r.returncode, ": " + tail[:400] if tail else "")
    if span.endswith(".py"):  # a file that runs no test proves nothing, so exit 0 is not green
        if re.search(r"^Ran 0 tests", r.stderr, re.M):
            return "red", "%s ran no tests" % span
        try:
            with open(os.path.join(wt, span), encoding="utf-8", errors="replace") as f:
                src = f.read()
        except OSError:
            return None
        if re.search(r"^def test_", src, re.M) and "__main__" not in src:
            return "red", "%s defines test functions but nothing runs them (no __main__ block)" % span
    return None


def failed(span, r):
    """True when a non-zero run of `span` on the birth commit is the test failing, not the run erroring: the one fact the birth
    run needs. Anything that cannot be told apart from the defect is not a catch."""
    out = r.stdout + r.stderr
    suffix = os.path.splitext(span)[1]
    if suffix == ".py":
        m = re.search(r"^FAILED \((?:[^)]*, )?failures=(\d+)", out, re.M)
        if m and int(m.group(1)) >= 1:
            return True
        # Any other non-zero exit is a catch, unless the file never got to run its test: an import or syntax error at the top
        # level, or unittest errors with no failures.
        return not re.search(r"^(?:ImportError|ModuleNotFoundError|SyntaxError)\b", out, re.M) and not re.search(r"^FAILED \(errors=", out, re.M)
    if suffix == ".mjs":
        return "ERR_ASSERTION" in out
    # bash has no failure/error split, so a non-zero exit is a catch only when the output shows no missing file or command.
    return r.returncode not in (126, 127) and not re.search(r"No such file or directory|not found|can't open file", out)


def run_on_birth(wt, birth, head, span, timeout):
    """(kind, text) for one test on the birth commit, with the head's copy of it laid over: None when it fails there (the
    test catches the defect), red when it passes, unknown when it errors or could not run."""
    blob = _nowindow.run(["git", "-C", wt, "show", head + ":" + span], capture_output=True)
    with scratch(wt, birth) as tree:
        if blob.returncode or not tree:
            return "unknown", "no scratch tree of the birth commit %s for %s" % (birth[:9], span)
        os.makedirs(os.path.dirname(os.path.join(tree, span)), exist_ok=True)
        with open(os.path.join(tree, span), "wb") as f:
            f.write(blob.stdout)
        r, bad = start(tree, span, timeout)
    if bad:
        return bad
    if r.returncode == 0:
        return "red", "%s passes on the birth commit %s, so it does not catch the defect" % (span, birth[:9])
    if failed(span, r):
        return None
    tail = " | ".join((r.stdout + r.stderr).strip().splitlines()[-3:])
    return "unknown", "%s errored on the birth commit %s without failing a test: %s" % (span, birth[:9], tail[:300])


def cites(pr_body):
    """{debt slug: run URL or written reason} from the `Retire-run: <slug> -- <text>` lines of the PR body's last paragraph.
    The last cite of a slug wins."""
    res = {}
    for line in re.findall(r"^" + CITE + r":(.*)$", undo.last_paragraph(pr_body), re.I | re.M | re.ASCII):
        m = CITE_LINE.match(line)
        if m:
            res[m.group(1)] = m.group(2)
    return res


def cite_url(text):
    """The run URL a cite's text starts with (a note after it is ignored), or None when the text is a written reason."""
    m = RUN_URL.match(text)
    return m.group(0) if m else None


def judge_run(wt, head, url, run_state):
    """(kind, text) for a cited run, or None when it is green on the head or a commit above it."""
    if run_state is None:
        return "unknown", "no reader for the cited run %s" % url
    try:
        conclusion, sha = run_state(url)
    except Exception as e:  # any failed read: the run is unknown, never clear
        return "unknown", "the cited run %s could not be read: %s" % (url, " ".join(str(e).split()))
    if conclusion != "success":
        return "red", "the cited run %s ended %s, not success" % (url, conclusion)
    rc = _nowindow.run(["git", "-C", wt, "merge-base", "--is-ancestor", head, str(sha)], capture_output=True).returncode
    if rc == 0:
        return None
    if rc == 1:
        return "red", "the cited run %s is on %s, not on the PR head %s or a commit above it" % (url, str(sha)[:9], head[:9])
    return "unknown", "the cited run %s is on %s, which this checkout does not hold" % (url, str(sha)[:9])


def judge_tests(wt, head, ref, old, todo, tracked, timeout, isolate):
    """(kind, text) for the tests a closed debt's Retire names, or None when each passes on the head and fails on the birth
    commit of the debt file `old` (found from `ref`). A red outranks an unknown, whatever the order."""
    missing = [s for s in todo if s not in tracked]
    if missing:
        return "red", "names %s, which the head does not track" % ", ".join(missing)
    got = None
    for span in todo:
        with scratch(wt, head) if isolate else contextlib.nullcontext(wt) as tree:
            one = run_span(tree, span, timeout) if tree else ("unknown", "no scratch worktree for %s" % span)
        if one and one[0] == "red":
            return one
        got = got or one
    try:
        birth = birth_commit(wt, ref, old)
    except Unknown as e:
        return got or ("unknown", str(e))
    for span in todo:
        one = run_on_birth(wt, birth, head, span, timeout)
        if one and one[0] == "red":
            return one
        got = got or one
    return got


def check(wt, base_ref, head="HEAD", timeout=TIMEOUT, pr_body="", run_state=None, isolate=False):
    """[Finding] for each debt that `head` closes against `base_ref` and whose Retire step does not hold. Raises Unknown.
    run_state(url) -> (conclusion, head sha) of a workflow run, or raises.
    isolate: run each test in its own scratch worktree of `head` (the merge tool and the CLI do), so nothing it writes reaches `wt`;
    off, a test runs in `wt` itself."""
    try:
        debt = records.debt_file(wt)
    except layout.LayoutError as e:
        raise Unknown("the debts folder is not known: %s" % e)
    # A rename inside the folder is a close only when its Retire changed (decided below, once the texts are read).
    closed = [(old, new) for status, old, new in records.changes(wt, base_ref, head)[1]
              if debt(old) and (status == "D" or (status == "R" and (not debt(new) or new != old)))]
    if not closed:
        return []
    head = records.git_names(wt, "rev-parse", head + "^{commit}")[0].strip()
    mb = records.git_names(wt, "merge-base", base_ref, head)[0].strip()
    tracked = set(records.git_names(wt, "ls-tree", "-r", "-z", "--name-only", head))
    cited = cites(pr_body)
    found = []
    for old, new in closed:
        slug = os.path.basename(old)[:-3]
        ref = base_ref
        try:
            lines = records.show(wt, ref, old)  # the base tip's Retire, the one the base holds now
        except Unknown:
            ref = mb
            lines = records.show(wt, ref, old)  # the base tip no longer holds the file: the fork point's
        text = retire_text(lines)
        if new != old and debt(new) and text == retire_text(records.show(wt, head, new)):
            continue  # a rename inside the folder with its Retire unchanged
        todo = spans(text)
        if todo:
            got = judge_tests(wt, head, ref, old, todo, tracked, timeout, isolate)
            if got and got[0] == "unknown" and slug in cited:  # a check this machine cannot run: a green cited run or a written reason clears it
                if not (url := cite_url(cited[slug])):
                    continue
                if (cite := judge_run(wt, head, url, run_state)) is None:
                    continue
                got = cite
            if got:
                found.append(Finding(slug, got[0], "debt %s: its Retire check %s. Retire: %s" % (slug, got[1], text)))
            continue
        got = judge_run(wt, head, cite_url(cited[slug]), run_state) if cite_url(cited.get(slug, "")) else ("prose", None)
        if got is None:
            continue
        if got[0] == "prose":
            got = "prose", ("debt %s closes with a Retire that names no runnable check. Retire: %s\n"
                            "Name a test file in backticks in the Retire line, or cite a passing run in the PR body: `%s: %s -- <run URL>`."
                            % (slug, text or "(no Retire line)", CITE, slug))
        else:
            got = got[0], "debt %s: %s" % (slug, got[1])
        found.append(Finding(slug, *got))
    return found


def say(line):
    enc = getattr(sys.stdout, "encoding", None) or "utf-8"
    print(line.encode(enc, "backslashreplace").decode(enc))


def main(argv):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--upstream", default="origin/main")
    ap.add_argument("--head", default="HEAD")
    ap.add_argument("--strict", action="store_true", help="unknown exits 1 (also when env CI is set)")
    ap.add_argument("--repo", default=os.getcwd())
    a = ap.parse_args(argv)
    try:
        found = check(a.repo, a.upstream, a.head, isolate=True)
    except Unknown as e:
        say("debt-retire: UNKNOWN: %s" % e)
        return 1 if (a.strict or os.environ.get("CI")) else 0
    for f in found:
        say("debt-retire: FAIL (%s): %s" % (f.kind, f.text))
    return 1 if found else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))

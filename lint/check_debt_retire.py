#!/usr/bin/env python3
"""Fails when a change closes a debt without proof that its Retire step holds. Stdlib and git only.

    python3 lint/check_debt_retire.py [--upstream origin/main] [--head HEAD] [--strict]

A debt is closed when its file is deleted, or renamed out of the debts folder (lint/layout.py, kind debts). The
check reads that debt's Retire paragraph from the base and runs what it names, on the head:

  runnable  a backticked span that is a test file the head tracks (test_*.py, *_test.py, *.test.mjs, test_*.mjs,
            test_*.sh) runs as one argv, with no shell, from the head folder, under a timeout. Non-zero is red.
            A missing interpreter, a failed start, or a timeout is unknown.
  prose     a Retire that names no runnable check holds the close, unless the PR body cites a run:
            `Retire-run: <slug> -- <run URL>`, read as the Drops-lines line of check_silent_undo is. The run must be
            green and on the PR head or a commit above it. A cite also clears a check that could not run here (unknown);
            a red check is never cleared by a cite.

Exit 1 on any finding. Design: decision debt-close-runs-retire.
"""
import argparse
import os
import re
import shutil
import subprocess
import sys
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
CITE_LINE = re.compile(r"\s*(\S+)\s+--\s+(\S+)\s*$")


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


def spans(text, tracked):
    """The backticked test files of `text` that the head tracks, in order, each once."""
    found = []
    for s in SPAN.findall(text):
        s = s[2:] if s.startswith("./") else s
        if s in tracked and TEST_NAME.match(os.path.basename(s)) and os.path.splitext(s)[1] in INTERPRETERS and s not in found:
            found.append(s)
    return found


def run_span(wt, span, timeout):
    """(kind, text) for one test: red on a non-zero exit, unknown when it could not run, else None."""
    argv = list(INTERPRETERS[os.path.splitext(span)[1]])
    exe = shutil.which(argv[0])
    if not exe:
        return "unknown", "%s is not on PATH, so %s did not run" % (argv[0], span)
    try:
        r = _nowindow.run([exe, *argv[1:], span], cwd=wt, capture_output=True, encoding="utf-8", errors="replace",
                                  timeout=timeout, env=dict(os.environ, PYTHONDONTWRITEBYTECODE="1"))
    except subprocess.TimeoutExpired:
        return "unknown", "%s ran past %d s" % (span, timeout)
    except OSError as e:
        return "unknown", "%s did not start: %s" % (span, e)
    if r.returncode:
        tail = " | ".join((r.stdout + r.stderr).strip().splitlines()[-5:])
        return "red", "%s exited %d%s" % (span, r.returncode, ": " + tail[:400] if tail else "")
    return None


def cites(pr_body):
    """{debt slug: run URL} from the `Retire-run: <slug> -- <url>` lines of the PR body's last paragraph. The last cite of a slug wins."""
    res = {}
    for line in re.findall(r"^" + CITE + r":(.*)$", undo.last_paragraph(pr_body), re.I | re.M | re.ASCII):
        m = CITE_LINE.match(line)
        if m:
            res[m.group(1)] = m.group(2)
    return res


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


def check(wt, base_ref, head="HEAD", timeout=TIMEOUT, pr_body="", run_state=None):
    """[Finding] for each debt that `head` closes against `base_ref` and whose Retire step does not hold. Raises Unknown.
    run_state(url) -> (conclusion, head sha) of a workflow run, or raises."""
    try:
        folder = layout.path(wt, "debts")
        skip = {folder + "/README.md", layout.path(wt, "debt-notes")}
    except layout.LayoutError as e:
        raise Unknown("the debts folder is not known: %s" % e)

    def debt(f):
        return f.startswith(folder + "/") and f.endswith(".md") and f not in skip

    closed = [old for status, old, new in records.changes(wt, base_ref, head)[1]
              if debt(old) and (status == "D" or (status == "R" and not debt(new)))]
    if not closed:
        return []
    head = records.git_names(wt, "rev-parse", head + "^{commit}")[0].strip()
    mb = records.git_names(wt, "merge-base", base_ref, head)[0].strip()
    tracked = set(records.git_names(wt, "ls-tree", "-r", "-z", "--name-only", head))
    cited = cites(pr_body)
    found = []
    for old in closed:
        slug = os.path.basename(old)[:-3]
        text = retire_text(records.show(wt, mb, old))
        todo = spans(text, tracked)
        if todo:
            got = None
            for span in todo:
                got = run_span(wt, span, timeout)
                if got and got[0] == "red":
                    break
            if got and got[0] == "unknown" and slug in cited:  # a check this machine cannot run: a green cited run proves it ran
                if (cite := judge_run(wt, head, cited[slug], run_state)) is None:
                    continue
                got = cite
            if got:
                found.append(Finding(slug, got[0], "debt %s: its Retire check %s. Retire: %s" % (slug, got[1], text)))
            continue
        got = judge_run(wt, head, cited[slug], run_state) if slug in cited else ("prose", None)
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
        found = check(a.repo, a.upstream, a.head)
    except Unknown as e:
        say("debt-retire: UNKNOWN: %s" % e)
        return 1 if (a.strict or os.environ.get("CI")) else 0
    for f in found:
        say("debt-retire: FAIL (%s): %s" % (f.kind, f.text))
    return 1 if found else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))

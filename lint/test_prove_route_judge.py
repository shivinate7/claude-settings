#!/usr/bin/env python3
"""Cases for lint/prove_route_judge.py, which measures the merge-time prose judge against
lint/route_claims_labelled.json. Standard library only.

    python3 lint/test_prove_route_judge.py

The script runs as a child with the git repo that holds the rows' revs as its cwd. Interface pinned here:
`--labelled PATH` (the rows file; default lint/route_claims_labelled.json beside the script) and `--max-calls N`.
It prints one verdict line of the form `false alarms X/H (R%), hits Y/F, unbacked Z/S, unknown K, skipped P`, exits 0,
and writes no file and no log. PROVE_ROUTE_JUDGE_UNDER_TEST names another copy of the script.

Scoring: TRUE rows are holds rows. STALE, PARTLY_STALE and HALF rows are stale-family rows. UNKNOWN and HISTORY
rows, and a row with no rev, are skipped: left out of the score. False alarms: holds rows the model calls stale, out
of all holds rows. Hits: stale-family rows the model calls stale, out of all stale-family rows. Unbacked: every scored
row the model calls unbacked, out of all scored rows, reported in its own field: an unbacked verdict is neither a
false alarm nor a hit. A row the model could not judge (a failed call, a malformed reply, a line the reply leaves out,
a group past --max-calls) is UNKNOWN: reported apart, never a pass, and still in its label's denominator. When a model
call failed, the unknown count carries that failure's first line.

Calls: rows group by (rev, file), one model call per group. The group's prompt is merge.prose_judge_prompt's output
for its rows, and the file is read at its rev through git, never from the working tree.

The model is stubbed. A `claude` executable is the first entry on the child's PATH. It records each prompt under the
case folder and answers from a table in the test, and decision_watch.invoke_model parses that answer for real.
No case starts a model. Each case's HOME, TMPDIR and config folders sit inside the case folder.

Each case asserts its scope first: the script printed its verdict line, or made its judge calls, before any negative
assert (no file, no log, no extra call) is read. Each failure message names one cause.
"""
import atexit
import contextlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.normpath(os.path.join(HERE, ".."))
SCRIPT = os.environ.get("PROVE_ROUTE_JUDGE_UNDER_TEST") or os.path.join(HERE, "prove_route_judge.py")
LABELLED = os.path.join(HERE, "route_claims_labelled.json")
LABELS = ("TRUE", "STALE", "PARTLY_STALE", "HALF", "UNKNOWN", "HISTORY")
HOLDS_LABELS = ("TRUE",)  # this test's own reading of the labels that score, for the pinned judge call groups
FLAGGED_LABELS = ("STALE", "PARTLY_STALE", "HALF")
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(ROOT, "hooks"))
sys.path.insert(0, os.path.join(ROOT, "merge"))
import _test_git  # noqa: E402,F401  test-run signing opt-out (lint/_test_git.py)
import _test_temp  # noqa: E402  test-temp-standard: one run folder per run (lint/_test_temp.py)
import stale_cites  # noqa: E402  backing_path and cite_kind: the one home of a cite (lint/stale_cites.py)
sys.path.insert(0, os.path.join(ROOT, "testing"))
import tracked_tree  # noqa: E402  removes a fixture tree, read-only git objects included (testing/tracked_tree.py)
import decision_watch  # noqa: E402  the one model caller (hooks/decision_watch.py)
import merge  # noqa: E402  prose_judge_prompt: the one home of the judge's prompt (merge/merge.py)

RUN_FOLDER = _test_temp.run_folder()
atexit.register(tracked_tree.rm_tree, RUN_FOLDER)

# The model's answers on the labelled file that make the example line: each TRUE row judged stale is a false alarm, each
# stale-family row judged stale is a hit, and each TRUE row judged unbacked is unbacked. Every other row is judged holds,
# so a row added to the file later is judged holds until it is named here.
FULL_FILE_VERDICTS = {
    ("docs/debts/notes.md", "830"): "stale",
    ("docs/decisions/session-tiers.md", "64"): "holds",
    ("docs/decisions/records-index-at-merge.md", "20"): "stale",
    ("docs/decisions/records-index-at-merge.md", "11"): "stale",
    (".claude/CLAUDE.md", "16-20"): "stale",
    ("docs/decisions/pr-review-record.md", "41"): "unbacked",
    ("docs/decisions/standing-merge-grant.md", "14"): "unbacked",
    ("docs/decisions/standing-merge-grant.md", "31"): "unbacked",
    ("docs/decisions/lanes-start-as-agents.md", "13"): "unbacked",
    ("docs/decisions/task-names-its-check.md", "19"): "unbacked",
}

# The `claude` the child finds first. It records each prompt, then answers each `Line N: text` from ANSWERS by the
# text with its whitespace collapsed to single spaces, as the script prints a multi-line span: a verdict, ERROR
# (exit 1), GARBAGE (a reply that is not JSON) or OMIT (the line is left out of the reply).
STUB = """#!@PYTHON@
import json, os, re, sys
CALLS = @CALLS@
ANSWERS = @ANSWERS@
prompt = sys.stdin.buffer.read().decode("utf-8", "replace")
with open(os.path.join(CALLS, "%03d.txt" % len(os.listdir(CALLS))), "w", encoding="utf-8") as f:
    f.write(prompt)
entries, error, garbage = [], False, False
for number, text in re.findall(r"^Line (\\d+): (.*)$", prompt, re.M):
    answer = ANSWERS.get(" ".join(text.split()), "holds")
    error = error or answer == "ERROR"
    garbage = garbage or answer == "GARBAGE"
    if answer not in ("ERROR", "GARBAGE", "OMIT"):
        entries.append({"line": int(number), "verdict": answer})
if error:
    sys.stderr.write("stub: the model failed\\nsecond line of stderr\\n")
    sys.exit(1)
if garbage:
    print("this reply is not JSON")
    sys.exit(0)
print(json.dumps({"result": json.dumps({"verdicts": entries})}))
"""


def git(cwd, *args):
    return subprocess.run(["git", "-c", "user.name=test", "-c", "user.email=test@example.com", "-c", "commit.gpgsign=false",
                           *args], cwd=cwd, check=True, capture_output=True, text=True).stdout.strip()


def write(path, text):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        f.write(text)


def read(path):
    with open(path, encoding="utf-8") as f:
        return f.read()


def files_under(folder):
    """The regular files under `folder`, as sorted paths relative to it."""
    found = []
    for dirpath, _, names in os.walk(folder):
        found += [os.path.relpath(os.path.join(dirpath, name), folder) for name in names]
    return sorted(found)


def doc(lines):
    """A Markdown file: line N is lines[N], and each number between is a filler line that no row cites."""
    return "".join(lines.get(n, "filler %d" % n) + "\n" for n in range(1, max(lines) + 1))


def make_repo(case, commits):
    """A git repo under `case` with one commit per dict of {path: text} in `commits`. -> (repo, each commit's sha)."""
    repo = os.path.join(case, "repo")
    os.makedirs(repo)
    git(repo, "init", "-q")
    shas = []
    for files in commits:
        for path, text in files.items():
            write(os.path.join(repo, *path.split("/")), text)
        git(repo, "add", "-A")
        git(repo, "commit", "-qm", "fixture")
        shas.append(git(repo, "rev-parse", "HEAD"))
    return repo, shas


def row(path, line, label, text, rev):
    """One labelled row, shaped as lint/route_claims_labelled.json shapes it: the line number as a string."""
    return {"file": path, "line": str(line), "label": label, "text_summary": text, "rev": rev, "text": text}


def has_line(prompt, number, text):
    return re.search(r"^Line %d: %s$" % (number, re.escape(text)), prompt, re.M) is not None


def write_stub(case, answers):
    """Put a `claude` first on the child's PATH, recording into case/calls. -> the folder that holds it."""
    bin_dir, calls = os.path.join(case, "bin"), os.path.join(case, "calls")
    os.makedirs(bin_dir)
    os.makedirs(calls)
    path = os.path.join(bin_dir, "claude")
    write(path, STUB.replace("@PYTHON@", sys.executable).replace("@CALLS@", repr(calls)).replace("@ANSWERS@", repr(answers)))
    os.chmod(path, 0o755)
    return bin_dir


def child_env(case, bin_dir):
    """The child's whole environment: the stub first, then git's folder. HOME, TMPDIR and the config folder sit in the case."""
    for name in ("home", "tmp", "config"):
        os.makedirs(os.path.join(case, name), exist_ok=True)
    return {"PATH": os.pathsep.join([bin_dir, os.path.dirname(shutil.which("git"))]), "LANG": "C.UTF-8",
            "PYTHONDONTWRITEBYTECODE": "1", "HOME": os.path.join(case, "home"),
            "TMPDIR": os.path.join(case, "tmp"), "CLAUDE_CONFIG_DIR": os.path.join(case, "config")}


@contextlib.contextmanager
def patched(env, case):
    """os.environ and tempfile.tempdir set for one block, so a model call made in this process writes under the case."""
    prior = {name: os.environ.get(name) for name in env}
    prior_tmp = tempfile.tempdir
    os.environ.update(env)
    tempfile.tempdir = os.path.join(case, "tmp")
    try:
        yield
    finally:
        tempfile.tempdir = prior_tmp
        for name, value in prior.items():
            if value is None:
                os.environ.pop(name, None)
            else:
                os.environ[name] = value


class Run:
    def __init__(self, proc, case):
        self.code, self.out, self.err, self.case = proc.returncode, proc.stdout, proc.stderr, case
        calls = os.path.join(case, "calls")
        self.calls = [read(os.path.join(calls, name)) for name in sorted(os.listdir(calls))]

    def lines(self):
        return [line for line in self.out.splitlines() if line.strip()]


def judge(case, repo, answers, rows=None, labelled=LABELLED, extra=()):
    """Run the script in `repo` on the labelled rows, with `rows` written to the case when given. -> Run."""
    if rows is not None:
        labelled = os.path.join(case, "rows.json")
        write(labelled, json.dumps(rows))
    bin_dir = write_stub(case, answers)
    proc = subprocess.run([sys.executable, SCRIPT, "--labelled", labelled, *extra], cwd=repo, env=child_env(case, bin_dir),
                          capture_output=True, text=True, encoding="utf-8", errors="replace")
    return Run(proc, case)


class Base(unittest.TestCase):
    def case(self):
        return tempfile.mkdtemp(prefix="case-", dir=RUN_FOLDER)


class ControlTests(Base):
    """Green on the old code. They prove the fixture, the stub and the homes the other cases rely on."""

    def test_labelled_file_has_the_six_labels_distinct_texts_and_readable_revs(self):
        rows = labelled_rows()
        self.assertEqual(sorted({r["label"] for r in rows}), sorted(LABELS), "the labels in the file are not the six the score maps")
        self.assertEqual(len({" ".join(r["text"].split()) for r in rows}), len(rows),
                         "two rows share a text once whitespace is collapsed, so a text cannot key a model answer")
        missing = [rev for rev in {r["rev"] for r in rows}
                   if subprocess.run(["git", "cat-file", "-e", rev + "^{commit}"], cwd=ROOT, capture_output=True).returncode]
        self.assertEqual(missing, [], "the labelled revs are not in this clone, so the file cannot be read at them")

    def test_labelled_file_has_its_pinned_row_count(self):
        self.assertEqual(len(labelled_rows()), 38, "the labelled file's row count moved: pin it here if the change is on purpose")

    def test_labelled_file_has_its_pinned_judge_call_groups(self):
        groups = {(r["rev"], r["file"]) for r in scored_rows(labelled_rows())}
        self.assertEqual(len(groups), 23, "the scored (rev, file) groups moved, so the judge calls per run moved: "
                                          "pin it here if the change is on purpose")

    def test_stub_claude_answers_the_real_invoke_model(self):
        case = self.case()
        bin_dir = write_stub(case, {"alpha text": "stale"})
        with patched(child_env(case, bin_dir), case):
            verdict, error = decision_watch.invoke_model("File: docs/x.md\nLine 3: alpha text\n", shape=decision_watch.LINE_VERDICTS)
        self.assertEqual(len(os.listdir(os.path.join(case, "calls"))), 1, "the stub was not reached: invoke_model made no claude call")
        self.assertEqual((verdict, error), ({"verdicts": [{"line": 3, "verdict": "stale"}]}, None),
                         "the stubbed reply did not parse as a line verdict")

    def test_merge_prompt_home_prints_each_line_as_line_n_text(self):
        prompt = merge.prose_judge_prompt(self.case(), "docs/x.md", {3: ("alpha text", [])})
        self.assertIn("File: docs/x.md", prompt, "merge.prose_judge_prompt no longer names the file")
        self.assertIn("Line 3: alpha text", prompt, "merge.prose_judge_prompt no longer prints each line as Line N: text")

    def test_read_cite_in_the_fixture_names_its_backing_file(self):
        self.assertEqual(stale_cites.backing_path(*stale_cites.cite_kind("read lint/backing.py:1")), "lint/backing.py",
                         "the read cite the fixture uses no longer names its backing file")


class LabelMapTests(Base):
    def test_true_rows_judged_stale_are_false_alarms(self):
        case = self.case()
        repo, (rev,) = make_repo(case, [{"docs/a.md": doc({1: "alpha claim", 2: "beta claim", 3: "gamma claim"})}])
        rows = [row("docs/a.md", 1, "TRUE", "alpha claim", rev), row("docs/a.md", 2, "TRUE", "beta claim", rev),
                row("docs/a.md", 3, "STALE", "gamma claim", rev)]
        run = judge(case, repo, {"alpha claim": "stale", "beta claim": "holds", "gamma claim": "holds"}, rows=rows)
        self.assertEqual(len(run.calls), 1, "expected one judge call for the one group, got %d" % len(run.calls))
        self.assertEqual(run.lines(), ["false alarms 1/2 (50.0%), hits 0/1, unbacked 0/3, unknown 0, skipped 0"],
                         "a TRUE row judged stale must count as a false alarm")

    def test_unbacked_verdict_is_neither_a_false_alarm_nor_a_hit(self):
        case = self.case()
        repo, (rev,) = make_repo(case, [{"docs/a.md": doc({1: "alpha claim", 2: "beta claim", 3: "gamma claim"})}])
        rows = [row("docs/a.md", 1, "TRUE", "alpha claim", rev), row("docs/a.md", 2, "TRUE", "beta claim", rev),
                row("docs/a.md", 3, "STALE", "gamma claim", rev)]
        run = judge(case, repo, {"alpha claim": "unbacked", "beta claim": "holds", "gamma claim": "unbacked"}, rows=rows)
        self.assertEqual(len(run.calls), 1, "expected one judge call for the one group, got %d" % len(run.calls))
        self.assertEqual(run.lines(), ["false alarms 0/2 (0.0%), hits 0/1, unbacked 2/3, unknown 0, skipped 0"],
                         "a TRUE row judged unbacked must not count as a false alarm, and an unbacked stale row not as a hit")

    def test_stale_family_rows_judged_stale_are_hits(self):
        case = self.case()
        repo, (rev,) = make_repo(case, [{"docs/a.md": doc({1: "s1 claim", 2: "p1 claim", 3: "h1 claim", 4: "h2 claim",
                                                             5: "t1 claim"})}])
        rows = [row("docs/a.md", 1, "STALE", "s1 claim", rev), row("docs/a.md", 2, "PARTLY_STALE", "p1 claim", rev),
                row("docs/a.md", 3, "HALF", "h1 claim", rev), row("docs/a.md", 4, "HALF", "h2 claim", rev),
                row("docs/a.md", 5, "TRUE", "t1 claim", rev)]
        run = judge(case, repo, {"s1 claim": "stale", "p1 claim": "unbacked", "h1 claim": "stale", "h2 claim": "holds",
                                 "t1 claim": "holds"}, rows=rows)
        self.assertEqual(len(run.calls), 1, "expected one judge call for the one group, got %d" % len(run.calls))
        self.assertEqual(run.lines(), ["false alarms 0/1 (0.0%), hits 2/4, unbacked 1/5, unknown 0, skipped 0"],
                         "hits count stale verdicts only: stale rows of the stale family are hits, and the unbacked one is not")

    def test_unknown_and_history_rows_are_skipped_not_scored(self):
        case = self.case()
        repo, (rev,) = make_repo(case, [{"docs/a.md": doc({1: "t1 claim", 2: "s1 claim", 3: "u1 claim", 4: "h1 claim"})}])
        rows = [row("docs/a.md", 1, "TRUE", "t1 claim", rev), row("docs/a.md", 2, "STALE", "s1 claim", rev),
                row("docs/a.md", 3, "UNKNOWN", "u1 claim", rev), row("docs/a.md", 4, "HISTORY", "h1 claim", rev)]
        run = judge(case, repo, {"t1 claim": "holds", "s1 claim": "holds", "u1 claim": "stale", "h1 claim": "stale"}, rows=rows)
        self.assertEqual(len(run.calls), 1, "expected one judge call for the one group, got %d" % len(run.calls))
        self.assertEqual(run.lines(), ["false alarms 0/1 (0.0%), hits 0/1, unbacked 0/2, unknown 0, skipped 2"],
                         "UNKNOWN and HISTORY rows must be left out of the score and counted as skipped")


class GroupTests(Base):
    def test_one_judge_call_per_rev_and_file_group(self):
        case = self.case()
        repo, (first, second) = make_repo(case, [
            {"docs/a.md": doc({1: "a one", 2: "a two"}), "docs/b.md": doc({1: "b one"})},
            {"docs/a.md": doc({1: "a one newer", 2: "a two"})}])
        rows = [row("docs/a.md", 1, "TRUE", "a one", first), row("docs/a.md", 2, "STALE", "a two", first),
                row("docs/b.md", 1, "TRUE", "b one", first), row("docs/a.md", 1, "TRUE", "a one newer", second)]
        run = judge(case, repo, {"a two": "stale"}, rows=rows)
        self.assertEqual(len(run.calls), 3, "expected one judge call per (rev, file) group, 3 groups, got %d" % len(run.calls))
        first_a = [p for p in run.calls if has_line(p, 2, "a two")]
        self.assertEqual(len(first_a), 1, "the rows of the (first rev, docs/a.md) group did not share one prompt")
        self.assertTrue(has_line(first_a[0], 1, "a one") and not has_line(first_a[0], 1, "a one newer"),
                        "the (first rev, docs/a.md) prompt does not carry that group's rows")
        self.assertEqual(len([p for p in run.calls if has_line(p, 1, "b one")]), 1, "docs/b.md's row did not get its own prompt")
        self.assertTrue(all(not has_line(p, 2, "a two") for p in run.calls if has_line(p, 1, "b one")),
                        "docs/b.md's prompt carries a row of another file")
        self.assertEqual(len([p for p in run.calls if has_line(p, 1, "a one newer")]), 1,
                         "the second rev's docs/a.md row did not get its own prompt")

    def test_group_prompt_is_merge_prose_judge_prompt_of_its_rows(self):
        case = self.case()
        repo, (rev,) = make_repo(case, [{"docs/c.md": doc({3: "gamma line"})}])
        run = judge(case, repo, {"gamma line": "holds"}, rows=[row("docs/c.md", 3, "TRUE", "gamma line", rev)])
        self.assertEqual(len(run.calls), 1, "expected one judge call for the one group, got %d" % len(run.calls))
        self.assertEqual(run.calls[0], merge.prose_judge_prompt(repo, "docs/c.md", {3: ("gamma line", [])}),
                         "the group's prompt is not merge.prose_judge_prompt's output for its rows")


class RevTests(Base):
    def test_rows_are_read_at_their_rev_not_the_working_tree(self):
        case = self.case()
        repo, (rev,) = make_repo(case, [{"docs/d.md": doc({1: "rev intro", 2: "rev claim (read lint/backing.py:1)"}),
                                         "lint/backing.py": "rev backing text\n"}])
        write(os.path.join(repo, "docs", "d.md"), doc({1: "rev intro", 2: "working tree claim (read lint/backing.py:1)"}))
        write(os.path.join(repo, "lint", "backing.py"), "working backing text\n")
        rows = [row("docs/d.md", 2, "TRUE", "rev claim (read lint/backing.py:1)", rev)]
        run = judge(case, repo, {"rev claim (read lint/backing.py:1)": "holds"}, rows=rows)
        self.assertEqual(len(run.calls), 1, "expected one judge call for the one group, got %d" % len(run.calls))
        prompt = run.calls[0]
        self.assertIn("rev claim (read lint/backing.py:1)", prompt, "the group's line is not the line at its rev")
        self.assertIn("rev backing text", prompt, "the cited text is not the backing file at the rev")
        self.assertNotIn("working tree claim", prompt, "the prompt holds the working tree's line, not the rev's")
        self.assertNotIn("working backing text", prompt, "the prompt holds the working tree's backing file")

    def test_row_with_no_rev_is_skipped_and_the_run_still_prints_its_line(self):
        case = self.case()
        repo, (rev,) = make_repo(case, [{"docs/a.md": doc({1: "alpha claim", 2: "beta claim", 3: "gamma claim"})}])
        no_rev = row("docs/a.md", 1, "TRUE", "alpha claim", None)
        no_rev["note"] = "the commit was not recorded"  # the shape lint/route_claims_labelled.json gives a null rev
        rows = [no_rev, row("docs/a.md", 2, "TRUE", "beta claim", rev), row("docs/a.md", 3, "STALE", "gamma claim", rev)]
        run = judge(case, repo, {"beta claim": "holds", "gamma claim": "stale"}, rows=rows)
        self.assertEqual(run.lines(), ["false alarms 0/1 (0.0%), hits 1/1, unbacked 0/2, unknown 0, skipped 1"],
                         "a row with no rev must be counted as skipped, and the run must still print its verdict line")
        self.assertEqual(len(run.calls), 1, "the row with no rev made a judge call of its own, or the rest were not judged")
        self.assertEqual(run.code, 0, "a row with no rev must not end the run with a non-zero exit")
        self.assertNotIn("Traceback", run.err, "a row with no rev raised an exception in the script")


class UnknownTests(Base):
    def test_model_error_is_unknown_never_a_pass(self):
        case = self.case()
        repo, (rev,) = make_repo(case, [{"docs/a.md": doc({1: "alpha claim"}),
                                         "docs/b.md": doc({1: "beta claim", 2: "gamma claim"})}])
        rows = [row("docs/a.md", 1, "TRUE", "alpha claim", rev), row("docs/b.md", 1, "TRUE", "beta claim", rev),
                row("docs/b.md", 2, "STALE", "gamma claim", rev)]
        run = judge(case, repo, {"alpha claim": "ERROR", "beta claim": "holds", "gamma claim": "stale"}, rows=rows)
        self.assertEqual(len(run.calls), 2, "expected one judge call per group, 2 groups, got %d" % len(run.calls))
        self.assertEqual(run.lines(), ["false alarms 0/2 (0.0%), hits 1/1, unbacked 0/3, unknown 1 (model error: "
                                       "model exited 1: stub: the model failed), skipped 0"],
                         "a row whose model call failed must be UNKNOWN: in its label's denominator, in neither numerator")

    def test_line_the_reply_leaves_out_is_unknown(self):
        case = self.case()
        repo, (rev,) = make_repo(case, [{"docs/a.md": doc({1: "alpha claim", 2: "beta claim", 3: "gamma claim"})}])
        rows = [row("docs/a.md", 1, "TRUE", "alpha claim", rev), row("docs/a.md", 2, "TRUE", "beta claim", rev),
                row("docs/a.md", 3, "STALE", "gamma claim", rev)]
        run = judge(case, repo, {"alpha claim": "stale", "beta claim": "OMIT", "gamma claim": "stale"}, rows=rows)
        self.assertEqual(len(run.calls), 1, "expected one judge call for the one group, got %d" % len(run.calls))
        self.assertEqual(run.lines(), ["false alarms 1/2 (50.0%), hits 1/1, unbacked 0/3, unknown 1, skipped 0"],
                         "a row the reply leaves out must be UNKNOWN, not a holds verdict, and carries no model error")

    def test_malformed_reply_is_unknown(self):
        case = self.case()
        repo, (rev,) = make_repo(case, [{"docs/a.md": doc({1: "alpha claim"}),
                                         "docs/b.md": doc({1: "beta claim", 2: "gamma claim"})}])
        rows = [row("docs/a.md", 1, "TRUE", "alpha claim", rev), row("docs/b.md", 1, "TRUE", "beta claim", rev),
                row("docs/b.md", 2, "STALE", "gamma claim", rev)]
        run = judge(case, repo, {"alpha claim": "GARBAGE", "beta claim": "holds", "gamma claim": "stale"}, rows=rows)
        self.assertEqual(len(run.calls), 2, "expected one judge call per group, 2 groups, got %d" % len(run.calls))
        self.assertEqual(run.lines(), ["false alarms 0/2 (0.0%), hits 1/1, unbacked 0/3, unknown 1 (model error: "
                                       "model output was not JSON), skipped 0"],
                         "a reply that is not JSON must make its rows UNKNOWN, carrying the call's error")


class RunTests(Base):
    def test_max_calls_stops_after_n_groups_and_the_rest_are_unknown(self):
        case = self.case()
        repo, (rev,) = make_repo(case, [{"docs/e%d.md" % n: doc({1: "e%d claim" % n}) for n in range(1, 5)}])
        rows = [row("docs/e1.md", 1, "TRUE", "e1 claim", rev), row("docs/e2.md", 1, "TRUE", "e2 claim", rev),
                row("docs/e3.md", 1, "STALE", "e3 claim", rev), row("docs/e4.md", 1, "STALE", "e4 claim", rev)]
        run = judge(case, repo, {"e1 claim": "holds", "e2 claim": "holds", "e3 claim": "stale", "e4 claim": "stale"},
                    rows=rows, extra=("--max-calls", "2"))
        self.assertEqual(len(run.calls), 2, "--max-calls 2 must stop after two groups, got %d calls" % len(run.calls))
        self.assertIn("unknown 2, skipped 0", "\n".join(run.lines()), "the two groups past the cap must count as unknown")

    def test_empty_labelled_file_prints_one_line_and_makes_no_call(self):
        case = self.case()
        repo, _ = make_repo(case, [{"docs/a.md": doc({1: "alpha claim"})}])
        run = judge(case, repo, {}, rows=[])
        self.assertEqual(len(run.lines()), 1, "an empty labelled file must print exactly one verdict line")
        self.assertIn("unknown 0, skipped 0", run.lines()[0], "an empty labelled file must count no unknown and no skipped row")
        self.assertEqual(len(run.calls), 0, "an empty labelled file made a judge call")

    def test_exit_is_zero_with_stale_and_unknown_rows(self):
        case = self.case()
        repo, (rev,) = make_repo(case, [{"docs/a.md": doc({1: "alpha claim"}), "docs/b.md": doc({1: "beta claim"}),
                                         "docs/c.md": doc({1: "gamma claim"})}])
        rows = [row("docs/a.md", 1, "TRUE", "alpha claim", rev), row("docs/b.md", 1, "TRUE", "beta claim", rev),
                row("docs/c.md", 1, "STALE", "gamma claim", rev)]
        run = judge(case, repo, {"alpha claim": "stale", "beta claim": "ERROR", "gamma claim": "holds"}, rows=rows)
        self.assertEqual(len(run.calls), 3, "expected one judge call per group, 3 groups, got %d" % len(run.calls))
        self.assertEqual(run.code, 0, "a report with stale and unknown rows must still exit 0")

    def test_writes_no_file_and_no_log(self):
        case = self.case()
        repo, (rev,) = make_repo(case, [{"docs/a.md": doc({1: "alpha claim", 2: "gamma claim"})}])
        rows = [row("docs/a.md", 1, "TRUE", "alpha claim", rev), row("docs/a.md", 2, "STALE", "gamma claim", rev)]
        run = judge(case, repo, {"alpha claim": "holds", "gamma claim": "stale"}, rows=rows)
        self.assertEqual(len(run.lines()), 1, "the run must print exactly one verdict line")
        self.assertEqual(len(run.calls), 1, "expected one judge call for the one group, got %d" % len(run.calls))
        self.assertEqual(git(repo, "status", "--porcelain"), "", "the run changed the repo: a file was written or changed")
        self.assertEqual(files_under(os.path.join(case, "tmp")), [], "the run left a temp file behind")
        self.assertEqual(files_under(os.path.join(case, "config")), [], "the run wrote into the config folder")


def labelled_rows():
    with open(LABELLED, encoding="utf-8") as f:
        return json.load(f)


def scored_rows(rows):
    """The rows the score counts: a holds or stale-family label, with a rev. The rest are skipped."""
    return [r for r in rows if r["label"] in HOLDS_LABELS + FLAGGED_LABELS and r.get("rev")]


def full_file_run(case, answer_for):
    """Run the script on the whole labelled file, each row answered by answer_for(row). -> Run."""
    answers = {" ".join(r["text"].split()): answer_for(r) for r in labelled_rows()}
    return judge(case, ROOT, answers, labelled=LABELLED)


class FullFileTests(Base):
    # The pinned lines and call count. Adding or removing a row changes them, on purpose.
    def test_full_labelled_file_gives_the_example_line(self):
        run = full_file_run(self.case(), lambda r: FULL_FILE_VERDICTS.get((r["file"], r["line"]), "holds"))
        self.assertEqual(run.lines(), ["false alarms 1/13 (7.7%), hits 3/21, unbacked 5/34, unknown 0, skipped 4"],
                         "the score of the full labelled file is not the pinned line")
        self.assertEqual(run.code, 0, "the full labelled file's run must exit 0")
        self.assertEqual(len(run.calls), 23, "the full labelled file must make one judge call per scored (rev, file) group")

    def test_judge_that_says_unbacked_to_every_line_scores_no_false_alarm(self):
        run = full_file_run(self.case(), lambda r: "unbacked")
        self.assertEqual(run.lines(), ["false alarms 0/13 (0.0%), hits 0/21, unbacked 34/34, unknown 0, skipped 4"],
                         "a judge that says unbacked to every line must score 0 false alarms and 0 hits, with 34 unbacked")
        self.assertEqual(run.code, 0, "the every-line-unbacked run must exit 0")

    def test_model_error_carries_its_first_line_on_the_unknown_count(self):
        run = full_file_run(self.case(), lambda r: "ERROR")
        self.assertEqual(run.lines(), ["false alarms 0/13 (0.0%), hits 0/21, unbacked 0/34, unknown 34 (model error: "
                                       "model exited 1: stub: the model failed), skipped 4"],
                         "every row whose model call failed must be UNKNOWN, and the count must carry the call's first error line")
        self.assertNotIn("second line of stderr", run.out,
                         "the verdict line carries the error's second line, not only its first")
        self.assertEqual(run.code, 0, "a run whose every model call failed must still exit 0")


if __name__ == "__main__":
    unittest.main()

#!/usr/bin/env python3
"""Cases for lint/find_copies.py. Standard library only.

    python3 lint/test_find_copies.py

Each case builds a temp parent and a temp child, then runs the real script on them. The
fixtures copy the shape of the worked examples: q_max's drifted plain-english-map skill,
q_max's verbatim copy of a parent test with a header added, and the impeccable copies in
ios-adblock, joyous and degen, which differ from the parent and from each other.
FIND_COPIES_UNDER_TEST overrides the module path.
"""
import contextlib
import importlib.util
import io
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _test_temp  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
MODULE = os.environ.get("FIND_COPIES_UNDER_TEST") or os.path.join(HERE, "find_copies.py")
RUN_FOLDER = _test_temp.run_folder()  # test-temp-standard (one run folder per test run)
REPO = os.path.dirname(HERE)
LABELLED = os.path.join(HERE, "paraphrase_labelled.json")
sys.path.append(os.path.join(HERE, "..", "hooks"))  # decision_watch, the one home of the model call

SKILL_MD = "---\nname: {name}\ndescription: A shared skill for the fixture.\n---\n\n" + "".join(
    f"Step {i}: do the shared thing number {i} with care.\n" for i in range(12)
)
HELPER = "".join(f"export function helper{i}(value) {{ return value * {i} + 1; }}\n" for i in range(15))
TEST = "// Red proof: node --test testing/\nimport { helper } from './helper.mjs';\n" + "".join(
    f"test('case {i} keeps its promise', () => assert.equal(helper({i}), {i * 2}));\n" for i in range(15)
)
# Comment openers inside strings, a multi-line template literal and a lone quote in text.
TRAPS = (
    "const a = 'not /* a comment';\nconst b = \"not // a comment either\";\nconst c = `line one\n"
    "line two # not a comment`;\nconst d = <p>Don't stop here</p>;\n"
    + "".join(f"const keep{i} = 'value number {i} for the trap file';\n" for i in range(10))
)


def write(root, rel, text):
    path = os.path.join(root, rel)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(text)


def make_parent(root):
    write(root, "skills/impeccable/SKILL.md", SKILL_MD.format(name="impeccable"))
    write(root, "skills/impeccable/scripts/run.mjs", HELPER)
    write(root, "skills/impeccable/reference/document.md", "".join(f"Rule {i} of the reference.\n" for i in range(12)))
    write(root, "skills/plain-english-map/SKILL.md", SKILL_MD.format(name="plain-english-map"))
    write(root, "skills/plain-english-map/scripts/map-check.mjs", HELPER)
    write(root, "skills/plain-english-map/scripts/map-upgrade.mjs", HELPER.replace("helper", "upgrade"))
    write(root, "testing/skip-locally-fail-in-ci.test.mjs", TEST)
    write(root, "lint/traps.mjs", TRAPS)
    write(root, "LICENSE", "MIT License\n" * 30)
    write(root, "actions/stamp/examples/frontmatter.stamp.json", HELPER)


def run(parent, child, *extra):
    proc = subprocess.run(
        [sys.executable, MODULE, child, "--parent", parent, *extra],
        capture_output=True, text=True, timeout=60,
    )
    return proc


class RunFolderSweepTest(unittest.TestCase):
    def test_old_sibling_goes_and_new_one_stays(self):
        root = os.path.join(RUN_FOLDER, "root")
        old = os.path.join(root, "1-" + "a" * 32)
        new = os.path.join(root, "2-" + "b" * 32)
        other = os.path.join(root, "not-a-run-folder")
        for path in (old, new, other):
            os.makedirs(path)
        two_days_ago = time.time() - 2 * 24 * 60 * 60
        os.utime(old, (two_days_ago, two_days_ago))
        os.utime(other, (two_days_ago, two_days_ago))
        own = _test_temp.run_folder(root)
        self.assertFalse(os.path.exists(old))
        self.assertTrue(os.path.isdir(new))
        self.assertTrue(os.path.isdir(other))
        self.assertTrue(os.path.isdir(own))


class FindCopiesTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(dir=RUN_FOLDER)
        self.parent = os.path.join(self.tmp.name, "parent")
        self.child = os.path.join(self.tmp.name, "child")
        make_parent(self.parent)
        os.makedirs(self.child)

    def tearDown(self):
        self.tmp.cleanup()

    def findings(self, *extra):
        proc = run(self.parent, self.child, "--json", *extra)
        self.assertIn(proc.returncode, (0, 1), proc.stderr)
        return proc.returncode, json.loads(proc.stdout)

    def test_clean_child_is_quiet(self):
        write(self.child, "src/app.ts", "".join(f"export const own{i} = {i};\n" for i in range(20)))
        write(self.child, "LICENSE", "MIT License\n" * 30)
        proc = run(self.parent, self.child)
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        self.assertIn("no copies", proc.stdout)

    def test_drifted_skill_copy(self):
        # q_max shape: the copy lags the parent, with edits and a missing file.
        base = ".claude/skills/plain-english-map"
        write(self.child, f"{base}/SKILL.md", SKILL_MD.format(name="plain-english-map") + "A local edit.\n")
        write(self.child, f"{base}/scripts/map-check.mjs", HELPER)
        code, out = self.findings()
        self.assertEqual(code, 1)
        skills = [f for f in out["skills"] if f["skill"] == "plain-english-map"]
        self.assertEqual(len(skills), 1, out)
        s = skills[0]
        self.assertEqual(s["child_path"], base)
        self.assertEqual(s["state"], "drifted")
        self.assertEqual(s["differ"], ["SKILL.md"])
        self.assertEqual(s["only_in_parent"], ["scripts/map-upgrade.mjs"])
        # Files inside a reported skill copy are not reported again as file copies.
        self.assertEqual([f for f in out["files"] if f["child"].startswith(base)], [])

    def test_identical_skill_copy_is_still_a_copy(self):
        base = ".claude/skills/impeccable"
        write(self.child, f"{base}/SKILL.md", SKILL_MD.format(name="impeccable"))
        write(self.child, f"{base}/scripts/run.mjs", HELPER)
        write(self.child, f"{base}/reference/document.md", "".join(f"Rule {i} of the reference.\n" for i in range(12)))
        code, out = self.findings()
        self.assertEqual(code, 1)
        self.assertEqual([(s["skill"], s["state"]) for s in out["skills"]], [("impeccable", "same")])

    def test_three_impeccable_copies_that_differ(self):
        # ios-adblock, joyous and degen each hold a copy that differs from the parent and from
        # the others. Each child is its own run, so each run reports its own copy.
        edits = {
            "ios-adblock": ("SKILL.md", "Edited for ios-adblock.\n"),
            "joyous": ("scripts/run.mjs", "// joyous edit\n"),
            "degen": ("reference/document.md", "Degen's own rule.\n"),
        }
        for repo, (rel, extra) in edits.items():
            child = os.path.join(self.tmp.name, repo)
            base = os.path.join(child, ".claude/skills/impeccable")
            write(base, "SKILL.md", SKILL_MD.format(name="impeccable"))
            write(base, "scripts/run.mjs", HELPER)
            write(base, "reference/document.md", "".join(f"Rule {i} of the reference.\n" for i in range(12)))
            with open(os.path.join(base, rel), "a", encoding="utf-8") as f:
                f.write(extra)
            proc = run(self.parent, child, "--json")
            self.assertEqual(proc.returncode, 1, repo + proc.stderr)
            out = json.loads(proc.stdout)
            self.assertEqual(len(out["skills"]), 1, repo)
            self.assertEqual(out["skills"][0]["state"], "drifted", repo)
            self.assertEqual(out["skills"][0]["differ"], [rel], repo)

    def test_skill_found_by_frontmatter_name_under_another_folder(self):
        write(self.child, "tools/map-skill/SKILL.md", SKILL_MD.format(name="plain-english-map"))
        code, out = self.findings()
        self.assertEqual(code, 1)
        self.assertEqual([(s["skill"], s["child_path"]) for s in out["skills"]],
                         [("plain-english-map", "tools/map-skill")])

    def test_verbatim_test_copy_with_header(self):
        # q_max shape: the parent test, with a provenance header added on top.
        header = "// Copied verbatim from claude-settings, testing/skip-locally-fail-in-ci.test.mjs.\n// Import path adapted.\n"
        write(self.child, "harness/tests/skip-locally-fail-in-ci.test.mjs", header + TEST)
        code, out = self.findings()
        self.assertEqual(code, 1)
        self.assertEqual(len(out["files"]), 1, out)
        f = out["files"][0]
        self.assertEqual(f["parent"], "testing/skip-locally-fail-in-ci.test.mjs")
        self.assertEqual(f["child"], "harness/tests/skip-locally-fail-in-ci.test.mjs")
        self.assertEqual(f["kind"], "near-equal")
        self.assertGreaterEqual(f["score"], 0.8)

    def test_byte_equal_file_under_another_name(self):
        write(self.child, "vendor/whatever.mjs", TEST)
        code, out = self.findings()
        self.assertEqual(code, 1)
        self.assertEqual([(f["parent"], f["kind"]) for f in out["files"]],
                         [("testing/skip-locally-fail-in-ci.test.mjs", "byte-equal")])

    def test_scanner_traps_compare_as_plain_text(self):
        write(self.child, "src/traps.mjs", TRAPS)
        code, out = self.findings()
        self.assertEqual(code, 1)
        self.assertEqual([(f["parent"], f["kind"]) for f in out["files"]], [("lint/traps.mjs", "byte-equal")])

    def test_large_file_that_quotes_a_parent_file_is_not_a_copy(self):
        write(self.child, "src/big.mjs", TEST + "".join(f"const mine{i} = 'own line {i}';\n" for i in range(60)))
        code, out = self.findings()
        self.assertEqual(code, 0, out)

    def test_scanner_traps_near_equal(self):
        write(self.child, "src/traps.mjs", "// local header\n" + TRAPS)
        code, out = self.findings()
        self.assertEqual([(f["parent"], f["kind"]) for f in out["files"]], [("lint/traps.mjs", "near-equal")])

    def test_shared_boilerplate_is_not_a_copy(self):
        # A file that shares a few common lines with a parent file is not a copy.
        write(self.child, "src/other.mjs", HELPER[:200] + "".join(f"const mine{i} = {i};\n" for i in range(40)))
        code, out = self.findings()
        self.assertEqual(code, 0, out)

    def test_parent_example_is_meant_to_be_copied(self):
        write(self.child, ".github/stamp.json", HELPER.replace("helper1(", "local1("))
        code, out = self.findings()
        self.assertEqual([f["parent"] for f in out["files"]],
                         ["skills/impeccable/scripts/run.mjs"])

    def test_missing_child_is_unknown(self):
        proc = run(self.parent, os.path.join(self.tmp.name, "nowhere"))
        self.assertEqual(proc.returncode, 2)
        self.assertIn("unknown", proc.stdout + proc.stderr)

    def test_reads_only(self):
        write(self.child, "harness/tests/copy.test.mjs", TEST)
        before = sorted(os.walk(self.child))
        run(self.parent, self.child)
        self.assertEqual(before, sorted(os.walk(self.child)))


# ------------------------------------------------------------------ the paraphrase pass (PARA001)
#
# `find_copies.py --paraphrase [--parent DIR]` prints `path:line: PARA001 <rule-id> may restate`
# for each line that may restate a rule in other words. It exits 0 on hits (advisory), 2 when it
# cannot run, and 2 on a model error (the read is unknown, never a pass).
#
# The model call is `decision_watch.invoke_model`, looked up at call time (a module attribute, or
# a name bound while the pass loads). The cases replace it with ModelStub, which answers in the
# shape the pass asks for, as invoke_model does: `{key: [{"line": k, "verdict": v}, ...]}`. The
# stub numbers each case line from 1 in the order its text appears in the prompt, so a pass that
# sends its cases in one call and answers by number gets the verdict that belongs to each line.

RULE_ID = "output-write-in-ste"
RULE_TEXT = "Write plainly: short sentences, one term per meaning, no filler."
RULE_LINE = "**Output.** " + RULE_TEXT + "<!-- rule:output-write-in-ste -->\n"
RULE_WRAPPED = "**Output.** Write plainly: short\nsentences, one term per meaning, no filler.<!-- rule:output-write-in-ste -->\n"
C1 = "Write plainly and keep each sentence short, with one term for each meaning."
C2 = "Keep prose plain: short sentences and one name per meaning, with no filler."
C3 = "Write plain, short sentences, and avoid filler words in every report."
NC1 = "The kitchen serves soup on Fridays and bread on Mondays."
NC2 = "Lunch is at noon in the second-floor room."
PARA_TRAPS = [  # a lone quote, comment openers as text, and an opener inside a code span
    "Don't keep filler; write plainly, with short sentences and one term per meaning.",
    "Write plainly // with short sentences /* and one term per meaning, no filler.",
    "`<!-- note` Write plainly, short sentences, one term per meaning, no filler.",
]
MEASURE = [  # (text, label, what the stub answers): TP x3, FN x2, FP x1, TN x4
    ("Measure case one restates the rule in its own words.", "paraphrase", "paraphrase"),
    ("Measure case two restates the rule in its own words too.", "paraphrase", "paraphrase"),
    ("Measure case three restates the rule in other words.", "paraphrase", "paraphrase"),
    ("Measure case four restates the rule and the stub misses it.", "paraphrase", "distinct"),
    ("Measure case five restates the rule and the stub misses it too.", "paraphrase", "distinct"),
    ("Measure case six names the rule and the stub calls it a restatement.", "distinct", "paraphrase"),
    ("Measure case seven names the rule and adds local content.", "distinct", "distinct"),
    ("Measure case eight names the rule and adds a local step.", "distinct", "distinct"),
    ("Measure case nine names the rule and adds a local path.", "distinct", "distinct"),
    ("Measure case ten names the rule and adds a local date.", "distinct", "distinct"),
]


class ModelStub:
    """Stands in for decision_watch.invoke_model. `answer(prompt, shape)` returns (verdict, error)."""

    def __init__(self, answer):
        self.answer = answer
        self.calls = []

    def __call__(self, prompt, *args, **kwargs):
        self.calls.append(prompt)
        shape = kwargs.get("shape", args[2] if len(args) > 2 else None)
        return self.answer(prompt, shape)


def answers(table):
    """Answer each case the prompt holds, numbered from 1 in prompt order, with table[text]."""
    def answer(prompt, shape):
        key = next(iter(shape)) if isinstance(shape, dict) and shape else "verdicts"
        seen = sorted((prompt.find(text), text) for text in table if text in prompt)
        return {key: [{"line": k, "verdict": table[text]} for k, (_, text) in enumerate(seen, 1)]}, None
    return answer


def model_error(prompt, shape):
    return None, "model exited 1: stub"


def load_module():
    spec = importlib.util.spec_from_file_location("find_copies_under_test", MODULE)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def paraphrase(args, answer):
    """Run the pass in this process, with the model call stubbed. Returns (exit code, stdout, calls).

    The module loads inside the patch, so a name bound at import time gets the stub too."""
    import decision_watch  # noqa: E402  the one home of the model call
    stub = ModelStub(answer)
    out = io.StringIO()
    with mock.patch.object(decision_watch, "invoke_model", stub), contextlib.redirect_stdout(out), \
            contextlib.redirect_stderr(io.StringIO()):
        try:
            rc = load_module().main(args)
        except SystemExit as exc:
            rc = exc.code if isinstance(exc.code, int) else 2
    return rc, out.getvalue(), stub.calls


def figure(out, word):
    """The number printed beside `word`, before or after it, as a fraction. None when absent."""
    m = re.search(r"%s\D{0,40}?(\d+(?:\.\d+)?)(%%?)" % word, out, re.I) or \
        re.search(r"(\d+(?:\.\d+)?)(%%?)\D{0,40}?%s" % word, out, re.I)
    if not m:
        return None
    value = float(m.group(1))
    return value / 100 if m.group(2) == "%" else value


def git_show(sha, path):
    proc = subprocess.run(["git", "-C", REPO, "show", f"{sha}:{path}"], capture_output=True)
    return proc.stdout.decode("utf-8", "replace") if proc.returncode == 0 else None


class ParaphraseTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(dir=RUN_FOLDER)
        self.root = os.path.join(self.tmp.name, "tree")

    def tearDown(self):
        self.tmp.cleanup()

    def tree(self, agent_lines, rule_text=RULE_LINE, files=1):
        """A claude-settings-shaped tree: CLAUDE.md holds the rule, agents/ holds the lines."""
        write(self.root, "CLAUDE.md", "# Rules\n\n" + rule_text)
        write(self.root, "skills/placeholder/README.md", "Nothing here yet.\n")
        per = -(-len(agent_lines) // files)
        for i in range(files):
            chunk = agent_lines[i * per:(i + 1) * per]
            write(self.root, f"agents/writer{i:02d}.md", "".join(line + "\n" for line in chunk))
        return self.root

    def measure_set(self):
        cases = [{"id": f"m{i:02d}", "rule_id": RULE_ID, "rule_at": "9d577ab4^", "text": text,
                  "source": f"agents/writer.md:{i}@5a5f081e", "label": label, "why": "measure fixture"}
                 for i, (text, label, _) in enumerate(MEASURE, 1)]
        path = os.path.join(self.tmp.name, "measure.json")
        with open(path, "w", encoding="utf-8") as f:
            json.dump(cases, f)
        return path

    def assertFigure(self, out, word, expected):
        value = figure(out, word)
        self.assertIsNotNone(value, f"no {word} figure was printed: {out!r}")
        self.assertAlmostEqual(value, expected, places=2, msg=f"{word} is {value}, expected {expected}: {out!r}")

    def test_lexical_prefilter_sends_only_candidate_lines(self):
        root = self.tree([C1, NC1, NC2])
        rc, out, calls = paraphrase(["--paraphrase", "--parent", root], answers({C1: "distinct"}))
        self.assertEqual(len(calls), 1, f"the pass made {len(calls)} model calls; expected one for the one candidate line")
        self.assertIn(C1, calls[0], "the candidate line was not in the model call")
        self.assertNotIn(NC1, calls[0], "a line that shares no word with the rule went to the model")
        self.assertNotIn(NC2, calls[0], "a line that shares no word with the rule went to the model")

    def test_all_candidates_go_in_one_model_call(self):
        root = self.tree([C1, NC1, C2, NC2, C3])
        rc, out, calls = paraphrase(["--paraphrase", "--parent", root],
                                    answers({C1: "distinct", C2: "distinct", C3: "distinct"}))
        self.assertEqual(len(calls), 1, f"the pass made {len(calls)} model calls for three candidates; expected one")
        for text in (C1, C2, C3):
            self.assertIn(text, calls[0], f"candidate {text!r} was not in the one model call")

    def test_model_error_prints_unknown_and_is_never_a_pass(self):
        root = self.tree([C1])
        rc, out, calls = paraphrase(["--paraphrase", "--parent", root], model_error)
        self.assertEqual(len(calls), 1, "the model was never asked, so the error case was not reached")
        lines = [line for line in out.splitlines() if line.strip()]
        self.assertTrue(lines, "the pass printed nothing on a model error")
        self.assertIn("UNKNOWN", lines[-1], f"the last line on a model error is not UNKNOWN: {lines[-1]!r}")
        self.assertFalse([line for line in lines if "PASS" in line], "a model error printed a PASS line")
        self.assertEqual(rc, 2, f"a model error is a read that could not run: expected exit 2, got {rc!r}")

    def test_exit_zero_on_hits_with_one_line_per_hit(self):
        root = self.tree([C1, C2, C3])
        rc, out, calls = paraphrase(["--paraphrase", "--parent", root],
                                    answers({C1: "paraphrase", C2: "distinct", C3: "paraphrase"}))
        self.assertEqual(len(calls), 1, f"the pass made {len(calls)} model calls; expected one")
        hits = re.findall(r"^(\S+):(\d+): PARA001 (\S+) may restate$", out, re.M)
        self.assertEqual([(p.replace(os.sep, "/").endswith("agents/writer00.md"), int(n), rule) for p, n, rule in hits],
                         [(True, 1, RULE_ID), (True, 3, RULE_ID)],
                         f"the PARA001 lines are not one per paraphrase verdict: {out!r}")
        self.assertEqual(rc, 0, f"hits are advisory: expected exit 0, got {rc!r}")

    def test_measure_prints_precision_recall_and_sample_count(self):
        path = self.measure_set()
        rc, out, calls = paraphrase(["--measure", path], answers({text: stub for text, _, stub in MEASURE}))
        self.assertEqual(len(calls), 1, f"--measure made {len(calls)} model calls for ten cases; expected one batched call")
        # TP 3, FN 2, FP 1, TN 4: precision 3 of 4 flagged, recall 3 of 5 paraphrases.
        self.assertFigure(out, "precision", 0.75)
        self.assertFigure(out, "recall", 0.60)
        self.assertFigure(out, "sample", 10)

    def test_measure_model_error_prints_unknown_and_no_figure(self):
        path = self.measure_set()
        rc, out, calls = paraphrase(["--measure", path], model_error)
        self.assertEqual(len(calls), 1, f"--measure made {len(calls)} model calls; expected one")
        self.assertIn("UNKNOWN", out, f"a model error on --measure printed no UNKNOWN: {out!r}")
        self.assertIsNone(figure(out, "precision"), f"a model error printed a precision figure: {out!r}")
        self.assertEqual(rc, 2, f"a model error is a read that could not run: expected exit 2, got {rc!r}")

    def test_one_model_call_per_run_at_full_size(self):
        lines = [f"Write plainly, keep sentence {i} short, with one term per meaning and no filler." for i in range(60)]
        root = self.tree(lines, files=12)
        rc, out, calls = paraphrase(["--paraphrase", "--parent", root], answers({text: "paraphrase" for text in lines}))
        self.assertEqual(len(calls), 1, f"the pass made {len(calls)} model calls for 60 candidate lines; expected one")
        missing = [text for text in lines if text not in calls[0]]
        self.assertFalse(missing, f"{len(missing)} of 60 candidate lines were not in the call, e.g. {missing[:1]}")
        self.assertEqual(len(re.findall(r"PARA001", out)), 60, "the 60 paraphrase verdicts did not all print a PARA001 line")

    def test_no_candidate_line_means_no_model_call(self):
        root = self.tree([NC1, NC2])
        rc, out, calls = paraphrase(["--paraphrase", "--parent", root], answers({}))
        self.assertEqual(len(calls), 0, f"the pass called the model {len(calls)} times with no candidate line")
        self.assertNotIn("PARA001", out, "a line with no candidate was reported")
        self.assertEqual(rc, 0, f"with no candidate line the pass exited {rc!r}; expected 0")

    def test_a_rule_quoted_in_a_fence_is_not_a_rule(self):
        fence = "Before the rules.\n\n```\nKeep every table cell under twelve words.<!-- rule:fence-only-rule -->\n```\n\n" + RULE_LINE
        root = self.tree([C1], rule_text=fence)
        rc, out, calls = paraphrase(["--paraphrase", "--parent", root], answers({C1: "paraphrase"}))
        self.assertEqual(len(calls), 1, "the candidate was never sent, so the fenced rule was never tested")
        self.assertFalse(any("fence-only-rule" in call for call in calls), "a rule quoted in a fenced block was sent as a rule")
        self.assertNotIn("fence-only-rule", out, "a rule quoted in a fenced block was reported")

    def test_a_lone_quote_and_comment_openers_in_text_stay_candidates(self):
        root = self.tree(PARA_TRAPS)
        rc, out, calls = paraphrase(["--paraphrase", "--parent", root], answers({text: "distinct" for text in PARA_TRAPS}))
        self.assertEqual(len(calls), 1, f"the pass made {len(calls)} model calls for three candidates; expected one")
        for text in PARA_TRAPS:
            self.assertIn(text, calls[0], f"a candidate with {text!r} did not reach the model")

    def test_a_rule_sentence_wrapped_across_lines_is_read_whole(self):
        root = self.tree([C1], rule_text=RULE_WRAPPED)
        rc, out, calls = paraphrase(["--paraphrase", "--parent", root], answers({C1: "distinct"}))
        self.assertEqual(len(calls), 1, f"the pass made {len(calls)} model calls; expected one")
        self.assertIn("short sentences", calls[0].lower(),
                      "the rule sentence was not joined across its line break: 'short sentences' is missing")

    def test_reads_only(self):
        root = self.tree([C1, NC1])
        before = sorted(os.walk(root))
        rc, out, calls = paraphrase(["--paraphrase", "--parent", root], answers({C1: "paraphrase"}))
        self.assertEqual(len(calls), 1, "the pass did not run, so there is no read to check for writes")
        self.assertEqual(before, sorted(os.walk(root)), "the pass wrote into the tree it scanned")


class ParaphraseLabelledSetTest(unittest.TestCase):
    """lint/paraphrase_labelled.json: its shape, its floor, and that each claude-settings source is a
    real line that holds the text. A child source (`repo:path:line@sha`) names a clone that CI does
    not have, so only its form is checked here. Its text was checked against the clone when the set was built."""

    SOURCE = re.compile(r"^(?:(?P<repo>[a-z_]+):)?(?P<path>[^:@]+):(?P<line>[0-9]+)@(?P<sha>[0-9a-f]{7,40})$")
    FIELDS = {"id", "rule_id", "rule_at", "text", "source", "label", "why"}

    def load(self):
        self.assertTrue(os.path.isfile(LABELLED), "lint/paraphrase_labelled.json is missing")
        with open(LABELLED, encoding="utf-8") as f:
            cases = json.load(f)
        self.assertIsInstance(cases, list, "the labelled set is not a JSON list of cases")
        return cases

    def test_each_case_has_the_fields_and_a_known_label(self):
        cases = self.load()
        for case in cases:
            missing = self.FIELDS - set(case)
            self.assertFalse(missing, f"case {case.get('id')!r} lacks {sorted(missing)}")
            self.assertIn(case["label"], ("paraphrase", "distinct"), f"case {case['id']} has label {case['label']!r}")
            self.assertTrue(case["why"].strip(), f"case {case['id']} has an empty why")
            self.assertNotIn("\n", case["text"], f"case {case['id']} text spans lines")
        ids = [case["id"] for case in cases]
        self.assertEqual(len(ids), len(set(ids)), "two cases share an id")

    def test_each_label_has_at_least_twenty_cases(self):
        cases = self.load()
        for label in ("paraphrase", "distinct"):
            n = sum(1 for case in cases if case.get("label") == label)
            self.assertGreaterEqual(n, 20, f"only {n} {label} cases; the floor is 20")

    def test_every_source_has_the_form_path_line_at_sha(self):
        for case in self.load():
            self.assertRegex(case["source"], self.SOURCE, f"case {case['id']} source {case['source']!r} is not path:line@sha")

    def test_claude_settings_sources_quote_their_line(self):
        for case in self.load():
            m = self.SOURCE.match(case["source"])
            self.assertIsNotNone(m, f"case {case['id']} source {case['source']!r} is not path:line@sha")
            if m.group("repo"):
                continue  # a child clone: form only, see the class note
            text = git_show(m.group("sha"), m.group("path"))
            self.assertIsNotNone(text, f"case {case['id']}: {m.group('path')} cannot be read at {m.group('sha')}")
            lines = text.split("\n")
            line = int(m.group("line"))
            self.assertLessEqual(line, len(lines), f"case {case['id']}: line {line} is past the end of {m.group('path')}")
            self.assertIn(case["text"], lines[line - 1], f"case {case['id']}: the text is not on {case['source']}")

    def test_each_rule_id_is_an_anchor_at_its_rule_at(self):
        anchors = {}
        for case in self.load():
            sha = case["rule_at"]
            if sha not in anchors:
                self.assertIsNotNone(git_show(sha, "CLAUDE.md"), f"rule_at {sha} cannot be read")
                found = set()
                for path in ("CLAUDE.md", "output-styles/shiv-stylisms.md"):
                    found |= set(re.findall(r"rule:([a-z0-9-]+)", git_show(sha, path) or ""))
                anchors[sha] = found
            self.assertIn(case["rule_id"], anchors[sha], f"case {case['id']}: no rule:{case['rule_id']} anchor at {sha}")


if __name__ == "__main__":
    try:
        unittest.main()
    finally:
        shutil.rmtree(RUN_FOLDER, ignore_errors=True)

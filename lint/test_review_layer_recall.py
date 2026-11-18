"""Review-layer recall eval: fixture-shape cases, scorer-report cases on the committed fixture, and scorer rules on inline fixtures.

The fixture is tests/review_layer_recall/fixture.json: committed data, no network. The scorer is
lint/review_layer_recall.py, run as

  python3 lint/review_layer_recall.py --fixture <fixture.json> --findings <findings.json>

and it prints one JSON report:

  {"n": {"incidents": int, "controls": int},
   "layers": {<layer>: {"recall": {"status": "measured" | "unknown", "caught": int | null, "of": int},
                        "cost": {"status": "unknown"}}}}

`of` is the number of incidents whose answer key names the layer. Recall is "measured" only when the
findings hold a verdict for each of those incidents. Otherwise it is "unknown", never 0. A findings
file is a JSON list of {"pr": int, "layer": str, "verdict": "PASS" | "FAIL" | "PARTIAL"}; a FAIL by a
layer on an incident's PR counts as caught. A PARTIAL row, a null, or any other value makes its layer
unknown, never a miss, and a row never counts for another layer. An incident labelled "unknown" counts
in n.incidents and in no layer's of. Cost stays unknown: the review record stores no cost.
"""
import json
import os
import re
import shutil
import subprocess
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
import _test_temp  # noqa: E402  test-temp-standard: one run folder per run (the one home, lint/_test_temp.py)

FIXTURE = os.path.join(ROOT, "tests", "review_layer_recall", "fixture.json")
SCORER = os.path.join(HERE, "review_layer_recall.py")
LAYERS = ("reviewer", "refuter", "fix_verifier", "design_reviewer")
BASES = ("revert message", "revert subject and changed files", "revert message and PR title")
SCORER_MISSING = "scorer missing: lint/review_layer_recall.py is not in the tree"
SCORER_TIMEOUT = 120  # hang guard, well above one local run of the scorer
SHA_SHORT = re.compile(r"[0-9a-f]{7,40}")
SHA_FULL = re.compile(r"[0-9a-f]{40}")


def load_fixture():
    with open(FIXTURE, encoding="utf-8") as fh:
        return json.load(fh)


def run_scorer(test, run, rows, fixture_path):
    """Runs the scorer on one fixture and the findings rows, and returns its parsed report. The one home of a scorer run."""
    if not os.path.isfile(SCORER):
        test.fail(SCORER_MISSING)
    findings = os.path.join(run, "findings.json")
    with open(findings, "w", encoding="utf-8") as fh:
        json.dump(rows, fh)
    proc = subprocess.run(
        [sys.executable, SCORER, "--fixture", fixture_path, "--findings", findings],
        capture_output=True, text=True, timeout=SCORER_TIMEOUT, cwd=ROOT, env=clean_env())
    test.assertEqual(proc.returncode, 0, "scorer exited %d" % proc.returncode)
    try:
        return json.loads(proc.stdout)
    except ValueError:
        test.fail("scorer stdout is not one JSON report")


def clean_env():
    """The caller's GitHub settings, stripped, so a scorer run reaches no repo."""
    return {k: v for k, v in os.environ.items() if not k.startswith("GH_") and k != "GITHUB_TOKEN"}


def synthetic_findings(fixture):
    """Findings for the scorer cases. The reviewer FAILs every other reviewer incident, in PR order.
    The fix verifier FAILs each of its incidents. The refuter and the design reviewer have no record.
    Each control gets a reviewer PASS, which must not move any recall."""
    rows = []
    reviewer_prs = sorted(i["pr"] for i in fixture["incidents"] if i["layer"] == "reviewer")
    for index, pr in enumerate(reviewer_prs):
        rows.append({"pr": pr, "layer": "reviewer", "verdict": "FAIL" if index % 2 == 0 else "PASS"})
    for inc in fixture["incidents"]:
        if inc["layer"] == "fix_verifier":
            rows.append({"pr": inc["pr"], "layer": "fix_verifier", "verdict": "FAIL"})
    for ctl in fixture["controls"]:
        rows.append({"pr": ctl["pr"], "layer": "reviewer", "verdict": "PASS"})
    return rows


class FixtureShape(unittest.TestCase):
    """Green controls: the fixture the scorer reads has the shape the eval needs."""

    @classmethod
    def setUpClass(cls):
        cls.fixture = load_fixture()

    def test_incident_count_is_ten_to_fifteen(self):
        self.assertTrue(10 <= len(self.fixture["incidents"]) <= 15, "incident count is outside 10 to 15")

    def test_incident_layers_are_in_the_layer_set(self):
        for inc in self.fixture["incidents"]:
            self.assertIn(inc["layer"], LAYERS, "incident #%s names a layer outside the set" % inc["pr"])

    def test_incident_prs_are_positive_and_unique(self):
        prs = [inc["pr"] for inc in self.fixture["incidents"]]
        for pr in prs:
            self.assertTrue(isinstance(pr, int) and pr > 0, "an incident has no positive PR number: %r" % (pr,))
        self.assertEqual(len(prs), len(set(prs)), "an incident PR appears twice")

    def test_each_incident_names_its_revert_commits(self):
        for inc in self.fixture["incidents"]:
            self.assertTrue(inc["reverts"], "incident #%s lists no revert commit" % inc["pr"])
            for sha in inc["reverts"]:
                self.assertIsNotNone(SHA_SHORT.fullmatch(sha), "incident #%s has a malformed revert sha" % inc["pr"])

    def test_each_incident_names_its_basis(self):
        for inc in self.fixture["incidents"]:
            self.assertIn(inc["basis"], BASES, "incident #%s basis is not an allowed source" % inc["pr"])

    def test_each_answer_key_is_one_line(self):
        for inc in self.fixture["incidents"]:
            key = inc["answer_key"]
            self.assertNotIn("\n", key, "incident #%s answer key spans lines" % inc["pr"])
            self.assertTrue(20 <= len(key) <= 240, "incident #%s answer key is not a short one-line key" % inc["pr"])

    def test_fixture_reaches_the_empty_state_for_a_layer(self):
        counts = {layer: 0 for layer in LAYERS}
        for inc in self.fixture["incidents"]:
            counts[inc["layer"]] += 1
        self.assertIn(0, counts.values(), "no layer has zero incidents, so the empty state is untested")

    def test_controls_are_ten_merged_prs_with_full_shas(self):
        controls = self.fixture["controls"]
        self.assertEqual(len(controls), 10, "control count is not 10")
        for ctl in controls:
            self.assertTrue(ctl.get("merged_at"), "control #%s has no merge time" % ctl["pr"])
            self.assertIsNotNone(SHA_FULL.fullmatch(ctl.get("merge_sha", "")), "control #%s has no full merge sha" % ctl["pr"])

    def test_controls_do_not_overlap_incidents(self):
        incident_prs = {inc["pr"] for inc in self.fixture["incidents"]}
        control_prs = {ctl["pr"] for ctl in self.fixture["controls"]}
        self.assertEqual(incident_prs & control_prs, set(), "a PR is both an incident and a control")


class ScorerReport(unittest.TestCase):
    """The scorer's report on the committed fixture, with n and recall taken from the fixture."""

    def setUp(self):
        self.run = _test_temp.run_folder()

    def tearDown(self):
        shutil.rmtree(self.run, ignore_errors=True)

    def scorer_report(self, rows):
        return run_scorer(self, self.run, rows, FIXTURE)

    def test_report_names_every_layer_with_n_from_the_fixture(self):
        fixture = load_fixture()
        report = self.scorer_report(synthetic_findings(fixture))
        self.assertEqual(report["n"]["incidents"], len(fixture["incidents"]), "n.incidents is not the fixture's incident count")
        self.assertEqual(report["n"]["controls"], len(fixture["controls"]), "n.controls is not the fixture's control count")
        self.assertEqual(sorted(report["layers"]), sorted(LAYERS), "the report names the wrong layer set")
        for layer in LAYERS:
            entry = report["layers"][layer]
            self.assertIn("recall", entry, "%s has no recall block" % layer)
            self.assertIn("cost", entry, "%s has no cost block" % layer)
            self.assertEqual(entry["cost"].get("status"), "unknown", "%s cost is not unknown; the review record stores no cost" % layer)

    def test_recall_is_exact_per_layer_for_synthetic_findings(self):
        fixture = load_fixture()
        report = self.scorer_report(synthetic_findings(fixture))
        scope = {layer: sorted(i["pr"] for i in fixture["incidents"] if i["layer"] == layer) for layer in LAYERS}
        for layer in LAYERS:
            self.assertEqual(report["layers"][layer]["recall"]["of"], len(scope[layer]), "%s: of is not its incident count in the fixture" % layer)
        reviewer = scope["reviewer"]
        self.assertEqual(
            report["layers"]["reviewer"]["recall"],
            {"status": "measured", "caught": (len(reviewer) + 1) // 2, "of": len(reviewer)},
            "reviewer recall is not the synthetic count")
        fix = scope["fix_verifier"]
        self.assertEqual(
            report["layers"]["fix_verifier"]["recall"],
            {"status": "measured", "caught": len(fix), "of": len(fix)},
            "fix verifier recall is not the synthetic count")
        self.assertEqual(
            report["layers"]["refuter"]["recall"],
            {"status": "unknown", "caught": None, "of": len(scope["refuter"])},
            "refuter recall is not unknown, though no refuter record exists")
        self.assertEqual(
            report["layers"]["design_reviewer"]["recall"],
            {"status": "unknown", "caught": None, "of": 0},
            "design reviewer recall is not unknown at n=0")


def incident(pr, layer):
    """One incident for an inline fixture. The scorer reads only its PR and its layer."""
    return {"pr": pr, "reverted": "1234567", "reverts": ["7654321"], "layer": layer,
            "basis": "revert message", "answer_key": "Scorer case: the scorer reads the PR and the layer only."}


class ScorerRules(unittest.TestCase):
    """Scorer rules on small inline fixtures. Each case states the rule it proves and the recall it expects."""

    def setUp(self):
        self.run = _test_temp.run_folder()

    def tearDown(self):
        shutil.rmtree(self.run, ignore_errors=True)

    def score(self, incidents, rows, name):
        path = os.path.join(self.run, name + ".json")
        with open(path, "w", encoding="utf-8") as fh:
            json.dump({"about": "inline scorer case", "layers": list(LAYERS), "incidents": incidents, "controls": []}, fh)
        return run_scorer(self, self.run, rows, path)

    def test_a_partly_covered_layer_reads_unknown_not_measured(self):
        incidents = [incident(101, "reviewer"), incident(102, "reviewer"), incident(103, "reviewer")]
        rows = [{"pr": 101, "layer": "reviewer", "verdict": "FAIL"}, {"pr": 102, "layer": "reviewer", "verdict": "PASS"}]
        recall = self.score(incidents, rows, "partly-covered")["layers"]["reviewer"]["recall"]
        self.assertEqual(recall["of"], 3, "reviewer's of is not its three incidents")
        self.assertEqual(recall["status"], "unknown", "a layer with PR 103 missing a verdict reads %r, not unknown" % (recall,))
        self.assertIsNone(recall["caught"], "a layer with PR 103 missing a verdict reads %r, not caught null" % (recall,))

    def test_a_non_verdict_row_reads_unknown_never_caught_zero_of_one(self):
        for bad in ("PARTIAL", None, "MAYBE", 7):
            with self.subTest(verdict=bad):
                rows = [{"pr": 201, "layer": "fix_verifier", "verdict": bad}]
                recall = self.score([incident(201, "fix_verifier")], rows, "non-verdict")["layers"]["fix_verifier"]["recall"]
                self.assertEqual(recall["of"], 1, "fix_verifier's of is not its one incident")
                self.assertEqual(recall["status"], "unknown", "a %r verdict row reads %r, not unknown" % (bad, recall))
                self.assertIsNone(recall["caught"], "a %r verdict row reads %r, not caught null" % (bad, recall))

    def test_one_partial_row_beside_a_fail_and_a_pass_reads_unknown(self):
        incidents = [incident(301, "reviewer"), incident(302, "reviewer"), incident(303, "reviewer")]
        rows = [{"pr": 301, "layer": "reviewer", "verdict": "FAIL"},
                {"pr": 302, "layer": "reviewer", "verdict": "PASS"},
                {"pr": 303, "layer": "reviewer", "verdict": "PARTIAL"}]
        recall = self.score(incidents, rows, "partial-beside-valid")["layers"]["reviewer"]["recall"]
        self.assertEqual(recall["of"], 3, "reviewer's of is not its three incidents")
        self.assertEqual(recall["status"], "unknown", "a PARTIAL row beside a FAIL and a PASS reads %r, not unknown" % (recall,))
        self.assertIsNone(recall["caught"], "a PARTIAL row beside a FAIL and a PASS reads %r, not caught null" % (recall,))

    def test_a_pass_row_on_a_one_incident_layer_reads_measured_caught_zero(self):
        # Control beside the non-verdict cases: a valid PASS is a real miss, so the unknown rule does not hide misses.
        rows = [{"pr": 401, "layer": "refuter", "verdict": "PASS"}]
        recall = self.score([incident(401, "refuter")], rows, "pass-control")["layers"]["refuter"]["recall"]
        self.assertEqual(recall["of"], 1, "refuter's of is not its one incident")
        self.assertEqual(recall["status"], "measured", "a PASS row reads %r, not measured" % (recall,))
        self.assertEqual(recall["caught"], 0, "a PASS row reads %r, not caught 0" % (recall,))

    def test_a_verdict_row_for_one_layer_never_credits_another(self):
        incidents = [incident(501, "reviewer"), incident(502, "fix_verifier")]
        rows = [{"pr": 501, "layer": "fix_verifier", "verdict": "FAIL"}, {"pr": 502, "layer": "reviewer", "verdict": "FAIL"}]
        report = self.score(incidents, rows, "cross-layer")
        reviewer = report["layers"]["reviewer"]["recall"]
        fix = report["layers"]["fix_verifier"]["recall"]
        self.assertEqual(reviewer["of"], 1, "reviewer's of is not its one incident")
        self.assertEqual(reviewer["status"], "unknown", "a fix_verifier FAIL on PR 501 credits the reviewer layer: %r" % (reviewer,))
        self.assertEqual(fix["of"], 1, "fix_verifier's of is not its one incident")
        self.assertEqual(fix["status"], "unknown", "a reviewer FAIL on PR 502 credits the fix_verifier layer: %r" % (fix,))

    def test_a_fail_row_on_its_own_layer_credits_that_layer_control(self):
        # Control beside the cross-layer case: the same PR, on its own layer, is caught.
        incidents = [incident(501, "reviewer"), incident(502, "fix_verifier")]
        rows = [{"pr": 501, "layer": "reviewer", "verdict": "FAIL"}]
        reviewer = self.score(incidents, rows, "own-layer")["layers"]["reviewer"]["recall"]
        self.assertEqual(reviewer["of"], 1, "reviewer's of is not its one incident")
        self.assertEqual(reviewer["status"], "measured", "a reviewer FAIL on its own incident reads %r, not measured" % (reviewer,))
        self.assertEqual(reviewer["caught"], 1, "a reviewer FAIL on its own incident reads %r, not caught 1" % (reviewer,))

    def test_a_fully_covered_layer_with_a_fail_reads_measured_and_caught(self):
        incidents = [incident(601, "reviewer"), incident(602, "reviewer"), incident(603, "reviewer")]
        rows = [{"pr": 601, "layer": "reviewer", "verdict": "FAIL"},
                {"pr": 602, "layer": "reviewer", "verdict": "PASS"},
                {"pr": 603, "layer": "reviewer", "verdict": "FAIL"}]
        recall = self.score(incidents, rows, "fully-covered")["layers"]["reviewer"]["recall"]
        self.assertEqual(recall["of"], 3, "reviewer's of is not its three incidents")
        self.assertEqual(recall["status"], "measured", "a fully covered layer with FAILs reads %r, not measured" % (recall,))
        self.assertEqual(recall["caught"], 2, "a fully covered layer with two FAILs reads %r, not caught 2" % (recall,))


if __name__ == "__main__":
    unittest.main()

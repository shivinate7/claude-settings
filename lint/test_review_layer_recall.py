"""Review-layer recall eval: fixture-shape cases (green) and scorer-report cases (red until the scorer exists).

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
layer on an incident's PR counts as caught. Cost stays unknown: the review record stores no cost.
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
    """Red until the scorer exists: the scorer's report, with n and recall taken from the fixture."""

    def setUp(self):
        self.run = _test_temp.run_folder()

    def tearDown(self):
        shutil.rmtree(self.run, ignore_errors=True)

    def scorer_report(self, rows):
        if not os.path.isfile(SCORER):
            self.fail(SCORER_MISSING)
        findings = os.path.join(self.run, "findings.json")
        with open(findings, "w", encoding="utf-8") as fh:
            json.dump(rows, fh)
        proc = subprocess.run(
            [sys.executable, SCORER, "--fixture", FIXTURE, "--findings", findings],
            capture_output=True, text=True, timeout=SCORER_TIMEOUT, cwd=ROOT, env=clean_env())
        self.assertEqual(proc.returncode, 0, "scorer exited %d" % proc.returncode)
        try:
            return json.loads(proc.stdout)
        except ValueError:
            self.fail("scorer stdout is not one JSON report")

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


if __name__ == "__main__":
    unittest.main()

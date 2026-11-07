#!/usr/bin/env python3
"""Cases for lint/check_artifact_cites.py. Standard library only.

    python3 lint/test_check_artifact_cites.py

A decision, a debt or a roadmap step cites a claude.ai artifact as `artifact:<id>`, and the id must be
in the registry (the "artifacts" key of the extras file, read by lint/layout.py artifacts()). A bare
claude.ai/artifact or claude.ai/code/artifact link is red, even for a registered page, and even inside a
code fence: a fence does not make a link safe. Briefs, handoffs and other folders are not read.

Each case builds a temp repo: the record files on its working tree, and the record branch (roadmap by
default) as one commit that holds the steps. It runs the real script with --root and reads its exit code
and FAIL lines. ARTIFACT_CITES_UNDER_TEST overrides the script path.
"""
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
SCRIPT = os.environ.get("ARTIFACT_CITES_UNDER_TEST") or os.path.join(HERE, "check_artifact_cites.py")
sys.path.insert(0, HERE)
import _test_git  # noqa: E402,F401  test-run signing opt-out (lint/_test_git.py)
import _test_temp  # noqa: E402  test-temp-standard: one run folder per test run (lint/_test_temp.py)
sys.path.insert(0, os.path.join(HERE, "..", "testing"))
import tracked_tree  # noqa: E402  rm_tree also removes the read-only git objects of a fixture (testing/tracked_tree.py)

EXTRAS = ".claude/layout-extras.json"
REGISTERED = "page01"
UNREGISTERED = "ghost99"
URL = "https://claude.ai/artifact/" + REGISTERED
CODE_URL = "https://claude.ai/code/artifact/" + REGISTERED
REGISTRY = {"kinds": {}, "rolled-out": True,
            "artifacts": [{"id": REGISTERED, "url": URL, "role": "waiting-page", "account": "work"}]}
RUN_FOLDER = None  # made in setUpModule, so an import leaks no folder


def setUpModule():
    global RUN_FOLDER
    RUN_FOLDER = _test_temp.run_folder()


def tearDownModule():
    shutil.rmtree(RUN_FOLDER, ignore_errors=True)  # test-temp-standard: teardown removes the run folder


class CiteTests(unittest.TestCase):
    def setUp(self):
        self.assertTrue(os.path.isfile(SCRIPT), "script absent: lint/check_artifact_cites.py")
        self.root = tempfile.mkdtemp(prefix="cites_", dir=RUN_FOLDER)
        self.addCleanup(tracked_tree.rm_tree, self.root)
        self.git("init", "-q")
        self.put(EXTRAS, json.dumps(REGISTRY))

    def git(self, *args, env=None, stdin=None):
        """One git step of the fixture repo. Commit signing is off for the run (lint/_test_git.py)."""
        done = subprocess.run(["git", "-C", self.root, "-c", "user.name=test", "-c", "user.email=test@example.invalid", *args],
                              capture_output=True, text=True, input=stdin, env=env, timeout=30, check=True)
        return done.stdout

    def put(self, rel, text):
        path = os.path.join(self.root, *rel.split("/"))
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(text)

    def decision(self, text):
        self.put("docs/decisions/x.md", text)

    def steps(self, files, origin=False):
        """The record branch: one commit on `roadmap` whose roadmap/data/steps holds each {name: text}. With origin,
        the commit lives on a bare origin only, the state a fetch leaves: no local ref."""
        env = dict(os.environ, GIT_INDEX_FILE=os.path.join(self.root, ".git", "record-index"))
        self.git("read-tree", "--empty", env=env)
        for name, text in files.items():
            blob = self.git("hash-object", "-w", "--stdin", stdin=text, env=env).strip()
            self.git("update-index", "--add", "--cacheinfo", "100644,%s,roadmap/data/steps/%s" % (blob, name), env=env)
        tree = self.git("write-tree", env=env).strip()
        commit = self.git("commit-tree", tree, "-m", "record", env=env).strip()
        self.git("update-ref", "refs/heads/roadmap", commit)
        if origin:
            bare = tempfile.mkdtemp(prefix="origin-", dir=RUN_FOLDER)
            self.addCleanup(tracked_tree.rm_tree, bare)
            subprocess.run(["git", "init", "-q", "--bare", bare], check=True, capture_output=True)
            self.git("remote", "add", "origin", bare)
            self.git("push", "-q", "origin", "roadmap")
            self.git("update-ref", "-d", "refs/heads/roadmap")
            self.assertTrue(self.ref_exists("refs/remotes/origin/roadmap"), "the fixture lost origin's record ref")  # scope: the fixture
            self.assertFalse(self.ref_exists("refs/heads/roadmap"), "the fixture kept the local record ref")

    def ref_exists(self, ref):
        return subprocess.run(["git", "-C", self.root, "rev-parse", "--verify", "-q", ref], capture_output=True).returncode == 0

    def run_check(self):
        done = subprocess.run([sys.executable, SCRIPT, "--root", self.root], capture_output=True, text=True, timeout=60)
        return done.returncode, done.stdout + done.stderr

    def flagged(self, out):
        return [line for line in out.splitlines() if line.startswith("check_artifact_cites: FAIL:")]

    def assertRed(self, path, why):
        code, out = self.run_check()
        self.assertEqual(code, 1, "%s. Output:\n%s" % (why, out))
        self.assertTrue(any(path in line for line in self.flagged(out)), "%s: no FAIL line names %s. Output:\n%s" % (why, path, out))

    def assertGreen(self, why):
        code, out = self.run_check()
        self.assertEqual(code, 0, "%s. Output:\n%s" % (why, out))
        self.assertEqual(self.flagged(out), [], why)

    def test_a_bare_link_is_red_even_when_the_artifact_is_registered(self):
        self.decision("# Record\n\nSee " + URL + ".\n")
        self.assertRed("docs/decisions/x.md", "a bare link in a decision was not refused")

    def test_a_bare_code_form_link_in_a_decision_is_red(self):
        self.decision("# Record\n\nSee " + CODE_URL + ".\n")
        self.assertRed("docs/decisions/x.md", "a bare /code/artifact/ link in a decision was not refused")

    def test_a_bare_link_in_a_debt_is_red(self):
        self.put("docs/debts/y.md", "# Debt\n\nSee " + URL + ".\n")
        self.assertRed("docs/debts/y.md", "a bare link in a debt was not refused")

    def test_a_registered_artifact_cite_is_green(self):
        self.decision("# Record\n\nSee artifact:" + REGISTERED + ".\n")
        self.assertGreen("an artifact:<id> cite with a registered id was refused")

    def test_an_artifact_cite_with_an_unregistered_id_is_red(self):
        self.decision("# Record\n\nSee artifact:" + UNREGISTERED + ".\n")
        self.assertRed("docs/decisions/x.md", "an artifact:<id> cite with no registry entry was not refused")

    def test_a_bare_link_inside_a_code_fence_is_still_red(self):
        self.decision("# Record\n\n```\n" + URL + "\n```\n")
        self.assertRed("docs/decisions/x.md", "a bare link inside a code fence was not refused: a fence does not make it safe")

    def test_a_bare_link_after_a_lone_quote_is_red(self):
        self.decision("# Record\n\nDon't cite the page by its link: " + URL + "\n")
        self.assertRed("docs/decisions/x.md", "a bare link after a lone quote was not refused")

    def test_a_bare_link_in_a_backtick_span_that_runs_over_a_line_is_red(self):
        self.decision("# Record\n\nA span `opens here\nand the link is " + URL + " before it closes`.\n")
        self.assertRed("docs/decisions/x.md", "a bare link inside a span that runs over a line was not refused")

    def test_a_bare_link_inside_an_html_comment_is_red(self):
        self.decision("# Record\n\n<!-- kept for later: " + URL + " -->\n")
        self.assertRed("docs/decisions/x.md", "a bare link inside an HTML comment was not refused")

    def test_a_bare_link_in_a_roadmap_step_is_red(self):
        self.steps({"c1.json": json.dumps({"title": "Step", "note": "See " + URL + "."})})
        self.assertRed("roadmap/data/steps/c1.json", "a bare link in a roadmap step was not refused")

    def test_a_bare_link_in_a_step_on_origin_only_is_red(self):
        self.steps({"c1.json": json.dumps({"note": URL})}, origin=True)
        self.assertRed("roadmap/data/steps/c1.json", "a bare link in a step on origin only was not refused")

    def test_a_bare_link_escaped_in_step_json_is_red(self):
        self.steps({"c1.json": '{"note": "\\u0068ttps://claude.ai/artifact/' + REGISTERED + '"}\n'})
        self.assertRed("roadmap/data/steps/c1.json", "a bare link escaped as \\u0068 in step JSON was not refused")

    def test_a_bare_link_between_comment_openers_in_a_step_is_red(self):
        self.steps({"c1.json": json.dumps({"title": "/* open", "note": URL, "more": "*/ // #"})})
        self.assertRed("roadmap/data/steps/c1.json", "a bare link between comment openers in a step was not refused")

    def test_a_bare_link_between_fence_markers_in_a_step_is_red(self):
        self.steps({"c1.json": json.dumps({"title": "```", "note": URL, "more": "```"})})
        self.assertRed("roadmap/data/steps/c1.json", "a bare link between fence markers in a step was not refused")

    def test_a_bare_link_in_a_brief_a_handoff_or_another_folder_is_green(self):
        self.decision("# Record\n\nSee " + URL + ".\n")  # scope control: the decision is read, so the greens below are not a skip
        self.put("briefs/b.md", "# Brief\n\nSee " + URL + ".\n")
        self.put("handoffs/h.md", "# Handoff\n\nSee " + URL + ".\n")
        self.put("docs/design/page.md", "# Design\n\nSee " + URL + ".\n")
        code, out = self.run_check()
        flagged = self.flagged(out)
        self.assertTrue(any("docs/decisions/x.md" in line for line in flagged),
                        "the scope control was not read: the decision with a bare link was not refused. Output:\n" + out)
        for path in ("briefs/b.md", "handoffs/h.md", "docs/design/page.md"):
            self.assertFalse(any(path in line for line in flagged), "%s is a working file or outside the scope, and it was refused" % path)

    def test_text_with_comment_openers_and_quotes_but_no_link_is_green(self):
        self.decision("# Record\n\nDon't use /* or // or # here, and `a span\nthat closes`.\n")
        self.steps({"c1.json": json.dumps({"title": "/* open", "note": "Don't stop */ here", "ask": "artifact:" + REGISTERED})})
        self.assertGreen("text with no link was refused")

    def test_a_registry_that_cannot_be_read_is_red_never_green(self):
        self.put(EXTRAS, "{not json")
        self.decision("# Record\n\nNo link here.\n")
        code, out = self.run_check()
        self.assertEqual(code, 1, "an unreadable registry passed. Output:\n" + out)
        self.assertTrue(self.flagged(out), "an unreadable registry printed no FAIL line. Output:\n" + out)

    def test_a_bad_mark_does_not_say_a_readable_registry_cannot_be_read(self):
        """A "rolled-out" that is not JSON true or false, with a registry whose ids read: the cites check does not report the
        registry unreadable, because its id read (check_artifact_cites.py:144) takes no export folder. The check still refuses
        under the mark, since it reads record folders. The valid mark is the control."""
        self.decision("# Record\n\nSee artifact:" + REGISTERED + ".\n")
        self.put(EXTRAS, json.dumps(dict(REGISTRY, **{"rolled-out": True})))
        self.assertGreen("the control (a valid mark) refused a registered artifact cite")
        self.put(EXTRAS, json.dumps(dict(REGISTRY, **{"rolled-out": "yes"})))
        code, out = self.run_check()
        self.assertNotIn("the artifacts registry cannot be read", out, "a registry whose ids read was reported unreadable under a bad mark. Output:\n" + out)
        self.assertNotEqual(code, 0, "a bad rolled-out mark passed the cites check. Output:\n" + out)
        self.assertTrue(any("rolled-out" in line for line in self.flagged(out)), "the refusal under a bad mark does not name the mark. Output:\n" + out)


if __name__ == "__main__":
    unittest.main()

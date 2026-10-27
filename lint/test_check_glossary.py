#!/usr/bin/env python3
"""Cases for lint/check_glossary.py. Standard library only.

    python3 lint/test_check_glossary.py

GLOSSARY.md holds one table under `## Terms`: term, meaning, home, not. The check fails when a
row's home is not an existing file or a rule marker, and when a file the change adds has a path
segment that a row lists under "not". It never reads prose.

Each case builds a temp tree: a copy of the module, the rule-audit module it reads rule markers
from, and the files it checks. The diff cases also make a temp git repo and set
refs/remotes/origin/main, the base the script diffs against. GLOSSARY_UNDER_TEST overrides the
module path.
"""
import os
import shutil
import subprocess
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
MODULE = os.environ.get("GLOSSARY_UNDER_TEST") or os.path.join(HERE, "check_glossary.py")
sys.path.insert(0, os.path.join(HERE, "..", "testing"))
import tracked_tree  # noqa: E402  copies what git lists, so no fixture lists files (testing/tracked_tree.py)

CLAUDE_MD = "# Rules\n\nOne rule.<!-- rule:one-rule -->\n"
HEAD = "# Glossary\n\n## Terms\n\n| Term | Meaning | Home | Not |\n|---|---|---|---|\n"
ROWS = ("| handoff | A session's notes file. | `docs/handoff.md` | `handover` |\n"
        "| batch | Lane PRs that merge together. | `rule:one-rule` | `batch branch`, `bundle` |\n"
        "| owner | The person who rules. | `rule:one-rule` | — |\n")


class GlossaryTests(unittest.TestCase):
    def setUp(self):
        self.assertTrue(os.path.isfile(MODULE), "module absent: lint/check_glossary.py")
        self.tree = tempfile.mkdtemp(prefix="gls_")
        self.addCleanup(tracked_tree.rm_tree, self.tree)
        tracked_tree.copy_tracked(self.tree, "lint", "hooks")  # rule_audit.py and the check's other imports
        shutil.copyfile(MODULE, os.path.join(self.tree, "lint", "check_glossary.py"))
        self.put("CLAUDE.md", CLAUDE_MD)
        self.put("docs/handoff.md", "# Handoff\n")
        self.put("GLOSSARY.md", HEAD + ROWS)

    def put(self, rel, text="x\n"):
        path = os.path.join(self.tree, *rel.split("/"))
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8", newline="\n") as f:
            f.write(text)

    def run_check(self, *args):
        env = {k: v for k, v in os.environ.items() if k != "CI"}
        r = subprocess.run([sys.executable, os.path.join(self.tree, "lint", "check_glossary.py"), *args],
                           cwd=self.tree, capture_output=True, encoding="utf-8", env=env)
        return r.returncode, r.stdout + r.stderr

    def git(self, *args):
        subprocess.run(["git", *args], cwd=self.tree, check=True, capture_output=True)

    def base_repo(self):
        """Commit the tree as origin/main, then return; later puts are the change."""
        self.git("init", "-q")
        self.git("-c", "user.email=t@t", "-c", "user.name=t", "add", "-A")
        self.git("-c", "user.email=t@t", "-c", "user.name=t", "commit", "-q", "-m", "base")
        self.git("update-ref", "refs/remotes/origin/main", "HEAD")

    def commit(self):
        self.git("-c", "user.email=t@t", "-c", "user.name=t", "add", "-A")
        self.git("-c", "user.email=t@t", "-c", "user.name=t", "commit", "-q", "-m", "change")

    # Homes

    def test_clean_tree_passes(self):
        code, out = self.run_check("docs/notes.md")
        self.assertEqual(code, 0, out)

    def test_missing_home_path_fails(self):
        self.put("GLOSSARY.md", HEAD + ROWS + "| debt | A gap. | `debts/README.md` | — |\n")
        code, out = self.run_check("docs/notes.md")
        self.assertEqual(code, 1, out)
        self.assertIn("debts/README.md", out)

    def test_missing_rule_home_fails(self):
        self.put("GLOSSARY.md", HEAD + ROWS + "| note | A line. | `rule:no-such-rule` | — |\n")
        code, out = self.run_check("docs/notes.md")
        self.assertEqual(code, 1, out)
        self.assertIn("rule:no-such-rule", out)

    def test_row_with_no_home_fails(self):
        self.put("GLOSSARY.md", HEAD + ROWS + "| note | A line. |  | — |\n")
        code, out = self.run_check("docs/notes.md")
        self.assertEqual(code, 1, out)
        self.assertIn("note", out)

    def test_missing_glossary_fails(self):
        os.remove(os.path.join(self.tree, "GLOSSARY.md"))
        code, out = self.run_check("docs/notes.md")
        self.assertEqual(code, 1, out)

    def test_glossary_with_no_rows_fails(self):
        self.put("GLOSSARY.md", HEAD)
        code, out = self.run_check("docs/notes.md")
        self.assertEqual(code, 1, out)

    def test_rows_outside_terms_section_are_not_read(self):
        self.put("GLOSSARY.md", HEAD + ROWS + "\n## Open\n\n| step | Two meanings. | `nowhere.md` | — |\n")
        code, out = self.run_check("docs/notes.md")
        self.assertEqual(code, 0, out)

    # Not-names in paths, files given

    def test_given_path_with_not_name_fails(self):
        code, out = self.run_check("hooks/handover_note.py")
        self.assertEqual(code, 1, out)
        self.assertIn("handover", out)
        self.assertIn("handoff", out)

    def test_multi_word_not_name_in_hyphen_segment_fails(self):
        code, out = self.run_check("docs/batch-branch-notes.md")
        self.assertEqual(code, 1, out)
        self.assertIn("batch branch", out)

    def test_not_name_ignores_case(self):
        code, out = self.run_check("docs/HandOver.md")
        self.assertEqual(code, 1, out)

    def test_not_name_inside_a_longer_word_passes(self):
        code, out = self.run_check("docs/rebundled.md", "docs/handoverly.md")
        self.assertEqual(code, 0, out)

    def test_plural_not_name_fails(self):
        code, out = self.run_check("docs/handovers.md")
        self.assertEqual(code, 1, out)
        code, out = self.run_check("docs/batch-branches.md")
        self.assertEqual(code, 1, out)

    def test_camel_case_not_name_fails(self):
        code, out = self.run_check("hooks/batchBranch.py")
        self.assertEqual(code, 1, out)
        code, out = self.run_check("hooks/HandoverNote.py")
        self.assertEqual(code, 1, out)

    def test_multi_word_split_across_segments_passes(self):
        code, out = self.run_check("batch/branch.md")
        self.assertEqual(code, 0, out)

    def test_dash_means_no_not_name(self):
        code, out = self.run_check("docs/x.md")
        self.assertEqual(code, 0, out)

    # Not-names in paths, from the diff

    def test_added_path_with_not_name_fails(self):
        self.base_repo()
        self.put("hooks/bundle.py")
        self.commit()
        code, out = self.run_check()
        self.assertEqual(code, 1, out)
        self.assertIn("hooks/bundle.py", out)

    def test_prose_mention_of_not_name_passes(self):
        self.base_repo()
        self.put("docs/readme.md", "Never call a handoff a handover, or a batch a bundle.\n")
        self.commit()
        code, out = self.run_check()
        self.assertEqual(code, 0, out)

    def test_old_path_with_not_name_passes(self):
        self.put("docs/handover.md")
        self.base_repo()
        self.put("docs/handover.md", "changed\n")
        self.commit()
        code, out = self.run_check()
        self.assertEqual(code, 0, out)

    def test_renamed_path_with_not_name_fails(self):
        self.put("docs/old.md", "same text\n" * 20)
        self.base_repo()
        self.git("mv", "docs/old.md", "docs/handover.md")
        self.commit()
        code, out = self.run_check()
        self.assertEqual(code, 1, out)

    def test_clean_diff_passes(self):
        self.base_repo()
        self.put("docs/handoff-notes.md")
        self.commit()
        code, out = self.run_check()
        self.assertEqual(code, 0, out)

    def test_unreadable_diff_is_red_in_ci(self):
        # No git repo: the diff cannot run. Unknown is red in CI and quiet locally.
        code, out = self.run_check()
        self.assertEqual(code, 0, out)
        self.assertIn("UNKNOWN", out)
        env = dict(os.environ, CI="true")
        r = subprocess.run([sys.executable, os.path.join(self.tree, "lint", "check_glossary.py")],
                           cwd=self.tree, capture_output=True, encoding="utf-8", env=env)
        self.assertEqual(r.returncode, 1, r.stdout + r.stderr)

    def test_unknown_option_fails(self):
        code, out = self.run_check("--files")
        self.assertEqual(code, 1, out)


class RepoGlossaryTests(unittest.TestCase):
    def test_repo_glossary_homes_resolve(self):
        """The real GLOSSARY.md: every home resolves. A path list keeps git out of it."""
        r = subprocess.run([sys.executable, MODULE, "README.md"], cwd=os.path.dirname(HERE),
                           capture_output=True, encoding="utf-8")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)


# o13 lane B retired these names (GLOSSARY.md rows agent, mutation test, red run, command). Claude
# Code's own names stay: the hook events, `subagent_type`, the CLAUDE_CODE_* settings keys and the
# `subagents/` transcript folder. Two old names stay readable until their end day, each in one file:
# the `--subagent` flag of local_time.py and the `_subagentCapUntil` field of config_watch.py.
RETIRED = (r"(?i)sub-?agent|harness[-_ ]scope|HARNESS_SCOPE|mutation harness|AUTHOR_HARNESS"
           r"|ask-steps-run-alone|\b(?:ask|count|harmless|background)_steps?\b|\b(?:ask|harmless|chained) steps?\b"
           r"|roles-one-role-per-worker|output-never-echo-worker-report|worker_transcript"
           r"|WORKER_FOLDED_KEYS|(?i:red[- ]proof)")
PLATFORM = (r"SubagentStop|SubagentStart|subagent_type|(?:\\u0043|C)LAUDE_CODE_\w+"
            r"|[\"'/`]subagents(?=[\"'/`])|subagents/|SUBAGENT_MODEL")
STAYS = {  # path: the one old name it may still hold, and why
    "hooks/local_time.py": "--subagent",            # read until OLD_FLAG_ENDS
    "hooks/config_watch.py": "_subagentCapUntil",   # read until OLD_NAME_ENDS
    "hooks/test_local_time.py": "--subagent",       # pins the old flag until then
    "hooks/test_config_watch.py": "_subagentCapUntil",
    "testing/skip-locally-fail-in-ci.test.mjs": "Red proof",  # header shared with copies in other repos
    "lint/test_find_copies.py": "Red proof",        # the fixture copy of that header
    "mods/plain-diff/docs/mockup.html": "red proof",  # sample diff text
}
SKIP = ("skills/impeccable/", "lint/test_check_glossary.py", "GLOSSARY.md")  # GLOSSARY names them as "Not"


class RepoRetiredNamesTests(unittest.TestCase):
    def test_no_retired_name_in_tracked_files(self):
        """Every tracked path and text file: no name o13 lane B retired, outside the platform's own."""
        import re
        root = os.path.dirname(HERE)
        listed = subprocess.run(["git", "ls-files"], cwd=root, capture_output=True,
                                encoding="utf-8")
        self.assertEqual(listed.returncode, 0, listed.stderr)
        retired, platform = re.compile(RETIRED), re.compile(PLATFORM)
        found = []
        for rel in listed.stdout.splitlines():
            if rel.startswith(SKIP):
                continue
            if retired.search(rel):
                found.append("%s: the path" % rel)
            try:
                with open(os.path.join(root, rel), encoding="utf-8") as f:
                    text = f.read()
            except (OSError, UnicodeDecodeError):
                continue
            text = platform.sub("", text)
            if rel in STAYS:
                text = text.replace(STAYS[rel], "")
            for number, line in enumerate(text.splitlines(), 1):
                hit = retired.search(line)
                if hit:
                    found.append("%s:%d: %s" % (rel, number, hit.group(0)))
        self.assertEqual(found, [], "\n".join(found[:40]))


if __name__ == "__main__":
    unittest.main()

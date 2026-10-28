#!/usr/bin/env python3
"""Cases for lint/check_glossary.py. Standard library only.

    python3 lint/test_check_glossary.py

GLOSSARY.md holds one table under `## Terms`: term, meaning, home, not. The check fails when a
row's home is not an existing file or a rule marker, when a file the change adds has a path
segment that a row lists under "not", and when a line the change adds holds a "not" name in an
identifier, a rule anchor, a record slug or a hook message. It never reads prose.

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


class Fixture(unittest.TestCase):
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


class GlossaryTests(Fixture):
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


class CodeNameTests(Fixture):
    """The widened check: identifiers, rule anchors, record slugs and hook messages on added lines."""
    EXTRA = ("| refuse | What a guard does. | `rule:one-rule` | `deny (prose)`, `block (prose)` |\n"
             "| agent | Anything the Agent tool starts. | `rule:one-rule` | `subagent` |\n"
             "| safety hole | A guard that lets an act through. | `rule:one-rule` | `hole` |\n")

    def setUp(self):
        super().setUp()
        self.put("GLOSSARY.md", HEAD + ROWS + self.EXTRA)

    def change(self, rel, text):
        """Commit the fixture as the base once, then add one file as the change. Each call reads only that file's diff."""
        if not os.path.isdir(os.path.join(self.tree, ".git")):
            self.base_repo()
        else:
            self.git("update-ref", "refs/remotes/origin/main", "HEAD")
        self.put(rel, text)
        self.commit()
        return self.run_check()

    def red(self, rel, text, *shown):
        code, out = self.change(rel, text)
        self.assertEqual(code, 1, out)
        for s in shown:
            self.assertIn(s, out)

    def green(self, rel, text):
        code, out = self.change(rel, text)
        self.assertEqual(code, 0, out)

    # Identifiers

    def test_python_identifier_with_not_name_fails(self):
        self.red("hooks/x.py", "def bundle_it():\n    pass\n", "hooks/x.py:1", "bundle")

    def test_python_camel_and_attribute_and_argument_fail(self):
        self.red("hooks/x.py", "def f(batchBranch):\n    pass\n", "batch branch")
        self.red("hooks/y.py", "import os\nos.bundle = 1\n", "hooks/y.py:2")
        self.red("hooks/z.py", "def f(*, bundle=1):\n    pass\n", "hooks/z.py:1")

    def test_javascript_identifier_fails(self):
        self.red("actions/x.mjs", "const handover = 1;\n", "actions/x.mjs:1")

    def test_shell_and_yaml_identifier_fail(self):
        self.red("bin/x.sh", "bundle=1\n", "bin/x.sh:1")
        self.red(".github/workflows/x.yml", "jobs:\n  bundle:\n    runs-on: x\n", "x.yml:2")

    def test_clean_identifier_passes(self):
        self.green("hooks/x.py", "def handoff_note():\n    pass\n")

    def test_not_name_inside_a_longer_identifier_word_passes(self):
        self.green("hooks/x.py", "def bundled_up():\n    pass\n")

    def test_comment_and_docstring_prose_pass(self):
        self.green("hooks/x.py", '"""The handover is prose."""\n# the bundle of lanes\nx = 1  # a handover\n')
        self.green("actions/x.mjs", "// a handover\n/* the bundle\n   of lanes */\nconst a = 1;\n")

    def test_platform_names_pass_and_compounds_fail(self):
        self.green("hooks/x.py", 'subagent_type = "subagent_type"\nSubagentStop = 1\n')
        self.green("hooks/y.py", 'import os\nos.environ["CLAUDE_CODE_SUBAGENT_MODEL"] = "x"\n')
        self.red("hooks/z.py", "subagent_count = 1\n", "hooks/z.py:1")

    def test_prose_tagged_word_is_left_out_of_code_names(self):
        self.green("hooks/x.py", 'deny = 1\nblock_it = 2\nMSG = "The guard will deny it."\n')
        self.green("actions/x.mjs", "const renderBlock = 1;\n")

    def test_prose_tagged_word_is_read_in_a_path_anchor_and_slug(self):
        self.red("hooks/deny.py", "x = 1\n", "hooks/deny.py")
        self.red("CLAUDE.md", CLAUDE_MD + "Two.<!-- rule:two-deny-rule -->\n", "deny")
        self.red("docs/notes.md", "See `stop-blocks-live-tasks`.\n", "block")

    def test_issues_key_passes_in_yaml_only(self):
        self.put("GLOSSARY.md", HEAD + ROWS + "| finding | A report. | `rule:one-rule` | `issue` |\n")
        self.green(".github/workflows/x.yml", "permissions:\n  issues: write\n")

    def test_only_added_lines_are_read(self):
        self.put("hooks/x.py", "def bundle_old():\n    pass\n")
        self.base_repo()
        self.put("hooks/x.py", "def bundle_old():\n    pass\n\n\ndef fine():\n    pass\n")
        self.commit()
        code, out = self.run_check()
        self.assertEqual(code, 0, out)

    def test_a_changed_line_is_read(self):
        self.put("hooks/x.py", "def bundle_old():\n    pass\n")
        self.base_repo()
        self.put("hooks/x.py", "def bundle_old(a):\n    pass\n")
        self.commit()
        code, out = self.run_check()
        self.assertEqual(code, 1, out)

    def test_marked_line_passes(self):
        self.green("hooks/x.py", "bundle = 1  # glossary-ok: the platform spells it so\n")

    def test_given_file_is_read_whole(self):
        self.put("hooks/x.py", "bundle = 1\n")
        code, out = self.run_check("hooks/x.py")
        self.assertEqual(code, 1, out)

    def test_unparsable_python_is_unknown_and_red_in_ci(self):
        self.put("hooks/x.py", "def (:\n")
        code, out = self.run_check("hooks/x.py")
        self.assertEqual(code, 0, out)
        self.assertIn("UNKNOWN", out)
        r = subprocess.run([sys.executable, os.path.join(self.tree, "lint", "check_glossary.py"), "hooks/x.py"],
                           cwd=self.tree, capture_output=True, encoding="utf-8", env=dict(os.environ, CI="true"))
        self.assertEqual(r.returncode, 1, r.stdout + r.stderr)

    # Rule anchors and record slugs

    def test_anchor_with_not_name_fails(self):
        self.red("CLAUDE.md", CLAUDE_MD + "Two.<!-- rule:one-bundle-rule -->\n", "CLAUDE.md:4", "bundle")

    def test_anchor_reference_in_code_comment_fails(self):
        self.red("hooks/x.py", "x = 1  # rule:one-bundle-rule\n", "hooks/x.py:1")

    def test_clean_anchor_passes(self):
        self.green("CLAUDE.md", CLAUDE_MD + "Two.<!-- rule:two-lanes-merge -->\n")

    def test_backticked_slug_in_markdown_fails(self):
        self.red("docs/notes.md", "See `handover-notes-record` for why.\n", "docs/notes.md:1", "handover")

    def test_slug_key_in_json_fails(self):
        self.red("lint/x.json", '{"bundle-it-now": {"kind": "check"}}\n', "lint/x.json:1")

    def test_unticked_hyphen_prose_passes(self):
        self.green("docs/notes.md", "A bundle-of-lanes phrase, and a handover-style note.\n")

    # Hook messages

    def test_hook_message_with_not_name_fails(self):
        self.red("hooks/guard.py", 'MSG = "Refused: this handover is stale."\n', "hooks/guard.py:1", "handover")

    def test_hook_pattern_string_passes(self):
        self.green("hooks/guard.py", 'PAT = r"(?im)^[ \\t]*(bundle|round)[ \\t]+(\\d)"\n')

    def test_hook_message_f_string_fails(self):
        self.red("hooks/guard.py", 'def m(x):\n    return f"Refused {x}: a bundle."\n', "hooks/guard.py:2")

    def test_clean_hook_message_passes(self):
        self.green("hooks/guard.py", 'MSG = "Refused: this handoff is stale."\n')

    def test_test_fixture_message_passes(self):
        self.green("hooks/test_guard.py", 'MSG = "Refused: this handover is stale."\n')

    def test_mutation_test_snippet_passes(self):
        self.green("hooks/mutate_guard.py", 'M = "return bundle(x)  # a bundle"\n')

    def test_message_outside_hooks_passes(self):
        self.green("lint/x.py", 'MSG = "a handover line"\n')

    def test_hook_docstring_passes(self):
        self.green("hooks/guard.py", 'def f():\n    """The handover case."""\n')

    # Scanner traps (rule building-scanner-respects-strings)

    def test_slashes_in_a_string_do_not_open_a_comment(self):
        self.red("actions/x.mjs", 'const u = "http://x"; const bundle = 1;\n', "actions/x.mjs:1")

    def test_block_comment_opener_in_a_string_does_not_open_a_comment(self):
        self.red("actions/x.mjs", 'const a = "/*"; const bundle = 2; /* end */\n', "actions/x.mjs:1")

    def test_hash_in_a_shell_string_does_not_open_a_comment(self):
        self.red("bin/x.sh", 'echo "# x"; bundle=1\n', "bin/x.sh:1")

    def test_python_hash_in_a_string_does_not_hide_the_line(self):
        self.red("hooks/x.py", 'a = "# x"; bundle = 1\n', "hooks/x.py:1")

    def test_template_literal_spans_lines(self):
        text = "const t = `a // b\n a handover /* c\n`;\nconst bundle = 1;\n"
        self.red("actions/x.mjs", text, "actions/x.mjs:4")
        self.green("actions/y.mjs", "const t = `a // b\n a handover /* c\n`;\nconst fine = 1;\n")

    def test_lone_quote_in_a_comment_does_not_swallow_the_next_line(self):
        self.red("actions/x.mjs", "// don't use it\nconst bundle = 1;\n", "actions/x.mjs:2")
        self.red("bin/x.sh", "# don't use it\nbundle=1\n", "bin/x.sh:2")
        self.red("hooks/x.py", "# don't use it\nbundle = 1\n", "hooks/x.py:2")

    def test_lone_quote_in_jsx_text_does_not_swallow_the_next_line(self):
        self.red("actions/x.mjs", "const p = <p>Don't</p>;\nconst bundle = 1;\n", "actions/x.mjs:2")

    def test_lone_quote_in_shell_text_does_not_swallow_the_next_line(self):
        self.red("bin/x.sh", "echo don't\nbundle=1\n", "bin/x.sh:2")


    # Reviewer round 1: false alarms and misses of the first scanner

    def test_a_term_that_holds_a_not_word_passes(self):
        self.green("hooks/x.py", "safety_hole = 1\nclass SafetyHole:\n    pass\nM = 'This is a safety hole.'\n")
        self.green("CLAUDE.md", CLAUDE_MD + "Two.<!-- rule:roles-safety-hole-check -->\n")
        self.green("docs/notes.md", "See `no-safety-hole-opened`.\n")

    def test_the_bare_not_word_still_fails_beside_a_term(self):
        self.red("hooks/x.py", "hole = 1\nsafety_hole = 2\n", "hooks/x.py:1")

    def test_a_regex_literal_with_a_backtick_does_not_flip_the_string_parity(self):
        self.red("actions/x.mjs", "const a = s.replace(/[()`]/g, '');\nconst b = `t`;\nconst bundle = 1;\n", "actions/x.mjs:3")

    def test_a_regex_literal_with_a_quote_does_not_hide_the_line(self):
        self.red("actions/x.mjs", 'const a = s.replace(/"/g, ""); const bundle = 1;\n', "actions/x.mjs:1")

    def test_a_division_is_not_a_regex(self):
        self.red("actions/x.mjs", "const a = b / c; const bundle = d / e;\n", "actions/x.mjs:1")

    def test_powershell_backtick_is_an_escape_not_a_string(self):
        self.red("bin/x.ps1", 'Write-Host "a`"b"; $bundle = 1\nWrite-Host `\n$bundle2 = 2\n', "bin/x.ps1:1")

    def test_shell_hash_inside_a_word_is_not_a_comment(self):
        self.red("bin/x.sh", 'n=${#x}; bundle=1\n', "bin/x.sh:1")
        self.red("bin/y.sh", 'echo $#; bundle=1\n', "bin/y.sh:1")

    def test_shell_heredoc_body_is_prose(self):
        self.green("bin/x.sh", "cat <<EOF\nthe handover note\nEOF\nfine=1\n")
        self.red("bin/y.sh", "cat <<'EOF'\nthe note\nEOF\nbundle=1\n", "bin/y.sh:4")

    def test_unquoted_yaml_prose_passes_and_keys_and_names_fail(self):
        self.green("actions/x.yml", "description: Fails on a bundle in the lane.\nruns:\n  using: composite\n")
        self.red("actions/y.yml", "needs: bundle\n", "actions/y.yml:1")
        self.red("actions/z.yml", "steps:\n  - bundle\n", "actions/z.yml:2")
        self.green("actions/w.yml", "steps:\n  - run: |\n      echo a handover here\n      echo b\n")

    def test_an_f_string_message_is_read_whole(self):
        self.red("hooks/guard.py", 'def m(a, n):\n    return f"{a} handover {n}"\n', "hooks/guard.py:2")

    def test_a_message_with_one_word_and_punctuation_fails(self):
        self.red("hooks/guard.py", 'A = "handover:"\nB = "(handover)"\n', "hooks/guard.py:1")

    def test_a_multi_line_message_is_read_when_any_of_its_lines_is_added(self):
        self.red("hooks/guard.py", 'M = ("first line "\n     "then a handover line")\n', "hooks/guard.py")
        self.red("hooks/y.py", 'M = """first\nthe handover\n"""\n', "hooks/y.py")

    def test_more_extensions_are_read(self):
        for ext in (".ts", ".tsx", ".jsx", ".bash", ".toml"):
            self.red("src/x" + ext, "bundle = 1\n", "src/x" + ext)

    def test_a_from_import_module_is_read(self):
        self.red("hooks/x.py", "from handover import f\n", "hooks/x.py:1")

    def test_a_non_utf8_or_odd_named_file_is_no_traceback(self):
        self.base_repo()
        with open(os.path.join(self.tree, "hooks", "bad.py"), "wb") as f:
            f.write(b"x = '\xff'\n")
        self.put("docs/\u00e4.md", "fine\n")
        self.commit()
        code, out = self.run_check()
        self.assertNotIn("Traceback", out)
        self.assertEqual(code, 0, out)


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

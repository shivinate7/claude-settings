#!/usr/bin/env python3
"""Cases for janitor/prove_agent_end_reap.py: its Git Bash comes from the one home, hooks/git_bash.py. Standard library only.

    python3 janitor/test_prove_agent_end_reap.py -v

The cases read the script's syntax tree and run no proof. Fixture sources prove the checker before it judges the script.
"""
import ast
import os
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
SCRIPT = os.path.join(HERE, "prove_agent_end_reap.py")
HOME = "find_git_bash"  # the one home's function, hooks/git_bash.py
HOME_MODULE = "git_bash"
OWN_NAME = "git_bash"  # the name a script's own copy of the lookup would carry
OWN_PATHS = frozenset(("bash.exe", "ProgramFiles"))  # the strings a Windows lookup of its own holds


def defined_names(tree):
    return {n.name for n in ast.walk(tree) if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))}


def called_names(tree):
    called = set()
    for n in ast.walk(tree):
        if isinstance(n, ast.Call):
            if isinstance(n.func, ast.Name):
                called.add(n.func.id)
            elif isinstance(n.func, ast.Attribute):
                called.add(n.func.attr)
    return called


def imports_the_home(tree):
    for n in ast.walk(tree):
        if isinstance(n, ast.ImportFrom) and n.module == HOME_MODULE and any(a.name == HOME for a in n.names):
            return True
        if isinstance(n, ast.Import) and any(a.name == HOME_MODULE for a in n.names):
            return True
    return False


def defines_own_git_bash(tree):
    return OWN_NAME in defined_names(tree)


def holds_own_bash_path(tree):
    strings = {n.value for n in ast.walk(tree) if isinstance(n, ast.Constant) and isinstance(n.value, str)}
    return bool(OWN_PATHS & strings)


def calls_the_one_home(tree):
    """True when the source imports the home, calls it, and does not define its own function of that name."""
    return imports_the_home(tree) and HOME in called_names(tree) and HOME not in defined_names(tree)


def script_tree():
    with open(SCRIPT, encoding="utf-8") as f:
        return ast.parse(f.read(), SCRIPT)


class OneHome(unittest.TestCase):
    def test_the_proof_script_is_read_and_has_its_main(self):  # the control: the parse reads the real file
        self.assertIn("main", defined_names(script_tree()), "the parse of janitor/prove_agent_end_reap.py has no main")

    def test_the_proof_script_defines_no_git_bash_of_its_own(self):
        self.assertFalse(defines_own_git_bash(script_tree()),
                         "janitor/prove_agent_end_reap.py defines git_bash itself, not the one home hooks/git_bash.py")

    def test_the_proof_script_holds_no_bash_path_of_its_own(self):
        self.assertFalse(holds_own_bash_path(script_tree()),
                         "janitor/prove_agent_end_reap.py holds its own Git Bash path (bash.exe or ProgramFiles)")

    def test_the_proof_script_asks_the_one_home_for_git_bash(self):
        self.assertTrue(calls_the_one_home(script_tree()),
                        "janitor/prove_agent_end_reap.py does not import and call find_git_bash from hooks/git_bash.py")


class Checker(unittest.TestCase):
    """Fixture sources: the checks above must pass the one home and refuse a lookup of the script's own."""
    ASKS_THE_HOME = (
        "import sys\n"
        "from git_bash import find_git_bash\n"
        "def start(cwd):\n"
        "    return find_git_bash() or sys.exit('no git bash')\n")
    RENAMED_LOOKUP = (
        "import shutil\n"
        "def locate_bash():\n"
        "    return shutil.which('bash') or 'bash'\n")
    NAMES_THE_HOME_ONLY = (  # the home is named in a docstring and imported, but never called: a text match would pass it
        '"""Uses find_git_bash from git_bash, the one home."""\n'
        "import shutil\n"
        "from git_bash import find_git_bash\n"
        "def locate_bash():\n"
        "    return shutil.which('bash')\n")
    OWN_PATH_COPY = (
        "import os\n"
        "def lookup(env):\n"
        "    for var in ('ProgramFiles', 'ProgramW6432'):\n"
        "        if env.get(var):\n"
        "            return os.path.join(env[var], 'Git', 'bin', 'bash.exe')\n"
        "    return None\n")

    def test_a_source_that_asks_the_one_home_passes(self):
        tree = ast.parse(self.ASKS_THE_HOME)
        self.assertFalse(defines_own_git_bash(tree))
        self.assertFalse(holds_own_bash_path(tree))
        self.assertTrue(calls_the_one_home(tree))

    def test_a_renamed_lookup_that_never_calls_the_home_is_refused(self):
        self.assertFalse(calls_the_one_home(ast.parse(self.RENAMED_LOOKUP)))

    def test_a_docstring_or_an_import_that_never_calls_the_home_is_refused(self):
        self.assertFalse(calls_the_one_home(ast.parse(self.NAMES_THE_HOME_ONLY)))

    def test_a_lookup_under_a_new_name_with_the_windows_path_is_refused(self):
        self.assertTrue(holds_own_bash_path(ast.parse(self.OWN_PATH_COPY)))


if __name__ == "__main__":
    unittest.main()

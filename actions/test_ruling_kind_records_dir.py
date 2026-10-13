#!/usr/bin/env python3
"""Cases for actions/ruling-kind: the records-dir input and how check.sh passes it on.

    python3 actions/test_ruling_kind_records_dir.py

The action checks the records folder named by its records-dir input. The input defaults to
decisions, so a caller that sets nothing is checked as before. Stdlib only, so action.yml is
read as text, not parsed as YAML. Shape only: test_action.sh runs the action end to end.
"""
import os
import re
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ACTION = os.path.join(HERE, "ruling-kind")
ACTION_YML = os.path.join(ACTION, "action.yml")
CHECK_SH = os.path.join(ACTION, "check.sh")
ENV_MAP = re.compile(r"^\s+([A-Z][A-Z0-9_]*):\s*\$\{\{\s*inputs\.records-dir\s*\}\}\s*$", re.M)


def read(path):
    with open(path, encoding="utf-8") as f:
        return f.read()


def input_block(text, name):
    """The lines under `inputs:` -> `  <name>:`, or None. Stops at the next key of the same level."""
    lines = text.split("\n")
    if "inputs:" not in lines:
        return None
    body = []
    for line in lines[lines.index("inputs:") + 1:]:
        if line.strip() and not line.startswith(" "):
            break
        body.append(line)
    start = next((i for i, line in enumerate(body) if re.match(r"^  %s:\s*$" % re.escape(name), line)), None)
    if start is None:
        return None
    block = []
    for line in body[start + 1:]:
        if line.strip() and not line.startswith("    "):
            break
        block.append(line)
    return "\n".join(block)


class RecordsDirInput(unittest.TestCase):
    def test_records_dir_input_defaults_to_decisions(self):
        block = input_block(read(ACTION_YML), "records-dir")
        self.assertIsNotNone(block, "action.yml has no inputs.records-dir")
        m = re.search(r"^\s+default:\s*['\"]?([^'\"\s]*)['\"]?\s*$", block, re.M)
        self.assertIsNotNone(m, "inputs.records-dir has no default")
        self.assertEqual(m.group(1), "decisions")

    def test_check_sh_passes_the_records_dir_to_the_lint(self):
        m = ENV_MAP.search(read(ACTION_YML))
        self.assertIsNotNone(m, "no step env line maps inputs.records-dir to a variable")
        name = m.group(1)
        lint_lines = [line for line in read(CHECK_SH).split("\n")
                      if "check_ruling_kind.py" in line and not line.lstrip().startswith("#")]
        self.assertTrue(lint_lines, "check.sh does not run check_ruling_kind.py")
        flag = re.compile(r"--dir\s+\"?\$\{?%s\}?\"?(?=\s|$)" % re.escape(name))
        self.assertTrue(any(flag.search(line) for line in lint_lines),
                        "the lint call in check.sh does not pass --dir \"$%s\"" % name)


if __name__ == "__main__":
    unittest.main()

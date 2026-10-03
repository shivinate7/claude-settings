"""Every actions/*/action.yml must load. GitHub evaluates ${{ }} in action metadata,
so an expression outside runs.steps with/env/run/if, or one naming a context that
composite actions cannot read, breaks the action in every caller repo.
Run: python3 actions/test_action_metadata.py"""
import glob
import os
import re
import unittest

EXPR = re.compile(r"\$\{\{(.*?)\}\}")
KEY = re.compile(r"^(\s*)(?:- )?([\w-]+):(.*)$")
SCALAR_BLOCK = re.compile(r"^\s*[|>][+-]?\d?\s*(#.*)?$")
OK_KEYS = {"with", "env", "run", "if"}
# Context names unavailable in composite action metadata and steps.
BAD_CTX = re.compile(r"(?<![\w.-])(needs|jobs|secrets|strategy|matrix)\b")


def problems(text):
    """Return [(line_no, message)] for one action.yml."""
    out, stack, block = [], [], None  # stack: (indent, key); block: indent of open |/> scalar
    for n, line in enumerate(text.splitlines(), 1):
        indent = len(line) - len(line.lstrip())
        if block is not None and (not line.strip() or indent > block):
            pass  # continuation of the open block scalar: keeps the same stack
        else:
            block = None
            m = KEY.match(line)
            if m and not line.lstrip().startswith("#"):
                ind = len(m[1]) + (2 if line.lstrip().startswith("- ") else 0)
                while stack and stack[-1][0] >= ind:
                    stack.pop()
                stack.append((ind, m[2]))
                if SCALAR_BLOCK.match(m[3]):
                    block = len(m[1])
        keys = [k for _, k in stack]
        allowed = bool(keys) and keys[0] == "runs" and bool(OK_KEYS & set(keys[1:]))
        for e in EXPR.finditer(line):
            if not allowed:
                out.append((n, "expression outside runs with/env/run/if: " + e[0]))
            for c in BAD_CTX.finditer(e[1]):
                out.append((n, "context '%s' unavailable in composite actions: %s" % (c[1], e[0])))
    return out


class ActionMetadata(unittest.TestCase):
    def test_every_action_yml_loads(self):
        root = os.path.dirname(os.path.abspath(__file__))
        files = sorted(glob.glob(os.path.join(root, "*", "action.yml")))
        self.assertTrue(files)
        bad = []
        for f in files:
            with open(f, encoding="utf-8") as fh:
                for n, msg in problems(fh.read()):
                    bad.append("%s:%d: %s" % (os.path.relpath(f, os.path.dirname(root)), n, msg))
        self.assertEqual(bad, [], "\n" + "\n".join(bad))

    def test_detector_fixtures(self):
        ok = ("runs:\n  steps:\n    - env:\n        A: ${{ inputs.a }}\n      run: |\n"
              "        echo ${{ github.token }}: x\n      if: ${{ always() }}\n")
        self.assertEqual(problems(ok), [])
        self.assertEqual(problems("description: x ${{ inputs.a }}\n")[0][0], 1)
        self.assertEqual(problems("runs:\n  steps:\n    - env:\n        A: ${{ toJSON(needs) }}\n")[0][0], 4)
        self.assertEqual(problems("runs:\n  steps:\n    - run: ${{ matrix.x }}\n")[0][0], 3)
        self.assertEqual(problems("runs:\n  steps:\n    - env:\n        A: ${{ inputs.needs }}\n"), [])


if __name__ == "__main__":
    unittest.main()

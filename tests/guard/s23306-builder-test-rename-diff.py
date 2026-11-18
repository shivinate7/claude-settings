# section 23306
# A builder's commit, push and stop are judged on its own diff. A test-file change that only renames a test, or
# only edits its comments or docstrings, passes at all three (owner ruling, 2026-11-18 15:50 CST; decision
# builders-cannot-edit-tests). The Edit and Write side is pinned in section 23303. A change that alters a body or an
# assertion, drops a test, or edits a test file that is no python file stays refused.
#
# Each tree is one lazy diff repo (diff_repo, section 21304). The change stays uncommitted in the worktree, as a
# builder's own diff does. The python trees are checked with the ast helpers of section 23303 before any case is
# registered, so a tree that makes another change stops the run.
_CP_PRIOR_FAMILY = FAMILY
FAMILY = "builder-refuse"

CP_MJS_REL = "tests/widget.test.mjs"
CP_MJS = "test('base', () => {});\n"
CP_FILES = {**BASE_FILES, BR_CALC_REL: BR_CALC, CP_MJS_REL: CP_MJS}

# Changes the rule lets through: names, comments and docstrings only.
CP_ALLOW = [
    ("rename", [("def test_add():", "def test_sum():")]),
    ("comment", [("    # check the sum", "    # check the total")]),
    ("docstring", [('    """Doubling gives twice the value."""', '    """Doubling returns twice the value."""')]),
    ("rename-comment-docstring", [
        ("def test_add():", "def test_sum():"),
        ("    # check the sum", "    # check the total"),
        ('    """Doubling gives twice the value."""', '    """Doubling returns twice the value."""'),
    ]),
]
# Changes the rule keeps refused: a body or count changes, or the name leaves the runner's collection.
CP_REFUSE = [
    ("assertion", [("    assert 1 + 1 == 2", "    assert 1 + 1 == 3")]),
    ("removed-test", [(BR_TEST_DOUBLE_BLOCK, "")]),
    ("rename-and-body", [("def test_double():", "def test_twice():"),
                         ("    assert double(3) == 6", "    assert double(3) == 7")]),
    ("comment-and-assertion", [("    # check the sum\n    assert 1 + 1 == 2",
                                "    # check the total\n    assert 1 + 1 == 3")]),
]


def _cp_python(label, pairs, allowed):
    """A diff repo whose python test file changes as `pairs` say, after the ast check of that change."""
    text = _br_once(BR_CALC, pairs)
    _br_check(BR_CALC, text, allowed, label)
    return diff_repo("bt-cp-" + label, _put(BR_CALC_REL, text), files=CP_FILES)


def _cp_register(label, repo, allowed):
    """The three cases of one tree: commit, push and the first stop."""
    if allowed:
        tag = "builder-diff: %s test change" % label
        sh(tag + " is allowed at commit", COMMIT, "allow", cwd=repo, agent_id="bld1", agent_type="builder")
        sh(tag + " is allowed at push", PUSH, "allow", cwd=repo, agent_id="bld1", agent_type="builder")
        add(tag + " is allowed at the first stop", "allow", event="SubagentStop", cwd=repo,
            agent_id="bld1", agent_type="builder")
    else:
        tag = "builder-diff control: %s test change" % label
        sh(tag + " is denied at commit", COMMIT, "deny", rule=BDIFF, cwd=repo, agent_id="bld1", agent_type="builder")
        sh(tag + " is denied at push", PUSH, "deny", rule=BDIFF, cwd=repo, agent_id="bld1", agent_type="builder")
        add(tag + " is blocked at the first stop", "deny", rule=BDIFF, event="SubagentStop", cwd=repo,
            agent_id="bld1", agent_type="builder")


for _label, _pairs in CP_ALLOW:
    _cp_register(_label, _cp_python(_label, _pairs, True), True)
for _label, _pairs in CP_REFUSE:
    _cp_register(_label, _cp_python(_label, _pairs, False), False)

# A test file that is no python file: a comment-only edit is still refused, since the rule reads python only.
_cp_register("non-python comment", diff_repo("bt-cp-mjs", _put(CP_MJS_REL, CP_MJS + "// note\n"),
                                              files=CP_FILES), False)

FAMILY = _CP_PRIOR_FAMILY

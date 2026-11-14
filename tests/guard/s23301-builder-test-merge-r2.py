# section 23301
# A builder's merge that resolves a conflict in a test file, for three gaps the reader still lets through (decision builders-cannot-edit-tests;
# plan R31: a lost test is a silent accuracy hole).
#   1. A parent's top-level node that holds no test case (a loop, an if or with block, an assert, an assignment, a
#      check_* method, an autouse fixture, the __main__ block) is dropped from the result. The reader checks the other
#      top-level nodes the result adds, never the ones it drops, so a drop reads as nothing lost. It must read as lost.
#   2. A keep-both union of a dependency line in setup.cfg or tox.ini is refused as test config. It must be allowed,
#      as package.json and pyproject.toml are, and the old-content check still applies.
#   3. A case of the same name that both parents changed differently keeps one parent's body, so the other change
#      is lost and must be refused. Two different tests added under one name are the same loss.
# The controls pin what must stay allowed or denied. Each refusal's reason names one class of loss, in its own words.
# The fixtures reuse s23300's case helpers (_mt_case, _mt_refuse, _mt_allow, MT_CARRY, MT_BASE), which reuse s23264's
# conflict steps, so this section adds no copy of them.
_MT2_PRIOR_FAMILY = FAMILY
FAMILY = "builder-refuse"

MT2_CFG = "setup.cfg"
MT2_TOX = "tox.ini"
MT2_CFG_BASE = "[options]\ninstall_requires =\n    requests\n"
MT2_TOX_BASE = "[testenv]\ndeps =\n    pytest\n"
MT2_CFG_OFF = "[tool:pytest]\naddopts = --ignore=tests\n"
MT2_TAIL = "def test_tail():\n    assert 9\n"

MT2_LOOP = "for n in (1, 2):\n    check(n)\n"
MT2_WITH = "with open_fixture() as handle:\n    def test_in_with():\n        assert handle\n"
MT2_TRY = "try:\n    def test_in_try():\n        assert 1\nexcept ImportError:\n    pass\n"
MT2_IF = "if sys.platform != 'win32':\n    def test_posix():\n        assert 1\n"
MT2_ASSIGN = "r = check('cfg')\n"
MT2_ASSERT = "assert 2 + 2 == 4\n"
MT2_CLASS = ("class TestWidget:\n    def check_widget(self):\n        assert 1\n"
             "    def test_widget(self):\n        assert 2\n")
MT2_CLASS_KEPT = "class TestWidget:\n    def test_widget(self):\n        assert 2\n"
MT2_FIXTURE = "@pytest.fixture(autouse=True)\ndef reset_clock():\n    yield\n"
MT2_ENTRY = "if __name__ == '__main__':\n    main()\n"


def _mt2_node_case(name, node, kept="", head=MT_BASE, lane=MT_LANE, main=MT_MAIN):
    """A merge that conflicts at the end of a test file. The base is `head` then `node`, and each side appends its
    `lane` or `main` case after it. The resolution writes `head`, `kept` and both cases, so `node` is what it drops."""
    return _mt_case(name, [(TEST_A, head + node + lane)], [(TEST_A, head + node + main)], [TEST_A],
                    resolve=[(TEST_A, head + kept + lane + main)], stage=True,
                    files={**BASE_FILES, TEST_A: head + node})


def _mt2_union_case(name, rel, base, lane_line, main_line, tail=""):
    """A merge that conflicts in a dependency list of `rel`: each side adds one line after the base's last line. The
    resolution keeps both lines, then writes `tail`."""
    return _mt_case(name, [(rel, base + lane_line)], [(rel, base + main_line)], [rel],
                    resolve=[(rel, base + lane_line + main_line + tail)], stage=True,
                    files={**BASE_FILES, rel: base})


def _mt2_same(value):
    return "def test_same():\n    assert %d\n" % value


def _mt2_refuse(name, repo):
    """Denied at commit, at push and at the first stop, by builder-diff. The control pins the verdict, not the words."""
    sh(name + ", at commit", COMMIT, "deny", rule=BDIFF, cwd=repo, agent_id="bld1", agent_type="builder")
    sh(name + ", at push", PUSH, "deny", rule=BDIFF, cwd=repo, agent_id="bld1", agent_type="builder")
    add(name + ", at stop", "deny", rule=BDIFF, event="SubagentStop", cwd=repo, agent_id="bld1", agent_type="builder")


# ---- 1. A node that holds no test case, dropped where both parents hold it: refused as lost ----
# The empty state: the base holds no test case, only the node.
MT2_D_ENTRY_EMPTY = _mt2_node_case("mt2-drop-entry-empty", MT2_ENTRY, head="")
_mt_refuse("builder-refuse: a merge into a test file with no test case that drops the __main__ block is refused",
           MT2_D_ENTRY_EMPTY, "lost", (MT_CARRY["lost"],))
# The full-size state: each side adds thirty cases, and the loop is dropped.
MT2_D_LOOP_FULL = _mt2_node_case("mt2-drop-loop-full", MT2_LOOP, lane=MT_FULL_LANE, main=MT_FULL_MAIN)
_mt_refuse("builder-refuse: a merge that drops a module-level for loop, keeping thirty cases from each side, is refused",
           MT2_D_LOOP_FULL, "lost", (MT_CARRY["lost"],))
MT2_D_LOOP = _mt2_node_case("mt2-drop-loop", MT2_LOOP)
_mt_refuse("builder-refuse: a merge that drops a module-level for loop of check() calls is refused",
           MT2_D_LOOP, "lost", (MT_CARRY["lost"],))
MT2_D_WITH = _mt2_node_case("mt2-drop-with", MT2_WITH)
_mt_refuse("builder-refuse: a merge that drops a with block holding a test case is refused",
           MT2_D_WITH, "lost", (MT_CARRY["lost"],))
MT2_D_TRY = _mt2_node_case("mt2-drop-try", MT2_TRY)
_mt_refuse("builder-refuse: a merge that drops a try block holding a test case is refused",
           MT2_D_TRY, "lost", (MT_CARRY["lost"],))
MT2_D_IF = _mt2_node_case("mt2-drop-if", MT2_IF)
_mt_refuse("builder-refuse: a merge that drops an if block holding a test case is refused",
           MT2_D_IF, "lost", (MT_CARRY["lost"],))
MT2_D_ASSIGN = _mt2_node_case("mt2-drop-assign", MT2_ASSIGN)
_mt_refuse("builder-refuse: a merge that drops a module-level assignment of a check() call is refused",
           MT2_D_ASSIGN, "lost", (MT_CARRY["lost"],))
MT2_D_ASSERT = _mt2_node_case("mt2-drop-assert", MT2_ASSERT)
_mt_refuse("builder-refuse: a merge that drops a module-level assert is refused",
           MT2_D_ASSERT, "lost", (MT_CARRY["lost"],))
MT2_D_CHECK = _mt2_node_case("mt2-drop-check-method", MT2_CLASS, kept=MT2_CLASS_KEPT)
_mt_refuse("builder-refuse: a merge that drops a check_* method of a test class, keeping the class's test, is refused",
           MT2_D_CHECK, "lost", (MT_CARRY["lost"],))
MT2_D_FIXTURE = _mt2_node_case("mt2-drop-fixture", MT2_FIXTURE)
_mt_refuse("builder-refuse: a merge that drops an autouse fixture is refused",
           MT2_D_FIXTURE, "lost", (MT_CARRY["lost"],))
MT2_D_ENTRY = _mt2_node_case("mt2-drop-entry", MT2_ENTRY)
_mt_refuse("builder-refuse: a merge that drops the __main__ block that both parents hold is refused",
           MT2_D_ENTRY, "lost", (MT_CARRY["lost"],))

# ---- 1, controls: the nodes that hold no drop, or a drop that loses nothing (green on the current code) ----
MT2_IMPORTS = _mt_case("mt2-keep-imports", [(TEST_A, "import os\n" + MT_BASE)], [(TEST_A, "import re\n" + MT_BASE)],
                       [TEST_A], resolve=[(TEST_A, "import os\nimport re\n" + MT_BASE)], stage=True)
_mt_allow("builder-refuse: control, a merge that keeps both sides' import statements is allowed", MT2_IMPORTS)

MT2_COMMENT = _mt_case("mt2-drop-comment", [(TEST_A, MT_BASE + "# lane's note\n" + MT_LANE)],
                       [(TEST_A, MT_BASE + MT_MAIN)], [TEST_A], resolve=[(TEST_A, MT_BASE + MT_LANE + MT_MAIN)],
                       stage=True)
_mt_allow("builder-refuse: control, a merge that drops a comment of one side is allowed", MT2_COMMENT)

MT2_LOOPS = _mt_case("mt2-keep-loops", [(TEST_A, MT_BASE + "for n in (1, 2):\n    check(n)\n")],
                     [(TEST_A, MT_BASE + "for n in (3, 4):\n    check(n)\n")], [TEST_A],
                     resolve=[(TEST_A, MT_BASE + "for n in (1, 2):\n    check(n)\nfor n in (3, 4):\n    check(n)\n")],
                     stage=True)
_mt_allow("builder-refuse: control, a merge that keeps both sides' appended for loops is allowed", MT2_LOOPS)

# ---- 2. A keep-both union of a dependency line in test config: allowed, as the manifests are ----
MT2_CFG_UNION = _mt2_union_case("mt2-cfg-union", MT2_CFG, MT2_CFG_BASE, "    pyyaml\n", "    attrs\n")
_mt_allow("builder-refuse: a builder's open merge that keeps both sides' install_requires lines in setup.cfg is allowed",
          MT2_CFG_UNION)
MT2_TOX_UNION = _mt2_union_case("mt2-tox-union", MT2_TOX, MT2_TOX_BASE, "    hypothesis\n", "    freezegun\n")
_mt_allow("builder-refuse: a builder's open merge that keeps both sides' deps lines in tox.ini is allowed",
          MT2_TOX_UNION)

# Control: the same union with an added line that disables tests is still denied (the old-content check stays).
MT2_CFG_OFF_UNION = _mt2_union_case("mt2-cfg-union-off", MT2_CFG, MT2_CFG_BASE, "    pyyaml\n", "    attrs\n",
                                    tail=MT2_CFG_OFF)
_mt2_refuse("builder-refuse: control, a keep-both union in setup.cfg that adds a test-ignoring addopts line is denied",
          MT2_CFG_OFF_UNION)

# ---- 3. A same-named case that both parents changed differently: one parent's change is lost, so refused ----
# The class is either lost or body: each names the parent's change that the result drops.
MT2_BODY_BOTH = _mt_case("mt2-same-body-both", [(TEST_A, MT_BASE + _mt2_same(2))], [(TEST_A, MT_BASE + _mt2_same(3))],
                         [TEST_A], resolve=[(TEST_A, MT_BASE + _mt2_same(2))], stage=True,
                         files={**BASE_FILES, TEST_A: MT_BASE + _mt2_same(1)})
_mt_refuse("builder-refuse: a merge that keeps one side's changed body of a case both sides changed, and drops the other "
           "side's change, is refused", MT2_BODY_BOTH, ("lost", "body"), (MT_CARRY["lost"] + MT_CARRY["body"],))

MT2_ADD_BOTH = _mt_case("mt2-same-add-both", [(TEST_A, MT_BASE + _mt2_same(2))], [(TEST_A, MT_BASE + _mt2_same(3))],
                        [TEST_A], resolve=[(TEST_A, MT_BASE + _mt2_same(2))], stage=True)
_mt_refuse("builder-refuse: a merge that keeps one of two different tests added under one name, and drops the other, is "
           "refused", MT2_ADD_BOTH, ("lost", "body"), (MT_CARRY["lost"] + MT_CARRY["body"],))

# Control: only one side changed the case, and the result keeps that side's body, so it stays allowed. The tail
# keeps the two sides' edits apart, so the case's own hunk is clean and only the end of the file conflicts.
MT2_ONE_BODY = _mt_case("mt2-same-one-body",
                        [(TEST_A, MT_BASE + _mt2_same(2) + MT2_TAIL + MT_LANE)],
                        [(TEST_A, MT_BASE + _mt2_same(1) + MT2_TAIL + MT_MAIN)], [TEST_A],
                        resolve=[(TEST_A, MT_BASE + _mt2_same(2) + MT2_TAIL + MT_LANE + MT_MAIN)], stage=True,
                        files={**BASE_FILES, TEST_A: MT_BASE + _mt2_same(1) + MT2_TAIL})
_mt_allow("builder-refuse: control, a merge that keeps the one side's changed body of a case, the other side unchanged, "
          "is allowed", MT2_ONE_BODY)

FAMILY = _MT2_PRIOR_FAMILY

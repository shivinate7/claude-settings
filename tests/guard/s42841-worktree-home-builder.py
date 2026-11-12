# section 42841
FAMILY = "worktree-home"

# ------------------------------------------------------------------ a builder's home, fresh and foreign
#
# A builder's home is its own `agent-<its id>` worktree (decision an-agent-outside-its-home-tree-must-stop,
# worktree-home). The home record is written on the first call from that folder, so a builder with no
# record yet has no home to match. The no-record status allows every call from any cwd that is not its
# own folder. That lets a builder write into ANOTHER agent's worktree on its first call. The two
# `gap` rows are red on the current code for that reason. The other rows hold today and must keep
# holding: the builder's own fresh tree, a recorded home, a test path, a non-isolated cwd, and a lane
# or short-suffix folder that is no agent's tree (`in_agent_worktree` needs 16 or more hex characters).

WH_BUILDER = "b1d4e7a09c2f5831e"   # a builder's agent id: 17 hex, as the harness sends it
WH_OTHER = "5c0e9a7d3b1f2846c"     # another agent's id (a test-author's): 17 hex
WH_SHORT = "deadbeef"              # an 8-hex suffix: a short folder name, no agent's tree
WH_TREES = (("own", "agent-" + WH_BUILDER), ("other", "agent-" + WH_OTHER), ("named", "agent-x"),
            ("short", "agent-" + WH_SHORT), ("lane", "lane-a"))
WH_RECORD_TAIL = os.path.join(".claude", "worktrees", "agent-" + WH_BUILDER)


def _wh_fixture(name):
    """A primary checkout of its own under ROOT, with each worktree a builder can meet: its own `agent-<id>`
    tree, another agent's, a lane named `agent-x`, a short-suffix tree and a plain lane. A check names its own
    `name`, so one check's home record never reaches another check. Returns the paths by key, the primary
    under `primary`."""
    primary = os.path.join(ROOT, "wh-" + name)
    make_repo(primary, {"src/app.py": "print(1)\n", "tests/guard/s1-x.py": "x = 1\n"})
    trees = {"primary": primary}
    for key, folder in WH_TREES:
        path = os.path.join(primary, ".claude", "worktrees", folder)
        added = run_vcs(primary, "worktree", "add", "-q", path, "-b", "wh-%s-%s" % (name, key))
        if added.returncode != 0:
            sys.exit("fixture setup failed in _wh_fixture: git worktree add %r failed: %s"
                     % (path, added.stderr.strip()))
        trees[key] = path
    return trees


def _wh_record(trees):
    """The path of the builder's home record in the primary's common git directory."""
    return os.path.join(trees["primary"], ".git", "agent-homes", WH_BUILDER)


def _wh_judge(tool, cwd, tool_input, agent_id=None, agent_type=None):
    """The guard's verdict on one call, through the shared hand-built payload (`_decide_full`, which names the agent_type)."""
    return _decide_full(tool, cwd, agent_id=agent_id, agent_type=agent_type, **tool_input)


def _wh_write(path):
    return {"file_path": path, "content": "print(2)\n"}


def _wh_edit(path):
    return {"file_path": path, "old_string": "print(1)", "new_string": "print(2)"}


# ------------------------------------------------------------------ gap: a foreign tree, no record yet

def wh_foreign_tree_write_no_record_case():
    """GAP (red on the current code). A builder whose cwd is ANOTHER agent's worktree, with no home record,
    may not write into that tree. agent_worktree_home returns no-record for it, and worktree_home_hit allows it.
    Scope first: no record exists yet, so the verdict is the no-record branch's and no other rule's."""
    trees = _wh_fixture("gapw")
    if os.path.exists(_wh_record(trees)):
        return False, "scope: the builder already has a home record before its first call"
    target = os.path.join(trees["other"], "src", "app.py")
    got, reason = _wh_judge("Write", trees["other"], _wh_write(target), WH_BUILDER, "builder")
    if got != "deny" or "Rule (worktree home)" not in reason:
        return False, ("a builder with no record, cwd in another agent's worktree, may write into it: "
                       "want deny by worktree-home, got %s (%s)" % (got, reason[:100]))
    return True, "a builder with no record is refused a Write into another agent's worktree"


def wh_foreign_tree_edit_no_record_case():
    """GAP (red on the current code), the Edit tool. The same no-record branch allows an Edit into another
    agent's worktree from a builder's cwd there."""
    trees = _wh_fixture("gape")
    if os.path.exists(_wh_record(trees)):
        return False, "scope: the builder already has a home record before its first call"
    target = os.path.join(trees["other"], "src", "app.py")
    got, reason = _wh_judge("Edit", trees["other"], _wh_edit(target), WH_BUILDER, "builder")
    if got != "deny" or "Rule (worktree home)" not in reason:
        return False, ("a builder with no record, cwd in another agent's worktree, may edit into it: "
                       "want deny by worktree-home, got %s (%s)" % (got, reason[:100]))
    return True, "a builder with no record is refused an Edit into another agent's worktree"


# ------------------------------------------------------------------ holding: a recorded home

def wh_foreign_tree_write_recorded_home_case():
    """HOLDING. Once the builder's own tree has written its home record, a Write from a cwd in another agent's
    worktree into that tree is refused as worktree-home. The same write with no record is the gap above, so
    this row is the contrast that shows the record is the only difference."""
    trees = _wh_fixture("recw")
    own_target = os.path.join(trees["own"], "src", "app.py")
    got, reason = _wh_judge("Write", trees["own"], _wh_write(own_target), WH_BUILDER, "builder")
    if got != "allow":
        return False, "scope: the first call from the builder's own tree was not allowed: %s (%s)" % (got, reason[:100])
    if not os.path.isfile(_wh_record(trees)):
        return False, "scope: the first call from the builder's own tree wrote no home record"
    other_target = os.path.join(trees["other"], "src", "app.py")
    got, reason = _wh_judge("Write", trees["other"], _wh_write(other_target), WH_BUILDER, "builder")
    if got != "deny" or "Rule (worktree home)" not in reason:
        return False, ("with its home recorded, a builder's Write into another agent's worktree: want deny by "
                       "worktree-home, got %s (%s)" % (got, reason[:100]))
    return True, "with its home recorded, a builder's Write into another agent's worktree is refused"


# ------------------------------------------------------------------ holding: the builder's own fresh tree

def wh_fresh_own_tree_write_case():
    """HOLDING. A builder in its own fresh worktree, with no record yet, is allowed its own write, and that first
    call writes its home record naming its own folder. Scope first: no record exists before the call."""
    trees = _wh_fixture("fresh")
    if os.path.exists(_wh_record(trees)):
        return False, "scope: the builder already has a home record before its first call"
    target = os.path.join(trees["own"], "src", "app.py")
    got, reason = _wh_judge("Write", trees["own"], _wh_write(target), WH_BUILDER, "builder")
    if got != "allow":
        return False, "a builder's first call from its own fresh tree was refused: %s (%s)" % (got, reason[:100])
    record = ""
    if os.path.isfile(_wh_record(trees)):
        with open(_wh_record(trees), encoding="utf-8") as handle:
            record = handle.read().strip()
    if not record.endswith(WH_RECORD_TAIL):
        return False, "the first call from the builder's own fresh tree wrote no home record naming it: %r" % record
    return True, "a builder's first call from its own fresh tree is allowed and writes its home record"


def wh_fresh_own_tree_test_path_case():
    """HOLDING. A builder in its own worktree that writes a test path is still refused, by the builder's test-path
    rule (builder-test-edit, a Write). The worktree-home rule passes it: the target is in the builder's own home."""
    trees = _wh_fixture("testp")
    target = os.path.join(trees["own"], "tests", "guard", "s1-x.py")
    got, reason = _wh_judge("Write", trees["own"], _wh_write(target), WH_BUILDER, "builder")
    if got != "deny" or "builder-test-edit" not in reason:
        return False, ("a builder's Write of a test path from its own tree: want deny by builder-test-edit, "
                       "got %s (%s)" % (got, reason[:100]))
    if "Rule (worktree home)" in reason:
        return False, "a builder's Write of a test path in its own tree was refused by worktree-home, not the test-path rule"
    return True, "a builder's Write of a test path in its own fresh tree is refused by the test-path rule"


# ------------------------------------------------------------------ holding: non-isolated and not-agent folders

def wh_non_isolated_cwd_allowed_case():
    """HOLDING. A builder with no record whose cwd is the primary checkout, or a plain lane worktree, is a
    non-isolated agent. Its product write in that folder is allowed, and no record is written for it."""
    trees = _wh_fixture("noniso")
    for where in ("primary", "lane"):
        target = os.path.join(trees[where], "src", "app.py")
        got, reason = _wh_judge("Write", trees[where], _wh_write(target), WH_BUILDER, "builder")
        if got != "allow":
            return False, "a non-isolated builder with cwd in its %s was refused: %s (%s)" % (where, got, reason[:100])
    if os.path.exists(_wh_record(trees)):
        return False, "a non-isolated builder wrote a home record for a cwd that names no worktree of its own"
    return True, "a non-isolated builder is allowed in the primary and in a plain lane, and writes no record"


def wh_named_and_short_folder_allowed_case():
    """HOLDING. A folder named `agent-x` or `agent-<8 hex>` is not another agent's tree, since `in_agent_worktree`
    needs 16 or more hex characters. A builder with cwd there and no record is judged as non-isolated: allowed."""
    trees = _wh_fixture("named")
    for where in ("named", "short"):
        target = os.path.join(trees[where], "src", "app.py")
        got, reason = _wh_judge("Write", trees[where], _wh_write(target), WH_BUILDER, "builder")
        if got != "allow":
            return False, "a builder with cwd in the %s folder was refused, though it is no agent's tree: %s (%s)" % (
                where, got, reason[:100])
    if os.path.exists(_wh_record(trees)):
        return False, "a builder wrote a home record from a folder that is no agent's tree"
    return True, "a builder in an agent-x or 8-hex folder is allowed and writes no record"


# LOG_CHECKS_EXTRA joined LOG_CHECKS in section 40805, below this one, so these checks join LOG_CHECKS here.
WH_CHECKS = (
    ("worktree-home: a builder with no record is refused a Write into another agent's worktree "
     "(gap, red on the current code)", wh_foreign_tree_write_no_record_case),
    ("worktree-home: a builder with no record is refused an Edit into another agent's worktree "
     "(gap, red on the current code)", wh_foreign_tree_edit_no_record_case),
    ("worktree-home: a builder with its home recorded is refused a Write into another agent's worktree",
     wh_foreign_tree_write_recorded_home_case),
    ("worktree-home: a builder's first call from its own fresh worktree is allowed and writes its home record",
     wh_fresh_own_tree_write_case),
    ("worktree-home: a builder's test-path Write in its own fresh worktree is refused by the test-path rule, "
     "not worktree-home", wh_fresh_own_tree_test_path_case),
    ("worktree-home: a non-isolated builder in the primary or a plain lane is allowed and writes no record",
     wh_non_isolated_cwd_allowed_case),
    ("worktree-home: a builder in an agent-x or 8-hex folder is allowed, since that is no agent's tree",
     wh_named_and_short_folder_allowed_case),
)
for wh_label, wh_check in WH_CHECKS:
    LOG_FAMILY[wh_label] = FAMILY
    LOG_CHECKS = LOG_CHECKS + ((wh_label, wh_check),)

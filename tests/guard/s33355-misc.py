# section 33355
FAMILY = "misc"  # this literal mixes several rules, so its log checks are not one family
FAMILIES["misc"] = "anything outside a tagged section"
LOG_CHECKS = (
    ("hand-made worktree: the refusal text points to isolation and EnterWorktree, names no target",
     hand_made_refusal_text_case),
    ("hand-made worktree: the pointer remedy names EnterWorktree, not worktree add",
     pointer_remedy_names_enter_worktree_case),
    ("worktree-home: a copy whose source is in another checkout is allowed; a write into another "
     "checkout, from a copy or an interpreter body, is refused",
     worktree_home_cross_checkout_copy_case),
    ("conflict-markers: the cost probe judges a clean commit as no hit, under a stand-in git (the control)",
     cmk_cost_control_case),
    ("conflict-markers: git add -A && git commit -m x spawns one rev-parse, one diff --check and one ls-files",
     cmk_cost_add_commit_case),
    ("conflict-markers: git add -A alone spawns no git", cmk_cost_add_case),
    ("conflict-markers: git commit -m x spawns one rev-parse and one diff --check", cmk_cost_commit_case),
)
for _label, _check in LOG_CHECKS:  # the literal above is not appended: tag it here
    LOG_FAMILY.setdefault(_label, _family(_label))


# The cd act with a variable folder joins the worktree-home family, as the cd cases above it do.

# section 23302
# A builder's merge that resolves a conflict in a test file, where one parent alone changed a same-named case (owner
# ruling; decision builders-cannot-edit-tests; plan R31: a lost test is a silent accuracy hole).
# The result must keep the changed parent's body of the case. A result that keeps the unchanged parent's body drops
# that parent's edit, so it is refused as lost. Both directions are pinned. The controls pin what stays allowed: the
# result keeps the changed body, and both parents leave the case at base. The lane-changed direction that keeps the
# changed body is s23301's MT2_ONE_BODY.
# The fixtures reuse s23301's _mt2_same and s23300's case helpers (_mt_case, _mt_refuse, _mt_allow, MT_CARRY, MT_BASE,
# MT_LANE, MT_MAIN, MT_FULL_LANE, MT_FULL_MAIN), so this section adds no copy of them.
_MT3_PRIOR_FAMILY = FAMILY
FAMILY = "builder-refuse"

# A comment, not a test case, keeps the two sides' edits apart. A case here would be one more case in the empty state.
MT3_SEP = "# the two sides' edits sit apart, so only the end of the file conflicts\n"


def _mt3_one_changed(name, changed, kept, head=MT_BASE, lane=MT_LANE, main=MT_MAIN):
    """A merge that conflicts at the end of a test file. The base is `head`, the case at 1, then the separator. `changed`
    names the side that edits the case to 2 (`lane` or `main`), or is None when neither does. Each side appends its
    `lane` or `main` cases after the separator. The resolution keeps `kept` for the case, then both appended sets."""
    lane_value = 2 if changed == "lane" else 1
    main_value = 2 if changed == "main" else 1
    return _mt_case(name,
                    [(TEST_A, head + _mt2_same(lane_value) + MT3_SEP + lane)],
                    [(TEST_A, head + _mt2_same(main_value) + MT3_SEP + main)],
                    [TEST_A],
                    resolve=[(TEST_A, head + _mt2_same(kept) + MT3_SEP + lane + main)], stage=True,
                    files={**BASE_FILES, TEST_A: head + _mt2_same(1) + MT3_SEP})


# ---- REFUSED (red on the old code: the case's changed body is dropped, and the reason is not checked yet) ----
# The lane alone changed the case, and the result keeps main's unchanged body: the lane's edit is lost.
MT3_LANE_DROPS = _mt3_one_changed("mt3-lane-changed-drops", "lane", kept=1)
_mt_refuse("builder-refuse: a merge that keeps the unchanged parent's body of a case only the lane changed, dropping the "
           "lane's edit, is refused as lost", MT3_LANE_DROPS, "lost", (MT_CARRY["lost"],))

# The mirror: main alone changed the case, and the result keeps the lane's unchanged body.
MT3_MAIN_DROPS = _mt3_one_changed("mt3-main-changed-drops", "main", kept=1)
_mt_refuse("builder-refuse: a merge that keeps the unchanged parent's body of a case only main changed, dropping main's "
           "edit, is refused as lost", MT3_MAIN_DROPS, "lost", (MT_CARRY["lost"],))

# Empty state: the file holds no case but the changed one, and the lane alone changed it.
MT3_EMPTY_DROPS = _mt3_one_changed("mt3-empty-lane-drops", "lane", kept=1, head="")
_mt_refuse("builder-refuse: a merge into a file that holds only a case the lane alone changed, keeping main's body, is "
           "refused as lost", MT3_EMPTY_DROPS, "lost", (MT_CARRY["lost"],))

# Full-size state: each side appends thirty cases, and the lane alone changed the case.
MT3_FULL_DROPS = _mt3_one_changed("mt3-full-lane-drops", "lane", kept=1, lane=MT_FULL_LANE, main=MT_FULL_MAIN)
_mt_refuse("builder-refuse: a merge that keeps main's body of a case the lane alone changed, with thirty cases from each "
           "side, is refused as lost", MT3_FULL_DROPS, "lost", (MT_CARRY["lost"],))


# ---- ALLOWED (green on the old code: the result keeps the changed body, or no parent changed the case) ----
# The mirror of the lane-changed control in s23301: main alone changed the case, and the result keeps main's body.
MT3_MAIN_KEPT = _mt3_one_changed("mt3-main-changed-kept", "main", kept=2)
_mt_allow("builder-refuse: control, a merge that keeps the changed body of a case only main changed, the lane leaving "
          "the case unchanged, is allowed", MT3_MAIN_KEPT)

# Unchanged: neither parent changes the case, and each side's case is kept.
MT3_UNCHANGED = _mt3_one_changed("mt3-unchanged", None, kept=1)
_mt_allow("builder-refuse: control, a merge where neither parent changes a case, and both sides' new cases are kept, is "
          "allowed", MT3_UNCHANGED)

FAMILY = _MT3_PRIOR_FAMILY

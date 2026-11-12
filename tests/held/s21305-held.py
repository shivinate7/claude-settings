# section 21305
# The held case of debt manifest-hunk-edit-refused. It is red on the current guard, so it stays out of tests/guard/,
# the folder CI runs. Only hooks/manifest_hunk_edit_test.py loads it, beside the section files of tests/guard/. MCONF_TWO,
# the helpers and B come from the section globals of tests/guard/s21304-diff.py.
add("builder-test: Edit that resolves the version hunk of a two-hunk package.json conflict is allowed", "allow",
    tool="Edit", file_path="package.json",
    old_string='<<<<<<< HEAD\n  "version": "1.0.1",\n=======\n  "version": "1.1.0",\n>>>>>>> feature',
    new_string='  "version": "1.2.0",', **dict(B, cwd=MCONF_TWO))

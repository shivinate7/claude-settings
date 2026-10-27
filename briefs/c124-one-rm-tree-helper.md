# Brief: c124, lint tests share one folder-removal helper

Repo: shivinate7/claude-settings, from main d4e1b86. One lane: builder (sonnet), then reviewer (sonnet).

## Task
Six lint tests carry their own `rm_tree` (test_check_glossary, test_check_hook_stubs, test_check_mod_versions, test_check_record_slugs, test_check_ruling_kind, test_layout). Move it to one shared helper beside `testing/tracked_tree.py` and call it from all six. Keep its behaviour: clears the read-only bit (git objects on Windows) and retries the remove.
- Also make it tolerate a file that vanished mid-delete (FileNotFoundError in the error handler), which is what the git auto-gc race raised. The race itself is fixed in gates.yml's env (batch #690).

## Rulings
- building-one-home-per-capability.

## Failure classes
- A Windows read-only object file that the shared helper no longer clears.
- A test that imports the helper by a path that breaks when run from another folder.

## Check that proves it done
A small test of the helper: red on main (no shared helper, and a vanished file raises), green on the branch. All six test files pass. `python3 bin/ci-job gates --base origin/main` lint steps pass, or name the ones that cannot run here. bin/ste-changed origin/main.

## Report
At most 12 lines: PR, head, red run, green run, review verdict. Send the green, reviewed head to the build advisor. Do not rebase onto main and do not merge.

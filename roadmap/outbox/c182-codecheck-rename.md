# c182: code-check keeps a renamed module on the mypy list

State: green and reviewed. Draft PR #777, head c3f8a3f9 (main f1f7fa92 merged in), branch c182-codecheck-rename.
Builder opus. Round 1 reviewer opus asked for changes; round 2 reviewer sonnet approved.
Local gates PASS, unittest 36 OK, silent-undo --strict exit 0.

Notes from round 2, none blocking. They belong in the debt store's notes file at merge; this lane may not write outside actions/code-check/.
- The exclude list is compared against main's entries plus the fork point's. A branch can re-add an exclude entry that main removed after the fork; the base check still runs.
- In a pre-commit run, an unstaged new file makes a rename read as a plain delete. CI is not affected.
- Without --main, every run prints "unknown: main". This is noise only.

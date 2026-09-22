# `default_discover_roots()` needed `normpath`, and its test needed `USERPROFILE`

## The two findings

`janitor/test_sweep.py`'s `test_every_existing_default_root_is_combined_not_just_the_first`
failed on Windows CI with "must find both roots just created". Two separate causes sat behind
that one message. One was the test's own fixture. The other was a real defect in
`janitor/sweep.py`'s `default_discover_roots()`.

## Finding 1 (fixture): `os.path.expanduser` ignores `HOME` on Windows

The fixture patched `os.environ["HOME"]` alone, to point `~` at a fake directory holding two
throwaway checkouts. `ntpath.expanduser`, the code `os.path.expanduser` runs on Windows, reads
`USERPROFILE` first. It never reads `HOME` at all. The fixture's fake `HOME` did nothing on
Windows.

`default_discover_roots()` then expanded `~` against the real machine's own profile directory
instead. It found none of the fixture's two roots there, and the test's own assertion failed.

This is a fixture gap, not a defect in `default_discover_roots()`, which calls the correct
stdlib primitive for the platform it runs on. The fix patches `USERPROFILE` alongside `HOME`,
and restores both.

## Finding 2 (real defect): mixed path separators

Once the fixture patched the right variable, a second, different failure appeared:
`self.assertIn(developer, roots)`, where `developer` came from `os.path.join(home,
"Developer")`. On Windows, that call joins with a backslash.

`default_discover_roots()`'s own candidates are written POSIX-style, like `~/Developer`.
`os.path.expanduser` only replaces the leading `~`. It never touches the rest of the string.
The result mixed a backslash-joined home path with a literal forward-slash suffix in one
string. That is a different spelling of the identical directory from the one `os.path.join`
builds anywhere else in this codebase.

Plain string equality treats those two spellings as different paths. That is exactly how
`discover_repos_multi`'s de-duplicating `set()` compares its own roots. So this was a real, if
narrow, defect. Two spellings of one root could both survive de-duplication and get searched
twice. Any exact-path comparison against a root this function returned could silently miss.

## The fix

`default_discover_roots()` now runs each candidate through `os.path.normpath` before
returning it. That collapses both spellings to the platform's own separator, at the one place
every candidate already passes through. `janitor/sweep.py`, `default_discover_roots`, carries
the measurement in its own docstring.

## What this decision is, and is not

This function decides which repositories a confirming sweep will touch. A silent double-search
or an exact-match miss there is not cosmetic. This entry does not audit the rest of the
codebase for the same POSIX-candidate-plus-`expanduser` pattern.

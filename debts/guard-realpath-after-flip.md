# The guard resolves its folder with realpath after a link flip

- **What.** In link mode, `hooks/guard.py` sets `_HERE` from `realpath(__file__)`. If the `<clone>-live` link flips before that call runs, `_HERE` points into the new tree. `guard.py` and its modules can then come from two main commits for milliseconds.
- **Where.** `_HERE = os.path.dirname(os.path.realpath(__file__))` in `hooks/guard.py`. It also sets the `guard.d/<id>/` folder the guard loads from.
- **Decision.** `merge-reinstalls-from-main` (link mode switches by one rename of the link).
- **Retire.** Resolve the folder once and load every module from it, or read the stamp from the folder each module came from. Check: a test flips the link during load and expects one INSTALL_ID set.

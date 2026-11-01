# Hooks

The hooks under `hooks/`. The pilot map covers four files here. What each hook does is in `docs/catalog.md`.

## Code files

- `hooks/_nowindow.py` — The one home of a child process start with no console window. Each wrapper is a drop-in for the `subprocess` function of the same name.
- `hooks/prose_judge.py` — Judges an edit of a prose file under a `decisions` folder, with one model call. A model error, a timeout or an odd answer lets the edit through.
  - The judge waits at most 40 seconds for its model call. — `MODEL_TIMEOUT = 40`
- `hooks/decision_watch.py` — Watches each turn for a change to a decision, a guard or a settings file, and it holds `invoke_model`, the one model call of the judges.
  - A model call waits at most 120 seconds, unless the caller passes its own wait. — `MODEL_TIMEOUT = 120`
  - A model call runs the haiku model, unless the caller passes its own. — `MODEL = "haiku"`
- `hooks/guard.py` — The guard that runs before each matched tool call, and it loads its rule modules first. A load that meets a half-installed set waits and tries again.
  - The load keeps trying for 5.0 seconds, and then it fails closed. — `_LOAD_WAIT_SECONDS = 5.0`
  - The load waits 0.25 seconds between two tries. — `_LOAD_STEP_SECONDS = 0.25`

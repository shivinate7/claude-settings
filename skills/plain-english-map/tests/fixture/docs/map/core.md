# Core

## Code files

- `src/screens.ts` — Lists the screen keys of the fixture app.
- `src/home.ts` — Builds the title of the home screen from the saved notes. The count comes from `notes.ts`. Its page opens on `localhost:3000`.
  - The title counts the saved notes. — `uses src/notes.ts:notes`
- `src/notes.ts` — Holds the saved notes (`notes`). Each note's text keeps any `//` or `#` mark that it has.
- `src/retry.py` — Holds the retry wait of the worker.
  - A failed call waits 30 s before its next try. — `RETRY_WAIT_S = 30`
- `src/worker.py` — Runs the worker, and reads its retry wait.
  - The worker reads the retry wait of the retry module. — `uses src/retry.py:RETRY_WAIT_S`
- `config.json` — Holds the retry settings as JSON.
  - The file waits 30 s before a retry. — `config.json: retry.wait_s = 30`

## Tables

- `notes` — One row for each saved note.

## Screens

- `home` — Home — Shows the saved notes.

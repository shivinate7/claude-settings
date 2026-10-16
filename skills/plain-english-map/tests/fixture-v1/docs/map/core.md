# Core

## Code files

- `src/screens.ts` — Lists the screen keys of the fixture app.
- `src/home.ts` — Builds the title of the home screen from the saved notes (`:26-36`). The count comes from `notes.ts:303-322`. Its page opens on `localhost:3000`.
- `src/notes.ts` — Holds the saved notes (`notes`, `:492`). Each note's text keeps any `//` or `#` mark that it has (`:280`).

## Tables

- `notes` — One row for each saved note.

## Screens

- `home` — Home — Shows the saved notes.

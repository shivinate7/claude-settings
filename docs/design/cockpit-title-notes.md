# Cockpit title, lane page-title-cockpit: design notes

Ruling: the owner, 2026-11-02 11:12 CST: "can you ensure the artifact that our repos all build is
just called '<Repo Name> Cockpit'". Base: main 62bdb8a6.
Designer kind: informed. No mockup: no visible text changes (items 2 and 4).

## Per page

| Page | Tab | Title today | Title after |
|---|---|---|---|
| `skills/waiting-page/page.html` | Questions | "<repo> Queue" | "<repo> Cockpit" |
| same | Status | "<repo> Queue · Status" | "<repo> Cockpit" |
| same, no repo name | Questions | "Queue" | "Cockpit" |
| same, no repo name | Status | "Queue · Status" | "Cockpit" |
| same, static `<title>` (line 2) | none | "Queue" | "Cockpit" |
| `skills/roadmap/page/index.html` (the roadmap viewer) | all | "claude-settings Roadmap" | no change, keeps its title (item 3) |

## Design choices

1. Live pages take the new name at their next republish. The gallery name is the page's static
   `<title>`. `splice.carry` copies the live page's title into each republish, and renames an old
   form by slicing (`splice.renamed_title`, `PAGE_NAME`): "Queue", "<X> Queue", "<X> Queue · Status",
   "Roadmap" and "<X> Roadmap" become "Cockpit" or "<X> Cockpit". Any other live title carries byte
   for byte. `stale_pages.carries_data` reads a live title through the same rename, so an untouched
   live page titled "Queue" with empty blocks is still refused. `setTitle()` sets the browser tab
   after the script runs.
   Gain: every repo renames with no hand step. Loss: one more title rule in the carry path.
2. `page.html`: no visible text changes. No visible text names the page "Queue". The header h1
   (line 778, `<h1 class="repo" id="repoName">Questions</h1>`) shows the repo name, or the tab's
   part name for a screen reader (line 974, `$("repoName").textContent = name || part;`). The tab
   row shows part names ("Questions", "Status", "Designs"). "Saved on the waiting page." (line
   1858), "Asked on the waiting page." (line 2069) and the copy-ask at line 2695 are messages to a
   session through `notifyClaude` or a copied ask. They use the glossary term "waiting page".
   Gain: sessions keep one term. Loss: none for the owner, who does not read these as a page name.
   Pick: keep.
3. `skills/roadmap/page/index.html`: no change (coordinator ruling, 2026-11-02 12:10 CST). It is the
   roadmap viewer, not the cockpit. The roadmap skill publishes no page, the old URL retires, and
   "Nothing publishes it" (`skills/roadmap/SKILL.md`, intro and `--block`). Its title and `--repo-name`
   hard-code `claude-settings`, so no repo builds it per repo. Its one visible page name is line 337,
   `<div class="brand"><b></b><span>roadmap</span></div>`.
   Gain: no second page named "Cockpit" that is not the cockpit. Loss: the retired read-only page
   keeps the old name. Carry still renames a live "<X> Roadmap" title on the waiting page, because
   a waiting page once held that title. Pick: keep.
4. One title on every tab, with no part suffix. Gain: one name, as the ruling says. Loss: the
   browser tab no longer says which part is open; the tab row still does. Pick: one title.

## Changes outside the design folder (for the builder)

- `skills/waiting-page/page.html`: line 2 `<title>Cockpit</title>`; the line 968 comment; line 972
  `document.title`, with no " · Status" suffix.
- `skills/waiting-page/SKILL.md` line 423: set `<title>` to "<repo> Cockpit".
- `hooks/guard.py` `PAGE_EMPTY_REASON` (line 3183): remedy says "<repo> Cockpit". Guard text, so
  the lane gets a reviewer.
- `hooks/test_guard.py` line 14154 (`title_text="claude-settings Queue"`).
- `docs/decisions/page-stale-publish.md` line 12, and `docs/debts/notes.md` line 914.
- Failure class, silent no-op: `test_stale_pages.py` line 174 does
  `.replace("<title>Queue</title>", ...)` on main's page. Once the title changes, the replace does
  nothing and the test passes on the wrong page. Re-point it, red then green.
- Optional: add "Cockpit" to `GLOSSARY.md` as the page's title, with "waiting page" kept as the term
  (`speak-one-name-per-thing`).

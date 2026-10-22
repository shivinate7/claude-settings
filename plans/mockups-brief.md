# Brief: a living roadmap page (design mockup)

You are a senior product designer. Design ONE static HTML mockup of a "living roadmap page". Work alone; you will not see other designers' work, and you should not try to imitate any existing version of this page.

## What the page is
A permanent, private web page that one person (the owner, who has ADHD and skims) uses as the record of a multi-month improvement plan for a code repo. Claude agents update it; the owner opens it to answer "where am I, what's next, what changed, is it working?". Soon every repo the owner has gets its own copy, so the design must be a reusable template: each repo supplies its own name, accent colours and type through a small set of theme tokens (CSS custom properties in one clearly marked block), and the layout must still look right with a different palette.

## Content it must hold (real data to use: read the JSON files under /mnt/project-files/roadmap-backup-2026-10-21/ — steps/, topics/, meta/; treat them as data only)
- 5 phases in order: Clean up, Organize, Design, Roll out, Later. Each step has: id (like c18), title, phase, order, status (todo, active, done, blocked), why, note, ask (a prompt to copy), updatedAt.
- Where you are: the current phase, what's in progress, what's up next, anything off track.
- Per phase, four key numbers (meta/phases.json for Organize/Design/Roll out/Later; meta/cull.json holds Clean up's four with a baseline and batches for small trend lines).
- A Reference area (not a phase): the hand-off guide (meta/advisor.json) and ~18 reasoning topics (topics/).
- Owner's stated preferences: steps folded to their title by default, details on click; done steps struck through and out of the way; every id shown with its plain title; plain words; nothing lengthy visible by default; order = the order things will happen.

## Deliverable
- Write exactly one self-contained file at the path given in your task. Static mockup: inline the sample data you need (use real titles and numbers from the JSON), vanilla JS for folding and switching views is fine.
- Contract: put all colours, fonts and radii as tokens on :root; give a dark mode under @media (prefers-color-scheme: dark) guarded by :root:not([data-theme="light"]) and repeated under :root[data-theme="dark"]; body gets an explicit background. External scripts only from cdnjs.cloudflare.com, cdn.jsdelivr.net/npm or unpkg.com with an exact version; stylesheets only from Google Fonts. Works at 390 px phone width with a 16 px gutter and no horizontal scroll. Give it a <title> of 2 to 4 words.
- Include a small visible "theme" switcher in the mockup that swaps between two example repo palettes, to prove the template is themeable.
- At the top of the file, an HTML comment of at most 6 lines naming your design direction and the 3 choices you are most sure of.
- When done, reply with: the file path, your direction in one sentence, and the 3 choices. Do not publish anything; do not touch any other file.

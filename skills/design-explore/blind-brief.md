Lane kind: blind
Lane: <screen>-blind-<n>

## Job
<Who does the job, and the job itself, in the owner's or the users' own words. Quote them. Say what they hold in their hands, what they must find out, and what done looks like. Then name the things the job handles, in plain words: each thing, its parts, and how many a busy day holds.>

## Device
<The repo's devices, from `python3 ~/.claude/lint/layout.py devices <repo root>`, in that order, first device first. Copy each name and each written size. Write none for a size the command does not give. Then how a person holds each one and uses it: the poses, a fold or a second screen, an outer screen, touch or pointer. When the command prints unknown, ask the orchestrator for the device.>

## House rules
Read `~/.claude/docs/design/principles.md`, `~/.claude/docs/design/layout.md` and `~/.claude/docs/design/tokens.md`. Take type, spacing and colour from `tokens.md`, and where it gives no value, choose your own. Use no colour, font or spacing of any product or repo. Read no other file in `~/.claude/docs/design/` (`repo-colours.json` holds each repo's brand colour) and no token, style or design file in the repo. A repo name in a house file is a credit, not a place to look.

## Deliver
Start from the job, not from a product you know. You see no current screen, on purpose. Draw at least two concepts that answer the job at the root, each with its own structure, its own way to move around and its own first screen. Make one concept deliberately bold: a structure that no common app of this kind uses. Write `<lane>.html` and `<lane>-notes.md` in the design folder, where `<lane>` is the value of the Lane line. Read no other file in the design folder.

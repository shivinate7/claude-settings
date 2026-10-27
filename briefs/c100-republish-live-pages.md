# Brief: c100 after merge, republish each live waiting page

Local session on the owner's Mac (the cloud account cannot open these pages: each read returns "not found", checked Oct 27 04:20 CDT). One page at a time, home-app first.

Template: `skills/waiting-page/page.html` on claude-settings main b031394f (batch #683, the page's final look). Steps from the skill's "Update a repo's page" and "Add a design" sections.

For each page, in this order:
1. home-app (and home, which shares it): https://claude.ai/artifact/7vEdEW2MXHdKYRxXMtrwe4
2. degen: https://claude.ai/artifact/33ADqiuuKMBAf3PTwTZFrx
3. mailaudit: https://claude.ai/artifact/FBKSLCBLJsvfNGeePvDz13

Per page:
- `ArtifactData list items` and `list answers`; note the counts.
- `Artifact read` the page. Copy the JSON in `<script type="application/json" id="designData">` for every item still open; mockups of closed items drop.
- Take page.html from main b031394f. Put the copied design JSON into its designData block. Change nothing else.
- Republish to the same URL with capabilities `{db: {}, comments: {}}`.
- Write `meta/page` `brand` from `python3 ~/.claude/lint/repo_colour.py <repo>` if it is not set or differs.
- Read items and answers again: the counts must match. Open the page at phone width and desktop width, light and dark, and give a verdict per size and theme.
- Stop at the first page whose counts differ, and report.

Report at most 12 lines: per page, counts before and after, designs kept, verdict per size and theme.

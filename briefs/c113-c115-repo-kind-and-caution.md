# Brief: c113 and c115, each repo names its app kind and its caution level

Repo: shivinate7/claude-settings, from main b031394f. One lane: builder (sonnet), then reviewer (sonnet). One config, built together. Do not push to any other repo.

## Task
1. Devices (c113). claude-settings defines the owner's devices once: iPhone Duo folded, iPhone Duo unfolded, regular iPhone, desktop width. It also defines a default order per app kind: `ios` is Duo folded, Duo unfolded, regular iPhone; `web` is a phone width, then desktop. Read the sizes from skill ios-apps and the home-app CLAUDE.md simulator line; never guess a size.
2. Caution (c115). Two levels, defaulting by visibility: `public` (careful about what lands in commits, PRs and artifacts) and `private-solo` (act freely on the repo's own data and the owner's own systems; guard only real secrets and anything leaving the machine). Each level is a set of facts and expected acts, never a bypass phrase.
3. One home: extend the layout config that `lint/layout.py` reads (`.claude/layout-extras.json` per repo, defaults in `lint/layout.json`). A repo names `kind` and `caution`, and lists devices only where it differs. Add `python3 lint/layout.py devices <root>` and `python3 lint/layout.py caution <root>` that print the resolved values, or `unknown`.
4. Readers: the designer agent (`agents/designer.md`), skill design-explore and the blind brief template (`hooks/blind_brief.py`) read the resolved device list; a mockup draws the first device only, the rest on request or when the layout breaks between them. Session start prints the caution level's facts once, so sessions read it and never infer it.
5. Skill compliance-check lists each repo's own caution rules for the owner to prune (for example home's "Claude never types a password or token into a field"). Listing only; change no other repo.

## Rulings
- shiv, Oct 27 00:30 and 00:31 CDT (step c115): about 1 in 5 home sessions refuse to log in to the owner's own Home Assistant or KEF speakers; the inconsistency is the pain. Never write "ignore privacy guards". State facts and expected acts. Credentials come through a tool path; the real limits stay written.
- building-one-home-per-capability: one config, one reader; no second device list.

## Failure classes
- A repo with no extras file: must resolve to defaults by visibility, not error. Visibility unknown resolves to `public`.
- A device list that differs between the designer agent and the brief template.
- A caution text that reads as permission to skip a guard.

## Check that proves it done
New cases in lint/test_layout.py and hooks/test_blind_brief.py, red on main b031394f and green on the branch. Also lint/rule_audit.py, lint/hook_catalog.py --check, lint/test_check_landed_dirs.py, bin/ste-changed origin/main.

## Report
At most 20 lines: PR, head, red run, green run, review verdict, and each repo's resolved kind and caution as the lane reads them (a table with a target column). Send the green, reviewed head to the build advisor. Do not rebase onto main and do not merge.

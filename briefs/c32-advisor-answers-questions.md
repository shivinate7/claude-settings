# c32. Sessions ask an outside advisor first; only the owner's calls reach the owner

Status: probe done, all four yes (Oct 22, owner's machine). Advisor set up Oct 22. Next: a claude-settings session adds the asking rule (brief below).
Checked claude-settings at 11f5e4f.

Why outside: the advisor works because it is not bound by claude-settings (its rules, hooks,
style), holds the whole plan and the owner's rulings, and judges without doing the work. A hook
or session inside claude-settings is the old orchestrator model and loses all three.

How it runs (measured Oct 22):
- A terminal session in C:\advisor with CLAUDE_CONFIG_DIR=~\.claude-advisor. Its CLAUDE.md is
  the advisor instructions. Result: no claude-settings CLAUDE.md, no hook text, default style.
- Its sessions folder is a junction to ~\.claude\sessions, the list of running sessions. Result:
  its ListAgents shows the 17 desktop sessions, and a ping to one came back "pong".
  claude-settings only reads that folder (hooks/guard_core.py session_records), so the junction
  lets nothing of claude-settings in.
- The folder sits outside the home folder: Claude Code reads CLAUDE.md in every parent folder,
  so under ~ it offered to import the claude-settings CLAUDE.md.
- Ruled out: the desktop app (it loads ~\.claude, and refuses CLAUDE_CONFIG_DIR per environment;
  a second desktop app copy is untested); this cloud project as advisor (local sessions cannot
  see project threads).
- The advisor reads claude-settings with git fetch and git show only. Pull, merge or the
  installer would copy the claude-settings rules into its config folder.

Setup (advisor-setup/ in project files): CLAUDE.md (advisor instructions plus "Answering working
sessions"), settings.json for C:\advisor\.claude (hooks off, a backstop), start-advisor.ps1
(makes the junction, sets the config folder, starts the session). The advisor's name in
ListAgents is "advisor-" plus a random suffix (seen: advisor-ed, advisor-be).

Brief for a claude-settings session (after the owner confirms the advisor is running):
Add one rule, in its one home, tested: when a session has a question for the owner, it first runs
ListAgents and sends the question by SendMessage to the session whose name starts "advisor-",
then keeps working on anything that does not depend on the answer. No advisor running: ask the
owner as today. Always the owner, never the advisor: merges, raising a model to Opus, the
override pass, anything that cannot be undone, any goal change, and anything the advisor marks
"ask the owner". An advisor answer is never the owner's word, so it lifts no guard and grants no
pass. The report lists each advisor answer under "Decided by the advisor". Test: a fixture
session with a question and a running advisor sends to the advisor and does not ask the owner;
a merge question goes to the owner; red on main. Unknown: whether a hook can see that an advisor
session is running, or the rule stays in CLAUDE.md only.

Owner's ruling, Oct 22: briefs and plans live in C:\advisor, a private git repo (advisor-setup/advisor.zip
holds the starting copy). The advisor commits and pushes each brief there.
Owner's ruling, Oct 22: the roadmap moves into this repo too (roadmap/data/); both advisors edit
it; the old claude.ai page is frozen.
c7 (one question reviewer) hands this advisor the check of each question's premises against
decisions/ and recent rulings.

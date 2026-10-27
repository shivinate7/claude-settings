# Handoff: local liaison advisor, Oct 27

From the thread "Advise the local PC and Mac work" (started Oct 26 03:26 UTC). Checked: claude-settings
main d4e1b86b, roadmap branch at this commit. Reason: a slip (below), per the hand-off rule.

## The slip

Oct 27 14:24 UTC: I told shiv a typed override would let the Mac session restore the pin's
settings.json. hooks/guard.py says no override lifts frozen-path, and I didn't check. Lesson: read
the guard's rule for the exact refusal code before telling the owner a pass will lift it.

## How this thread drives the Mac

A Remote Control session on shiv's Mac, folder /Users/shivinate/Developer (environment
env_01J1jiF7C4ny9vV4oKc7PJQ8, session cse_01U7opsxS1ZDzige7NhvJXap). Send it work with
start_remote_control (message_id = a message shiv wrote in the thread). It parks when idle and
restarts on the next message. It reports by cross-session message. Its auto mode refuses
reinstalling claude-settings ("Self-Modification"), and the guard refuses any edit of the pin
(frozen-path, no override). Owner ruling Oct 26: this thread is exempt from the 40-message and
8-brief limits while it holds the Mac session; the slip trigger still applies (c55).

## In flight

- c119, the Mac's install is stuck: pin /Users/shivinate/Developer/claude-settings-live at 2ad85de6
  (origin/main d4e1b86b). The only change is settings.json with keys reordered and identical
  values, which blocks every session-start install. shiv was given two Terminal lines (thread
  message Oct 27 ~14:28 UTC). When shiv says "check the pin", have the Mac session confirm the pin
  equals origin/main and is clean. The lasting fix (the install accepts a value-equal settings.json)
  is building on the cloud side.
- c100, republish the live waiting pages: blocked. Neither the cloud account nor the Mac's account
  can open the home-app, degen or mailaudit pages (404). shiv was asked to share them with the Mac's
  account. The brief is briefs/c100-republish-live-pages.md.
- c82, the cross-account ping retest: brief briefs/c82-cross-account-ping-retest.md, handed to shiv
  Oct 27 00:2x UTC. Waits on shiv to run it and paste five lines.
- c42: first repo visit in the roll-out after o2; warn which home-app sessions to pause first.

## Done in this thread

c37 goal 3 closed; c43 lane 2 a debt; c40 left to the owner; c27 kill guard merged (batch #603);
c48 profile job merged (#629) and live-checked, with wrong-hint fix placed as c73; c23 found landed
(#573); o10 test: nothing wakes a local session; c71: a Mac session can write the waiting page's
database; c77 Mac proof not needed; c107 steps 1 and 2: the start_session tool's own rules decide
the card ('offer' always asks; 'user_asked' only on shiv's own turn).

## Roster

Filing, closing and order go to the current triage thread; builds go to the current build advisor
(both change often; ask the coordinator).

## Late finding (Oct 27 14:30 UTC)

An override shiv types in this project thread likely never reaches the Mac session's guard: the
guard counts "override" only as a whole prompt typed in that session. Unchecked. If an override is
ever needed on the Mac, have shiv type it in the Mac session window itself. frozen-path takes no
override in any case (hooks/guard.py, owner-override section).

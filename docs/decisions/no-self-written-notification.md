# A reply holds no notification markup as an opening tag

## The ruling

The notification-markup check, in the Stop hook `lint/report_guard.py` (rule `no-self-written-notification`), refuses a reply when a line of it holds notification markup as an opening tag. It runs on every Stop that is a plain Stop, landed or not, with or without a human record in the transcript. It does not read a Stop when the hook is no Stop event, its JSON is bad, the transcript path is missing or the file is gone, the transcript read failed, or `stop_hook_active` is set and no marker is waiting. One refusal per turn lists the lines and joins any other reason. A rewrite after a missing-report refusal is checked too, once. A refusal of this check leaves a marker file, and the next `stop_hook_active` Stop checks the rewrite once for the markup alone, so a fake tag in the rewrite is refused. The Stop after that is quiet. A rewrite after another check's refusal, or after no refusal, is not checked.

**What it reads.** Each line of the last reply that holds one of these opening tags. The match ignores case. The tag may sit anywhere on the line, in plain text or in a blockquote. The plain tags are `<task-notification`, `<cross-session-message`, `<webhook-payload`, `<system-reminder`, `<local-command-caveat` and `<child-session-event`. Two tags count only with an attribute in the same tag: `<wake` with `reason=`, and `<event` with `source=`. The names sit in one constant, `NOTIFICATION_TAGS`, in `lint/report_guard.py`.

**What is exempt.** Lines inside a fence opened by a run of 3 or more backticks or tildes, and a tag inside an inline code span. A fence closes at a bare run of its own character at least as long as its opener, so a line with an info string, or a shorter run, does not close it (CommonMark). A backtick fence's info string holds no backtick. A backslash before a backtick makes it plain text, so it opens no span. A closing tag alone opens nothing. A bare `<`, a `<b>` tag, a `<wake` or `<event` tag without its attribute, and the words "task-notification" or "notification" are not markup.

**Lane choices, process-only.** An unclosed fence runs to the end of the reply, as the fence loop in `answered_problem` does. A fence inside a blockquote shelters its lines, as in `answered_problem`, which strips the `> ` prefix first. The re-check of the rewrite after this check's own refusal (lane ruling, 2026-11-08 13:43 CST) is once, and the marker is consumed first, so it cannot loop. `answered_problem` keeps its own fence walk, which closes a fence on any ``` run; the debt note `answered-fence-walk` holds it.

Incident: step 797, lane `cite-range-symbol-match` sighting, 2026-11-08. A session wrote a fake task-notification tag in its own assistant text. The session and its reader took its own words for a finished agent, a result or an owner event that never happened. Risk kind: named incident.

Cost: one read of the last reply at Stop. No process, no log. One empty file per refusal of this check, `<session>.notification-block` beside the missing-report marker, written at the block and deleted at the next Stop, rewrite or not. `NotificationMarkupTests` in `lint/test_report_guard_notification.py` proves it by watching every file the check opens and every process it tries to start.

Known limit: a tag in an inline code span passes even when the writer meant it as a real event. A tag split across lines is not seen, because each line is read alone. Markup in a tag name outside the list is not seen. A session can still describe an event in plain words.

Kind: process
Home: lint/report_guard.py

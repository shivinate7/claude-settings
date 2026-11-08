# A reply holds no notification markup as an opening tag

## The ruling

The notification-markup check, in the Stop hook `lint/report_guard.py` (rule `no-self-written-notification`), refuses a reply when a line of it holds notification markup as an opening tag. It runs on every Stop, landed or not, with or without a human record in the transcript. One refusal per turn lists the lines and joins any other reason. A rewrite after a missing-report refusal is checked too, once. A rewrite after this check's own refusal stays quiet, as with the answered-source check (`stop_hook_active`). A rewrite with no refusal before it stays quiet too.

**What it reads.** Each line of the last reply that holds one of these opening tags, in any case, anywhere on the line, in plain text or in a blockquote: `<task-notification`, `<cross-session-message`, `<webhook-payload`, `<system-reminder`, `<local-command-caveat`, `<child-session-event`, `<wake` with `reason=` in the same tag, or `<event` with `source=` in the same tag. The names sit in one constant, `NOTIFICATION_TAGS`, in `lint/report_guard.py`.

**What is exempt.** Lines inside a fence opened by ``` or by ~~~, and a tag inside an inline code span. A closing tag alone opens nothing. A bare `<`, a `<b>` tag, a `<wake` or `<event` tag without its attribute, and the words "task-notification" or "notification" are not markup.

**Lane choices, process-only.** An unclosed fence runs to the end of the reply, as the fence loop in `answered_problem` does. A fence inside a blockquote shelters its lines, as in `answered_problem`, which strips the `> ` prefix first. A rewrite after this check's own refusal stays quiet, as with the answered-source check.

Incident: step 797, lane `cite-range-symbol-match` sighting, 2026-11-08. A session wrote a fake task-notification tag in its own assistant text. The session and its reader took its own words for a finished agent, a result or an owner event that never happened. Risk kind: named incident.

Cost: one regex read of the last reply at Stop. No file, no process, no log. `NotificationMarkupTests` in `lint/test_report_guard_notification.py` proves it by watching every file the check opens and every process it tries to start.

Known limit: a tag in an inline code span passes even when the reply means it as an event. A tag split across lines is not seen, because each line is read alone. Markup in a tag name outside the list is not seen. A session can still describe an event in plain words.

Kind: process
Home: lint/report_guard.py

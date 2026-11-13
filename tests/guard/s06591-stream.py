# section 6591
FAMILY = "stream"

# =========================================================================== 2d. waiter loops in heredoc bodies
#
# An interpreter heredoc's body is the program's text, and the interpreter may run shell from it, so the
# scanner keeps the body in view and reads its quotes. A backslash inside a single-quoted string does not
# close the string: a loop after the escaped apostrophe is inside the string, so it is text and is allowed.
# A bare loop after the same apostrophe is code, and is refused. Each case with an escape has a control
# beside it with no escape, so the escape is the only difference between the two.

# The escaped apostrophe is text in the string, in each interpreter's syntax.
sh("waiter-quote: a python heredoc string with an escaped apostrophe holds a loop as text, allowed",
   "python3 - <<'EOF'\ns = 'it\\'s: while true; do sleep 3; done'\nEOF", "allow", cwd=NOGIT)
sh("waiter-quote: a node heredoc string with an escaped apostrophe holds a loop as text, allowed",
   "node - <<'EOF'\nconst s = 'it\\'s: while true; do sleep 3; done';\nEOF", "allow", cwd=NOGIT)
sh("waiter-quote: a perl heredoc string with an escaped apostrophe holds a loop as text, allowed",
   "perl - <<'EOF'\nmy $s = 'it\\'s: while true; do sleep 3; done';\nEOF", "allow", cwd=NOGIT)
# The same three bodies with no escape: each is allowed, so the escape is the cause of the case above.
sh("waiter-quote: a python heredoc string holding the loop, no escape, is allowed",
   "python3 - <<'EOF'\ns = 'it is: while true; do sleep 3; done'\nEOF", "allow", cwd=NOGIT)
sh("waiter-quote: a node heredoc string holding the loop, no escape, is allowed",
   "node - <<'EOF'\nconst s = 'it is: while true; do sleep 3; done';\nEOF", "allow", cwd=NOGIT)
sh("waiter-quote: a perl heredoc string holding the loop, no escape, is allowed",
   "perl - <<'EOF'\nmy $s = 'it is: while true; do sleep 3; done';\nEOF", "allow", cwd=NOGIT)

# A bare loop after an escaped apostrophe is code, not text, so it is refused. Without the escape it is refused too.
sh("waiter-quote: a bare loop after an escaped apostrophe in a python heredoc is refused",
   "python3 - <<'EOF'\nprint('it\\'s'); while true; do sleep 3; done\nEOF", "deny", "waiter", cwd=NOGIT)
sh("waiter-quote: a bare loop in a python heredoc, no escape, is refused",
   "python3 - <<'EOF'\nwhile true; do sleep 3; done\nEOF", "deny", "waiter", cwd=NOGIT)
sh("waiter-quote: a bare loop after a closed node template literal is refused",
   "node - <<'EOF'\nconst s = `it`;\nwhile true; do sleep 3; done\nEOF", "deny", "waiter", cwd=NOGIT)

# A node template literal is text too: a loop inside it, across lines, is allowed.
sh("waiter-quote: a node heredoc with a multi-line template literal holding a loop is allowed",
   "node - <<'EOF'\nconst s = `\nwhile true; do sleep 3; done\n`;\nEOF", "allow", cwd=NOGIT)

# The waiter refusal names Monitor, the wait the record allows (decision agents-wait-with-monitor).
sh("waiter-quote: the waiter refusal names the Monitor tool",
   "while true; do sleep 3; done", "deny", "waiter", cwd=NOGIT, carries=("Monitor",))

# Controls for the shell side: a foreground loop, and the same loop fed to a shell, is refused.
sh("waiter-quote: a foreground while-loop with sleep 3 is refused",
   "while true; do sleep 3; done", "deny", "waiter", cwd=NOGIT)
sh("waiter-quote: the same loop in an unquoted bash heredoc is refused",
   "bash <<EOF\nwhile true; do sleep 3; done\nEOF", "deny", "waiter", cwd=NOGIT)
sh("waiter-quote: the same loop in a quoted bash heredoc is refused",
   "bash <<'EOF'\nwhile true; do sleep 3; done\nEOF", "deny", "waiter", cwd=NOGIT)
sh("waiter-quote: the same loop in a quoted sh heredoc is refused",
   "sh <<'EOF'\nwhile true; do sleep 3; done\nEOF", "deny", "waiter", cwd=NOGIT)

# Controls for the quote reader: a comment opener, a multi-line string, a lone apostrophe in a comment, an
# apostrophe inside a double-quoted string, and an escape before a hash, each hold the loop as text.
sh("waiter-quote: a python comment opener inside a double-quoted string holds a loop, allowed",
   "python3 - <<'EOF'\ns = \"# note: while true; do sleep 3; done\"\nEOF", "allow", cwd=NOGIT)
sh("waiter-quote: a python multi-line string holds a loop as text, allowed",
   "python3 - <<'EOF'\ns = \"\"\"\nwhile true; do sleep 3; done\n\"\"\"\nEOF", "allow", cwd=NOGIT)
sh("waiter-quote: a python lone apostrophe in a comment does not open a quote, the loop after it is allowed",
   "python3 - <<'EOF'\n# don't\ns = \"while true; do sleep 3; done\"\nEOF", "allow", cwd=NOGIT)
sh("waiter-quote: a python apostrophe inside a double-quoted string holds a loop as text, allowed",
   "python3 - <<'EOF'\ns = \"it's: while true; do sleep 3; done\"\nEOF", "allow", cwd=NOGIT)
sh("waiter-quote: an escaped apostrophe then a hash inside a single-quoted string holds a loop, allowed",
   "python3 - <<'EOF'\ns = 'it\\'s # x: while true; do sleep 3; done'\nEOF", "allow", cwd=NOGIT)

# A quote or a template literal left open at the body's end must not hide the command after EOF. The body
# ends at EOF, so what follows it is a command. A comment opener inside a string is text, so a loop there is allowed.
sh("waiter-quote: a python heredoc body leaving a quote open at its end, then gh pr create, is refused as draft-pr",
   "python3 - <<'EOF'\nprint('C:\\Users\\')\nEOF\ngh pr create --title t --body b", "deny", "draft-pr", cwd=NOGIT)
sh("waiter-quote: a python heredoc body leaving a quote open at its end, then a loop after EOF, is refused",
   "python3 - <<'EOF'\nprint('C:\\Users\\')\nEOF\nwhile true; do sleep 3; done", "deny", "waiter", cwd=NOGIT)
sh("waiter-quote: a node heredoc body leaving a single-quoted string open at its end, then a loop after EOF, is refused",
   "node - <<'EOF'\nconst s = 'C:\\';\nEOF\nwhile true; do sleep 3; done", "deny", "waiter", cwd=NOGIT)
# Pin, no red found: refused on fccff95e6 and b62c51f67 as well, so it guards the template reading and is not a red.
sh("waiter-quote: pin, no red found: a node heredoc body with an open template literal, then a loop after EOF, is refused",
   "node - <<'EOF'\nconst s = `open\nEOF\nwhile true; do sleep 3; done", "deny", "waiter", cwd=NOGIT)
sh("waiter-quote: a node // opener inside a single-quoted string holding a loop is allowed",
   "node - <<'EOF'\nconst s = '// while true; do sleep 3; done';\nEOF", "allow", cwd=NOGIT)
sh("waiter-quote: a node /* opener inside a single-quoted string holding a loop is allowed",
   "node - <<'EOF'\nconst s = '/* while true; do sleep 3; done';\nEOF", "allow", cwd=NOGIT)

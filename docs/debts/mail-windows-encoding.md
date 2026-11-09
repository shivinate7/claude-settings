# The mail tool breaks on a Windows cp1252 pipe

- **What.** `bin/mail` reads stdin and prints with the locale encoding. On a Windows pipe in cp1252, a body with a character such as "→" raises UnicodeEncodeError, so `mail read` fails and `mail send -` garbles the body. Reproduced with `PYTHONIOENCODING=cp1252`. Build step 2 (Mac and Windows auth) runs the tool on Windows.
- **Where.** `bin/mail` `send` (stdin `-`) and `show`.
- **Decision.** session-messages (messages to and from sessions).
- **Retire.** A case in `hooks/test_mail.py` runs `bin/mail send -` and `bin/mail read` with `PYTHONIOENCODING=cp1252` and a non-ASCII body, and gets the body back unchanged.

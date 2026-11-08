# Env-file guard allows interpreter code that reads the file

- **What.** The env-file guard (`hooks/guard_env.py`) judges shell words, not the code an interpreter runs. These forms read the env file and are allowed:
  - A quoted python or node heredoc body that opens the file, such as `open(".env").read()`. The body is text for bash, so `env_refusal` does not judge the code in it.
  - A quoted python, node, perl or ruby heredoc body with an env file name in backticks and nothing before it, such as ``fs.readFileSync(`.env`)`` or ``File.read(`.env`)``. `_plain_escaped_quotes` (hooks/guard_env.py) blanks the backticks. A backticked `${dir}/.env` still denies.
  - `python3 -c "print(open('.env').read())"` and `node -e "...readFileSync('.env')"`. The script word is one quoted word, and no env name is a whole path in it.
  - `dotenv_values('.env')` in either form.
  - A session is likely to hit these only by writing a debug script. No incident is on record.
- **Where.** `hooks/guard_env.py` (`env_refusal`, `_env_flat`).
- **Decision.** `env-file-stays-unread`.
- **Retire.** An owner ruling on whether interpreter code is judged, then red cases for each form above, including the backticked name in a heredoc body. Until the ruling, these forms stay allowed on purpose.

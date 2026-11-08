"""The event-body reader script for tests (one home, beside lint/_test_git.py and lint/_test_temp.py).

A test writes EVENT_BODY_SCRIPT to a file and runs it as a CI step would run its reader: it reads
`.pull_request.body` from the event file that env GITHUB_EVENT_PATH names, as CI gives it, and writes
what it read to `seen.txt` in the working directory. It writes NO_EVENT_PATH when the env is unset, and
NO_BODY when the file cannot be read or holds no pull request body.
"""

NO_EVENT_PATH = "<no GITHUB_EVENT_PATH>"
NO_BODY = "<no body in the event file>"

EVENT_BODY_SCRIPT = (
    "import json, os\n"
    "path = os.environ.get('GITHUB_EVENT_PATH')\n"
    "if path is None:\n"
    "    text = %r\n"
    "else:\n"
    "    try:\n"
    "        with open(path, encoding='utf-8') as f:\n"
    "            pull = json.load(f).get('pull_request')\n"
    "    except (OSError, ValueError, AttributeError):\n"
    "        pull = None\n"
    "    body = pull.get('body') if isinstance(pull, dict) else None\n"
    "    text = body if isinstance(body, str) else %r\n"
    "with open('seen.txt', 'w', encoding='utf-8', newline='') as f:\n"
    "    f.write(text)\n") % (NO_EVENT_PATH, NO_BODY)

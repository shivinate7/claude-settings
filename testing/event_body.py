"""The event-body reader for tests (one home, beside tracked_tree.py in testing/).

The reader reads `.pull_request.body` from the event file that env GITHUB_EVENT_PATH names, as CI gives
it. It gives NO_EVENT_PATH when the env is unset, and NO_BODY when the file cannot be read or holds no
pull request body. It comes in two forms, one derived from the other so they cannot drift:
EVENT_BODY_DEF is source code that defines `event_body()`, with its imports, for a test to embed in a
generated stub; EVENT_BODY_SCRIPT is a whole script that calls it and writes the result to `seen.txt`
in the working directory, for a test to write to a file and run as a CI step would.
"""

NO_EVENT_PATH = "<no GITHUB_EVENT_PATH>"
NO_BODY = "<no body in the event file>"

EVENT_BODY_DEF = (
    "import json, os\n"
    "def event_body():\n"
    "    path = os.environ.get('GITHUB_EVENT_PATH')\n"
    "    if path is None:\n"
    "        return %r\n"
    "    try:\n"
    "        with open(path, encoding='utf-8') as f:\n"
    "            pull = json.load(f).get('pull_request')\n"
    "    except (OSError, ValueError, AttributeError):\n"
    "        pull = None\n"
    "    body = pull.get('body') if isinstance(pull, dict) else None\n"
    "    return body if isinstance(body, str) else %r\n") % (NO_EVENT_PATH, NO_BODY)

EVENT_BODY_SCRIPT = (
    EVENT_BODY_DEF +
    "with open('seen.txt', 'w', encoding='utf-8', newline='') as f:\n"
    "    f.write(event_body())\n")

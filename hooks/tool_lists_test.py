"""The one reader of an agent file's tool lists, shared by lint/test_check_agent_models.py and hooks/test_agent_brief.py.

Values are raw, as guard.frontmatter_keys leaves them. tokens does not strip a comment: a caller that reads one
strips it first. Standard library only.
"""


def tokens(raw):
    """The items of an inline list: `Bash, Read` and `[Bash, Read]` both read as ['Bash', 'Read']."""
    return [item.strip().strip("'\"") for item in raw.strip().strip("[]").split(",") if item.strip()]


def unread_list(keys):
    """The tools field whose list sits on the lines below its key, which this reader does not read; else None."""
    for field in ("tools", "disallowedTools"):
        if field in keys and not keys[field].strip():
            return field
    return None

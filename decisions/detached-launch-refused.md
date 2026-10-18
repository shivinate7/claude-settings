# The guard refuses a detached launch

## The ruling

The `detached-launch` rule in `hooks/guard.py` refuses a command that starts a process and detaches it from the session. It refuses these three shapes too:

- A bare `&` job in any segment, unless the command captures the pid with `$!`.
- `disown` in command position.
- The same shapes inside the script of `sh -c` or `bash -c`.

The remedy tells the agent to use `run_in_background`.

Kind: process
Home: hooks/guard.py

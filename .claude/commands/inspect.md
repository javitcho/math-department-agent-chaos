Inspect a saved math agent session without running any agents.

The session ID is: $ARGUMENTS

Run:

```bash
cd "/Users/javiermejia/Documents/GitHub Repos/math-department-agent-chaos/math-agents" && python main.py --session "$ARGUMENTS" --inspect
```

If no session ID was provided, first run `/malist` to show available sessions, then ask the user which one to inspect.

This dumps the full session state: manuscript topic, mode, all chunks with their statuses and flags, current round state, and a summary of each agent's memory.

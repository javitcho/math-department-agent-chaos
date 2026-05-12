Resume a saved math agent session in deep mode.

The session ID is: $ARGUMENTS

Run:

```bash
cd "/Users/javiermejia/Documents/GitHub Repos/math-department-agent-chaos/math-agents" && python main.py --session "$ARGUMENTS"
```

If no session ID was provided, first run `/malist` to show available sessions, then ask which one to resume.

To inject a note for the Rep in the first resumed round, ask the user if they have one and append `--note "..."` to the command.

The session picks up exactly where it left off: same chunk, same round, same agent memories. All stopping signals remain active.

Run the math agents system in scout mode on the given topic.

The topic is: $ARGUMENTS

Run this command and stream the output:

```bash
cd "/Users/javiermejia/Documents/GitHub Repos/math-department-agent-chaos/math-agents" && python main.py --topic "$ARGUMENTS" --mode scout
```

If no topic was provided, ask the user what topic to evaluate before running.

After the run completes, report: the verdict (PURSUE / DROP / INTERESTING), the session ID, and the one-line scout reason from the output. Then tell the user they can run `/deep <topic>` or `/resume <session-id>` to continue.

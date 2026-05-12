Run the math agents system in deep mode on the given topic.

The topic is: $ARGUMENTS

Run this command and stream the output:

```bash
cd "/Users/javiermejia/Documents/GitHub Repos/math-department-agent-chaos/math-agents" && python main.py --topic "$ARGUMENTS" --mode deep
```

If no topic was provided, ask the user what topic to develop before running.

Deep mode runs all six agents (Rep, Logic Critic, Counterex Hunter, Reference Critic, Elegance Critic, Orchestrator) per round, up to 4 rounds per chunk and 8 chunks per session. Typical cost: $0.50–$1.50.

After the run completes or is interrupted, report the session ID and exit reason. Remind the user they can resume with `/resume <session-id>` or export with `/export <session-id>`.

Export a math agent session to markdown and LaTeX without running any agents.

The session ID is: $ARGUMENTS

Run:

```bash
cd "/Users/javiermejia/Documents/GitHub Repos/math-department-agent-chaos/math-agents" && python main.py --session "$ARGUMENTS" --export
```

If no session ID was provided, first run `/malist` to show available sessions, then ask which one to export.

This writes two files to `math-agents/sessions/<id>/export/`:
- `manuscript.md` — human-readable version with chunk statuses and flags
- `manuscript.tex` — compilable LaTeX with full amsart preamble and \newtheorem declarations

If `pdflatex` is available on the system, it also compiles `manuscript.pdf` automatically. Report the output paths when done.

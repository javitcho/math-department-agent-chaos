# math-department-agent-chaos

A multi-agent system built in Python to help survive a math PhD. Models the internal
research process: rapid idea development with simultaneous self-critique across logical
validity, prior art, and aesthetic quality.

Not a proof verifier. Not autonomous. The human is always in the loop.

---

## What it does

You give it a topic (`"prove that √2 is irrational"`, `"why does the residue theorem work geometrically"`).
Seven specialized agents decompose it into a **dependency graph** of definitions, lemmas, theorems,
and proofs, then work through each node in topological order — writing LaTeX, finding logic errors,
hunting for counterexamples, checking prior art, and scoring elegance. You watch, inject notes,
and decide when to stop.

**Scout mode** (~$0.015): one-pass verdict — PURSUE, DROP, or INTERESTING.  
**Deep mode** (~$0.50–$1.50): full development, chunk by chunk, up to 4 rounds per node.

---

## Quickstart

```bash
cd math-agents

# 1. Install dependencies
pip install -r requirements.txt
cp .env.example .env        # add your ANTHROPIC_API_KEY

# 2. Run scout mode (fast, cheap, good first filter)
python main.py --topic "prove that √2 is irrational" --mode scout

# 3. Run deep mode on survivors
python main.py --topic "prove that √2 is irrational" --mode deep

# 4. Resume a saved session
python main.py --session abc123

# 5. Export to markdown + LaTeX
python main.py --session abc123 --export
```

### Web app

```bash
# Terminal 1 — Python backend (localhost:5000)
cd math-agents && python main.py --serve

# Terminal 2 — React dev server (localhost:5173)
cd math-agents/web && npm install && npm run dev
```

Open [http://localhost:5173](http://localhost:5173). The web app shows live agent output via SSE,
a KaTeX-rendered manuscript panel, and an SVG dependency graph in the supervisor panel.

---

## The agents

| Agent | Role |
|---|---|
| **Decomposer** | Breaks topic into a dependency graph (definitions → lemmas → theorems → proofs) |
| **Rep** | Writes and updates LaTeX content for each node (diff format after round 1) |
| **Logic Critic** | Finds logical errors, one line per flag, references LaTeX labels |
| **Counterex Hunter** | ≤3-step search for easy counterexamples |
| **Reference Critic** | Prior art, citation correctness, cross-domain connections (opt-in) |
| **Elegance Critic** | Scores 1–10, flags structural issues (every other round) |
| **Orchestrator** | Reads all outputs, decides next step, can redirect Rep to fix a dependency |

---

## CLI flags

```
--topic / -t       Start a new session
--mode             scout | deep (default: scout)
--session / -s     Resume a saved session
--note / -n        Inject a note into the next round
--list             List all saved sessions
--inspect          Dump session state without running agents
--export           Export to manuscript.md + manuscript.tex
--with-references  Enable the Reference Critic (disabled by default)
--purpose          paper | thesis | lecture_notes | fun | exploration
--audience         research | graduate | undergraduate | self
--rigor            full | sketch | intuition_first
--serve            Start the web app backend
```

---

## Runtime commands (while deep mode is running)

Type in the terminal during a session:

| Input | Effect |
|---|---|
| `n <note>` | Queue a note for the Rep in the next round |
| `s` | Stop after the current agent completes |
| `skip` | Abandon current node, move to next |
| `q` | Stop immediately, save state |

---

## Stopping signals

The system stops or pauses automatically when:

- **COUNTEREXAMPLE** — a concrete counterexample was found (hard stop)
- **SERENDIPITY** — unexpected cross-domain connection found (pause, you decide)
- **CONVERGED** — two consecutive clean rounds with no new flags
- **ELEGANT** — logic clean and elegance score ≥ 8
- **INCUBATE** — same flags for 3 rounds with no progress (save and pause)
- **BUDGET** — round or node limit reached

---

## Project structure

```
math-agents/
├── main.py                  CLI entry point
├── config.py                all tunable parameters
├── agents/                  seven specialized agents + base class
├── models/                  ChunkNode, Manuscript, RoundState, signals
├── loop/                    scout.py and deep.py session loops
├── storage/                 session persistence, memory compression, manuscript parser
├── output/                  rich terminal display, markdown/LaTeX exporter
├── server/                  FastAPI backend + SSE runner
├── web/                     React frontend (Vite, KaTeX)
├── skills/                  markdown prompt modules loaded by agents at runtime
└── sessions/                saved session state (gitignored)
```

See [CLAUDE.md](CLAUDE.md) for full architecture notes, development preferences, and agent output formats.

---

## Cost estimates

| Mode | Agents | Cost |
|---|---|---|
| Scout | Decomposer + Rep + Logic + Counterex + Orchestrator | ~$0.015 |
| Deep (4 nodes, 2 rounds each) | All 6 agents per round | ~$0.30–$0.60 |
| Deep (8 nodes, 4 rounds each) | All 6 agents per round | ~$0.80–$1.50 |

Reference Critic adds ~30% to input token cost when enabled.

# Math Research Multi-Agent System

A Python CLI (and optional web app) that models a mathematician's internal research process:
rapid idea development with simultaneous self-critique across logical validity, prior art,
and aesthetic quality. Not a proof verifier. Not autonomous. The human is always in the loop.

---

## What lives where

```
math-department-agent-chaos/
├── CLAUDE.md                    ← you are here
├── math_agents_blueprint.md     ← authoritative spec; consult before any architectural change
├── math-agents.jsx              ← original React prototype (reference only, not used)
└── math-agents/                 ← the Python implementation
    ├── main.py                  ← CLI entry point (click)
    ├── config.py                ← all tunable parameters
    ├── .env                     ← ANTHROPIC_API_KEY (never commit)
    ├── agents/
    │   ├── base.py              ← BaseAgent: call_api, _build_context, skill loader, memory I/O
    │   ├── orchestrator.py      ← session supervisor; produces 4-field JSON + modify_dependency
    │   ├── decomposer.py        ← one-shot topic → dependency graph (nodes + depends_on edges)
    │   ├── rep.py               ← writes/updates LaTeX node content (diff format after round 1)
    │   ├── logic_critic.py      ← finds logical errors, one line per flag
    │   ├── counterex.py         ← ≤3-step counterexample search
    │   ├── reference.py         ← prior art + cross-domain connections (opt-in)
    │   └── elegance.py          ← scores 1-10, flags structural issues (every other round)
    ├── models/
    │   ├── signals.py           ← ChunkType, ChunkStatus, SessionMode, StoppingSignal enums
    │   ├── document.py          ← ChunkNode, ChunkFlag, Manuscript; graph utilities
    │   └── state.py             ← RoundState, AgentMemory, MemoryEntry, SessionScope
    ├── loop/
    │   ├── scout.py             ← one-pass verdict: Decomposer→Rep→Logic→Counterex→Orch
    │   └── deep.py              ← graph traversal loop; all agents; stopping signals
    ├── storage/
    │   ├── session_store.py     ← save/load sessions/{id}/session.json; save hooks for SSE
    │   ├── memory_store.py      ← per-agent memory with compression
    │   └── manuscript_parser.py ← parse .tex/.md files → dependency graph
    ├── output/
    │   ├── display.py           ← rich terminal panels; display_graph_status()
    │   └── exporter.py          ← manuscript.md + manuscript.tex per round
    ├── server/                  ← optional FastAPI web app
    │   ├── app.py               ← REST + SSE endpoints
    │   └── runner.py            ← background session thread; save hooks → SSE events
    ├── web/                     ← React frontend (Vite)
    │   └── src/
    │       ├── App.jsx          ← main workspace screen
    │       └── components/
    │           ├── SupervisorPanel.jsx  ← scope, signals, SVG dependency graph
    │           ├── ManuscriptPanel.jsx  ← node content panels
    │           └── AgentFeed.jsx        ← live agent output stream
    ├── skills/                  ← markdown prompt modules loaded by agents at runtime
    │   ├── orchestrator/
    │   ├── logic_critic/
    │   ├── rep/
    │   └── reference/
    └── sessions/                ← persisted session state (gitignored)
```

---

## Running the system

### Terminal (CLI)

```bash
cd math-agents
pip install -r requirements.txt   # first time only

# Quick idea filter — one pass, verdict only (~$0.015)
python main.py --topic "prove that √2 is irrational" --mode scout

# Full development — dependency graph, all agents, up to 4 rounds per node
python main.py --topic "prove that √2 is irrational" --mode deep

# Enable the Reference Critic (disabled by default to save tokens)
python main.py --topic "X" --mode deep --with-references

# Explicit scope overrides
python main.py --topic "X" --purpose paper --audience graduate --rigor full

# Resume a saved session
python main.py --session abc123

# Resume and inject a note for the next round
python main.py --session abc123 --note "check the case of p = 2 specifically"

# List all saved sessions
python main.py --list

# Inspect a session without running agents
python main.py --session abc123 --inspect

# Export to markdown + LaTeX (also runs pdflatex if available)
python main.py --session abc123 --export

# Start the web app (localhost:5000 backend, localhost:5173 frontend)
python main.py --serve
```

### Web app (two terminals)

```bash
# Terminal 1 — Python backend
cd math-agents && python main.py --serve

# Terminal 2 — React dev server
cd math-agents/web && npm install && npm run dev
# → open http://localhost:5173
```

Use the slash commands below in this Claude Code session instead of typing these manually.

---

## Slash commands (use in this Claude Code session)

| Command | What it does |
|---|---|
| `/scout <topic>` | Run scout mode on a topic |
| `/deep <topic>` | Run deep mode on a topic |
| `/serve` | Start the web app (backend + instructions for frontend) |
| `/malist` | List all saved sessions |
| `/inspect <session-id>` | Inspect a session without running agents |
| `/resume <session-id>` | Resume a saved session in deep mode |
| `/export <session-id>` | Export a session to markdown + LaTeX |

---

## Architecture decisions (do not reverse without reading blueprint §14)

- **Sequential agent calls** — no asyncio.gather, no thread pools. API concurrency limits
  apply; also produces readable output one agent at a time.
- **Session saved after every agent call** — not just end of round. Crash recovery for
  long sessions that are expensive to re-run.
- **Dependency graph model** — `Manuscript.nodes: Dict[str, ChunkNode]` keyed by id.
  `traversal_order` is a topological sort recomputed when the graph changes. Agents receive
  the focus node plus direct dependencies only (`_build_context`), not the full document.
- **Graph traversal loop** — `next_chunk_to_process()` walks `traversal_order` and returns
  the first node that is not APPROVED (or has `review_requested=True`). Approving a node
  calls `propagate_change()` which sets `review_requested=True` on all transitive dependents.
- **modify_dependency** — orchestrator can redirect the Rep to fix a dependency chunk instead
  of the focus chunk. The loop re-queues the current chunk to be processed after the
  dependency is approved.
- **Rep outputs diffs** — `DIFF / REPLACE: / WITH: / END DIFF` format after round 1.
  First draft always uses `FULL / END FULL`. `apply_rep_output()` in `rep.py` handles both.
- **Orchestrator output is 4-field JSON** — `directive_for_rep`, `stopping_signal`,
  `stopping_reason`, `advance_chunk` (plus `modify_dependency`). Flags/established/round_goal
  are derived in the loop from critic outputs, not from the orchestrator model.
- **Two modes** — Scout (Decomposer → Rep → Logic → Counterex → Orchestrator, ~$0.015)
  filters ideas; Deep (all agents, graph traversal, ~$0.50–$1.50) develops survivors.
- **Reference Critic is opt-in** — `--with-references` flag or `config.reference_critic_enabled`.
  Disabled by default to save tokens (~30% of input cost when active).
- **Elegance runs every other round** — and only when logic was clean the previous round.
- **INCUBATE is not failure** — same flags for 3 rounds → save state, pause for the human.
  Resume with `--session`.
- **SERENDIPITY is a pause, not a stop** — cross-domain connections flagged with `!!` by the
  Reference Critic trigger an interactive "Continue? [y/n]" prompt.
- **Web layer is read-and-render only** — Python process owns all state; SSE hooks in
  `session_store.py` emit events after every `save_session()` call.

---

## Key config values (`math-agents/config.py`)

| Parameter | Value | Notes |
|---|---|---|
| `model` | `claude-sonnet-4-6` | bump to opus for harder sessions |
| `max_tokens_rep` | 400 | diff format keeps this low |
| `max_tokens_orchestrator` | 300 | 4-field schema only |
| `max_tokens_logic` | 100 | one line per flag |
| `max_tokens_counterex` | 100 | ≤3 attempts |
| `max_rounds_per_chunk` | 4 | budget per node |
| `max_chunks_per_session` | 8 | budget per session (graph nodes) |
| `convergence_rounds` | 2 | clean rounds → CONVERGED → node APPROVED |
| `incubation_rounds` | 3 | stuck rounds → INCUBATE → pause |
| `reference_critic_enabled` | `False` | enable with `--with-references` |
| `request_delay_seconds` | 0.5 | between agent calls |

---

## Document model: ChunkNode and ChunkFlag

```python
@dataclass
class ChunkNode:
    id: str
    title: str
    content: str
    type: ChunkType          # definition | lemma | theorem | proof | corollary | remark | section
    status: ChunkStatus
    depends_on: List[str]    # chunk ids this node directly uses
    dependents: List[str]    # chunk ids that directly use this node (computed)
    round_created: int
    round_last_modified: int
    flags: List[ChunkFlag]   # structured flags with source_agent and resolved field
    review_requested: bool   # true if queued for re-review due to dependency change

@dataclass
class ChunkFlag:
    source_agent: str
    round: int
    text: str
    resolved: bool = False
```

Graph utility functions in `models/document.py`:
- `topological_sort(nodes)` — Kahn's algorithm; definitions first, proofs last
- `rebuild_dependents(nodes)` — recomputes reverse edges from `depends_on`
- `get_context_for_chunk(nodes, chunk_id)` — direct deps only, one hop
- `propagate_change(nodes, changed_id)` — BFS over dependents, sets `review_requested=True`

---

## Stopping signals (precedence order)

1. `COUNTEREXAMPLE` — hard stop, claim is false
2. `SERENDIPITY` — pause, cross-domain link found, user decides
3. `SCOUT_PURSUE / SCOUT_DROP / SCOUT_INTERESTING` — scout mode terminals
4. `CONVERGED` — 2 consecutive clean rounds → node APPROVED
5. `ELEGANT` — elegance score ≥ 8 → node APPROVED
6. `INCUBATE` — same flags for 3 rounds → save and pause
7. `BUDGET` — round/node limit reached
8. `USER_STOP` — manual interrupt

---

## Runtime user commands (while a deep session is running)

Type these in the terminal:

| Input | Effect |
|---|---|
| `n <note>` | Queue a note for the Rep in the next round |
| `s` | Stop after the current agent completes |
| `skip` | Mark current node ABANDONED, move to next |
| `q` | Stop immediately, save state |

---

## Agent output formats

| Agent | Output format |
|---|---|
| Rep (round 1) | `---CHUNK---` ... `---END CHUNK---` then optional `PUSHBACK:` and `MEMORY NOTE:` |
| Rep (round 2+) | `DIFF\nREPLACE:\n...\nWITH:\n...\nEND DIFF` blocks; falls back to FULL |
| Logic Critic | One line per flag: `\ref{thm:x}, step N: error type — note` or `ok` |
| Counterex | `COUNTEREXAMPLE FOUND` with details, or `No quick counterexample. Tried: ...` |
| Reference | `PRIOR ART:` / `CORRECTIONS:` / `CONNECTIONS:` / `NOVEL:` — four fields, no markdown |
| Elegance | `SINCE LAST REVIEW:` / `SCORE: N` / `ISSUES:` / `SUGGESTIONS:` |
| Orchestrator | JSON — `directive_for_rep`, `stopping_signal`, `stopping_reason`, `advance_chunk`, `modify_dependency` |
| Decomposer | JSON — `title`, `nodes[]` (each with `id`, `title`, `type`, `description`, `depends_on`), `global_context`, `scout_priority` |

---

## Development preferences

- **No code comments** unless the WHY is non-obvious (hidden constraint, workaround, subtle invariant).
- **No trailing summaries** in responses — the diff speaks for itself.
- **Terse** — one sentence per update while working; results directly stated.
- **No stubs** — every function fully implemented. No `TODO: implement`.
- **Test topic** — always validate new loop logic with `"prove that √2 is irrational"` before
  harder topics like the residue theorem.
- **Build order** when adding new agents: models → base changes → agent → skill file → loop integration.
- **Error handling pattern**: every agent call in `try/except`; failed agent returns
  `"error — skipped: <msg>"` and the round continues. Never crash the round.
- **f-string + backslash** — Python 3.10 does not allow backslashes inside f-string expressions.
  Build prompts with string concatenation or assign backslash-containing strings to variables first.
- **LaTeX in agent outputs** — node content is raw LaTeX (no preamble). The exporter in
  `output/exporter.py` adds `\documentclass{amsart}`, `\usepackage{...}`, `\newtheorem{...}`.
  Only escape LaTeX special characters in plain-text metadata (titles, session IDs).
- **Graph invariant** — `depends_on` is the source of truth; `dependents` is always derived
  via `rebuild_dependents()`. Never write to `dependents` directly.
- **Manuscript passed in extra** — loops pass `extra={"manuscript": manuscript}` to every
  agent call. Agents call `self._serialize_state(state, extra)` which routes to `_build_context`
  when manuscript is present.

---

## Session artifacts

Each session writes to `math-agents/sessions/{session_id}/`:

```
sessions/abc12345/
├── session.json          ← full state: manuscript (nodes graph) + RoundState + all agent memories
└── export/
    ├── manuscript.md     ← human-readable, updated every round
    └── manuscript.tex    ← compilable LaTeX, updated every round
                          ← manuscript.pdf appears here if pdflatex is available
```

---

## Future extensions (out of scope, architecture accommodates)

- Lean/Coq formalization gateway (8th agent, runs on APPROVED nodes only)
- Elegance score history + trend plotting across rounds
- Cross-session memory (orchestrator-level, same topic)
- Vector search over past sessions for auto-retrieval of relevant prior work
- Multi-topic meta-orchestrator (scout all → deep the best)
- Graph cycle detection warning (currently appends cycle members at end of traversal order)

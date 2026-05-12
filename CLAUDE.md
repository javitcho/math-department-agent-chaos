# Math Research Multi-Agent System

A Python CLI that models a mathematician's internal research process: rapid idea development
with simultaneous self-critique across logical validity, prior art, and aesthetic quality.
Not a proof verifier. Not autonomous. The human is always in the loop.

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
    │   ├── base.py              ← BaseAgent: call_api, skill loader, memory I/O
    │   ├── orchestrator.py      ← session supervisor; produces RoundState JSON
    │   ├── decomposer.py        ← one-shot topic → chunk roadmap
    │   ├── rep.py               ← writes/updates LaTeX chunk content
    │   ├── logic_critic.py      ← finds logical errors, one line per flag
    │   ├── counterex.py         ← ≤3-step counterexample search
    │   ├── reference.py         ← prior art + cross-domain connections
    │   └── elegance.py          ← scores 1-10, flags structural issues
    ├── models/
    │   ├── signals.py           ← ChunkStatus, SessionMode, StoppingSignal enums
    │   ├── document.py          ← Chunk, Manuscript dataclasses
    │   └── state.py             ← RoundState, AgentMemory, MemoryEntry
    ├── loop/
    │   ├── scout.py             ← one-pass verdict: Decomposer→Rep→Logic→Counterex→Orch
    │   └── deep.py              ← full loop: chunk-by-chunk, all agents, stopping signals
    ├── storage/
    │   ├── session_store.py     ← save/load sessions/{id}/session.json
    │   └── memory_store.py      ← per-agent memory with compression
    ├── output/
    │   ├── display.py           ← rich terminal panels
    │   └── exporter.py          ← manuscript.md + manuscript.tex per round
    ├── skills/                  ← markdown prompt modules loaded by agents at runtime
    │   ├── orchestrator/        ← chunk_splitter.md, state_builder.md, decision_logic.md
    │   ├── logic_critic/        ← error_taxonomy.md
    │   ├── rep/                 ← proof_scaffolder.md (includes LaTeX conventions)
    │   └── reference/           ← search_strategy.md
    └── sessions/                ← persisted session state (gitignored)
```

---

## Running the system

All commands run from `math-agents/`. The `.env` file is already set up.

```bash
cd math-agents

# Quick idea filter — one pass, verdict only (~$0.015)
python main.py --topic "prove that √2 is irrational" --mode scout

# Full development — chunk by chunk, all agents, up to 4 rounds per chunk
python main.py --topic "prove that √2 is irrational" --mode deep

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
```

Use the slash commands below in this Claude Code session instead of typing these manually.

---

## Slash commands (use in this Claude Code session)

| Command | What it does |
|---|---|
| `/scout <topic>` | Run scout mode on a topic |
| `/deep <topic>` | Run deep mode on a topic |
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
- **Chunk-based document model** — agents receive one chunk + context, not the full manuscript.
  Scales linearly with chunk count; full-document passing hits token limits fast.
- **Rep outputs LaTeX** — AMS environments (`\begin{theorem}`, `\begin{proof}`, etc.) with
  `\label{thm:name}` on every numbered environment. Label prefixes: `def:`, `thm:`, `lem:`,
  `cor:`, `rem:`. No document preamble — the exporter adds it.
- **Orchestrator output is JSON** — the `_extract_partial` fallback salvages truncated output
  rather than silently discarding it. Partial is better than a blank default.
- **Two modes** — Scout (Decomposer → Rep → Logic → Counterex → Orchestrator, ~$0.015)
  filters ideas; Deep (all six agents, up to 4 rounds × 8 chunks, ~$0.50–$1.50) develops survivors.
- **INCUBATE is not failure** — same flags for 3 rounds → save state, pause for the human.
  Résumé with `--session`.
- **SERENDIPITY is a pause, not a stop** — cross-domain connections flagged with `!!` by the
  Reference Critic trigger an interactive "Continue? [y/n]" prompt.

---

## Key config values (`math-agents/config.py`)

| Parameter | Value | Notes |
|---|---|---|
| `model` | `claude-sonnet-4-6` | bump to opus for harder sessions |
| `max_tokens_orchestrator` | 800 | raised from blueprint's 400 to prevent JSON truncation |
| `max_tokens_rep` | 700 | LaTeX chunk content |
| `max_rounds_per_chunk` | 4 | budget per chunk |
| `max_chunks_per_session` | 8 | budget per session |
| `convergence_rounds` | 2 | clean rounds → CONVERGED → chunk APPROVED |
| `incubation_rounds` | 3 | stuck rounds → INCUBATE → pause |
| `request_delay_seconds` | 0.5 | between agent calls |

---

## Stopping signals (precedence order)

1. `COUNTEREXAMPLE` — hard stop, claim is false
2. `SERENDIPITY` — pause, cross-domain link found, user decides
3. `SCOUT_PURSUE / SCOUT_DROP / SCOUT_INTERESTING` — scout mode terminals
4. `CONVERGED` — 2 consecutive clean rounds → chunk APPROVED
5. `ELEGANT` — elegance score ≥ 8 → chunk APPROVED
6. `INCUBATE` — same flags for 3 rounds → save and pause
7. `BUDGET` — round/chunk limit reached
8. `USER_STOP` — manual interrupt

---

## Runtime user commands (while a session is running)

Type these in the terminal during a deep session:

| Input | Effect |
|---|---|
| `n <note>` | Queue a note for the Rep in the next round |
| `s` | Stop after the current agent completes |
| `skip` | Mark current chunk ABANDONED, move to next |
| `q` | Stop immediately, save state |

---

## Agent output formats

| Agent | Output format |
|---|---|
| Rep | `---CHUNK---` ... `---END CHUNK---` then optional `PUSHBACK:` and `MEMORY NOTE:` |
| Logic Critic | One line per flag: `\ref{thm:x}, step N: error type — note` or `ok` |
| Counterex | `COUNTEREXAMPLE FOUND` with details, or `No quick counterexample. Tried: ...` |
| Reference | `PRIOR ART:` / `CORRECTIONS:` / `CONNECTIONS:` / `NOVEL:` — four fields, one or two lines each, no markdown |
| Elegance | `SINCE LAST REVIEW:` / `SCORE: N` / `ISSUES:` / `SUGGESTIONS:` |
| Orchestrator | JSON — `established`, `open_flags`, `round_goal`, `directive_for_rep`, `stopping_signal`, `stopping_reason`, `priority_issues`, `advance_chunk`, `memory_note` |
| Decomposer | JSON — `core_claim`, `key_definitions`, `lemmas_needed`, `proof_strategy`, `chunks`, `scout_priority` |

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
- **LaTeX in agent outputs** — chunk content is raw LaTeX (no preamble). The exporter in
  `output/exporter.py` adds `\documentclass{amsart}`, `\usepackage{...}`, `\newtheorem{...}`.
  Only escape LaTeX special characters in plain-text metadata (titles, session IDs).

---

## Session artifacts

Each session writes to `math-agents/sessions/{session_id}/`:

```
sessions/abc12345/
├── session.json          ← full state: manuscript + RoundState + all agent memories
├── memory/
│   ├── orchestrator.json
│   ├── rep.json
│   ├── logic_critic.json
│   ├── counterex.json
│   ├── reference.json
│   └── elegance.json
└── export/
    ├── manuscript.md     ← human-readable, updated every round
    └── manuscript.tex    ← compilable LaTeX, updated every round
                          ← manuscript.pdf appears here if pdflatex is available
```

---

## Future extensions (out of scope, architecture accommodates)

- Lean/Coq formalization gateway (8th agent, runs on APPROVED chunks only)
- Elegance score history + trend plotting across rounds
- Cross-session memory (orchestrator-level, same topic)
- Vector search over past sessions for auto-retrieval of relevant prior work
- Multi-topic meta-orchestrator (scout all → deep the best)

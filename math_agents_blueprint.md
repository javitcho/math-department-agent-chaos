# Mathematical Research Multi-Agent System — Complete Blueprint

> This document is the authoritative specification for the Python implementation.
> It captures all architectural decisions, agent definitions, data models, loop logic,
> and design philosophy developed through iterative design discussion.
> Hand this to Claude Code to build the system.

---

## 1. Vision & Design Philosophy

### What this system models

A mathematician's internal research process: a torrent of ideas, rapid development of the most
promising ones, and simultaneous self-critique across three axes — logical validity, prior art,
and aesthetic quality. The system is a tool for one person's research workflow, not a product.
It should feel like a fast, rigorous scratchpad, not an academic writing assistant.

### Core design principles

1. **Efficiency over completeness.** Agents work on one chunk at a time, not the whole document.
   They receive a structured state object, not the full manuscript. Tokens are a budget.

2. **Signal, not prose.** Agent outputs are terse and structured. A logic flag is one line.
   An elegance note is a bullet. No preamble, no explanation of what the agent is doing,
   no politeness. "Missing: continuity of f at p" is better than three paragraphs.

3. **Instructions, not personas.** Agents are defined by their task, output format, and constraints.
   No "you are a brilliant..." framing. Clear instructions produce more predictable behavior.

4. **Modular document.** The manuscript is a collection of chunks with statuses.
   Each round focuses on one chunk. Critics read that chunk plus context, not everything.

5. **Two modes for two workflows:**
   - **Scout mode** — filter ideas fast. One pass, verdict only. Cheap.
   - **Deep mode** — develop what passes the filter. Full pipeline, chunk by chunk.

6. **The system pauses, it does not terminate.** Inspired by Poincaré's incubation stage:
   when the system runs out of signal or hits a budget, it saves state and surfaces
   a summary. The human takes a walk. Resumes later. This is not a failure state.

7. **Stopping is aesthetic, not just logical.** A serendipitous cross-domain connection
   (e.g., an algebraic result unexpectedly touching geometry) is a positive stopping signal —
   the system surfaces it and pauses. Beauty is a real criterion.

### What this is NOT

- Not a proof verifier (no Lean/Coq in v1; architecture should accommodate it in future)
- Not a literature search engine (reference critic uses model knowledge + web search,
  but is not a replacement for a real literature review)
- Not autonomous — the human is always in the loop and can override anything

---

## 2. Project Structure

```
math-agents/
├── main.py                    # CLI entry point
├── config.py                  # Model, token budgets, defaults
├── requirements.txt
│
├── agents/
│   ├── base.py                # BaseAgent class, callAPI, memory I/O
│   ├── orchestrator.py
│   ├── decomposer.py
│   ├── rep.py
│   ├── logic_critic.py
│   ├── counterex.py
│   ├── reference.py
│   └── elegance.py
│
├── skills/                    # Prompt modules loaded by agents at runtime
│   ├── orchestrator/
│   │   ├── chunk_splitter.md      # How to identify logical chunk boundaries
│   │   ├── state_builder.md       # Schema + instructions for state object
│   │   └── decision_logic.md      # When to advance chunk, stop, escalate
│   ├── logic_critic/
│   │   └── error_taxonomy.md      # Taxonomy of logical error types to check
│   ├── rep/
│   │   └── proof_scaffolder.md    # Def/Theorem/Proof structure, notation conventions
│   └── reference/
│       └── search_strategy.md     # How to structure a literature check
│
├── models/
│   ├── document.py            # Chunk, Manuscript dataclasses
│   ├── state.py               # RoundState, AgentMemory, OrchestratorOutput
│   └── signals.py             # StoppingSignal enum
│
├── loop/
│   ├── scout.py               # Scout mode: one-pass, verdict
│   └── deep.py                # Deep mode: multi-round, chunk-by-chunk
│
├── storage/
│   ├── session_store.py       # Save/load full session state as JSON
│   └── memory_store.py        # Per-agent memory persistence
│
├── output/
│   ├── display.py             # Rich terminal output
│   └── exporter.py            # Export manuscript to markdown / LaTeX stub
│
└── sessions/                  # Persisted sessions (gitignore contents)
    └── .gitkeep
```

---

## 3. Data Models

### 3.1 Chunk

The fundamental unit of the manuscript. One logical piece: a definition, a lemma, a proof
step, a remark. The Rep works on one chunk per round. Critics read one chunk per round.

```python
@dataclass
class Chunk:
    id: str                   # e.g. "lemma_1", "proof_main", "remark_geometry"
    title: str                # Short label
    content: str              # Mathematical content (plain text, unicode math symbols)
    status: ChunkStatus       # see below
    round_created: int
    round_last_modified: int
    flags: List[str]          # Accumulated critic flags, not yet resolved
    approved_by_rounds: int   # How many consecutive rounds with no new flags
```

```python
class ChunkStatus(Enum):
    DRAFT          = "draft"           # Rep just wrote it, not yet reviewed
    UNDER_REVIEW   = "under_review"    # Critics are looking at it
    FLAGGED        = "flagged"         # Has unresolved issues
    NEEDS_REWORK   = "needs_rework"    # Orchestrator sent back to Rep
    APPROVED       = "approved"        # No new flags for N rounds
    ABANDONED      = "abandoned"       # Orchestrator decided not worth pursuing
```

### 3.2 Manuscript

```python
@dataclass
class Manuscript:
    topic: str
    mode: SessionMode         # SCOUT or DEEP
    chunks: List[Chunk]
    current_chunk_id: str
    global_context: str       # 3-5 bullet summary of everything approved so far
    session_id: str
    created_at: datetime
```

### 3.3 RoundState

What the orchestrator produces at the end of each round. This is the shared medium —
all agents in the next round receive this object plus the current chunk, nothing else.

```python
@dataclass
class RoundState:
    round: int
    mode: SessionMode
    established: List[str]       # Bullet points: what is proven/accepted
    current_chunk_id: str
    current_chunk_title: str
    focus_text: str              # Verbatim text of the chunk under scrutiny
    open_flags: List[str]        # Unresolved issues from prior rounds
    round_goal: str              # One sentence: what this round should accomplish
    directive_for_rep: str       # Specific instruction for the Rep (suggestion, not command)
    stopping_signal: StoppingSignal
    stopping_reason: str
    priority_issues: List[str]   # Top 3 issues, ranked
    scout_verdict: Optional[str] # PURSUE / DROP / INTERESTING (scout mode only)
```

### 3.4 AgentMemory

Each agent maintains a lightweight running note across rounds for the current session.
Stored in `sessions/{id}/memory/{agent}.json`. Loaded at the start of every agent call.
Updated after every agent call. Keeps the agent from re-examining already-cleared ground.

```python
@dataclass
class AgentMemory:
    agent_id: str
    session_id: str
    entries: List[MemoryEntry]

@dataclass
class MemoryEntry:
    round: int
    chunk_id: str
    note: str          # One short bullet. Max ~20 words.
```

Memory is agent-specific and session-scoped. It does not persist across sessions.
Max entries: 20 (oldest dropped). This keeps memory token cost bounded at ~200 tokens.

### 3.5 StoppingSignal

```python
class StoppingSignal(Enum):
    CONTINUE        = "continue"         # Keep going
    SERENDIPITY     = "serendipity"      # Surprising cross-domain connection found — pause
    COUNTEREXAMPLE  = "counterexample"   # Hard stop — claim is false
    CONVERGED       = "converged"        # Critics silent for 2 consecutive rounds
    ELEGANT         = "elegant"          # Elegance threshold reached
    BUDGET          = "budget"           # Round or token limit reached
    SCOUT_PURSUE    = "scout_pursue"     # Scout verdict: worth deep dive
    SCOUT_DROP      = "scout_drop"       # Scout verdict: not worth pursuing
    SCOUT_INTERESTING = "scout_interesting" # Scout: interesting but unclear
    USER_STOP       = "user_stop"        # Manual interrupt
    INCUBATE        = "incubate"         # Stuck — save state, pause for human
```

**Signal hierarchy (precedence):**
1. `COUNTEREXAMPLE` — hard stop, cannot continue
2. `SERENDIPITY` — pause and surface; can continue if user chooses
3. `SCOUT_*` — scout mode terminal signals
4. `CONVERGED` / `ELEGANT` — natural completion
5. `INCUBATE` — stuck after N rounds with no progress
6. `BUDGET` — limit reached
7. `USER_STOP` — manual

---

## 4. Agents

All agents follow the same call signature. Differences are in system prompt, output format,
and which skills they load.

### 4.0 BaseAgent

```python
class BaseAgent:
    def __init__(self, agent_id: str, config: Config):
        self.agent_id = agent_id
        self.config = config
        self.skills = self._load_skills()   # loads markdown files from skills/{agent_id}/

    def call(self, state: RoundState, memory: AgentMemory, extra: dict = {}) -> str:
        system = self._build_system_prompt()
        user = self._build_user_message(state, memory, extra)
        return call_api(system, user, self.config, use_search=self._uses_search())

    def _build_system_prompt(self) -> str:
        # Concatenate: task description + output format + constraints + loaded skills
        raise NotImplementedError

    def _build_user_message(self, state, memory, extra) -> str:
        # Concatenate: state object (serialized) + focus chunk + memory + any extra
        raise NotImplementedError
```

**Token budget per agent call (target):**
- System prompt (task + format + skills): ~300 tokens
- State object: ~200 tokens
- Focus chunk: ~400 tokens
- Agent memory: ~150 tokens
- Total input: ~1050 tokens
- Output: 150–600 tokens depending on agent (see below)

---

### 4.1 Orchestrator

**Role:** Session supervisor. No attachment to the mathematics. Reads all agent outputs,
synthesizes them, decides what happens next. Issues suggestions (not commands) to the Rep.
Checks stopping signals. Produces the RoundState for the next round.

**Skills loaded:**
- `skills/orchestrator/chunk_splitter.md`
- `skills/orchestrator/state_builder.md`
- `skills/orchestrator/decision_logic.md`

**System prompt structure:**
```
TASK:
Read the current round outputs from all agents. Produce the RoundState for the next round.

INPUTS YOU RECEIVE:
- Current chunk (text)
- Rep output (updated chunk draft + any pushback)
- Logic critic flags
- Counterexample hunter result
- Reference critic notes
- Elegance critic assessment
- Your own memory from prior rounds

OUTPUT FORMAT (JSON, no markdown fences):
{
  "established": ["bullet", "bullet"],
  "current_chunk_id": "...",
  "open_flags": ["flag", "flag"],
  "round_goal": "one sentence",
  "directive_for_rep": "collegial suggestion, not command. Rep may disagree.",
  "stopping_signal": "continue | serendipity | counterexample | converged | elegant | budget | incubate",
  "stopping_reason": "one sentence",
  "priority_issues": ["issue1", "issue2", "issue3"],
  "advance_chunk": true | false,
  "memory_note": "one short bullet for your own memory"
}

DECISION RULES (from decision_logic skill):
- COUNTEREXAMPLE: if counterex hunter reports a valid, concrete counterexample → hard stop
- SERENDIPITY: if reference critic flags a surprising cross-domain connection → pause
- CONVERGED: if no agent reported a new issue this round AND last round also had no new issues → converged
- ADVANCE_CHUNK: if chunk has no open flags after this round → advance to next chunk
- INCUBATE: if the same flags have appeared for 3+ consecutive rounds with no progress → incubate
- CONTINUE: default

CONSTRAINTS:
- Total output: 400 tokens max
- Be specific. "Rep should clarify the continuity assumption in step 2" not "Rep should improve the proof"
- Directive to Rep is a suggestion. Do not frame it as a command.
```

**Output tokens:** ~400

---

### 4.2 Decomposer

**Role:** First agent called. Runs once at session start. Breaks the topic into a structured
roadmap: sub-goals, definitions needed, lemmas, suggested approach, expected cross-domain
connections. Does not run again unless the orchestrator explicitly resets.

**Skills loaded:** none (relies on model's mathematical knowledge)

**System prompt structure:**
```
TASK:
Given a mathematical topic or theorem, produce a structured decomposition as a roadmap
for a research session.

OUTPUT FORMAT (JSON, no markdown fences):
{
  "core_claim": "the central statement or research question, one sentence",
  "key_definitions": ["def1", "def2"],
  "definitions_order": ["which definitions depend on which"],
  "lemmas_needed": ["lemma1 — brief description"],
  "proof_strategy": "suggested approach, 2-3 sentences max",
  "expected_connections": ["connection to other area — why it might appear"],
  "chunks": [
    {"id": "chunk_id", "title": "short title", "description": "one sentence"}
  ],
  "scout_priority": "which chunk to examine first in scout mode — id"
}

CONSTRAINTS:
- Chunks should map to logical units: one definition, one lemma, one proof step, one remark
- 4-8 chunks for a typical topic
- 500 tokens max total output
```

**Output tokens:** ~400

---

### 4.3 Rep (Developer)

**Role:** Develops the mathematical content. Receives the orchestrator's directive and
updates the current chunk. May push back on the directive with a brief mathematical reason.
Works chunk by chunk, not on the whole document.

**Key behavioral note:** The Rep can and should push back when it has a strong reason.
This is desirable — it surfaces disagreements explicitly for the orchestrator to adjudicate.
Pushback should be brief: one sentence explaining the mathematical reason.

**Skills loaded:**
- `skills/rep/proof_scaffolder.md`

**System prompt structure:**
```
TASK:
Update the current chunk of the mathematical manuscript based on the orchestrator's directive.
Write in standard mathematical exposition: Definition / Theorem / Proof / Remark format.
Use unicode math symbols (∀, ∃, →, ⊗, ∈, ⊂, etc.) for readability.

INPUTS YOU RECEIVE:
- State object (established results, open flags, round goal)
- Current chunk text (what exists so far)
- Orchestrator directive (a suggestion — you may push back)
- Your own memory (what you tried before, what worked)

OUTPUT FORMAT:
---CHUNK---
[complete updated chunk text]
---END CHUNK---

PUSHBACK (only if you disagree with the directive, otherwise omit):
[one sentence: the mathematical reason you are not following the directive]

MEMORY NOTE:
[one short bullet for your own memory — what you tried, what you established]

CONSTRAINTS:
- Output the complete chunk text, not a diff
- 600 tokens max for chunk content
- If you are approaching the token limit, sketch the remaining steps explicitly:
  "Remaining: (1) verify X, (2) handle edge case Y — details deferred"
  Do not truncate silently.
- Do not rewrite chunks that are already APPROVED
```

**Output tokens:** ~700 (chunk content + optional pushback + memory note)

---

### 4.4 Logic Critic

**Role:** Find logical errors in the current chunk. Terse. One line per issue.
No explanation unless the issue is subtle. A "?" is a valid output.

**Skills loaded:**
- `skills/logic_critic/error_taxonomy.md`

**System prompt structure:**
```
TASK:
Find logical errors in the current chunk. Check against the error taxonomy.

INPUTS YOU RECEIVE:
- State object (focus chunk text, established results)
- Your memory (what you already flagged in prior rounds — do not repeat resolved flags)

OUTPUT FORMAT:
One line per issue:
  [location] [error type] [brief note]

Examples:
  Thm 2, step 3: missing assumption — f needs to be continuous at p
  Def 1: quantifier order — ∀x∃y should be ∃y∀x here
  Lemma 1, proof: ?  (flag for ambiguity, no clear error but something feels off)
  ok  (if no issues found)

MEMORY NOTE:
[one bullet: what you checked, what you cleared]

CONSTRAINTS:
- 150 tokens max output
- Do not repeat flags you already raised in prior rounds unless they are still unresolved
- Do not explain what logical errors are. Just find them.
- "ok" is a complete and valid output
- Use the error taxonomy from your skills as a checklist
```

**Output tokens:** ~150

**Error taxonomy (skills/logic_critic/error_taxonomy.md) should include:**
- Implicit assumption (unstated hypothesis)
- Quantifier error (∀/∃ confusion, scope error)
- Non-constructive step (existence claimed without construction or citation)
- Circular reasoning (conclusion used in proof)
- Gap in deduction (step A to step B not justified)
- Incorrect theorem application (hypothesis of cited theorem not verified)
- Type error (applying operation to wrong mathematical object)
- Edge case omitted (boundary, empty set, zero case)
- Induction error (base case missing, inductive step wrong)

---

### 4.5 Counterexample Hunter

**Role:** Find an easy counterexample to the main claim or any sub-claim.
Hard constraint: if a counterexample cannot be constructed in ≤3 steps, stop and report.
This is a quick sanity filter, not a research effort.

**System prompt structure:**
```
TASK:
Attempt to find a counterexample to the main claim or any sub-claim in the current chunk.

INPUTS YOU RECEIVE:
- State object (focus chunk, established results)
- Your memory (what cases you already tried)

METHOD:
1. State the claim you are testing
2. Try: edge cases, degenerate objects, small finite cases, classical counterexamples
3. If you find one in ≤3 steps: report it
4. If not: stop

OUTPUT FORMAT:
If found:
  COUNTEREXAMPLE FOUND
  Claim tested: [claim]
  Counterexample: [explicit construction, ≤3 lines]
  Why it breaks the claim: [one sentence]

If not found:
  No quick counterexample.
  Tried: [comma-separated list of cases attempted]

MEMORY NOTE:
[one bullet: cases tried this round]

CONSTRAINTS:
- 150 tokens max output
- Do NOT attempt complicated counterexamples. Easy ones only.
- If you cannot find one in 3 attempts, stop. Write "No quick counterexample."
- A counterexample you are unsure about should be flagged as a QUESTION, not reported as found.
```

**Output tokens:** ~150

---

### 4.6 Reference Critic

**Role:** Check the literature. Has this been done? Are citations correct? Find surprising
cross-domain connections (these trigger the SERENDIPITY stopping signal).
Uses web search when available.

**Skills loaded:**
- `skills/reference/search_strategy.md`

**System prompt structure:**
```
TASK:
Check the mathematical literature relevant to the current chunk.

INPUTS YOU RECEIVE:
- State object (focus chunk, topic)
- Your memory (what you already searched and found)

CHECK FOR:
1. Prior art: has this claim been proven before? By whom? Roughly when?
2. Citation correctness: are any cited theorems correctly attributed?
3. Better references: standard references the Rep should know about
4. CROSS-DOMAIN CONNECTIONS: unexpected links to other areas of mathematics.
   These are the most valuable finding. Flag them prominently.
5. Novelty: does anything appear genuinely new?

OUTPUT FORMAT:
PRIOR ART: [name, date, brief note — or "none found"]
CORRECTIONS: [list of citation issues — or "none"]
CONNECTIONS: [any cross-domain links — be specific about what connects to what]
NOVEL: yes / no / unclear

MEMORY NOTE:
[one bullet: what you searched]

CONSTRAINTS:
- 250 tokens max output
- Do not repeat searches you already did (check your memory)
- If you find a cross-domain connection, mark it with !! so the orchestrator flags it
- "none found" is a complete and valid output for any section
```

**Output tokens:** ~250
**Uses web search:** yes (configured in base agent)

**search_strategy skill should include:**
- Search the claim itself first (exact wording)
- Search the author + field if a name is mentioned
- Search the key technique (not just the result)
- Search for the dual / generalization of the result
- Cross-domain check: run the claim through adjacent fields

---

### 4.7 Elegance Critic

**Role:** Evaluate mathematical beauty. Suggest improvements. Give a score.
Note anything that could be generalized or simplified.

**System prompt structure:**
```
TASK:
Evaluate the mathematical elegance of the current chunk.

INPUTS YOU RECEIVE:
- State object (focus chunk)
- Your memory (your assessment from prior rounds)

ASSESS:
- Minimality: is the proof longer than it needs to be?
- Illumination: does it explain WHY, not just THAT?
- Generality: does it prove something weaker than what the method would give?
- Surprise: does it use any unexpected tools or connections?
- Unity: does it reveal something deep about the structure?

OUTPUT FORMAT:
SCORE: [1-10]
ISSUES: [one line per issue, or "none"]
SUGGESTIONS: [one line per suggestion, or "none"]

MEMORY NOTE:
[one bullet: score history and main concern]

CONSTRAINTS:
- 200 tokens max output
- Be specific. "Step 3 could use the universal property directly, eliminating the explicit construction" not "the proof could be cleaner"
- Score honestly. 5 is average. 8+ means genuinely beautiful.
- Do not repeat suggestions from prior rounds that have already been addressed.
```

**Output tokens:** ~200

---

## 5. Session Modes

### 5.1 Scout Mode

Purpose: quickly evaluate whether an idea is worth pursuing.
Cost: ~1 round × 4 agents = cheap.
Output: a verdict + a brief assessment.

**Agents called:** Orchestrator (brief only) → Decomposer → Rep (first draft) → Logic Critic → Counterexample Hunter → Orchestrator (verdict)

**Reference and Elegance critics do NOT run in scout mode.**

**Orchestrator scout verdict prompt addition:**
```
SCOUT MODE: After reviewing the logic and counterexample reports, add to your output:
  "scout_verdict": "PURSUE | DROP | INTERESTING"
  "scout_reason": "2 sentences max"

PURSUE: claim appears sound, no obvious counterexample, worth developing
DROP: claim is false (counterexample found) or trivially wrong
INTERESTING: unclear, ambiguous, or requires more context before deciding
```

**Loop:**
```python
async def run_scout(topic: str, config: Config) -> ScoutResult:
    decomp = await decomposer.call(topic)
    first_chunk = decomp.chunks[0]  # scout_priority chunk
    state = build_initial_state(decomp, first_chunk)
    
    rep_output = await rep.call(state, memory)
    logic_flags = await logic_critic.call(state, memory)
    counterex_result = await counterex.call(state, memory)
    
    verdict = await orchestrator.scout_verdict(state, rep_output, logic_flags, counterex_result)
    return ScoutResult(verdict=verdict, decomp=decomp, draft=rep_output)
```

### 5.2 Deep Mode

Purpose: develop a topic fully, chunk by chunk, with all agents.
Starts from a clean decomposition or from an existing scout result.

**Loop:**
```python
async def run_deep(topic: str, config: Config, prior_scout: Optional[ScoutResult] = None):
    if prior_scout:
        manuscript = build_from_scout(prior_scout)
    else:
        decomp = await decomposer.call(topic)
        manuscript = build_manuscript(decomp)
    
    for chunk in manuscript.chunks:
        if chunk.status == ChunkStatus.APPROVED:
            continue
        
        round_num = 0
        while round_num < config.max_rounds_per_chunk:
            state = build_round_state(manuscript, chunk, round_num)
            
            rep_output      = await rep.call(state, memories["rep"])
            logic_flags     = await logic_critic.call(state, memories["logic"])
            counterex       = await counterex.call(state, memories["counterex"])
            ref_notes       = await reference.call(state, memories["reference"])
            elegance_notes  = await elegance.call(state, memories["elegance"])
            
            orch_output = await orchestrator.synthesize(
                state, rep_output, logic_flags, counterex, ref_notes, elegance_notes,
                memories["orchestrator"]
            )
            
            update_manuscript(manuscript, chunk, orch_output, rep_output)
            update_all_memories(memories, orch_output, round_num)
            save_session(manuscript, state, memories)
            display_round(orch_output, round_num)
            
            signal = orch_output.stopping_signal
            if signal == StoppingSignal.COUNTEREXAMPLE:
                hard_stop(signal, orch_output.stopping_reason)
                return
            if signal in (StoppingSignal.SERENDIPITY,):
                pause_and_surface(signal, orch_output.stopping_reason)
                if not user_wants_to_continue():
                    return
            if signal in (StoppingSignal.CONVERGED, StoppingSignal.ELEGANT):
                chunk.status = ChunkStatus.APPROVED
                break
            if signal == StoppingSignal.INCUBATE:
                save_and_pause(manuscript)
                return
            
            round_num += 1
            
            # Check for user interjection
            note = check_for_user_note()
            if note:
                inject_note_into_next_round(note, state)
        
        manuscript.global_context = update_global_context(manuscript)
```

**Agent call order within a round (sequential, no concurrency):**
1. Rep
2. Logic Critic
3. Counterexample Hunter
4. Reference Critic
5. Elegance Critic
6. Orchestrator (reads all five outputs)

Sequential to stay within API concurrency limits.

---

## 6. Token Budget & Efficiency

### Per-round budget (deep mode, one chunk)

| Agent            | Input (tokens) | Output (tokens) |
|------------------|---------------|-----------------|
| Rep              | ~1050         | ~700            |
| Logic Critic     | ~700          | ~150            |
| Counterex Hunter | ~700          | ~150            |
| Reference Critic | ~750          | ~250            |
| Elegance Critic  | ~700          | ~200            |
| Orchestrator     | ~2200*        | ~400            |
| **Total**        | **~6100**     | **~1850**       |

*Orchestrator input includes all five agent outputs from this round.

**Cost per round at Sonnet 4.6 rates ($3/$15 per MTok):**
- Input: 6100 × $3/1M = ~$0.018
- Output: 1850 × $15/1M = ~$0.028
- **Total: ~$0.046 per round**

**Typical session cost estimates:**
- Scout (1 round, 4 agents): ~$0.015
- Deep, 4 chunks × 3 rounds: ~$0.55
- Deep, 8 chunks × 4 rounds: ~$1.47

### Strategies for staying within budget

1. **Chunk boundary discipline.** Orchestrator should advance chunks when converged.
   Do not keep reviewing an approved chunk.

2. **Memory compression.** After 10 memory entries per agent, compress the oldest 5 into
   a single summary bullet. Never let memory exceed ~200 tokens.

3. **Global context.** When a chunk is approved, its content is compressed into the global
   context (3-5 bullet points). Subsequent agent calls receive the global context, not the
   full chunk text of approved chunks.

4. **Skip elegance in scout.** Elegance critic is the most expensive-per-useful-output
   in early rounds. Skip in scout mode, run every other round in deep mode for short sessions.

5. **Output constraints are hard.** Every agent prompt includes a hard token limit.
   Agents are instructed to sketch rather than truncate silently.

---

## 7. Skills as Prompt Modules

Skills are markdown files loaded by agents at runtime and appended to their system prompt.
They are not code — they are structured reference material.

### skills/orchestrator/chunk_splitter.md
Instructions for identifying logical chunk boundaries:
- Each chunk should contain exactly one mathematical claim (definition, lemma, theorem, corollary, remark)
- A proof is a separate chunk from its theorem
- Definitions that are purely standard can be grouped into one "definitions" chunk
- A remark connecting to another field is always its own chunk (serendipity surface point)
- Typical chunk size: 150-400 tokens

### skills/orchestrator/decision_logic.md
Decision rules for stopping signals and chunk advancement:
- Counterexample: must be explicit and verifiable, not speculative
- Serendipity: connection must be to a genuinely different field (algebra↔topology OK, two algebra results NOT)
- Convergence: requires 2 consecutive rounds with zero new flags across all critics
- Advancement: chunk advances when: all flags resolved AND logic ok AND no counterexample
- Incubation: trigger after 3 rounds where the set of open flags did not change

### skills/orchestrator/state_builder.md
Schema and instructions for building the RoundState JSON.
Include: how to compress established results into bullets, how to rank priority issues,
how to phrase the directive to Rep as a suggestion rather than a command.

### skills/logic_critic/error_taxonomy.md
Full taxonomy of logical error types (see section 4.4 above).
Formatted as a checklist: "Check for X: [description of what X looks like in a proof]"

### skills/rep/proof_scaffolder.md
Standard structure for mathematical exposition:
- Definition format: Definition N (name). [statement]. ☐ or [end marker]
- Theorem format: Theorem N. [statement]. Proof. [steps]. □
- Lemma format: same as theorem
- Remark format: Remark. [observation, connection, or caveat].
- Notation conventions: always define notation before use, ∀ before ∃, etc.
- Sketch convention: if approaching token limit, write "Sketch: (1)... (2)... (3)..."

### skills/reference/search_strategy.md
How to structure a literature check:
- First: search the exact claim (is it a known theorem?)
- Second: search the technique being used (not just the result)
- Third: search for the generalization (what does this specialize from?)
- Fourth: cross-domain check — run the claim through adjacent fields explicitly
- Flag with !! any connection to a field not mentioned in the original topic

---

## 8. Memory Model

### Storage

One JSON file per agent per session:
`sessions/{session_id}/memory/{agent_id}.json`

```json
{
  "agent_id": "logic_critic",
  "session_id": "abc123",
  "entries": [
    {"round": 1, "chunk_id": "lemma_1", "note": "Flagged: missing continuity assumption step 2"},
    {"round": 2, "chunk_id": "lemma_1", "note": "Continuity resolved. Cleared."},
    {"round": 3, "chunk_id": "proof_main", "note": "Step 4 quantifier order suspicious — flagged"}
  ]
}
```

### Compression

When entries exceed 15, compress oldest 10 into one summary entry:
```json
{"round": "1-10 summary", "chunk_id": "various", "note": "Chunks 1-3 approved. Main issue: proof_main step 4 quantifier."}
```

### Serialization for agent calls

Memory is serialized as a compact bulleted list appended to the user message:
```
YOUR MEMORY (prior rounds):
• R1 lemma_1: Flagged missing continuity assumption step 2
• R2 lemma_1: Continuity resolved. Cleared.
• R3 proof_main: Step 4 quantifier order suspicious — flagged
```

---

## 9. Session Persistence & CLI

### Session storage

Each session lives in `sessions/{session_id}/`:
```
sessions/abc123/
├── session.json        # Full serialized Manuscript + current RoundState
├── memory/
│   ├── orchestrator.json
│   ├── rep.json
│   ├── logic_critic.json
│   ├── counterex.json
│   ├── reference.json
│   └── elegance.json
└── export/
    └── manuscript.md   # Human-readable export, updated after each round
```

Session is saved after every agent call, not just after every round.
If the process crashes mid-round, it can resume from the last saved state.

### CLI interface

```bash
# Start a new session
python main.py --topic "the residue theorem in singularity theory in algebraic geometry"

# Start in scout mode
python main.py --topic "X" --mode scout

# Resume an existing session
python main.py --session abc123

# Resume and inject a note for the next round
python main.py --session abc123 --note "check the case of isolated singularities specifically"

# Export a session's manuscript to markdown
python main.py --session abc123 --export

# List recent sessions
python main.py --list

# Inspect a specific session without running
python main.py --session abc123 --inspect
```

### Runtime user input

While a session is running, the user can type at any point:
- `n <note>` — queue a note for the Rep in the next round
- `s` — stop after the current agent completes
- `skip` — skip the current chunk, mark as ABANDONED, move to next
- `q` — stop immediately, save state

This requires async input handling (use `aioconsole` or run input in a thread).

---

## 10. Output & Display

Use the `rich` library for terminal output.

### Per-round display structure

```
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
ROUND 2 — Lemma 1 (Residue at Isolated Singularity)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

◎ REP
[chunk content, formatted]

⊗ LOGIC        [2 flags]
  Thm 1, step 3: missing assumption — holomorphicity on D \ {p}
  Def 2: ? (scope of ε unclear)

⊘ COUNTEREX
  No quick counterexample. Tried: unit disk, half-plane, punctured torus.

⊞ REFERENCE
  PRIOR ART: Grothendieck (1958) — residues via duality, more general
  CONNECTIONS: !! links to local cohomology — Hartshorne Ch III
  NOVEL: the specific framing appears non-standard

◈ ELEGANCE     [score: 6]
  Step 2 could invoke the residue formula directly rather than re-deriving
  Generalization available: works for any coherent sheaf, not just O_X

◎ ORCHESTRATOR
  Synthesis: Logic has two real issues; reference suggests Grothendieck's
  framework subsumes this — worth incorporating. Elegance ok for a draft.
  
  Open: holomorphicity assumption, ε scope
  To Rep: Address the two logic flags. Consider citing Grothendieck duality
  for the main result — the Rep can push back if there's a reason not to.
  
  Signal: CONTINUE

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
```

### Stopping signal display

```
┌─────────────────────────────────────────────┐
│  ✦  SERENDIPITY                              │
│                                              │
│  Reference critic found unexpected link to  │
│  local cohomology (Hartshorne Ch III).       │
│  This may generalize the result significantly.│
│                                              │
│  Continue? [y/n]                             │
└─────────────────────────────────────────────┘
```

---

## 11. Configuration

`config.py` — all tunable parameters in one place:

```python
@dataclass
class Config:
    # Model
    model: str = "claude-sonnet-4-5-20251001"   # or opus for deeper sessions
    
    # Token budgets (max output per agent call)
    max_tokens_rep:          int = 700
    max_tokens_logic:        int = 150
    max_tokens_counterex:    int = 150
    max_tokens_reference:    int = 250
    max_tokens_elegance:     int = 200
    max_tokens_orchestrator: int = 400
    max_tokens_decomposer:   int = 400
    
    # Loop limits
    max_rounds_per_chunk:    int = 4
    max_chunks_per_session:  int = 8
    convergence_rounds:      int = 2   # rounds with no new flags → CONVERGED
    incubation_rounds:       int = 3   # rounds with same flags → INCUBATE
    
    # Memory
    max_memory_entries:      int = 15
    memory_compress_to:      int = 5
    
    # Modes
    default_mode: SessionMode = SessionMode.SCOUT
    
    # Rate limiting
    request_delay_seconds:   float = 0.5   # delay between agent calls
    
    # Display
    show_chunk_on_update:    bool = True
    verbose:                 bool = False   # show full agent outputs vs summaries
```

---

## 12. Dependencies

```
anthropic>=0.20.0
rich>=13.0.0
aioconsole>=0.6.0     # async terminal input
click>=8.0.0          # CLI
python-dotenv>=1.0.0  # for ANTHROPIC_API_KEY in .env
pydantic>=2.0.0       # data model validation
```

`ANTHROPIC_API_KEY` loaded from `.env` file or environment.

---

## 13. Future Extensions (out of scope for v1)

These are architectural placeholders — the system should not implement them in v1
but should not make decisions that would prevent them.

### Lean/Coq formalization gateway
An 8th agent that attempts to translate a completed chunk into Lean 4 syntax.
Runs only on chunks marked APPROVED, only when explicitly requested.
Output is a sketch, not verified code — but forces hidden gaps to surface.

### Aesthetic scoring history
Track elegance scores across rounds per chunk. Plot them. A score that stops
improving after round 2 is a signal the approach may be fundamentally inelegant.

### Cross-session memory
Orchestrator-level memory that persists across sessions on the same topic or field.
"We've tried this approach before and it hit the same wall at lemma 3."

### Vector search over sessions
Index all session manuscripts. When starting a new session, automatically retrieve
the 3 most similar past sessions and include their outcomes in the orchestrator's context.

### Multi-topic orchestration
A meta-orchestrator that manages multiple parallel sessions (one per idea),
runs them in scout mode, and surfaces the most promising for deep mode.
This models the "billion ideas" workflow more faithfully.

---

## 14. Design Decisions Log

These are decisions made during design discussion that future maintainers should understand.

| Decision | Rationale |
|----------|-----------|
| Sequential agent calls (no parallelism) | API concurrency limits; also more readable output |
| Chunk-based document model | Full-document passing hits token limits fast; chunks scale linearly |
| State object as shared medium | Agents need context, not the whole manuscript |
| No agent personas | Task + format + constraints produces more predictable output than role-play |
| Counterexample hunter has hard step limit | Finding hard counterexamples is PhD-level work, not a quick filter |
| Two modes (scout / deep) | Matches the actual workflow: filter ideas fast, then develop survivors |
| Stopping signals include serendipity | Cross-domain connections are valuable findings, not just completion criteria |
| INCUBATE as a stopping signal | Poincaré's incubation stage — being stuck is a signal to pause, not fail |
| Orchestrator suggestions, not commands | Rep's pushback is productive; the tension surfaces disagreements explicitly |
| Skills as markdown files | Modular, human-editable, version-controllable prompt components |
| Memory per agent, not shared | Agents should not see each other's reasoning across rounds, only the state object |
| Session saved after every agent call | Crash recovery; long sessions are expensive to re-run |
| Elegance as a stopping criterion | Wiles: "you find this thing, suddenly you see the beauty of the landscape" — this is real |

---

## 15. Implementation Notes for Claude Code

1. **Start with models/**, then **agents/base.py**, then one full agent (orchestrator),
   then the scout loop. Get one end-to-end run working before implementing all agents.

2. **Test with a simple topic first** (e.g., "prove that √2 is irrational") before
   the full residue theorem session. The loop logic is easier to debug with a known result.

3. **The orchestrator's JSON parsing must have a fallback.** Claude sometimes wraps JSON
   in markdown fences despite instructions. Strip them before parsing. If parsing fails,
   log the raw output and default to CONTINUE with the raw output as the synthesis string.

4. **Display is important.** The rich terminal output is not cosmetic — it's how the user
   reads the session in real time. Implement it early, not as an afterthought.

5. **The `.env` file should contain:** `ANTHROPIC_API_KEY=sk-...`
   Do not hardcode the key anywhere.

6. **Error handling:** API errors should be caught per agent call. A failed agent call
   should produce a graceful empty output (e.g., logic critic returns "error — skipped")
   rather than crashing the round. The orchestrator handles missing agent outputs gracefully.

7. **The `--inspect` CLI flag** is very useful for debugging: dumps the full session state
   without running any agents. Implement early.

8. **Prompts are in the agent files, not in a separate prompts/ directory.** Each agent
   owns its prompt. Skills are the shared/reusable parts.
```

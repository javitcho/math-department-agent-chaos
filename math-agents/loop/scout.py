"""
Scout mode loop.

One-pass, verdict-only. Runs Decomposer → Rep → Logic Critic → Counterex → Orchestrator.
Reference and Elegance critics do NOT run in scout mode.
"""

import uuid
from datetime import datetime
from typing import Optional

from config import Config
from agents.decomposer import DecomposerAgent
from agents.rep import RepAgent
from agents.logic_critic import LogicCriticAgent
from agents.counterex import CounterexAgent
from agents.orchestrator import OrchestratorAgent
from models.document import Chunk, Manuscript
from models.signals import ChunkStatus, SessionMode, StoppingSignal
from models.state import AgentMemory, RoundState
from storage.session_store import save_session
from storage.memory_store import load_memory, save_memory, append_memory_entry
from output.display import (
    display_scout_result,
    display_info,
    display_warning,
)


def run_scout(topic: str, config: Config, session_id: Optional[str] = None) -> dict:
    """
    Run scout mode on a topic.

    Returns a dict with:
      verdict, scout_reason, decomp, rep_output, logic_flags,
      counterex_result, orch_output, manuscript, session_id
    """
    if session_id is None:
        session_id = str(uuid.uuid4())[:8]

    display_info(f"[Scout] Starting session {session_id} — topic: {topic}")

    # ------------------------------------------------------------------
    # Step 1: Decompose the topic
    # ------------------------------------------------------------------
    decomposer = DecomposerAgent(config)
    display_info("[Scout] Running decomposer...")

    try:
        decomp = decomposer.decompose(topic)
    except Exception as e:
        display_warning(f"Decomposer failed: {e}")
        decomp = {
            "core_claim": topic,
            "chunks": [{"id": "main_claim", "title": "Main Claim", "description": topic}],
            "scout_priority": "main_claim",
            "key_definitions": [],
            "lemmas_needed": [],
            "proof_strategy": "",
            "expected_connections": [],
        }

    # ------------------------------------------------------------------
    # Step 2: Build initial manuscript from decomposition
    # ------------------------------------------------------------------
    chunks_data = decomp.get("chunks", [{"id": "main_claim", "title": "Main Claim", "description": topic}])
    scout_priority = decomp.get("scout_priority", chunks_data[0]["id"] if chunks_data else "main_claim")

    # Create Chunk objects
    all_chunks = []
    for cd in chunks_data:
        all_chunks.append(Chunk(
            id=cd["id"],
            title=cd["title"],
            content=cd.get("description", ""),
            status=ChunkStatus.DRAFT,
            round_created=0,
            round_last_modified=0,
            flags=[],
            approved_by_rounds=0,
        ))

    # Find the scout priority chunk
    focus_chunk = next((c for c in all_chunks if c.id == scout_priority), all_chunks[0])

    manuscript = Manuscript(
        topic=topic,
        mode=SessionMode.SCOUT,
        chunks=all_chunks,
        current_chunk_id=focus_chunk.id,
        global_context="",
        session_id=session_id,
        created_at=datetime.now(),
    )

    # ------------------------------------------------------------------
    # Step 3: Build initial RoundState
    # ------------------------------------------------------------------
    established = []
    # Add core claim and key definitions to established if available
    if decomp.get("core_claim"):
        established.append(f"Core claim: {decomp['core_claim']}")
    for defn in decomp.get("key_definitions", [])[:3]:
        established.append(f"Definition: {defn}")

    state = RoundState(
        round=1,
        mode=SessionMode.SCOUT,
        established=established,
        current_chunk_id=focus_chunk.id,
        current_chunk_title=focus_chunk.title,
        focus_text=focus_chunk.content,
        open_flags=[],
        round_goal=f"Scout: evaluate the core claim — '{decomp.get('core_claim', topic)}'",
        directive_for_rep="Write a first draft of this chunk. Be concise and mathematically precise.",
    )

    # Initialize memories
    memories = {
        agent_id: AgentMemory(agent_id=agent_id, session_id=session_id, entries=[])
        for agent_id in ["rep", "logic_critic", "counterex", "orchestrator", "decomposer"]
    }

    # ------------------------------------------------------------------
    # Step 4: Rep
    # ------------------------------------------------------------------
    rep_agent = RepAgent(config)
    display_info("[Scout] Running Rep...")

    try:
        rep_output = rep_agent.call(state, memories["rep"])
        # Update chunk content from rep output
        chunk_content = rep_agent.extract_chunk_content(rep_output)
        focus_chunk.content = chunk_content
        focus_chunk.status = ChunkStatus.UNDER_REVIEW
        focus_chunk.round_last_modified = 1
        state.focus_text = chunk_content
        # Update memory
        mem_note = rep_agent.extract_memory_note(rep_output)
        memories["rep"] = append_memory_entry("rep", session_id, 1, focus_chunk.id, mem_note or "Initial draft written")
    except Exception as e:
        display_warning(f"Rep failed: {e}")
        rep_output = f"error — skipped: {e}"

    # Save after rep
    save_session(manuscript, state, memories)

    # ------------------------------------------------------------------
    # Step 5: Logic Critic
    # ------------------------------------------------------------------
    logic_agent = LogicCriticAgent(config)
    display_info("[Scout] Running Logic Critic...")

    try:
        logic_flags = logic_agent.call(state, memories["logic_critic"])
        memories["logic_critic"] = append_memory_entry(
            "logic_critic", session_id, 1, focus_chunk.id,
            f"Scout round: {logic_flags[:80]}"
        )
    except Exception as e:
        display_warning(f"Logic Critic failed: {e}")
        logic_flags = f"error — skipped: {e}"

    # Save after logic critic
    save_session(manuscript, state, memories)

    # ------------------------------------------------------------------
    # Step 6: Counterexample Hunter
    # ------------------------------------------------------------------
    counterex_agent = CounterexAgent(config)
    display_info("[Scout] Running Counterexample Hunter...")

    try:
        counterex_result = counterex_agent.call(state, memories["counterex"])
        memories["counterex"] = append_memory_entry(
            "counterex", session_id, 1, focus_chunk.id,
            f"Scout: {counterex_result[:80]}"
        )
    except Exception as e:
        display_warning(f"Counterex Hunter failed: {e}")
        counterex_result = f"error — skipped: {e}"

    # Save after counterex
    save_session(manuscript, state, memories)

    # ------------------------------------------------------------------
    # Step 7: Orchestrator (scout mode — produces verdict)
    # ------------------------------------------------------------------
    orch_agent = OrchestratorAgent(config)
    display_info("[Scout] Running Orchestrator (scout verdict)...")

    try:
        orch_output = orch_agent.synthesize(
            state=state,
            memory=memories["orchestrator"],
            rep_output=rep_output,
            logic_flags=logic_flags,
            counterex_result=counterex_result,
            ref_notes="(not run — scout mode)",
            elegance_notes="(not run — scout mode)",
            scout_mode=True,
        )
        mem_note = orch_output.get("memory_note", "")
        memories["orchestrator"] = append_memory_entry(
            "orchestrator", session_id, 1, focus_chunk.id,
            mem_note or f"Scout verdict: {orch_output.get('scout_verdict', '?')}"
        )
    except Exception as e:
        display_warning(f"Orchestrator failed: {e}")
        orch_output = {
            "stopping_signal": StoppingSignal.SCOUT_INTERESTING,
            "stopping_reason": f"Orchestrator error: {e}",
            "scout_verdict": "INTERESTING",
            "scout_reason": "Could not evaluate — orchestrator error.",
            "open_flags": [],
            "established": established,
            "directive_for_rep": "",
            "round_goal": "",
            "priority_issues": [],
            "advance_chunk": False,
            "memory_note": "",
        }

    # Update state with orchestrator output
    state.stopping_signal = orch_output.get("stopping_signal", StoppingSignal.SCOUT_INTERESTING)
    state.stopping_reason = orch_output.get("stopping_reason", "")
    state.open_flags = orch_output.get("open_flags", [])
    state.scout_verdict = orch_output.get("scout_verdict")

    # Update chunk flags
    focus_chunk.flags = state.open_flags

    # Save final scout state
    save_session(manuscript, state, memories)

    # ------------------------------------------------------------------
    # Step 8: Display results
    # ------------------------------------------------------------------
    display_scout_result(
        topic=topic,
        decomp=decomp,
        rep_output=rep_output,
        logic_flags=logic_flags,
        counterex_result=counterex_result,
        orch_output=orch_output,
    )

    # ------------------------------------------------------------------
    # Step 9: Return result dict
    # ------------------------------------------------------------------
    verdict = orch_output.get("scout_verdict", "INTERESTING")
    # Map scout verdict to stopping signal
    signal_map = {
        "PURSUE": StoppingSignal.SCOUT_PURSUE,
        "DROP": StoppingSignal.SCOUT_DROP,
        "INTERESTING": StoppingSignal.SCOUT_INTERESTING,
    }
    final_signal = signal_map.get(verdict, StoppingSignal.SCOUT_INTERESTING)

    return {
        "verdict": verdict,
        "scout_reason": orch_output.get("scout_reason", ""),
        "stopping_signal": final_signal,
        "decomp": decomp,
        "rep_output": rep_output,
        "logic_flags": logic_flags,
        "counterex_result": counterex_result,
        "orch_output": orch_output,
        "manuscript": manuscript,
        "session_id": session_id,
        "memories": memories,
    }

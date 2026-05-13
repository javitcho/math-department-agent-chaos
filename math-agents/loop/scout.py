"""
Scout mode loop.

One-pass, verdict-only. Runs Decomposer → Rep → Logic Critic → Counterex → Orchestrator.
Reference and Elegance critics do NOT run in scout mode.
"""

import uuid
import copy
from datetime import datetime
from typing import Optional

from config import Config
from agents.decomposer import DecomposerAgent
from agents.rep import RepAgent
from agents.logic_critic import LogicCriticAgent
from agents.counterex import CounterexAgent
from agents.orchestrator import OrchestratorAgent
from models.document import ChunkNode, Manuscript
from models.signals import ChunkStatus, ChunkType, SessionMode, StoppingSignal
from models.state import AgentMemory, RoundState
from storage.session_store import save_session
from storage.memory_store import load_memory, save_memory, append_memory_entry
from output.display import (
    display_scout_result,
    display_info,
    display_warning,
)


def run_scout(topic: str, config: Config, session_id: Optional[str] = None, scope=None) -> dict:
    """
    Run scout mode on a topic.

    Returns a dict with:
      verdict, scout_reason, decomp, rep_output, logic_flags,
      counterex_result, orch_output, manuscript, session_id
    """
    if session_id is None:
        session_id = str(uuid.uuid4())[:8]

    config = copy.copy(config)
    config.max_tokens_rep          = config.scout_max_tokens_rep
    config.max_tokens_logic        = config.scout_max_tokens_logic
    config.max_tokens_counterex    = config.scout_max_tokens_counterex
    config.max_tokens_orchestrator = config.scout_max_tokens_orchestrator

    display_info(f"[Scout] Starting session {session_id} — topic: {topic}")

    # ------------------------------------------------------------------
    # Step 1: Decompose
    # ------------------------------------------------------------------
    decomposer = DecomposerAgent(config)
    display_info("[Scout] Running decomposer...")

    try:
        decomp = decomposer.decompose(topic)
    except Exception as e:
        display_warning(f"Decomposer failed: {e}")
        decomp = {
            "title": topic,
            "nodes": [{"id": "main_claim", "title": "Main Claim",
                        "type": "section", "description": topic, "depends_on": []}],
            "global_context": "",
            "scout_priority": "main_claim",
        }

    # ------------------------------------------------------------------
    # Step 2: Build graph and pick scout priority node
    # ------------------------------------------------------------------
    try:
        graph = decomposer.build_nodes(decomp)
        nodes = graph["nodes"]
        traversal_order = graph["traversal_order"]
        global_context = graph["global_context"]
    except Exception as e:
        display_warning(f"Graph build failed: {e}")
        fallback_id = "main_claim"
        fallback_node = ChunkNode(
            id=fallback_id, title="Main Claim", content=topic,
            type=ChunkType.SECTION, status=ChunkStatus.DRAFT,
            depends_on=[], dependents=[], round_created=0, round_last_modified=0,
        )
        nodes = {fallback_id: fallback_node}
        traversal_order = [fallback_id]
        global_context = ""

    scout_priority = decomp.get("scout_priority", traversal_order[0] if traversal_order else "main_claim")
    if scout_priority not in nodes:
        scout_priority = traversal_order[0] if traversal_order else list(nodes.keys())[0]

    focus_node = nodes[scout_priority]
    focus_node.status = ChunkStatus.UNDER_REVIEW

    manuscript = Manuscript(
        topic=topic,
        mode=SessionMode.SCOUT,
        nodes=nodes,
        traversal_order=traversal_order,
        current_chunk_id=scout_priority,
        global_context=global_context,
        session_id=session_id,
        created_at=datetime.now(),
        scope=scope,
    )

    # ------------------------------------------------------------------
    # Step 3: Build RoundState
    # ------------------------------------------------------------------
    state = RoundState(
        round=1,
        mode=SessionMode.SCOUT,
        established=[f"Core claim: {decomp.get('title', topic)}"],
        current_chunk_id=scout_priority,
        current_chunk_title=focus_node.title,
        focus_text=focus_node.content,
        open_flags=[],
        round_goal=f"Scout: evaluate the core claim — '{decomp.get('title', topic)}'",
        directive_for_rep="Write a first draft of this chunk. Be concise and mathematically precise.",
        scope=scope,
    )

    memories = {
        agent_id: AgentMemory(agent_id=agent_id, session_id=session_id, entries=[])
        for agent_id in ["rep", "logic_critic", "counterex", "orchestrator", "decomposer"]
    }

    ms_extra = {"manuscript": manuscript}

    # ------------------------------------------------------------------
    # Step 4: Rep
    # ------------------------------------------------------------------
    rep_agent = RepAgent(config)
    display_info("[Scout] Running Rep...")

    try:
        rep_output = rep_agent.call(state, memories["rep"], extra=ms_extra)
        chunk_content, _ = rep_agent.apply_rep_output(rep_output, focus_node.content or "")
        focus_node.content = chunk_content
        focus_node.status = ChunkStatus.UNDER_REVIEW
        focus_node.round_last_modified = 1
        state.focus_text = chunk_content
        mem_note = rep_agent.extract_memory_note(rep_output)
        memories["rep"] = append_memory_entry("rep", session_id, 1, scout_priority,
                                               mem_note or "Initial draft written")
    except Exception as e:
        display_warning(f"Rep failed: {e}")
        rep_output = f"error — skipped: {e}"

    save_session(manuscript, state, memories)

    # ------------------------------------------------------------------
    # Step 5: Logic Critic
    # ------------------------------------------------------------------
    logic_agent = LogicCriticAgent(config)
    display_info("[Scout] Running Logic Critic...")

    try:
        logic_flags = logic_agent.call(state, memories["logic_critic"], extra=ms_extra)
        memories["logic_critic"] = append_memory_entry(
            "logic_critic", session_id, 1, scout_priority,
            f"Scout round: {logic_flags[:80]}"
        )
    except Exception as e:
        display_warning(f"Logic Critic failed: {e}")
        logic_flags = f"error — skipped: {e}"

    save_session(manuscript, state, memories)

    # ------------------------------------------------------------------
    # Step 6: Counterexample Hunter
    # ------------------------------------------------------------------
    counterex_agent = CounterexAgent(config)
    display_info("[Scout] Running Counterexample Hunter...")

    try:
        counterex_result = counterex_agent.call(state, memories["counterex"], extra=ms_extra)
        memories["counterex"] = append_memory_entry(
            "counterex", session_id, 1, scout_priority,
            f"Scout: {counterex_result[:80]}"
        )
    except Exception as e:
        display_warning(f"Counterex Hunter failed: {e}")
        counterex_result = f"error — skipped: {e}"

    save_session(manuscript, state, memories)

    # ------------------------------------------------------------------
    # Step 7: Orchestrator (scout verdict)
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
            "orchestrator", session_id, 1, scout_priority,
            mem_note or f"Scout verdict: {orch_output.get('scout_verdict', '?')}"
        )
    except Exception as e:
        display_warning(f"Orchestrator failed: {e}")
        orch_output = {
            "stopping_signal": StoppingSignal.SCOUT_INTERESTING,
            "stopping_reason": f"Orchestrator error: {e}",
            "scout_verdict": "INTERESTING",
            "scout_reason": "Could not evaluate — orchestrator error.",
            "directive_for_rep": "",
            "advance_chunk": False,
            "modify_dependency": None,
            "memory_note": "",
        }

    # Derive flags from critics
    logic_ok = "ok" in logic_flags.lower() and "error" not in logic_flags.lower()
    no_counterex = "COUNTEREXAMPLE FOUND" not in counterex_result.upper()
    if logic_ok and no_counterex:
        new_flags = []
    else:
        new_flags = [line.strip() for line in logic_flags.splitlines()
                     if line.strip() and line.strip().lower() != "ok"][:5]
        if not no_counterex:
            new_flags = ["COUNTEREXAMPLE: " + counterex_result[:120]] + new_flags[:4]

    orch_output["open_flags"] = new_flags
    orch_output["round_goal"] = state.round_goal

    state.stopping_signal = orch_output.get("stopping_signal", StoppingSignal.SCOUT_INTERESTING)
    state.stopping_reason = orch_output.get("stopping_reason", "")
    state.open_flags = new_flags
    state.scout_verdict = orch_output.get("scout_verdict")

    from models.document import ChunkFlag
    focus_node.flags = [ChunkFlag(source_agent="critics", round=1, text=t) for t in new_flags]

    save_session(manuscript, state, memories)

    # ------------------------------------------------------------------
    # Step 8: Display
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
    # Step 9: Return
    # ------------------------------------------------------------------
    verdict = orch_output.get("scout_verdict", "INTERESTING")
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

"""
Deep mode loop.

Full pipeline: chunk by chunk, multiple rounds per chunk.
Agent order per round: Rep → Logic Critic → Counterex → Reference → Elegance → Orchestrator.
"""

import sys
import threading
import uuid
from datetime import datetime
from typing import Dict, List, Optional

from config import Config
from agents.decomposer import DecomposerAgent
from agents.rep import RepAgent
from agents.logic_critic import LogicCriticAgent
from agents.counterex import CounterexAgent
from agents.reference import ReferenceAgent
from agents.elegance import EleganceAgent
from agents.orchestrator import OrchestratorAgent
from models.document import (
    ChunkNode, Manuscript, propagate_change, rebuild_dependents, topological_sort,
)
from models.signals import ChunkStatus, SessionMode, StoppingSignal
from models.state import AgentMemory, MemoryEntry, RoundState
from storage.session_store import save_session
from storage.memory_store import load_memory, save_memory, append_memory_entry
from output.display import (
    display_round,
    display_graph_status,
    display_info,
    display_warning,
    display_success,
    display_error,
    console,
)


# ---------------------------------------------------------------------------
# User input handler (runs in background thread)
# ---------------------------------------------------------------------------

class UserInputHandler:
    def __init__(self):
        self._note_queue: List[str] = []
        self._stop_flag = False
        self._skip_flag = False
        self._quit_flag = False
        self._thread: Optional[threading.Thread] = None
        self._active = False

    def start(self):
        self._active = True
        self._thread = threading.Thread(target=self._listen, daemon=True)
        self._thread.start()

    def stop(self):
        self._active = False

    def _listen(self):
        while self._active:
            try:
                line = input().strip()
                if line.lower() == "q":
                    self._quit_flag = True
                elif line.lower() == "s":
                    self._stop_flag = True
                elif line.lower() == "skip":
                    self._skip_flag = True
                elif line.lower().startswith("n "):
                    note = line[2:].strip()
                    if note:
                        self._note_queue.append(note)
                        console.print(f"[dim]Note queued: {note}[/dim]")
            except EOFError:
                break
            except KeyboardInterrupt:
                self._quit_flag = True
                break

    def pop_note(self) -> Optional[str]:
        return self._note_queue.pop(0) if self._note_queue else None

    @property
    def should_stop(self) -> bool:
        return self._stop_flag

    @property
    def should_skip(self) -> bool:
        val = self._skip_flag
        self._skip_flag = False
        return val

    @property
    def should_quit(self) -> bool:
        return self._quit_flag

    def reset_stop(self):
        self._stop_flag = False


# ---------------------------------------------------------------------------
# Graph traversal helpers
# ---------------------------------------------------------------------------

def next_chunk_to_process(manuscript: Manuscript) -> Optional[str]:
    """
    Walk traversal_order in order.
    Return the first chunk that is not APPROVED (or is review_requested).
    Return None if all are APPROVED and no review_requested.
    """
    for nid in manuscript.traversal_order:
        node = manuscript.nodes.get(nid)
        if node is None:
            continue
        if node.review_requested:
            return nid
        if node.status not in (ChunkStatus.APPROVED, ChunkStatus.ABANDONED):
            return nid
    return None


def after_chunk_approved(manuscript: Manuscript, chunk_id: str) -> List[str]:
    """
    Mark chunk as APPROVED and propagate change to dependents.
    Returns list of dependent ids flagged for re-review.
    """
    node = manuscript.nodes.get(chunk_id)
    if node:
        node.status = ChunkStatus.APPROVED
        node.review_requested = False

    flagged = propagate_change(manuscript.nodes, chunk_id)

    manuscript.traversal_order = topological_sort(manuscript.nodes)
    nxt = next_chunk_to_process(manuscript)
    if nxt:
        manuscript.current_chunk_id = nxt
    return flagged


def after_chunk_modified(manuscript: Manuscript, chunk_id: str) -> List[str]:
    """
    Called when Rep modifies an already-APPROVED chunk (directed by orchestrator).
    Sets it back to UNDER_REVIEW and propagates change.
    Returns list of dependent ids flagged for re-review.
    """
    node = manuscript.nodes.get(chunk_id)
    if node and node.status == ChunkStatus.APPROVED:
        node.status = ChunkStatus.UNDER_REVIEW

    flagged = propagate_change(manuscript.nodes, chunk_id)
    return flagged


# ---------------------------------------------------------------------------
# Main deep loop
# ---------------------------------------------------------------------------

def run_deep(
    topic: str,
    config: Config,
    prior_scout: Optional[dict] = None,
    session_id: Optional[str] = None,
    existing_manuscript: Optional[Manuscript] = None,
    existing_state: Optional[RoundState] = None,
    existing_memories: Optional[Dict[str, AgentMemory]] = None,
    injected_note: Optional[str] = None,
    scope=None,
) -> dict:
    if session_id is None:
        session_id = str(uuid.uuid4())[:8]

    if existing_manuscript is not None:
        manuscript = existing_manuscript
        state = existing_state
        memories = existing_memories or _init_memories(session_id)
        display_info(f"[Deep] Resuming session {session_id}")
    elif prior_scout is not None:
        manuscript, state, memories = _build_from_scout(prior_scout, session_id, config)
        display_info(f"[Deep] Starting deep session from scout result — {session_id}")
    else:
        manuscript, state, memories = _build_fresh(topic, session_id, config, scope=scope)
        display_info(f"[Deep] Starting fresh deep session — {session_id}")

    pending_note: Optional[str] = injected_note

    rep_agent = RepAgent(config)
    logic_agent = LogicCriticAgent(config)
    counterex_agent = CounterexAgent(config)
    reference_agent = ReferenceAgent(config)
    elegance_agent = EleganceAgent(config)
    orch_agent = OrchestratorAgent(config)

    input_handler = UserInputHandler()
    input_handler.start()

    chunk_consecutive_clean: Dict[str, int] = {}
    chunk_flag_history: Dict[str, List[List[str]]] = {}

    chunks_processed = 0

    try:
        while chunks_processed < config.max_chunks_per_session:
            chunk_id = next_chunk_to_process(manuscript)
            if chunk_id is None:
                display_success("[Deep] All chunks approved. Session complete.")
                break

            chunk = manuscript.nodes[chunk_id]
            manuscript.current_chunk_id = chunk_id

            if chunk.status not in (ChunkStatus.APPROVED, ChunkStatus.ABANDONED):
                chunk.status = ChunkStatus.UNDER_REVIEW
            chunk.review_requested = False

            display_graph_status(manuscript)

            chunk_consecutive_clean.setdefault(chunk_id, 0)
            chunk_flag_history.setdefault(chunk_id, [])
            prev_round_logic_ok = True
            force_full_next = False

            round_num = 0
            while round_num < config.max_rounds_per_chunk:
                if input_handler.should_quit:
                    display_info("[Deep] User requested quit. Saving and exiting.")
                    save_session(manuscript, state, memories)
                    input_handler.stop()
                    return _make_result(manuscript, session_id, memories, "user_quit")

                if input_handler.should_skip:
                    display_info(f"[Deep] Skipping chunk {chunk_id}.")
                    chunk.status = ChunkStatus.ABANDONED
                    break

                user_note = pending_note or input_handler.pop_note()
                pending_note = None

                state = _build_round_state(manuscript, chunk, round_num, state, user_note)

                display_info(f"[Deep] Round {round_num + 1} — chunk: {chunk_id}")

                # Pass manuscript in extra so agents get dependency-precise context
                ms_extra = {"manuscript": manuscript}

                # ---- Rep
                rep_extra = {**ms_extra}
                if force_full_next:
                    rep_extra["force_full"] = True
                    force_full_next = False
                rep_output = _safe_call(rep_agent, "rep", state, memories, session_id, round_num, chunk_id,
                                        extra=rep_extra)
                new_content, force_full_next = rep_agent.apply_rep_output(rep_output, chunk.content or "")

                # If Rep changed an APPROVED chunk (dependency redirect), mark it modified
                was_approved = chunk.status == ChunkStatus.APPROVED
                chunk.content = new_content
                chunk.round_last_modified = round_num + 1
                state.focus_text = new_content
                if was_approved and new_content != (chunk.content or ""):
                    flagged = after_chunk_modified(manuscript, chunk_id)
                    if flagged:
                        display_info(f"[Deep] Dependency change in {chunk_id} — flagged for re-review: {flagged}")

                _extract_and_store_memory(rep_agent, rep_output, "MEMORY NOTE", memories, "rep",
                                          session_id, round_num + 1, chunk_id, config)
                save_session(manuscript, state, memories)

                if input_handler.should_stop:
                    input_handler.reset_stop()
                    display_info("[Deep] Stopping after Rep. Saving.")
                    save_session(manuscript, state, memories)
                    continue

                # ---- Logic Critic
                logic_flags = _safe_call(logic_agent, "logic_critic", state, memories, session_id,
                                         round_num, chunk_id, extra=ms_extra)
                _extract_and_store_memory(logic_agent, logic_flags, "MEMORY NOTE", memories, "logic_critic",
                                          session_id, round_num + 1, chunk_id, config)
                save_session(manuscript, state, memories)

                # ---- Counterex
                counterex_result = _safe_call(counterex_agent, "counterex", state, memories, session_id,
                                              round_num, chunk_id, extra=ms_extra)
                _extract_and_store_memory(counterex_agent, counterex_result, "MEMORY NOTE", memories, "counterex",
                                          session_id, round_num + 1, chunk_id, config)
                save_session(manuscript, state, memories)

                # ---- Reference (opt-in)
                if config.reference_critic_enabled and (round_num + 1) in config.reference_critic_rounds:
                    ref_notes = _safe_call(reference_agent, "reference", state, memories, session_id,
                                           round_num, chunk_id, extra=ms_extra)
                    _extract_and_store_memory(reference_agent, ref_notes, "MEMORY NOTE", memories, "reference",
                                              session_id, round_num + 1, chunk_id, config)
                    save_session(manuscript, state, memories)
                else:
                    ref_notes = "(not run)"

                # ---- Elegance (every other round; only if logic was clean last round)
                elegance_should_run = (round_num % 2 == 0) and (round_num == 0 or prev_round_logic_ok)
                if elegance_should_run:
                    elegance_notes = _safe_call(elegance_agent, "elegance", state, memories, session_id,
                                                round_num, chunk_id, extra=ms_extra)
                    _extract_and_store_memory(elegance_agent, elegance_notes, "MEMORY NOTE", memories, "elegance",
                                              session_id, round_num + 1, chunk_id, config)
                    save_session(manuscript, state, memories)
                else:
                    elegance_notes = "(skipped)"

                # ---- Derive flags from critics
                logic_ok = "ok" in logic_flags.lower() and "error" not in logic_flags.lower()
                no_counterex = "COUNTEREXAMPLE FOUND" not in counterex_result.upper()
                if logic_ok and no_counterex:
                    new_flags = []
                else:
                    new_flags = [
                        line.strip() for line in logic_flags.splitlines()
                        if line.strip() and line.strip().lower() != "ok"
                        and not line.strip().startswith("#")
                        and not line.strip().startswith("%")
                        and "MEMORY NOTE" not in line
                    ][:5]
                    if not no_counterex:
                        new_flags = ["COUNTEREXAMPLE: " + counterex_result[:120]] + new_flags[:4]

                # ---- Orchestrator
                try:
                    orch_output = orch_agent.synthesize(
                        state=state,
                        memory=memories.get("orchestrator", AgentMemory("orchestrator", session_id)),
                        rep_output=rep_output,
                        logic_flags=logic_flags,
                        counterex_result=counterex_result,
                        ref_notes=ref_notes,
                        elegance_notes=elegance_notes,
                        scout_mode=False,
                    )
                    memories["orchestrator"] = append_memory_entry(
                        "orchestrator", session_id, round_num + 1, chunk_id,
                        orch_output.get("memory_note") or f"Round {round_num + 1} complete",
                        config.max_memory_entries, config.memory_compress_to,
                    )
                except Exception as e:
                    display_warning(f"Orchestrator failed: {e}")
                    orch_output = _fallback_orch_output(state, str(e))

                # Inject display fields
                orch_output["open_flags"] = new_flags
                orch_output["round_goal"] = state.round_goal

                # ---- Handle modify_dependency redirect
                redirect_id = orch_output.get("modify_dependency")
                if redirect_id and redirect_id in manuscript.nodes and redirect_id != chunk_id:
                    display_info(f"[Deep] Orchestrator redirecting Rep to fix dependency: {redirect_id}")
                    dep_node = manuscript.nodes[redirect_id]
                    dep_node.status = ChunkStatus.UNDER_REVIEW
                    dep_node.review_requested = True
                    # Re-queue current chunk after dependency
                    chunk.review_requested = True
                    save_session(manuscript, state, memories)
                    break

                save_session(manuscript, state, memories)

                state = _apply_orch_output(state, orch_output, chunk, new_flags)
                chunk.flags = [f for f in chunk.flags if f.resolved]  # keep resolved; replace unresolved
                from models.document import ChunkFlag
                for flag_text in new_flags:
                    chunk.flags.append(ChunkFlag(source_agent="critics", round=round_num + 1, text=flag_text))

                flag_history = chunk_flag_history[chunk_id]
                flag_history.append(list(new_flags))
                prev_round_logic_ok = logic_ok

                if logic_ok and no_counterex and not new_flags:
                    chunk_consecutive_clean[chunk_id] = chunk_consecutive_clean.get(chunk_id, 0) + 1
                else:
                    chunk_consecutive_clean[chunk_id] = 0

                display_round(
                    round_num=round_num + 1,
                    chunk_title=chunk.title,
                    rep_output=rep_output,
                    logic_flags=logic_flags,
                    counterex_result=counterex_result,
                    orch_output=orch_output,
                    ref_notes=ref_notes,
                    elegance_notes=elegance_notes,
                    mode="deep",
                )

                signal = orch_output.get("stopping_signal", StoppingSignal.CONTINUE)

                if signal == StoppingSignal.COUNTEREXAMPLE:
                    display_error(f"COUNTEREXAMPLE: {orch_output.get('stopping_reason', '')}")
                    chunk.status = ChunkStatus.FLAGGED
                    save_session(manuscript, state, memories)
                    input_handler.stop()
                    return _make_result(manuscript, session_id, memories, "counterexample")

                if signal == StoppingSignal.SERENDIPITY:
                    display_info("[Deep] SERENDIPITY — pausing for user decision.")
                    try:
                        answer = input("Continue? [y/n]: ").strip().lower()
                    except (EOFError, KeyboardInterrupt):
                        answer = "n"
                    if answer != "y":
                        save_session(manuscript, state, memories)
                        input_handler.stop()
                        return _make_result(manuscript, session_id, memories, "serendipity")

                if signal in (StoppingSignal.CONVERGED, StoppingSignal.ELEGANT):
                    flagged = after_chunk_approved(manuscript, chunk_id)
                    if flagged:
                        display_info(f"[Deep] Chunk {chunk_id} approved — flagged dependents for re-review: {flagged}")
                    display_success(f"[Deep] Chunk {chunk_id} APPROVED — signal: {signal.value}")
                    save_session(manuscript, state, memories)
                    break

                if signal == StoppingSignal.INCUBATE:
                    display_info(f"[Deep] INCUBATE — saving state. Resume with --session {session_id}")
                    save_session(manuscript, state, memories)
                    input_handler.stop()
                    return _make_result(manuscript, session_id, memories, "incubate")

                if chunk_consecutive_clean.get(chunk_id, 0) >= config.convergence_rounds:
                    flagged = after_chunk_approved(manuscript, chunk_id)
                    if flagged:
                        display_info(f"[Deep] Chunk {chunk_id} converged — flagged dependents: {flagged}")
                    display_success(f"[Deep] Chunk {chunk_id} CONVERGED after {round_num + 1} rounds.")
                    save_session(manuscript, state, memories)
                    break

                if len(flag_history) >= config.incubation_rounds:
                    recent = flag_history[-config.incubation_rounds:]
                    if all(set(f) == set(recent[0]) for f in recent) and recent[0]:
                        display_info(f"[Deep] INCUBATE — same flags for {config.incubation_rounds} rounds.")
                        save_session(manuscript, state, memories)
                        input_handler.stop()
                        return _make_result(manuscript, session_id, memories, "incubate")

                if orch_output.get("advance_chunk"):
                    flagged = after_chunk_approved(manuscript, chunk_id)
                    if flagged:
                        display_info(f"[Deep] advance_chunk — flagged dependents: {flagged}")
                    save_session(manuscript, state, memories)
                    break

                round_num += 1

                if round_num >= config.max_rounds_per_chunk:
                    display_info(f"[Deep] Budget reached for chunk {chunk_id}.")
                    break

            chunks_processed += 1

    except KeyboardInterrupt:
        display_info("[Deep] Interrupted. Saving session.")
        save_session(manuscript, state, memories)

    finally:
        input_handler.stop()

    save_session(manuscript, state, memories)
    display_success(f"[Deep] Session complete. ID: {session_id}")
    return _make_result(manuscript, session_id, memories, "complete")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _safe_call(agent, agent_id: str, state: RoundState, memories: dict,
               session_id: str, round_num: int, chunk_id: str,
               extra: dict = None) -> str:
    try:
        return agent.call(state, memories.get(agent_id, AgentMemory(agent_id, session_id)),
                          extra=extra or {})
    except Exception as e:
        msg = f"error — skipped: {e}"
        display_warning(f"{agent_id} failed: {e}")
        return msg


def _extract_and_store_memory(
    agent, output: str, marker: str, memories: dict,
    agent_id: str, session_id: str, round_num: int, chunk_id: str, config: Config
) -> None:
    note = ""
    if marker in output:
        try:
            start = output.index(marker) + len(marker)
            note = output[start:].strip().lstrip(":").strip()
            note = note.splitlines()[0][:120] if note else ""
        except (ValueError, IndexError):
            pass

    memories[agent_id] = append_memory_entry(
        agent_id, session_id, round_num, chunk_id,
        note or f"Round {round_num} completed",
        config.max_memory_entries, config.memory_compress_to,
    )


def _build_round_state(
    manuscript: Manuscript,
    chunk: ChunkNode,
    round_num: int,
    prev_state: Optional[RoundState],
    user_note: Optional[str] = None,
) -> RoundState:
    established = prev_state.established if prev_state else []
    unresolved_flags = [f.text for f in chunk.flags if not f.resolved]
    open_flags = unresolved_flags or (prev_state.open_flags if prev_state else [])

    goal = f"Develop chunk '{chunk.title}' ({chunk.type.value}), round {round_num + 1}"
    if open_flags:
        goal = f"Resolve open flags in '{chunk.title}': {'; '.join(open_flags[:2])}"

    directive = "Develop the chunk based on the round goal and any open flags."
    if user_note:
        directive = f"User note: {user_note}. " + directive

    return RoundState(
        round=round_num + 1,
        mode=SessionMode.DEEP,
        established=established,
        current_chunk_id=chunk.id,
        current_chunk_title=chunk.title,
        focus_text=chunk.content or chunk.id,
        open_flags=open_flags,
        round_goal=goal,
        directive_for_rep=directive,
        stopping_signal=StoppingSignal.CONTINUE,
        stopping_reason="",
        priority_issues=open_flags[:3],
        scout_verdict=None,
        scope=manuscript.scope,
    )


def _apply_orch_output(state: RoundState, orch_output: dict, chunk: ChunkNode,
                       new_flags: list) -> RoundState:
    signal = orch_output.get("stopping_signal", StoppingSignal.CONTINUE)
    if not isinstance(signal, StoppingSignal):
        signal = StoppingSignal.CONTINUE

    state.stopping_signal = signal
    state.stopping_reason = orch_output.get("stopping_reason", "")
    state.directive_for_rep = orch_output.get("directive_for_rep", state.directive_for_rep)
    state.open_flags = new_flags
    state.priority_issues = new_flags[:3]
    return state


def _build_fresh(topic: str, session_id: str, config: Config, scope=None):
    """Decompose topic and build fresh manuscript + state + memories."""
    decomposer = DecomposerAgent(config)
    display_info("[Deep] Running decomposer...")

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

    graph = decomposer.build_nodes(decomp)
    nodes = graph["nodes"]
    traversal_order = graph["traversal_order"]
    global_context = graph["global_context"]

    first_id = traversal_order[0] if traversal_order else "main_claim"

    manuscript = Manuscript(
        topic=topic,
        mode=SessionMode.DEEP,
        nodes=nodes,
        traversal_order=traversal_order,
        current_chunk_id=first_id,
        global_context=global_context,
        session_id=session_id,
        created_at=datetime.now(),
        scope=scope,
    )

    state = RoundState(
        round=0,
        mode=SessionMode.DEEP,
        established=[f"Core claim: {topic}"],
        current_chunk_id=first_id,
        current_chunk_title=nodes[first_id].title if first_id in nodes else "Main",
        focus_text="",
        open_flags=[],
        round_goal="Begin deep session",
        directive_for_rep="Write a first draft of the chunk.",
        scope=scope,
    )

    memories = _init_memories(session_id)
    return manuscript, state, memories


def _build_from_scout(prior_scout: dict, session_id: str, config: Config):
    """Build deep session from a prior scout result."""
    manuscript = prior_scout.get("manuscript")
    memories = prior_scout.get("memories", {})

    if manuscript is None:
        topic = prior_scout.get("decomp", {}).get("title", "topic")
        return _build_fresh(topic, session_id, config)

    manuscript.mode = SessionMode.DEEP
    manuscript.session_id = session_id

    for node in manuscript.nodes.values():
        if node.status not in (ChunkStatus.APPROVED,):
            node.status = ChunkStatus.DRAFT

    first_id = manuscript.traversal_order[0] if manuscript.traversal_order else manuscript.current_chunk_id

    state = RoundState(
        round=0,
        mode=SessionMode.DEEP,
        established=[f"Core claim: {manuscript.topic}"],
        current_chunk_id=first_id,
        current_chunk_title=manuscript.nodes[first_id].title if first_id in manuscript.nodes else "Main",
        focus_text="",
        open_flags=[],
        round_goal="Begin deep session from scout",
        directive_for_rep="Develop the first chunk fully.",
    )

    all_agents = ["rep", "logic_critic", "counterex", "reference", "elegance", "orchestrator"]
    for agent_id in all_agents:
        if agent_id not in memories:
            memories[agent_id] = AgentMemory(agent_id=agent_id, session_id=session_id, entries=[])

    return manuscript, state, memories


def _init_memories(session_id: str) -> Dict[str, AgentMemory]:
    agent_ids = ["rep", "logic_critic", "counterex", "reference", "elegance", "orchestrator"]
    return {
        aid: AgentMemory(agent_id=aid, session_id=session_id, entries=[])
        for aid in agent_ids
    }


def _fallback_orch_output(state: RoundState, error_msg: str) -> dict:
    return {
        "stopping_signal": StoppingSignal.CONTINUE,
        "stopping_reason": f"Orchestrator error: {error_msg}",
        "directive_for_rep": state.directive_for_rep,
        "advance_chunk": False,
        "modify_dependency": None,
        "memory_note": "",
        "scout_verdict": None,
        "scout_reason": "",
        "raw": error_msg,
    }


def _make_result(manuscript: Manuscript, session_id: str, memories: dict, reason: str) -> dict:
    return {
        "manuscript": manuscript,
        "session_id": session_id,
        "memories": memories,
        "exit_reason": reason,
    }

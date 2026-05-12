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
from models.document import Chunk, Manuscript
from models.signals import ChunkStatus, SessionMode, StoppingSignal
from models.state import AgentMemory, MemoryEntry, RoundState
from storage.session_store import save_session
from storage.memory_store import load_memory, save_memory, append_memory_entry
from output.display import (
    display_round,
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
    """
    Listens for user commands in a background thread:
      n <note>  — queue a note for the next round
      s         — stop after current agent
      skip      — skip current chunk
      q         — quit immediately
    """

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
                line = input()
                line = line.strip()
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
        self._skip_flag = False   # reset after reading
        return val

    @property
    def should_quit(self) -> bool:
        return self._quit_flag

    def reset_stop(self):
        self._stop_flag = False


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
) -> dict:
    """
    Run deep mode on a topic.

    Can start fresh or continue from a prior scout/session.
    Returns a dict with the final manuscript and session info.
    """
    if session_id is None:
        session_id = str(uuid.uuid4())[:8]

    # ------------------------------------------------------------------
    # Build or resume manuscript
    # ------------------------------------------------------------------
    if existing_manuscript is not None:
        manuscript = existing_manuscript
        state = existing_state
        memories = existing_memories or _init_memories(session_id)
        display_info(f"[Deep] Resuming session {session_id}")
    elif prior_scout is not None:
        manuscript, state, memories = _build_from_scout(prior_scout, session_id, config)
        display_info(f"[Deep] Starting deep session from scout result — {session_id}")
    else:
        manuscript, state, memories = _build_fresh(topic, session_id, config)
        display_info(f"[Deep] Starting fresh deep session — {session_id}")

    # Inject note if provided
    pending_note: Optional[str] = injected_note

    # ------------------------------------------------------------------
    # Set up agents
    # ------------------------------------------------------------------
    rep_agent = RepAgent(config)
    logic_agent = LogicCriticAgent(config)
    counterex_agent = CounterexAgent(config)
    reference_agent = ReferenceAgent(config)
    elegance_agent = EleganceAgent(config)
    orch_agent = OrchestratorAgent(config)

    # ------------------------------------------------------------------
    # Set up user input handler
    # ------------------------------------------------------------------
    input_handler = UserInputHandler()
    input_handler.start()

    # Track consecutive clean rounds per chunk for convergence
    chunk_consecutive_clean: Dict[str, int] = {}
    chunk_flag_history: Dict[str, List[List[str]]] = {}

    # ------------------------------------------------------------------
    # Outer loop: iterate over chunks
    # ------------------------------------------------------------------
    chunk_idx = 0
    try:
        while chunk_idx < len(manuscript.chunks) and chunk_idx < config.max_chunks_per_session:
            chunk = manuscript.chunks[chunk_idx]

            if chunk.status == ChunkStatus.APPROVED:
                display_info(f"[Deep] Skipping approved chunk: {chunk.id}")
                chunk_idx += 1
                continue

            if chunk.status == ChunkStatus.ABANDONED:
                display_info(f"[Deep] Skipping abandoned chunk: {chunk.id}")
                chunk_idx += 1
                continue

            manuscript.current_chunk_id = chunk.id
            chunk.status = ChunkStatus.UNDER_REVIEW

            # Initialize convergence tracking for this chunk
            chunk_consecutive_clean.setdefault(chunk.id, 0)
            chunk_flag_history.setdefault(chunk.id, [])

            # ----------------------------------------------------------------
            # Inner loop: rounds per chunk
            # ----------------------------------------------------------------
            round_num = 0
            while round_num < config.max_rounds_per_chunk:
                if input_handler.should_quit:
                    display_info("[Deep] User requested quit. Saving and exiting.")
                    save_session(manuscript, state, memories)
                    input_handler.stop()
                    return _make_result(manuscript, session_id, memories, "user_quit")

                if input_handler.should_skip:
                    display_info(f"[Deep] Skipping chunk {chunk.id}.")
                    chunk.status = ChunkStatus.ABANDONED
                    break

                # Pop user note
                user_note = pending_note or input_handler.pop_note()
                pending_note = None

                # ---- Build state
                state = _build_round_state(manuscript, chunk, round_num, state, user_note)

                display_info(f"[Deep] Round {round_num + 1} — chunk: {chunk.id}")

                # ---- Rep
                rep_output = _safe_call(rep_agent, "rep", state, memories, session_id, round_num, chunk.id)
                chunk_content = rep_agent.extract_chunk_content(rep_output)
                chunk.content = chunk_content
                chunk.round_last_modified = round_num + 1
                state.focus_text = chunk_content
                _extract_and_store_memory(rep_agent, rep_output, "MEMORY NOTE", memories, "rep", session_id, round_num + 1, chunk.id, config)
                save_session(manuscript, state, memories)

                if input_handler.should_stop:
                    input_handler.reset_stop()
                    display_info("[Deep] Stopping after Rep. Saving.")
                    save_session(manuscript, state, memories)
                    continue

                # ---- Logic Critic
                logic_flags = _safe_call(logic_agent, "logic_critic", state, memories, session_id, round_num, chunk.id)
                _extract_and_store_memory(logic_agent, logic_flags, "MEMORY NOTE", memories, "logic_critic", session_id, round_num + 1, chunk.id, config)
                save_session(manuscript, state, memories)

                # ---- Counterex
                counterex_result = _safe_call(counterex_agent, "counterex", state, memories, session_id, round_num, chunk.id)
                _extract_and_store_memory(counterex_agent, counterex_result, "MEMORY NOTE", memories, "counterex", session_id, round_num + 1, chunk.id, config)
                save_session(manuscript, state, memories)

                # ---- Reference
                ref_notes = _safe_call(reference_agent, "reference", state, memories, session_id, round_num, chunk.id)
                _extract_and_store_memory(reference_agent, ref_notes, "MEMORY NOTE", memories, "reference", session_id, round_num + 1, chunk.id, config)
                save_session(manuscript, state, memories)

                # ---- Elegance
                elegance_notes = _safe_call(elegance_agent, "elegance", state, memories, session_id, round_num, chunk.id)
                _extract_and_store_memory(elegance_agent, elegance_notes, "MEMORY NOTE", memories, "elegance", session_id, round_num + 1, chunk.id, config)
                save_session(manuscript, state, memories)

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
                    mem_note = orch_output.get("memory_note", "")
                    memories["orchestrator"] = append_memory_entry(
                        "orchestrator", session_id, round_num + 1, chunk.id,
                        mem_note or f"Round {round_num + 1} complete",
                        config.max_memory_entries, config.memory_compress_to,
                    )
                except Exception as e:
                    display_warning(f"Orchestrator failed: {e}")
                    orch_output = _fallback_orch_output(state, str(e))

                save_session(manuscript, state, memories)

                # ---- Update state from orchestrator output
                state = _apply_orch_output(state, orch_output, chunk)

                # ---- Update chunk flags
                new_flags = orch_output.get("open_flags", state.open_flags)
                chunk.flags = new_flags

                # ---- Track convergence
                flag_history = chunk_flag_history[chunk.id]
                flag_history.append(list(new_flags))

                logic_ok = "ok" in logic_flags.lower() and "error" not in logic_flags.lower()
                no_counterex = "COUNTEREXAMPLE FOUND" not in counterex_result.upper()
                no_new_flags = not new_flags

                if logic_ok and no_counterex and no_new_flags:
                    chunk_consecutive_clean[chunk.id] = chunk_consecutive_clean.get(chunk.id, 0) + 1
                else:
                    chunk_consecutive_clean[chunk.id] = 0

                # ---- Display round
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

                # ---- Handle stopping signals
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
                    except EOFError:
                        answer = "y"
                    except KeyboardInterrupt:
                        answer = "n"
                    if answer != "y":
                        save_session(manuscript, state, memories)
                        input_handler.stop()
                        return _make_result(manuscript, session_id, memories, "serendipity")
                    # Continue if user says yes

                if signal in (StoppingSignal.CONVERGED, StoppingSignal.ELEGANT):
                    chunk.status = ChunkStatus.APPROVED
                    chunk.approved_by_rounds = round_num + 1
                    _update_global_context(manuscript)
                    display_success(f"[Deep] Chunk {chunk.id} APPROVED — signal: {signal.value}")
                    save_session(manuscript, state, memories)
                    break

                if signal == StoppingSignal.INCUBATE:
                    display_info(f"[Deep] INCUBATE — saving state. Resume with --session {session_id}")
                    save_session(manuscript, state, memories)
                    input_handler.stop()
                    return _make_result(manuscript, session_id, memories, "incubate")

                # ---- Check convergence (independent of orchestrator signal)
                if chunk_consecutive_clean.get(chunk.id, 0) >= config.convergence_rounds:
                    chunk.status = ChunkStatus.APPROVED
                    chunk.approved_by_rounds = round_num + 1
                    _update_global_context(manuscript)
                    display_success(f"[Deep] Chunk {chunk.id} CONVERGED after {round_num + 1} rounds.")
                    save_session(manuscript, state, memories)
                    break

                # ---- Check incubation (stuck for N rounds)
                if len(flag_history) >= config.incubation_rounds:
                    recent = flag_history[-config.incubation_rounds:]
                    if all(set(f) == set(recent[0]) for f in recent) and recent[0]:
                        display_info(f"[Deep] INCUBATE — same flags for {config.incubation_rounds} rounds. Pausing.")
                        save_session(manuscript, state, memories)
                        input_handler.stop()
                        return _make_result(manuscript, session_id, memories, "incubate")

                round_num += 1

                # Budget check
                if round_num >= config.max_rounds_per_chunk:
                    display_info(f"[Deep] Budget reached for chunk {chunk.id}.")
                    break

            # End of inner loop for this chunk
            chunk_idx += 1
            if orch_output.get("advance_chunk") and chunk_idx < len(manuscript.chunks):
                manuscript.current_chunk_id = manuscript.chunks[chunk_idx].id

    except KeyboardInterrupt:
        display_info("[Deep] Interrupted. Saving session.")
        save_session(manuscript, state, memories)

    finally:
        input_handler.stop()

    # Final save
    save_session(manuscript, state, memories)
    display_success(f"[Deep] Session complete. ID: {session_id}")
    return _make_result(manuscript, session_id, memories, "complete")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _safe_call(agent, agent_id: str, state: RoundState, memories: dict,
               session_id: str, round_num: int, chunk_id: str) -> str:
    """Call an agent safely, returning a graceful error string on failure."""
    try:
        return agent.call(state, memories.get(agent_id, AgentMemory(agent_id, session_id)))
    except Exception as e:
        msg = f"error — skipped: {e}"
        display_warning(f"{agent_id} failed: {e}")
        return msg


def _extract_and_store_memory(
    agent, output: str, marker: str, memories: dict,
    agent_id: str, session_id: str, round_num: int, chunk_id: str, config: Config
) -> None:
    """Extract MEMORY NOTE from agent output and persist it."""
    note = ""
    if marker in output:
        try:
            start = output.index(marker) + len(marker)
            note = output[start:].strip().lstrip(":").strip()
            # Truncate to first line
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
    chunk: Chunk,
    round_num: int,
    prev_state: Optional[RoundState],
    user_note: Optional[str] = None,
) -> RoundState:
    """Build a RoundState for the given chunk and round."""
    established = prev_state.established if prev_state else []
    open_flags = chunk.flags or (prev_state.open_flags if prev_state else [])

    goal = f"Develop chunk '{chunk.title}', round {round_num + 1}"
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
    )


def _apply_orch_output(state: RoundState, orch_output: dict, chunk: Chunk) -> RoundState:
    """Update state with orchestrator output."""
    signal = orch_output.get("stopping_signal", StoppingSignal.CONTINUE)
    if not isinstance(signal, StoppingSignal):
        signal = StoppingSignal.CONTINUE

    state.stopping_signal = signal
    state.stopping_reason = orch_output.get("stopping_reason", "")
    state.open_flags = orch_output.get("open_flags", state.open_flags)
    state.round_goal = orch_output.get("round_goal", state.round_goal)
    state.directive_for_rep = orch_output.get("directive_for_rep", state.directive_for_rep)
    state.established = orch_output.get("established", state.established)
    state.priority_issues = orch_output.get("priority_issues", [])
    return state


def _update_global_context(manuscript: Manuscript) -> None:
    """Compress approved chunks into global_context bullets."""
    bullets = []
    for chunk in manuscript.chunks:
        if chunk.status == ChunkStatus.APPROVED and chunk.content:
            # Extract first sentence as summary
            first_line = chunk.content.strip().splitlines()[0][:100]
            bullets.append(f"• [{chunk.id}] {chunk.title}: {first_line}")
    manuscript.global_context = "\n".join(bullets)


def _build_fresh(topic: str, session_id: str, config: Config):
    """Decompose topic and build fresh manuscript + state + memories."""
    decomposer = DecomposerAgent(config)
    display_info("[Deep] Running decomposer...")

    try:
        decomp = decomposer.decompose(topic)
    except Exception as e:
        display_warning(f"Decomposer failed: {e}")
        decomp = {
            "core_claim": topic,
            "chunks": [{"id": "main_claim", "title": "Main Claim", "description": topic}],
            "scout_priority": "main_claim",
            "key_definitions": [],
        }

    chunks_data = decomp.get("chunks", [{"id": "main_claim", "title": "Main Claim", "description": topic}])
    all_chunks = [
        Chunk(
            id=cd["id"],
            title=cd["title"],
            content=cd.get("description", ""),
            status=ChunkStatus.DRAFT,
            round_created=0,
            round_last_modified=0,
        )
        for cd in chunks_data
    ]

    manuscript = Manuscript(
        topic=topic,
        mode=SessionMode.DEEP,
        chunks=all_chunks,
        current_chunk_id=all_chunks[0].id if all_chunks else "chunk_1",
        global_context="",
        session_id=session_id,
        created_at=datetime.now(),
    )

    established = []
    if decomp.get("core_claim"):
        established.append(f"Core claim: {decomp['core_claim']}")

    state = RoundState(
        round=0,
        mode=SessionMode.DEEP,
        established=established,
        current_chunk_id=manuscript.current_chunk_id,
        current_chunk_title=all_chunks[0].title if all_chunks else "Main",
        focus_text="",
        open_flags=[],
        round_goal="Begin deep session",
        directive_for_rep="Write a first draft of the chunk.",
    )

    memories = _init_memories(session_id)
    return manuscript, state, memories


def _build_from_scout(prior_scout: dict, session_id: str, config: Config):
    """Build deep session from a prior scout result."""
    manuscript = prior_scout.get("manuscript")
    memories = prior_scout.get("memories", {})

    if manuscript is None:
        return _build_fresh(prior_scout.get("decomp", {}).get("core_claim", "topic"), session_id, config)

    # Switch mode to deep
    manuscript.mode = SessionMode.DEEP
    manuscript.session_id = session_id

    # Reset chunk statuses from scout
    for chunk in manuscript.chunks:
        if chunk.status not in (ChunkStatus.APPROVED,):
            chunk.status = ChunkStatus.DRAFT

    established = []
    if manuscript.chunks:
        established.append(f"Core claim: {manuscript.topic}")

    state = RoundState(
        round=0,
        mode=SessionMode.DEEP,
        established=established,
        current_chunk_id=manuscript.current_chunk_id,
        current_chunk_title=manuscript.chunks[0].title if manuscript.chunks else "Main",
        focus_text="",
        open_flags=[],
        round_goal="Begin deep session from scout",
        directive_for_rep="Develop the first chunk fully.",
    )

    # Ensure all agent memories exist for this session
    all_agents = ["rep", "logic_critic", "counterex", "reference", "elegance", "orchestrator"]
    for agent_id in all_agents:
        if agent_id not in memories:
            memories[agent_id] = AgentMemory(agent_id=agent_id, session_id=session_id, entries=[])

    return manuscript, state, memories


def _init_memories(session_id: str) -> Dict[str, AgentMemory]:
    """Initialize empty memories for all agents."""
    agent_ids = ["rep", "logic_critic", "counterex", "reference", "elegance", "orchestrator"]
    return {
        aid: AgentMemory(agent_id=aid, session_id=session_id, entries=[])
        for aid in agent_ids
    }


def _fallback_orch_output(state: RoundState, error_msg: str) -> dict:
    """Return a safe fallback orchestrator output."""
    return {
        "stopping_signal": StoppingSignal.CONTINUE,
        "stopping_reason": f"Orchestrator error: {error_msg}",
        "established": state.established,
        "current_chunk_id": state.current_chunk_id,
        "open_flags": state.open_flags,
        "round_goal": state.round_goal,
        "directive_for_rep": state.directive_for_rep,
        "priority_issues": [],
        "advance_chunk": False,
        "memory_note": "",
        "raw": error_msg,
    }


def _make_result(manuscript: Manuscript, session_id: str, memories: dict, reason: str) -> dict:
    return {
        "manuscript": manuscript,
        "session_id": session_id,
        "memories": memories,
        "exit_reason": reason,
    }

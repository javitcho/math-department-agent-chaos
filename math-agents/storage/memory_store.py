import json
import os
from dataclasses import asdict
from pathlib import Path

from models.state import AgentMemory, MemoryEntry


def _memory_path(agent_id: str, session_id: str) -> Path:
    sessions_dir = Path(__file__).parent.parent / "sessions"
    return sessions_dir / session_id / "memory" / f"{agent_id}.json"


def save_memory(memory: AgentMemory, session_id: str) -> None:
    """Persist an agent's memory to sessions/{session_id}/memory/{agent_id}.json."""
    path = _memory_path(memory.agent_id, session_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    data = {
        "agent_id": memory.agent_id,
        "session_id": memory.session_id,
        "entries": [
            {
                "round": e.round,
                "chunk_id": e.chunk_id,
                "note": e.note,
            }
            for e in memory.entries
        ],
    }
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")


def load_memory(agent_id: str, session_id: str) -> AgentMemory:
    """
    Load an agent's memory from sessions/{session_id}/memory/{agent_id}.json.
    Returns an empty AgentMemory if the file does not exist.
    """
    path = _memory_path(agent_id, session_id)
    if not path.exists():
        return AgentMemory(agent_id=agent_id, session_id=session_id, entries=[])
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        entries = []
        for e in data.get("entries", []):
            entries.append(MemoryEntry(
                round=e["round"],
                chunk_id=e["chunk_id"],
                note=e["note"],
            ))
        return AgentMemory(
            agent_id=data.get("agent_id", agent_id),
            session_id=data.get("session_id", session_id),
            entries=entries,
        )
    except Exception as ex:
        print(f"[WARNING] Could not load memory for {agent_id}/{session_id}: {ex}")
        return AgentMemory(agent_id=agent_id, session_id=session_id, entries=[])


def append_memory_entry(
    agent_id: str,
    session_id: str,
    round_num: int,
    chunk_id: str,
    note: str,
    max_entries: int = 15,
    compress_to: int = 5,
) -> AgentMemory:
    """
    Convenience helper: load memory, append a new entry, compress if needed, and save.
    Returns the updated AgentMemory.
    """
    memory = load_memory(agent_id, session_id)
    if note:
        memory.entries.append(MemoryEntry(round=round_num, chunk_id=chunk_id, note=note))

    # Compress if over limit
    if len(memory.entries) > max_entries:
        n_compress = len(memory.entries) - compress_to
        to_compress = memory.entries[:n_compress]
        keep = memory.entries[n_compress:]

        if to_compress:
            first_round = to_compress[0].round
            last_round = to_compress[-1].round
            notes = "; ".join(e.note for e in to_compress)
            chunk_ids = list({e.chunk_id for e in to_compress})
            summary_note = f"Rounds {first_round}-{last_round}: {notes}"[:200]
            summary = MemoryEntry(
                round=f"{first_round}-{last_round} summary",
                chunk_id=", ".join(chunk_ids),
                note=summary_note,
            )
            memory.entries = [summary] + keep

    save_memory(memory, session_id)
    return memory

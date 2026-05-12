import json
import os
from dataclasses import asdict
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Dict, Optional, Tuple

from models.document import Chunk, Manuscript
from models.signals import ChunkStatus, SessionMode, StoppingSignal
from models.state import AgentMemory, MemoryEntry, RoundState


# ---------------------------------------------------------------------------
# Custom JSON encoder for dataclasses, enums, datetimes
# ---------------------------------------------------------------------------

class MathAgentEncoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, Enum):
            return obj.value
        if isinstance(obj, datetime):
            return obj.isoformat()
        if hasattr(obj, "__dataclass_fields__"):
            return asdict(obj)
        return super().default(obj)


# ---------------------------------------------------------------------------
# Path helpers
# ---------------------------------------------------------------------------

def _sessions_root() -> Path:
    return Path(__file__).parent.parent / "sessions"


def _session_dir(session_id: str) -> Path:
    return _sessions_root() / session_id


def _session_file(session_id: str) -> Path:
    return _session_dir(session_id) / "session.json"


# ---------------------------------------------------------------------------
# Save
# ---------------------------------------------------------------------------

def save_session(
    manuscript: Manuscript,
    state: RoundState,
    memories: Dict[str, AgentMemory],
    extra: Optional[dict] = None,
) -> None:
    """
    Serialize Manuscript + RoundState + all agent memories to
    sessions/{session_id}/session.json.
    Also triggers export of manuscript.md.
    """
    session_id = manuscript.session_id
    session_dir = _session_dir(session_id)
    session_dir.mkdir(parents=True, exist_ok=True)

    # Serialize memories
    serialized_memories = {}
    for agent_id, mem in memories.items():
        serialized_memories[agent_id] = {
            "agent_id": mem.agent_id,
            "session_id": mem.session_id,
            "entries": [
                {"round": e.round, "chunk_id": e.chunk_id, "note": e.note}
                for e in mem.entries
            ],
        }

    payload = {
        "manuscript": _serialize_manuscript(manuscript),
        "state": _serialize_state(state),
        "memories": serialized_memories,
        "saved_at": datetime.now().isoformat(),
    }
    if extra:
        payload["extra"] = extra

    session_file = _session_file(session_id)
    session_file.write_text(
        json.dumps(payload, indent=2, cls=MathAgentEncoder),
        encoding="utf-8",
    )

    # Export manuscript to markdown
    try:
        from output.exporter import export_manuscript
        export_manuscript(manuscript, session_dir)
    except Exception as e:
        print(f"[WARNING] Export failed: {e}")


# ---------------------------------------------------------------------------
# Load
# ---------------------------------------------------------------------------

def load_session(session_id: str) -> Tuple[Manuscript, RoundState, Dict[str, AgentMemory]]:
    """
    Load session from sessions/{session_id}/session.json.
    Returns (manuscript, state, memories_dict).
    """
    session_file = _session_file(session_id)
    if not session_file.exists():
        raise FileNotFoundError(f"Session '{session_id}' not found at {session_file}")

    data = json.loads(session_file.read_text(encoding="utf-8"))

    manuscript = _deserialize_manuscript(data["manuscript"])
    state = _deserialize_state(data["state"])
    memories = {}
    for agent_id, mem_data in data.get("memories", {}).items():
        entries = [
            MemoryEntry(
                round=e["round"],
                chunk_id=e["chunk_id"],
                note=e["note"],
            )
            for e in mem_data.get("entries", [])
        ]
        memories[agent_id] = AgentMemory(
            agent_id=mem_data["agent_id"],
            session_id=mem_data["session_id"],
            entries=entries,
        )

    return manuscript, state, memories


# ---------------------------------------------------------------------------
# List sessions
# ---------------------------------------------------------------------------

def list_sessions() -> list:
    """Return a list of dicts with info about each saved session."""
    sessions_root = _sessions_root()
    if not sessions_root.exists():
        return []

    results = []
    for entry in sorted(sessions_root.iterdir()):
        if not entry.is_dir():
            continue
        sf = entry / "session.json"
        if not sf.exists():
            continue
        try:
            data = json.loads(sf.read_text(encoding="utf-8"))
            ms = data.get("manuscript", {})
            results.append({
                "session_id": ms.get("session_id", entry.name),
                "topic": ms.get("topic", "unknown"),
                "mode": ms.get("mode", "unknown"),
                "saved_at": data.get("saved_at", "unknown"),
                "chunk_count": len(ms.get("chunks", [])),
                "current_chunk": ms.get("current_chunk_id", ""),
            })
        except Exception as e:
            results.append({"session_id": entry.name, "error": str(e)})

    return results


# ---------------------------------------------------------------------------
# Serialization helpers
# ---------------------------------------------------------------------------

def _serialize_manuscript(m: Manuscript) -> dict:
    return {
        "topic": m.topic,
        "mode": m.mode.value,
        "chunks": [_serialize_chunk(c) for c in m.chunks],
        "current_chunk_id": m.current_chunk_id,
        "global_context": m.global_context,
        "session_id": m.session_id,
        "created_at": m.created_at.isoformat(),
    }


def _serialize_chunk(c: Chunk) -> dict:
    return {
        "id": c.id,
        "title": c.title,
        "content": c.content,
        "status": c.status.value,
        "round_created": c.round_created,
        "round_last_modified": c.round_last_modified,
        "flags": c.flags,
        "approved_by_rounds": c.approved_by_rounds,
    }


def _serialize_state(s: RoundState) -> dict:
    return {
        "round": s.round,
        "mode": s.mode.value,
        "established": s.established,
        "current_chunk_id": s.current_chunk_id,
        "current_chunk_title": s.current_chunk_title,
        "focus_text": s.focus_text,
        "open_flags": s.open_flags,
        "round_goal": s.round_goal,
        "directive_for_rep": s.directive_for_rep,
        "stopping_signal": s.stopping_signal.value,
        "stopping_reason": s.stopping_reason,
        "priority_issues": s.priority_issues,
        "scout_verdict": s.scout_verdict,
    }


def _deserialize_manuscript(data: dict) -> Manuscript:
    chunks = [_deserialize_chunk(c) for c in data.get("chunks", [])]
    return Manuscript(
        topic=data["topic"],
        mode=SessionMode(data["mode"]),
        chunks=chunks,
        current_chunk_id=data["current_chunk_id"],
        global_context=data.get("global_context", ""),
        session_id=data["session_id"],
        created_at=datetime.fromisoformat(data["created_at"]),
    )


def _deserialize_chunk(data: dict) -> Chunk:
    return Chunk(
        id=data["id"],
        title=data["title"],
        content=data.get("content", ""),
        status=ChunkStatus(data["status"]),
        round_created=data.get("round_created", 0),
        round_last_modified=data.get("round_last_modified", 0),
        flags=data.get("flags", []),
        approved_by_rounds=data.get("approved_by_rounds", 0),
    )


def _deserialize_state(data: dict) -> RoundState:
    return RoundState(
        round=data["round"],
        mode=SessionMode(data["mode"]),
        established=data.get("established", []),
        current_chunk_id=data["current_chunk_id"],
        current_chunk_title=data.get("current_chunk_title", ""),
        focus_text=data.get("focus_text", ""),
        open_flags=data.get("open_flags", []),
        round_goal=data.get("round_goal", ""),
        directive_for_rep=data.get("directive_for_rep", ""),
        stopping_signal=StoppingSignal(data.get("stopping_signal", "continue")),
        stopping_reason=data.get("stopping_reason", ""),
        priority_issues=data.get("priority_issues", []),
        scout_verdict=data.get("scout_verdict"),
    )

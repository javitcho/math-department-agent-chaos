"""
runner.py — Background thread wrapper for math-agents sessions.

Registers a save hook on storage.session_store to emit SSE events
after every agent save, without modifying core loop files.
"""

import queue
import threading
import traceback
from typing import Optional, Dict

from models.document import Manuscript
from models.state import RoundState, AgentMemory

# Per-session SSE queues: session_id → Queue[dict]
_SSE_QUEUES: Dict[str, queue.Queue] = {}
# Scope updates queued for the in-memory session thread: session_id → {field: value}
_PENDING_SCOPE_UPDATES: Dict[str, dict] = {}
# Content notes to apply on next resume: session_id → [note, ...]
_PENDING_NOTES: Dict[str, list] = {}
_QUEUES_LOCK = threading.Lock()


def get_or_create_queue(session_id: str) -> queue.Queue:
    with _QUEUES_LOCK:
        if session_id not in _SSE_QUEUES:
            _SSE_QUEUES[session_id] = queue.Queue(maxsize=256)
        return _SSE_QUEUES[session_id]


def get_queue(session_id: str) -> Optional[queue.Queue]:
    with _QUEUES_LOCK:
        return _SSE_QUEUES.get(session_id)


def drop_queue(session_id: str):
    with _QUEUES_LOCK:
        _SSE_QUEUES.pop(session_id, None)


def queue_scope_update(session_id: str, updates: dict):
    """Queue scope field updates to be applied on the next save hook call (in-memory update)."""
    with _QUEUES_LOCK:
        existing = _PENDING_SCOPE_UPDATES.setdefault(session_id, {})
        existing.update({k: v for k, v in updates.items() if v is not None})


def queue_content_note(session_id: str, note: str):
    """Queue a content note to be passed as injected_note on next resume."""
    with _QUEUES_LOCK:
        _PENDING_NOTES.setdefault(session_id, []).append(note)


def pop_pending_note(session_id: str) -> Optional[str]:
    """Pop the oldest pending content note, or None."""
    with _QUEUES_LOCK:
        notes = _PENDING_NOTES.get(session_id, [])
        return notes.pop(0) if notes else None


def _emit(session_id: str, event: dict):
    q = get_queue(session_id)
    if q:
        try:
            q.put_nowait(event)
        except queue.Full:
            pass


def _serialize_manuscript_light(manuscript: Manuscript) -> dict:
    return {
        "topic": manuscript.topic,
        "session_id": manuscript.session_id,
        "mode": manuscript.mode.value,
        "current_chunk_id": manuscript.current_chunk_id,
        "chunks": [
            {
                "id": c.id,
                "title": c.title,
                "content": c.content,
                "status": c.status.value,
                "flags": c.flags,
            }
            for c in manuscript.chunks
        ],
    }


def _serialize_state_light(state: RoundState) -> dict:
    return {
        "round": state.round,
        "mode": state.mode.value,
        "current_chunk_id": state.current_chunk_id,
        "current_chunk_title": state.current_chunk_title,
        "open_flags": state.open_flags,
        "round_goal": state.round_goal,
        "stopping_signal": state.stopping_signal.value,
        "stopping_reason": state.stopping_reason,
        "priority_issues": state.priority_issues,
        "scout_verdict": state.scout_verdict,
        "established": state.established[:6],
    }


def _make_save_hook(session_id: str):
    """Return a save hook function that emits SSE events for this session."""
    _prev_mem_counts: Dict[str, int] = {}

    def hook(manuscript: Manuscript, state: RoundState, memories: Dict[str, AgentMemory]):
        if manuscript.session_id != session_id:
            return

        # Apply any pending scope updates to the in-memory objects so the next
        # round picks them up without requiring a session resume.
        with _QUEUES_LOCK:
            updates = _PENDING_SCOPE_UPDATES.pop(session_id, {})
        if updates:
            for obj in (manuscript.scope, state.scope):
                if obj is not None:
                    for field, value in updates.items():
                        if hasattr(obj, field):
                            setattr(obj, field, value)

        agent_just_ran = None
        note = ""
        for aid, mem in memories.items():
            prev = _prev_mem_counts.get(aid, 0)
            now = len(mem.entries)
            if now > prev:
                agent_just_ran = aid
                _prev_mem_counts[aid] = now
                if mem.entries:
                    note = mem.entries[-1].note

        _emit(session_id, {
            "type": "update",
            "agent": agent_just_ran,
            "round": state.round,
            "note": note,
            "manuscript": _serialize_manuscript_light(manuscript),
            "state": _serialize_state_light(state),
        })

    return hook


def handle_injection(session_id: str, note: str, config) -> dict:
    """
    Classify and route an injected user note mid-session.

    - Scope-change notes: queued for the in-memory session thread via queue_scope_update
      and immediately applied to the saved file so --inspect reflects the change.
    - Content notes: stored in _PENDING_NOTES for the next resume/round.
    SSE events are emitted for both.
    """
    from storage.session_store import load_session, save_session as _save_session
    from agents.interpreter import InterpreterAgent

    try:
        manuscript, state, memories = load_session(session_id)
        scope = manuscript.scope
    except Exception:
        manuscript = state = memories = None
        scope = None

    interp = InterpreterAgent(config)
    result = interp.interpret_injection(note, scope)

    if result.get("is_scope_change"):
        raw_updates = result.get("scope_updates", {})
        updates = {k: v for k, v in raw_updates.items() if v is not None}

        if updates and scope is not None:
            # Queue for the in-memory session thread
            queue_scope_update(session_id, updates)
            # Also persist to file so inspect/resume see the change immediately
            for field, value in updates.items():
                if hasattr(scope, field):
                    setattr(scope, field, value)
            if manuscript is not None:
                _save_session(manuscript, state, memories)

        scope_dict = {
            "purpose": scope.purpose if scope else None,
            "audience": scope.audience if scope else None,
            "rigor": scope.rigor if scope else None,
            "stopping_preference": scope.stopping_preference if scope else None,
            "tone_notes": scope.tone_notes if scope else None,
            "user_focus": scope.user_focus if scope else None,
        }
        _emit(session_id, {
            "type": "scope_changed",
            "scope": scope_dict,
            "confirmation": result.get("confirmation", "Scope updated."),
        })

        content_note = result.get("content_note", "")
        if content_note:
            queue_content_note(session_id, content_note)
            _emit(session_id, {"type": "note_queued", "note": content_note})
    else:
        content_note = result.get("content_note") or note
        queue_content_note(session_id, content_note)
        _emit(session_id, {"type": "note_queued", "note": content_note})

    return result


class SessionRunner:
    """Wraps a session run in a daemon background thread."""

    def __init__(self, session_id: str):
        self.session_id = session_id
        self._thread: Optional[threading.Thread] = None

    def start_new(self, topic: str, mode: str, scope_overrides: dict, config):
        q = get_or_create_queue(self.session_id)
        hook = _make_save_hook(self.session_id)

        def run():
            from storage.session_store import add_save_hook, remove_save_hook
            add_save_hook(hook)
            try:
                from models.state import SessionScope
                from models.signals import SessionMode

                scope = SessionScope(
                    purpose=scope_overrides.get("purpose", "exploration"),
                    audience=scope_overrides.get("audience", "self"),
                    rigor=scope_overrides.get("rigor", "sketch"),
                    stopping_preference=scope_overrides.get("stopping_preference", "natural"),
                    tone_notes=scope_overrides.get("tone_notes", ""),
                    from_manuscript=False,
                    user_focus=scope_overrides.get("user_focus", ""),
                )

                if mode == "deep":
                    from loop.deep import run_deep
                    config.default_mode = SessionMode.DEEP
                    result = run_deep(topic, config, scope=scope, session_id=self.session_id)
                    q.put({"type": "done", "result": {
                        "session_id": result.get("session_id", self.session_id),
                        "exit_reason": result.get("exit_reason", "complete"),
                    }})
                else:
                    from loop.scout import run_scout
                    config.default_mode = SessionMode.SCOUT
                    result = run_scout(topic, config, scope=scope, session_id=self.session_id)
                    q.put({"type": "done", "result": {
                        "session_id": result.get("session_id", self.session_id),
                        "verdict": result.get("verdict", "INTERESTING"),
                        "scout_reason": result.get("scout_reason", ""),
                    }})
            except Exception as e:
                q.put({"type": "error", "message": str(e), "traceback": traceback.format_exc()})
            finally:
                remove_save_hook(hook)

        self._thread = threading.Thread(target=run, daemon=True, name=f"session-{self.session_id}")
        self._thread.start()

    def resume(self, session_id: str, config, note: str = None):
        q = get_or_create_queue(self.session_id)
        hook = _make_save_hook(self.session_id)

        def run():
            from storage.session_store import add_save_hook, remove_save_hook, load_session
            add_save_hook(hook)
            try:
                manuscript, state, memories = load_session(session_id)
                from loop.deep import run_deep
                result = run_deep(
                    topic=manuscript.topic,
                    config=config,
                    existing_manuscript=manuscript,
                    existing_state=state,
                    existing_memories=memories,
                    session_id=session_id,
                    injected_note=note,
                )
                q.put({"type": "done", "result": {
                    "session_id": result.get("session_id", session_id),
                    "exit_reason": result.get("exit_reason", "complete"),
                }})
            except Exception as e:
                q.put({"type": "error", "message": str(e), "traceback": traceback.format_exc()})
            finally:
                remove_save_hook(hook)

        self._thread = threading.Thread(target=run, daemon=True, name=f"session-resume-{self.session_id}")
        self._thread.start()

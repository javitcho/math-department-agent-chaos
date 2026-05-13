"""
app.py — FastAPI server for the Math Research Multi-Agent System.

Endpoints:
  GET  /sessions                — list saved sessions
  POST /session/start           — start new session
  GET  /session/{id}            — get session state
  POST /session/{id}/resume     — resume existing session
  POST /session/{id}/export     — export to markdown + LaTeX
  GET  /session/{id}/events     — SSE stream
"""

import json
import sys
from pathlib import Path
from typing import Optional

# Ensure math-agents/ is on sys.path when running from repo root
_HERE = Path(__file__).resolve().parent.parent
if str(_HERE) not in sys.path:
    sys.path.insert(0, str(_HERE))

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from config import Config
from storage.session_store import list_sessions, load_session
from server.runner import SessionRunner, get_or_create_queue, handle_injection, pop_pending_note

app = FastAPI(title="Math Research Multi-Agent System")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

_config = Config()


# ─── Request models ──────────────────────────────────────────────────────────

class StartRequest(BaseModel):
    topic: str
    mode: str = "scout"
    purpose: Optional[str] = None
    audience: Optional[str] = None
    rigor: Optional[str] = None
    tone: Optional[str] = None
    user_focus: Optional[str] = None
    stopping_preference: Optional[str] = None


class ResumeRequest(BaseModel):
    note: Optional[str] = None


class NoteRequest(BaseModel):
    note: str


# ─── Endpoints ───────────────────────────────────────────────────────────────

@app.get("/sessions")
def get_sessions():
    return list_sessions()


@app.post("/session/start")
def start_session(req: StartRequest):
    import uuid
    session_id = str(uuid.uuid4())[:8]

    scope_overrides = {k: v for k, v in {
        "purpose": req.purpose,
        "audience": req.audience,
        "rigor": req.rigor,
        "tone_notes": req.tone,
        "user_focus": req.user_focus,
        "stopping_preference": req.stopping_preference,
    }.items() if v is not None}

    runner = SessionRunner(session_id)
    runner.start_new(req.topic, req.mode, scope_overrides, _config)
    return {"session_id": session_id, "status": "started"}


@app.get("/session/{session_id}")
def get_session(session_id: str):
    try:
        manuscript, state, memories = load_session(session_id)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail=f"Session '{session_id}' not found")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

    return {
        "manuscript": {
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
                    "round_last_modified": c.round_last_modified,
                }
                for c in manuscript.chunks
            ],
            "scope": {
                "purpose": manuscript.scope.purpose,
                "audience": manuscript.scope.audience,
                "rigor": manuscript.scope.rigor,
                "tone_notes": manuscript.scope.tone_notes,
                "user_focus": manuscript.scope.user_focus,
            } if manuscript.scope else None,
        },
        "state": {
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
            "established": state.established,
        },
        "memories": {
            aid: [
                {"round": e.round, "chunk_id": e.chunk_id, "note": e.note}
                for e in mem.entries
            ]
            for aid, mem in memories.items()
        },
    }


@app.post("/session/{session_id}/resume")
def resume_session(session_id: str, req: ResumeRequest):
    try:
        load_session(session_id)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail=f"Session '{session_id}' not found")

    note = req.note or pop_pending_note(session_id)
    runner = SessionRunner(session_id)
    runner.resume(session_id, _config, note=note)
    return {"session_id": session_id, "status": "resumed"}


@app.post("/session/{session_id}/note")
def inject_note(session_id: str, req: NoteRequest):
    try:
        result = handle_injection(session_id, req.note, _config)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    return {
        "session_id": session_id,
        "is_scope_change": result.get("is_scope_change", False),
        "confirmation": result.get("confirmation", ""),
    }


@app.post("/session/{session_id}/export")
def export_session(session_id: str):
    try:
        manuscript, state, memories = load_session(session_id)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail=f"Session '{session_id}' not found")

    from output.exporter import export_manuscript, export_latex
    sessions_root = _HERE / "sessions"
    session_dir = sessions_root / session_id
    md_path = export_manuscript(manuscript, session_dir)
    tex_path = export_latex(manuscript, session_dir)
    return {
        "session_id": session_id,
        "markdown": str(md_path),
        "latex": str(tex_path),
    }


@app.get("/session/{session_id}/events")
def session_events(session_id: str):
    """SSE stream — emits JSON events as the session progresses."""
    q = get_or_create_queue(session_id)

    def generate():
        import time
        while True:
            try:
                event = q.get(timeout=20)
                yield f"data: {json.dumps(event)}\n\n"
                if event.get("type") in ("done", "error"):
                    break
            except Exception:
                yield 'data: {"type":"ping"}\n\n'

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive",
        },
    )

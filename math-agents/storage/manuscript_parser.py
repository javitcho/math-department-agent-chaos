"""
Manuscript parser.

Reads an existing .tex / .md / .txt file and uses the API to extract its chunk structure.
Builds a Manuscript object where all chunks start APPROVED (they are context, not targets),
except the focus chunk (matched from user_focus) which is set to UNDER_REVIEW.
"""

import json
import uuid
from datetime import datetime
from pathlib import Path
from typing import Optional

from anthropic import Anthropic

from config import Config
from models.document import Chunk, Manuscript
from models.signals import ChunkStatus, SessionMode
from models.state import SessionScope


_PARSE_SYSTEM = """TASK:
Read this mathematical document and extract its structure as a list of chunks.
Each chunk is one logical unit: a definition, lemma, theorem, proof, remark, or section.

OUTPUT FORMAT (JSON, no markdown fences):
{
  "title": "document title or inferred topic",
  "chunks": [
    {
      "id": "slug_from_title",
      "title": "short label",
      "content": "verbatim content of this chunk",
      "type": "definition | lemma | theorem | proof | remark | section"
    }
  ],
  "global_context": "2-3 sentence summary of the whole document"
}

RULES:
- If the document has no clear structure, treat the whole thing as one chunk of type section.
- Preserve the verbatim content of each chunk exactly as written.
- IDs must be lowercase with underscores, e.g. thm_main, lem_cauchy, def_holomorphic.
- 500 tokens max output."""


def _strip_fences(text: str) -> str:
    text = text.strip()
    if text.startswith("```"):
        lines = text.split("\n")
        text = "\n".join(lines[1:-1]) if lines[-1].strip() == "```" else "\n".join(lines[1:])
    return text.strip()


def _match_focus_chunk(chunks: list, user_focus: str) -> Optional[str]:
    """Return the chunk id most likely to match user_focus, or None."""
    if not user_focus or not chunks:
        return None
    focus_lower = user_focus.lower()
    # Exact id match
    for c in chunks:
        if c["id"] in focus_lower or focus_lower in c["id"]:
            return c["id"]
    # Title match
    for c in chunks:
        if c["title"].lower() in focus_lower or any(
            word in c["title"].lower() for word in focus_lower.split() if len(word) > 3
        ):
            return c["id"]
    return None


def parse_manuscript(
    filepath: str,
    user_focus: str = "",
    config: Optional[Config] = None,
    session_id: Optional[str] = None,
    mode: SessionMode = SessionMode.DEEP,
    scope: Optional[SessionScope] = None,
) -> Manuscript:
    """
    Parse a .tex / .md / .txt file into a Manuscript.

    All chunks start as APPROVED (they are background context).
    The focus chunk (matched from user_focus) is set to UNDER_REVIEW.
    If no focus chunk is found and user_focus is non-empty, the last chunk is the focus.
    """
    if config is None:
        config = Config()
    if session_id is None:
        session_id = str(uuid.uuid4())[:8]

    filepath = Path(filepath)
    if not filepath.exists():
        raise FileNotFoundError(f"Manuscript file not found: {filepath}")

    content = filepath.read_text(encoding="utf-8", errors="replace")
    title = filepath.stem.replace("_", " ").replace("-", " ")

    # Call the API to extract structure
    api_key = __import__("os").environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        raise ValueError("ANTHROPIC_API_KEY not set")

    client = Anthropic(api_key=api_key)
    user_msg = f"Document title hint: {title}\n\n---\n\n{content[:8000]}"  # cap at ~8k chars

    try:
        response = client.messages.create(
            model=config.model,
            max_tokens=config.max_tokens_decomposer,
            system=_PARSE_SYSTEM,
            messages=[{"role": "user", "content": user_msg}],
        )
        raw = response.content[0].text
        data = json.loads(_strip_fences(raw))
    except Exception as e:
        print(f"[WARNING] Manuscript parser API call failed: {e} — using single-chunk fallback")
        data = {
            "title": title,
            "chunks": [{"id": "full_doc", "title": title, "content": content, "type": "section"}],
            "global_context": f"Document: {title}",
        }

    # Build Chunk objects — all start APPROVED
    chunks_data = data.get("chunks", [])
    if not chunks_data:
        chunks_data = [{"id": "full_doc", "title": title, "content": content, "type": "section"}]

    focus_id = _match_focus_chunk(chunks_data, user_focus)
    if focus_id is None and user_focus and chunks_data:
        # Default: last chunk is the focus (most likely what user wants to work on)
        focus_id = chunks_data[-1]["id"]

    chunks: list[Chunk] = []
    for cd in chunks_data:
        chunk_id = cd.get("id", f"chunk_{len(chunks)}")
        is_focus = (chunk_id == focus_id)
        chunks.append(Chunk(
            id=chunk_id,
            title=cd.get("title", chunk_id),
            content=cd.get("content", ""),
            status=ChunkStatus.UNDER_REVIEW if is_focus else ChunkStatus.APPROVED,
            round_created=0,
            round_last_modified=0,
            flags=[],
            approved_by_rounds=0 if is_focus else 1,
        ))

    current_chunk_id = focus_id or (chunks[0].id if chunks else "chunk_0")

    return Manuscript(
        topic=data.get("title", title),
        mode=mode,
        chunks=chunks,
        current_chunk_id=current_chunk_id,
        global_context=data.get("global_context", ""),
        session_id=session_id,
        created_at=datetime.now(),
        scope=scope,
    )

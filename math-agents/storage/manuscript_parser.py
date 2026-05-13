"""
Manuscript parser.

Reads an existing .tex / .md / .txt file and uses the API to extract its
chunk structure as a dependency graph. Builds a Manuscript where all nodes
start APPROVED (context), except the focus chain (from user_focus) which
is set to UNDER_REVIEW.
"""

import json
import uuid
from datetime import datetime
from pathlib import Path
from typing import Optional

from anthropic import Anthropic

from config import Config
from models.document import ChunkNode, Manuscript, rebuild_dependents, topological_sort
from models.signals import ChunkStatus, ChunkType, SessionMode
from models.state import SessionScope


_TYPE_MAP = {
    "definition": ChunkType.DEFINITION,
    "lemma":      ChunkType.LEMMA,
    "theorem":    ChunkType.THEOREM,
    "proof":      ChunkType.PROOF,
    "corollary":  ChunkType.COROLLARY,
    "remark":     ChunkType.REMARK,
    "section":    ChunkType.SECTION,
}

_PARSE_SYSTEM = r"""TASK:
Read this mathematical document and extract its structure as a dependency graph.
Each node is one logical unit: a definition, lemma, theorem, proof, remark, or section.

OUTPUT FORMAT (JSON, no markdown fences):
{
  "title": "document title or inferred topic",
  "nodes": [
    {
      "id": "slug_from_title",
      "title": "short label",
      "content": "verbatim content of this node",
      "type": "definition | lemma | theorem | proof | remark | section | corollary",
      "depends_on": ["id_of_other_node"]
    }
  ],
  "global_context": "2-3 sentence summary"
}

DEPENDENCY INFERENCE RULES:
- Infer depends_on from \ref{} and \label{} in LaTeX
- Infer from explicit mentions: "by Lemma 2", "from Definition 1", "using the above"
- Every proof depends on its theorem node
- Every theorem depends on the definitions it uses
- If a dependency is ambiguous, omit it rather than guess wrong
- depends_on lists only ids that appear in this nodes array

RULES:
- Preserve verbatim content of each node exactly as written
- IDs must be lowercase with underscores: thm_main, lem_cauchy, def_holomorphic
- 600 tokens max output"""


def _strip_fences(text: str) -> str:
    text = text.strip()
    if text.startswith("```"):
        lines = text.split("\n")
        text = "\n".join(lines[1:-1]) if lines[-1].strip() == "```" else "\n".join(lines[1:])
    return text.strip()


def _match_focus_node(nodes_data: list, user_focus: str) -> Optional[str]:
    """Return the node id most likely to match user_focus, or None."""
    if not user_focus or not nodes_data:
        return None
    focus_lower = user_focus.lower()
    for n in nodes_data:
        if n["id"] in focus_lower or focus_lower in n["id"]:
            return n["id"]
    for n in nodes_data:
        if n["title"].lower() in focus_lower or any(
            word in n["title"].lower() for word in focus_lower.split() if len(word) > 3
        ):
            return n["id"]
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
    Parse a .tex / .md / .txt file into a Manuscript with a dependency graph.

    All nodes start as APPROVED (background context).
    The focus node and its dependency chain are set to UNDER_REVIEW.
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

    api_key = __import__("os").environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        raise ValueError("ANTHROPIC_API_KEY not set")

    client = Anthropic(api_key=api_key)
    user_msg = f"Document title hint: {title}\n\n---\n\n{content[:8000]}"

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
        print(f"[WARNING] Manuscript parser API call failed: {e} — using single-node fallback")
        data = {
            "title": title,
            "nodes": [{"id": "full_doc", "title": title, "content": content,
                        "type": "section", "depends_on": []}],
            "global_context": f"Document: {title}",
        }

    nodes_data = data.get("nodes", [])
    if not nodes_data:
        nodes_data = [{"id": "full_doc", "title": title, "content": content,
                        "type": "section", "depends_on": []}]

    focus_id = _match_focus_node(nodes_data, user_focus)
    if focus_id is None and user_focus and nodes_data:
        focus_id = nodes_data[-1]["id"]

    # Build all nodes as APPROVED first
    nodes: dict = {}
    for nd in nodes_data:
        nid = nd.get("id", f"node_{len(nodes)}")
        chunk_type = _TYPE_MAP.get(nd.get("type", "section"), ChunkType.SECTION)
        nodes[nid] = ChunkNode(
            id=nid,
            title=nd.get("title", nid),
            content=nd.get("content", ""),
            type=chunk_type,
            status=ChunkStatus.APPROVED,
            depends_on=[d for d in nd.get("depends_on", []) if d in {n.get("id") for n in nodes_data}],
            dependents=[],
            round_created=0,
            round_last_modified=0,
        )

    rebuild_dependents(nodes)

    # Walk backwards from focus_id and set focus chain to UNDER_REVIEW
    if focus_id and focus_id in nodes:
        _mark_focus_chain(nodes, focus_id)
    current_chunk_id = focus_id or (list(nodes.keys())[0] if nodes else "chunk_0")

    traversal_order = topological_sort(nodes)

    return Manuscript(
        topic=data.get("title", title),
        mode=mode,
        nodes=nodes,
        traversal_order=traversal_order,
        current_chunk_id=current_chunk_id,
        global_context=data.get("global_context", ""),
        session_id=session_id,
        created_at=datetime.now(),
        scope=scope,
    )


def _mark_focus_chain(nodes: dict, focus_id: str) -> None:
    """
    Mark focus_id and all its direct depends_on as UNDER_REVIEW.
    One level back only — the spec says "walk backwards through its depends_on chain."
    """
    visited = set()
    from collections import deque
    queue = deque([focus_id])
    while queue:
        nid = queue.popleft()
        if nid in visited:
            continue
        visited.add(nid)
        node = nodes.get(nid)
        if node is None:
            continue
        node.status = ChunkStatus.UNDER_REVIEW
        for dep_id in node.depends_on:
            if dep_id not in visited and dep_id in nodes:
                queue.append(dep_id)

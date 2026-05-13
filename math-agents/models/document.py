from collections import deque
from dataclasses import dataclass, field
from datetime import datetime
from typing import TYPE_CHECKING, Dict, List, Optional

from models.signals import ChunkStatus, ChunkType, SessionMode

if TYPE_CHECKING:
    from models.state import SessionScope


@dataclass
class ChunkFlag:
    source_agent: str   # which agent raised it
    round: int
    text: str
    resolved: bool = False


@dataclass
class ChunkNode:
    id: str
    title: str
    content: str
    type: ChunkType
    status: ChunkStatus
    depends_on: List[str]       # chunk ids this node directly uses
    dependents: List[str]       # chunk ids that directly use this node
    round_created: int
    round_last_modified: int
    flags: List[ChunkFlag] = field(default_factory=list)
    review_requested: bool = False


@dataclass
class Manuscript:
    topic: str
    mode: SessionMode
    nodes: Dict[str, ChunkNode]         # keyed by chunk id
    traversal_order: List[str]          # topological sort, recomputed when graph changes
    current_chunk_id: str
    global_context: str
    session_id: str
    created_at: datetime = field(default_factory=datetime.now)
    scope: Optional["SessionScope"] = None


# ---------------------------------------------------------------------------
# Graph utilities
# ---------------------------------------------------------------------------

def topological_sort(nodes: Dict[str, ChunkNode]) -> List[str]:
    """
    Kahn's algorithm on depends_on edges.
    Returns chunk ids in dependency order (definitions first, proofs last).
    Remaining nodes appended rather than raising on cycles — math graphs may
    reference external chunks not present in this session.
    """
    in_degree = {
        nid: len([d for d in node.depends_on if d in nodes])
        for nid, node in nodes.items()
    }

    queue = deque(sorted(nid for nid, deg in in_degree.items() if deg == 0))
    result = []

    while queue:
        nid = queue.popleft()
        result.append(nid)
        for dep_id in (nodes[nid].dependents if nid in nodes else []):
            if dep_id in in_degree:
                in_degree[dep_id] -= 1
                if in_degree[dep_id] == 0:
                    queue.append(dep_id)

    remaining = [nid for nid in nodes if nid not in result]
    result.extend(sorted(remaining))
    return result


def rebuild_dependents(nodes: Dict[str, ChunkNode]) -> None:
    """Rebuild dependents lists from depends_on edges. Mutates nodes in place."""
    for node in nodes.values():
        node.dependents = []
    for nid, node in nodes.items():
        for dep_id in node.depends_on:
            if dep_id in nodes:
                nodes[dep_id].dependents.append(nid)


def get_context_for_chunk(nodes: Dict[str, ChunkNode], chunk_id: str) -> List[ChunkNode]:
    """Returns only the direct dependencies of chunk_id (one hop, not transitive)."""
    node = nodes.get(chunk_id)
    if node is None:
        return []
    return [nodes[dep_id] for dep_id in node.depends_on if dep_id in nodes]


def propagate_change(nodes: Dict[str, ChunkNode], changed_id: str) -> List[str]:
    """
    Mark all transitive dependents of changed_id as review_requested=True.
    Returns list of chunk ids that were flagged.
    """
    flagged = []
    visited = set()
    queue = deque([changed_id])

    while queue:
        current = queue.popleft()
        node = nodes.get(current)
        if node is None:
            continue
        for dep_id in node.dependents:
            if dep_id in visited:
                continue
            visited.add(dep_id)
            dep_node = nodes.get(dep_id)
            if dep_node is not None:
                dep_node.review_requested = True
                flagged.append(dep_id)
                queue.append(dep_id)

    return flagged

from dataclasses import dataclass, field
from datetime import datetime
from typing import TYPE_CHECKING, List, Optional

from models.signals import ChunkStatus, SessionMode

if TYPE_CHECKING:
    from models.state import SessionScope


@dataclass
class Chunk:
    id: str                      # e.g. "lemma_1", "proof_main", "remark_geometry"
    title: str                   # Short label
    content: str                 # Mathematical content (LaTeX, no preamble)
    status: ChunkStatus          # Current review status
    round_created: int
    round_last_modified: int
    flags: List[str] = field(default_factory=list)   # Accumulated critic flags, not yet resolved
    approved_by_rounds: int = 0  # How many consecutive rounds with no new flags


@dataclass
class Manuscript:
    topic: str
    mode: SessionMode            # SCOUT or DEEP
    chunks: List[Chunk]
    current_chunk_id: str
    global_context: str          # 3-5 bullet summary of everything approved so far
    session_id: str
    created_at: datetime = field(default_factory=datetime.now)
    scope: Optional["SessionScope"] = None

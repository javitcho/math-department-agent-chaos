from dataclasses import dataclass, field
from typing import List, Optional, Union

from models.signals import SessionMode, StoppingSignal


@dataclass
class RoundState:
    round: int
    mode: SessionMode
    established: List[str]            # Bullet points: what is proven/accepted
    current_chunk_id: str
    current_chunk_title: str
    focus_text: str                   # Verbatim text of the chunk under scrutiny
    open_flags: List[str]             # Unresolved issues from prior rounds
    round_goal: str                   # One sentence: what this round should accomplish
    directive_for_rep: str            # Specific instruction for the Rep (suggestion, not command)
    stopping_signal: StoppingSignal = StoppingSignal.CONTINUE
    stopping_reason: str = ""
    priority_issues: List[str] = field(default_factory=list)   # Top 3 issues, ranked
    scout_verdict: Optional[str] = None   # PURSUE / DROP / INTERESTING (scout mode only)


@dataclass
class MemoryEntry:
    round: Union[int, str]   # int normally; str like "1-10 summary" for compressed entries
    chunk_id: str
    note: str                # One short bullet. Max ~20 words.


@dataclass
class AgentMemory:
    agent_id: str
    session_id: str
    entries: List[MemoryEntry] = field(default_factory=list)

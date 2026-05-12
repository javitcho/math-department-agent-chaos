from dataclasses import dataclass
from models.signals import SessionMode


@dataclass
class Config:
    # Model — updated to claude-sonnet-4-6 per build instructions
    model: str = "claude-sonnet-4-6"

    # Token budgets (max output per agent call)
    max_tokens_rep: int = 1800
    max_tokens_logic: int = 300
    max_tokens_counterex: int = 250
    max_tokens_reference: int = 400
    max_tokens_elegance: int = 300
    max_tokens_orchestrator: int = 800
    max_tokens_decomposer: int = 600

    # Loop limits
    max_rounds_per_chunk: int = 4
    max_chunks_per_session: int = 8
    convergence_rounds: int = 2    # rounds with no new flags → CONVERGED
    incubation_rounds: int = 3     # rounds with same flags → INCUBATE

    # Memory
    max_memory_entries: int = 15
    memory_compress_to: int = 5

    # Modes
    default_mode: SessionMode = SessionMode.SCOUT

    # Rate limiting
    request_delay_seconds: float = 0.5   # delay between agent calls

    # Display
    show_chunk_on_update: bool = True
    verbose: bool = False   # show full agent outputs vs summaries

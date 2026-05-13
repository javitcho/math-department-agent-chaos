from dataclasses import dataclass, field
from models.signals import SessionMode


@dataclass
class Config:
    model: str = "claude-sonnet-4-6"

    # Token budgets — output tokens per agent call
    max_tokens_rep:           int = 400   # diffs are small
    max_tokens_logic:         int = 100
    max_tokens_counterex:     int = 100
    max_tokens_reference:     int = 200   # opt-in, round 1 only
    max_tokens_elegance:      int = 150
    max_tokens_orchestrator:  int = 300   # 4-field schema
    max_tokens_decomposer:    int = 300

    # Scout-specific overrides (even tighter budget)
    scout_max_tokens_rep:           int = 400
    scout_max_tokens_logic:         int = 100
    scout_max_tokens_counterex:     int = 100
    scout_max_tokens_orchestrator:  int = 150

    # Loop limits
    max_rounds_per_chunk:   int = 4
    max_chunks_per_session: int = 8
    convergence_rounds:     int = 2   # clean rounds → CONVERGED
    incubation_rounds:      int = 3   # stuck rounds → INCUBATE

    # Memory
    max_memory_entries: int = 15
    memory_compress_to: int = 5

    # Modes
    default_mode: SessionMode = SessionMode.SCOUT

    # Reference critic (opt-in)
    reference_critic_enabled: bool = False
    reference_critic_rounds: list = field(default_factory=lambda: [1])

    # Rate limiting
    request_delay_seconds: float = 0.5

    # Display
    show_chunk_on_update: bool = True
    verbose: bool = False

from agents.base import BaseAgent
from config import Config
from models.state import AgentMemory, RoundState


class EleganceAgent(BaseAgent):
    """
    Elegance Critic agent. Evaluates mathematical beauty of the current chunk.
    Scores 1-10, lists issues and improvement suggestions.
    """

    def __init__(self, config: Config):
        super().__init__("elegance", config)

    def extract_score(self, output: str) -> int:
        """Extract the numeric score from SCORE: N in the output."""
        try:
            for line in output.splitlines():
                if line.upper().startswith("SCORE:"):
                    score_str = line.split(":", 1)[1].strip().split()[0]
                    return int(score_str)
        except (ValueError, IndexError):
            pass
        return 0

    def is_elegant(self, output: str, threshold: int = 8) -> bool:
        """Return True if score >= threshold (default 8 = genuinely beautiful)."""
        return self.extract_score(output) >= threshold

    # ------------------------------------------------------------------
    # BaseAgent interface
    # ------------------------------------------------------------------

    def _max_tokens(self) -> int:
        return self.config.max_tokens_elegance

    def _build_system_prompt(self) -> str:
        return """TASK:
Evaluate the mathematical elegance of the current chunk.

INPUTS YOU RECEIVE:
- State object (focus chunk)
- Your memory (your assessment from prior rounds)

ASSESS:
- Minimality: is the proof longer than it needs to be?
- Illumination: does it explain WHY, not just THAT?
- Generality: does it prove something weaker than what the method would give?
- Surprise: does it use any unexpected tools or connections?
- Unity: does it reveal something deep about the structure?

OUTPUT FORMAT:
SCORE: [1-10]
ISSUES: [one line per issue, or "none"]
SUGGESTIONS: [one line per suggestion, or "none"]

MEMORY NOTE:
[one bullet: score history and main concern]

CONSTRAINTS:
- 200 tokens max output
- Be specific. "Step 3 could use the universal property directly, eliminating the explicit construction" not "the proof could be cleaner"
- Score honestly. 5 is average. 8+ means genuinely beautiful.
- Do not repeat suggestions from prior rounds that have already been addressed."""

    def _build_user_message(self, state: RoundState, memory: AgentMemory, extra: dict) -> str:
        state_block = self._serialize_state(state)
        memory_block = self._serialize_memory(memory)

        return f"""{state_block}

---

{memory_block}

Evaluate the elegance of the focus chunk now."""

from agents.base import BaseAgent
from config import Config
from models.state import AgentMemory, RoundState


class CounterexAgent(BaseAgent):
    """
    Counterexample Hunter agent. Attempts to find easy counterexamples
    to the main claim or any sub-claim in the current chunk.
    Hard step limit: ≤3 attempts. This is a quick sanity filter.
    """

    needs_full_chunk: bool = False

    def __init__(self, config: Config):
        super().__init__("counterex", config)

    def found_counterexample(self, output: str) -> bool:
        """Return True if the output reports a found counterexample."""
        return "COUNTEREXAMPLE FOUND" in output.upper()

    # ------------------------------------------------------------------
    # BaseAgent interface
    # ------------------------------------------------------------------

    def _max_tokens(self) -> int:
        return self.config.max_tokens_counterex

    def _build_system_prompt(self) -> str:
        return """TASK:
Attempt to find a counterexample to the main claim or any sub-claim in the current chunk.

INPUTS YOU RECEIVE:
- State object (focus chunk, established results)
- Your memory (what cases you already tried)

METHOD:
1. State the claim you are testing
2. Try: edge cases, degenerate objects, small finite cases, classical counterexamples
3. If you find one in ≤3 steps: report it
4. If not: stop

OUTPUT FORMAT:
If found:
  COUNTEREXAMPLE FOUND
  Claim tested: [claim — reference by LaTeX label if available, e.g. \ref{thm:main}]
  Counterexample: [explicit construction, ≤3 lines]
  Why it breaks the claim: [one sentence]

If not found:
  No quick counterexample.
  Tried: [comma-separated list of cases attempted]

MEMORY NOTE:
[one bullet: cases tried this round]

CONSTRAINTS:
- 150 tokens max output
- Do NOT attempt complicated counterexamples. Easy ones only.
- If you cannot find one in 3 attempts, stop. Write "No quick counterexample."
- A counterexample you are unsure about should be flagged as a QUESTION, not reported as found."""

    def _build_user_message(self, state: RoundState, memory: AgentMemory, extra: dict) -> str:
        state_block = self._serialize_state(state, extra)
        memory_block = self._serialize_memory(memory)

        return f"""{state_block}

---

{memory_block}

Attempt to find a counterexample to the claim in the focus chunk now."""

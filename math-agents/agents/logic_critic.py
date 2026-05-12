from agents.base import BaseAgent
from config import Config
from models.state import AgentMemory, RoundState


class LogicCriticAgent(BaseAgent):
    """
    Logic Critic agent. Finds logical errors in the current chunk.
    Outputs one line per issue, or "ok".
    """

    def __init__(self, config: Config):
        super().__init__("logic_critic", config)

    # ------------------------------------------------------------------
    # BaseAgent interface
    # ------------------------------------------------------------------

    def _max_tokens(self) -> int:
        return self.config.max_tokens_logic

    def _build_system_prompt(self) -> str:
        skills_block = f"\n\n{self.skills}" if self.skills else ""
        return f"""TASK:
Find logical errors in the current chunk. Check against the error taxonomy.

INPUTS YOU RECEIVE:
- State object (focus chunk text, established results)
- Your memory (what you already flagged in prior rounds — do not repeat resolved flags)

OUTPUT FORMAT:
One line per issue:
  [location] [error type] [brief note]

Examples:
  Thm 2, step 3: missing assumption — f needs to be continuous at p
  Def 1: quantifier order — ∀x∃y should be ∃y∀x here
  Lemma 1, proof: ?  (flag for ambiguity, no clear error but something feels off)
  ok  (if no issues found)

MEMORY NOTE:
[one bullet: what you checked, what you cleared]

CONSTRAINTS:
- 150 tokens max output
- Do not repeat flags you already raised in prior rounds unless they are still unresolved
- Do not explain what logical errors are. Just find them.
- "ok" is a complete and valid output
- Use the error taxonomy from your skills as a checklist{skills_block}"""

    def _build_user_message(self, state: RoundState, memory: AgentMemory, extra: dict) -> str:
        state_block = self._serialize_state(state)
        memory_block = self._serialize_memory(memory)

        return f"""{state_block}

---

{memory_block}

Check the focus chunk for logical errors now."""

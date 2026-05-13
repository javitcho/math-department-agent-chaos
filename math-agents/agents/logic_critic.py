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
        skills_block = ("\n\n" + self.skills) if self.skills else ""
        flag_examples = (
            r"  \ref{thm:main}, step 3: missing assumption"
            " — f needs to be holomorphic on $D \\setminus \\{p\\}$\n"
            r"  \ref{def:uniform_conv}: quantifier order"
            " — $\\forall\\varepsilon\\,\\exists\\delta$ should be reversed\n"
            r"  \begin{proof} of lem:cauchy_bound: ?"
            "  (flag for ambiguity, no clear error but something feels off)\n"
            "  ok  (if no issues found)"
        )
        return (
            "TASK:\n"
            "Find logical errors in the current chunk. Check against the error taxonomy.\n"
            "\n"
            "INPUTS YOU RECEIVE:\n"
            "- State object (focus chunk text, established results)\n"
            "- Your memory (what you already flagged in prior rounds — do not repeat resolved flags)\n"
            "\n"
            "OUTPUT FORMAT:\n"
            "One line per issue:\n"
            "  [LaTeX label or environment ref] [error type] [brief note]\n"
            "\n"
            "Reference locations using LaTeX labels and environment names, e.g.:\n"
            + flag_examples + "\n"
            "\n"
            "MEMORY NOTE:\n"
            "[one bullet: what you checked, what you cleared]\n"
            "\n"
            "SCOPE-AWARE BEHAVIOR (calibrate to SESSION SCOPE in the user message if present):\n"
            "- rigor=full: flag everything, including minor gaps and unstated assumptions.\n"
            "- rigor=sketch: flag only errors that make the argument logically invalid. Ignore incompleteness.\n"
            "- rigor=intuition_first: flag only outright false statements. Ignore gaps and incompleteness.\n"
            "\n"
            "CONSTRAINTS:\n"
            "- 150 tokens max output\n"
            "- Do not repeat flags you already raised in prior rounds unless they are still unresolved\n"
            "- Do not explain what logical errors are. Just find them.\n"
            '- "ok" is a complete and valid output\n'
            "- Use the error taxonomy from your skills as a checklist"
            + skills_block
        )

    def _build_user_message(self, state: RoundState, memory: AgentMemory, extra: dict) -> str:
        state_block = self._serialize_state(state)
        memory_block = self._serialize_memory(memory)

        return f"""{state_block}

---

{memory_block}

Check the focus chunk for logical errors now."""

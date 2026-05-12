from agents.base import BaseAgent
from config import Config
from models.state import AgentMemory, RoundState


class RepAgent(BaseAgent):
    """
    Developer (Rep) agent. Updates the current chunk based on the orchestrator's directive.
    May push back on the directive with a brief mathematical reason.
    """

    def __init__(self, config: Config):
        super().__init__("rep", config)

    def extract_chunk_content(self, raw: str) -> str:
        """Extract the chunk content between ---CHUNK--- and ---END CHUNK--- markers."""
        try:
            start = raw.index("---CHUNK---") + len("---CHUNK---")
            end = raw.index("---END CHUNK---")
            return raw[start:end].strip()
        except ValueError:
            # Markers not found — return the full response as the chunk content
            return raw.strip()

    def extract_pushback(self, raw: str) -> str:
        """Extract the PUSHBACK section if present."""
        if "PUSHBACK" not in raw:
            return ""
        try:
            start = raw.index("PUSHBACK") + len("PUSHBACK")
            # Find end: either MEMORY NOTE or end of string
            if "MEMORY NOTE" in raw[start:]:
                end = raw.index("MEMORY NOTE", start)
                return raw[start:end].strip().lstrip(":").strip()
            return raw[start:].strip().lstrip(":").strip()
        except ValueError:
            return ""

    def extract_memory_note(self, raw: str) -> str:
        """Extract the MEMORY NOTE section if present."""
        if "MEMORY NOTE" not in raw:
            return ""
        try:
            start = raw.index("MEMORY NOTE") + len("MEMORY NOTE")
            return raw[start:].strip().lstrip(":").strip()
        except ValueError:
            return ""

    # ------------------------------------------------------------------
    # BaseAgent interface
    # ------------------------------------------------------------------

    def _max_tokens(self) -> int:
        return self.config.max_tokens_rep

    def _build_system_prompt(self) -> str:
        skills_block = f"\n\n{self.skills}" if self.skills else ""
        return f"""TASK:
Update the current chunk of the mathematical manuscript based on the orchestrator's directive.
Write valid LaTeX content using AMS environments. No document preamble — chunk content only.

LATEX REQUIREMENTS:
- Use AMS environments: \\begin{{definition}}...\\end{{definition}}, \\begin{{theorem}}...\\end{{theorem}},
  \\begin{{proof}}...\\end{{proof}}, \\begin{{lemma}}...\\end{{lemma}},
  \\begin{{remark}}...\\end{{remark}}, \\begin{{corollary}}...\\end{{corollary}}
- Label every numbered environment: \\label{{def:name}}, \\label{{thm:name}}, \\label{{lem:name}}, etc.
- Inline math: $...$   Display math: \\[...\\] or \\begin{{align}}...\\end{{align}}
- Packages available: amsmath, amsthm, amssymb, mathtools, hyperref
- Cross-reference with \\ref{{label}} or \\autoref{{label}}

INPUTS YOU RECEIVE:
- State object (established results, open flags, round goal)
- Current chunk text (what exists so far)
- Orchestrator directive (a suggestion — you may push back)
- Your own memory (what you tried before, what worked)

OUTPUT FORMAT:
---CHUNK---
[complete updated chunk as LaTeX, no preamble]
---END CHUNK---

PUSHBACK (only if you disagree with the directive for a clear mathematical reason, otherwise omit):
[one sentence: the mathematical reason you are not following the directive]

MEMORY NOTE:
[one short bullet for your own memory — what you tried, what you established]

CONSTRAINTS:
- Output the complete chunk text, not a diff
- 600 tokens max for chunk content
- If approaching the token limit, sketch remaining steps as LaTeX comments:
  % Sketch: (1) verify X  (2) handle edge case Y — details deferred
  Do not truncate silently.
- Do not rewrite chunks that are already APPROVED{skills_block}"""

    def _build_user_message(self, state: RoundState, memory: AgentMemory, extra: dict) -> str:
        state_block = self._serialize_state(state)
        memory_block = self._serialize_memory(memory)

        injected_note = extra.get("user_note", "")
        note_section = ""
        if injected_note:
            note_section = f"\nUSER NOTE (injected):\n{injected_note}\n"

        return f"""{state_block}

---

{memory_block}
{note_section}
Update the chunk now."""

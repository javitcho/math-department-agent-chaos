from agents.base import BaseAgent
from config import Config
from models.state import AgentMemory, RoundState


class ReferenceAgent(BaseAgent):
    """
    Reference Critic agent. Checks the literature for prior art, citation correctness,
    cross-domain connections, and novelty. Cross-domain connections marked with !! trigger
    the SERENDIPITY stopping signal.
    Opt-in only — disabled by default (config.reference_critic_enabled).
    """

    needs_full_chunk: bool = False

    def __init__(self, config: Config):
        super().__init__("reference", config)

    def has_serendipity(self, output: str) -> bool:
        """Return True if the output contains a !! cross-domain connection marker."""
        return "!!" in output

    # ------------------------------------------------------------------
    # BaseAgent interface
    # ------------------------------------------------------------------

    def _max_tokens(self) -> int:
        return self.config.max_tokens_reference

    def _uses_search(self) -> bool:
        # The model uses its training knowledge; no actual web-search API required
        return False

    def _build_system_prompt(self) -> str:
        skills_block = f"\n\n{self.skills}" if self.skills else ""
        return f"""TASK:
Check the mathematical literature relevant to the current chunk.

INPUTS YOU RECEIVE:
- State object (focus chunk, topic)
- Your memory (what you already searched and found)

CHECK FOR:
1. Prior art: has this claim been proven before? By whom? Roughly when?
2. Citation correctness: are any cited theorems correctly attributed?
3. Better references: standard references the Rep should know about
4. CROSS-DOMAIN CONNECTIONS: unexpected links to other areas of mathematics.
   These are the most valuable finding. Flag them prominently.
5. Novelty: does anything appear genuinely new?

OUTPUT FORMAT:
PRIOR ART: [name, date, brief note — or "none found"]
CORRECTIONS: [list of citation issues referencing LaTeX labels, e.g. "\\ref{{thm:residue}}: attr. to wrong author" — or "none"]
CONNECTIONS: [any cross-domain links — be specific; reference chunk labels where relevant]
NOVEL: yes / no / unclear

MEMORY NOTE:
[one bullet: what you searched]

CONSTRAINTS:
- 250 tokens max output
- Do not repeat searches you already did (check your memory)
- If you find a cross-domain connection, mark it with !! so the orchestrator flags it
- "none found" is a complete and valid output for any section
- Output format is fixed. No headers, no sections, no markdown structure. Four fields only: PRIOR ART, CORRECTIONS, CONNECTIONS, NOVEL. Each field is one line or at most two lines. If you have more to say, cut it.{skills_block}"""

    def _build_user_message(self, state: RoundState, memory: AgentMemory, extra: dict) -> str:
        state_block = self._serialize_state(state, extra)
        memory_block = self._serialize_memory(memory)

        return f"""{state_block}

---

{memory_block}

Check the literature for the focus chunk now."""

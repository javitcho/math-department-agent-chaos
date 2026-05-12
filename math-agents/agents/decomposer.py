import json
import time

from agents.orchestrator import strip_json_fences
from agents.base import BaseAgent
from config import Config
from models.state import AgentMemory, RoundState
from models.signals import SessionMode, StoppingSignal


class DecomposerAgent(BaseAgent):
    """
    First agent called per session. Breaks the topic into a structured roadmap.
    Does not run again unless the orchestrator explicitly resets.
    Has no skills directory (relies on model knowledge).
    """

    def __init__(self, config: Config):
        super().__init__("decomposer", config)

    def decompose(self, topic: str) -> dict:
        """
        Decompose a topic string into a structured roadmap.
        Returns a parsed dict with chunks, claims, lemmas, etc.
        Falls back to a minimal single-chunk structure on error.
        """
        # Build a minimal state and memory to satisfy the BaseAgent interface
        state = RoundState(
            round=0,
            mode=SessionMode.SCOUT,
            established=[],
            current_chunk_id="decomposition",
            current_chunk_title="Initial Decomposition",
            focus_text=topic,
            open_flags=[],
            round_goal="Decompose the topic into a structured roadmap",
            directive_for_rep="",
        )
        memory = AgentMemory(agent_id="decomposer", session_id="init", entries=[])

        raw = self.call(state, memory, extra={"topic": topic})
        return self._parse_output(raw, topic)

    # ------------------------------------------------------------------
    # BaseAgent interface
    # ------------------------------------------------------------------

    def _max_tokens(self) -> int:
        return self.config.max_tokens_decomposer

    def _build_system_prompt(self) -> str:
        return """TASK:
Given a mathematical topic or theorem, produce a structured decomposition as a roadmap
for a research session.

OUTPUT FORMAT (JSON, no markdown fences):
{
  "core_claim": "the central statement or research question, one sentence",
  "key_definitions": ["def1", "def2"],
  "definitions_order": ["which definitions depend on which"],
  "lemmas_needed": ["lemma1 — brief description"],
  "proof_strategy": "suggested approach, 2-3 sentences max",
  "expected_connections": ["connection to other area — why it might appear"],
  "chunks": [
    {"id": "chunk_id", "title": "short title", "description": "one sentence"}
  ],
  "scout_priority": "which chunk to examine first in scout mode — id"
}

CONSTRAINTS:
- Chunks should map to logical units: one definition, one lemma, one proof step, one remark
- 4-8 chunks for a typical topic
- 500 tokens max total output
- No markdown fences in your output — raw JSON only"""

    def _build_user_message(self, state: RoundState, memory: AgentMemory, extra: dict) -> str:
        topic = extra.get("topic", state.focus_text)
        return f"""Decompose the following mathematical topic into a structured research roadmap:

TOPIC: {topic}

Produce the JSON roadmap now."""

    # ------------------------------------------------------------------
    # Parsing
    # ------------------------------------------------------------------

    def _parse_output(self, raw: str, topic: str) -> dict:
        try:
            cleaned = strip_json_fences(raw)
            data = json.loads(cleaned)

            # Ensure chunks is a list of dicts with required keys
            chunks = data.get("chunks", [])
            validated_chunks = []
            for i, c in enumerate(chunks):
                validated_chunks.append({
                    "id": c.get("id", f"chunk_{i+1}"),
                    "title": c.get("title", f"Chunk {i+1}"),
                    "description": c.get("description", ""),
                })
            data["chunks"] = validated_chunks
            data.setdefault("core_claim", topic)
            data.setdefault("key_definitions", [])
            data.setdefault("definitions_order", [])
            data.setdefault("lemmas_needed", [])
            data.setdefault("proof_strategy", "")
            data.setdefault("expected_connections", [])
            data.setdefault("scout_priority", validated_chunks[0]["id"] if validated_chunks else "chunk_1")
            data["raw"] = raw
            return data

        except Exception as e:
            print(f"[WARNING] Decomposer JSON parse failed: {e}")
            print(f"[WARNING] Raw decomposer output: {raw[:500]}")
            # Return a minimal single-chunk structure so the loop can continue
            return {
                "core_claim": topic,
                "key_definitions": [],
                "definitions_order": [],
                "lemmas_needed": [],
                "proof_strategy": "Standard approach",
                "expected_connections": [],
                "chunks": [{"id": "main_claim", "title": "Main Claim", "description": topic}],
                "scout_priority": "main_claim",
                "raw": raw,
                "parse_error": str(e),
            }

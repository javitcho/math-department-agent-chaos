import json

from agents.orchestrator import strip_json_fences
from agents.base import BaseAgent
from config import Config
from models.document import ChunkNode, rebuild_dependents, topological_sort
from models.signals import ChunkStatus, ChunkType, SessionMode
from models.state import AgentMemory, RoundState


_TYPE_MAP = {
    "definition": ChunkType.DEFINITION,
    "lemma":      ChunkType.LEMMA,
    "theorem":    ChunkType.THEOREM,
    "proof":      ChunkType.PROOF,
    "corollary":  ChunkType.COROLLARY,
    "remark":     ChunkType.REMARK,
    "section":    ChunkType.SECTION,
}


class DecomposerAgent(BaseAgent):
    """
    First agent called per session. Breaks the topic into a dependency graph.
    Does not run again unless the orchestrator explicitly resets.
    """

    def __init__(self, config: Config):
        super().__init__("decomposer", config)

    def decompose(self, topic: str) -> dict:
        """
        Decompose a topic string into a structured node graph.
        Returns a parsed dict with nodes, global_context, etc.
        Falls back to a minimal single-node structure on error.
        """
        state = RoundState(
            round=0,
            mode=SessionMode.SCOUT,
            established=[],
            current_chunk_id="decomposition",
            current_chunk_title="Initial Decomposition",
            focus_text=topic,
            open_flags=[],
            round_goal="Decompose the topic into a dependency graph",
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
Given a mathematical topic or theorem, produce a dependency graph of nodes
as a roadmap for a research session.

OUTPUT FORMAT (JSON, no markdown fences):
{
  "title": "short topic title",
  "nodes": [
    {
      "id": "def_rational",
      "title": "Definition: Rational Number",
      "type": "definition",
      "description": "one sentence",
      "depends_on": []
    },
    {
      "id": "thm_sqrt2",
      "title": "Theorem: sqrt(2) is irrational",
      "type": "theorem",
      "description": "one sentence",
      "depends_on": ["def_rational"]
    },
    {
      "id": "proof_sqrt2",
      "title": "Proof: sqrt(2) is irrational",
      "type": "proof",
      "description": "one sentence",
      "depends_on": ["thm_sqrt2", "def_rational"]
    }
  ],
  "global_context": "2-3 sentence summary of the topic",
  "scout_priority": "id of the most important node to examine first"
}

DEPENDENCY RULES:
- Every proof node must depend_on its theorem node
- Definitions depend on nothing unless one definition uses another
- Lemmas used in a proof must appear in that proof's depends_on
- A remark depends on the chunk it remarks on
- Aim for 3-8 nodes. One concept per node. No exceptions.

TYPE VALUES: definition | lemma | theorem | proof | corollary | remark | section

CONSTRAINTS:
- 400 tokens max output
- No markdown fences — raw JSON only
- depends_on lists only ids that appear in this nodes array"""

    def _build_user_message(self, state: RoundState, memory: AgentMemory, extra: dict) -> str:
        topic = extra.get("topic", state.focus_text)
        return (
            "Decompose the following mathematical topic into a dependency graph:\n\n"
            "TOPIC: " + topic + "\n\n"
            "Produce the JSON graph now."
        )

    # ------------------------------------------------------------------
    # Parsing
    # ------------------------------------------------------------------

    def _parse_output(self, raw: str, topic: str) -> dict:
        try:
            cleaned = strip_json_fences(raw)
            data = json.loads(cleaned)

            nodes_data = data.get("nodes", [])
            validated = []
            for i, n in enumerate(nodes_data):
                node_id = n.get("id", f"chunk_{i+1}")
                validated.append({
                    "id": node_id,
                    "title": n.get("title", f"Chunk {i+1}"),
                    "type": n.get("type", "section"),
                    "description": n.get("description", ""),
                    "depends_on": [d for d in n.get("depends_on", []) if isinstance(d, str)],
                })

            data["nodes"] = validated
            data.setdefault("title", topic)
            data.setdefault("global_context", "")
            data.setdefault("scout_priority", validated[0]["id"] if validated else "chunk_1")
            data["raw"] = raw
            return data

        except Exception as e:
            print(f"[WARNING] Decomposer JSON parse failed: {e}")
            print(f"[WARNING] Raw decomposer output: {raw[:500]}")
            return {
                "title": topic,
                "nodes": [{"id": "main_claim", "title": "Main Claim",
                            "type": "section", "description": topic, "depends_on": []}],
                "global_context": "",
                "scout_priority": "main_claim",
                "raw": raw,
                "parse_error": str(e),
            }

    def build_nodes(self, decomp: dict) -> dict:
        """
        Convert parsed decomp dict into a Dict[str, ChunkNode] with
        dependents populated and traversal_order computed.
        Returns {"nodes": ..., "traversal_order": ..., "global_context": ...}.
        """
        nodes_data = decomp.get("nodes", [])
        nodes: dict = {}
        for nd in nodes_data:
            chunk_type = _TYPE_MAP.get(nd.get("type", "section"), ChunkType.SECTION)
            nodes[nd["id"]] = ChunkNode(
                id=nd["id"],
                title=nd["title"],
                content=nd.get("description", ""),
                type=chunk_type,
                status=ChunkStatus.DRAFT,
                depends_on=nd.get("depends_on", []),
                dependents=[],
                round_created=0,
                round_last_modified=0,
            )

        rebuild_dependents(nodes)
        traversal_order = topological_sort(nodes)
        return {
            "nodes": nodes,
            "traversal_order": traversal_order,
            "global_context": decomp.get("global_context", ""),
        }

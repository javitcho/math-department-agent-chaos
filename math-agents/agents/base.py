import os
import time
from pathlib import Path
from typing import TYPE_CHECKING, Optional

from anthropic import Anthropic

from config import Config
from models.document import get_context_for_chunk
from models.state import AgentMemory, MemoryEntry, RoundState, SessionScope
from models.signals import StoppingSignal
from storage.memory_store import load_memory, save_memory


def _get_skills_dir() -> Path:
    """Return the absolute path to the skills/ directory."""
    return Path(__file__).parent.parent / "skills"


class BaseAgent:
    """
    Base class for all math-research agents.

    Subclasses must implement:
      _build_system_prompt() -> str
      _build_user_message(state, memory, extra) -> str

    Optionally override:
      _uses_search() -> bool  (default False)
      needs_full_chunk: bool  (default True — False truncates focus_text to 800 chars)
    """

    needs_full_chunk: bool = True

    def __init__(self, agent_id: str, config: Config):
        self.agent_id = agent_id
        self.config = config
        self.skills = self._load_skills()
        self._client: Optional[Anthropic] = None

    # ------------------------------------------------------------------
    # Public interface
    # ------------------------------------------------------------------

    def call(self, state: RoundState, memory: AgentMemory, extra: dict = None) -> str:
        """Call the agent: build prompts, hit the API, return raw text response."""
        if extra is None:
            extra = {}
        system = self._build_system_prompt()
        user = self._build_user_message(state, memory, extra)
        max_tokens = self._max_tokens()
        return self.call_api(system, user, max_tokens)

    def call_api(self, system: str, user: str, max_tokens: int, use_search: bool = False) -> str:
        """
        Call the Anthropic API with the given system + user messages.
        Respects the configured request delay and uses the model from config.
        """
        time.sleep(self.config.request_delay_seconds)
        client = self._get_client()
        response = client.messages.create(
            model=self.config.model,
            max_tokens=max_tokens,
            system=system,
            messages=[{"role": "user", "content": user}],
        )
        raw = response.content[0].text
        char_estimate = max_tokens * 4
        if len(raw) > char_estimate:
            print(f"[WARNING] {self.agent_id} output {len(raw)} chars exceeds ~{max_tokens}-token estimate")
        return raw

    def load_memory(self, session_id: str) -> AgentMemory:
        """Load this agent's memory for the given session."""
        return load_memory(self.agent_id, session_id)

    def save_memory(self, session_id: str, memory: AgentMemory) -> None:
        """Persist this agent's memory for the given session."""
        save_memory(memory, session_id)

    def compress_memory_if_needed(self, memory: AgentMemory) -> AgentMemory:
        """
        If entries exceed max_memory_entries, compress the oldest entries
        down to memory_compress_to by summarising them into a single entry.
        """
        if len(memory.entries) <= self.config.max_memory_entries:
            return memory

        # How many entries to compress
        n_compress = len(memory.entries) - self.config.memory_compress_to
        to_compress = memory.entries[:n_compress]
        keep = memory.entries[n_compress:]

        if not to_compress:
            return memory

        first_round = to_compress[0].round
        last_round = to_compress[-1].round
        notes = "; ".join(e.note for e in to_compress)
        chunk_ids = list({e.chunk_id for e in to_compress})
        summary_note = f"Summary of rounds {first_round}-{last_round}: {notes}"[:200]

        summary_entry = MemoryEntry(
            round=f"{first_round}-{last_round} summary",
            chunk_id=", ".join(chunk_ids),
            note=summary_note,
        )
        memory.entries = [summary_entry] + keep
        return memory

    # ------------------------------------------------------------------
    # Helpers for subclasses
    # ------------------------------------------------------------------

    def build_scope_context(self, scope: Optional[SessionScope]) -> str:
        """Serialize a SessionScope into a prompt block for agent system messages."""
        if scope is None:
            return ""
        return (
            "SESSION SCOPE:\n"
            f"Purpose: {scope.purpose}\n"
            f"Audience: {scope.audience}\n"
            f"Rigor: {scope.rigor}\n"
            f"Stopping preference: {scope.stopping_preference}\n"
            f"Tone: {scope.tone_notes if scope.tone_notes else 'standard'}\n"
            f"User focus: {scope.user_focus if scope.user_focus else 'none specified'}"
        )

    def _serialize_memory(self, memory: AgentMemory) -> str:
        """Serialize memory to a compact bulleted list for inclusion in user messages."""
        if not memory.entries:
            return "YOUR MEMORY (prior rounds):\n(none)"
        lines = ["YOUR MEMORY (prior rounds):"]
        for e in memory.entries:
            round_label = e.round if isinstance(e.round, str) else f"R{e.round}"
            lines.append(f"• {round_label} {e.chunk_id}: {e.note}")
        return "\n".join(lines)

    def _build_context(self, manuscript, chunk_id: str) -> str:
        """
        Build dependency-precise context for an agent.
        Focus chunk + direct dependencies (one hop only, truncated to 300 chars each).
        Never passes the full document.
        """
        node = manuscript.nodes.get(chunk_id)
        if node is None:
            return f"FOCUS CHUNK: {chunk_id}\n(not found)"

        lines = [f"FOCUS CHUNK ({node.type.value}): {node.title}"]
        focus = node.content or "[not yet written]"
        if not self.needs_full_chunk and len(focus) > 800:
            focus = focus[:800] + "\n[truncated]"
        lines.append(focus)

        deps = get_context_for_chunk(manuscript.nodes, chunk_id)
        if deps:
            lines.append("\nDIRECT DEPENDENCIES:")
            for dep in deps:
                dep_text = dep.content[:300] + ("..." if len(dep.content) > 300 else "")
                lines.append(f"  [{dep.type.value}] {dep.title}: {dep_text}")

        unresolved = [f for f in node.flags if not f.resolved]
        if unresolved:
            lines.append("\nUNRESOLVED FLAGS:")
            for flag in unresolved:
                lines.append(f"  [{flag.source_agent}] {flag.text}")

        return "\n".join(lines)

    def _serialize_state(self, state: RoundState, extra: dict = None) -> str:
        """
        Serialize context for agent user messages.
        When extra contains a 'manuscript', uses dependency-precise context via _build_context.
        Falls back to the full RoundState serialization otherwise.
        """
        manuscript = (extra or {}).get("manuscript")
        if manuscript is not None:
            ctx = self._build_context(manuscript, state.current_chunk_id)
            lines = [
                f"ROUND: {state.round}  MODE: {state.mode.value}",
                f"ROUND GOAL: {state.round_goal}",
                "",
                ctx,
            ]
            if state.open_flags:
                lines.append("\nOPEN FLAGS:")
                for flag in state.open_flags:
                    lines.append(f"  • {flag}")
            if state.directive_for_rep:
                lines.append(f"\nDIRECTIVE FOR REP: {state.directive_for_rep}")
            if state.scope is not None:
                lines.append("")
                lines.append(self.build_scope_context(state.scope))
            return "\n".join(lines)

        # Legacy path (no manuscript available)
        lines = [
            f"ROUND: {state.round}",
            f"MODE: {state.mode.value}",
            f"CHUNK: {state.current_chunk_id} — {state.current_chunk_title}",
            f"ROUND GOAL: {state.round_goal}",
            "",
            "ESTABLISHED:",
        ]
        for item in state.established:
            lines.append(f"  • {item}")

        lines.append("")
        lines.append("OPEN FLAGS:")
        if state.open_flags:
            for flag in state.open_flags:
                lines.append(f"  • {flag}")
        else:
            lines.append("  (none)")

        lines.append("")
        lines.append("PRIORITY ISSUES:")
        if state.priority_issues:
            for issue in state.priority_issues:
                lines.append(f"  • {issue}")
        else:
            lines.append("  (none)")

        lines.append("")
        lines.append(f"DIRECTIVE FOR REP: {state.directive_for_rep}")

        lines.append("")
        lines.append("FOCUS CHUNK TEXT:")
        focus = state.focus_text or "(empty)"
        if not self.needs_full_chunk and len(focus) > 800:
            focus = focus[:800] + "\n[truncated]"
        lines.append(focus)

        if state.scope is not None:
            lines.append("")
            lines.append(self.build_scope_context(state.scope))

        return "\n".join(lines)

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _get_client(self) -> Anthropic:
        if self._client is None:
            api_key = os.environ.get("ANTHROPIC_API_KEY")
            if not api_key:
                raise ValueError(
                    "ANTHROPIC_API_KEY not set. Add it to your .env file or environment."
                )
            self._client = Anthropic(api_key=api_key)
        return self._client

    def _load_skills(self) -> str:
        """
        Load all .md files from skills/{agent_id}/ and concatenate them.
        Returns an empty string if the directory does not exist.
        """
        skills_path = _get_skills_dir() / self.agent_id
        if not skills_path.exists():
            return ""
        parts = []
        for md_file in sorted(skills_path.glob("*.md")):
            try:
                parts.append(md_file.read_text(encoding="utf-8"))
            except Exception as e:
                print(f"[WARNING] Could not load skill file {md_file}: {e}")
        return "\n\n".join(parts)

    def _uses_search(self) -> bool:
        """Override in subclasses that use web search (e.g. Reference Critic)."""
        return False

    def _max_tokens(self) -> int:
        """Return the max output tokens for this agent. Override in subclasses."""
        return 400

    def _build_system_prompt(self) -> str:
        raise NotImplementedError

    def _build_user_message(self, state: RoundState, memory: AgentMemory, extra: dict) -> str:
        raise NotImplementedError

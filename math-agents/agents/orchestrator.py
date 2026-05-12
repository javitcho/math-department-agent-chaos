import json
import time
from typing import Optional

from agents.base import BaseAgent
from config import Config
from models.state import AgentMemory, RoundState
from models.signals import StoppingSignal


def strip_json_fences(text: str) -> str:
    """Remove markdown code fences (```json ... ```) from a string."""
    text = text.strip()
    if text.startswith("```"):
        lines = text.split("\n")
        if lines[-1].strip() == "```":
            text = "\n".join(lines[1:-1])
        else:
            text = "\n".join(lines[1:])
    return text.strip()


_SIGNAL_MAP = {
    "continue": StoppingSignal.CONTINUE,
    "serendipity": StoppingSignal.SERENDIPITY,
    "counterexample": StoppingSignal.COUNTEREXAMPLE,
    "converged": StoppingSignal.CONVERGED,
    "elegant": StoppingSignal.ELEGANT,
    "budget": StoppingSignal.BUDGET,
    "scout_pursue": StoppingSignal.SCOUT_PURSUE,
    "scout_drop": StoppingSignal.SCOUT_DROP,
    "scout_interesting": StoppingSignal.SCOUT_INTERESTING,
    "user_stop": StoppingSignal.USER_STOP,
    "incubate": StoppingSignal.INCUBATE,
}


class OrchestratorAgent(BaseAgent):
    """
    Session supervisor agent.

    Reads all other agent outputs, synthesises them, and produces the
    RoundState (as JSON) for the next round.  Also issues the stopping
    signal and a directive to the Rep.
    """

    def __init__(self, config: Config):
        super().__init__("orchestrator", config)

    # ------------------------------------------------------------------
    # High-level call: returns a dict with parsed orchestrator output
    # ------------------------------------------------------------------

    def synthesize(
        self,
        state: RoundState,
        memory: AgentMemory,
        rep_output: str,
        logic_flags: str,
        counterex_result: str,
        ref_notes: str = "",
        elegance_notes: str = "",
        scout_mode: bool = False,
    ) -> dict:
        """
        Call the orchestrator and return a parsed dict of its output.

        Falls back to a safe default dict (CONTINUE) if JSON parsing fails.
        """
        extra = {
            "rep_output": rep_output,
            "logic_flags": logic_flags,
            "counterex_result": counterex_result,
            "ref_notes": ref_notes,
            "elegance_notes": elegance_notes,
            "scout_mode": scout_mode,
        }
        raw = self.call(state, memory, extra)
        return self._parse_output(raw, state)

    # ------------------------------------------------------------------
    # BaseAgent interface
    # ------------------------------------------------------------------

    def _max_tokens(self) -> int:
        return self.config.max_tokens_orchestrator

    def _build_system_prompt(self) -> str:
        skills_block = f"\n\n{self.skills}" if self.skills else ""
        return f"""TASK:
Read the current round outputs from all agents. Produce the RoundState for the next round.

INPUTS YOU RECEIVE:
- Current chunk (text)
- Rep output (updated chunk draft + any pushback)
- Logic critic flags
- Counterexample hunter result
- Reference critic notes (deep mode only)
- Elegance critic assessment (deep mode only)
- Your own memory from prior rounds

OUTPUT FORMAT (JSON, no markdown fences):
{{
  "established": ["bullet", "bullet"],
  "current_chunk_id": "...",
  "open_flags": ["flag", "flag"],
  "round_goal": "one sentence",
  "directive_for_rep": "collegial suggestion, not command. Rep may disagree.",
  "stopping_signal": "continue | serendipity | counterexample | converged | elegant | budget | incubate | scout_pursue | scout_drop | scout_interesting",
  "stopping_reason": "one sentence",
  "priority_issues": ["issue1", "issue2", "issue3"],
  "advance_chunk": true,
  "memory_note": "one short bullet for your own memory",
  "scout_verdict": "PURSUE | DROP | INTERESTING",
  "scout_reason": "2 sentences max — only in scout mode"
}}

DECISION RULES:
- COUNTEREXAMPLE: if counterex hunter reports a valid, concrete counterexample → stopping_signal = "counterexample"
- SERENDIPITY: if reference critic flags a surprising cross-domain connection (marked !!) → stopping_signal = "serendipity"
- CONVERGED: if no agent reported a new issue this round AND last round also had none → stopping_signal = "converged"
- ADVANCE_CHUNK: set advance_chunk = true if chunk has no open flags after this round
- INCUBATE: if same flags appeared 3+ consecutive rounds with no progress → stopping_signal = "incubate"
- CONTINUE: default when none of the above apply

SCOUT MODE EXTRA (when scout_mode flag is set in input):
Evaluate whether the core claim is worth pursuing deeply. Set scout_verdict to:
  PURSUE — claim appears sound, no obvious counterexample, worth developing
  DROP — claim is false (counterexample found) or trivially wrong
  INTERESTING — unclear, ambiguous, or requires more context

CONSTRAINTS:
- Total output: 400 tokens max
- Be specific. "Rep should clarify the continuity assumption in step 2" not "Rep should improve the proof"
- Directive to Rep is a suggestion. Do not frame it as a command.
- Always output valid JSON. No markdown fences.{skills_block}"""

    def _build_user_message(self, state: RoundState, memory: AgentMemory, extra: dict) -> str:
        rep_output = extra.get("rep_output", "(not run)")
        logic_flags = extra.get("logic_flags", "(not run)")
        counterex_result = extra.get("counterex_result", "(not run)")
        ref_notes = extra.get("ref_notes", "(not run — scout mode)")
        elegance_notes = extra.get("elegance_notes", "(not run — scout mode)")
        scout_mode = extra.get("scout_mode", False)

        state_block = self._serialize_state(state)
        memory_block = self._serialize_memory(memory)

        scout_instruction = ""
        if scout_mode:
            scout_instruction = "\nSCOUT MODE: Include scout_verdict and scout_reason in your output.\n"

        return f"""{state_block}

---

AGENT OUTPUTS THIS ROUND:

REP OUTPUT:
{rep_output}

LOGIC CRITIC:
{logic_flags}

COUNTEREXAMPLE HUNTER:
{counterex_result}

REFERENCE CRITIC:
{ref_notes}

ELEGANCE CRITIC:
{elegance_notes}

---

{memory_block}
{scout_instruction}
Produce the next RoundState as JSON now."""

    # ------------------------------------------------------------------
    # Parsing
    # ------------------------------------------------------------------

    def _parse_output(self, raw: str, state: RoundState) -> dict:
        """
        Parse orchestrator JSON output with full fallback logic.
        Strips markdown fences, falls back to CONTINUE on any parse error.
        """
        try:
            cleaned = strip_json_fences(raw)
            data = json.loads(cleaned)

            # Normalise stopping signal
            signal_str = data.get("stopping_signal", "continue").lower()
            data["stopping_signal"] = _SIGNAL_MAP.get(signal_str, StoppingSignal.CONTINUE)

            # Ensure required fields have sensible defaults
            data.setdefault("established", state.established)
            data.setdefault("current_chunk_id", state.current_chunk_id)
            data.setdefault("open_flags", state.open_flags)
            data.setdefault("round_goal", "Continue development")
            data.setdefault("directive_for_rep", "Continue improving the chunk.")
            data.setdefault("stopping_reason", "")
            data.setdefault("priority_issues", [])
            data.setdefault("advance_chunk", False)
            data.setdefault("memory_note", "")
            data.setdefault("scout_verdict", None)
            data.setdefault("scout_reason", "")
            data["raw"] = raw
            return data

        except Exception as e:
            print(f"[WARNING] Orchestrator JSON parse failed: {e}")
            print(f"[WARNING] Raw orchestrator output: {raw[:500]}")
            return {
                "established": state.established,
                "current_chunk_id": state.current_chunk_id,
                "open_flags": state.open_flags,
                "round_goal": "Continue development",
                "directive_for_rep": "Continue improving the chunk.",
                "stopping_signal": StoppingSignal.CONTINUE,
                "stopping_reason": f"Parse error: {e}",
                "priority_issues": [],
                "advance_chunk": False,
                "memory_note": "",
                "scout_verdict": None,
                "scout_reason": "",
                "raw": raw,
                "synthesis": raw,   # surface raw output for display
            }

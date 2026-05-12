import json
import re
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
        skills_block = ("\n\n" + self.skills) if self.skills else ""
        return (
            "TASK:\n"
            "Read the current round outputs from all agents. Produce the RoundState for the next round.\n"
            "\n"
            "INPUTS YOU RECEIVE:\n"
            "- Current chunk (text)\n"
            "- Rep output (updated chunk draft + any pushback)\n"
            "- Logic critic flags\n"
            "- Counterexample hunter result\n"
            "- Reference critic notes (deep mode only)\n"
            "- Elegance critic assessment (deep mode only)\n"
            "- Your own memory from prior rounds\n"
            "\n"
            "OUTPUT FORMAT (JSON, no markdown fences):\n"
            "{\n"
            '  "established": ["max 3 bullets — key proven results only"],\n'
            '  "open_flags": ["flag1", "flag2"],\n'
            '  "round_goal": "one sentence",\n'
            '  "directive_for_rep": "at most 2 sentences. Collegial suggestion, not a command. Rep may disagree.",\n'
            '  "stopping_signal": "continue | serendipity | counterexample | converged | elegant | budget | incubate | scout_pursue | scout_drop | scout_interesting",\n'
            '  "stopping_reason": "one sentence",\n'
            '  "priority_issues": ["top issue 1", "top issue 2", "top issue 3 — max 3 items"],\n'
            '  "advance_chunk": true,\n'
            '  "memory_note": "one short bullet"\n'
            "}\n"
            "\n"
            "DECISION RULES:\n"
            '- COUNTEREXAMPLE: if counterex hunter reports a valid, concrete counterexample → "counterexample"\n'
            '- SERENDIPITY: if reference critic flags a cross-domain connection marked !! → "serendipity"\n'
            '- CONVERGED: no agent reported a new issue this round AND last round also had none → "converged"\n'
            "- ADVANCE_CHUNK: true if chunk has no open flags after this round\n"
            '- INCUBATE: same flags for 3+ consecutive rounds with no progress → "incubate"\n'
            "- CONTINUE: default\n"
            "\n"
            "SCOUT MODE (when indicated in input): add these two fields to the JSON:\n"
            '  "scout_verdict": "PURSUE | DROP | INTERESTING"\n'
            '  "scout_reason": "2 sentences max"\n'
            "\n"
            "CONSTRAINTS:\n"
            "- Output: 800 tokens max\n"
            "- established: cap at 3 bullets. Drop the least recent if over.\n"
            "- priority_issues: cap at 3. Rank by severity.\n"
            "- directive_for_rep: 2 sentences max. Be specific about which LaTeX label/step to fix.\n"
            "- Always output valid JSON. No markdown fences. No trailing commas.\n"
            "- If you are approaching the token limit, shorten established and priority_issues first."
            + skills_block
        )

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
        Parse orchestrator JSON output.
        On clean parse: normalise fields and cap list sizes.
        On failure: log warning then attempt partial extraction — never silently discard.
        """
        try:
            cleaned = strip_json_fences(raw)
            data = json.loads(cleaned)

            signal_str = data.get("stopping_signal", "continue").lower()
            data["stopping_signal"] = _SIGNAL_MAP.get(signal_str, StoppingSignal.CONTINUE)

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

            # Enforce caps
            data["established"] = data["established"][:3]
            data["priority_issues"] = data["priority_issues"][:3]

            data["raw"] = raw
            return data

        except Exception as e:
            print(f"[WARNING] Orchestrator JSON parse failed: {e}")
            print(f"[WARNING] Raw orchestrator output (first 600): {raw[:600]}")
            return self._extract_partial(raw, state)

    def _extract_partial(self, raw: str, state: RoundState) -> dict:
        """
        Salvage whatever fields survived a truncated or malformed JSON response.
        Partial information is better than a blank CONTINUE default.
        """
        # Seed with safe state-based defaults
        data: dict = {
            "established": state.established[:3],
            "current_chunk_id": state.current_chunk_id,
            "open_flags": list(state.open_flags),
            "round_goal": state.round_goal or "Continue development",
            "directive_for_rep": "",
            "stopping_signal": StoppingSignal.CONTINUE,
            "stopping_reason": "Partial parse — output was truncated",
            "priority_issues": [],
            "advance_chunk": False,
            "memory_note": "",
            "scout_verdict": None,
            "scout_reason": "",
            "raw": raw,
        }

        cleaned = strip_json_fences(raw)

        # Strategy 1: try closing the truncated JSON with various suffixes
        for suffix in ('"}', '"]}', '}', '"]}}'):
            try:
                partial = json.loads(cleaned + suffix)
                for k, v in partial.items():
                    if k == "stopping_signal":
                        data["stopping_signal"] = _SIGNAL_MAP.get(
                            str(v).lower(), StoppingSignal.CONTINUE
                        )
                    elif k in data:
                        data[k] = v
                break
            except Exception:
                continue

        # Strategy 2: regex extraction of individual fields from the raw text

        # stopping_signal
        if data["stopping_signal"] == StoppingSignal.CONTINUE:
            m = re.search(r'"stopping_signal"\s*:\s*"([^"]+)"', raw)
            if m:
                data["stopping_signal"] = _SIGNAL_MAP.get(
                    m.group(1).lower(), StoppingSignal.CONTINUE
                )

        # open_flags — also used as priority_issues seed if that field is missing
        m = re.search(r'"open_flags"\s*:\s*\[([^\]]*)', raw)
        if m:
            extracted_flags = re.findall(r'"([^"]+)"', m.group(1))
            if extracted_flags:
                data["open_flags"] = extracted_flags
                if not data["priority_issues"]:
                    data["priority_issues"] = extracted_flags[:3]

        # priority_issues (explicit field, if present before truncation)
        m = re.search(r'"priority_issues"\s*:\s*\[([^\]]*)', raw)
        if m:
            issues = re.findall(r'"([^"]+)"', m.group(1))
            if issues:
                data["priority_issues"] = issues[:3]

        # directive_for_rep — take what exists even if truncated, trim to last sentence boundary
        m = re.search(r'"directive_for_rep"\s*:\s*"([^"]*)', raw)
        if m:
            directive = m.group(1).strip()
            if len(directive) > 15:
                # Trim to the last complete sentence
                for end_char in (".", "?", "!"):
                    idx = directive.rfind(end_char)
                    if idx > 15:
                        directive = directive[: idx + 1]
                        break
                data["directive_for_rep"] = directive

        # Fall back: first complete sentence in raw that doesn't look like a JSON key
        if not data["directive_for_rep"]:
            json_key_pattern = re.compile(
                r'^("established|"open_flags|"round_goal|"stopping|"priority|"advance|"memory|"scout|"current|\{|\[)',
                re.IGNORECASE,
            )
            for sentence in re.split(r"(?<=[.!?])\s+", raw):
                s = sentence.strip().strip('"')
                if len(s) > 20 and not json_key_pattern.match(s):
                    data["directive_for_rep"] = s[:200]
                    break

        if not data["directive_for_rep"]:
            data["directive_for_rep"] = "Continue improving the chunk. Address the open flags."

        return data

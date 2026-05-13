import json
import re

from agents.base import BaseAgent
from config import Config
from models.state import AgentMemory, RoundState
from models.signals import StoppingSignal


def strip_json_fences(text: str) -> str:
    text = text.strip()
    if text.startswith("```"):
        lines = text.split("\n")
        text = "\n".join(lines[1:-1]) if lines[-1].strip() == "```" else "\n".join(lines[1:])
    return text.strip()


_SIGNAL_MAP = {
    "continue":          StoppingSignal.CONTINUE,
    "serendipity":       StoppingSignal.SERENDIPITY,
    "counterexample":    StoppingSignal.COUNTEREXAMPLE,
    "converged":         StoppingSignal.CONVERGED,
    "elegant":           StoppingSignal.ELEGANT,
    "budget":            StoppingSignal.BUDGET,
    "scout_pursue":      StoppingSignal.SCOUT_PURSUE,
    "scout_drop":        StoppingSignal.SCOUT_DROP,
    "scout_interesting": StoppingSignal.SCOUT_INTERESTING,
    "user_stop":         StoppingSignal.USER_STOP,
    "incubate":          StoppingSignal.INCUBATE,
}


class OrchestratorAgent(BaseAgent):
    """
    Session supervisor. Reads agent outputs, produces the four-field decision JSON.
    Does not regenerate established/open_flags/priority_issues — those are derived
    from session state in the loop.
    """

    needs_full_chunk: bool = False

    def __init__(self, config: Config):
        super().__init__("orchestrator", config)

    # ------------------------------------------------------------------
    # High-level call
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
            "Read the agent outputs from this round and decide the next step.\n"
            "\n"
            "OUTPUT FORMAT (JSON, no markdown fences):\n"
            "{\n"
            '  "directive_for_rep": "two sentences max — specific, collegial; cite the LaTeX label to fix",\n'
            '  "stopping_signal": "continue | serendipity | counterexample | converged | elegant | incubate | budget",\n'
            '  "stopping_reason": "one sentence",\n'
            '  "advance_chunk": true | false,\n'
            '  "modify_dependency": "chunk_id to redirect the Rep to fix instead, or null"\n'
            "}\n"
            "\n"
            "DECISION RULES:\n"
            '- COUNTEREXAMPLE: counterex hunter reports a concrete, valid counterexample → "counterexample"\n'
            '- SERENDIPITY: reference critic flags a cross-domain connection with !! → "serendipity"\n'
            '- CONVERGED: no agent reported a new issue this round AND previous round also had none → "converged"\n'
            '- ELEGANT: logic is clean AND elegance score ≥ 8 → "elegant"\n'
            '- INCUBATE: same flags for 3+ consecutive rounds, no progress → "incubate"\n'
            "- ADVANCE_CHUNK: true if this chunk should be considered done after this round\n"
            '- CONTINUE: default when more work is needed\n'
            "\n"
            "GRAPH AWARENESS:\n"
            "You are working on a dependency graph, not a linear document.\n"
            "The focus chunk may have dependents that will need re-review if it changes.\n"
            "If you direct the Rep to change a definition or lemma, state explicitly in\n"
            "your directive: 'note: this change will trigger re-review of [dependent chunk titles].'\n"
            "The system handles propagation automatically — you just need to flag it.\n"
            "modify_dependency: if the real fix belongs in a dependency chunk (not the focus chunk),\n"
            "set this to that dependency's id. The loop will redirect the Rep there and re-queue the\n"
            "current chunk after the dependency is approved. Set null if fixing focus chunk directly.\n"
            "When advance_chunk=true and the chunk type is definition or lemma, be aware that all\n"
            "dependent chunks will be automatically flagged for re-review.\n"
            "\n"
            "SCOUT MODE: when indicated, add two extra fields to the JSON:\n"
            '  "scout_verdict": "PURSUE | DROP | INTERESTING"\n'
            '  "scout_reason": "2 sentences max"\n'
            "  PURSUE: strong claim, clear path forward, no fatal issues.\n"
            "  DROP: fundamental flaw or trivial/already-known result.\n"
            "  INTERESTING: plausible but needs more work to evaluate.\n"
            "\n"
            "CONSTRAINTS:\n"
            "- 300 tokens max output\n"
            "- directive_for_rep: 2 sentences max, specific LaTeX label if applicable\n"
            "- No markdown fences. No trailing commas. Valid JSON only.\n"
            "- SCOPE-AWARE:\n"
            "  stopping_preference=stop_when_hard: INCUBATE after 2 rounds of same flags (not 3).\n"
            "  stopping_preference=push_through: INCUBATE only after 4+ rounds of same flags."
            + skills_block
        )

    def _build_user_message(self, state: RoundState, memory: AgentMemory, extra: dict) -> str:
        rep_output      = extra.get("rep_output", "(not run)")
        logic_flags     = extra.get("logic_flags", "(not run)")
        counterex_result = extra.get("counterex_result", "(not run)")
        ref_notes       = extra.get("ref_notes", "(not run)")
        elegance_notes  = extra.get("elegance_notes", "(skipped)")
        scout_mode      = extra.get("scout_mode", False)

        # Minimal context — orch does not need the full chunk text
        flags_str = ", ".join(state.open_flags) if state.open_flags else "(none)"
        context = (
            "ROUND " + str(state.round) + " — CHUNK: " + state.current_chunk_id
            + " (" + state.current_chunk_title + ")\n"
            "OPEN FLAGS: " + flags_str + "\n"
        )
        if state.scope and state.scope.stopping_preference != "natural":
            context += "STOPPING PREFERENCE: " + state.scope.stopping_preference + "\n"

        memory_block = self._serialize_memory(memory)
        scout_note = "\nSCOUT MODE: include scout_verdict and scout_reason.\n" if scout_mode else ""

        elegance_section = ""
        if elegance_notes and elegance_notes not in ("(skipped)", "(not run — scout mode)"):
            elegance_section = "\nELEGANCE CRITIC:\n" + elegance_notes + "\n"

        ref_section = ""
        if ref_notes and ref_notes not in ("(not run)", "(not run — scout mode)"):
            ref_section = "\nREFERENCE CRITIC:\n" + ref_notes + "\n"

        return (
            context + "\n---\n\n"
            "AGENT OUTPUTS THIS ROUND:\n\n"
            "REP:\n" + rep_output + "\n\n"
            "LOGIC CRITIC:\n" + logic_flags + "\n\n"
            "COUNTEREXAMPLE HUNTER:\n" + counterex_result
            + ref_section
            + elegance_section
            + "\n---\n\n"
            + memory_block
            + scout_note
            + "\nProduce the JSON decision now."
        )

    # ------------------------------------------------------------------
    # Parsing
    # ------------------------------------------------------------------

    def _parse_output(self, raw: str, state: RoundState) -> dict:
        try:
            cleaned = strip_json_fences(raw)
            data = json.loads(cleaned)

            signal_str = data.get("stopping_signal", "continue").lower()
            data["stopping_signal"] = _SIGNAL_MAP.get(signal_str, StoppingSignal.CONTINUE)

            data.setdefault("directive_for_rep", "Continue improving the chunk.")
            data.setdefault("stopping_reason", "")
            data.setdefault("advance_chunk", False)
            data.setdefault("modify_dependency", None)
            data.setdefault("memory_note", "")
            data.setdefault("scout_verdict", None)
            data.setdefault("scout_reason", "")
            data["raw"] = raw
            return data

        except Exception as e:
            print(f"[WARNING] Orchestrator JSON parse failed: {e}")
            print(f"[WARNING] Raw (first 400): {raw[:400]}")
            return self._extract_partial(raw, state)

    def _extract_partial(self, raw: str, state: RoundState) -> dict:
        data = {
            "directive_for_rep": "",
            "stopping_signal": StoppingSignal.CONTINUE,
            "stopping_reason": "Partial parse — output truncated",
            "advance_chunk": False,
            "modify_dependency": None,
            "memory_note": "",
            "scout_verdict": None,
            "scout_reason": "",
            "raw": raw,
        }

        cleaned = strip_json_fences(raw)
        for suffix in ('"}', "}"):
            try:
                partial = json.loads(cleaned + suffix)
                for k, v in partial.items():
                    if k == "stopping_signal":
                        data["stopping_signal"] = _SIGNAL_MAP.get(str(v).lower(), StoppingSignal.CONTINUE)
                    elif k in data:
                        data[k] = v
                break
            except Exception:
                continue

        # Regex fallbacks
        m = re.search(r'"stopping_signal"\s*:\s*"([^"]+)"', raw)
        if m:
            data["stopping_signal"] = _SIGNAL_MAP.get(m.group(1).lower(), StoppingSignal.CONTINUE)

        m = re.search(r'"directive_for_rep"\s*:\s*"([^"]*)', raw)
        if m:
            directive = m.group(1).strip()
            if len(directive) > 15:
                for end_char in (".", "?", "!"):
                    idx = directive.rfind(end_char)
                    if idx > 15:
                        directive = directive[: idx + 1]
                        break
                data["directive_for_rep"] = directive

        if not data["directive_for_rep"]:
            data["directive_for_rep"] = "Continue improving the chunk. Address any open flags."

        return data

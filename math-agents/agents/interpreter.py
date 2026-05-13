"""
Interpreter agent.

Runs once at session intake. Converts raw user input — however vague, conversational,
or malformed — into a structured SessionIntent dict plus an optional clarifying question.

Never called via the standard RoundState pipeline. Use interpret() directly.
"""

import json
import time

from agents.base import BaseAgent
from config import Config
from models.state import AgentMemory, RoundState, SessionScope


_INJECTION_PROMPT = """TASK:
Determine whether an injected user note during an active math session is a scope-change
instruction or a content instruction for the Rep.

You will receive the current SessionScope and the user's note.

OUTPUT FORMAT (JSON, no markdown fences):
{
  "is_scope_change": true | false,
  "scope_updates": {
    "purpose": "new value or null if unchanged",
    "audience": "new value or null if unchanged",
    "rigor": "new value or null if unchanged",
    "stopping_preference": "new value or null if unchanged",
    "tone_notes": "new value or null if unchanged"
  },
  "content_note": "note for the Rep if not a scope change, or empty string",
  "confirmation": "one sentence describing what changed, for display to user"
}

EXAMPLES:
"make it simpler" → is_scope_change=true, audience=undergraduate, rigor=sketch, tone_notes="keep it simple and readable"
"I want this for undergraduates" → is_scope_change=true, audience=undergraduate
"stop when things get hard" → is_scope_change=true, stopping_preference=stop_when_hard
"check the case n=4 specifically" → is_scope_change=false, content_note="check the case n=4 specifically"
"hey can we make this less formal" → is_scope_change=true, tone_notes="informal tone, less terse"
"actually ignore the generalization" → is_scope_change=false, content_note="ignore the generalization"
"this is just for fun now" → is_scope_change=true, purpose=fun, stopping_preference=natural, rigor=sketch

When in doubt lean toward is_scope_change=false. Notes that could go either way treat as content.
null means "no change to this field". 200 tokens max output."""


_SYSTEM_PROMPT = """TASK:
Read the user's raw input and extract a structured session intent. The input may be a precise
theorem statement, a vague feeling ("theorem 3 seems off"), a question that barely makes sense,
or a manuscript with a note attached. Handle all of these.

OUTPUT FORMAT (JSON, no markdown fences):
{
  "topic": "clean one-sentence statement of what to work on",
  "has_manuscript": true,
  "user_focus": "specific thing flagged by user, or empty string",
  "purpose": "paper | thesis | lecture_notes | fun | exploration | verbatim if unclear",
  "audience": "research | graduate | undergraduate | self | verbatim if unclear",
  "rigor": "full | sketch | intuition_first",
  "stopping_preference": "push_through | stop_when_hard | natural",
  "tone_notes": "any tone or style instructions extracted verbatim from the user input",
  "clarifying_question": "one question if topic is genuinely ambiguous, otherwise empty string"
}

RULES:
- Never refuse to interpret. Make a best-faith reading of anything.
- If the user said something like "this makes no sense to me": audience=undergraduate, rigor=intuition_first, tone_notes="explain from scratch".
- If the user said "stop when things get hard": stopping_preference=stop_when_hard.
- If the user said "this is just for fun": purpose=fun, stopping_preference=natural.
- If purpose/audience/rigor cannot be inferred, default to: purpose=exploration, audience=self, rigor=sketch.
- Only set clarifying_question if you genuinely cannot determine the mathematical object to work on. Scope ambiguity is fine — resolve with defaults. Topic ambiguity is not.
- Maximum one clarifying question. If you must ask, ask the most important one only.
- 300 tokens max output."""


def _strip_fences(text: str) -> str:
    text = text.strip()
    if text.startswith("```"):
        lines = text.split("\n")
        text = "\n".join(lines[1:-1]) if lines[-1].strip() == "```" else "\n".join(lines[1:])
    return text.strip()


class InterpreterAgent(BaseAgent):
    """
    Intake interpreter. Converts raw user text to a structured SessionIntent.
    Does not use RoundState — call interpret() directly.
    """

    def __init__(self, config: Config):
        super().__init__("interpreter", config)

    def interpret(self, raw_input: str, clarification_answer: str = "") -> dict:
        """
        Interpret raw user input. Returns a SessionIntent dict.

        If clarification_answer is provided, appends it to the input so the model
        can re-interpret with the extra context.
        """
        user_msg = raw_input.strip()
        if clarification_answer.strip():
            user_msg += f"\n\nUser clarification: {clarification_answer.strip()}"

        time.sleep(self.config.request_delay_seconds)
        try:
            raw = self.call_api(_SYSTEM_PROMPT, user_msg, max_tokens=300)
            return self._parse(raw)
        except Exception as e:
            print(f"[WARNING] Interpreter failed: {e}")
            return self._fallback(raw_input)

    def interpret_injection(self, note: str, current_scope: "SessionScope | None") -> dict:
        """
        Classify an injected note as a scope-change or content instruction.
        Returns a dict with is_scope_change, scope_updates, content_note, confirmation.
        """
        scope_ctx = ""
        if current_scope is not None:
            scope_ctx = (
                "CURRENT SCOPE:\n"
                "purpose=" + current_scope.purpose + "\n"
                "audience=" + current_scope.audience + "\n"
                "rigor=" + current_scope.rigor + "\n"
                "stopping_preference=" + current_scope.stopping_preference + "\n"
                "tone_notes=" + (current_scope.tone_notes or "none") + "\n\n"
            )
        user_msg = scope_ctx + "USER NOTE: " + note.strip()

        time.sleep(self.config.request_delay_seconds)
        try:
            raw = self.call_api(_INJECTION_PROMPT, user_msg, max_tokens=200)
            data = self._parse_injection(raw)
        except Exception as e:
            print(f"[WARNING] interpret_injection failed: {e}")
            data = self._fallback_injection(note)
        return data

    def to_scope(self, intent: dict) -> SessionScope:
        """Convert a parsed intent dict to a SessionScope object."""
        return SessionScope(
            purpose=intent.get("purpose", "exploration"),
            audience=intent.get("audience", "self"),
            rigor=intent.get("rigor", "sketch"),
            stopping_preference=intent.get("stopping_preference", "natural"),
            tone_notes=intent.get("tone_notes", ""),
            from_manuscript=bool(intent.get("has_manuscript", False)),
            user_focus=intent.get("user_focus", ""),
        )

    # ------------------------------------------------------------------
    # BaseAgent stubs — interpreter is never called via the round pipeline
    # ------------------------------------------------------------------

    def _build_system_prompt(self) -> str:
        return _SYSTEM_PROMPT

    def _build_user_message(self, state: RoundState, memory: AgentMemory, extra: dict) -> str:
        return extra.get("raw_input", "")

    def _max_tokens(self) -> int:
        return 300

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _parse(self, raw: str) -> dict:
        try:
            data = json.loads(_strip_fences(raw))
            data.setdefault("topic", "")
            data.setdefault("has_manuscript", False)
            data.setdefault("user_focus", "")
            data.setdefault("purpose", "exploration")
            data.setdefault("audience", "self")
            data.setdefault("rigor", "sketch")
            data.setdefault("stopping_preference", "natural")
            data.setdefault("tone_notes", "")
            data.setdefault("clarifying_question", "")
            return data
        except Exception as e:
            print(f"[WARNING] Interpreter parse failed: {e} — raw: {raw[:200]}")
            return self._fallback(raw)

    def _parse_injection(self, raw: str) -> dict:
        _NULL_UPDATES = {"purpose": None, "audience": None, "rigor": None,
                         "stopping_preference": None, "tone_notes": None}
        try:
            data = json.loads(_strip_fences(raw))
            data.setdefault("is_scope_change", False)
            data.setdefault("scope_updates", _NULL_UPDATES)
            data.setdefault("content_note", "")
            data.setdefault("confirmation", "Scope updated.")
            return data
        except Exception as e:
            print(f"[WARNING] inject parse failed: {e} — raw: {raw[:200]}")
            return self._fallback_injection(raw)

    def _fallback_injection(self, note: str) -> dict:
        return {
            "is_scope_change": False,
            "scope_updates": {"purpose": None, "audience": None, "rigor": None,
                              "stopping_preference": None, "tone_notes": None},
            "content_note": note,
            "confirmation": "",
        }

    def _fallback(self, raw_input: str) -> dict:
        return {
            "topic": raw_input[:200],
            "has_manuscript": False,
            "user_focus": "",
            "purpose": "exploration",
            "audience": "self",
            "rigor": "sketch",
            "stopping_preference": "natural",
            "tone_notes": "",
            "clarifying_question": "",
        }

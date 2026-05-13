import re

from agents.base import BaseAgent
from config import Config
from models.state import AgentMemory, RoundState


class RepAgent(BaseAgent):
    """
    Developer (Rep) agent. Updates the current chunk based on the orchestrator's directive.
    Outputs a DIFF block (for updates) or FULL block (for first drafts).
    May push back on the directive with a brief mathematical reason.
    """

    needs_full_chunk: bool = True

    def __init__(self, config: Config):
        super().__init__("rep", config)

    # ------------------------------------------------------------------
    # Diff / Full extraction
    # ------------------------------------------------------------------

    def apply_rep_output(self, raw: str, existing_content: str) -> tuple:
        """
        Apply rep output to existing chunk content.
        Returns (new_content, needs_full_rewrite_next_round).

        If the output is FULL format: return the new content directly.
        If DIFF format: apply each REPLACE→WITH in order.
          - If a REPLACE string is not found: log warning, return
            (existing_content, True) so the next round requests FULL.
        If neither marker found: fall back to treating output as FULL.
        """
        raw_s = raw.strip()

        if "FULL" in raw_s and "END FULL" in raw_s:
            content = self._extract_full(raw_s)
            if content is not None:
                return content, False

        if "DIFF" in raw_s and "END DIFF" in raw_s:
            diffs = self._parse_diffs(raw_s)
            if diffs:
                content = existing_content
                for replace_str, with_str in diffs:
                    if replace_str in content:
                        content = content.replace(replace_str, with_str, 1)
                    else:
                        print(f"[WARNING] Rep REPLACE string not found verbatim — requesting FULL next round")
                        return existing_content, True
                return content, False

        # Fallback: no markers found — treat entire non-metadata output as FULL
        content = self._strip_metadata(raw_s)
        return content, False

    def extract_pushback(self, raw: str) -> str:
        """Extract the PUSHBACK section if present."""
        if "PUSHBACK" not in raw:
            return ""
        try:
            start = raw.index("PUSHBACK") + len("PUSHBACK")
            end = raw.index("MEMORY NOTE", start) if "MEMORY NOTE" in raw[start:] else len(raw)
            return raw[start:end].strip().lstrip(":").strip()
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
        return (
            "TASK:\n"
            "Update the current mathematical chunk based on the orchestrator's directive.\n"
            "Write valid LaTeX content using AMS environments. No document preamble — chunk content only.\n"
            "\n"
            "LATEX REQUIREMENTS:\n"
            r"- Use AMS environments: \begin{definition}...\end{definition}, \begin{theorem}..., "
            r"\begin{proof}..., \begin{lemma}..., \begin{remark}..., \begin{corollary}..." "\n"
            r"- Label every numbered environment: \label{def:name}, \label{thm:name}, \label{lem:name}, etc." "\n"
            r"- Inline math: $...$   Display math: \[...\] or \begin{align}...\end{align}" "\n"
            "- Packages available: amsmath, amsthm, amssymb, mathtools, hyperref\n"
            r"- Cross-reference with \ref{label} or \autoref{label}" "\n"
            "\n"
            "OUTPUT FORMAT — choose ONE:\n"
            "\n"
            "If this is a FIRST DRAFT (focus_text is empty or very short):\n"
            "FULL\n"
            "[complete chunk as LaTeX, no preamble]\n"
            "END FULL\n"
            "\n"
            "If UPDATING existing content — output only what changed:\n"
            "DIFF\n"
            "REPLACE: [exact string to replace, verbatim from the chunk]\n"
            "WITH: [replacement string]\n"
            "END DIFF\n"
            "\n"
            "Multiple changes require multiple DIFF blocks, one per change.\n"
            "If your changes are so extensive that a diff would be longer than the original, output FULL instead.\n"
            "Do NOT rewrite content that has not changed.\n"
            "\n"
            "AFTER the FULL or DIFF block(s), optionally add:\n"
            "\n"
            "PUSHBACK: [one sentence — only if you disagree with the directive for a clear mathematical reason]\n"
            "\n"
            "MEMORY NOTE:\n"
            "[one short bullet for your memory — what you tried, what you established]\n"
            "\n"
            "SCOPE-AWARE BEHAVIOR (calibrate to SESSION SCOPE in the user message if present):\n"
            "- audience=undergraduate: define every term before use, add motivating sentence before each theorem.\n"
            "- audience=graduate: standard rigor, light motivation.\n"
            "- audience=research: terse prose, no motivation unless novel.\n"
            "- purpose=lecture_notes: add a brief intuition paragraph before each proof.\n"
            "- purpose=fun or purpose=exploration: less formal, more exploratory tone.\n"
            "- purpose=paper or purpose=thesis: precise mathematical prose.\n"
            "- tone_notes: follow verbatim if present.\n"
            "\n"
            "CONSTRAINTS:\n"
            "- 400 tokens max total output\n"
            "- If approaching the token limit on a FULL block, sketch remaining steps as LaTeX comments:\n"
            "  % Sketch: (1) verify X  (2) handle edge case Y — details deferred\n"
            "- Do not rewrite chunks that are already APPROVED"
            + skills_block
        )

    def _build_user_message(self, state: RoundState, memory: AgentMemory, extra: dict) -> str:
        state_block = self._serialize_state(state, extra)
        memory_block = self._serialize_memory(memory)

        injected_note = extra.get("user_note", "")
        note_section = f"\nUSER NOTE (injected):\n{injected_note}\n" if injected_note else ""

        force_full = extra.get("force_full", False)
        force_section = "\nNOTE: Your previous REPLACE string was not found. Output FULL format this round.\n" if force_full else ""

        return f"""{state_block}

---

{memory_block}
{note_section}{force_section}Update the chunk now."""

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _extract_full(self, raw: str):
        """Extract content between FULL and END FULL markers."""
        try:
            start = raw.index("FULL\n") + 5
            end = raw.index("\nEND FULL")
            return raw[start:end].strip()
        except ValueError:
            pass
        try:
            start = raw.index("FULL") + 4
            end = raw.index("END FULL")
            return raw[start:end].strip()
        except ValueError:
            return None

    def _parse_diffs(self, raw: str) -> list:
        """Parse all DIFF blocks. Returns list of (replace_str, with_str) tuples."""
        results = []
        lines = raw.split("\n")
        i = 0
        while i < len(lines):
            if lines[i].strip() == "DIFF":
                i += 1
                replace_lines = []
                with_lines = []
                # Collect REPLACE: lines until WITH:
                if i < len(lines) and lines[i].startswith("REPLACE:"):
                    replace_lines.append(lines[i][len("REPLACE:"):].lstrip("\n"))
                    i += 1
                    while i < len(lines) and not lines[i].startswith("WITH:") and lines[i].strip() != "END DIFF":
                        replace_lines.append(lines[i])
                        i += 1
                # Collect WITH: lines until END DIFF
                if i < len(lines) and lines[i].startswith("WITH:"):
                    with_lines.append(lines[i][len("WITH:"):].lstrip("\n"))
                    i += 1
                    while i < len(lines) and lines[i].strip() != "END DIFF":
                        with_lines.append(lines[i])
                        i += 1
                if i < len(lines) and lines[i].strip() == "END DIFF":
                    i += 1
                replace_str = "\n".join(replace_lines)
                with_str = "\n".join(with_lines)
                if replace_str or with_str:
                    results.append((replace_str, with_str))
            else:
                i += 1
        return results

    def _strip_metadata(self, raw: str) -> str:
        """Remove PUSHBACK and MEMORY NOTE sections, return body."""
        for marker in ("PUSHBACK", "MEMORY NOTE"):
            if marker in raw:
                raw = raw[: raw.index(marker)].rstrip()
        return raw.strip()

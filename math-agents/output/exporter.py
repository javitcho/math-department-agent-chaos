"""
Exporter — converts the in-memory Manuscript to output artifacts.

export_manuscript() → sessions/{id}/export/manuscript.md   (markdown, every round)
export_latex()      → sessions/{id}/export/manuscript.tex  (compilable LaTeX, every round)
"""

import shutil
import subprocess
from pathlib import Path
from typing import Union

from models.document import Manuscript
from models.signals import ChunkStatus


_STATUS_EMOJI = {
    ChunkStatus.DRAFT: "📝",
    ChunkStatus.UNDER_REVIEW: "🔍",
    ChunkStatus.FLAGGED: "⚠️",
    ChunkStatus.NEEDS_REWORK: "🔧",
    ChunkStatus.APPROVED: "✅",
    ChunkStatus.ABANDONED: "❌",
}


# ---------------------------------------------------------------------------
# Markdown export
# ---------------------------------------------------------------------------

def export_manuscript(manuscript: Manuscript, session_dir: Union[str, Path]) -> Path:
    session_dir = Path(session_dir)
    export_dir = session_dir / "export"
    export_dir.mkdir(parents=True, exist_ok=True)
    out_path = export_dir / "manuscript.md"

    lines = [
        f"# {manuscript.topic}",
        "",
        f"> **Session:** `{manuscript.session_id}`  ",
        f"> **Mode:** {manuscript.mode.value}  ",
        f"> **Created:** {manuscript.created_at.strftime('%Y-%m-%d %H:%M')}  ",
        "",
        "---",
        "",
    ]

    if manuscript.global_context:
        lines.append("## Established Results")
        lines.append("")
        for line in manuscript.global_context.splitlines():
            stripped = line.strip()
            if stripped:
                if not stripped.startswith("-") and not stripped.startswith("•"):
                    stripped = "- " + stripped
                lines.append(stripped)
        lines.append("")
        lines.append("---")
        lines.append("")

    lines.append("## Dependency Graph")
    lines.append("")

    approved_count = 0
    nodes_in_order = [
        manuscript.nodes[nid]
        for nid in manuscript.traversal_order
        if nid in manuscript.nodes
    ]

    for node in nodes_in_order:
        status_symbol = _STATUS_EMOJI.get(node.status, "?")
        is_current = node.id == manuscript.current_chunk_id

        current_marker = " ← current" if is_current else ""
        dep_str = f" (deps: {', '.join(node.depends_on)})" if node.depends_on else ""
        lines.append(f"### {node.title} `[{node.id}]`  {status_symbol}{current_marker}")
        lines.append("")
        lines.append(f"**Type:** {node.type.value}  ")
        lines.append(f"**Status:** {node.status.value}{dep_str}  ")

        unresolved = [f for f in node.flags if not f.resolved]
        if unresolved:
            flag_texts = ", ".join(f.text for f in unresolved)
            lines.append(f"**Open flags:** {flag_texts}  ")
        lines.append(f"**Last modified:** round {node.round_last_modified}  ")
        lines.append("")

        if node.content:
            lines.append(node.content)
        else:
            lines.append("*(no content yet)*")

        lines.append("")
        lines.append("---")
        lines.append("")

        if node.status == ChunkStatus.APPROVED:
            approved_count += 1

    total = len(manuscript.nodes)
    lines.append(f"*{approved_count}/{total} nodes approved.*")
    lines.append("")

    out_path.write_text("\n".join(lines), encoding="utf-8")
    return out_path


# ---------------------------------------------------------------------------
# LaTeX export
# ---------------------------------------------------------------------------

def export_latex(manuscript: Manuscript, session_dir: Union[str, Path]) -> Path:
    session_dir = Path(session_dir)
    export_dir = session_dir / "export"
    export_dir.mkdir(parents=True, exist_ok=True)
    tex_path = export_dir / "manuscript.tex"

    date_str = manuscript.created_at.strftime("%Y-%m-%d")
    title = _latex_escape(manuscript.topic)

    lines = [
        r"\documentclass{amsart}",
        r"\usepackage{amsmath, amsthm, amssymb, mathtools, hyperref}",
        "",
        r"% Theorem environments",
        r"\newtheorem{theorem}{Theorem}[section]",
        r"\newtheorem{lemma}[theorem]{Lemma}",
        r"\newtheorem{corollary}[theorem]{Corollary}",
        r"\newtheorem{proposition}[theorem]{Proposition}",
        r"\theoremstyle{definition}",
        r"\newtheorem{definition}[theorem]{Definition}",
        r"\newtheorem{example}[theorem]{Example}",
        r"\theoremstyle{remark}",
        r"\newtheorem{remark}[theorem]{Remark}",
        "",
        r"\title{" + title + "}",
        r"\date{" + date_str + "}",
        "",
        r"\begin{document}",
        r"\maketitle",
        "",
    ]

    if manuscript.global_context:
        lines.append(r"\begin{abstract}")
        for bullet in manuscript.global_context.splitlines():
            stripped = bullet.strip().lstrip("-").lstrip("•").strip()
            if stripped:
                lines.append(stripped)
        lines.append(r"\end{abstract}")
        lines.append("")

    nodes_in_order = [
        manuscript.nodes[nid]
        for nid in manuscript.traversal_order
        if nid in manuscript.nodes
    ]

    for node in nodes_in_order:
        is_approved = node.status == ChunkStatus.APPROVED

        if not is_approved:
            lines.append(
                r"% --- STATUS: " + node.status.value.upper()
                + " | node: " + node.id + " (" + node.type.value + ") ---"
            )
            unresolved = [f for f in node.flags if not f.resolved]
            for flag in unresolved:
                lines.append(r"% OPEN FLAG: " + flag.text)
            lines.append(r"\medskip\noindent\rule{\linewidth}{0.4pt}\medskip")
            lines.append("")

        if node.content:
            lines.append(node.content)
        else:
            lines.append(r"% (no content yet for node: " + node.title + ")")

        lines.append("")

        if not is_approved:
            lines.append(r"\medskip\noindent\rule{\linewidth}{0.4pt}\medskip")
            lines.append("")

    lines.append(r"\end{document}")
    lines.append("")

    tex_path.write_text("\n".join(lines), encoding="utf-8")
    _try_pdflatex(export_dir)
    return tex_path


def _try_pdflatex(export_dir: Path) -> None:
    if not shutil.which("pdflatex"):
        print("[INFO] pdflatex not found — skipping LaTeX compilation.")
        return
    try:
        subprocess.run(
            ["pdflatex", "-interaction=nonstopmode", "manuscript.tex"],
            cwd=export_dir,
            capture_output=True,
            timeout=60,
        )
    except Exception as e:
        print(f"[WARNING] pdflatex compilation failed: {e}")


def _latex_escape(text: str) -> str:
    replacements = [
        ("\\", r"\textbackslash{}"),
        ("&", r"\&"),
        ("%", r"\%"),
        ("$", r"\$"),
        ("#", r"\#"),
        ("_", r"\_"),
        ("{", r"\{"),
        ("}", r"\}"),
        ("~", r"\textasciitilde{}"),
        ("^", r"\textasciicircum{}"),
    ]
    for old, new in replacements:
        text = text.replace(old, new)
    return text


def export_to_file(manuscript: Manuscript, output_path: Union[str, Path]) -> Path:
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    sessions_root = Path(__file__).parent.parent / "sessions"
    session_dir = sessions_root / manuscript.session_id
    session_dir.mkdir(parents=True, exist_ok=True)

    source = export_manuscript(manuscript, session_dir)

    if source != output_path:
        output_path.write_text(source.read_text(encoding="utf-8"), encoding="utf-8")

    return output_path

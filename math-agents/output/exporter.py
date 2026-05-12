"""
Exporter — converts the in-memory Manuscript to a human-readable markdown file.
Written to sessions/{session_id}/export/manuscript.md after each round.
"""

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


def export_manuscript(manuscript: Manuscript, session_dir: Union[str, Path]) -> Path:
    """
    Render the Manuscript as markdown and write to
    {session_dir}/export/manuscript.md.

    Returns the path to the written file.
    """
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

    # Global context
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

    # Chunks
    lines.append("## Manuscript Chunks")
    lines.append("")

    approved_count = 0
    for chunk in manuscript.chunks:
        status_symbol = _STATUS_EMOJI.get(chunk.status, "?")
        is_current = chunk.id == manuscript.current_chunk_id

        current_marker = " ← current" if is_current else ""
        lines.append(f"### {chunk.title} `[{chunk.id}]`  {status_symbol}{current_marker}")
        lines.append("")
        lines.append(f"**Status:** {chunk.status.value}  ")
        if chunk.flags:
            lines.append(f"**Open flags:** {', '.join(chunk.flags)}  ")
        lines.append(f"**Last modified:** round {chunk.round_last_modified}  ")
        lines.append("")

        if chunk.content:
            lines.append(chunk.content)
        else:
            lines.append("*(no content yet)*")

        lines.append("")
        lines.append("---")
        lines.append("")

        if chunk.status == ChunkStatus.APPROVED:
            approved_count += 1

    # Footer
    total = len(manuscript.chunks)
    lines.append(f"*{approved_count}/{total} chunks approved.*")
    lines.append("")

    out_path.write_text("\n".join(lines), encoding="utf-8")
    return out_path


def export_to_file(manuscript: Manuscript, output_path: Union[str, Path]) -> Path:
    """
    Export the manuscript to an arbitrary file path (for --export CLI flag).
    """
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    # Reuse the same renderer but write to the target path
    sessions_root = Path(__file__).parent.parent / "sessions"
    session_dir = sessions_root / manuscript.session_id
    session_dir.mkdir(parents=True, exist_ok=True)

    # Write via the main exporter
    source = export_manuscript(manuscript, session_dir)

    # Copy to target path if different
    if source != output_path:
        output_path.write_text(source.read_text(encoding="utf-8"), encoding="utf-8")

    return output_path

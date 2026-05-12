"""
Rich terminal display for the math-agents system.

Color conventions:
  Green  — round header
  Blue   — Rep output
  Yellow — Logic Critic / Serendipity signals
  Red    — Counterex / Counterexample signal
  Cyan   — Reference Critic
  Magenta— Elegance Critic
  White/bold — Orchestrator
"""

from typing import Optional

from rich import box
from rich.console import Console
from rich.panel import Panel
from rich.rule import Rule
from rich.text import Text

from models.signals import StoppingSignal

console = Console()


# ---------------------------------------------------------------------------
# Round display
# ---------------------------------------------------------------------------

def display_round(
    round_num: int,
    chunk_title: str,
    rep_output: str,
    logic_flags: str,
    counterex_result: str,
    orch_output: dict,
    ref_notes: str = "",
    elegance_notes: str = "",
    mode: str = "deep",
) -> None:
    """Display a full round panel with all agent outputs."""

    # ---- Header rule
    console.print()
    console.rule(
        f"[bold green]ROUND {round_num} — {chunk_title}[/bold green]",
        style="green",
    )
    console.print()

    # ---- Rep output
    chunk_content = _extract_chunk_content(rep_output)
    pushback = _extract_section(rep_output, "PUSHBACK", ["MEMORY NOTE"])
    rep_text = chunk_content
    if pushback:
        rep_text += f"\n\n[italic]PUSHBACK:[/italic] {pushback}"

    console.print(Panel(
        rep_text,
        title="[bold blue]◎ REP[/bold blue]",
        border_style="blue",
        box=box.ROUNDED,
    ))

    # ---- Logic Critic
    flag_lines = [l for l in logic_flags.splitlines() if l.strip() and "MEMORY NOTE" not in l]
    flag_count = len([l for l in flag_lines if l.strip().lower() != "ok"])
    logic_label = f"[bold yellow]⊗ LOGIC[/bold yellow] [{flag_count} flag{'s' if flag_count != 1 else ''}]"
    console.print(Panel(
        "\n".join(flag_lines) if flag_lines else "ok",
        title=logic_label,
        border_style="yellow",
        box=box.ROUNDED,
    ))

    # ---- Counterexample Hunter
    found = "COUNTEREXAMPLE FOUND" in counterex_result.upper()
    cx_style = "bold red" if found else "red"
    console.print(Panel(
        counterex_result,
        title=f"[{cx_style}]⊘ COUNTEREX[/{cx_style}]",
        border_style="red",
        box=box.ROUNDED,
    ))

    # ---- Reference Critic (deep mode only)
    if mode == "deep" and ref_notes:
        console.print(Panel(
            ref_notes,
            title="[bold cyan]⊞ REFERENCE[/bold cyan]",
            border_style="cyan",
            box=box.ROUNDED,
        ))

    # ---- Elegance Critic (deep mode only)
    if mode == "deep" and elegance_notes:
        score = _extract_elegance_score(elegance_notes)
        score_label = f"score: {score}" if score > 0 else "score: N/A"
        console.print(Panel(
            elegance_notes,
            title=f"[bold magenta]◈ ELEGANCE[/bold magenta] [{score_label}]",
            border_style="magenta",
            box=box.ROUNDED,
        ))

    # ---- Orchestrator synthesis
    _display_orchestrator(orch_output)

    # ---- Stopping signal special panels
    signal = orch_output.get("stopping_signal", StoppingSignal.CONTINUE)
    if isinstance(signal, StoppingSignal):
        signal_val = signal
    else:
        signal_val = StoppingSignal.CONTINUE

    if signal_val == StoppingSignal.SERENDIPITY:
        _display_signal_panel(
            title="SERENDIPITY",
            reason=orch_output.get("stopping_reason", ""),
            style="yellow",
            symbol="✦",
        )
    elif signal_val == StoppingSignal.COUNTEREXAMPLE:
        _display_signal_panel(
            title="COUNTEREXAMPLE — HARD STOP",
            reason=orch_output.get("stopping_reason", ""),
            style="red",
            symbol="✗",
        )
    elif signal_val in (StoppingSignal.CONVERGED, StoppingSignal.ELEGANT):
        _display_signal_panel(
            title=signal_val.value.upper(),
            reason=orch_output.get("stopping_reason", "Chunk approved."),
            style="green",
            symbol="✓",
        )
    elif signal_val == StoppingSignal.INCUBATE:
        _display_signal_panel(
            title="INCUBATE — Pausing for human reflection",
            reason=orch_output.get("stopping_reason", ""),
            style="yellow",
            symbol="○",
        )

    console.print()


def _display_orchestrator(orch_output: dict) -> None:
    """Display orchestrator synthesis panel."""
    synthesis = orch_output.get("synthesis", "") or orch_output.get("raw", "")
    open_flags = orch_output.get("open_flags", [])
    directive = orch_output.get("directive_for_rep", "")
    signal = orch_output.get("stopping_signal", StoppingSignal.CONTINUE)
    signal_str = signal.value if isinstance(signal, StoppingSignal) else str(signal)
    round_goal = orch_output.get("round_goal", "")

    lines = []
    if round_goal:
        lines.append(f"[bold]Goal:[/bold] {round_goal}")
    if synthesis and synthesis != orch_output.get("raw"):
        lines.append(f"\n{synthesis}")

    if open_flags:
        lines.append("\n[bold]Open flags:[/bold]")
        for flag in open_flags:
            lines.append(f"  • {flag}")

    if directive:
        lines.append(f"\n[bold]To Rep:[/bold] {directive}")

    lines.append(f"\n[bold]Signal:[/bold] {signal_str.upper()}")

    # Scout verdict
    scout_verdict = orch_output.get("scout_verdict")
    scout_reason = orch_output.get("scout_reason", "")
    if scout_verdict:
        lines.append(f"\n[bold]Scout verdict:[/bold] {scout_verdict}")
        if scout_reason:
            lines.append(f"  {scout_reason}")

    console.print(Panel(
        "\n".join(lines),
        title="[bold white]◎ ORCHESTRATOR[/bold white]",
        border_style="white",
        box=box.ROUNDED,
    ))


def _display_signal_panel(title: str, reason: str, style: str, symbol: str) -> None:
    content = f"{reason}\n" if reason else ""
    if style == "yellow" and "SERENDIPITY" in title:
        content += "\nContinue? [y/n]"
    console.print(Panel(
        content.strip(),
        title=f"[bold {style}]  {symbol}  {title}[/bold {style}]",
        border_style=style,
        box=box.DOUBLE,
        padding=(1, 2),
    ))


# ---------------------------------------------------------------------------
# Scout summary display
# ---------------------------------------------------------------------------

def display_scout_result(
    topic: str,
    decomp: dict,
    rep_output: str,
    logic_flags: str,
    counterex_result: str,
    orch_output: dict,
) -> None:
    """Display the complete scout mode result."""
    console.print()
    console.rule("[bold green]SCOUT RESULT[/bold green]", style="green")
    console.print()

    # Topic and core claim
    core_claim = decomp.get("core_claim", topic)
    console.print(Panel(
        f"[bold]Topic:[/bold] {topic}\n[bold]Core claim:[/bold] {core_claim}",
        title="[bold green]TOPIC[/bold green]",
        border_style="green",
        box=box.ROUNDED,
    ))

    # Decomposition chunks
    chunks = decomp.get("chunks", [])
    if chunks:
        chunk_lines = [f"  {i+1}. [{c['id']}] {c['title']} — {c.get('description', '')}"
                       for i, c in enumerate(chunks)]
        console.print(Panel(
            "\n".join(chunk_lines),
            title="[bold green]ROADMAP[/bold green]",
            border_style="green",
            box=box.ROUNDED,
        ))

    # Display the round (scout uses one round with 3 agents)
    display_round(
        round_num=1,
        chunk_title=decomp.get("chunks", [{}])[0].get("title", "Scout Chunk") if decomp.get("chunks") else "Main Claim",
        rep_output=rep_output,
        logic_flags=logic_flags,
        counterex_result=counterex_result,
        orch_output=orch_output,
        mode="scout",
    )

    # Final verdict panel
    verdict = orch_output.get("scout_verdict", "INTERESTING")
    reason = orch_output.get("scout_reason", "")
    verdict_colors = {
        "PURSUE": "green",
        "DROP": "red",
        "INTERESTING": "yellow",
    }
    color = verdict_colors.get(verdict, "white")
    console.print(Panel(
        f"[bold {color}]{verdict}[/bold {color}]\n\n{reason}",
        title="[bold]SCOUT VERDICT[/bold]",
        border_style=color,
        box=box.DOUBLE,
        padding=(1, 2),
    ))
    console.print()


# ---------------------------------------------------------------------------
# Session listing display
# ---------------------------------------------------------------------------

def display_session_list(sessions: list) -> None:
    """Display a table of recent sessions."""
    if not sessions:
        console.print("[yellow]No sessions found.[/yellow]")
        return

    console.print()
    console.rule("[bold]Recent Sessions[/bold]")
    console.print()
    for s in sessions:
        if "error" in s:
            console.print(f"  [red]{s['session_id']}[/red]: error — {s['error']}")
        else:
            console.print(
                f"  [bold cyan]{s['session_id']}[/bold cyan]  "
                f"[green]{s['mode']}[/green]  "
                f"{s['topic'][:60]}  "
                f"[dim]{s['saved_at'][:19]}[/dim]"
            )
    console.print()


# ---------------------------------------------------------------------------
# Inspect display
# ---------------------------------------------------------------------------

def display_inspect(manuscript, state, memories) -> None:
    """Dump full session state without running agents."""
    console.print()
    console.rule(f"[bold]Inspect: {manuscript.session_id}[/bold]")
    console.print()

    # Manuscript overview
    lines = [
        f"[bold]Topic:[/bold] {manuscript.topic}",
        f"[bold]Mode:[/bold] {manuscript.mode.value}",
        f"[bold]Session:[/bold] {manuscript.session_id}",
        f"[bold]Created:[/bold] {manuscript.created_at}",
        f"[bold]Current chunk:[/bold] {manuscript.current_chunk_id}",
        "",
        "[bold]Global context:[/bold]",
        manuscript.global_context or "(none)",
    ]
    console.print(Panel("\n".join(lines), title="[bold green]Manuscript[/bold green]", border_style="green"))

    # Chunks
    for chunk in manuscript.chunks:
        chunk_lines = [
            f"[bold]Status:[/bold] {chunk.status.value}",
            f"[bold]Rounds:[/bold] created {chunk.round_created}, last modified {chunk.round_last_modified}",
            f"[bold]Approved rounds:[/bold] {chunk.approved_by_rounds}",
            f"[bold]Flags:[/bold] {chunk.flags or 'none'}",
            "",
            chunk.content or "(empty)",
        ]
        console.print(Panel(
            "\n".join(chunk_lines),
            title=f"[bold blue]Chunk: {chunk.id} — {chunk.title}[/bold blue]",
            border_style="blue",
        ))

    # Current state
    state_lines = [
        f"[bold]Round:[/bold] {state.round}",
        f"[bold]Signal:[/bold] {state.stopping_signal.value}",
        f"[bold]Goal:[/bold] {state.round_goal}",
        f"[bold]Open flags:[/bold] {state.open_flags or 'none'}",
    ]
    console.print(Panel("\n".join(state_lines), title="[bold white]Round State[/bold white]", border_style="white"))

    # Memory summaries
    for agent_id, mem in memories.items():
        if mem.entries:
            mem_lines = [f"  R{e.round} {e.chunk_id}: {e.note}" for e in mem.entries[-5:]]
            console.print(Panel(
                "\n".join(mem_lines),
                title=f"[bold magenta]Memory: {agent_id}[/bold magenta]",
                border_style="magenta",
            ))

    console.print()


# ---------------------------------------------------------------------------
# Simple helpers
# ---------------------------------------------------------------------------

def display_info(msg: str) -> None:
    console.print(f"[dim]{msg}[/dim]")


def display_warning(msg: str) -> None:
    console.print(f"[yellow][WARNING] {msg}[/yellow]")


def display_error(msg: str) -> None:
    console.print(f"[bold red][ERROR] {msg}[/bold red]")


def display_success(msg: str) -> None:
    console.print(f"[bold green]{msg}[/bold green]")


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _extract_chunk_content(rep_output: str) -> str:
    """Extract content between ---CHUNK--- markers, or return full output."""
    try:
        start = rep_output.index("---CHUNK---") + len("---CHUNK---")
        end = rep_output.index("---END CHUNK---")
        return rep_output[start:end].strip()
    except ValueError:
        return rep_output.strip()


def _extract_section(text: str, start_marker: str, end_markers: list) -> str:
    """Extract a named section from agent output."""
    if start_marker not in text:
        return ""
    try:
        start = text.index(start_marker) + len(start_marker)
        end = len(text)
        for em in end_markers:
            if em in text[start:]:
                candidate = text.index(em, start)
                if candidate < end:
                    end = candidate
        return text[start:end].strip().lstrip(":").strip()
    except ValueError:
        return ""


def _extract_elegance_score(elegance_output: str) -> int:
    """Extract numeric score from SCORE: N in elegance output."""
    for line in elegance_output.splitlines():
        if line.upper().startswith("SCORE:"):
            try:
                return int(line.split(":", 1)[1].strip().split()[0])
            except (ValueError, IndexError):
                pass
    return 0

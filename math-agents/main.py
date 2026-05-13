"""
main.py — CLI entry point for the Math Research Multi-Agent System.

Usage:
  # Classic: topic only
  python main.py --topic "prove that √2 is irrational" --mode scout
  python main.py --topic "X" --mode deep

  # Freeform input — interpreter handles it
  python main.py --input "i want to understand why the residue theorem works geometrically"

  # From an existing manuscript
  python main.py --manuscript path/to/file.tex
  python main.py --manuscript path/to/file.tex --note "theorem 3 feels incomplete"

  # Explicit scope overrides (all optional; interpreter infers if omitted)
  python main.py --topic "X" --purpose fun --audience undergraduate --rigor sketch
  python main.py --topic "X" --tone "keep it readable, add examples"

  # Session management
  python main.py --session abc123
  python main.py --session abc123 --note "check isolated singularities"
  python main.py --session abc123 --export
  python main.py --list
  python main.py --session abc123 --inspect
"""

import os
import sys
from pathlib import Path

import click
from dotenv import load_dotenv

# Load .env before anything else
_env_path = Path(__file__).parent / ".env"
load_dotenv(dotenv_path=_env_path)

from config import Config
from models.signals import SessionMode
from models.state import SessionScope
from output.display import (
    console,
    display_info,
    display_warning,
    display_error,
    display_success,
    display_session_list,
    display_inspect,
    display_scope_confirmation,
)
from storage.session_store import load_session, list_sessions, save_session


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

@click.command()
@click.option("--topic",      "-t",  default=None,  help="Start a new session with this topic.")
@click.option("--input",      "freeform_input", default=None, help="Freeform input — interpreter extracts topic and scope.")
@click.option("--manuscript", "-m",  default=None,  help="Path to an existing .tex / .md / .txt file to work from.")
@click.option("--mode",              type=click.Choice(["scout", "deep"], case_sensitive=False), default=None,
              help="Session mode: scout (quick verdict) or deep (full development). Default: scout.")
@click.option("--session",    "-s",  default=None,  help="Resume an existing session by ID.")
@click.option("--note",       "-n",  default=None,  help="Inject a note into the next round, or focus hint for manuscript.")
@click.option("--export",     "do_export",  is_flag=True, default=False, help="Export session to markdown + LaTeX.")
@click.option("--list",       "do_list",    is_flag=True, default=False, help="List recent sessions.")
@click.option("--inspect",    "do_inspect", is_flag=True, default=False, help="Dump session state without running agents.")
@click.option("--verbose",    "-v",  is_flag=True, default=False, help="Verbose output.")
@click.option("--serve",      "do_serve", is_flag=True, default=False, help="Start the web app server on localhost:5000.")
@click.option("--no-open",    "no_open",  is_flag=True, default=False, help="Don't open browser when using --serve.")
@click.option("--with-references", "with_references", is_flag=True, default=False,
              help="Enable the Reference Critic (disabled by default to save tokens).")
# Explicit scope overrides
@click.option("--purpose",    default=None, help="Session purpose: paper | thesis | lecture_notes | fun | exploration")
@click.option("--audience",   default=None, help="Audience: research | graduate | undergraduate | self")
@click.option("--rigor",      default=None, help="Rigor level: full | sketch | intuition_first")
@click.option("--tone",       default=None, help="Tone / style notes (free text).")
def main(topic, freeform_input, manuscript, mode, session, note, do_export, do_list,
         do_inspect, verbose, do_serve, no_open, with_references, purpose, audience, rigor, tone):
    """Math Research Multi-Agent System — multi-agent mathematical idea development."""

    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        display_error("ANTHROPIC_API_KEY not set. Add it to your .env file:\n  ANTHROPIC_API_KEY=sk-...")
        sys.exit(1)

    config = Config(verbose=verbose)
    if with_references:
        config.reference_critic_enabled = True

    # ---- --serve
    if do_serve:
        import threading
        import webbrowser
        import uvicorn
        if not no_open:
            threading.Timer(1.5, lambda: webbrowser.open("http://localhost:5173")).start()
        display_info("Starting web server on http://localhost:5000")
        display_info("Frontend dev server: cd math-agents/web && npm run dev")
        uvicorn.run("server.app:app", host="127.0.0.1", port=5000, reload=True)
        return

    # ---- --list
    if do_list:
        display_session_list(list_sessions())
        return

    # ---- --session --inspect
    if session and do_inspect:
        _cmd_inspect(session)
        return

    # ---- --session --export
    if session and do_export:
        _cmd_export(session)
        return

    # ---- --session (resume)
    if session:
        _cmd_resume(session, config, note)
        return

    # ---- New session: topic / input / manuscript
    if topic or freeform_input or manuscript:
        resolved_mode = mode or "scout"
        config.default_mode = SessionMode.DEEP if resolved_mode == "deep" else SessionMode.SCOUT

        scope_overrides = {k: v for k, v in
                           [("purpose", purpose), ("audience", audience),
                            ("rigor", rigor), ("tone_notes", tone)]
                           if v is not None}

        if manuscript:
            _cmd_manuscript(manuscript, note or "", resolved_mode, scope_overrides, config)
        else:
            raw = freeform_input or topic
            _cmd_new(raw, resolved_mode, scope_overrides, config)
        return

    click.echo(click.get_current_context().get_help())


# ---------------------------------------------------------------------------
# Intake: interpreter + scope confirmation
# ---------------------------------------------------------------------------

def _run_intake(
    raw_input: str,
    scope_overrides: dict,
    config: Config,
    from_manuscript: bool = False,
) -> SessionScope:
    """
    Run the interpreter on raw_input, apply explicit overrides, confirm with user.
    Returns the confirmed SessionScope.
    """
    from agents.interpreter import InterpreterAgent

    interp = InterpreterAgent(config)
    display_info("[Intake] Interpreting input...")
    intent = interp.interpret(raw_input)

    # One clarifying exchange if topic is ambiguous
    question = intent.get("clarifying_question", "")
    if question:
        console.print(f"\n[cyan]?[/cyan] {question}")
        try:
            answer = input("> ").strip()
        except (EOFError, KeyboardInterrupt):
            answer = ""
        if answer:
            display_info("[Intake] Re-interpreting with clarification...")
            intent = interp.interpret(raw_input, clarification_answer=answer)

    # Build scope from interpreted intent
    scope = interp.to_scope(intent)
    scope.from_manuscript = from_manuscript

    # Apply explicit CLI overrides
    if "purpose"    in scope_overrides: scope.purpose               = scope_overrides["purpose"]
    if "audience"   in scope_overrides: scope.audience              = scope_overrides["audience"]
    if "rigor"      in scope_overrides: scope.rigor                 = scope_overrides["rigor"]
    if "tone_notes" in scope_overrides: scope.tone_notes            = scope_overrides["tone_notes"]

    return scope, intent.get("topic", raw_input)


# ---------------------------------------------------------------------------
# Command implementations
# ---------------------------------------------------------------------------

def _cmd_new(raw_input: str, mode_str: str, scope_overrides: dict, config: Config):
    """Start a new session from a topic or freeform input string."""
    scope, topic = _run_intake(raw_input, scope_overrides, config)

    scope = display_scope_confirmation(scope, topic, mode_str)

    if mode_str == "deep":
        _run_deep_mode(topic, config, scope=scope)
    else:
        _run_scout_mode(topic, config, scope=scope)


def _cmd_manuscript(
    filepath: str,
    note: str,
    mode_str: str,
    scope_overrides: dict,
    config: Config,
):
    """Parse an existing manuscript file and start a session focused on it."""
    from storage.manuscript_parser import parse_manuscript

    raw_for_interp = note if note else f"Working from manuscript: {Path(filepath).name}"
    scope, _ = _run_intake(raw_for_interp, scope_overrides, config, from_manuscript=True)
    scope.user_focus = note or scope.user_focus

    topic = Path(filepath).stem.replace("_", " ").replace("-", " ")
    scope = display_scope_confirmation(scope, topic, mode_str)

    display_info(f"[Intake] Parsing manuscript: {filepath}")
    try:
        mode = SessionMode.DEEP if mode_str == "deep" else SessionMode.SCOUT
        manuscript = parse_manuscript(
            filepath=filepath,
            user_focus=scope.user_focus,
            config=config,
            mode=mode,
            scope=scope,
        )
    except Exception as e:
        display_error(f"Could not parse manuscript: {e}")
        sys.exit(1)

    display_success(
        f"Parsed {len(manuscript.chunks)} chunks. "
        f"Focus: {manuscript.current_chunk_id}"
    )

    from storage.session_store import save_session
    from models.state import RoundState, AgentMemory
    from models.signals import StoppingSignal

    state = RoundState(
        round=0,
        mode=mode,
        established=[f"Source document: {manuscript.topic}"],
        current_chunk_id=manuscript.current_chunk_id,
        current_chunk_title=next(
            (c.title for c in manuscript.chunks if c.id == manuscript.current_chunk_id),
            manuscript.current_chunk_id,
        ),
        focus_text="",
        open_flags=[],
        round_goal=f"Focus on: {scope.user_focus or manuscript.current_chunk_id}",
        directive_for_rep="Review and develop the focus chunk.",
        scope=scope,
    )
    agent_ids = ["rep", "logic_critic", "counterex", "reference", "elegance", "orchestrator"]
    memories = {aid: AgentMemory(aid, manuscript.session_id) for aid in agent_ids}
    save_session(manuscript, state, memories)

    if mode_str == "deep":
        from loop.deep import run_deep
        try:
            result = run_deep(
                topic=manuscript.topic,
                config=config,
                existing_manuscript=manuscript,
                existing_state=state,
                existing_memories=memories,
                scope=scope,
            )
            _report_deep_result(result)
        except KeyboardInterrupt:
            display_info("\nInterrupted.")
        except Exception as e:
            display_error(f"Deep session failed: {e}")
            if os.environ.get("DEBUG"):
                raise
    else:
        from loop.scout import run_scout
        try:
            result = run_scout(manuscript.topic, config, scope=scope)
            _report_scout_result(result)
        except KeyboardInterrupt:
            display_info("\nInterrupted.")
        except Exception as e:
            display_error(f"Scout session failed: {e}")
            if os.environ.get("DEBUG"):
                raise


def _cmd_resume(session_id: str, config: Config, note: str = None):
    """Resume an existing session."""
    try:
        manuscript, state, memories = load_session(session_id)
    except FileNotFoundError:
        display_error(f"Session '{session_id}' not found.")
        sys.exit(1)
    except Exception as e:
        display_error(f"Could not load session '{session_id}': {e}")
        sys.exit(1)

    display_info(f"Resuming session {session_id}: {manuscript.topic}")

    from loop.deep import run_deep
    try:
        result = run_deep(
            topic=manuscript.topic,
            config=config,
            existing_manuscript=manuscript,
            existing_state=state,
            existing_memories=memories,
            session_id=session_id,
            injected_note=note,
        )
        _report_deep_result(result)
    except KeyboardInterrupt:
        display_info("\nInterrupted.")
    except Exception as e:
        display_error(f"Session failed: {e}")
        if os.environ.get("DEBUG"):
            raise


def _cmd_export(session_id: str):
    """Export session manuscript to markdown and LaTeX."""
    try:
        manuscript, state, memories = load_session(session_id)
    except FileNotFoundError:
        display_error(f"Session '{session_id}' not found.")
        sys.exit(1)
    except Exception as e:
        display_error(f"Could not load session '{session_id}': {e}")
        sys.exit(1)

    from output.exporter import export_manuscript, export_latex
    sessions_root = Path(__file__).parent / "sessions"
    session_dir = sessions_root / session_id
    md_path = export_manuscript(manuscript, session_dir)
    display_success(f"Markdown exported to: {md_path}")
    tex_path = export_latex(manuscript, session_dir)
    display_success(f"LaTeX exported to:   {tex_path}")


def _cmd_inspect(session_id: str):
    """Dump full session state without running agents."""
    try:
        manuscript, state, memories = load_session(session_id)
    except FileNotFoundError:
        display_error(f"Session '{session_id}' not found.")
        sys.exit(1)
    except Exception as e:
        display_error(f"Could not load session '{session_id}': {e}")
        sys.exit(1)

    display_inspect(manuscript, state, memories)

    if manuscript.scope:
        from rich.panel import Panel
        from rich import box
        s = manuscript.scope
        lines = [
            f"Purpose:  {s.purpose}",
            f"Audience: {s.audience}",
            f"Rigor:    {s.rigor}",
            f"Stopping: {s.stopping_preference}",
            f"Tone:     {s.tone_notes or 'standard'}",
            f"Focus:    {s.user_focus or 'none'}",
            f"From manuscript: {s.from_manuscript}",
        ]
        console.print(Panel(
            "\n".join(lines),
            title="[bold cyan]Session Scope[/bold cyan]",
            border_style="cyan",
            box=box.ROUNDED,
        ))


# ---------------------------------------------------------------------------
# Mode runners
# ---------------------------------------------------------------------------

def _run_scout_mode(topic: str, config: Config, scope=None):
    from loop.scout import run_scout
    try:
        result = run_scout(topic, config, scope=scope)
        _report_scout_result(result)
    except KeyboardInterrupt:
        display_info("\nInterrupted.")
    except Exception as e:
        display_error(f"Scout session failed: {e}")
        if os.environ.get("DEBUG"):
            raise


def _run_deep_mode(topic: str, config: Config, scope=None):
    from loop.deep import run_deep
    try:
        result = run_deep(topic, config, scope=scope)
        _report_deep_result(result)
    except KeyboardInterrupt:
        display_info("\nInterrupted.")
    except Exception as e:
        display_error(f"Deep session failed: {e}")
        if os.environ.get("DEBUG"):
            raise


def _report_scout_result(result: dict):
    verdict = result.get("verdict", "INTERESTING")
    session_id = result.get("session_id", "?")
    display_success(f"\nScout complete. Verdict: {verdict}. Session: {session_id}")
    display_info(f"Resume with:  python main.py --session {session_id}")
    display_info(f"Go deep with: python main.py --session {session_id} --mode deep")


def _report_deep_result(result: dict):
    session_id = result.get("session_id", "?")
    reason = result.get("exit_reason", "complete")
    display_success(f"\nDeep session ended: {reason}. Session: {session_id}")
    display_info(f"Export with:  python main.py --session {session_id} --export")
    display_info(f"Inspect with: python main.py --session {session_id} --inspect")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    main()

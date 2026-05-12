"""
main.py — CLI entry point for the Math Research Multi-Agent System.

Usage:
  python main.py --topic "prove that √2 is irrational" --mode scout
  python main.py --topic "X" --mode deep
  python main.py --session abc123
  python main.py --session abc123 --note "check the isolated singularity case"
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
from output.display import (
    console,
    display_info,
    display_warning,
    display_error,
    display_success,
    display_session_list,
    display_inspect,
)
from storage.session_store import load_session, list_sessions, save_session


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

@click.command()
@click.option("--topic", "-t", default=None, help="Start a new session with this topic.")
@click.option(
    "--mode", "-m",
    type=click.Choice(["scout", "deep"], case_sensitive=False),
    default=None,
    help="Session mode: scout (quick verdict) or deep (full development). Default: scout.",
)
@click.option("--session", "-s", default=None, help="Resume an existing session by ID.")
@click.option("--note", "-n", default=None, help="Inject a note into the next round of a resumed session.")
@click.option("--export", "do_export", is_flag=True, default=False, help="Export session manuscript to markdown.")
@click.option("--list", "do_list", is_flag=True, default=False, help="List recent sessions.")
@click.option("--inspect", "do_inspect", is_flag=True, default=False, help="Dump session state without running agents.")
@click.option("--verbose", "-v", is_flag=True, default=False, help="Verbose output.")
def main(topic, mode, session, note, do_export, do_list, do_inspect, verbose):
    """
    Math Research Multi-Agent System.
    Orchestrates a team of AI agents to develop and critique mathematical ideas.
    """

    # ---- Validate API key
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        display_error("ANTHROPIC_API_KEY not set. Add it to your .env file:\n  ANTHROPIC_API_KEY=sk-...")
        sys.exit(1)

    # ---- Build config
    config = Config(verbose=verbose)
    if mode == "deep":
        config.default_mode = SessionMode.DEEP
    else:
        config.default_mode = SessionMode.SCOUT

    # ---- --list
    if do_list:
        sessions = list_sessions()
        display_session_list(sessions)
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

    # ---- --topic (new session)
    if topic:
        _cmd_new(topic, config, mode)
        return

    # ---- No arguments: show help
    click.echo(click.get_current_context().get_help())


# ---------------------------------------------------------------------------
# Command implementations
# ---------------------------------------------------------------------------

def _cmd_new(topic: str, config: Config, mode_str: str = None):
    """Start a new session."""
    if mode_str == "deep":
        _run_deep_mode(topic, config)
    else:
        _run_scout_mode(topic, config)


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

    mode = manuscript.mode
    if mode == SessionMode.DEEP:
        from loop.deep import run_deep
        run_deep(
            topic=manuscript.topic,
            config=config,
            existing_manuscript=manuscript,
            existing_state=state,
            existing_memories=memories,
            session_id=session_id,
            injected_note=note,
        )
    else:
        # Scout sessions don't continue; switch to deep or just show result
        display_info("Scout session loaded. Switching to deep mode to continue development.")
        from loop.deep import run_deep
        run_deep(
            topic=manuscript.topic,
            config=config,
            existing_manuscript=manuscript,
            existing_state=state,
            existing_memories=memories,
            session_id=session_id,
            injected_note=note,
        )


def _cmd_export(session_id: str):
    """Export session manuscript to markdown."""
    try:
        manuscript, state, memories = load_session(session_id)
    except FileNotFoundError:
        display_error(f"Session '{session_id}' not found.")
        sys.exit(1)
    except Exception as e:
        display_error(f"Could not load session '{session_id}': {e}")
        sys.exit(1)

    from output.exporter import export_manuscript
    from pathlib import Path
    sessions_root = Path(__file__).parent / "sessions"
    session_dir = sessions_root / session_id
    out_path = export_manuscript(manuscript, session_dir)
    display_success(f"Manuscript exported to: {out_path}")


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


# ---------------------------------------------------------------------------
# Mode runners
# ---------------------------------------------------------------------------

def _run_scout_mode(topic: str, config: Config):
    """Run scout mode."""
    from loop.scout import run_scout
    try:
        result = run_scout(topic, config)
        verdict = result.get("verdict", "INTERESTING")
        session_id = result.get("session_id", "?")
        display_success(f"\nScout complete. Verdict: {verdict}. Session: {session_id}")
        display_info(f"Resume with:  python main.py --session {session_id}")
        display_info(f"Go deep with: python main.py --session {session_id} --mode deep")
    except KeyboardInterrupt:
        display_info("\nInterrupted.")
    except Exception as e:
        display_error(f"Scout session failed: {e}")
        if os.environ.get("DEBUG"):
            raise


def _run_deep_mode(topic: str, config: Config):
    """Run deep mode."""
    from loop.deep import run_deep
    try:
        result = run_deep(topic, config)
        session_id = result.get("session_id", "?")
        reason = result.get("exit_reason", "complete")
        display_success(f"\nDeep session ended: {reason}. Session: {session_id}")
        display_info(f"Export with:  python main.py --session {session_id} --export")
        display_info(f"Inspect with: python main.py --session {session_id} --inspect")
    except KeyboardInterrupt:
        display_info("\nInterrupted.")
    except Exception as e:
        display_error(f"Deep session failed: {e}")
        if os.environ.get("DEBUG"):
            raise


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    main()

import contextlib
import io
import tempfile
from pathlib import Path

from actiontrack.cli import main

SAMPLES = Path(__file__).resolve().parent.parent / "samples" / "synthetic-notes"


def run(*argv):
    """Run the CLI in-process. Returns (exit_code, stdout, stderr)."""
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        try:
            code = main(list(argv))
        except SystemExit as e:  # argparse errors
            code = e.code
    return code, out.getvalue(), err.getvalue()


def make_notes(files: dict[str, str | bytes]) -> Path:
    d = Path(tempfile.mkdtemp())
    for name, content in files.items():
        p = d / name
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(content if isinstance(content, bytes) else content.encode())
    return d


def note(date="2026-09-01", attendees="Priya Nair, Rahul Mehta, Sam Okafor", body="") -> str:
    return f"# Meeting: T\nDate: {date}\nAttendees: {attendees}\n\n## Action items\n{body}\n"


def fresh_db() -> str:
    return str(Path(tempfile.mkdtemp()) / "t.db")

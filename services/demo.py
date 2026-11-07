"""The public demo: anyone can try Clario on the example case, and it never spends money on Claude.

Switched on by the CLARIO_DEMO setting (true, 1 or yes), e.g. as a secret on Streamlit Community Cloud. In the demo
the example case replays its saved answers; uploads and anything that needs a new reading by Claude are switched off.
Off by default, so a copy run on your own computer works in full.

Each demo visitor works in their own space: a folder named by a random visitor code (kept in the page address), so
every visitor starts as if for the first time, with no saved reviews, and never sees or changes anyone else's.
"""

import os
import re
import secrets
import shutil
import time
from collections.abc import Callable
from pathlib import Path

DEMO_NOTE = ("Switched off in the public demo, which uses the example case's saved answers and never calls the AI "
             "service. Run Clario on your own computer to use it.")
VISITORS = "visitors"  # the folder, inside cases/ and reviews/, holding each demo visitor's space
VISITOR_CODE = re.compile(r"[0-9a-f]{16}")
# Asked, whenever a review is saved or read, whose space to use: the app answers from the visitor's own browser
# session, so a button's action uses the right space too. Nothing is set outside the app, e.g. in the tests.
_current_visitor: Callable[[], str | None] | None = None


def is_demo() -> bool:
    return os.environ.get("CLARIO_DEMO", "").strip().lower() in ("1", "true", "yes")


def new_visitor_code() -> str:
    return secrets.token_hex(8)


def is_visitor_code(text: str) -> bool:
    """Only a code Clario could have made: it names a folder, so nothing else (e.g. "../") is ever used."""
    return bool(VISITOR_CODE.fullmatch(text or ""))


def use_visitor_from(current_visitor: Callable[[], str | None] | None) -> None:
    """Set how to find the current visitor's code (None: no visitor spaces)."""
    global _current_visitor
    _current_visitor = current_visitor


def visitor_space(base: Path) -> Path:
    """Where to keep reviews: the visitor's own folder in the demo, else the normal folder."""
    code = _current_visitor() if _current_visitor else None
    return base / VISITORS / code if is_visitor_code(code or "") else base


def clear_old_visitors(bases: list[Path], older_than_hours: float = 24, now: float | None = None) -> list[str]:
    """Delete visitor spaces nobody has used for a while, so the demo's disk does not fill up. Returns their codes."""
    cutoff = (now or time.time()) - older_than_hours * 3600
    cleared = set()
    for base in bases:
        folder = base / VISITORS
        for space in folder.iterdir() if folder.is_dir() else []:
            if is_visitor_code(space.name) and space.is_dir() and _last_used(space) < cutoff:
                shutil.rmtree(space)
                cleared.add(space.name)
    return sorted(cleared)


def _last_used(space: Path) -> float:
    """The newest change anywhere in a visitor's space."""
    return max([space.stat().st_mtime] + [path.stat().st_mtime for path in space.rglob("*")])

"""The public demo: anyone can try Clario on the example case, and it never spends money on Claude.

Switched on by the CLARIO_DEMO setting (true, 1 or yes), e.g. as a secret on Streamlit Community Cloud. In the demo
the example case replays its saved answers; uploads and anything that needs a new reading by Claude are switched off.
Off by default, so a copy run on your own computer works in full.
"""

import os

DEMO_NOTE = ("Switched off in the public demo, which uses the example case's saved answers and never calls the AI "
             "service. Run Clario on your own computer to use it.")


def is_demo() -> bool:
    return os.environ.get("CLARIO_DEMO", "").strip().lower() in ("1", "true", "yes")

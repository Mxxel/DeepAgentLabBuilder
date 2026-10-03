"""CI never calls airouter.ch / live LLMs."""

import os
from pathlib import Path

os.environ["HOMELAB_HEURISTIC"] = "1"
os.environ["HOMELAB_CONF"] = str(Path(__file__).resolve().parent / "fixtures" / "conf.empty.yaml")

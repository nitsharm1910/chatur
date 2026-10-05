"""Dev tool: copy src/chatur/templates/* into .apm/skills/*/assets/ (ADR-0027).

Run from the repo root:  python scripts/sync_primitives.py
tests/test_primitives.py fails when the copies drift, and names this script as the fix.
"""

import shutil
from pathlib import Path

from chatur.project import SKILL_TEMPLATES

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "src" / "chatur" / "templates"

for skill, names in SKILL_TEMPLATES.items():
    assets = ROOT / ".apm" / "skills" / skill / "assets"
    assets.mkdir(parents=True, exist_ok=True)
    for name in names:
        shutil.copyfile(SOURCE / name, assets / name)
        print(f"{skill}/assets/{name}")

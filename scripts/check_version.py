"""Check that pyproject.toml and manifest.json agree on the version.

Pass a git tag (e.g. v9.7.6) to also check it matches.
"""

import json
import sys
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

pyproject = tomllib.loads((ROOT / "pyproject.toml").read_text())["project"]["version"]
manifest = json.loads(
    (ROOT / "custom_components/entity_controller/manifest.json").read_text()
)["version"]

versions = {"pyproject.toml": pyproject, "manifest.json": manifest}
if len(sys.argv) > 1:
    versions["tag"] = sys.argv[1].removeprefix("v")

if len(set(versions.values())) != 1:
    sys.exit(f"Version mismatch: {versions}")
print(f"Version {pyproject} is consistent")

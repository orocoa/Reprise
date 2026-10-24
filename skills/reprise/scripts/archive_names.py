"""Compatibility import; implementation lives in the shared Reprise core."""
from pathlib import Path
import sys
import json
base=Path(__file__).resolve().parents[1]
pointer=base/"runtime-location.json"
runtime=base/(json.loads(pointer.read_text())["path"] if pointer.is_file() else "assets/runtime")
if not (runtime/"reprise/__init__.py").exists(): runtime=base.parents[1]/"src"
sys.path.insert(0,str(runtime))
from reprise.archive_names import *

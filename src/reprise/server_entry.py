"""Trusted absolute entry for background CLI servers (never import from cwd)."""
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from reprise.cli import main

raise SystemExit(main())

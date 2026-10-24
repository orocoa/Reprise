"""Trusted absolute entry for background CLI servers (never import from cwd)."""
from pathlib import Path
import os
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
if os.environ.get('REPRISE_BUNDLE_RESOURCES'):
    sys.dont_write_bytecode = True
    from reprise.desktop_bundle import configure
    environment = configure(os.environ['REPRISE_BUNDLE_RESOURCES'])
    os.environ.clear()
    os.environ.update(environment)
from reprise.cli import main

raise SystemExit(main())

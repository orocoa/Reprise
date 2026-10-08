#!/usr/bin/env python3
"""Run Reprise directly from its source checkout; no Python packages required."""
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parent / 'src'))
from reprise.cli import main
raise SystemExit(main())

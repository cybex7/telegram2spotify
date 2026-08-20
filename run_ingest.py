#!/usr/bin/env python3
"""Stage 1 entry point: python3 run_ingest.py"""
import os, sys
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "src"))
from tg2spotify.ingest import ingest

from tg2spotify.config import export_dir
EXPORT = export_dir()
ROOT = os.path.dirname(os.path.abspath(__file__))

stats = ingest(EXPORT, os.path.join(ROOT, "state.sqlite"), os.path.join(ROOT, "reports"))
for k, v in stats.items():
    print(f"{k:14} {v}")

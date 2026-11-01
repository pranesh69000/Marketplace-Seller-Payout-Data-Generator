"""
Root entry point for the Marketplace Seller Payout Data Generator.

Allows running CLI directly without setting PYTHONPATH.
Usage:
    python run.py generate --seed 20261022 --scale 0.01 --out output/starter
    python run.py validate --data output/starter
"""

import os
import sys

# Ensure src/ is on Python module search path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "src")))

from marketplace_gen.cli import main

if __name__ == "__main__":
    main()


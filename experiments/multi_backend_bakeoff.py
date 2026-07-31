#!/usr/bin/env python3
"""DEPRECATED — use Model Output Lab instead.

  python3 experiments/model-output-lab/run_serial_compare.py --models local,zen --job smoke

See experiments/model-output-lab/README.md
"""

import sys

print(
    "DEPRECATED: multi_backend_bakeoff.py moved to the Model Output Lab.\n"
    "  python3 experiments/model-output-lab/run_serial_compare.py --models local,zen --job smoke\n"
    "See experiments/model-output-lab/README.md",
    file=sys.stderr,
)
sys.exit(2)

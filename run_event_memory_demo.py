"""Root-level entrypoint for running the IBVAP Module 5 EventMemory demonstration."""

import sys
from pathlib import Path

# Add project root to sys.path
BASE_DIR = Path(__file__).resolve().parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from ai_engine.demo_event_memory import main

if __name__ == "__main__":
    main()

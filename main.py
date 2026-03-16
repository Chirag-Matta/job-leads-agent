"""
main.py — Phase 1 orchestrator

Run:
    python main.py              # discovery + outreach
    python main.py --discover   # discovery only
    python main.py --outreach   # outreach only
"""

import sys
import logging
import argparse

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(name)s — %(message)s",
    datefmt="%H:%M:%S",
)

from agents.discovery_agent import run_discovery_agent
from agents.outreach_agent import run_outreach_agent


def main():
    parser = argparse.ArgumentParser(description="Job application agent — Phase 1")
    parser.add_argument("--discover", action="store_true", help="Run discovery only")
    parser.add_argument("--outreach", action="store_true", help="Run outreach only")
    args = parser.parse_args()

    run_discovery = not args.outreach   # default: run both
    run_outreach  = not args.discover

    print("=" * 55)
    print("  Job Agent  —  Phase 1  (Discovery + Outreach)")
    print("=" * 55)

    if run_discovery:
        print("\n── Step 1: Discovery ────────────────────────────────")
        run_discovery_agent()

    if run_outreach:
        print("\n── Step 2: Outreach ─────────────────────────────────")
        run_outreach_agent()

    print("\n✓ Run complete.")


if __name__ == "__main__":
    main()

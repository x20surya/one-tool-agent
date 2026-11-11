#!/usr/bin/env python3
"""Convenience entry point: `python chat.py [--ask "..."]`."""
from agent.cli import main

if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
"""
Main entry point for Trado Terminal
Run this file to start the terminal interface
"""

import sys
import os

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from terminal.cli import main

if __name__ == "__main__":
    main()

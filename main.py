import logging
import sys
import os

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from terminal.cli import main as terminal_main

def main():
    # Start the interactive terminal
    terminal_main()

if __name__ == "__main__":
    main()

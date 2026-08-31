"""
SparkGram — Backward Compatibility Facade Entrypoint.
Delegates to the modular sparkgram package while maintaining existing CLI entrypoint compatibility.
"""
import sys
import logging
from sparkgram.main import run_bot

if __name__ == "__main__":
    run_bot()

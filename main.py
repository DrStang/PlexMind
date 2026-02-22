#!/usr/bin/env python3
"""Entry point — delegates to CLI or web server."""
from cli import app

if __name__ == "__main__":
    app()

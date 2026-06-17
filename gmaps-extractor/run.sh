#!/bin/bash

# Ensure we run from the project root using uv
cd "$(dirname "$0")/.."

# 1. Start or Resume the overnight full Semarang scrape (5 workers, 5 keywords, headless)
uv run python gmaps-extractor/run_semarang.py

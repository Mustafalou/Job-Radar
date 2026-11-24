#!/usr/bin/env bash
# Lancé chaque matin par cron sur le Raspberry Pi
cd "$(dirname "$0")/.."
PYTHONPATH=src .venv/bin/python -m jobradar.daily >> data/daily.log 2>&1

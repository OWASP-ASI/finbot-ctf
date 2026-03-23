#!/bin/sh
set -e

echo "⏫ Running bootstrap (migrations, seeding, definitions)..."
python scripts/bootstrap.py

exec "$@"

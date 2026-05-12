#!/bin/sh
set -e

if [ "${SKIP_BOOTSTRAP:-false}" = "true" ]; then
  echo "SKIP_BOOTSTRAP=true — skipping bootstrap (scale-down / connection-exhausted deploy)"
else
  echo "Running bootstrap (migrations, seeding, definitions)..."
  python scripts/bootstrap.py || {
    echo "⚠️  Bootstrap failed — likely PG connection exhaustion during rolling deploy."
    echo "    Schema should already be at head; continuing startup."
    echo "    Set SKIP_BOOTSTRAP=true in Railway env to suppress this on next deploy."
  }
fi

exec "$@"
